from __future__ import annotations

from datetime import datetime, timezone

from ai_news_feed.curation import curate_sections
from ai_news_feed.fetchers import build_sample_articles


def test_curate_sections_hits_minimums() -> None:
    articles = build_sample_articles()
    sections = curate_sections(
        articles=articles,
        min_per_section=3,
        max_per_section=5,
        feed_dt=datetime.now(timezone.utc),
    )
    for section_slug, picks in sections.items():
        assert section_slug
        assert len(picks) >= 3
        assert len(picks) <= 5

