##########################################################################################
#
# Script name: test_fetchers_reddit_search.py
#
# Description: Tests Reddit search source ingestion.
#
##########################################################################################

from ai_news_feed import fetchers


class _Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_fetch_reddit_search_source_parses_posts(monkeypatch) -> None:
    payload = {
        'data': {
            'children': [
                {
                    'data': {
                        'title': 'I built an AI workflow debugger',
                        'permalink': '/r/ChatGPTCoding/comments/abc123/i_built_an_ai_workflow_debugger/',
                        'selftext': 'Step-by-step implementation notes.',
                        'created_utc': 1772539200,
                        'score': 42,
                        'num_comments': 9,
                        'subreddit': 'ChatGPTCoding',
                        'subreddit_subscribers': 54321,
                    }
                }
            ]
        }
    }

    def _fake_get(endpoint: str, headers: dict, params: dict, timeout: int):
        assert endpoint == 'https://www.reddit.com/search.json'
        assert params.get('sort') == 'new'
        assert params.get('t') == 'day'
        return _Response(200, payload)

    monkeypatch.setattr(fetchers.requests, 'get', _fake_get)

    source = {
        'id': 'reddit-ai-workflows-search',
        'type': 'reddit-search',
        'name': 'Reddit AI Workflow Search',
        'query': 'ai workflow',
        'sort': 'new',
        'time': 'day',
        'max_items': 25,
        'section_hint': 'under-the-radar',
        'tags': ['under-the-radar', 'reddit'],
        'priority': 6.0,
    }
    articles = fetchers.fetch_reddit_search_source(source)

    assert len(articles) == 1
    article = articles[0]
    assert article.source_type == 'reddit'
    assert article.source_name == 'r/ChatGPTCoding'
    assert article.url.startswith('https://www.reddit.com/r/ChatGPTCoding/comments/abc123/')
    assert article.metrics.get('subreddit_subscribers') == 54321.0
