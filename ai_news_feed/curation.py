##########################################################################################
#
# Script name: curation.py
#
# Description: Deduplication, scoring, and section-level curation logic.
#
##########################################################################################

import json
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .llm_utils import LlmUsageTotals, call_chat_completion_json
from .config import (
    BIG_ANNOUNCEMENT_INTENT_KEYWORDS,
    BIG_ANNOUNCEMENT_DOMAINS,
    BUSINESS_ANNOUNCEMENT_KEYWORDS,
    BUSINESS_PRACTICAL_KEYWORDS,
    KEYWORDS,
    LOW_SIGNAL_BIG_ANNOUNCEMENT_DOMAINS,
    MAINSTREAM_DOMAINS,
    RECENCY_REQUIRED_HOURS,
    SECTION_TARGET_MAX,
    SECTION_TARGET_MIN,
    SECTIONS,
    UNDER_THE_RADAR_BUILDER_KEYWORDS,
    UNDER_THE_RADAR_INDEPENDENT_PLATFORM_HINTS,
)
from .models import Article
from .utils import canonicalize_url, normalize_whitespace

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************

log = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(os.getenv('SECTION_PROMPTS_DIR') or (ROOT_DIR / 'prompts' / 'sections'))
SYSTEM_PROMPT_PATH = Path(os.getenv('SYSTEM_PROMPT_FILE') or (ROOT_DIR / 'prompts' / 'system.md'))
WORKFLOW_PROMPT_PATH = Path(os.getenv('WORKFLOW_PROMPT_FILE') or (ROOT_DIR / 'prompts' / 'workflow.md'))
DEFAULT_CURATION_SYSTEM_PROMPT = 'You are a strict AI news curator. Return JSON only.'


# ****************************************************************************************
# Functions
# ****************************************************************************************


def dedupe_articles(articles: list[Article]) -> list[Article]:
    unique: dict[str, Article] = {}
    for article in articles:
        key = canonicalize_url(article.url) or normalize_whitespace(article.title).lower()
        existing = unique.get(key)
        if existing is None:
            unique[key] = article
            continue
        existing_score = existing.priority + existing.metrics.get('points', 0) * 0.01
        incoming_score = article.priority + article.metrics.get('points', 0) * 0.01
        if incoming_score > existing_score:
            unique[key] = article
    return list(unique.values())


def _keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


def _recency_score(article: Article, feed_dt: datetime) -> float:
    if article.published_at is None:
        return 0.0
    delta_hours = (feed_dt - article.published_at).total_seconds() / 3600
    delta_hours = max(0.0, delta_hours)
    return max(0.0, 4.0 * math.exp(-delta_hours / 24))


def _is_within_recency_window(article: Article, feed_dt: datetime, max_age_hours: float) -> bool:
    if article.published_at is None:
        return False
    delta_hours = (feed_dt - article.published_at).total_seconds() / 3600
    if delta_hours <= 0:
        return True
    return delta_hours <= max_age_hours


def _business_penalty(article: Article, text_blob: str) -> float:
    penalty = 0.0
    announcement_hits = _keyword_hits(text_blob, BUSINESS_ANNOUNCEMENT_KEYWORDS)
    practical_hits = _keyword_hits(text_blob, BUSINESS_PRACTICAL_KEYWORDS)
    penalty += announcement_hits * 2.0
    if practical_hits == 0:
        penalty += 2.2
    if article.domain in BIG_ANNOUNCEMENT_DOMAINS:
        penalty += 3.0
    if article.section_hint == 'big-announcements':
        penalty += 3.0
    return penalty


def _is_big_announcement_candidate(article: Article, text_blob: str) -> bool:
    intent_hits = _keyword_hits(text_blob, BIG_ANNOUNCEMENT_INTENT_KEYWORDS)
    if article.domain in BIG_ANNOUNCEMENT_DOMAINS:
        return True
    if article.section_hint == 'big-announcements' and intent_hits >= 1:
        return True
    if intent_hits >= 2:
        return True
    return False


