from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .config import SECTIONS
from .models import Article, DailyFeed


CSS = """
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

.story a {
  color: var(--accent);
  text-decoration-thickness: 2px;
  text-underline-offset: 2px;
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
"""


def _article_to_json(article: Article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "source_name": article.source_name,
        "domain": article.domain,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "summary_text": article.summary_text,
        "why_it_matters": article.why_it_matters,
        "section_score": article.section_score,
        "scores": article.scores,
    }


def _render_story(article: Article) -> str:
    published = article.published_at.strftime("%Y-%m-%d %H:%M UTC") if article.published_at else "time unknown"
    return (
        '<article class="story">'
        f'<h3><a href="{escape(article.url)}" target="_blank" rel="noopener noreferrer">{escape(article.title)}</a></h3>'
        f'<p class="meta">{escape(article.source_name)} · {escape(article.domain)} · {escape(published)}</p>'
        f'<p class="summary">{escape(article.summary_text or article.summary)}</p>'
        f'<p class="why">Why it matters: {escape(article.why_it_matters or "High-signal item for this section.")}</p>'
        "</article>"
    )


def _render_sections(feed: DailyFeed) -> str:
    cards = []
    for section in SECTIONS:
        stories = feed.sections.get(section.slug, [])
        stories_html = "".join(_render_story(story) for story in stories)
        cards.append(
            '<section class="section-card">'
            f'<h2 class="section-title">{escape(section.label)}</h2>'
            f'<p class="section-desc">{escape(section.description)}</p>'
            f"{stories_html}"
            "</section>"
        )
    return "".join(cards)


def _render_archive_links(archive: list[dict]) -> str:
    lines = []
    for entry in archive[:30]:
        date = entry.get("date", "")
        title = entry.get("title", date)
        lines.append(f'<li><a href="./archive/{escape(date)}.html">{escape(title)}</a></li>')
    return "".join(lines)


def _render_page(feed: DailyFeed, archive: list[dict], title_suffix: str = "") -> str:
    suffix = f" - {title_suffix}" if title_suffix else ""
    return f"""<!doctype html>
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
"""


def _render_archive_page(feed: DailyFeed, archive: list[dict]) -> str:
    page = _render_page(feed, archive, title_suffix="Archive")
    return page.replace('href="./style.css"', 'href="../style.css"').replace(
        'href="./archive/', 'href="./'
    )


def _read_archive(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return payload
    return []


def _update_archive(existing: list[dict], feed: DailyFeed) -> list[dict]:
    entries = [entry for entry in existing if entry.get("date") != feed.date]
    lead_story = ""
    lead_url = ""
    for stories in feed.sections.values():
        if stories:
            lead_story = stories[0].title
            lead_url = stories[0].url
            break
    entries.append(
        {
            "date": feed.date,
            "title": feed.title,
            "lead_story": lead_story,
            "lead_url": lead_url,
            "generated_at": feed.generated_at,
        }
    )
    entries.sort(key=lambda item: item.get("date", ""), reverse=True)
    return entries


def write_site(feed: DailyFeed, output_dir: str) -> None:
    root = Path(output_dir)
    data_dir = root / "data"
    archive_dir = root / "archive"
    root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_index_path = data_dir / "archive.json"
    archive_data = _read_archive(archive_index_path)
    archive_data = _update_archive(archive_data, feed)

    day_payload = {
        "date": feed.date,
        "generated_at": feed.generated_at,
        "title": feed.title,
        "intro": feed.intro,
        "sections": {
            slug: [_article_to_json(article) for article in feed.sections.get(slug, [])]
            for slug in feed.sections
        },
    }
    (data_dir / f"{feed.date}.json").write_text(
        json.dumps(day_payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    archive_index_path.write_text(json.dumps(archive_data, ensure_ascii=True, indent=2), encoding="utf-8")
    (root / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    (root / ".nojekyll").write_text("", encoding="utf-8")

    index_html = _render_page(feed, archive_data)
    archive_html = _render_archive_page(feed, archive_data)
    (root / "index.html").write_text(index_html, encoding="utf-8")
    (archive_dir / f"{feed.date}.html").write_text(archive_html, encoding="utf-8")
