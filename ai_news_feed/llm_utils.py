##########################################################################################
#
# Script name: llm_utils.py
#
# Description: Shared LLM helpers for model selection, token/cost estimation, and calls.
#
##########################################################################################

import json
import logging
import os
from dataclasses import dataclass
from typing import Any


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************

PRICE_TABLE_DEFAULT = {
    'gpt-5-nano': {'in_per_m': 0.05, 'out_per_m': 0.40},
    'gpt-5-mini': {'in_per_m': 0.25, 'out_per_m': 2.00},
    'gpt-5': {'in_per_m': 1.25, 'out_per_m': 10.00},
    'gpt-5-chat-latest': {'in_per_m': 1.25, 'out_per_m': 10.00},
    'gpt-5.2': {'in_per_m': 1.75, 'out_per_m': 14.00},
    'gpt-5.2-chat-latest': {'in_per_m': 1.75, 'out_per_m': 14.00},
    'gpt-5.1': {'in_per_m': 1.25, 'out_per_m': 10.00},
    'gpt-5.1-chat-latest': {'in_per_m': 1.25, 'out_per_m': 10.00},
    'gpt-4o-mini': {'in_per_m': 0.15, 'out_per_m': 0.60},
    'gpt-4o': {'in_per_m': 2.50, 'out_per_m': 10.00},
}

SAMPLE_OUTPUTS = {
    'summarization': {
        'items': [
            {
                'id': 'example-id',
                'summary': 'Short factual summary.',
                'why_it_matters': 'Short actionable reason.',
            }
        ]
    },
    'curation': {
        'items': [
            {
                'id': 'example-id',
                'score': 7.5,
                'exclude': False,
                'reason': 'Section fit and practical relevance.',
            }
        ]
    },
}


# ****************************************************************************************
# Functions
# ****************************************************************************************


