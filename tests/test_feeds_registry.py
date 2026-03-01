##########################################################################################
#
# Script name: test_feeds_registry.py
#
# Description: Tests markdown feed registry parsing and source merge behavior.
#
##########################################################################################

from pathlib import Path

from ai_news_feed.fetchers import load_source_config


def _write_file(path: Path, content: str) -> None:
    path.write_text(content.strip() + '\n', encoding='utf-8')


def test_load_source_config_merges_feeds_registry(tmp_path: Path) -> None:
    yaml_path = tmp_path / 'sources.yaml'
    feeds_path = tmp_path / 'feeds.md'

    _write_file(
        yaml_path,
        '''
        sources:
          - id: base-rss
            type: rss
            name: Base RSS
            url: https://example.com/feed.xml
            priority: 5
            section_hint: under-the-radar
            tags: [under-the-radar]
        ''',
    )
    _write_file(
        feeds_path,
        '''
        ## 1. URLs
        - https://example.com/feed.xml | name=Duplicate RSS
        - https://another.example/rss | name=Another RSS | section=engineering

        ## 2. LinkedIN users
        - urn:li:organization:12345 | name=LinkedIn Org

        ## 3. X users
        - @example_ai
        ''',
    )

    merged = load_source_config(str(yaml_path), feeds_file=str(feeds_path))
    source_types = [source.get('type') for source in merged]
    rss_urls = [source.get('url') for source in merged if source.get('type') == 'rss']
    x_sources = [source for source in merged if source.get('type') == 'x']
    linkedin_sources = [source for source in merged if source.get('type') == 'linkedin']

    assert source_types.count('rss') == 2
    assert 'https://example.com/feed.xml' in rss_urls
    assert 'https://another.example/rss' in rss_urls
    assert len(x_sources) == 1
    assert x_sources[0].get('query') == 'from:example_ai -is:retweet -is:reply lang:en'
    assert len(linkedin_sources) == 1
    assert linkedin_sources[0].get('author_urn') == 'urn:li:organization:12345'


def test_load_source_config_skips_invalid_linkedin_registry_entry(tmp_path: Path) -> None:
    yaml_path = tmp_path / 'sources.yaml'
    feeds_path = tmp_path / 'feeds.md'

    _write_file(yaml_path, 'sources: []')
    _write_file(
        feeds_path,
        '''
        ## 2. LinkedIN users
        - not-a-linkedin-entry
        ''',
    )

    merged = load_source_config(str(yaml_path), feeds_file=str(feeds_path))
    linkedin_sources = [source for source in merged if source.get('type') == 'linkedin']

    assert linkedin_sources == []


def test_load_source_config_accepts_linkedin_profile_url_entry(tmp_path: Path) -> None:
    yaml_path = tmp_path / 'sources.yaml'
    feeds_path = tmp_path / 'feeds.md'

    _write_file(yaml_path, 'sources: []')
    _write_file(
        feeds_path,
        '''
        ## 2. LinkedIN users
        - https://www.linkedin.com/in/emollick/
        ''',
    )

    merged = load_source_config(str(yaml_path), feeds_file=str(feeds_path))
    linkedin_sources = [source for source in merged if source.get('type') == 'linkedin']

    assert len(linkedin_sources) == 1
    assert linkedin_sources[0].get('profile_url') == 'https://www.linkedin.com/in/emollick/'
    assert linkedin_sources[0].get('author_urn') == ''


def test_load_source_config_normalizes_substack_and_medium_urls(tmp_path: Path) -> None:
    yaml_path = tmp_path / 'sources.yaml'
    feeds_path = tmp_path / 'feeds.md'

    _write_file(yaml_path, 'sources: []')
    _write_file(
        feeds_path,
        '''
        ## 1. URLs
        - https://example.substack.com/p/auto-detect-substack-article | name=Auto Substack
        - https://medium.com/@auto_user/auto-post-abc123 | name=Auto Medium
        - https://latent.space/p/some-article | platform=substack | name=Latent
        - https://medium.com/@example_user/some-post-123456 | platform=medium | name=Medium Author
        - https://medium.com/towards-artificial-intelligence | platform=medium | name=TAI
        ''',
    )

    merged = load_source_config(str(yaml_path), feeds_file=str(feeds_path))
    rss_urls = sorted([source.get('url') for source in merged if source.get('type') == 'rss'])

    assert 'https://example.substack.com/feed' in rss_urls
    assert 'https://medium.com/feed/@auto_user' in rss_urls
    assert 'https://latent.space/feed' in rss_urls
    assert 'https://medium.com/feed/@example_user' in rss_urls
    assert 'https://medium.com/feed/towards-artificial-intelligence' in rss_urls
