##########################################################################################
#
# Script name: fetchers.py
#
# Description: Fetches and normalizes source items from RSS, Hacker News, arXiv, X, and LinkedIn.
#
##########################################################################################

import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    from dateutil import parser as date_parser
except ImportError:  # pragma: no cover
    date_parser = None

from .models import Article
from .utils import canonicalize_url, extract_domain, stable_id, strip_html


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************

log = logging.getLogger(__name__)
USER_AGENT = 'ai-news-feed-bot/1.0 (+https://github.com/)'
DEFAULT_FEEDS_FILE = 'config/feeds.md'
AUTO_DISCOVER_DISABLE_VALUES = {'0', 'false', 'no', 'off', 'disabled'}
AUTO_DISCOVER_PATH_GUESSES = (
    '/feed',
    '/rss',
    '/rss.xml',
    '/feed.xml',
    '/atom.xml',
    '/index.xml',
)
AUTO_DISCOVER_IGNORED_DOMAINS = {
    'x.com',
    'www.x.com',
    'twitter.com',
    'www.twitter.com',
    'linkedin.com',
    'www.linkedin.com',
    'news.ycombinator.com',
    'arxiv.org',
    'www.arxiv.org',
    'github.com',
    'www.github.com',
}
AUTO_DISCOVER_REDDIT_EXCLUDED_SUBREDDITS = {
    'all',
    'popular',
    'announcements',
    'news',
}
WEB_DISCOVERY_QUERIES = {
    'big-announcements': [
        'AI layoffs announced',
        'AI model launch announced',
        'AI partnership announced enterprise',
        'AI policy regulation announcement',
    ],
    'engineering': [
        'agentic engineering workflow blog',
        'LLM eval framework engineering',
        'AI coding benchmark developer tools',
    ],
    'product-development': [
        'AI product workflow experimentation',
        'PM AI product development case study',
        'AI feature design launch playbook',
    ],
    'business': [
        'AI coding agent tutorial workflow',
        'software developer AI automation guide',
        'developer productivity AI implementation',
    ],
    'under-the-radar': [
        'indie AI engineering blog',
        'small AI lab blog notes',
        'niche AI workflow writeup',
        'site:substack.com AI engineering workflow',
        'site:substack.com "I built" AI',
        'site:reddit.com/r AI workflow tutorial',
        'site:dev.to AI agent workflow',
        'site:reddit.com/r/ChatGPTCoding AI coding workflow',
        'site:reddit.com/r/LocalLLaMA project writeup',
        'site:x.com AI engineer "I built"',
        'site:linkedin.com/in AI software engineer workflow',
    ],
    'for-fun': [
        'creative AI project demo',
        'weird AI experiment',
        'AI game build log',
    ],
}


# ****************************************************************************************
# Functions
# ****************************************************************************************


def _normalize_feeds_section(line: str) -> str | None:
    if not line.startswith('#'):
        return None
    normalized = line.lstrip('#').strip().lower()
    normalized = re.sub(r'^\d+\.\s*', '', normalized)
    normalized = normalized.replace('_', ' ')
    normalized = ' '.join(normalized.split())
    if normalized in {'urls', 'url', 'feeds', 'rss'}:
        return 'urls'
    if normalized in {'linkedin users', 'linkedin', 'linkedin profiles'}:
        return 'linkedin-users'
    if normalized in {'x users', 'x', 'twitter users', 'twitter'}:
        return 'x-users'
    if normalized in {'other', 'notes', 'misc'}:
        return 'other'
    return None


