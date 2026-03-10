# Daily AI Feed (Fully Automated)

This project generates and publishes a daily curated AI briefing website.

Each daily post includes:
- Original-source links
- `3-5` selected links in each section:
  - `0) Practical Prompts`
  - `1) Engineering`
  - `2) Product Development`
  - `3) Software Development`
  - `4) Under the Radar`
  - `5) For Fun`

## How It Works

1. Ingest from curated sources in `config/sources.yaml` and `config/feeds.md`:
   - RSS feeds
   - Hacker News API
   - arXiv API
   - X API (optional)
   - LinkedIn API (optional)
   - Includes default Hacker News (`hackernews-ai`) and TLDR (`tldr-ai`) sources
2. Normalize and deduplicate links.
3. Require source items to be within the last 24 hours, then score each item across the six sections.
   - High-signal model/company announcements from trusted domains get a 48-hour grace window to avoid missing major releases by schedule timing.
4. Apply LLM-assisted curation reranking (default on) with deterministic fallback if LLM is unavailable.
5. Select top `3-5` per section with domain diversity constraints.
6. Generate concise summaries and "why it matters":
   - Uses OpenAI if `OPENAI_API_KEY` exists.
   - Falls back to deterministic local summaries if missing.
   - Loads section prompt guidance from `prompts/sections/*.md`.
7. Render static site files into `site/`:
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
- `OPENAI_MINIMIZE_COST` (default: `1`, auto-selects lowest estimated-cost model)
- `OPENAI_MODEL_CANDIDATES` (optional comma-separated model allowlist for auto-selection)
- `OPENAI_TEMPERATURE` (optional)
- `SECTION_PROMPTS_DIR` (optional override path for section prompt markdown files)
- `SYSTEM_PROMPT_FILE` (optional override path for system prompt markdown file)
- `WORKFLOW_PROMPT_FILE` (optional override path for workflow prompt markdown file; default `prompts/workflow.md`)
- `LLM_CURATION_MAX_CANDIDATES` (default `20`)
- `LLM_CURATION_WEIGHT` (default `1.3`)
- `LLM_CURATION_EXCLUDE_PENALTY` (default `8.0`)
- `X_BEARER_TOKEN` (for `type: x` sources)
- `LINKEDIN_ACCESS_TOKEN` (for `type: linkedin` sources)
- `LINKEDIN_API_VERSION` (default: `202503`)
- `LINKEDIN_AUTHOR_URN` (optional override for LinkedIn org/person URN)
- `DISCORD_APPLICATION_ID` (Discord app client id)
- `DISCORD_BOT_TOKEN` (Discord bot token)
- `DISCORD_GUILD_ID` (Discord server id)
- `DISCORD_CHANNEL_IDS` (comma-separated Discord channel ids)
- `FEED_TIMEZONE` (default: `America/New_York`)
- `NEWSLETTER_SUBSCRIBE_ENDPOINT` (optional subscribe API URL embedded in site header)

Discord setup helper:

```bash
python -m ai_news_feed.discord_setup \
  --application-id "$DISCORD_APPLICATION_ID" \
  --bot-token "$DISCORD_BOT_TOKEN" \
  --guild-id "$DISCORD_GUILD_ID" \
  --write-env .env \
  --append-feeds-other \
  --feeds-file config/feeds.md
```

What it automates:
- Builds install URL for your bot
- Validates bot token
- Lists accessible guilds/channels
- Writes Discord keys into `.env`
- Appends selected Discord channel notes into `config/feeds.md` section `4. other`

## Email Subscription API (Phase 1)

Phase 1 includes:
- Subscriber database (SQLite)
- Double opt-in confirmation flow
- Unsubscribe flow
- Confirmation/welcome emails via Resend

Run locally:

```bash
python -m ai_news_feed.subscriptions --init-db --serve --host 0.0.0.0 --port 8090
```

Deploy on Google Cloud Run (containerized):

```bash
PROJECT_ID="$(gcloud config get-value project)"
REGION="us-east1"
IMAGE="gcr.io/${PROJECT_ID}/ai-news-subscriptions:latest"

gcloud builds submit --tag "${IMAGE}" .
gcloud run deploy ai-news-subscriptions \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars SUBSCRIPTION_DB_PATH=/tmp/subscribers.db,NEWSLETTER_CORS_ORIGINS=https://johnmaconline.github.io
```

API endpoints:
- `POST /subscribe` with JSON body `{"email":"you@example.com","source":"site"}`
- `GET /confirm?token=...`
- `GET /unsubscribe?token=...`
- `GET /health`

Required env for email delivery:
- `RESEND_API_KEY`
- `NEWSLETTER_FROM_EMAIL`

