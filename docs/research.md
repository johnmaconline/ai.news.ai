# Research Notes: Daily AI Feed Automation

Date: 2026-02-22

## Key Findings

1. GitHub Actions scheduled workflows use POSIX cron syntax and run on UTC.
   Source: <https://docs.github.com/en/actions/reference/events-that-trigger-workflows#schedule>

2. Scheduled workflows run on the latest commit of the default branch.
   Source: <https://docs.github.com/en/actions/reference/events-that-trigger-workflows#schedule>

3. GitHub Pages supports custom workflow deployment using:
   - `actions/configure-pages`
   - `actions/upload-pages-artifact`
   - `actions/deploy-pages`
   Source: <https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages>

4. Events created with `GITHUB_TOKEN` do not recursively trigger other workflows (except specific event types), which avoids infinite CI loops when committing generated content.
   Source: <https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow>

5. Hacker News has an official Firebase API with list endpoints (`topstories`, `newstories`, etc.) and item detail endpoints (`/v0/item/<id>.json`).
   Source: <https://github.com/HackerNews/API>

6. OpenAI supports structured JSON outputs and Python SDK usage with API-key environment configuration.
   Sources:
   - <https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses>
   - <https://platform.openai.com/docs/libraries>

7. RSS 2.0 is a stable syndication format suitable for low-maintenance ingestion from official blogs and news sources.
   Source: <https://www.rssboard.org/rss-specification>

## Applied Decisions

- Use a static site + daily workflow for maximum reliability and low ops overhead.
- Prefer source feeds/APIs that are public and machine-readable (RSS, Hacker News API).
- Keep source attribution explicit: every story links to original URL.
- Keep summarization optional: OpenAI-enabled when configured, deterministic fallback otherwise.
- Store daily JSON snapshots to preserve history and support future API or UI expansions.

