##########################################################################################
#
# Script name: test_fetchers_x_fallback.py
#
# Description: Tests X source fallback behavior when the X API is unavailable.
#
##########################################################################################

from ai_news_feed import fetchers


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b'', payload: dict | None = None):
        self.status_code = status_code
        self.content = content
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


def _build_rss_payload(username: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>X @{username}</title>
    <item>
      <title>Test post</title>
      <link>https://x.com/{username}/status/12345</link>
      <description>Fallback body</description>
      <pubDate>Wed, 04 Mar 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
""".encode('utf-8')


def test_fetch_x_source_uses_rss_fallback_on_api_forbidden(monkeypatch) -> None:
    def _fake_get(url: str, headers=None, params=None, timeout: int = 0):
        del headers, params, timeout
        if 'api.x.com/2/tweets/search/recent' in url:
            return _FakeResponse(status_code=403, payload={'title': 'Client Forbidden'})
        if 'nitter.net/swyx/rss' in url:
            return _FakeResponse(status_code=200, content=_build_rss_payload('swyx'))
        return _FakeResponse(status_code=404)

    monkeypatch.setenv('X_BEARER_TOKEN', 'token')
    monkeypatch.setattr(fetchers, 'requests', type('Requests', (), {'get': staticmethod(_fake_get), 'RequestException': Exception}))

    articles = fetchers.fetch_x_source(
        {
            'id': 'x-test-swyx',
            'type': 'x',
            'query': 'from:swyx -is:retweet',
            'username': 'swyx',
            'max_items': 10,
        }
    )

    assert len(articles) == 1
    assert articles[0].url == 'https://x.com/swyx/status/12345'
    assert articles[0].source_name == 'X @swyx'
    assert articles[0].title == 'Fallback body'


def test_fetch_x_source_uses_rss_fallback_when_token_missing(monkeypatch) -> None:
    def _fake_get(url: str, headers=None, params=None, timeout: int = 0):
        del headers, params, timeout
        if 'nitter.net/openai/rss' in url:
            return _FakeResponse(status_code=200, content=_build_rss_payload('openai'))
        return _FakeResponse(status_code=404)

    monkeypatch.delenv('X_BEARER_TOKEN', raising=False)
    monkeypatch.setattr(fetchers, 'requests', type('Requests', (), {'get': staticmethod(_fake_get), 'RequestException': Exception}))

    articles = fetchers.fetch_x_source(
        {
            'id': 'x-test-openai',
            'type': 'x',
            'query': 'from:openai -is:retweet',
            'username': 'openai',
            'max_items': 10,
        }
    )

    assert len(articles) == 1
    assert articles[0].url == 'https://x.com/openai/status/12345'
    assert articles[0].source_name == 'X @openai'
    assert articles[0].title == 'Fallback body'


def test_fetch_x_source_builds_short_headline_from_api_text(monkeypatch) -> None:
    def _fake_get(url: str, headers=None, params=None, timeout: int = 0):
        del headers, params, timeout
        if 'api.x.com/2/tweets/search/recent' not in url:
            return _FakeResponse(status_code=404)
        return _FakeResponse(
            status_code=200,
            payload={
                'data': [
                    {
                        'id': '98765',
                        'text': "I'm excited to announce Context Hub, an open tool that gives your coding agent up-to-date API docs. Install it and prompt your agent to use it.",
                        'author_id': '42',
                        'created_at': '2026-03-10T10:00:00Z',
                        'public_metrics': {
                            'like_count': 10,
                            'reply_count': 2,
                            'retweet_count': 3,
                        },
                    }
                ],
                'includes': {
                    'users': [
                        {
                            'id': '42',
                            'username': 'andrewyng',
                            'name': 'Andrew Ng',
                            'verified': True,
                            'public_metrics': {'followers_count': 1000},
                        }
                    ]
                },
            },
        )

    monkeypatch.setenv('X_BEARER_TOKEN', 'token')
    monkeypatch.setattr(fetchers, 'requests', type('Requests', (), {'get': staticmethod(_fake_get), 'RequestException': Exception}))

    articles = fetchers.fetch_x_source(
        {
            'id': 'x-test-andrewyng',
            'type': 'x',
            'query': 'from:andrewyng -is:retweet',
            'username': 'andrewyng',
            'max_items': 10,
        }
    )

    assert len(articles) == 1
    assert articles[0].title == 'Context Hub'
    assert articles[0].summary.startswith("I'm excited to announce Context Hub")