Recommended env for production:
- `SUBSCRIPTION_PUBLIC_BASE_URL` (for confirm/unsubscribe links)
- `SUBSCRIPTION_TOKEN_SECRET`
- `SUBSCRIPTION_DB_PATH`
- `NEWSLETTER_CORS_ORIGINS`

To wire the website subscribe form:
- Set `NEWSLETTER_SUBSCRIBE_ENDPOINT` when generating the site.
- In GitHub Actions, set repository variable `NEWSLETTER_SUBSCRIBE_ENDPOINT` to your API URL.

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
- Built-in defaults include:
  - `hackernews-ai` (`type: hackernews`) in `config/sources.yaml`
  - `tldr-ai` (`type: rss`) in `config/sources.yaml`
  - Extra TLDR variants can stay in `config/feeds.md` under `1. URLs`
- Tune section scoring keywords in `ai_news_feed/config.py`.
- Adjust min/max links per section via CLI:

```bash
python -m ai_news_feed.main --min-per-section 3 --max-per-section 5
```

Disable LLM-assisted curation reranking:

```bash
python -m ai_news_feed.main --no-llm-curation
```

For social sources:
- `type: x` uses `query` (X recent search).
- `type: linkedin` uses `author_urn` and fetches from LinkedIn posts API.
- `type: reddit-search` uses Reddit search API (`q`, `sort`, `time`) for deeper daily Reddit mining.
- `LINKEDIN_AUTHOR_URN` in `.env` overrides the LinkedIn `author_urn` in `config/sources.yaml`, so you can switch orgs without editing YAML.
- If corresponding tokens are not set, those sources are skipped safely.

Software Development section intent:
- Focuses on practical implementation for developers: agent workflows, skills, and how-to guidance.
- Announcement-heavy items are deprioritized for this section and should appear only when they include reusable prompt patterns.

Under-the-Radar mining intent:
- Biases toward independent voices and practical builder content (Substack/Medium/dev blogs, Reddit workflow posts, smaller social accounts).
- Uses follower/community-size-aware scoring where available (for example X follower counts and Reddit subreddit size) to reduce dominance from very large accounts.

`config/feeds.md` behavior:
- This file is loaded on every run (default path).
- Daily runs also auto-discover new RSS feeds from article domains outside configured sources,
  validate them, and append them to `1. URLs` with `discovered=auto`.
- Daily runs also execute external web discovery queries (Google News RSS + DuckDuckGo by default)
  to find new relevant domains beyond existing feeds.
- Sections:
  - `1. URLs` (RSS/Atom URLs; optional metadata such as `name=`, `section=`, `tags=`)
  - `2. LinkedIN users` (LinkedIn `urn:li:...` or LinkedIn profile/company URLs)
  - `3. X users` (usernames like `@swyx` or profile URL)
  - `4. other` (notes only; not ingested)
- For URL entries, optional metadata `platform=substack` or `platform=medium` is supported.
  This lets you add article/profile URLs, and ingestion auto-converts them to feed endpoints.
- For LinkedIn URL entries, add `author_urn=urn:li:person:...` (or org URN) when available.
  Without a URN, the source is tracked but LinkedIn API ingestion is skipped.
- Auto-discovery controls:
  - `AUTO_DISCOVER_FEEDS=1` (default enabled; set `0` to disable)
  - `AUTO_DISCOVER_MAX_NEW_FEEDS=8` (max newly added feeds per run)
  - `AUTO_DISCOVER_MAX_DOMAINS=40` (max domains to probe per run)
  - `AUTO_DISCOVER_MIN_FEED_ENTRIES=5` (minimum entries required to accept a feed)
  - `AUTO_DISCOVER_WEB=1` (default enabled; external web query discovery)
  - `AUTO_DISCOVER_WEB_PROVIDER=all` (`all`, `google-news`, `duckduckgo`)
  - `AUTO_DISCOVER_WEB_MAX_QUERIES=18` (max query templates executed per run)
  - `AUTO_DISCOVER_WEB_MAX_RESULTS_PER_QUERY=8`
  - `AUTO_DISCOVER_WEB_MAX_CANDIDATES=120`
  - `AUTO_DISCOVER_WEB_RECENCY_DAYS=2`
- You can override the registry path:

```bash
python -m ai_news_feed.main --feeds-file config/feeds.md
```

Prompt customization:
- Edit `prompts/system.md` for global summarization behavior.
- Edit `prompts/workflow.md` for global workflow-level guidance shared by curation and summarization.
- Edit section-specific files in `prompts/sections/`:
  - `practical-prompts.md`
  - `engineering.md`
  - `product-development.md`
  - `software.md` (used by section slug `business`)
  - `under-the-radar.md`
  - `for-fun.md`

## Research References

See `docs/research.md` for the external references used to choose automation and ingestion patterns.
