##########################################################################################
#
# Script name: main.py
#
# Description: CLI entrypoint for generating and publishing the daily AI feed.
#
##########################################################################################

import argparse
import logging
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import SECTIONS, SECTION_TARGET_MAX, SECTION_TARGET_MIN
from .curation import curate_sections, dedupe_articles
from .fetchers import build_sample_articles, fetch_all_sources, load_source_config
from .models import DailyFeed
from .render import write_site
from .summarizer import enrich_summaries
from .utils import utc_now_iso


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************

log = logging.getLogger(os.path.basename(sys.argv[0]))
log.setLevel(logging.DEBUG)
log.propagate = False
formatter = logging.Formatter(
    '%(asctime)-15s [%(funcName)25s:%(lineno)-5s] %(levelname)-8s %(message)s'
)

# File handler for logging
fh = logging.FileHandler('ai_news_feed.log', mode='w')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
if not any(isinstance(handler, logging.FileHandler) for handler in log.handlers):
    log.addHandler(fh)

root_log = logging.getLogger()
root_log.setLevel(logging.DEBUG)
if not any(isinstance(handler, logging.FileHandler) for handler in root_log.handlers):
    root_log.addHandler(fh)


# ****************************************************************************************
# Functions
# ****************************************************************************************


def _resolve_feed_date(explicit_date: str | None) -> str:
    if explicit_date:
        return explicit_date
    tz_name = os.getenv('FEED_TIMEZONE') or 'America/New_York'
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001
        now = datetime.now(ZoneInfo('UTC'))
    return now.strftime('%Y-%m-%d')


def build_daily_feed(
    feed_date: str,
    source_config_path: str,
    feeds_file: str,
    output_dir: str,
    min_per_section: int,
    max_per_section: int,
    use_sample_data: bool = False,
) -> None:
    if use_sample_data:
        articles = build_sample_articles()
        log.debug('Using sample data for feed generation.')
    else:
        sources = load_source_config(source_config_path, feeds_file=feeds_file)
        articles = fetch_all_sources(sources)
        log.debug('Fetched %d raw articles from configured sources.', len(articles))

    articles = dedupe_articles(articles)
    log.debug('Article count after dedupe: %d', len(articles))
    if not articles:
        raise RuntimeError('No articles fetched. Aborting publish to avoid empty feed.')

    sections = curate_sections(
        articles=articles,
        min_per_section=min_per_section,
        max_per_section=max_per_section,
    )
    enrich_summaries(sections)
    title = f'Daily AI Feed - {feed_date}'
    intro = (
        'A curated daily AI briefing with original-source links across industry announcements, '
        'engineering, product development, software development, under-the-radar signals, and fun experiments.'
    )
    ordered_sections = {section.slug: sections.get(section.slug, []) for section in SECTIONS}
    feed = DailyFeed(
        date=feed_date,
        generated_at=utc_now_iso(),
        title=title,
        sections=ordered_sections,
        intro=intro,
    )
    write_site(feed, output_dir=output_dir)


# ****************************************************************************************
# Handle the arguments
# ****************************************************************************************


def handle_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate and publish a daily AI feed.')
    parser.add_argument('--date', help='Date string in YYYY-MM-DD format.', default=None)
    parser.add_argument('--config', default='config/sources.yaml', help='Path to source config YAML.')
    parser.add_argument(
        '--feeds-file',
        default='config/feeds.md',
        help='Path to markdown feed registry (URLs, LinkedIn users, X users).',
    )
    parser.add_argument('--output-dir', default='site', help='Directory where static site is written.')
    parser.add_argument('--min-per-section', type=int, default=SECTION_TARGET_MIN)
    parser.add_argument('--max-per-section', type=int, default=SECTION_TARGET_MAX)
    parser.add_argument(
        '--sample',
        action='store_true',
        help='Use local sample data and skip all network requests.',
    )
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output to stdout.')
    parser.add_argument('-q', '--quiet', action='store_true', help='Minimal stdout.')
    args = parser.parse_args()

    # Configure stdout logging based on arguments
    ch = logging.StreamHandler(sys.stdout)
    if args.verbose:
        ch.setLevel(logging.DEBUG)
    elif args.quiet:
        ch.setLevel(logging.ERROR)
    else:
        ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    log.addHandler(ch)
    root_log.addHandler(ch)

    log.debug('Checking script requirements...')
    if not args.verbose and not args.quiet:
        log.debug('No output level specified. Defaulting to INFO.')

    log.info('++++++++++++++++++++++++++++++++++++++++++++++')
    log.info('+  %s', os.path.basename(sys.argv[0]))
    log.info('+  Python Version: %s', sys.version.split()[0])
    log.info('+  Today is: %s', date.today())
    log.info('++++++++++++++++++++++++++++++++++++++++++++++')
    return args


# ****************************************************************************************
# Main
# ****************************************************************************************


def main() -> None:
    args = handle_args()
    feed_date = _resolve_feed_date(args.date)
    build_daily_feed(
        feed_date=feed_date,
        source_config_path=args.config,
        feeds_file=args.feeds_file,
        output_dir=args.output_dir,
        min_per_section=args.min_per_section,
        max_per_section=args.max_per_section,
        use_sample_data=args.sample,
    )
    log.info('Generated site for %s at %s', feed_date, args.output_dir)


if __name__ == '__main__':
    main()
