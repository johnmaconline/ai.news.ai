##########################################################################################
#
# Script name: render.py
#
# Description: Static-site rendering and archive persistence.
#
##########################################################################################

import json
from html import escape
from pathlib import Path

from .config import SECTIONS
from .models import Article, DailyFeed


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************

CSS = '''
:root {
  --bg-1: #fdf7ea;
  --bg-2: #e6f0ff;
  --surface: rgba(255, 255, 255, 0.82);
  --text: #1d212a;
  --muted: #5b6270;
  --stroke: rgba(31, 42, 64, 0.14);
  --accent: #004f8c;
  --accent-2: #008056;
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  color: var(--text);
  background:
    radial-gradient(1200px 500px at 10% -10%, #ffd89f 0%, transparent 55%),
    radial-gradient(900px 420px at 100% 0%, #a9cdfc 0%, transparent 60%),
    linear-gradient(165deg, var(--bg-1), var(--bg-2));
  min-height: 100vh;
}

.wrap {
  max-width: 1150px;
  margin: 0 auto;
  padding: 1.2rem 1rem 4rem;
}

header {
  margin-bottom: 1.3rem;
}

.headline {
  font-family: "Space Grotesk", "Avenir Next", sans-serif;
  font-size: clamp(1.8rem, 3.6vw, 3rem);
  line-height: 1.05;
  letter-spacing: -0.02em;
  margin: 0;
}

.subline {
  color: var(--muted);
  margin: 0.7rem 0 0;
  max-width: 70ch;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 0.95rem;
}

.section-card {
  background: var(--surface);
  border: 1px solid var(--stroke);
  border-radius: 14px;
  padding: 0.9rem;
  backdrop-filter: blur(4px);
  animation: fadeUp 0.45s ease both;
}

.section-title {
  font-family: "Space Grotesk", sans-serif;
  margin: 0;
  font-size: 1.1rem;
}

.section-desc {
  color: var(--muted);
  font-size: 0.9rem;
  margin-top: 0.28rem;
}

.story {
  border-top: 1px dashed var(--stroke);
  padding-top: 0.62rem;
  margin-top: 0.62rem;
}

.story-top {
  display: flex;
  gap: 0.55rem;
  justify-content: space-between;
  align-items: flex-start;
}

.story h3 {
  margin: 0;
  line-height: 1.18;
}

.story a {
  color: var(--accent);
  text-decoration-thickness: 2px;
  text-underline-offset: 2px;
}

.story-icons {
  display: inline-flex;
  align-items: center;
  gap: 0.32rem;
  flex-shrink: 0;
}

.icon-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.2rem;
  min-width: 1.92rem;
  height: 1.92rem;
  border-radius: 999px;
  border: 1px solid var(--stroke);
  background: #fff;
  color: var(--text) !important;
  text-decoration: none !important;
  font-size: 0.74rem;
  font-weight: 700;
  line-height: 1;
  padding: 0 0.34rem;
}

.icon-svg {
  width: 0.95rem;
  height: 0.95rem;
  display: block;
  flex-shrink: 0;
}

.icon-link:hover {
  transform: translateY(-1px);
}

.icon-source-linkedin {
  background: #0a66c2;
  color: #fff !important;
  border-color: #0a66c2;
}

.icon-source-x {
  background: #111;
  color: #fff !important;
  border-color: #111;
}

.icon-source-hn {
  background: #ff6600;
  color: #fff !important;
  border-color: #ff6600;
}

.icon-source-reddit {
  background: #ff4500;
  color: #fff !important;
  border-color: #ff4500;
}

.icon-source-arxiv {
  background: #b31b1b;
  color: #fff !important;
  border-color: #b31b1b;
}

.icon-score {
  background: #e9fff4;
  border-color: #9ddac0;
  color: #00744f !important;
  padding: 0 0.44rem;
}

.icon-score-value {
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1;
}

.meta {
  font-size: 0.78rem;
  color: var(--muted);
  margin: 0.25rem 0;
}

.summary, .why {
  margin: 0.3rem 0;
  font-size: 0.93rem;
}

.why {
  color: var(--accent-2);
}

.archive {
  margin-top: 1.4rem;
  background: rgba(255, 255, 255, 0.68);
  border: 1px solid var(--stroke);
  border-radius: 12px;
  padding: 0.8rem;
}

.archive ul {
  margin: 0.6rem 0 0;
  padding-left: 1.2rem;
}

.archive li { margin: 0.2rem 0; }

footer {
  margin-top: 1.2rem;
  color: var(--muted);
  font-size: 0.82rem;
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
'''


# ****************************************************************************************
# Functions
# ****************************************************************************************


