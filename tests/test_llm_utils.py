##########################################################################################
#
# Script name: test_llm_utils.py
#
# Description: Tests model auto-selection and resilient LLM call helpers.
#
##########################################################################################

import logging

from ai_news_feed.llm_utils import call_chat_completion_json, is_cost_minimization_enabled, select_min_cost_model


class _FakeUsage:
    prompt_tokens = 120
    completion_tokens = 45


class _FakeChoiceMessage:
    content = '{"items":[]}'


class _FakeChoice:
    message = _FakeChoiceMessage()


class _FakeResponse:
    usage = _FakeUsage()
    choices = [_FakeChoice()]


class _FakeCompletions:
    def __init__(self, fail_first_temperature: bool = False):
        self.fail_first_temperature = fail_first_temperature
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_first_temperature and len(self.calls) == 1:
            raise RuntimeError('temperature unsupported for this model')
        return _FakeResponse()


class _FakeChat:
    def __init__(self, fail_first_temperature: bool = False):
        self.completions = _FakeCompletions(fail_first_temperature=fail_first_temperature)


class _FakeClient:
    def __init__(self, fail_first_temperature: bool = False):
        self.chat = _FakeChat(fail_first_temperature=fail_first_temperature)


def test_is_cost_minimization_enabled_defaults_true(monkeypatch) -> None:
    monkeypatch.delenv('OPENAI_MINIMIZE_COST', raising=False)
    assert is_cost_minimization_enabled() is True


def test_select_min_cost_model_prefers_lower_estimated_cost(monkeypatch) -> None:
    monkeypatch.setenv('OPENAI_MODEL_CANDIDATES', 'gpt-5,gpt-5-mini,gpt-5-nano')
    model, info = select_min_cost_model(
        system_prompt='System prompt',
        user_prompt='User payload for scoring',
        preferred_model='gpt-5',
        operation='summarization:engineering',
    )
    assert model == 'gpt-5-nano'
    assert float(info.get('total_cost') or 0.0) >= 0.0
    assert int(info.get('input_tokens') or 0) > 0


def test_call_chat_completion_json_retries_without_temperature(monkeypatch) -> None:
    monkeypatch.setenv('OPENAI_MINIMIZE_COST', '1')
    monkeypatch.setenv('OPENAI_TEMPERATURE', '1')
    client = _FakeClient(fail_first_temperature=True)
    logger = logging.getLogger('test_call_chat_completion_json_retries_without_temperature')
    response, selected_model, selection_info, temperature_retry = call_chat_completion_json(
        client=client,
        logger=logger,
        preferred_model='gpt-5-mini',
        operation='curation:engineering',
        system_prompt='System',
        user_prompt='User',
    )
    assert response is not None
    assert selected_model
    assert isinstance(selection_info, dict)
    assert temperature_retry is True
    assert len(client.chat.completions.calls) == 2
