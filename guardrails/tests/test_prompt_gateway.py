import pytest

from data.decision_log import get_decisions_for_payment
from data.loader import load_by_flag_reason
from data.models import FlagReason
from guardrails import PIILeakError, PromptGateway, mask_payment
from llm.fakes import SpyLLM

REAL_NAME = "Zed Trading Consolidated"


def _setup(tmp_path, response="ok"):
    payment = load_by_flag_reason(FlagReason.COMPLIANCE_HOLD)
    masked, vault = mask_payment(payment)
    spy = SpyLLM(response=response)
    gateway = PromptGateway(client=spy, vault=vault, db_path=tmp_path / "test.db")
    return payment, masked, spy, gateway


def test_clean_prompt_reaches_model_and_response_is_returned(tmp_path):
    _, masked, spy, gateway = _setup(tmp_path, response="classified")
    prompt = f"Classify:\n{masked.model_dump_json()}"

    assert gateway.send(prompt) == "classified"
    assert spy.prompts == [prompt]


def test_prompt_with_raw_value_is_blocked_before_model_is_called(tmp_path):
    _, _, spy, gateway = _setup(tmp_path)

    with pytest.raises(PIILeakError) as error:
        gateway.send(f"Is {REAL_NAME} sanctioned?")

    assert error.value.direction == "prompt"
    assert error.value.labels == ["[CREDITOR_NAME]"]
    assert spy.prompts == []


def test_response_with_raw_value_is_blocked(tmp_path):
    _, _, _, gateway = _setup(tmp_path, response=f"The payee is {REAL_NAME}")

    with pytest.raises(PIILeakError) as error:
        gateway.send("Who is [CREDITOR_NAME]?")

    assert error.value.direction == "response"


def test_non_string_prompt_is_rejected(tmp_path):
    payment, _, spy, gateway = _setup(tmp_path)

    with pytest.raises(TypeError):
        gateway.send(payment)

    assert spy.prompts == []


def test_leak_is_logged_with_labels_only(tmp_path):
    payment, _, _, gateway = _setup(tmp_path)

    with pytest.raises(PIILeakError) as error:
        gateway.send(f"Is {REAL_NAME} sanctioned?")

    entries = get_decisions_for_payment(payment.payment_id, db_path=tmp_path / "test.db")
    assert len(entries) == 1
    assert entries[0].agent_name == "pii_guardrail"
    assert entries[0].decision == "blocked"
    assert entries[0].context == {"labels": ["[CREDITOR_NAME]"]}
    assert REAL_NAME.lower() not in entries[0].model_dump_json().lower()
    assert REAL_NAME.lower() not in str(error.value).lower()