def _parse_markdown_list_item(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith('- '):
        return stripped[2:].strip()
    if stripped.startswith('* '):
        return stripped[2:].strip()
    return ''


def _parse_registry_entry(raw_entry: str) -> tuple[str, dict]:
    parts = [part.strip() for part in raw_entry.split('|') if part.strip()]
    if not parts:
        return '', {}
    primary = parts[0]
    metadata: dict[str, str] = {}
    for part in parts[1:]:
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        key = key.strip().lower().replace(' ', '_')
        value = value.strip()
        if key and value:
            metadata[key] = value
    return primary, metadata


def _parse_registry_tags(metadata: dict) -> list[str]:
    tags_raw = metadata.get('tags', '')
    if not tags_raw:
        return []
    return [tag.strip() for tag in tags_raw.split(',') if tag.strip()]


def _safe_float(metadata: dict, key: str, default: float) -> float:
    value = metadata.get(key)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _safe_int(metadata: dict, key: str, default: int) -> int:
    value = metadata.get(key)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _detect_registry_platform(cleaned_url: str, metadata: dict) -> str:
    explicit = (metadata.get('platform') or '').strip().lower()
    if explicit in {'substack', 'medium'}:
        return explicit
    parsed = urlparse(cleaned_url)
    domain = parsed.netloc.lower()
    if domain.endswith('substack.com'):
        return 'substack'
    if domain.endswith('medium.com'):
        return 'medium'
    return ''


def _normalize_registry_rss_url(url: str, metadata: dict) -> str:
    cleaned_url = canonicalize_url(url)
    if not cleaned_url:
        return ''

    parsed = urlparse(cleaned_url)
    scheme = parsed.scheme or 'https'
    domain = parsed.netloc.lower()
    path = parsed.path or ''
    normalized_path = path.rstrip('/')
    lowered_path = normalized_path.lower()

    if (
        lowered_path.endswith('/feed')
        or lowered_path.endswith('.xml')
        or lowered_path.endswith('/rss')
        or lowered_path.endswith('/rss.xml')
        or lowered_path.endswith('/atom.xml')
    ):
        return cleaned_url

    platform = _detect_registry_platform(cleaned_url, metadata)
    if platform == 'substack':
        return canonicalize_url(f'{scheme}://{domain}/feed')

    if platform == 'medium':
        segments = [segment for segment in normalized_path.split('/') if segment]
        if not segments:
            return canonicalize_url(f'{scheme}://{domain}/feed')
        if segments[0] == 'feed':
            return cleaned_url
        if segments[0].startswith('@'):
            return canonicalize_url(f'{scheme}://{domain}/feed/{segments[0]}')
        if segments[0] == 'p':
            return canonicalize_url(f'{scheme}://{domain}/feed')
        return canonicalize_url(f'{scheme}://{domain}/feed/{segments[0]}')

    return cleaned_url


def _registry_slug(value: str) -> str:
    lower = value.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', lower).strip('-')
    return slug or 'source'


def _extract_x_username(value: str) -> str:
    username = value.strip()
    if username.startswith('@'):
        username = username[1:]
    if username.startswith('https://x.com/'):
        username = username.replace('https://x.com/', '', 1)
    if username.startswith('http://x.com/'):
        username = username.replace('http://x.com/', '', 1)
    if username.startswith('https://twitter.com/'):
        username = username.replace('https://twitter.com/', '', 1)
    if username.startswith('http://twitter.com/'):
        username = username.replace('http://twitter.com/', '', 1)
    username = username.split('/', 1)[0].split('?', 1)[0].split('#', 1)[0]
    if re.fullmatch(r'[A-Za-z0-9_]{1,15}', username or ''):
        return username
    return ''


def _extract_reddit_subreddit(path: str) -> str:
    path_value = (path or '').strip()
    match = re.match(r'^/r/([A-Za-z0-9_]+)/', path_value)
    if not match:
        return ''
    return match.group(1)


def _extract_linkedin_profile_url(value: str) -> str:
    cleaned = value.strip()
    lowered = cleaned.lower()
    if lowered.startswith('https://www.linkedin.com/in/') or lowered.startswith('http://www.linkedin.com/in/'):
        return canonicalize_url(cleaned)
    if lowered.startswith('https://linkedin.com/in/') or lowered.startswith('http://linkedin.com/in/'):
        return canonicalize_url(cleaned)
    if lowered.startswith('https://www.linkedin.com/company/') or lowered.startswith('http://www.linkedin.com/company/'):
        return canonicalize_url(cleaned)
    if lowered.startswith('https://linkedin.com/company/') or lowered.startswith('http://linkedin.com/company/'):
        return canonicalize_url(cleaned)
    return ''


def _parse_feeds_registry(path: str) -> dict[str, list[tuple[str, dict]]]:
    registry: dict[str, list[tuple[str, dict]]] = {
        'urls': [],
        'linkedin-users': [],
        'x-users': [],
        'other': [],
    }
    if not os.path.exists(path):
        return registry

    current_section = ''
    with open(path, 'r', encoding='utf-8') as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith('<!--'):
                continue
            section = _normalize_feeds_section(line)
            if section:
                current_section = section
                continue
            if not current_section:
                continue
            item = _parse_markdown_list_item(line)
            if not item:
                continue
            primary, metadata = _parse_registry_entry(item)
            if not primary:
                continue
            registry[current_section].append((primary, metadata))
    return registry


def _build_registry_url_source(url: str, metadata: dict, idx: int) -> dict | None:
    cleaned_url = _normalize_registry_rss_url(url, metadata)
    if not cleaned_url:
        return None
    name = metadata.get('name') or extract_domain(cleaned_url) or f'Registry URL {idx}'
    section_hint = metadata.get('section_hint') or metadata.get('section') or 'under-the-radar'
    source_id = metadata.get('id') or f'feeds-md-url-{_registry_slug(name)}-{idx}'
    source = {
        'id': source_id,
        'type': 'rss',
        'name': name,
        'url': cleaned_url,
        'priority': _safe_float(metadata, 'priority', 6.0),
        'section_hint': section_hint,
        'tags': _parse_registry_tags(metadata) or ['under-the-radar', 'registry'],
        'max_items': _safe_int(metadata, 'max_items', 20),
    }
    return source


def _build_registry_x_source(entry: str, metadata: dict, idx: int) -> dict | None:
    username = _extract_x_username(entry)
    if not username:
        log.warning('feeds.md x-users entry is invalid: %s', entry)
        return None
    section_hint = metadata.get('section_hint') or metadata.get('section') or 'under-the-radar'
    source_id = metadata.get('id') or f'feeds-md-x-{_registry_slug(username)}-{idx}'
    source = {
        'id': source_id,
        'type': 'x',
        'name': metadata.get('name') or f'X @{username}',
        'username': username,
        'query': metadata.get('query') or f'from:{username} -is:retweet -is:reply lang:en',
        'priority': _safe_float(metadata, 'priority', 5.0),
        'section_hint': section_hint,
        'tags': _parse_registry_tags(metadata) or ['under-the-radar', 'social'],
        'max_items': _safe_int(metadata, 'max_items', 20),
    }
    return source


def _build_registry_linkedin_source(entry: str, metadata: dict, idx: int) -> dict | None:
    author_urn = (metadata.get('author_urn') or '').strip()
    profile_url = _extract_linkedin_profile_url(entry)

    if not author_urn:
        raw_entry = entry.strip()
        if raw_entry.startswith('urn:li:'):
            author_urn = raw_entry
        elif profile_url:
            author_urn = ''
        else:
            log.warning('feeds.md linkedin-users entry must be LinkedIn URN or profile URL: %s', entry)
            return None

    section_hint = metadata.get('section_hint') or metadata.get('section') or 'under-the-radar'
    slug_basis = author_urn or profile_url
    source_id = metadata.get('id') or f'feeds-md-linkedin-{_registry_slug(slug_basis)}-{idx}'
    default_name = metadata.get('name')
    if not default_name:
        if author_urn:
            default_name = f'LinkedIn {author_urn.split(":")[-1]}'
        else:
            default_name = f'LinkedIn {profile_url.rsplit("/", 2)[-2] if "/" in profile_url else "profile"}'
    source = {
        'id': source_id,
        'type': 'linkedin',
        'name': default_name,
        'author_urn': author_urn,
        'profile_url': profile_url,
        'priority': _safe_float(metadata, 'priority', 5.0),
        'section_hint': section_hint,
        'tags': _parse_registry_tags(metadata) or ['under-the-radar', 'social'],
        'max_items': _safe_int(metadata, 'max_items', 20),
    }
    return source


def _source_signature(source: dict) -> str:
    source_type = (source.get('type') or '').strip().lower()
    if source_type == 'rss':
        return f'rss:{canonicalize_url(source.get("url") or "")}'
    if source_type == 'x':
        query = (source.get('query') or '').strip().lower()
        return f'x:{query}'
    if source_type == 'linkedin':
        author = (source.get('author_urn') or '').strip().lower()
        if author:
            return f'linkedin:{author}'
        profile_url = canonicalize_url(source.get('profile_url') or '').lower()
        return f'linkedin-profile:{profile_url}'
    if source_type == 'arxiv':
        query = (source.get('query') or '').strip().lower()
        return f'arxiv:{query}'
    if source_type == 'hackernews':
        endpoint = (source.get('endpoint') or 'top').strip().lower()
        return f'hackernews:{endpoint}'
    return f'{source_type}:{(source.get("id") or "").strip().lower()}'


def _merge_sources(base_sources: list[dict], extra_sources: list[dict]) -> list[dict]:
    merged = list(base_sources)
    seen = {_source_signature(source) for source in base_sources}
    for source in extra_sources:
        signature = _source_signature(source)
        if signature in seen:
            continue
        merged.append(source)
        seen.add(signature)
    return merged


def _load_registry_sources(feeds_file: str) -> list[dict]:
    registry = _parse_feeds_registry(feeds_file)
    sources: list[dict] = []

    for idx, (entry, metadata) in enumerate(registry['urls'], start=1):
        source = _build_registry_url_source(entry, metadata, idx)
        if source:
            sources.append(source)

    for idx, (entry, metadata) in enumerate(registry['linkedin-users'], start=1):
        source = _build_registry_linkedin_source(entry, metadata, idx)
        if source:
            sources.append(source)

    for idx, (entry, metadata) in enumerate(registry['x-users'], start=1):
        source = _build_registry_x_source(entry, metadata, idx)
        if source:
            sources.append(source)

    return sources


def load_source_config(path: str, feeds_file: str = DEFAULT_FEEDS_FILE) -> list[dict]:
    if yaml is None:
        raise RuntimeError('PyYAML is required to load source configuration.')
    with open(path, 'r', encoding='utf-8') as handle:
        payload = yaml.safe_load(handle) or {}
    sources = payload.get('sources', [])
    if not isinstance(sources, list):
        raise ValueError('config.sources must be a list')
    registry_sources = _load_registry_sources(feeds_file)
    if registry_sources:
        merged_sources = _merge_sources(sources, registry_sources)
        log.info(
            'Loaded %s source(s) from %s (%s total configured source(s)).',
            len(registry_sources),
            feeds_file,
            len(merged_sources),
        )
        return merged_sources
    return sources


def _safe_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = (os.getenv(name) or '').strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def _is_auto_discovery_enabled() -> bool:
    raw_value = (os.getenv('AUTO_DISCOVER_FEEDS') or '1').strip().lower()
    return raw_value not in AUTO_DISCOVER_DISABLE_VALUES


def _is_auto_web_discovery_enabled() -> bool:
    raw_value = (os.getenv('AUTO_DISCOVER_WEB') or '1').strip().lower()
    return raw_value not in AUTO_DISCOVER_DISABLE_VALUES


def _build_discovery_queries() -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []
    for section_slug, query_list in WEB_DISCOVERY_QUERIES.items():
        for query in query_list:
            queries.append((section_slug, query))
    max_queries = _safe_env_int('AUTO_DISCOVER_WEB_MAX_QUERIES', default=18, minimum=1, maximum=80)
    return queries[:max_queries]


def _resolve_candidate_base(url: str) -> tuple[str, str] | None:
    canonical_url = canonicalize_url(url)
    if not canonical_url:
        return None
    parsed = urlparse(canonical_url)
    if parsed.scheme not in {'http', 'https'}:
        return None
    domain = (parsed.netloc or '').lower()
    if not domain or domain in AUTO_DISCOVER_IGNORED_DOMAINS:
        return None
    if domain.endswith('reddit.com'):
        subreddit = _extract_reddit_subreddit(parsed.path)
        if not subreddit:
            return None
        lowered = subreddit.lower()
        if lowered in AUTO_DISCOVER_REDDIT_EXCLUDED_SUBREDDITS:
            return None
        rss_url = f'https://www.reddit.com/r/{subreddit}/.rss'
        return rss_url, f'reddit.com/r/{lowered}'
    return f'{parsed.scheme}://{domain}/', domain


def _search_google_news_candidates(
    section_slug: str,
    query: str,
    max_results: int,
    recency_days: int,
) -> list[tuple[str, str, str, float]]:
    if feedparser is None:
        return []
    encoded_query = quote(f'{query} when:{recency_days}d', safe='')
    rss_url = (
        f'https://news.google.com/rss/search?q={encoded_query}'
        '&hl=en-US&gl=US&ceid=US:en'
    )
    parsed = feedparser.parse(rss_url, agent=USER_AGENT)
    rows: list[tuple[str, str, str, float]] = []
    for entry in parsed.entries[:max_results]:
        source = entry.get('source') or {}
        source_href = ''
        if isinstance(source, dict):
            source_href = (source.get('href') or '').strip()
        if not source_href:
            source_href = (entry.get('link') or '').strip()
        resolved = _resolve_candidate_base(source_href)
        if not resolved:
            continue
        base_url, domain = resolved
        rows.append((base_url, domain, section_slug, 6.0))
    return rows


def _extract_ddg_target_url(href: str) -> str:
    cleaned = href.strip()
    if not cleaned:
        return ''
    if cleaned.startswith('//'):
        cleaned = f'https:{cleaned}'
    absolute = urljoin('https://duckduckgo.com', cleaned)
    parsed = urlparse(absolute)
    if parsed.netloc.lower().endswith('duckduckgo.com'):
        params = parse_qs(parsed.query)
        uddg_values = params.get('uddg') or []
        if uddg_values:
            return unquote(uddg_values[0])
    return absolute


def _search_duckduckgo_candidates(
    section_slug: str,
    query: str,
    max_results: int,
) -> list[tuple[str, str, str, float]]:
    if requests is None:
        return []
    try:
        response = requests.get(
            'https://duckduckgo.com/html/',
            params={'q': query},
            headers={'User-Agent': USER_AGENT},
            timeout=20,
        )
    except requests.RequestException:
        return []
    if response.status_code >= 400:
        return []
    rows: list[tuple[str, str, str, float]] = []
    seen_domains: set[str] = set()
    html = response.text[:500000]
    pattern = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"',
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        href = match.group(1).strip()
        target_url = _extract_ddg_target_url(href)
        resolved = _resolve_candidate_base(target_url)
        if not resolved:
            continue
        base_url, domain = resolved
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        rows.append((base_url, domain, section_slug, 5.0))
        if len(rows) >= max_results:
            break
    return rows


def discover_web_discovery_candidates() -> list[tuple[str, str, str, float]]:
    if not _is_auto_discovery_enabled() or not _is_auto_web_discovery_enabled():
        return []
    queries = _build_discovery_queries()
    if not queries:
        return []
    max_results_per_query = _safe_env_int(
        'AUTO_DISCOVER_WEB_MAX_RESULTS_PER_QUERY',
        default=8,
        minimum=2,
        maximum=20,
    )
    recency_days = _safe_env_int('AUTO_DISCOVER_WEB_RECENCY_DAYS', default=2, minimum=1, maximum=7)
    provider_mode = (os.getenv('AUTO_DISCOVER_WEB_PROVIDER') or 'all').strip().lower()
    use_google_news = provider_mode in {'all', 'google-news', 'google', 'news'}
    use_duckduckgo = provider_mode in {'all', 'duckduckgo', 'ddg'}

    merged: dict[str, tuple[str, str, str, float]] = {}
    for section_slug, query in queries:
        candidates: list[tuple[str, str, str, float]] = []
        if use_google_news:
            candidates.extend(
                _search_google_news_candidates(
                    section_slug=section_slug,
                    query=query,
                    max_results=max_results_per_query,
                    recency_days=recency_days,
                )
            )
        if use_duckduckgo:
            candidates.extend(
                _search_duckduckgo_candidates(
                    section_slug=section_slug,
                    query=query,
                    max_results=max_results_per_query,
                )
            )
        for base_url, domain, hint, priority in candidates:
            existing = merged.get(domain)
            if existing is None or priority > existing[3]:
                merged[domain] = (base_url, domain, hint, priority)
    rows = sorted(merged.values(), key=lambda item: item[3], reverse=True)
    max_candidates = _safe_env_int('AUTO_DISCOVER_WEB_MAX_CANDIDATES', default=120, minimum=10, maximum=500)
    rows = rows[:max_candidates]
    if rows:
        log.info('Web discovery found %s candidate domain(s).', len(rows))
    return rows


def _extract_feed_links_from_html(html: str, page_url: str) -> list[str]:
    if not html:
        return []
    links: list[str] = []
    for match in re.finditer(r'<link\b[^>]*>', html, flags=re.IGNORECASE):
        tag = match.group(0)
        lowered = tag.lower()
        if 'href=' not in lowered:
            continue
        if 'rss' not in lowered and 'atom' not in lowered and 'application/xml' not in lowered:
            continue
        href_match = re.search(r'href\s*=\s*[\'"]([^\'"]+)[\'"]', tag, flags=re.IGNORECASE)
        if not href_match:
            continue
        href = href_match.group(1).strip()
        if not href:
            continue
        resolved = canonicalize_url(urljoin(page_url, href))
        if resolved:
            links.append(resolved)
    return links


def _validate_feed_url(url: str, min_entries: int) -> tuple[str, str] | None:
    if feedparser is None:
        return None
    parsed = feedparser.parse(url, agent=USER_AGENT)
    status = getattr(parsed, 'status', None)
    if status is not None and int(status) >= 400:
        return None
    entries = getattr(parsed, 'entries', []) or []
    if len(entries) < min_entries:
        return None
    feed_title = strip_html((parsed.feed.get('title') or '').strip())
    feed_url = canonicalize_url(url)
    if not feed_url:
        return None
    return feed_url, feed_title


def _discover_feed_url_for_base_url(base_url: str, min_entries: int) -> tuple[str, str] | None:
    if requests is None:
        return None
    direct_validated = _validate_feed_url(base_url, min_entries=min_entries)
    if direct_validated:
        return direct_validated
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    candidate_urls: list[str] = []
    page_url = base_url
    try:
        response = requests.get(base_url, headers=headers, timeout=12)
        if response.status_code < 400:
            page_url = response.url or base_url
            candidate_urls.extend(_extract_feed_links_from_html(response.text[:400000], page_url))
    except requests.RequestException:
        pass

    parsed = urlparse(page_url)
    scheme = parsed.scheme or 'https'
    domain = parsed.netloc.lower()
    if not domain:
        return None
    for path in AUTO_DISCOVER_PATH_GUESSES:
        candidate_urls.append(canonicalize_url(f'{scheme}://{domain}{path}'))

    seen: set[str] = set()
    for candidate in candidate_urls:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        validated = _validate_feed_url(candidate, min_entries=min_entries)
        if validated:
            return validated
    return None


def _resolve_article_base_url(article: Article) -> tuple[str, str] | None:
    canonical_url = canonicalize_url(article.url)
    if not canonical_url:
        return None
    parsed = urlparse(canonical_url)
    if parsed.scheme not in {'http', 'https'}:
        return None
    domain = (parsed.netloc or '').lower()
    if not domain:
        return None
    if domain in AUTO_DISCOVER_IGNORED_DOMAINS:
        return None
    if domain.endswith('reddit.com'):
        subreddit = _extract_reddit_subreddit(parsed.path)
        if not subreddit:
            return None
        lowered = subreddit.lower()
        if lowered in AUTO_DISCOVER_REDDIT_EXCLUDED_SUBREDDITS:
            return None
        rss_url = f'https://www.reddit.com/r/{subreddit}/.rss'
        return rss_url, f'reddit.com/r/{lowered}'
    return f'{parsed.scheme}://{domain}/', domain


def _collect_discovery_candidates(
    articles: list[Article],
    existing_domains: set[str],
    max_domains: int,
) -> list[tuple[str, str, str, float]]:
    by_domain: dict[str, dict] = {}
    for article in articles:
        resolved = _resolve_article_base_url(article)
        if not resolved:
            continue
        base_url, domain = resolved
        if domain in existing_domains:
            continue
        payload = by_domain.setdefault(
            domain,
            {
                'base_url': base_url,
                'count': 0,
                'max_priority': 0.0,
                'section_counter': Counter(),
            },
        )
        payload['count'] += 1
        payload['max_priority'] = max(payload['max_priority'], float(article.priority or 0.0))
        section_hint = (article.section_hint or '').strip()
        if section_hint:
            payload['section_counter'][section_hint] += 1

    ranked = sorted(
        by_domain.values(),
        key=lambda item: (item['max_priority'], item['count']),
        reverse=True,
    )
    candidates: list[tuple[str, str, str, float]] = []
    for item in ranked[:max_domains]:
        counter = item['section_counter']
        section_hint = counter.most_common(1)[0][0] if counter else 'under-the-radar'
        candidates.append((item['base_url'], item['base_url'].split('//', 1)[-1].rstrip('/'), section_hint, item['max_priority']))
    return candidates


def discover_registry_url_sources(
    articles: list[Article],
    sources: list[dict],
    external_candidates: list[tuple[str, str, str, float]] | None = None,
) -> list[dict]:
    if not _is_auto_discovery_enabled():
        log.info('Auto-discovery disabled via AUTO_DISCOVER_FEEDS.')
        return []
    if feedparser is None or requests is None:
        log.warning('Auto-discovery skipped: feedparser/requests dependencies are unavailable.')
        return []
    if not articles and not external_candidates:
        return []

    max_domains = _safe_env_int('AUTO_DISCOVER_MAX_DOMAINS', default=40, minimum=5, maximum=200)
    max_new_feeds = _safe_env_int('AUTO_DISCOVER_MAX_NEW_FEEDS', default=8, minimum=1, maximum=50)
    min_entries = _safe_env_int('AUTO_DISCOVER_MIN_FEED_ENTRIES', default=5, minimum=1, maximum=100)

    existing_urls: set[str] = set()
    existing_domains: set[str] = set()
    for source in sources:
        if (source.get('type') or '').lower() != 'rss':
            continue
        source_url = canonicalize_url(source.get('url') or '')
        if not source_url:
            continue
        existing_urls.add(source_url)
        source_domain = extract_domain(source_url).lower()
        if source_domain:
            existing_domains.add(source_domain)

    discovered: list[dict] = []
    discovered_urls: set[str] = set()
    merged_candidates: dict[str, tuple[str, str, str, float]] = {}
    for base_url, domain, section_hint, max_priority in _collect_discovery_candidates(
        articles,
        existing_domains=existing_domains,
        max_domains=max_domains,
    ):
        merged_candidates[domain] = (base_url, domain, section_hint, max_priority)
    for candidate in external_candidates or []:
        base_url, domain, section_hint, max_priority = candidate
        if domain in existing_domains:
            continue
        existing = merged_candidates.get(domain)
        if existing is None or max_priority > existing[3]:
            merged_candidates[domain] = (base_url, domain, section_hint, max_priority)

    candidates = sorted(merged_candidates.values(), key=lambda item: item[3], reverse=True)
    for base_url, domain, section_hint, max_priority in candidates:
        if len(discovered) >= max_new_feeds:
            break
        discovered_feed = _discover_feed_url_for_base_url(base_url, min_entries=min_entries)
        if not discovered_feed:
            continue
        feed_url, feed_title = discovered_feed
        feed_domain = extract_domain(feed_url).lower()
        if feed_url in existing_urls or feed_url in discovered_urls or feed_domain in existing_domains:
            continue
        name = (feed_title or domain).strip() or domain
        source_id = f'feeds-md-autodiscovered-{_registry_slug(domain)}'
        section = section_hint or 'under-the-radar'
        tags = [section, 'autodiscovered', 'under-the-radar']
        source = {
            'id': source_id,
            'type': 'rss',
            'name': name,
            'url': feed_url,
            'priority': max(4.0, min(max_priority, 7.0)),
            'section_hint': section,
            'tags': sorted(set(tags)),
            'max_items': 20,
        }
        discovered.append(source)
        discovered_urls.add(feed_url)
        existing_domains.add(feed_domain)

    if discovered:
        log.info('Auto-discovery found %s new RSS source(s).', len(discovered))
    return discovered


def _ensure_registry_file(path: str) -> None:
    if os.path.exists(path):
        return
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    template = [
        '# Feed Registry',
        '',
        '## 1. URLs',
        '',
        '## 2. LinkedIN users',
        '',
        '## 3. X users',
        '',
        '## 4. other',
        '',
    ]
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(template))


