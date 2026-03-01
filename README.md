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

1. Ingest from curated sources in `config/sources.yaml` and `config/feeds.md`:
   - RSS feeds
   - Hacker News API
   - arXiv API
   - X API (optional)
   - LinkedIn API (optional)
2. Normalize and deduplicate links.
3. Require source items to be within the last 24 hours, then score each item across the six sections.
4. Select top `3-5` per section with domain diversity constraints.
5. Generate concise summaries and "why it matters":
   - Uses OpenAI if `OPENAI_API_KEY` exists.
   - Falls back to deterministic local summaries if missing.
   - Loads section prompt guidance from `prompts/sections/*.md`.
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
- `SECTION_PROMPTS_DIR` (optional override path for section prompt markdown files)
- `SYSTEM_PROMPT_FILE` (optional override path for system prompt markdown file)
- `X_BEARER_TOKEN` (for `type: x` sources)
- `LINKEDIN_ACCESS_TOKEN` (for `type: linkedin` sources)
- `LINKEDIN_API_VERSION` (default: `202503`)
- `LINKEDIN_AUTHOR_URN` (optional override for LinkedIn org/person URN)
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
   - Variable `LINKEDIN_AUTHOR_URN` (for example `urn:li:organization:123456`)
   - Variable `FEED_TIMEZONE` (for example `America/Los_Angeles`)

## Customization

- Edit sources in `config/sources.yaml`.
- Maintain ongoing discovered feeds/users in `config/feeds.md`.
- Tune section scoring keywords in `ai_news_feed/config.py`.
- Adjust min/max links per section via CLI:

```bash
python -m ai_news_feed.main --min-per-section 3 --max-per-section 5
```

For social sources:
- `type: x` uses `query` (X recent search).
- `type: linkedin` uses `author_urn` and fetches from LinkedIn posts API.
- `LINKEDIN_AUTHOR_URN` in `.env` overrides the LinkedIn `author_urn` in `config/sources.yaml`, so you can switch orgs without editing YAML.
- If corresponding tokens are not set, those sources are skipped safely.

Business section intent:
- Focuses on practical business application, AI-native side hustles, and workflow execution.
- Announcement-heavy or partnership-only items are deprioritized for this section and should appear in `0) Big Announcements` when relevant.

`config/feeds.md` behavior:
- This file is loaded on every run (default path).
- Sections:
  - `1. URLs` (RSS/Atom URLs; optional metadata such as `name=`, `section=`, `tags=`)
  - `2. LinkedIN users` (LinkedIn `urn:li:...` or LinkedIn profile/company URLs)
  - `3. X users` (usernames like `@swyx` or profile URL)
  - `4. other` (notes only; not ingested)
- For LinkedIn URL entries, add `author_urn=urn:li:person:...` (or org URN) when available.
  Without a URN, the source is tracked but LinkedIn API ingestion is skipped.
- You can override the registry path:

```bash
python -m ai_news_feed.main --feeds-file config/feeds.md
```

Prompt customization:
- Edit `prompts/system.md` for global summarization behavior.
- Edit section-specific files in `prompts/sections/`:
  - `big-announcements.md`
  - `engineering.md`
  - `product-development.md`
  - `business.md`
  - `under-the-radar.md`
  - `for-fun.md`

## Research References

See `docs/research.md` for the external references used to choose automation and ingestion patterns.