def _under_the_radar_boost(article: Article, text_blob: str) -> float:
    boost = 0.0
    if any(hint in article.domain for hint in UNDER_THE_RADAR_INDEPENDENT_PLATFORM_HINTS):
        boost += 1.8
    if _keyword_hits(text_blob, UNDER_THE_RADAR_BUILDER_KEYWORDS) > 0:
        boost += 1.2
    if article.source_type in {'x', 'linkedin'}:
        followers = article.metrics.get('followers', 0.0)
        if followers > 0:
            if followers <= 20_000:
                boost += 2.0
            elif followers <= 100_000:
                boost += 1.0
            elif followers >= 1_000_000:
                boost -= 2.0
        if article.metrics.get('verified', 0.0) >= 1.0:
            boost -= 0.6
    if article.source_type == 'reddit':
        subreddit_subscribers = article.metrics.get('subreddit_subscribers', 0.0)
        if subreddit_subscribers > 0:
            if subreddit_subscribers <= 100_000:
                boost += 2.0
            elif subreddit_subscribers <= 500_000:
                boost += 1.0
            elif subreddit_subscribers >= 3_000_000:
                boost -= 1.5
        boost += min(1.4, article.metrics.get('comments', 0.0) / 80.0)
    return boost


def _is_curator_watchlist_article(article: Article) -> bool:
    tag_set = {tag.strip().lower() for tag in article.tags if isinstance(tag, str)}
    return 'curators' in tag_set


def _curator_watchlist_enabled() -> bool:
    raw_value = (os.getenv('CURATOR_WATCHLIST_ENABLED') or '1').strip().lower()
    return raw_value not in {'0', 'false', 'no', 'off', 'disabled'}


def _curator_watchlist_score_boost(section_slug: str) -> float:
    raw_value = (os.getenv('CURATOR_WATCHLIST_SCORE_BOOST') or '').strip()
    if not raw_value:
        base_boost = 1.25
    else:
        try:
            base_boost = float(raw_value)
        except ValueError:
            base_boost = 1.25
    base_boost = max(0.0, min(base_boost, 5.0))
    if section_slug == 'under-the-radar':
        return min(0.25, base_boost * 0.2)
    if section_slug == 'for-fun':
        return base_boost * 0.5
    return base_boost


def _curator_watchlist_per_section_cap() -> int:
    raw_value = (os.getenv('CURATOR_WATCHLIST_PER_SECTION_CAP') or '').strip()
    if not raw_value:
        return 1
    try:
        parsed = int(raw_value)
    except ValueError:
        return 1
    return max(0, min(parsed, 3))


def _curator_watchlist_max_total() -> int:
    raw_value = (os.getenv('CURATOR_WATCHLIST_MAX_TOTAL') or '').strip()
    if not raw_value:
        return 4
    try:
        parsed = int(raw_value)
    except ValueError:
        return 4
    return max(0, min(parsed, 12))


def _curator_watchlist_min_score() -> float:
    raw_value = (os.getenv('CURATOR_WATCHLIST_MIN_SCORE') or '').strip()
    if not raw_value:
        return 2.0
    try:
        parsed = float(raw_value)
    except ValueError:
        return 2.0
    return max(-5.0, min(parsed, 30.0))


@lru_cache(maxsize=1)
def _load_curation_system_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        return DEFAULT_CURATION_SYSTEM_PROMPT
    try:
        content = SYSTEM_PROMPT_PATH.read_text(encoding='utf-8').strip()
    except OSError as exc:
        log.warning('Failed reading system prompt file %s: %s', SYSTEM_PROMPT_PATH, exc)
        return DEFAULT_CURATION_SYSTEM_PROMPT
    return content or DEFAULT_CURATION_SYSTEM_PROMPT


@lru_cache(maxsize=1)
def _load_workflow_prompt() -> str:
    if not WORKFLOW_PROMPT_PATH.exists():
        return ''
    try:
        content = WORKFLOW_PROMPT_PATH.read_text(encoding='utf-8').strip()
    except OSError as exc:
        log.warning('Failed reading workflow prompt file %s: %s', WORKFLOW_PROMPT_PATH, exc)
        return ''
    return content


@lru_cache(maxsize=16)
def _load_section_prompt(section_slug: str) -> str:
    prompt_filename = 'software.md' if section_slug == 'business' else f'{section_slug}.md'
    prompt_path = PROMPTS_DIR / prompt_filename
    if not prompt_path.exists():
        return ''
    try:
        return prompt_path.read_text(encoding='utf-8').strip()
    except OSError as exc:
        log.warning('Failed reading section prompt file %s: %s', prompt_path, exc)
        return ''


def _refresh_article_assignments(articles: list[Article]) -> None:
    for article in articles:
        if not article.scores:
            continue
        top_section, top_score = max(article.scores.items(), key=lambda item: item[1])
        article.assigned_section = top_section
        article.section_score = top_score


