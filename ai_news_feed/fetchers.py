from __future__ import annotations

import logging
from datetime import datetime, timezone

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    from dateutil import parser as date_parser
except ImportError:  # pragma: no cover
    date_parser = None

from .models import Article
from .utils import canonicalize_url, extract_domain, stable_id, strip_html

LOGGER = logging.getLogger(__name__)
USER_AGENT = "ai-news-feed-bot/1.0 (+https://github.com/)"


def load_source_config(path: str) -> list[dict]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load source configuration.")
    with open(path, "r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("config.sources must be a list")
    return sources


def parse_published(entry: dict) -> datetime | None:
    if date_parser is None:
        return None
    candidates = [
        entry.get("published"),
        entry.get("updated"),
        entry.get("created"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = date_parser.parse(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def fetch_all_sources(sources: list[dict]) -> list[Article]:
    articles: list[Article] = []
    for source in sources:
        source_type = (source.get("type") or "").lower()
        try:
            if source_type == "rss":
                articles.extend(fetch_rss_source(source))
            elif source_type == "hackernews":
                articles.extend(fetch_hackernews_source(source))
            elif source_type == "arxiv":
                articles.extend(fetch_arxiv_source(source))
            else:
                LOGGER.warning("Skipping unsupported source type: %s", source_type)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Source fetch failed for %s: %s", source.get("id"), exc)
    return articles


def _make_article(source: dict, title: str, url: str, summary: str, published_at: datetime | None, metrics: dict | None = None) -> Article:
    canonical_url = canonicalize_url(url)
    domain = extract_domain(canonical_url)
    article_id = stable_id(canonical_url or title, title)
    tags = set(source.get("tags") or [])
    return Article(
        id=article_id,
        title=strip_html(title),
        url=canonical_url,
        summary=strip_html(summary),
        source_name=source.get("name", source.get("id", "Unknown")),
        source_type=source.get("type", "unknown"),
        domain=domain,
        published_at=published_at,
        priority=float(source.get("priority", 1.0)),
        tags=tags,
        section_hint=source.get("section_hint"),
        metrics=metrics or {},
    )


def fetch_rss_source(source: dict) -> list[Article]:
    if feedparser is None:
        raise RuntimeError("feedparser is required for RSS ingestion.")
    url = source.get("url")
    if not url:
        return []
    max_items = int(source.get("max_items", 20))
    parsed = feedparser.parse(url, agent=USER_AGENT)
    if getattr(parsed, "bozo", False):
        LOGGER.warning("RSS parse warning for %s", source.get("id"))
    articles: list[Article] = []
    for entry in parsed.entries[:max_items]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        summary = entry.get("summary") or entry.get("description") or ""
        published_at = parse_published(entry)
        article = _make_article(source, title, link, summary, published_at)
        if article.url:
            articles.append(article)
    return articles


def fetch_hackernews_source(source: dict) -> list[Article]:
    if requests is None:
        raise RuntimeError("requests is required for Hacker News ingestion.")
    endpoint = source.get("endpoint", "top").strip().lower()
    max_items = int(source.get("max_items", 120))
    keywords = [item.lower() for item in source.get("keywords", [])]
    story_ids_url = f"https://hacker-news.firebaseio.com/v0/{endpoint}stories.json"
    response = requests.get(story_ids_url, timeout=15)
    response.raise_for_status()
    story_ids = response.json()[:max_items]
    articles: list[Article] = []
    for story_id in story_ids:
        item_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        item_response = requests.get(item_url, timeout=10)
        if item_response.status_code != 200:
            continue
        payload = item_response.json() or {}
        if payload.get("type") != "story":
            continue
        title = (payload.get("title") or "").strip()
        url = (payload.get("url") or "").strip()
        if not title or not url:
            continue
        blob = f"{title} {payload.get('text', '')}".lower()
        if keywords and not any(keyword in blob for keyword in keywords):
            continue
        unix_ts = payload.get("time")
        published_at = None
        if unix_ts:
            published_at = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        metrics = {
            "points": float(payload.get("score") or 0),
            "comments": float(payload.get("descendants") or 0),
        }
        article = _make_article(
            source,
            title=title,
            url=url,
            summary=payload.get("text") or "",
            published_at=published_at,
            metrics=metrics,
        )
        articles.append(article)
    return articles


def fetch_arxiv_source(source: dict) -> list[Article]:
    if feedparser is None:
        raise RuntimeError("feedparser is required for arXiv ingestion.")
    query = source.get("query", "cat:cs.AI+OR+cat:cs.LG")
    max_items = int(source.get("max_items", 40))
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query={query}&sortBy=submittedDate&sortOrder=descending&start=0&max_results={max_items}"
    )
    parsed = feedparser.parse(url, agent=USER_AGENT)
    articles: list[Article] = []
    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        url = entry.get("id", "").strip()
        summary = entry.get("summary", "").strip()
        if not title or not url:
            continue
        published_at = parse_published(entry)
        article = _make_article(source, title, url, summary, published_at)
        articles.append(article)
    return articles


def build_sample_articles() -> list[Article]:
    now = datetime.now(timezone.utc)
    templates = [
        ("Major model provider launches multimodal coding agent", "big-announcements"),
        ("Engineering team replaces flaky tests with AI-generated fixtures", "engineering"),
        ("PM team ships weekly experiments with AI-generated specs", "product-development"),
        ("Solo founder reaches $42k MRR with AI-native support desk", "business"),
        ("Tiny blog shows 10x prompt compression trick for retrieval", "under-the-radar"),
        ("AI turns childhood doodles into playable arcade games", "for-fun"),
    ]
    articles: list[Article] = []
    for idx in range(30):
        title, hint = templates[idx % len(templates)]
        url = f"https://example.com/post-{idx}"
        article = Article(
            id=stable_id(url, title),
            title=f"{title} ({idx + 1})",
            url=url,
            summary=f"Sample content for {hint}.",
            source_name="Sample Source",
            source_type="sample",
            domain="example.com",
            published_at=now,
            priority=5.0,
            tags={hint},
            section_hint=hint,
        )
        articles.append(article)
    return articles
