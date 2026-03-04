##########################################################################################
#
# Script name: test_fetchers_hackernews.py
#
# Description: Tests Hacker News source ingestion resiliency.
#
##########################################################################################

from ai_news_feed import fetchers


class _RequestException(Exception):
    pass


class _Response:
    def __init__(self, status_code: int = 200, payload=None, raise_error: Exception | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self._raise_error = raise_error

    def raise_for_status(self) -> None:
        if self._raise_error is not None:
            raise self._raise_error
        if self.status_code >= 400:
            raise _RequestException(f'http status {self.status_code}')

    def json(self):
        return self._payload


def test_fetch_hackernews_source_skips_item_request_errors(monkeypatch) -> None:
    def _fake_get(url: str, timeout: int):
        del timeout
        if url.endswith('/v0/topstories.json'):
            return _Response(status_code=200, payload=[111, 222])
        if url.endswith('/v0/item/111.json'):
            raise _RequestException('tls eof')
        if url.endswith('/v0/item/222.json'):
            return _Response(
                status_code=200,
                payload={
                    'type': 'story',
                    'title': 'LLM agent benchmark notes',
                    'url': 'https://example.com/hn-post',
                    'time': 1772539200,
                    'score': 25,
                    'descendants': 7,
                },
            )
        return _Response(status_code=404, payload={})

    monkeypatch.setattr(
        fetchers,
        'requests',
        type('Requests', (), {'get': staticmethod(_fake_get), 'RequestException': _RequestException}),
    )

    source = {
        'id': 'hackernews-ai',
        'type': 'hackernews',
        'endpoint': 'top',
        'max_items': 10,
        'priority': 6,
        'section_hint': 'engineering',
        'keywords': ['llm', 'agent'],
    }
    articles = fetchers.fetch_hackernews_source(source)

    assert len(articles) == 1
    assert articles[0].title == 'LLM agent benchmark notes'
    assert articles[0].metrics.get('points') == 25.0


def test_fetch_hackernews_source_returns_empty_when_topstories_fails(monkeypatch) -> None:
    def _fake_get(url: str, timeout: int):
        del timeout
        if url.endswith('/v0/topstories.json'):
            raise _RequestException('network failure')
        return _Response(status_code=404, payload={})

    monkeypatch.setattr(
        fetchers,
        'requests',
        type('Requests', (), {'get': staticmethod(_fake_get), 'RequestException': _RequestException}),
    )

    source = {
        'id': 'hackernews-ai',
        'type': 'hackernews',
        'endpoint': 'top',
        'max_items': 10,
    }
    articles = fetchers.fetch_hackernews_source(source)
    assert articles == []