def _article_to_json(article: Article) -> dict:
    return {
        'id': article.id,
        'title': article.title,
        'url': article.url,
        'source_name': article.source_name,
        'domain': article.domain,
        'published_at': article.published_at.isoformat() if article.published_at else None,
        'summary_text': article.summary_text,
        'why_it_matters': article.why_it_matters,
        'section_score': article.section_score,
        'scores': article.scores,
    }


def _source_icon_data(article: Article) -> tuple[str, str, str]:
    domain = (article.domain or '').lower()
    source_type = (article.source_type or '').lower()
    source_name = article.source_name or 'Source'

    if source_type == 'linkedin' or 'linkedin.com' in domain:
        return source_name, 'icon-source-linkedin', 'linkedin'
    if source_type == 'x' or domain in {'x.com', 'twitter.com'}:
        return source_name, 'icon-source-x', 'x'
    if source_type == 'hackernews' or 'ycombinator.com' in domain:
        return source_name, 'icon-source-hn', 'hackernews'
    if 'reddit.com' in domain:
        return source_name, 'icon-source-reddit', 'reddit'
    if source_type == 'arxiv' or 'arxiv.org' in domain:
        return source_name, 'icon-source-arxiv', 'arxiv'
    return source_name, '', 'source'


def _icon_svg(icon_name: str) -> str:
    if icon_name == 'linkedin':
        return (
            '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">'
            '<rect x="2.4" y="2.4" width="19.2" height="19.2" rx="3.2" fill="none" stroke="currentColor" stroke-width="2"/>'
            '<circle cx="8.1" cy="8.3" r="1.4" fill="currentColor"/>'
            '<rect x="6.8" y="11.0" width="2.6" height="6.2" fill="currentColor"/>'
            '<path d="M12 11h2.5v1.2c.6-.9 1.5-1.4 2.8-1.4 2.2 0 3.4 1.4 3.4 4.0v2.4h-2.6v-2.2c0-1.4-.5-2.0-1.6-2.0-1.1 0-1.8.8-1.8 2.1v2.1H12z" fill="currentColor"/>'
            '</svg>'
        )
    if icon_name == 'x':
        return (
            '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M5 4h3.4l3.8 5.1L16.6 4H20l-6.2 7.4L20.2 20h-3.4l-4.4-5.9L7.4 20H4l6.6-7.8z" fill="currentColor"/>'
            '</svg>'
        )
    if icon_name == 'hackernews':
        return (
            '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M6 4h3.2l2.8 5.2L14.8 4H18l-4.4 8v8h-3.2v-8z" fill="currentColor"/>'
            '</svg>'
        )
    if icon_name == 'reddit':
        return (
            '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">'
            '<circle cx="12" cy="13" r="5.2" fill="none" stroke="currentColor" stroke-width="1.8"/>'
            '<circle cx="9.8" cy="12.6" r="1" fill="currentColor"/>'
            '<circle cx="14.2" cy="12.6" r="1" fill="currentColor"/>'
            '<path d="M9.4 15.2c.8.8 1.5 1.1 2.6 1.1s1.8-.3 2.6-1.1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'
            '<circle cx="17.8" cy="9.2" r="1.4" fill="none" stroke="currentColor" stroke-width="1.6"/>'
            '<path d="M13 8.4l1.2-3.3 2.4.6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'
            '</svg>'
        )
    if icon_name == 'arxiv':
        return (
            '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M3.8 18 10.9 5.8h2.2L20.2 18h-2.8l-1.5-2.6H8.1L6.6 18zM9.2 13.2h5.6L12 8.6z" fill="currentColor"/>'
            '</svg>'
        )
    if icon_name == 'relevance':
        return (
            '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">'
            '<circle cx="12" cy="12" r="8.2" fill="none" stroke="currentColor" stroke-width="1.8"/>'
            '<circle cx="12" cy="12" r="4.4" fill="none" stroke="currentColor" stroke-width="1.8"/>'
            '<circle cx="12" cy="12" r="1.3" fill="currentColor"/>'
            '</svg>'
        )
    return (
        '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M8.2 8.6h3.2a2.8 2.8 0 0 1 0 5.6H9.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        '<path d="M15.8 15.4h-3.2a2.8 2.8 0 0 1 0-5.6h1.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        '<path d="M10.1 13.9 13.9 10.1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        '</svg>'
    )