def _format_registry_url_entry(source: dict) -> str:
    url = canonicalize_url(source.get('url') or '')
    name = (source.get('name') or extract_domain(url) or 'Auto-discovered').replace('|', '-').strip()
    section_hint = (source.get('section_hint') or 'under-the-radar').strip()
    tags = list(source.get('tags') or [])
    if section_hint and section_hint not in tags:
        tags.append(section_hint)
    if 'autodiscovered' not in tags:
        tags.append('autodiscovered')
    tags_csv = ','.join([tag for tag in tags if tag])
    return f'- {url} | name={name} | section={section_hint} | tags={tags_csv} | discovered=auto'


def persist_discovered_registry_sources(feeds_file: str, discovered_sources: list[dict]) -> int:
    if not discovered_sources:
        return 0
    _ensure_registry_file(feeds_file)
    registry = _parse_feeds_registry(feeds_file)
    existing_urls: set[str] = set()
    for entry, metadata in registry['urls']:
        normalized = _normalize_registry_rss_url(entry, metadata)
        if normalized:
            existing_urls.add(normalized)

    pending_lines: list[str] = []
    for source in discovered_sources:
        url = canonicalize_url(source.get('url') or '')
        if not url or url in existing_urls:
            continue
        pending_lines.append(_format_registry_url_entry(source))
        existing_urls.add(url)

    if not pending_lines:
        return 0

    with open(feeds_file, 'r', encoding='utf-8') as handle:
        lines = handle.read().splitlines()

    urls_header_idx = None
    next_header_idx = None
    for idx, raw_line in enumerate(lines):
        section = _normalize_feeds_section(raw_line.strip())
        if section == 'urls':
            urls_header_idx = idx
            continue
        if urls_header_idx is not None and section is not None:
            next_header_idx = idx
            break

    if urls_header_idx is None:
        lines.extend(['', '## 1. URLs', ''])
        urls_header_idx = len(lines) - 2
    insert_at = next_header_idx if next_header_idx is not None else len(lines)
    if insert_at > 0 and lines[insert_at - 1].strip():
        lines.insert(insert_at, '')
        insert_at += 1
    for line in pending_lines:
        lines.insert(insert_at, line)
        insert_at += 1

    with open(feeds_file, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines).rstrip() + '\n')
    return len(pending_lines)