@dataclass
class LlmUsageTotals:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_input_tokens: int = 0
    estimated_input_cost: float = 0.0
    total_cost: float = 0.0
    temperature_fallback_retries: int = 0
    call_count: int = 0

    def add_usage(self, response: Any, model: str) -> None:
        usage = getattr(response, 'usage', None)
        if usage is None:
            return
        prompt_tokens = int(getattr(usage, 'prompt_tokens', 0) or 0)
        completion_tokens = int(getattr(usage, 'completion_tokens', 0) or 0)
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_cost += usage_cost_usd(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def add_estimate(self, selection_info: dict[str, Any]) -> None:
        if not selection_info:
            return
        self.estimated_input_tokens += int(selection_info.get('input_tokens', 0) or 0)
        self.estimated_input_cost += float(selection_info.get('input_cost', 0.0) or 0.0)

    def estimated_cost(self) -> float:
        if self.total_cost > 0:
            return self.total_cost
        prompt_rate = float(os.getenv('OPENAI_PROMPT_COST_PER_1M') or 0.05)
        completion_rate = float(os.getenv('OPENAI_COMPLETION_COST_PER_1M') or 0.40)
        prompt_cost = (self.prompt_tokens / 1_000_000) * prompt_rate
        completion_cost = (self.completion_tokens / 1_000_000) * completion_rate
        return prompt_cost + completion_cost

    def log_summary(self, logger: logging.Logger, label: str = 'LLM totals') -> None:
        logger.info('++++++++++++++++++++++++++++++++++++++++++++++')
        logger.info(
            '+  %s: prompt_tokens=%d, completion_tokens=%d',
            label,
            self.prompt_tokens,
            self.completion_tokens,
        )
        if self.estimated_input_tokens:
            logger.info('+  Estimated input tokens: %d', self.estimated_input_tokens)
            logger.info('+  Estimated input cost: $%.4f', self.estimated_input_cost)
        logger.info('+  Temperature fallback retries: %d', self.temperature_fallback_retries)
        logger.info('+  Estimated LLM cost: $%.4f', self.estimated_cost())
        logger.info('++++++++++++++++++++++++++++++++++++++++++++++')


def _is_truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {'1', 'true', 'yes', 'y', 'on'}:
        return True
    if lowered in {'0', 'false', 'no', 'n', 'off'}:
        return False
    return default


def is_cost_minimization_enabled() -> bool:
    return _is_truthy(os.getenv('OPENAI_MINIMIZE_COST'), default=True)


def estimate_tokens(text: str, model: str) -> int:
    try:
        import tiktoken  # type: ignore
    except Exception:
        tiktoken = None
    if not tiktoken:
        return max(1, int(len(text or '') / 4))
    try:
        encoder = tiktoken.encoding_for_model(model)
    except Exception:
        encoder = tiktoken.get_encoding('cl100k_base')
    return len(encoder.encode(text or ''))


def _candidate_models(preferred_model: str) -> list[str]:
    configured = (os.getenv('OPENAI_MODEL_CANDIDATES') or '').strip()
    if configured:
        values = [item.strip() for item in configured.split(',') if item.strip()]
    else:
        values = list(PRICE_TABLE_DEFAULT.keys())
    if preferred_model and preferred_model not in values:
        values.append(preferred_model)
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _sample_output_text(operation: str) -> str:
    lowered = operation.strip().lower()
    if lowered.startswith('curation'):
        return json.dumps(SAMPLE_OUTPUTS['curation'], ensure_ascii=False)
    return json.dumps(SAMPLE_OUTPUTS['summarization'], ensure_ascii=False)


def _lookup_price(model: str) -> dict[str, float]:
    exact = PRICE_TABLE_DEFAULT.get(model)
    if exact:
        return exact
    for candidate, pricing in PRICE_TABLE_DEFAULT.items():
        if model.startswith(f'{candidate}-'):
            return pricing
    return {}


def usage_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = _lookup_price(model)
    if pricing:
        prompt_rate = float(pricing.get('in_per_m') or 0.0)
        completion_rate = float(pricing.get('out_per_m') or 0.0)
    else:
        prompt_rate = float(os.getenv('OPENAI_PROMPT_COST_PER_1M') or 0.05)
        completion_rate = float(os.getenv('OPENAI_COMPLETION_COST_PER_1M') or 0.40)
    prompt_cost = (prompt_tokens / 1_000_000) * prompt_rate
    completion_cost = (completion_tokens / 1_000_000) * completion_rate
    return prompt_cost + completion_cost


def select_min_cost_model(
    system_prompt: str,
    user_prompt: str,
    preferred_model: str,
    operation: str,
) -> tuple[str, dict[str, Any]]:
    sample_output = _sample_output_text(operation)
    candidates: list[dict[str, Any]] = []
    for model in _candidate_models(preferred_model):
        pricing = _lookup_price(model)
        if not pricing:
            continue
        in_tokens = estimate_tokens(system_prompt, model) + estimate_tokens(user_prompt, model)
        out_tokens = estimate_tokens(sample_output, model)
        in_rate = float(pricing.get('in_per_m') or 0.0)
        out_rate = float(pricing.get('out_per_m') or 0.0)
        in_cost = (in_tokens / 1_000_000) * in_rate if in_rate else 0.0
        out_cost = (out_tokens / 1_000_000) * out_rate if out_rate else 0.0
        candidates.append(
            {
                'model': model,
                'input_tokens': in_tokens,
                'output_tokens': out_tokens,
                'input_cost': in_cost,
                'output_cost': out_cost,
                'total_cost': in_cost + out_cost,
                'operation': operation,
            }
        )
    if not candidates:
        return preferred_model, {}
    candidates.sort(
        key=lambda item: (item['total_cost'], 0 if item['model'] == preferred_model else 1, item['model'])
    )
    chosen = candidates[0]
    return chosen['model'], chosen


def _configured_temperature() -> float | None:
    raw_temperature = (os.getenv('OPENAI_TEMPERATURE') or '').strip()
    if not raw_temperature:
        return None
    try:
        return float(raw_temperature)
    except ValueError:
        return None


def _is_unsupported_temperature_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return 'temperature' in lowered and ('unsupported' in lowered or 'not supported' in lowered)


def call_chat_completion_json(
    client,
    logger: logging.Logger,
    preferred_model: str,
    operation: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[Any, str, dict[str, Any], bool]:
    selected_model = preferred_model
    selection_info: dict[str, Any] = {}
    if is_cost_minimization_enabled():
        selected_model, selection_info = select_min_cost_model(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            preferred_model=preferred_model,
            operation=operation,
        )
        if selection_info:
            logger.info(
                '+  Model selection: operation=%s, selected=%s, preferred=%s, '
                'input_tokens=%d, output_tokens=%d, est_total_cost=$%.6f',
                operation,
                selected_model,
                preferred_model,
                int(selection_info.get('input_tokens') or 0),
                int(selection_info.get('output_tokens') or 0),
                float(selection_info.get('total_cost') or 0.0),
            )

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]
    kwargs: dict[str, Any] = {
        'model': selected_model,
        'response_format': {'type': 'json_object'},
        'messages': messages,
    }
    temperature = _configured_temperature()
    if temperature is not None:
        kwargs['temperature'] = temperature

    temperature_fallback_retry = False
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if 'temperature' in kwargs and _is_unsupported_temperature_error(exc):
            temperature_fallback_retry = True
            kwargs.pop('temperature', None)
            response = client.chat.completions.create(**kwargs)
        else:
            raise
    return response, selected_model, selection_info, temperature_fallback_retry