def _render_story(article: Article) -> str:
    published = article.published_at.strftime('%Y-%m-%d %H:%M UTC') if article.published_at else 'time unknown'
    why_text = article.why_it_matters or 'High-signal item for this section.'
    source_name, source_class, source_icon_name = _source_icon_data(article)
    source_classes = f'icon-link {source_class}'.strip()
    source_link = (
        f'<a class="{escape(source_classes)}" href="{escape(article.url)}" target="_blank" rel="noopener noreferrer" '
        f'title="Source: {escape(source_name)}">{_icon_svg(source_icon_name)}</a>'
    )
    relevance_link = (
        f'<a class="icon-link icon-score" href="{escape(article.url)}" target="_blank" rel="noopener noreferrer" '
        f'title="Relevance factor: {article.section_score:.2f}">{_icon_svg("relevance")}'
        f'<span class="icon-score-value">{article.section_score:.1f}</span></a>'
    )
    return (
        '<article class="story">'
        '<div class="story-top">'
        f'<h3><a href="{escape(article.url)}" target="_blank" rel="noopener noreferrer">{escape(article.title)}</a></h3>'
        f'<div class="story-icons">{source_link}{relevance_link}</div>'
        '</div>'
        f'<p class="meta">{escape(article.source_name)} · {escape(article.domain)} · {escape(published)}</p>'
        f'<p class="summary">{escape(article.summary_text or article.summary)}</p>'
        f'<p class="why">Why it matters: {escape(why_text)}</p>'
        '</article>'
    )


def _render_sections(feed: DailyFeed) -> str:
    cards = []
    for section in SECTIONS:
        stories = feed.sections.get(section.slug, [])
        stories_html = ''.join(_render_story(story) for story in stories)
        cards.append(
            '<section class="section-card">'
            f'<h2 class="section-title">{escape(section.label)}</h2>'
            f'<p class="section-desc">{escape(section.description)}</p>'
            f'{stories_html}'
            '</section>'
        )
    return ''.join(cards)


def _render_archive_links(archive: list[dict]) -> str:
    lines = []
    for entry in archive[:30]:
        date = entry.get('date', '')
        title = entry.get('title', date)
        lines.append(f'<li><a href="./archive/{escape(date)}.html">{escape(title)}</a></li>')
    return ''.join(lines)


def _render_page(feed: DailyFeed, archive: list[dict], title_suffix: str = '') -> str:
    suffix = f' - {title_suffix}' if title_suffix else ''
    return f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(feed.title)}{escape(suffix)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="./style.css" />
  </head>
  <body>
    <div class="wrap">
      <header>
        <h1 class="headline">{escape(feed.title)}</h1>
        <p class="subline">{escape(feed.intro)}</p>
      </header>
      <main class="grid">{_render_sections(feed)}</main>
      <aside class="archive">
        <strong>Archive</strong>
        <ul>{_render_archive_links(archive)}</ul>
      </aside>
      <footer>
        Generated {escape(feed.generated_at)}. Each item links to the original source.
      </footer>
    </div>
  </body>
</html>
'''


def _render_archive_page(feed: DailyFeed, archive: list[dict]) -> str:
    page = _render_page(feed, archive, title_suffix='Archive')
    return page.replace('href="./style.css"', 'href="../style.css"').replace(
        'href="./archive/', 'href="./'
    )


def _read_archive(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return payload
    return []


def _update_archive(existing: list[dict], feed: DailyFeed) -> list[dict]:
    entries = [entry for entry in existing if entry.get('date') != feed.date]
    lead_story = ''
    lead_url = ''
    for stories in feed.sections.values():
        if stories:
            lead_story = stories[0].title
            lead_url = stories[0].url
            break
    entries.append(
        {
            'date': feed.date,
            'title': feed.title,
            'lead_story': lead_story,
            'lead_url': lead_url,
            'generated_at': feed.generated_at,
        }
    )
    entries.sort(key=lambda item: item.get('date', ''), reverse=True)
    return entries


def write_site(feed: DailyFeed, output_dir: str) -> None:
    root = Path(output_dir)
    data_dir = root / 'data'
    archive_dir = root / 'archive'
    root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_index_path = data_dir / 'archive.json'
    archive_data = _read_archive(archive_index_path)
    archive_data = _update_archive(archive_data, feed)

    day_payload = {
        'date': feed.date,
        'generated_at': feed.generated_at,
        'title': feed.title,
        'intro': feed.intro,
        'sections': {
            slug: [_article_to_json(article) for article in feed.sections.get(slug, [])]
            for slug in feed.sections
        },
    }
    (data_dir / f'{feed.date}.json').write_text(
        json.dumps(day_payload, ensure_ascii=True, indent=2), encoding='utf-8'
    )
    archive_index_path.write_text(json.dumps(archive_data, ensure_ascii=True, indent=2), encoding='utf-8')
    (root / 'style.css').write_text(CSS.strip() + '\n', encoding='utf-8')
    (root / '.nojekyll').write_text('', encoding='utf-8')

    index_html = _render_page(feed, archive_data)
    archive_html = _render_archive_page(feed, archive_data)
    (root / 'index.html').write_text(index_html, encoding='utf-8')
    (archive_dir / f'{feed.date}.html').write_text(archive_html, encoding='utf-8')
