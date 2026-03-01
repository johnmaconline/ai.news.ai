##########################################################################################
#
# Script name: test_curation.py
#
# Description: Basic curation behavior tests.
#
##########################################################################################

from datetime import datetime, timezone

from ai_news_feed.curation import curate_sections, score_articles
from ai_news_feed.fetchers import build_sample_articles
from ai_news_feed.models import Article


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


def test_curate_sections_filters_items_older_than_24_hours() -> None:
    feed_dt = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    old_article = Article(
        id='old-item',
        title='Old but high score announcement',
        url='https://example.com/old',
        summary='partnership launch funding and valuation',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 2, 27, 10, 0, tzinfo=timezone.utc),
        priority=10.0,
        section_hint='big-announcements',
    )
    fresh_article = Article(
        id='fresh-item',
        title='Fresh workflow update',
        url='https://example.com/fresh',
        summary='automation workflow for small business operations',
        source_name='Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc),
        priority=5.0,
        section_hint='business',
    )
    sections = curate_sections(
        articles=[old_article, fresh_article],
        min_per_section=1,
        max_per_section=3,
        feed_dt=feed_dt,
    )
    all_ids = {item.id for picks in sections.values() for item in picks}
    assert 'old-item' not in all_ids
    assert 'fresh-item' in all_ids


def test_business_prefers_practical_over_announcement_items() -> None:
    feed_dt = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    announcement = Article(
        id='announce',
        title='OpenAI and Amazon announce strategic partnership',
        url='https://openai.com/index/partnership',
        summary='announcing partnership funding valuation and launch details',
        source_name='OpenAI News',
        source_type='rss',
        domain='openai.com',
        published_at=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
        priority=8.0,
        section_hint='big-announcements',
    )
    practical = Article(
        id='practical',
        title='How a solo founder uses AI workflows for a side hustle',
        url='https://example.com/side-hustle',
        summary='solopreneur automation workflow for customer support and operations',
        source_name='Indie Example',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 1, 9, 30, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='business',
    )
    articles = [announcement, practical]
    score_articles(articles, feed_dt=feed_dt)
    assert practical.scores['business'] > announcement.scores['business']
