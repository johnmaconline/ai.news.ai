##########################################################################################
#
# Script name: fetchers.py
#
# Description: Fetches and normalizes source items from RSS, Hacker News, arXiv, X, and LinkedIn.
#
##########################################################################################

import logging
import os
from datetime import datetime, timezone
from urllib.parse import quote

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


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************

log = logging.getLogger(__name__)
USER_AGENT = 'ai-news-feed-bot/1.0 (+https://github.com/)'


# ****************************************************************************************
# Functions
# ****************************************************************************************


def load_source_config(path: str) -> list[dict]:
    if yaml is None:
        raise RuntimeError('PyYAML is required to load source configuration.')
    with open(path, 'r', encoding='utf-8') as handle:
        payload = yaml.safe_load(handle) or {}
    sources = payload.get('sources', [])
    if not isinstance(sources, list):
        raise ValueError('config.sources must be a list')
    return sources


def parse_published(entry: dict) -> datetime | None:
    if date_parser is None:
        return None
    candidates = [
        entry.get('published'),
        entry.get('updated'),
        entry.get('created'),
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
        source_type = (source.get('type') or '').lower()
        try:
            if source_type == 'rss':
                articles.extend(fetch_rss_source(source))
            elif source_type == 'hackernews':
                articles.extend(fetch_hackernews_source(source))
            elif source_type == 'arxiv':
                articles.extend(fetch_arxiv_source(source))
            elif source_type == 'x':
                articles.extend(fetch_x_source(source))
            elif source_type == 'linkedin':
                articles.extend(fetch_linkedin_source(source))
            else:
                log.warning('Skipping unsupported source type: %s', source_type)
        except Exception as exc:  # noqa: BLE001
            log.exception('Source fetch failed for %s: %s', source.get('id'), exc)
    return articles


def _make_article(
    source: dict,
    title: str,
    url: str,
    summary: str,
    published_at: datetime | None,
    metrics: dict | None = None,
) -> Article:
    canonical_url = canonicalize_url(url)
    domain = extract_domain(canonical_url)
    article_id = stable_id(canonical_url or title, title)
    tags = set(source.get('tags') or [])
    return Article(
        id=article_id,
        title=strip_html(title),
        url=canonical_url,
        summary=strip_html(summary),
        source_name=source.get('name', source.get('id', 'Unknown')),
        source_type=source.get('type', 'unknown'),
        domain=domain,
        published_at=published_at,
        priority=float(source.get('priority', 1.0)),
        tags=tags,
        section_hint=source.get('section_hint'),
        metrics=metrics or {},
    )


def fetch_rss_source(source: dict) -> list[Article]:
    if feedparser is None:
        raise RuntimeError('feedparser is required for RSS ingestion.')
    url = source.get('url')
    if not url:
        return []
    max_items = int(source.get('max_items', 20))
    parsed = feedparser.parse(url, agent=USER_AGENT)
    if getattr(parsed, 'bozo', False):
        log.warning('RSS parse warning for %s', source.get('id'))
    articles: list[Article] = []
    for entry in parsed.entries[:max_items]:
        title = entry.get('title', '').strip()
        link = entry.get('link', '').strip()
        if not title or not link:
            continue
        summary = entry.get('summary') or entry.get('description') or ''
        published_at = parse_published(entry)
        article = _make_article(source, title, link, summary, published_at)
        if article.url:
            articles.append(article)
    return articles


def fetch_hackernews_source(source: dict) -> list[Article]:
    if requests is None:
        raise RuntimeError('requests is required for Hacker News ingestion.')
    endpoint = source.get('endpoint', 'top').strip().lower()
    max_items = int(source.get('max_items', 120))
    keywords = [item.lower() for item in source.get('keywords', [])]
    story_ids_url = f'https://hacker-news.firebaseio.com/v0/{endpoint}stories.json'
    response = requests.get(story_ids_url, timeout=15)
    response.raise_for_status()
    story_ids = response.json()[:max_items]
    articles: list[Article] = []
    for story_id in story_ids:
        item_url = f'https://hacker-news.firebaseio.com/v0/item/{story_id}.json'
        item_response = requests.get(item_url, timeout=10)
        if item_response.status_code != 200:
            continue
        payload = item_response.json() or {}
        if payload.get('type') != 'story':
            continue
        title = (payload.get('title') or '').strip()
        url = (payload.get('url') or '').strip()
        if not title or not url:
            continue
        blob = f"{title} {payload.get('text', '')}".lower()
        if keywords and not any(keyword in blob for keyword in keywords):
            continue
        unix_ts = payload.get('time')
        published_at = None
        if unix_ts:
            published_at = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        metrics = {
            'points': float(payload.get('score') or 0),
            'comments': float(payload.get('descendants') or 0),
        }
        article = _make_article(
            source,
            title=title,
            url=url,
            summary=payload.get('text') or '',
            published_at=published_at,
            metrics=metrics,
        )
        articles.append(article)
    return articles


def fetch_arxiv_source(source: dict) -> list[Article]:
    if feedparser is None:
        raise RuntimeError('feedparser is required for arXiv ingestion.')
    query = source.get('query', 'cat:cs.AI+OR+cat:cs.LG')
    max_items = int(source.get('max_items', 40))
    url = (
        'http://export.arxiv.org/api/query?'
        f'search_query={query}&sortBy=submittedDate&sortOrder=descending&start=0&max_results={max_items}'
    )
    parsed = feedparser.parse(url, agent=USER_AGENT)
    articles: list[Article] = []
    for entry in parsed.entries:
        title = entry.get('title', '').strip()
        url = entry.get('id', '').strip()
        summary = entry.get('summary', '').strip()
        if not title or not url:
            continue
        published_at = parse_published(entry)
        article = _make_article(source, title, url, summary, published_at)
        articles.append(article)
    return articles


def _parse_datetime_value(value: str | int | float | dict | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return _parse_datetime_value(value.get('time') or value.get('created'))
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        if date_parser is not None:
            try:
                parsed = date_parser.parse(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except (ValueError, TypeError):
                return None
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _build_social_title(prefix: str, content: str, max_chars: int = 120) -> str:
    cleaned = strip_html(content)
    if not cleaned:
        return prefix
    if len(cleaned) <= max_chars:
        return f'{prefix}: {cleaned}'
    return f'{prefix}: {cleaned[: max_chars - 4].rstrip()}...'


def _extract_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            found = _extract_text(item)
            if found:
                return found
        return ''
    if isinstance(value, dict):
        preferred_keys = [
            'text',
            'commentary',
            'shareCommentary',
            'description',
            'title',
            'message',
        ]
        for key in preferred_keys:
            if key in value:
                found = _extract_text(value.get(key))
                if found:
                    return found
        for child in value.values():
            found = _extract_text(child)
            if found:
                return found
    return ''


def fetch_x_source(source: dict) -> list[Article]:
    if requests is None:
        raise RuntimeError('requests is required for X ingestion.')

    bearer_token = os.getenv('X_BEARER_TOKEN')
    if not bearer_token:
        log.warning('Skipping X source %s: X_BEARER_TOKEN is not set.', source.get('id'))
        return []

    query = (source.get('query') or '').strip()
    if not query:
        log.warning('Skipping X source %s: missing query.', source.get('id'))
        return []

    max_items = max(10, min(int(source.get('max_items', 25)), 100))
    endpoint = source.get('endpoint', 'https://api.x.com/2/tweets/search/recent')
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'User-Agent': USER_AGENT,
    }
    params = {
        'query': query,
        'max_results': max_items,
        'tweet.fields': 'created_at,public_metrics,author_id,lang',
        'user.fields': 'username,name,verified',
        'expansions': 'author_id',
    }
    response = requests.get(endpoint, headers=headers, params=params, timeout=20)
    if response.status_code >= 400:
        log.warning('X source %s request failed (%s).', source.get('id'), response.status_code)
        return []

    payload = response.json() or {}
    users_by_id = {}
    for user in payload.get('includes', {}).get('users', []):
        user_id = user.get('id')
        if user_id:
            users_by_id[user_id] = user

    articles: list[Article] = []
    for tweet in payload.get('data', []):
        tweet_id = str(tweet.get('id') or '').strip()
        text = strip_html(tweet.get('text') or '')
        if not tweet_id or not text:
            continue

        author = users_by_id.get(tweet.get('author_id')) or {}
        username = (author.get('username') or source.get('username') or '').strip()
        source_name = f'X @{username}' if username else 'X'
        url = f'https://x.com/{username}/status/{tweet_id}' if username else f'https://x.com/i/web/status/{tweet_id}'
        published_at = _parse_datetime_value(tweet.get('created_at'))
        metrics_payload = tweet.get('public_metrics') or {}
        metrics = {
            'points': float(metrics_payload.get('like_count') or 0),
            'comments': float(metrics_payload.get('reply_count') or 0),
            'reposts': float(metrics_payload.get('retweet_count') or 0),
        }
        title_prefix = f'@{username}' if username else 'X post'
        article = _make_article(
            source=source,
            title=_build_social_title(title_prefix, text),
            url=url,
            summary=text,
            published_at=published_at,
            metrics=metrics,
        )
        article.source_name = source_name
        articles.append(article)
    return articles


def _build_linkedin_url(post_id: str, fallback_url: str | None) -> str:
    if fallback_url:
        return fallback_url
    if not post_id:
        return 'https://www.linkedin.com/'
    encoded_id = quote(post_id, safe=':')
    return f'https://www.linkedin.com/feed/update/{encoded_id}/'


def fetch_linkedin_source(source: dict) -> list[Article]:
    if requests is None:
        raise RuntimeError('requests is required for LinkedIn ingestion.')

    access_token = os.getenv('LINKEDIN_ACCESS_TOKEN')
    if not access_token:
        log.warning('Skipping LinkedIn source %s: LINKEDIN_ACCESS_TOKEN is not set.', source.get('id'))
        return []

    author_urn = (source.get('author_urn') or '').strip()
    if not author_urn:
        log.warning('Skipping LinkedIn source %s: missing author_urn.', source.get('id'))
        return []

    max_items = max(5, min(int(source.get('max_items', 20)), 100))
    endpoint = source.get('endpoint', 'https://api.linkedin.com/rest/posts')
    api_version = os.getenv('LINKEDIN_API_VERSION') or source.get('api_version') or '202503'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'LinkedIn-Version': str(api_version),
        'X-Restli-Protocol-Version': '2.0.0',
        'User-Agent': USER_AGENT,
    }
    params = {
        'q': 'author',
        'author': author_urn,
        'count': max_items,
        'sortBy': 'LAST_MODIFIED',
    }
    response = requests.get(endpoint, headers=headers, params=params, timeout=20)
    if response.status_code >= 400:
        log.warning('LinkedIn source %s request failed (%s).', source.get('id'), response.status_code)
        return []

    payload = response.json() or {}
    rows = payload.get('elements') or payload.get('data') or payload.get('results') or []
    if not isinstance(rows, list):
        return []

    articles: list[Article] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        post_id = str(row.get('id') or row.get('urn') or row.get('entityUrn') or '').strip()
        text = strip_html(_extract_text(row))
        if not text:
            continue
        published_at = _parse_datetime_value(
            row.get('publishedAt')
            or row.get('lastModifiedAt')
            or row.get('createdAt')
            or row.get('firstPublishedAt')
        )
        fallback_url = row.get('permalink') or row.get('url')
        url = _build_linkedin_url(post_id, fallback_url)
        social_stats = row.get('socialDetail') or row.get('statistics') or {}
        metrics = {
            'points': float(
                social_stats.get('numLikes')
                or social_stats.get('likeCount')
                or social_stats.get('numImpressions')
                or 0
            ),
            'comments': float(social_stats.get('numComments') or social_stats.get('commentCount') or 0),
        }
        article = _make_article(
            source=source,
            title=_build_social_title('LinkedIn', text),
            url=url,
            summary=text,
            published_at=published_at,
            metrics=metrics,
        )
        articles.append(article)
    return articles


def build_sample_articles() -> list[Article]:
    now = datetime.now(timezone.utc)
    templates = [
        ('Major model provider launches multimodal coding agent', 'big-announcements'),
        ('Engineering team replaces flaky tests with AI-generated fixtures', 'engineering'),
        ('PM team ships weekly experiments with AI-generated specs', 'product-development'),
        ('Solo founder reaches $42k MRR with AI-native support desk', 'business'),
        ('Tiny blog shows 10x prompt compression trick for retrieval', 'under-the-radar'),
        ('AI turns childhood doodles into playable arcade games', 'for-fun'),
    ]
    articles: list[Article] = []
    for idx in range(30):
        title, hint = templates[idx % len(templates)]
        url = f'https://example.com/post-{idx}'
        article = Article(
            id=stable_id(url, title),
            title=f'{title} ({idx + 1})',
            url=url,
            summary=f'Sample content for {hint}.',
            source_name='Sample Source',
            source_type='sample',
            domain='example.com',
            published_at=now,
            priority=5.0,
            tags={hint},
            section_hint=hint,
        )
        articles.append(article)
    return articles
