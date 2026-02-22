from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

from .config import (
    BIG_ANNOUNCEMENT_DOMAINS,
    KEYWORDS,
    MAINSTREAM_DOMAINS,
    SECTION_TARGET_MAX,
    SECTION_TARGET_MIN,
    SECTIONS,
)
from .models import Article
from .utils import canonicalize_url, normalize_whitespace


def dedupe_articles(articles: list[Article]) -> list[Article]:
    unique: dict[str, Article] = {}
    for article in articles:
        key = canonicalize_url(article.url) or normalize_whitespace(article.title).lower()
        existing = unique.get(key)
        if existing is None:
            unique[key] = article
            continue
        existing_score = existing.priority + existing.metrics.get("points", 0) * 0.01
        incoming_score = article.priority + article.metrics.get("points", 0) * 0.01
        if incoming_score > existing_score:
            unique[key] = article
    return list(unique.values())


def _keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


def _recency_score(article: Article, feed_dt: datetime) -> float:
    if article.published_at is None:
        return 0.8
    delta_hours = (feed_dt - article.published_at).total_seconds() / 3600
    delta_hours = max(0.0, delta_hours)
    return max(0.0, 4.0 * math.exp(-delta_hours / 24))


def score_articles(articles: list[Article], feed_dt: datetime | None = None) -> None:
    if feed_dt is None:
        feed_dt = datetime.now(timezone.utc)
    for article in articles:
        text_blob = article.canonical_text().lower()
        scores: dict[str, float] = {}
        base = article.priority + _recency_score(article, feed_dt)
        for section in SECTIONS:
            section_score = base
            hits = _keyword_hits(text_blob, KEYWORDS.get(section.slug, []))
            section_score += hits * 1.5
            if article.section_hint == section.slug:
                section_score += 4.5
            if section.slug == "big-announcements" and article.domain in BIG_ANNOUNCEMENT_DOMAINS:
                section_score += 2.2
            if section.slug == "under-the-radar":
                if article.domain not in MAINSTREAM_DOMAINS:
                    section_score += 1.6
                else:
                    section_score -= 0.8
            if section.slug in {"engineering", "product-development"}:
                section_score += min(2.0, article.metrics.get("points", 0.0) / 150.0)
            if section.slug == "business":
                section_score += min(2.0, article.metrics.get("points", 0.0) / 220.0)
            scores[section.slug] = round(section_score, 3)
        article.scores = scores
        top_section, top_score = max(scores.items(), key=lambda item: item[1])
        article.assigned_section = top_section
        article.section_score = top_score


def _pick_candidates(
    candidates: list[Article],
    score_key: str,
    picked_ids: set[str],
    max_items: int,
    domain_cap: int = 2,
) -> list[Article]:
    selected: list[Article] = []
    domain_counts: defaultdict[str, int] = defaultdict(int)
    sorted_candidates = sorted(candidates, key=lambda item: item.scores.get(score_key, 0.0), reverse=True)
    for article in sorted_candidates:
        if len(selected) >= max_items:
            break
        if article.id in picked_ids:
            continue
        if domain_counts[article.domain] >= domain_cap:
            continue
        selected.append(article)
        picked_ids.add(article.id)
        domain_counts[article.domain] += 1
    return selected


def curate_sections(
    articles: list[Article],
    min_per_section: int = SECTION_TARGET_MIN,
    max_per_section: int = SECTION_TARGET_MAX,
    feed_dt: datetime | None = None,
) -> dict[str, list[Article]]:
    score_articles(articles, feed_dt=feed_dt)
    sections: dict[str, list[Article]] = {section.slug: [] for section in SECTIONS}
    picked_ids: set[str] = set()

    by_section: dict[str, list[Article]] = {section.slug: [] for section in SECTIONS}
    for article in articles:
        for section in SECTIONS:
            if article.scores.get(section.slug, 0.0) > 0:
                by_section[section.slug].append(article)

    for section in SECTIONS:
        picks = _pick_candidates(
            candidates=by_section[section.slug],
            score_key=section.slug,
            picked_ids=picked_ids,
            max_items=max_per_section,
        )
        sections[section.slug] = picks

    # Backfill sections that did not reach minimum target.
    for section in SECTIONS:
        if len(sections[section.slug]) >= min_per_section:
            continue
        needed = min_per_section - len(sections[section.slug])
        fallbacks = _pick_candidates(
            candidates=articles,
            score_key=section.slug,
            picked_ids=picked_ids,
            max_items=needed,
            domain_cap=3,
        )
        sections[section.slug].extend(fallbacks)

    return sections

