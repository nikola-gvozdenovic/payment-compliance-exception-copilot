"""Loads the committed synthetic payment fixtures back into validated Payment objects.

This is the integration point later tickets (Triage Agent, Compliance Agent,
eval harness) import from, rather than re-parsing JSON themselves.
"""

from pathlib import Path

from data.models import FlagReason, Payment

SYNTHETIC_PAYMENTS_DIR = Path(__file__).parent / "synthetic_payments"


def load_all() -> list[Payment]:
    """Load every committed synthetic payment fixture, sorted by payment_id."""
    payments = [
        Payment.model_validate_json(path.read_text())
        for path in SYNTHETIC_PAYMENTS_DIR.glob("*.json")
    ]
    return sorted(payments, key=lambda p: p.payment_id)


def load_by_flag_reason(reason: FlagReason) -> Payment:
    """Load the single fixture matching the given flag reason.

    Fixtures are 1:1 with FlagReason values by construction (see
    generate_synthetic_payments.py) -- zero or more than one match indicates
    the dataset has drifted from that invariant.
    """
    matches = [p for p in load_all() if p.flag_reason == reason]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one payment with flag_reason={reason!r}, found {len(matches)}"
        )
    return matches[0]
