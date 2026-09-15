from data.decision_log import get_decisions_for_payment, log_decision
from data.loader import load_all


def _log(db_path, **overrides):
    defaults = {
        "payment_id": "PMT-0001",
        "agent_name": "triage_agent",
        "input": {"x": 1},
        "context": {"docs": ["POL-0001"]},
        "decision": "flagged",
        "reasoning": "test reasoning",
    }
    defaults.update(overrides)
    return log_decision(db_path=db_path, **defaults)


def test_log_decision_returns_entry_with_id_and_timestamp(tmp_path):
    entry = _log(tmp_path / "test.db")
    assert isinstance(entry.id, int)
    assert entry.id > 0
    assert entry.timestamp is not None


def test_get_decisions_for_payment_returns_empty_list_for_unknown_payment(tmp_path):
    db_path = tmp_path / "test.db"
    _log(db_path, payment_id="PMT-0001")
    assert get_decisions_for_payment("PMT-9999", db_path=db_path) == []


def test_entries_returned_in_insertion_order(tmp_path):
    db_path = tmp_path / "test.db"
    _log(db_path, payment_id="PMT-0001", reasoning="first")
    _log(db_path, payment_id="PMT-0001", reasoning="second")
    _log(db_path, payment_id="PMT-0001", reasoning="third")

    entries = get_decisions_for_payment("PMT-0001", db_path=db_path)

    assert [e.reasoning for e in entries] == ["first", "second", "third"]


def test_get_decisions_for_payment_filters_by_payment_id(tmp_path):
    db_path = tmp_path / "test.db"
    _log(db_path, payment_id="PMT-0001", reasoning="for pmt 1")
    _log(db_path, payment_id="PMT-0002", reasoning="for pmt 2")

    pmt1_entries = get_decisions_for_payment("PMT-0001", db_path=db_path)
    pmt2_entries = get_decisions_for_payment("PMT-0002", db_path=db_path)

    assert [e.reasoning for e in pmt1_entries] == ["for pmt 1"]
    assert [e.reasoning for e in pmt2_entries] == ["for pmt 2"]


def test_pydantic_model_payload_round_trips(tmp_path):
    db_path = tmp_path / "test.db"
    payment = load_all()[0]

    entry = _log(db_path, payment_id=payment.payment_id, input=payment)
    retrieved = get_decisions_for_payment(payment.payment_id, db_path=db_path)[0]

    assert entry.input == payment.model_dump(mode="json")
    assert retrieved.input == payment.model_dump(mode="json")


def test_reasoning_accepts_empty_string(tmp_path):
    db_path = tmp_path / "test.db"
    entry = _log(db_path, reasoning="")
    assert entry.reasoning == ""
    assert get_decisions_for_payment(entry.payment_id, db_path=db_path)[0].reasoning == ""