def parse_published(entry: dict) -> datetime | None:
    if date_parser is None:
        return None
    candidates = [
        entry.get('published'),
        entry.get('updated'),
        entry.get('created'),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = date_parser.parse(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def fetch_all_sources(sources: list[dict]) -> list[Article]:
    articles: list[Article] = []
    for source in sources:
        source_type = (source.get('type') or '').lower()
        try:
            if source_type == 'rss':
                articles.extend(fetch_rss_source(source))
            elif source_type == 'hackernews':
                articles.extend(fetch_hackernews_source(source))
            elif source_type == 'arxiv':
                articles.extend(fetch_arxiv_source(source))
            elif source_type == 'reddit-search':
                articles.extend(fetch_reddit_search_source(source))
            elif source_type == 'x':
                articles.extend(fetch_x_source(source))
            elif source_type == 'linkedin':
                articles.extend(fetch_linkedin_source(source))
            else:
                log.warning('Skipping unsupported source type: %s', source_type)
        except Exception as exc:  # noqa: BLE001
            log.exception('Source fetch failed for %s: %s', source.get('id'), exc)
    return articles


def _make_article(
    source: dict,
    title: str,
    url: str,
    summary: str,
    published_at: datetime | None,
    metrics: dict | None = None,
) -> Article:
    canonical_url = canonicalize_url(url)
    domain = extract_domain(canonical_url)
    article_id = stable_id(canonical_url or title, title)
    tags = set(source.get('tags') or [])
    return Article(
        id=article_id,
        title=strip_html(title),
        url=canonical_url,
        summary=strip_html(summary),
        source_name=source.get('name', source.get('id', 'Unknown')),
        source_type=source.get('type', 'unknown'),
        domain=domain,
        published_at=published_at,
        priority=float(source.get('priority', 1.0)),
        tags=tags,
        section_hint=source.get('section_hint'),
        metrics=metrics or {},
    )


def fetch_rss_source(source: dict) -> list[Article]:
    if feedparser is None:
        raise RuntimeError('feedparser is required for RSS ingestion.')
    url = source.get('url')
    if not url:
        return []
    max_items = int(source.get('max_items', 20))
    parsed = feedparser.parse(url, agent=USER_AGENT)
    if getattr(parsed, 'bozo', False):
        log.warning('RSS parse warning for %s', source.get('id'))
    articles: list[Article] = []
    for entry in parsed.entries[:max_items]:
        title = entry.get('title', '').strip()
        link = entry.get('link', '').strip()
        if not title or not link:
            continue
        summary = entry.get('summary') or entry.get('description') or ''
        published_at = parse_published(entry)
        article = _make_article(source, title, link, summary, published_at)
        if article.url:
            articles.append(article)
    return articles


def fetch_hackernews_source(source: dict) -> list[Article]:
    if requests is None:
        raise RuntimeError('requests is required for Hacker News ingestion.')
    endpoint = source.get('endpoint', 'top').strip().lower()
    max_items = int(source.get('max_items', 120))
    keywords = [item.lower() for item in source.get('keywords', [])]
    story_ids_url = f'https://hacker-news.firebaseio.com/v0/{endpoint}stories.json'
    response = requests.get(story_ids_url, timeout=15)
    response.raise_for_status()
    story_ids = response.json()[:max_items]
    articles: list[Article] = []
    for story_id in story_ids:
        item_url = f'https://hacker-news.firebaseio.com/v0/item/{story_id}.json'
        item_response = requests.get(item_url, timeout=10)
        if item_response.status_code != 200:
            continue
        payload = item_response.json() or {}
        if payload.get('type') != 'story':
            continue
        title = (payload.get('title') or '').strip()
        url = (payload.get('url') or '').strip()
        if not title or not url:
            continue
        blob = f"{title} {payload.get('text', '')}".lower()
        if keywords and not any(keyword in blob for keyword in keywords):
            continue
        unix_ts = payload.get('time')
        published_at = None
        if unix_ts:
            published_at = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        metrics = {
            'points': float(payload.get('score') or 0),
            'comments': float(payload.get('descendants') or 0),
        }
        article = _make_article(
            source,
            title=title,
            url=url,
            summary=payload.get('text') or '',
            published_at=published_at,
            metrics=metrics,
        )
        articles.append(article)
    return articles


def fetch_arxiv_source(source: dict) -> list[Article]:
    if feedparser is None:
        raise RuntimeError('feedparser is required for arXiv ingestion.')
    query = source.get('query', 'cat:cs.AI+OR+cat:cs.LG')
    max_items = int(source.get('max_items', 40))
    url = (
        'http://export.arxiv.org/api/query?'
        f'search_query={query}&sortBy=submittedDate&sortOrder=descending&start=0&max_results={max_items}'
    )
    parsed = feedparser.parse(url, agent=USER_AGENT)
    articles: list[Article] = []
    for entry in parsed.entries:
        title = entry.get('title', '').strip()
        url = entry.get('id', '').strip()
        summary = entry.get('summary', '').strip()
        if not title or not url:
            continue
        published_at = parse_published(entry)
        article = _make_article(source, title, url, summary, published_at)
        articles.append(article)
    return articles


def fetch_reddit_search_source(source: dict) -> list[Article]:
    if requests is None:
        raise RuntimeError('requests is required for Reddit search ingestion.')

    query = (source.get('query') or '').strip()
    if not query:
        log.warning('Skipping Reddit source %s: missing query.', source.get('id'))
        return []

    endpoint = source.get('endpoint', 'https://www.reddit.com/search.json')
    max_items = max(10, min(int(source.get('max_items', 50)), 100))
    params = {
        'q': query,
        'sort': source.get('sort') or 'new',
        't': source.get('time') or 'day',
        'limit': max_items,
        'restrict_sr': 'false',
    }
    headers = {
        'User-Agent': USER_AGENT,
    }
    try:
        response = requests.get(endpoint, headers=headers, params=params, timeout=20)
    except requests.RequestException:
        log.warning('Reddit source %s request failed.', source.get('id'))
        return []
    if response.status_code >= 400:
        log.warning('Reddit source %s request failed (%s).', source.get('id'), response.status_code)
        return []

    payload = response.json() or {}
    children = (payload.get('data') or {}).get('children') or []
    if not isinstance(children, list):
        return []

    articles: list[Article] = []
    for child in children:
        row = child.get('data') if isinstance(child, dict) else {}
        if not isinstance(row, dict):
            continue
        title = strip_html((row.get('title') or '').strip())
        permalink = (row.get('permalink') or '').strip()
        if not title or not permalink:
            continue
        url = canonicalize_url(f'https://www.reddit.com{permalink}')
        if not url:
            continue
        summary = row.get('selftext') or title
        published_at = _parse_datetime_value(row.get('created_utc'))
        subreddit = (row.get('subreddit') or '').strip()
        metrics = {
            'points': float(row.get('score') or 0),
            'comments': float(row.get('num_comments') or 0),
            'subreddit_subscribers': float(row.get('subreddit_subscribers') or 0),
        }
        article = _make_article(
            source=source,
            title=title,
            url=url,
            summary=summary,
            published_at=published_at,
            metrics=metrics,
        )
        if subreddit:
            article.source_name = f'r/{subreddit}'
            article.tags.add(f'r/{subreddit.lower()}')
        else:
            article.source_name = source.get('name', 'Reddit Search')
        article.source_type = 'reddit'
        articles.append(article)
    return articles


def _parse_datetime_value(value: str | int | float | dict | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return _parse_datetime_value(value.get('time') or value.get('created'))
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        if date_parser is not None:
            try:
                parsed = date_parser.parse(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except (ValueError, TypeError):
                return None
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _build_social_title(prefix: str, content: str, max_chars: int = 120) -> str:
    cleaned = strip_html(content)
    if not cleaned:
        return prefix
    if len(cleaned) <= max_chars:
        return f'{prefix}: {cleaned}'
    return f'{prefix}: {cleaned[: max_chars - 4].rstrip()}...'


def _extract_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            found = _extract_text(item)
            if found:
                return found
        return ''
    if isinstance(value, dict):
        preferred_keys = [
            'text',
            'commentary',
            'shareCommentary',
            'description',
            'title',
            'message',
        ]
        for key in preferred_keys:
            if key in value:
                found = _extract_text(value.get(key))
                if found:
                    return found
        for child in value.values():
            found = _extract_text(child)
            if found:
                return found
    return ''


def _extract_x_source_username(source: dict) -> str:
    username = _extract_x_username(str(source.get('username') or ''))
    if username:
        return username

    query = str(source.get('query') or '').strip()
    match = re.search(r'(?i)\bfrom:([A-Za-z0-9_]{1,15})\b', query)
    if match:
        return match.group(1)
    return ''


def _fetch_x_rss_fallback(source: dict, max_items: int) -> list[Article]:
    if feedparser is None or requests is None:
        return []

    username = _extract_x_source_username(source)
    if not username:
        return []

    candidate_urls: list[str] = []
    explicit_rss_url = str(source.get('rss_url') or '').strip()
    if explicit_rss_url:
        candidate_urls.append(explicit_rss_url)
    candidate_urls.extend(
        [
            f'https://nitter.net/{username}/rss',
            f'https://nitter.poast.org/{username}/rss',
            f'https://rsshub.app/twitter/user/{username}',
        ]
    )

    deduped_urls: list[str] = []
    seen_urls: set[str] = set()
    for feed_url in candidate_urls:
        normalized = feed_url.strip()
        if not normalized or normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        deduped_urls.append(normalized)

    for feed_url in deduped_urls:
        try:
            response = requests.get(feed_url, headers={'User-Agent': USER_AGENT}, timeout=20)
        except requests.RequestException:
            continue

        if response.status_code >= 400:
            continue

        parsed_feed = feedparser.parse(response.content)
        if not parsed_feed.entries:
            continue

        articles: list[Article] = []
        feed_source_name = strip_html((parsed_feed.feed or {}).get('title') or '') or f'X @{username}'
        for entry in parsed_feed.entries[:max_items]:
            link = canonicalize_url((entry.get('link') or '').strip())
            if not link:
                continue
            title = strip_html(entry.get('title') or '')
            summary = strip_html(entry.get('summary') or entry.get('description') or '')
            if not summary:
                summary = title
            published_at = _parse_datetime_value(
                entry.get('published')
                or entry.get('updated')
                or entry.get('pubDate')
            )
            article_title = title or _build_social_title(f'@{username}', summary)
            article = _make_article(
                source=source,
                title=article_title,
                url=link,
                summary=summary,
                published_at=published_at,
                metrics={},
            )
            article.source_name = feed_source_name
            articles.append(article)

        if articles:
            log.info(
                'X source %s using RSS fallback (%s) yielded %s item(s).',
                source.get('id'),
                feed_url,
                len(articles),
            )
            return articles
    return []


def fetch_x_source(source: dict) -> list[Article]:
    if requests is None:
        raise RuntimeError('requests is required for X ingestion.')

    bearer_token = os.getenv('X_BEARER_TOKEN')
    if not bearer_token:
        log.warning('Skipping X source %s: X_BEARER_TOKEN is not set.', source.get('id'))
        fallback_articles = _fetch_x_rss_fallback(source, max(10, min(int(source.get('max_items', 25)), 100)))
        if fallback_articles:
            return fallback_articles
        return []

    query = (source.get('query') or '').strip()
    if not query:
        log.warning('Skipping X source %s: missing query.', source.get('id'))
        return []

    max_items = max(10, min(int(source.get('max_items', 25)), 100))
    endpoint = source.get('endpoint', 'https://api.x.com/2/tweets/search/recent')
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'User-Agent': USER_AGENT,
    }
    params = {
        'query': query,
        'max_results': max_items,
        'tweet.fields': 'created_at,public_metrics,author_id,lang',
        'user.fields': 'username,name,verified,public_metrics',
        'expansions': 'author_id',
    }
    response = requests.get(endpoint, headers=headers, params=params, timeout=20)
    if response.status_code >= 400:
        log.warning('X source %s request failed (%s).', source.get('id'), response.status_code)
        fallback_articles = _fetch_x_rss_fallback(source, max_items)
        if fallback_articles:
            return fallback_articles
        return []

    payload = response.json() or {}
    users_by_id = {}
    for user in payload.get('includes', {}).get('users', []):
        user_id = user.get('id')
        if user_id:
            users_by_id[user_id] = user

    articles: list[Article] = []
    for tweet in payload.get('data', []):
        tweet_id = str(tweet.get('id') or '').strip()
        text = strip_html(tweet.get('text') or '')
        if not tweet_id or not text:
            continue

        author = users_by_id.get(tweet.get('author_id')) or {}
        username = (author.get('username') or source.get('username') or '').strip()
        source_name = f'X @{username}' if username else 'X'
        url = f'https://x.com/{username}/status/{tweet_id}' if username else f'https://x.com/i/web/status/{tweet_id}'
        published_at = _parse_datetime_value(tweet.get('created_at'))
        metrics_payload = tweet.get('public_metrics') or {}
        metrics = {
            'points': float(metrics_payload.get('like_count') or 0),
            'comments': float(metrics_payload.get('reply_count') or 0),
            'reposts': float(metrics_payload.get('retweet_count') or 0),
            'followers': float((author.get('public_metrics') or {}).get('followers_count') or 0),
            'verified': 1.0 if author.get('verified') else 0.0,
        }
        title_prefix = f'@{username}' if username else 'X post'
        article = _make_article(
            source=source,
            title=_build_social_title(title_prefix, text),
            url=url,
            summary=text,
            published_at=published_at,
            metrics=metrics,
        )
        article.source_name = source_name
        articles.append(article)
    return articles


def _build_linkedin_url(post_id: str, fallback_url: str | None) -> str:
    if fallback_url:
        return fallback_url
    if not post_id:
        return 'https://www.linkedin.com/'
    encoded_id = quote(post_id, safe=':')
    return f'https://www.linkedin.com/feed/update/{encoded_id}/'


def _resolve_linkedin_author_urn(source: dict) -> str:
    env_author_urn = (os.getenv('LINKEDIN_AUTHOR_URN') or '').strip()
    profile_url = (source.get('profile_url') or '').strip()
    source_author_urn = (source.get('author_urn') or '').strip()

    if source_author_urn and not source_author_urn.endswith(':000000'):
        return source_author_urn

    if source_author_urn.endswith(':000000') and env_author_urn and not profile_url:
        log.info('LinkedIn source %s: using LINKEDIN_AUTHOR_URN from env.', source.get('id'))
        return env_author_urn

    if not source_author_urn and env_author_urn and not profile_url:
        return env_author_urn

    if source_author_urn:
        return source_author_urn

    return ''


def _extract_linkedin_profile_slug(profile_url: str) -> str:
    cleaned = profile_url.strip().rstrip('/')
    if '/in/' in cleaned:
        return cleaned.split('/in/', 1)[1].split('/', 1)[0]
    if '/company/' in cleaned:
        return cleaned.split('/company/', 1)[1].split('/', 1)[0]
    return ''


def _warn_linkedin_profile_requires_urn(source: dict) -> None:
    profile_url = (source.get('profile_url') or '').strip()
    if not profile_url:
        return
    slug = _extract_linkedin_profile_slug(profile_url)
    if slug:
        log.warning(
            'LinkedIn source %s has profile URL %s but no author_urn. '
            'Add metadata in feeds.md as: "%s | author_urn=urn:li:person:..." to enable ingestion.',
            source.get('id'),
            profile_url,
            profile_url,
        )
        return
    log.warning(
        'LinkedIn source %s has profile URL %s but no author_urn. '
        'Add author_urn metadata in feeds.md to enable ingestion.',
        source.get('id'),
        profile_url,
    )


def fetch_linkedin_source(source: dict) -> list[Article]:
    if requests is None:
        raise RuntimeError('requests is required for LinkedIn ingestion.')

    access_token = os.getenv('LINKEDIN_ACCESS_TOKEN')
    if not access_token:
        log.warning(
            'Skipping LinkedIn source %s: LINKEDIN_ACCESS_TOKEN is not set.',
            source.get('id'),
        )
        return []

    author_urn = _resolve_linkedin_author_urn(source)
    if not author_urn:
        _warn_linkedin_profile_requires_urn(source)
        if not (source.get('profile_url') or '').strip():
            log.warning(
                'Skipping LinkedIn source %s: missing author_urn. Set author_urn or LINKEDIN_AUTHOR_URN.',
                source.get('id'),
            )
        return []
    if author_urn.endswith(':000000'):
        log.warning(
            'Skipping LinkedIn source %s: author_urn appears to be placeholder (%s).',
            source.get('id'),
            author_urn,
        )
        return []

    max_items = max(5, min(int(source.get('max_items', 20)), 100))
    endpoint = source.get('endpoint', 'https://api.linkedin.com/rest/posts')
    api_version = os.getenv('LINKEDIN_API_VERSION') or source.get('api_version') or '202503'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'LinkedIn-Version': str(api_version),
        'X-Restli-Protocol-Version': '2.0.0',
        'User-Agent': USER_AGENT,
    }
    params = {
        'q': 'author',
        'author': author_urn,
        'count': max_items,
        'sortBy': 'LAST_MODIFIED',
    }
    response = requests.get(endpoint, headers=headers, params=params, timeout=20)
    if response.status_code >= 400:
        error_snippet = _linkedin_error_snippet(response)
        if response.status_code == 401:
            log.warning(
                'LinkedIn source %s unauthorized (401). Check LINKEDIN_ACCESS_TOKEN. Details: %s',
                source.get('id'),
                error_snippet,
            )
        elif response.status_code == 403:
            log.warning(
                'LinkedIn source %s access denied (403). '
                'Confirm product access/scopes for Posts API and author_urn ownership. Details: %s',
                source.get('id'),
                error_snippet,
            )
        else:
            log.warning(
                'LinkedIn source %s request failed (%s). Details: %s',
                source.get('id'),
                response.status_code,
                error_snippet,
            )
        return []

    payload = response.json() or {}
    rows = payload.get('elements') or payload.get('data') or payload.get('results') or []
    if not isinstance(rows, list):
        log.warning('LinkedIn source %s response did not contain a list payload.', source.get('id'))
        return []

    articles: list[Article] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        post_id = str(row.get('id') or row.get('urn') or row.get('entityUrn') or '').strip()
        text = strip_html(_extract_text(row))
        if not text:
            continue
        published_at = _parse_datetime_value(
            row.get('publishedAt')
            or row.get('lastModifiedAt')
            or row.get('createdAt')
            or row.get('firstPublishedAt')
        )
        fallback_url = row.get('permalink') or row.get('url')
        url = _build_linkedin_url(post_id, fallback_url)
        social_stats = row.get('socialDetail') or row.get('statistics') or {}
        metrics = {
            'points': float(
                social_stats.get('numLikes')
                or social_stats.get('likeCount')
                or social_stats.get('numImpressions')
                or 0
            ),
            'comments': float(social_stats.get('numComments') or social_stats.get('commentCount') or 0),
        }
        article = _make_article(
            source=source,
            title=_build_social_title('LinkedIn', text),
            url=url,
            summary=text,
            published_at=published_at,
            metrics=metrics,
        )
        articles.append(article)
    log.info(
        'LinkedIn source %s fetched %s item(s) for author %s.',
        source.get('id'),
        len(articles),
        author_urn,
    )
    return articles


def _linkedin_error_snippet(response) -> str:
    try:
        payload = response.json() or {}
    except ValueError:
        payload = {}
    message = payload.get('message') or payload.get('error_description') or ''
    code = payload.get('code') or payload.get('serviceErrorCode')
    if code and message:
        return f'{code}: {message}'
    if message:
        return str(message)
    body_text = response.text or ''
    return body_text.strip().replace('\n', ' ')[:240]


def build_sample_articles() -> list[Article]:
    now = datetime.now(timezone.utc)
    templates = [
        ('Major model provider launches multimodal coding agent', 'big-announcements'),
        ('Engineering team replaces flaky tests with AI-generated fixtures', 'engineering'),
        ('PM team ships weekly experiments with AI-generated specs', 'product-development'),
        ('Solo founder reaches $42k MRR with AI-native support desk', 'business'),
        ('Tiny blog shows 10x prompt compression trick for retrieval', 'under-the-radar'),
        ('AI turns childhood doodles into playable arcade games', 'for-fun'),
    ]
    articles: list[Article] = []
    for idx in range(30):
        title, hint = templates[idx % len(templates)]
        url = f'https://example.com/post-{idx}'
        article = Article(
            id=stable_id(url, title),
            title=f'{title} ({idx + 1})',
            url=url,
            summary=f'Sample content for {hint}.',
            source_name='Sample Source',
            source_type='sample',
            domain='example.com',
            published_at=now,
            priority=5.0,
            tags={hint},
            section_hint=hint,
        )
        articles.append(article)
    return articles
