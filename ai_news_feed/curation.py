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
import re
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .llm_utils import LlmUsageTotals, call_chat_completion_json, openai_client_kwargs
from .config import (
    BIG_ANNOUNCEMENT_DOMAINS,
    BUSINESS_ANNOUNCEMENT_KEYWORDS,
    BUSINESS_PRACTICAL_KEYWORDS,
    BIG_ANNOUNCEMENT_INTENT_KEYWORDS,
    FOR_FUN_EXCLUDE_KEYWORDS,
    FOR_FUN_REQUIRED_KEYWORDS,
    HIGH_SIGNAL_MODEL_RELEASE_KEYWORDS,
    HIGH_SIGNAL_RECENCY_HOURS,
    KEYWORDS,
    LOW_SIGNAL_BIG_ANNOUNCEMENT_DOMAINS,
    MAINSTREAM_DOMAINS,
    PRACTICAL_PROMPT_EXCLUDE_KEYWORDS,
    PRACTICAL_PROMPT_REQUIRED_KEYWORDS,
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
    duplicate_clusters: defaultdict[str, list[Article]] = defaultdict(list)
    for article in articles:
        key = canonicalize_url(article.url) or normalize_whitespace(article.title).lower()
        duplicate_clusters[key].append(article)
        existing = unique.get(key)
        if existing is None:
            unique[key] = article
            continue
        existing_score = existing.priority + existing.metrics.get('points', 0) * 0.01
        incoming_score = article.priority + article.metrics.get('points', 0) * 0.01
        if incoming_score > existing_score:
            unique[key] = article
    deduped = list(unique.values())
    _apply_duplicate_cluster_metadata(
        deduped_articles=deduped,
        duplicate_clusters=duplicate_clusters,
    )
    return deduped


def _title_fingerprint(title: str) -> str:
    normalized = normalize_whitespace(title).lower()
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
    tokens = [token for token in normalized.split() if token not in {'the', 'a', 'an', 'and', 'or', 'to', 'for'}]
    if not tokens:
        return ''
    return ' '.join(tokens[:14])


def _merge_corroborating_urls(existing: list[str], additions: list[str], max_urls: int = 6) -> list[str]:
    seen = {canonicalize_url(url) for url in existing if canonicalize_url(url)}
    merged: list[str] = []
    for url in existing:
        normalized = canonicalize_url(url)
        if not normalized or normalized in merged:
            continue
        merged.append(normalized)
    for url in additions:
        normalized = canonicalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
        if len(merged) >= max_urls:
            break
    return merged[:max_urls]


def _apply_duplicate_cluster_metadata(
    deduped_articles: list[Article],
    duplicate_clusters: dict[str, list[Article]],
) -> None:
    by_primary_id = {article.id: article for article in deduped_articles}
    for cluster_rows in duplicate_clusters.values():
        if len(cluster_rows) <= 1:
            continue
        canonical_urls = [canonicalize_url(item.url) for item in cluster_rows]
        corroborating_urls = [url for url in canonical_urls if url]
        for row in cluster_rows:
            primary = by_primary_id.get(row.id)
            if primary is None:
                continue
            existing_cluster_size = int(primary.metrics.get('duplicate_cluster_size', 1))
            primary.metrics['duplicate_cluster_size'] = float(max(existing_cluster_size, len(corroborating_urls)))
            related_urls = [url for url in corroborating_urls if url and url != canonicalize_url(primary.url)]
            if related_urls:
                primary.corroborating_urls = _merge_corroborating_urls(
                    existing=primary.corroborating_urls,
                    additions=related_urls,
                )

    by_fingerprint: defaultdict[str, list[Article]] = defaultdict(list)
    for article in deduped_articles:
        fingerprint = _title_fingerprint(article.title)
        if fingerprint:
            by_fingerprint[fingerprint].append(article)
    for similar_rows in by_fingerprint.values():
        if len(similar_rows) <= 1:
            continue
        related_urls = [canonicalize_url(item.url) for item in similar_rows if canonicalize_url(item.url)]
        if len(related_urls) <= 1:
            continue
        for article in similar_rows:
            existing_cluster_size = int(article.metrics.get('duplicate_cluster_size', 1))
            article.metrics['duplicate_cluster_size'] = float(max(existing_cluster_size, len(related_urls)))
            article.corroborating_urls = _merge_corroborating_urls(
                existing=article.corroborating_urls,
                additions=[url for url in related_urls if url != canonicalize_url(article.url)],
            )


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


def _source_quality_score(article: Article) -> float:
    domain = (article.domain or '').lower()
    score = 4.0
    if article.source_type in {'rss', 'arxiv', 'hackernews'}:
        score += 1.6
    if article.source_type in {'reddit', 'x', 'linkedin'}:
        score += 0.8
    if domain in MAINSTREAM_DOMAINS:
        score += 2.0
    if domain in LOW_SIGNAL_BIG_ANNOUNCEMENT_DOMAINS:
        score -= 1.5
    if article.metrics.get('points', 0.0) > 0:
        score += min(1.6, math.log1p(article.metrics.get('points', 0.0)) / 3.0)
    duplicate_cluster_size = max(1.0, float(article.metrics.get('duplicate_cluster_size', 1.0)))
    if duplicate_cluster_size > 1:
        score += min(1.4, (duplicate_cluster_size - 1.0) * 0.4)
    return max(0.0, min(score, 10.0))


def _novelty_score(article: Article, text_blob: str) -> float:
    score = 5.0
    if article.domain not in MAINSTREAM_DOMAINS:
        score += 1.7
    if article.source_type in {'x', 'linkedin', 'reddit'}:
        score += 0.8
    if _keyword_hits(text_blob, UNDER_THE_RADAR_BUILDER_KEYWORDS) > 0:
        score += 1.0
    duplicate_cluster_size = max(1.0, float(article.metrics.get('duplicate_cluster_size', 1.0)))
    if duplicate_cluster_size > 1:
        score -= min(2.6, (duplicate_cluster_size - 1.0) * 0.9)
    return max(0.0, min(score, 10.0))


def _confidence_score(article: Article) -> float:
    duplicate_cluster_size = max(1.0, float(article.metrics.get('duplicate_cluster_size', 1.0)))
    corroboration_boost = min(2.0, (duplicate_cluster_size - 1.0) * 0.45)
    confidence = (
        article.source_quality_score * 0.52
        + article.recency_score * 0.25
        + article.novelty_score * 0.08
        + corroboration_boost
    )
    if article.summary_text:
        confidence += 0.3
    return max(0.0, min(confidence, 10.0))


def _is_software_development_candidate(article: Article, text_blob: str) -> bool:
    practical_hits = _keyword_hits(text_blob, BUSINESS_PRACTICAL_KEYWORDS)
    announcement_hits = _keyword_hits(text_blob, BUSINESS_ANNOUNCEMENT_KEYWORDS)
    if practical_hits >= 2:
        return True
    if practical_hits >= 1 and announcement_hits == 0:
        return True
    if article.section_hint == 'business' and practical_hits >= 1:
        return True
    return False


def _is_practical_prompt_candidate(article: Article, text_blob: str) -> bool:
    required_hits = _keyword_hits(text_blob, PRACTICAL_PROMPT_REQUIRED_KEYWORDS)
    exclude_hits = _keyword_hits(text_blob, PRACTICAL_PROMPT_EXCLUDE_KEYWORDS)
    if required_hits >= 2 and exclude_hits == 0:
        return True
    if required_hits >= 1 and exclude_hits == 0:
        return True
    if article.section_hint == 'big-announcements' and required_hits >= 1 and exclude_hits == 0:
        return True
    return False


def _is_for_fun_candidate(article: Article, text_blob: str) -> bool:
    required_hits = _keyword_hits(text_blob, FOR_FUN_REQUIRED_KEYWORDS)
    exclude_hits = _keyword_hits(text_blob, FOR_FUN_EXCLUDE_KEYWORDS)
    if required_hits >= 2 and exclude_hits == 0:
        return True
    if required_hits >= 1 and exclude_hits == 0 and article.section_hint == 'for-fun':
        return True
    if article.source_type == 'reddit' and required_hits >= 1 and exclude_hits == 0:
        return True
    return False


def _business_penalty(article: Article, text_blob: str) -> float:
    penalty = 0.0
    announcement_hits = _keyword_hits(text_blob, BUSINESS_ANNOUNCEMENT_KEYWORDS)
    practical_hits = _keyword_hits(text_blob, BUSINESS_PRACTICAL_KEYWORDS)
    penalty += announcement_hits * 2.0
    if practical_hits == 0:
        penalty += 2.2
    if article.domain in BIG_ANNOUNCEMENT_DOMAINS:
        penalty += 3.0
    return penalty


def _has_model_release_signal(text_blob: str) -> bool:
    if any(keyword in text_blob for keyword in HIGH_SIGNAL_MODEL_RELEASE_KEYWORDS):
        return True
    return bool(
        re.search(
            r'\b(gpt|claude|gemini|llama|qwen|mistral|deepseek|grok)[\- ]?[a-z0-9\.]*\b',
            text_blob,
        )
    )


def _is_high_signal_announcement(article: Article, text_blob: str) -> bool:
    domain_signal = (article.domain or '').lower() in BIG_ANNOUNCEMENT_DOMAINS
    if not domain_signal:
        return False
    model_signal = _has_model_release_signal(text_blob)
    if not model_signal:
        return False
    intent_hits = _keyword_hits(text_blob, BIG_ANNOUNCEMENT_INTENT_KEYWORDS)
    card_or_notes_signal = (
        ('system card' in text_blob)
        or ('model card' in text_blob)
        or ('release notes' in text_blob)
    )
    return intent_hits > 0 or card_or_notes_signal


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

    client = OpenAI(api_key=api_key, **openai_client_kwargs())
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
        log.info(
            'LLM curation running for section=%s with %s candidate(s).',
            section_slug,
            len(candidates),
        )
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
        high_signal_announcement = _is_high_signal_announcement(article, text_blob)
        recency_score = _recency_score(article, feed_dt)
        article.recency_score = max(0.0, min(recency_score * 2.5, 10.0))
        article.source_quality_score = _source_quality_score(article)
        article.novelty_score = _novelty_score(article, text_blob)
        article.metrics['recency_score'] = article.recency_score
        article.metrics['source_quality_score'] = article.source_quality_score
        article.metrics['novelty_score'] = article.novelty_score
        article.metrics['high_signal_announcement'] = 1.0 if high_signal_announcement else 0.0
        base = (
            article.priority
            + recency_score
            + (article.source_quality_score * 0.22)
            + (article.novelty_score * 0.16)
        )
        for section in SECTIONS:
            section_score = base
            hits = _keyword_hits(text_blob, KEYWORDS.get(section.slug, []))
            section_score += hits * 1.5
            if article.section_hint == section.slug:
                if section.slug == 'business':
                    section_score += 2.2
                elif section.slug == 'big-announcements':
                    section_score += 2.2
                else:
                    section_score += 4.5
            if section.slug == 'big-announcements':
                prompt_hits = _keyword_hits(text_blob, PRACTICAL_PROMPT_REQUIRED_KEYWORDS)
                exclude_hits = _keyword_hits(text_blob, PRACTICAL_PROMPT_EXCLUDE_KEYWORDS)
                section_score += prompt_hits * 1.9
                section_score -= exclude_hits * 1.6
                section_score += min(1.2, article.metrics.get('comments', 0.0) / 80.0)
                if article.source_type in {'rss', 'reddit', 'x', 'linkedin'}:
                    section_score += 0.4
                if not _is_practical_prompt_candidate(article, text_blob):
                    section_score -= 6.0
            if section.slug == 'under-the-radar':
                if article.domain not in MAINSTREAM_DOMAINS:
                    section_score += 1.6
                else:
                    section_score -= 0.8
                section_score += _under_the_radar_boost(article, text_blob)
            if section.slug == 'for-fun':
                fun_hits = _keyword_hits(text_blob, FOR_FUN_REQUIRED_KEYWORDS)
                exclude_hits = _keyword_hits(text_blob, FOR_FUN_EXCLUDE_KEYWORDS)
                section_score += fun_hits * 1.7
                section_score -= exclude_hits * 1.8
                if _is_for_fun_candidate(article, text_blob):
                    section_score += 5.0
                else:
                    section_score -= 7.0
            if section.slug in {'engineering', 'product-development'}:
                section_score += min(2.0, article.metrics.get('points', 0.0) / 150.0)
            if section.slug == 'business':
                section_score += min(1.6, article.metrics.get('points', 0.0) / 260.0)
                section_score += _keyword_hits(text_blob, BUSINESS_PRACTICAL_KEYWORDS) * 1.2
                section_score -= _business_penalty(article, text_blob)
                if not _is_software_development_candidate(article, text_blob):
                    section_score -= 4.5
            if high_signal_announcement:
                if section.slug in {'engineering', 'product-development'}:
                    section_score += 5.0
                elif section.slug == 'business':
                    section_score += 2.4
                elif section.slug == 'for-fun':
                    section_score -= 3.0
            if _is_curator_watchlist_article(article):
                section_score += _curator_watchlist_score_boost(section.slug)
            scores[section.slug] = round(section_score, 3)
        article.scores = scores
        article.confidence_score = _confidence_score(article)
        article.metrics['confidence_score'] = article.confidence_score
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


def _ensure_high_signal_coverage(
    sections: dict[str, list[Article]],
    articles: list[Article],
    picked_ids: set[str],
    max_per_section: int,
) -> None:
    selected_items = [item for picks in sections.values() for item in picks]
    if any(float(item.metrics.get('high_signal_announcement', 0.0)) >= 1.0 for item in selected_items):
        return

    candidates = [
        article
        for article in articles
        if float(article.metrics.get('high_signal_announcement', 0.0)) >= 1.0
    ]
    if not candidates:
        return
    candidates = sorted(
        candidates,
        key=lambda item: max(
            item.scores.get('engineering', 0.0),
            item.scores.get('product-development', 0.0),
            item.scores.get('business', 0.0),
        ),
        reverse=True,
    )
    chosen = None
    for candidate in candidates:
        if candidate.id in picked_ids:
            return
        chosen = candidate
        break
    if chosen is None:
        return

    target_slug = 'engineering'
    target = sections.get(target_slug, [])
    if len(target) < max_per_section:
        target.append(chosen)
        picked_ids.add(chosen.id)
        log.info('Injected high-signal announcement into section=%s: %s', target_slug, chosen.title)
        return

    lowest = min(target, key=lambda item: item.scores.get(target_slug, 0.0))
    if chosen.scores.get(target_slug, 0.0) <= lowest.scores.get(target_slug, 0.0):
        return
    target.remove(lowest)
    picked_ids.discard(lowest.id)
    target.append(chosen)
    picked_ids.add(chosen.id)
    log.info(
        'Replaced low-score item with high-signal announcement in section=%s: %s',
        target_slug,
        chosen.title,
    )


def curate_sections(
    articles: list[Article],
    min_per_section: int = SECTION_TARGET_MIN,
    max_per_section: int = SECTION_TARGET_MAX,
    feed_dt: datetime | None = None,
    enable_llm_curation: bool = True,
) -> dict[str, list[Article]]:
    if feed_dt is None:
        feed_dt = datetime.now(timezone.utc)
    recent_articles: list[Article] = []
    high_signal_grace_count = 0
    for article in articles:
        if _is_within_recency_window(article, feed_dt, RECENCY_REQUIRED_HOURS):
            recent_articles.append(article)
            continue
        text_blob = article.canonical_text().lower()
        if (
            _is_high_signal_announcement(article, text_blob)
            and _is_within_recency_window(article, feed_dt, HIGH_SIGNAL_RECENCY_HOURS)
        ):
            article.metrics['recency_grace_applied'] = 1.0
            recent_articles.append(article)
            high_signal_grace_count += 1
    if high_signal_grace_count > 0:
        log.info(
            'Included %s high-signal announcement item(s) with %s-hour recency grace.',
            high_signal_grace_count,
            HIGH_SIGNAL_RECENCY_HOURS,
        )
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
        candidate_pool = [
            article for article in candidate_pool if article.assigned_section == section.slug
        ]
        if section.slug == 'big-announcements':
            narrowed = [
                article
                for article in candidate_pool
                if _is_practical_prompt_candidate(article, article.canonical_text().lower())
            ]
            candidate_pool = narrowed
        if section.slug == 'business':
            workflow_focused = [
                article
                for article in candidate_pool
                if _is_software_development_candidate(article, article.canonical_text().lower())
            ]
            if workflow_focused:
                candidate_pool = workflow_focused
        if section.slug == 'for-fun':
            playful_items = [
                article
                for article in candidate_pool
                if _is_for_fun_candidate(article, article.canonical_text().lower())
            ]
            candidate_pool = playful_items
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
        fallback_pool = [
            article for article in articles if article.assigned_section == section.slug
        ]
        if not fallback_pool:
            fallback_pool = articles
        if curator_enabled and curator_total_selected >= curator_total_cap:
            non_curator_fallback = [item for item in fallback_pool if not _is_curator_watchlist_article(item)]
            if non_curator_fallback:
                fallback_pool = non_curator_fallback
        if section.slug == 'big-announcements':
            narrowed = [
                article
                for article in articles
                if _is_practical_prompt_candidate(article, article.canonical_text().lower())
            ]
            fallback_pool = narrowed
        if section.slug == 'business':
            workflow_focused = [
                article
                for article in fallback_pool
                if _is_software_development_candidate(article, article.canonical_text().lower())
            ]
            if workflow_focused:
                fallback_pool = workflow_focused
        if section.slug == 'for-fun':
            playful_items = [
                article
                for article in fallback_pool
                if _is_for_fun_candidate(article, article.canonical_text().lower())
            ]
            fallback_pool = playful_items
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

    _ensure_high_signal_coverage(
        sections=sections,
        articles=articles,
        picked_ids=picked_ids,
        max_per_section=max_per_section,
    )

    return sections
