##########################################################################################
#
# Script name: test_feed_autodiscovery.py
#
# Description: Tests auto-discovery and persistence behavior for feeds.md updates.
#
##########################################################################################

from datetime import datetime, timezone
from pathlib import Path

from ai_news_feed import fetchers
from ai_news_feed.models import Article


def _article(article_id: str, url: str, section_hint: str, priority: float = 6.0) -> Article:
    return Article(
        id=article_id,
        title=f'Title {article_id}',
        url=url,
        summary='Summary',
        source_name='Source',
        source_type='rss',
        domain='example.com',
        published_at=datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
        priority=priority,
        tags={section_hint},
        section_hint=section_hint,
    )


def test_discover_registry_url_sources_discovers_new_domain(monkeypatch) -> None:
    sources = [{'type': 'rss', 'url': 'https://known.example/feed.xml'}]
    articles = [
        _article('1', 'https://fresh.example/post-a', 'engineering', 7.0),
        _article('2', 'https://fresh.example/post-b', 'engineering', 5.0),
        _article('3', 'https://known.example/post-c', 'business', 6.0),
    ]

    def _fake_discover(base_url: str, min_entries: int) -> tuple[str, str] | None:
        assert min_entries >= 1
        if base_url == 'https://fresh.example/':
            return 'https://fresh.example/feed', 'Fresh Example'
        return None

    monkeypatch.setenv('AUTO_DISCOVER_FEEDS', '1')
    monkeypatch.setattr(fetchers, '_discover_feed_url_for_base_url', _fake_discover)

    discovered = fetchers.discover_registry_url_sources(articles=articles, sources=sources)

    assert len(discovered) == 1
    assert discovered[0]['url'] == 'https://fresh.example/feed'
    assert discovered[0]['section_hint'] == 'engineering'
    assert 'autodiscovered' in discovered[0]['tags']


def test_discover_registry_url_sources_uses_external_candidates(monkeypatch) -> None:
    sources = [{'type': 'rss', 'url': 'https://known.example/feed.xml'}]
    articles = []

    def _fake_discover(base_url: str, min_entries: int) -> tuple[str, str] | None:
        assert min_entries >= 1
        if base_url == 'https://outside.example/':
            return 'https://outside.example/rss.xml', 'Outside Example'
        return None

    monkeypatch.setenv('AUTO_DISCOVER_FEEDS', '1')
    monkeypatch.setattr(fetchers, '_discover_feed_url_for_base_url', _fake_discover)

    discovered = fetchers.discover_registry_url_sources(
        articles=articles,
        sources=sources,
        external_candidates=[('https://outside.example/', 'outside.example', 'under-the-radar', 6.5)],
    )

    assert len(discovered) == 1
    assert discovered[0]['url'] == 'https://outside.example/rss.xml'
    assert discovered[0]['section_hint'] == 'under-the-radar'


def test_discover_web_discovery_candidates_merges_provider_results(monkeypatch) -> None:
    def _fake_google(section_slug: str, query: str, max_results: int, recency_days: int):
        assert max_results >= 2
        assert recency_days >= 1
        if section_slug == 'engineering':
            return [('https://eng.example/', 'eng.example', section_slug, 6.0)]
        return []

    def _fake_duck(section_slug: str, query: str, max_results: int):
        assert max_results >= 2
        if section_slug == 'engineering':
            return [('https://eng.example/', 'eng.example', section_slug, 5.0)]
        if section_slug == 'product-development':
            return [('https://product.example/', 'product.example', section_slug, 5.0)]
        return []

    monkeypatch.setenv('AUTO_DISCOVER_FEEDS', '1')
    monkeypatch.setenv('AUTO_DISCOVER_WEB', '1')
    monkeypatch.setenv('AUTO_DISCOVER_WEB_PROVIDER', 'all')
    monkeypatch.setattr(
        fetchers,
        '_build_discovery_queries',
        lambda: [('engineering', 'query one'), ('product-development', 'query two')],
    )
    monkeypatch.setattr(fetchers, '_search_google_news_candidates', _fake_google)
    monkeypatch.setattr(fetchers, '_search_duckduckgo_candidates', _fake_duck)

    rows = fetchers.discover_web_discovery_candidates()

    domains = {row[1] for row in rows}
    assert 'eng.example' in domains
    assert 'product.example' in domains


def test_persist_discovered_registry_sources_appends_new_url(tmp_path: Path) -> None:
    feeds_file = tmp_path / 'feeds.md'
    feeds_file.write_text(
        '\n'.join(
            [
                '# Feed Registry',
                '',
                '## 1. URLs',
                '- https://existing.example/feed.xml | name=Existing',
                '',
                '## 2. LinkedIN users',
                '',
                '## 3. X users',
                '',
                '## 4. other',
                '',
            ]
        ),
        encoding='utf-8',
    )

    discovered_sources = [
        {
            'url': 'https://existing.example/feed.xml',
            'name': 'Existing Duplicate',
            'section_hint': 'under-the-radar',
            'tags': ['under-the-radar', 'autodiscovered'],
        },
        {
            'url': 'https://new.example/feed',
            'name': 'New Feed',
            'section_hint': 'business',
            'tags': ['business', 'autodiscovered'],
        },
    ]

    added_count = fetchers.persist_discovered_registry_sources(str(feeds_file), discovered_sources)
    content = feeds_file.read_text(encoding='utf-8')

    assert added_count == 1
    assert 'https://new.example/feed' in content
    assert 'discovered=auto' in content
    assert content.count('https://existing.example/feed.xml') == 1
