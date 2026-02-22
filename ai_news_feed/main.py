from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import SECTIONS, SECTION_TARGET_MAX, SECTION_TARGET_MIN
from .curation import curate_sections, dedupe_articles
from .fetchers import build_sample_articles, fetch_all_sources, load_source_config
from .models import DailyFeed
from .render import write_site
from .summarizer import enrich_summaries
from .utils import utc_now_iso


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


def _resolve_feed_date(explicit_date: str | None) -> str:
    if explicit_date:
        return explicit_date
    tz_name = os.getenv("FEED_TIMEZONE") or "America/New_York"
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001
        now = datetime.now(ZoneInfo("UTC"))
    return now.strftime("%Y-%m-%d")


def build_daily_feed(
    date: str,
    source_config_path: str,
    output_dir: str,
    min_per_section: int,
    max_per_section: int,
    use_sample_data: bool = False,
) -> None:
    if use_sample_data:
        articles = build_sample_articles()
    else:
        sources = load_source_config(source_config_path)
        articles = fetch_all_sources(sources)
    articles = dedupe_articles(articles)
    if not articles:
        raise RuntimeError("No articles fetched. Aborting publish to avoid empty feed.")

    sections = curate_sections(
        articles=articles,
        min_per_section=min_per_section,
        max_per_section=max_per_section,
    )
    enrich_summaries(sections)
    title = f"Daily AI Feed - {date}"
    intro = (
        "A curated daily AI briefing with original-source links across industry announcements, "
        "engineering, product development, business, under-the-radar signals, and fun experiments."
    )
    ordered_sections = {section.slug: sections.get(section.slug, []) for section in SECTIONS}
    feed = DailyFeed(
        date=date,
        generated_at=utc_now_iso(),
        title=title,
        sections=ordered_sections,
        intro=intro,
    )
    write_site(feed, output_dir=output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and publish a daily AI feed.")
    parser.add_argument("--date", help="Date string in YYYY-MM-DD format.", default=None)
    parser.add_argument("--config", default="config/sources.yaml", help="Path to source config YAML.")
    parser.add_argument("--output-dir", default="site", help="Directory where static site is written.")
    parser.add_argument("--min-per-section", type=int, default=SECTION_TARGET_MIN)
    parser.add_argument("--max-per-section", type=int, default=SECTION_TARGET_MAX)
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use local sample data and skip all network requests.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _configure_logging(args.verbose)
    date = _resolve_feed_date(args.date)
    build_daily_feed(
        date=date,
        source_config_path=args.config,
        output_dir=args.output_dir,
        min_per_section=args.min_per_section,
        max_per_section=args.max_per_section,
        use_sample_data=args.sample,
    )
    print(f"Generated site for {date} at {args.output_dir}")  # noqa: T201


if __name__ == "__main__":
    main()
