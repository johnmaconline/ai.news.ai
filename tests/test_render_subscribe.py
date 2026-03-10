##########################################################################################
#
# Script name: test_render_subscribe.py
#
# Description: Tests subscribe endpoint rendering in page HTML.
#
##########################################################################################

from datetime import datetime, timezone

from ai_news_feed.models import Article, DailyFeed
from ai_news_feed.render import _headline_chip_text, _render_page


def test_render_page_includes_subscribe_endpoint(monkeypatch) -> None:
    monkeypatch.setenv('NEWSLETTER_SUBSCRIBE_ENDPOINT', 'https://newsletter.example.com/subscribe')
    feed = DailyFeed(
        date='2026-03-03',
        generated_at='2026-03-03T12:00:00Z',
        title='Daily AI Feed - 2026-03-03',
        sections={},
        intro='Intro',
    )
    html = _render_page(feed, archive=[])
    assert 'data-endpoint="https://newsletter.example.com/subscribe"' in html
    assert 'id="subscribe-company"' in html


def test_render_page_includes_actionable_and_provenance_fields() -> None:
    article = Article(
        id='item-1',
        title='Practical workflow item',
        url='https://example.com/workflow',
        summary='Summary',
        source_name='Example Source',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 4, 11, 0, tzinfo=timezone.utc),
        section_score=9.2,
        summary_text='Short factual summary.',
        why_it_matters='Inference: This changes implementation priorities.',
        who_should_care='Backend platform engineers',
        suggested_action='Test the workflow in your staging repo.',
        time_to_implement='1-2h',
        evidence_quote='copilot handled the refactor in one pass',
        inference_label='inference',
        source_quality_score=7.9,
        recency_score=9.1,
        novelty_score=6.8,
        confidence_score=8.2,
        first_seen_at='2026-03-04T12:00:00+00:00',
        corroborating_urls=['https://another.example/corroborating-item'],
    )
    feed = DailyFeed(
        date='2026-03-04',
        generated_at='2026-03-04T12:00:00Z',
        title='Daily AI Feed - 2026-03-04',
        sections={'practical-prompts': [article]},
        intro='Intro',
    )
    html = _render_page(feed, archive=[])
    assert 'Featured Practical Prompts' in html
    assert 'Who should care:' in html
    assert 'Suggested action:' in html
    assert 'Time to implement:' in html
    assert '>Evidence<' in html
    assert 'Relevance 9.2' in html
    assert 'Quality 7.9' in html
    assert 'Recency 9.1' in html
    assert 'Novelty 6.8' in html
    assert 'Confidence 8.2' in html
    assert 'corroborating source' in html


def test_headline_chip_text_is_capped_to_four_words() -> None:
    article = Article(
        id='item-2',
        title='OpenAI acquires Promptfoo to secure its AI agents',
        url='https://example.com/promptfoo',
        summary='I am excited to announce Context Hub for coding agents.',
        source_name='Example Source',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
    )
    chip_text = _headline_chip_text(article)
    assert len(chip_text.split()) <= 4
    assert chip_text == 'OpenAI acquires Promptfoo to'
