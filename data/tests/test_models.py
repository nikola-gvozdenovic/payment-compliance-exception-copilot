from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from data.models import FlagReason, Payment, PaymentStatus


def _make_payment(**overrides):
    defaults = {
        "payment_id": "PMT-0001",
        "source_currency": "EUR",
        "destination_currency": "GBP",
        "amount": Decimal("100.00"),
        "timestamp": datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
        "iso20022_xml": "<Document/>",
        "status": PaymentStatus.FLAGGED,
    }
    defaults.update(overrides)
    return Payment(**defaults)


def test_valid_payment_construction():
    payment = _make_payment()
    assert payment.payment_id == "PMT-0001"
    assert payment.status == PaymentStatus.FLAGGED


def test_corridor_auto_derivation_when_omitted():
    payment = _make_payment(source_currency="EUR", destination_currency="GBP")
    assert payment.corridor == "EUR-GBP"


def test_corridor_left_untouched_when_explicitly_passed():
    payment = _make_payment(
        source_currency="EUR", destination_currency="GBP", corridor="CUSTOM-CORRIDOR"
    )
    assert payment.corridor == "CUSTOM-CORRIDOR"


@pytest.mark.parametrize("bad_currency", ["eur", "EURO", "E1R", ""])
def test_invalid_currency_code_raises(bad_currency):
    with pytest.raises(ValidationError):
        _make_payment(source_currency=bad_currency)


@pytest.mark.parametrize("bad_amount", [Decimal(0), Decimal("-1.00")])
def test_non_positive_amount_raises(bad_amount):
    with pytest.raises(ValidationError):
        _make_payment(amount=bad_amount)


def test_flag_reason_values_match_triage_taxonomy():
    assert [reason.value for reason in FlagReason] == [
        "missing_malformed_field",
        "compliance_hold",
        "corridor_currency_issue",
        "timeout",
        "duplicate",
    ]
