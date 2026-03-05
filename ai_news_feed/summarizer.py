##########################################################################################
#
# Script name: summarizer.py
#
# Description: Summary generation and optional OpenAI enrichment.
#
##########################################################################################

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .llm_utils import LlmUsageTotals, call_chat_completion_json, openai_client_kwargs
from .models import Article
from .utils import safe_sentence, strip_html

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************

log = logging.getLogger(__name__)

SECTION_LENSES = {
    'big-announcements': 'practical prompt patterns for software development execution',
    'engineering': 'practical engineering workflow impact',
    'product-development': 'product workflow and shipping velocity impact',
    'business': 'software development workflow, agents, and implementation impact',
    'under-the-radar': 'why this overlooked signal matters early',
    'for-fun': 'why this is creative and interesting',
}

DEFAULT_SYSTEM_PROMPT = 'You write concise AI-news briefings. Return strict JSON only, no markdown.'

ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(os.getenv('SECTION_PROMPTS_DIR') or (ROOT_DIR / 'prompts' / 'sections'))
SYSTEM_PROMPT_PATH = Path(os.getenv('SYSTEM_PROMPT_FILE') or (ROOT_DIR / 'prompts' / 'system.md'))
WORKFLOW_PROMPT_PATH = Path(os.getenv('WORKFLOW_PROMPT_FILE') or (ROOT_DIR / 'prompts' / 'workflow.md'))


# ****************************************************************************************
# Functions
# ****************************************************************************************


def _fallback_article_copy(article: Article, section_slug: str) -> tuple[str, str]:
    source_text = strip_html(article.summary) or article.title
    summary_text = safe_sentence(source_text, 220)
    lens = SECTION_LENSES.get(section_slug, 'why this matters')
    why_text = safe_sentence(
        f'Direct: This matters for {lens}, based on this update from {article.source_name}.',
        180,
    )
    return summary_text, why_text


def _fallback_action_fields(article: Article, section_slug: str) -> tuple[str, str, str]:
    if section_slug == 'engineering':
        who = 'Staff+ engineers and platform teams'
        action = 'Pilot this workflow in one active repo this week.'
        effort = '1-2 days'
    elif section_slug == 'product-development':
        who = 'PMs, product designers, and product ops'
        action = 'Run one AI-assisted experiment in your weekly planning cycle.'
        effort = 'half-day'
    elif section_slug == 'business':
        who = 'Software developers building AI-enabled workflows'
        action = 'Implement one reproducible agent/runbook pattern in your team workflow.'
        effort = '1-2 days'
    elif section_slug == 'big-announcements':
        who = 'Software engineers, tech leads, and developer productivity teams'
        action = 'Copy one prompt pattern and run it on an active task this week.'
        effort = '1-2h'
    elif section_slug == 'under-the-radar':
        who = 'Builders looking for early, high-signal implementation ideas'
        action = 'Validate this pattern quickly with a constrained proof-of-concept.'
        effort = '1-2h'
    else:
        who = 'Curious builders and AI practitioners'
        action = 'Try this approach as a small side experiment.'
        effort = '<30m'
    return who, safe_sentence(action, 180), effort


def _fallback_evidence_quote(article: Article) -> str:
    text = safe_sentence(strip_html(article.summary) or article.title, 180)
    words = text.split()
    if not words:
        return ''
    return ' '.join(words[:18]).strip()


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        return DEFAULT_SYSTEM_PROMPT
    try:
        content = SYSTEM_PROMPT_PATH.read_text(encoding='utf-8').strip()
    except OSError as exc:
        log.warning('Failed reading system prompt file %s: %s', SYSTEM_PROMPT_PATH, exc)
        return DEFAULT_SYSTEM_PROMPT
    return content or DEFAULT_SYSTEM_PROMPT


@lru_cache(maxsize=16)
def _load_section_prompt(section_slug: str) -> str:
    lens = SECTION_LENSES.get(section_slug, 'why it matters')
    prompt_filename = 'software.md' if section_slug == 'business' else f'{section_slug}.md'
    prompt_path = PROMPTS_DIR / prompt_filename
    if not prompt_path.exists():
        log.warning('Missing section prompt file for %s at %s', section_slug, prompt_path)
        return f'Focus lens: {lens}.'
    try:
        content = prompt_path.read_text(encoding='utf-8').strip()
    except OSError as exc:
        log.warning('Failed reading section prompt file %s: %s', prompt_path, exc)
        return f'Focus lens: {lens}.'
    if not content:
        return f'Focus lens: {lens}.'
    return content


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


def _build_payload(articles: list[Article]) -> list[dict[str, Any]]:
    return [
        {
            'id': article.id,
            'title': article.title,
            'source': article.source_name,
            'url': article.url,
            'summary_input': safe_sentence(strip_html(article.summary), 360),
        }
        for article in articles
    ]


