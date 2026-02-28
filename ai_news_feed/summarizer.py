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
    'big-announcements': 'what changed and who it impacts',
    'engineering': 'practical engineering workflow impact',
    'product-development': 'product workflow and shipping velocity impact',
    'business': 'business model and monetization impact',
    'under-the-radar': 'why this overlooked signal matters early',
    'for-fun': 'why this is creative and interesting',
}

DEFAULT_SYSTEM_PROMPT = 'You write concise AI-news briefings. Return strict JSON only, no markdown.'

ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(os.getenv('SECTION_PROMPTS_DIR') or (ROOT_DIR / 'prompts' / 'sections'))
SYSTEM_PROMPT_PATH = Path(os.getenv('SYSTEM_PROMPT_FILE') or (ROOT_DIR / 'prompts' / 'system.md'))


# ****************************************************************************************
# Functions
# ****************************************************************************************


def _fallback_article_copy(article: Article, section_slug: str) -> tuple[str, str]:
    source_text = strip_html(article.summary) or article.title
    summary_text = safe_sentence(source_text, 220)
    lens = SECTION_LENSES.get(section_slug, 'why this matters')
    why_text = safe_sentence(
        f'This matters for {lens}, based on this update from {article.source_name}.',
        160,
    )
    return summary_text, why_text


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
    prompt_path = PROMPTS_DIR / f'{section_slug}.md'
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


def _try_openai_enrichment(section_slug: str, articles: list[Article]) -> dict[str, dict[str, str]] | None:
    api_key = os.getenv('OPENAI_API_KEY')
    model = os.getenv('OPENAI_MODEL') or 'gpt-5-mini'
    if not api_key or OpenAI is None or not articles:
        return None

    client = OpenAI(api_key=api_key)
    payload = _build_payload(articles)
    system_prompt = _load_system_prompt()
    section_prompt = _load_section_prompt(section_slug)
    lens = SECTION_LENSES.get(section_slug, 'why it matters')
    user_prompt = (
        f'Section: {section_slug}\n'
        'Section guidance markdown:\n'
        f'{section_prompt}\n\n'
        'For each item, create:\n'
        '1) "summary" = <= 45 words, factual.\n'
        '2) "why_it_matters" = <= 28 words, actionable.\n'
        'Focus lens: '
        f'{lens}.\n'
        'Input JSON:\n'
        f'{json.dumps(payload, ensure_ascii=True)}\n\n'
        'Return JSON object with exact shape:\n'
        '{"items":[{"id":"...","summary":"...","why_it_matters":"..."}]}'
    )
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
        )
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
            }
        return output
    except Exception as exc:  # noqa: BLE001
        log.warning('OpenAI enrichment failed for section=%s: %s', section_slug, exc)
        return None


def enrich_summaries(sections: dict[str, list[Article]]) -> None:
    for section_slug, articles in sections.items():
        llm_data = _try_openai_enrichment(section_slug, articles) or {}
        for article in articles:
            if article.id in llm_data:
                article.summary_text = llm_data[article.id]['summary']
                article.why_it_matters = llm_data[article.id]['why_it_matters']
            else:
                fallback_summary, fallback_why = _fallback_article_copy(article, section_slug)
                article.summary_text = fallback_summary
                article.why_it_matters = fallback_why