def _llm_curation_max_candidates() -> int:
    raw_value = (os.getenv('LLM_CURATION_MAX_CANDIDATES') or '').strip()
    if not raw_value:
        return 20
    try:
        parsed = int(raw_value)
    except ValueError:
        return 20
    return max(5, min(parsed, 50))


def _llm_curation_weight() -> float:
    raw_value = (os.getenv('LLM_CURATION_WEIGHT') or '').strip()
    if not raw_value:
        return 1.3
    try:
        parsed = float(raw_value)
    except ValueError:
        return 1.3
    return max(0.1, min(parsed, 4.0))


def _llm_curation_exclude_penalty() -> float:
    raw_value = (os.getenv('LLM_CURATION_EXCLUDE_PENALTY') or '').strip()
    if not raw_value:
        return 8.0
    try:
        parsed = float(raw_value)
    except ValueError:
        return 8.0
    return max(1.0, min(parsed, 20.0))


def _build_llm_curation_payload(section_slug: str, candidates: list[Article]) -> list[dict]:
    rows: list[dict] = []
    for article in candidates:
        rows.append(
            {
                'id': article.id,
                'title': article.title,
                'source': article.source_name,
                'domain': article.domain,
                'url': article.url,
                'summary_input': article.summary[:420],
                'rule_score': round(article.scores.get(section_slug, 0.0), 3),
                'section_hint': article.section_hint or '',
                'source_type': article.source_type,
            }
        )
    return rows


def _try_llm_section_adjustments(
    section_slug: str,
    candidates: list[Article],
    usage_totals: LlmUsageTotals,
) -> dict[str, dict]:
    api_key = os.getenv('OPENAI_API_KEY')
    preferred_model = os.getenv('OPENAI_MODEL') or 'gpt-5-mini'
    if not api_key or OpenAI is None or not candidates:
        return {}

    client = OpenAI(api_key=api_key)
    payload = _build_llm_curation_payload(section_slug, candidates)
    system_prompt = _load_curation_system_prompt()
    workflow_prompt = _load_workflow_prompt()
    section_prompt = _load_section_prompt(section_slug)
    user_prompt = (
        f'Section: {section_slug}\n'
        'Global workflow guidance markdown:\n'
        f'{workflow_prompt}\n\n'
        'Section guidance markdown:\n'
        f'{section_prompt}\n\n'
        'Task:\n'
        'Rate each candidate for fit to this section using semantic reasoning, actionability, and signal quality.\n'
        'Do not hallucinate. Use only provided fields. Prefer original, high-signal, and practical items.\n'
        'Return strict JSON with shape:\n'
        '{"items":[{"id":"...","score":0-10,"exclude":false,"reason":"..."}]}\n'
        f'Input JSON:\n{json.dumps(payload, ensure_ascii=True)}'
    )
    try:
        response, selected_model, selection_info, temperature_fallback_retry = call_chat_completion_json(
            client=client,
            logger=log,
            preferred_model=preferred_model,
            operation=f'curation:{section_slug}',
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        usage_totals.call_count += 1
        usage_totals.add_estimate(selection_info)
        usage_totals.add_usage(response, selected_model)
        if temperature_fallback_retry:
            usage_totals.temperature_fallback_retries += 1
        content = response.choices[0].message.content
        parsed = json.loads(content or '{}')
    except Exception as exc:  # noqa: BLE001
        log.warning('LLM curation failed for section=%s: %s', section_slug, exc)
        return {}

    rows = parsed.get('items') or []
    if not isinstance(rows, list):
        return {}
    output: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get('id') or '').strip()
        if not row_id:
            continue
        raw_score = row.get('score', 5.0)
        try:
            score_value = float(raw_score)
        except (TypeError, ValueError):
            score_value = 5.0
        score_value = max(0.0, min(score_value, 10.0))
        exclude = bool(row.get('exclude') is True)
        reason = str(row.get('reason') or '').strip()
        output[row_id] = {
            'score': score_value,
            'exclude': exclude,
            'reason': reason[:220],
        }
    return output


