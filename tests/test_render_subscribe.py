##########################################################################################
#
# Script name: test_render_subscribe.py
#
# Description: Tests subscribe endpoint rendering in page HTML.
#
##########################################################################################

from ai_news_feed.models import DailyFeed
from ai_news_feed.render import _render_page


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
