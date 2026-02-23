# Daily AI Feed (Fully Automated)

This project generates and publishes a daily curated AI briefing website.

Each daily post includes:
- Original-source links
- `3-5` selected links in each section:
  - `0) Big Announcements`
  - `1) Engineering`
  - `2) Product Development`
  - `3) Business`
  - `4) Under the Radar`
  - `5) For Fun`

## How It Works

1. Ingest from curated sources in `config/sources.yaml`:
   - RSS feeds
   - Hacker News API
   - arXiv API
   - X API (optional)
   - LinkedIn API (optional)
2. Normalize and deduplicate links.
3. Score each item across the six sections.
4. Select top `3-5` per section with domain diversity constraints.
5. Generate concise summaries and "why it matters":
   - Uses OpenAI if `OPENAI_API_KEY` exists.
   - Falls back to deterministic local summaries if missing.
6. Render static site files into `site/`:
   - `site/index.html` (latest)
   - `site/archive/YYYY-MM-DD.html`
   - `site/data/archive.json`
   - `site/data/YYYY-MM-DD.json`

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ai_news_feed.main --sample --output-dir site
```

Run against live sources:

```bash
python -m ai_news_feed.main --output-dir site
```

Optional environment variables:
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-5-mini`)
- `X_BEARER_TOKEN` (for `type: x` sources)
- `LINKEDIN_ACCESS_TOKEN` (for `type: linkedin` sources)
- `LINKEDIN_API_VERSION` (default: `202503`)
- `FEED_TIMEZONE` (default: `America/New_York`)

## GitHub Automation (No Daily Manual Work)

Workflow: `.github/workflows/daily-feed.yml`

- Runs daily via cron (`13:15 UTC`) and on manual dispatch.
- Generates the feed.
- Commits updated `site/` artifacts back to the repo.
- Deploys to GitHub Pages.

### One-Time GitHub Setup

1. In repository settings, enable **GitHub Pages** with **GitHub Actions** as source.
2. Add repository secret `OPENAI_API_KEY` (optional but recommended for better summaries).
3. Optional:
   - Secret `OPENAI_MODEL`
   - Secret `X_BEARER_TOKEN`
   - Secret `LINKEDIN_ACCESS_TOKEN`
   - Variable `LINKEDIN_API_VERSION` (for example `202503`)
   - Variable `FEED_TIMEZONE` (for example `America/Los_Angeles`)

## Customization

- Edit sources in `config/sources.yaml`.
- Tune section scoring keywords in `ai_news_feed/config.py`.
- Adjust min/max links per section via CLI:

```bash
python -m ai_news_feed.main --min-per-section 3 --max-per-section 5
```

For social sources:
- `type: x` uses `query` (X recent search).
- `type: linkedin` uses `author_urn` and fetches from LinkedIn posts API.
- If corresponding tokens are not set, those sources are skipped safely.

## Research References

See `docs/research.md` for the external references used to choose automation and ingestion patterns.
