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
        enable_llm_curation=False,
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
        enable_llm_curation=False,
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


def test_big_announcements_prefers_high_signal_layoff_news_over_social_post() -> None:
    feed_dt = datetime(2026, 3, 3, 13, 0, tzinfo=timezone.utc)
    high_signal = Article(
        id='layoff-news',
        title='Block lays off 900 employees as AI automation expands',
        url='https://www.reuters.com/world/us/block-lays-off-workers-ai-2026-03-02/',
        summary='Block announced layoffs and workforce restructuring tied to increased AI automation.',
        source_name='Reuters',
        source_type='rss',
        domain='reuters.com',
        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
        priority=7.0,
        section_hint='big-announcements',
    )
    low_signal = Article(
        id='social-post',
        title='Thoughts on this week in AI',
        url='https://www.reddit.com/r/singularity/comments/example',
        summary='My opinion on recent AI trends.',
        source_name='r/singularity',
        source_type='reddit',
        domain='reddit.com',
        published_at=datetime(2026, 3, 3, 9, 30, tzinfo=timezone.utc),
        priority=7.0,
        section_hint='big-announcements',
    )
    score_articles([high_signal, low_signal], feed_dt=feed_dt)
    assert high_signal.scores['big-announcements'] > low_signal.scores['big-announcements']


def test_under_the_radar_prefers_smaller_social_accounts() -> None:
    feed_dt = datetime(2026, 3, 3, 13, 0, tzinfo=timezone.utc)
    small_account = Article(
        id='small-social',
        title='I built an AI test workflow in one weekend',
        url='https://x.com/smallbuilder/status/1',
        summary='Workflow notes and lessons learned for shipping faster.',
        source_name='X @smallbuilder',
        source_type='x',
        domain='x.com',
        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='under-the-radar',
        metrics={'followers': 5500, 'verified': 0.0, 'points': 30.0, 'comments': 12.0},
    )
    large_account = Article(
        id='large-social',
        title='I built an AI test workflow in one weekend',
        url='https://x.com/bigaccount/status/2',
        summary='Workflow notes and lessons learned for shipping faster.',
        source_name='X @bigaccount',
        source_type='x',
        domain='x.com',
        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
        priority=6.0,
        section_hint='under-the-radar',
        metrics={'followers': 2200000, 'verified': 1.0, 'points': 30.0, 'comments': 12.0},
    )
    score_articles([small_account, large_account], feed_dt=feed_dt)
    assert small_account.scores['under-the-radar'] > large_account.scores['under-the-radar']