def _try_openai_enrichment(
    section_slug: str,
    articles: list[Article],
    usage_totals: LlmUsageTotals,
) -> dict[str, dict[str, str]] | None:
    api_key = os.getenv('OPENAI_API_KEY')
    preferred_model = os.getenv('OPENAI_MODEL') or 'gpt-5-mini'
    if not api_key or OpenAI is None or not articles:
        return None

    client = OpenAI(api_key=api_key, **openai_client_kwargs())
    payload = _build_payload(articles)
    system_prompt = _load_system_prompt()
    workflow_prompt = _load_workflow_prompt()
    section_prompt = _load_section_prompt(section_slug)
    lens = SECTION_LENSES.get(section_slug, 'why it matters')
    user_prompt = (
        f'Section: {section_slug}\n'
        'Global workflow guidance markdown:\n'
        f'{workflow_prompt}\n\n'
        'Section guidance markdown:\n'
        f'{section_prompt}\n\n'
        'For each item, create:\n'
        '1) "summary" = <= 45 words, factual, and only from provided input.\n'
        '2) "why_it_matters" = <= 28 words, actionable, and must start with either "Direct:" or "Inference:".\n'
        '3) "who_should_care" = <= 16 words naming the audience.\n'
        '4) "suggested_action" = <= 20 words with a concrete next step.\n'
        '5) "time_to_implement" = one of: "<30m", "1-2h", "half-day", "1-2 days", "multi-day".\n'
        '6) "evidence_quote" = <= 18 words copied verbatim from summary_input; empty string if unavailable.\n'
        '7) "inference_label" = "direct" or "inference".\n'
        'Focus lens: '
        f'{lens}.\n'
        'No hallucinations. Never make up facts not present in the input rows.\n'
        'Input JSON:\n'
        f'{json.dumps(payload, ensure_ascii=True)}\n\n'
        'Return JSON object with exact shape:\n'
        '{"items":[{"id":"...","summary":"...","why_it_matters":"...","who_should_care":"...",'
        '"suggested_action":"...","time_to_implement":"...","evidence_quote":"...","inference_label":"direct"}]}'
    )
    try:
        response, selected_model, selection_info, temperature_fallback_retry = call_chat_completion_json(
            client=client,
            logger=log,
            preferred_model=preferred_model,
            operation=f'summarization:{section_slug}',
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        usage_totals.call_count += 1
        usage_totals.add_estimate(selection_info)
        usage_totals.add_usage(response, selected_model)
        if temperature_fallback_retry:
            usage_totals.temperature_fallback_retries += 1
        content = response.choices[0].message.content
        parsed = json.loads(content)
        rows = parsed.get('items', [])
        output: dict[str, dict[str, str]] = {}
        for row in rows:
            row_id = row.get('id')
            if not row_id:
                continue
            output[row_id] = {
                'summary': safe_sentence(str(row.get('summary', '')), 260),
                'why_it_matters': safe_sentence(str(row.get('why_it_matters', '')), 180),
                'who_should_care': safe_sentence(str(row.get('who_should_care', '')), 120),
                'suggested_action': safe_sentence(str(row.get('suggested_action', '')), 160),
                'time_to_implement': safe_sentence(str(row.get('time_to_implement', '')), 40),
                'evidence_quote': safe_sentence(str(row.get('evidence_quote', '')), 140),
                'inference_label': str(row.get('inference_label', 'direct')).strip().lower(),
            }
        return output
    except Exception as exc:  # noqa: BLE001
        log.warning('OpenAI enrichment failed for section=%s: %s', section_slug, exc)
        return None


def enrich_summaries(sections: dict[str, list[Article]]) -> None:
    usage_totals = LlmUsageTotals()
    for section_slug, articles in sections.items():
        log.info(
            'LLM summarization running for section=%s with %s article(s).',
            section_slug,
            len(articles),
        )
        llm_data = _try_openai_enrichment(section_slug, articles, usage_totals) or {}
        for article in articles:
            if article.id in llm_data:
                article.summary_text = llm_data[article.id]['summary']
                why_text = llm_data[article.id]['why_it_matters']
                inference_label = llm_data[article.id].get('inference_label') or 'direct'
                if inference_label not in {'direct', 'inference'}:
                    inference_label = 'direct'
                if not why_text.lower().startswith('direct:') and not why_text.lower().startswith('inference:'):
                    prefix = 'Inference:' if inference_label == 'inference' else 'Direct:'
                    why_text = f'{prefix} {why_text}'.strip()
                article.why_it_matters = why_text
                article.who_should_care = llm_data[article.id].get('who_should_care', '')
                article.suggested_action = llm_data[article.id].get('suggested_action', '')
                article.time_to_implement = llm_data[article.id].get('time_to_implement', '')
                article.evidence_quote = llm_data[article.id].get('evidence_quote', '')
                article.inference_label = inference_label
            else:
                fallback_summary, fallback_why = _fallback_article_copy(article, section_slug)
                article.summary_text = fallback_summary
                article.why_it_matters = fallback_why
                fallback_who, fallback_action, fallback_time = _fallback_action_fields(article, section_slug)
                article.who_should_care = fallback_who
                article.suggested_action = fallback_action
                article.time_to_implement = fallback_time
                article.evidence_quote = _fallback_evidence_quote(article)
                article.inference_label = 'direct'
            if not article.who_should_care:
                fallback_who, _, _ = _fallback_action_fields(article, section_slug)
                article.who_should_care = fallback_who
            if not article.suggested_action:
                _, fallback_action, _ = _fallback_action_fields(article, section_slug)
                article.suggested_action = fallback_action
            if not article.time_to_implement:
                _, _, fallback_time = _fallback_action_fields(article, section_slug)
                article.time_to_implement = fallback_time
            if not article.evidence_quote:
                article.evidence_quote = _fallback_evidence_quote(article)
    if usage_totals.call_count > 0:
        usage_totals.log_summary(log, label='LLM totals')