def _apply_llm_curation_adjustments(
    articles: list[Article],
    by_section: dict[str, list[Article]],
    enable_llm_curation: bool,
) -> None:
    if not enable_llm_curation:
        log.info('LLM curation disabled via CLI flag.')
        return
    if OpenAI is None:
        return
    if not os.getenv('OPENAI_API_KEY'):
        return

    usage_totals = LlmUsageTotals()
    llm_weight = _llm_curation_weight()
    exclude_penalty = _llm_curation_exclude_penalty()
    max_candidates = _llm_curation_max_candidates()
    for section in SECTIONS:
        section_slug = section.slug
        ranked = sorted(
            by_section.get(section_slug, []),
            key=lambda item: item.scores.get(section_slug, 0.0),
            reverse=True,
        )
        candidates = ranked[:max_candidates]
        if not candidates:
            continue
        llm_rows = _try_llm_section_adjustments(section_slug, candidates, usage_totals)
        if not llm_rows:
            continue
        for article in candidates:
            row = llm_rows.get(article.id)
            if not row:
                continue
            llm_score = float(row.get('score') or 5.0)
            exclude = bool(row.get('exclude'))
            delta = (llm_score - 5.0) * llm_weight
            if exclude:
                delta -= exclude_penalty
            article.scores[section_slug] = round(article.scores.get(section_slug, 0.0) + delta, 3)
            score_key = section_slug.replace('-', '_')
            article.metrics[f'llm_score_{score_key}'] = llm_score
        log.info('LLM curation adjusted %s candidate(s) for section=%s', len(llm_rows), section_slug)

    if usage_totals.call_count > 0:
        usage_totals.log_summary(log, label='LLM curation totals')
        _refresh_article_assignments(articles)


def score_articles(articles: list[Article], feed_dt: datetime | None = None) -> None:
    if feed_dt is None:
        feed_dt = datetime.now(timezone.utc)
    for article in articles:
        text_blob = article.canonical_text().lower()
        scores: dict[str, float] = {}
        base = article.priority + _recency_score(article, feed_dt)
        for section in SECTIONS:
            section_score = base
            hits = _keyword_hits(text_blob, KEYWORDS.get(section.slug, []))
            section_score += hits * 1.5
            if article.section_hint == section.slug:
                if section.slug == 'business':
                    section_score += 2.2
                else:
                    section_score += 4.5
            if section.slug == 'big-announcements' and article.domain in BIG_ANNOUNCEMENT_DOMAINS:
                section_score += 2.2
            if section.slug == 'big-announcements':
                intent_hits = _keyword_hits(text_blob, BIG_ANNOUNCEMENT_INTENT_KEYWORDS)
                section_score += intent_hits * 1.7
                if article.domain in BIG_ANNOUNCEMENT_DOMAINS:
                    section_score += 1.2
                if article.domain in LOW_SIGNAL_BIG_ANNOUNCEMENT_DOMAINS:
                    section_score -= 3.0
                if not _is_big_announcement_candidate(article, text_blob):
                    section_score -= 5.0
            if section.slug == 'under-the-radar':
                if article.domain not in MAINSTREAM_DOMAINS:
                    section_score += 1.6
                else:
                    section_score -= 0.8
                section_score += _under_the_radar_boost(article, text_blob)
            if section.slug in {'engineering', 'product-development'}:
                section_score += min(2.0, article.metrics.get('points', 0.0) / 150.0)
            if section.slug == 'business':
                section_score += min(2.0, article.metrics.get('points', 0.0) / 220.0)
                section_score += _keyword_hits(text_blob, BUSINESS_PRACTICAL_KEYWORDS) * 1.2
                section_score -= _business_penalty(article, text_blob)
            if _is_curator_watchlist_article(article):
                section_score += _curator_watchlist_score_boost(section.slug)
            scores[section.slug] = round(section_score, 3)
        article.scores = scores
    _refresh_article_assignments(articles)


def _pick_candidates(
    candidates: list[Article],
    score_key: str,
    picked_ids: set[str],
    max_items: int,
    domain_cap: int = 2,
) -> list[Article]:
    selected: list[Article] = []
    domain_counts: defaultdict[str, int] = defaultdict(int)
    sorted_candidates = sorted(candidates, key=lambda item: item.scores.get(score_key, 0.0), reverse=True)
    for article in sorted_candidates:
        if len(selected) >= max_items:
            break
        if article.id in picked_ids:
            continue
        if domain_counts[article.domain] >= domain_cap:
            continue
        selected.append(article)
        picked_ids.add(article.id)
        domain_counts[article.domain] += 1
    return selected


def curate_sections(
    articles: list[Article],
    min_per_section: int = SECTION_TARGET_MIN,
    max_per_section: int = SECTION_TARGET_MAX,
    feed_dt: datetime | None = None,
    enable_llm_curation: bool = True,
) -> dict[str, list[Article]]:
    if feed_dt is None:
        feed_dt = datetime.now(timezone.utc)
    recent_articles = [
        article
        for article in articles
        if _is_within_recency_window(article, feed_dt, RECENCY_REQUIRED_HOURS)
    ]
    articles = recent_articles
    score_articles(articles, feed_dt=feed_dt)
    sections: dict[str, list[Article]] = {section.slug: [] for section in SECTIONS}
    picked_ids: set[str] = set()
    curator_enabled = _curator_watchlist_enabled()
    curator_per_section_cap = _curator_watchlist_per_section_cap() if curator_enabled else 0
    curator_total_cap = _curator_watchlist_max_total() if curator_enabled else 0
    curator_min_score = _curator_watchlist_min_score() if curator_enabled else 0.0
    curator_total_selected = 0

    by_section: dict[str, list[Article]] = {section.slug: [] for section in SECTIONS}
    for article in articles:
        for section in SECTIONS:
            if article.scores.get(section.slug, 0.0) > 0:
                by_section[section.slug].append(article)
    _apply_llm_curation_adjustments(
        articles=articles,
        by_section=by_section,
        enable_llm_curation=enable_llm_curation,
    )

    for section in SECTIONS:
        candidate_pool = by_section[section.slug]
        if section.slug == 'big-announcements':
            narrowed = [
                article
                for article in candidate_pool
                if _is_big_announcement_candidate(article, article.canonical_text().lower())
            ]
            if narrowed:
                candidate_pool = narrowed
        picks: list[Article] = []
        if (
            curator_enabled
            and curator_per_section_cap > 0
            and curator_total_selected < curator_total_cap
        ):
            curator_slots_left = max(0, curator_total_cap - curator_total_selected)
            section_curator_cap = min(curator_per_section_cap, curator_slots_left)
            curator_pool = [
                article
                for article in candidate_pool
                if _is_curator_watchlist_article(article)
                and article.scores.get(section.slug, 0.0) >= curator_min_score
            ]
            if curator_pool and section_curator_cap > 0:
                preselected = _pick_candidates(
                    candidates=curator_pool,
                    score_key=section.slug,
                    picked_ids=picked_ids,
                    max_items=section_curator_cap,
                    domain_cap=1,
                )
                picks.extend(preselected)
                curator_total_selected += len(preselected)
        fill_pool = candidate_pool
        if curator_enabled:
            non_curator_pool = [item for item in candidate_pool if not _is_curator_watchlist_article(item)]
            if non_curator_pool:
                fill_pool = non_curator_pool
            elif curator_total_selected >= curator_total_cap:
                fill_pool = []
        remaining_slots = max(0, max_per_section - len(picks))
        if remaining_slots > 0:
            picks.extend(
                _pick_candidates(
                    candidates=fill_pool,
                    score_key=section.slug,
                    picked_ids=picked_ids,
                    max_items=remaining_slots,
                )
            )
        sections[section.slug] = picks

    # Backfill sections that did not reach minimum target.
    for section in SECTIONS:
        if len(sections[section.slug]) >= min_per_section:
            continue
        needed = min_per_section - len(sections[section.slug])
        fallback_pool = articles
        if curator_enabled and curator_total_selected >= curator_total_cap:
            non_curator_fallback = [item for item in fallback_pool if not _is_curator_watchlist_article(item)]
            if non_curator_fallback:
                fallback_pool = non_curator_fallback
        if section.slug == 'big-announcements':
            narrowed = [
                article
                for article in articles
                if _is_big_announcement_candidate(article, article.canonical_text().lower())
            ]
            if narrowed:
                fallback_pool = narrowed
        fallbacks = _pick_candidates(
            candidates=fallback_pool,
            score_key=section.slug,
            picked_ids=picked_ids,
            max_items=needed,
            domain_cap=3,
        )
        sections[section.slug].extend(fallbacks)
        curator_total_selected += sum(1 for item in fallbacks if _is_curator_watchlist_article(item))

    if curator_enabled and curator_total_cap > 0:
        log.info(
            'Curator watchlist sampling selected %s item(s) (max_total=%s, per_section_cap=%s).',
            curator_total_selected,
            curator_total_cap,
            curator_per_section_cap,
        )

    return sections
