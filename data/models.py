"""Core data model for the Payment Compliance & Exception Copilot.

`Payment` is the single representation of a flagged/stuck cross-border payment
used across the repo. Every agent (Triage, Compliance, Audit) and the decision
log consume this model rather than raw dicts or ad-hoc XML parsing.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class PaymentStatus(str, Enum):
    """Lifecycle status of a payment.

    Only FLAGGED and STUCK are produced by this ticket's synthetic generator.
    CLEARED, BLOCKED, and ESCALATED are reserved for the Compliance Agent
    (TICKET-6) to set once it exists.
    """

    FLAGGED = "flagged"
    STUCK = "stuck"
    CLEARED = "cleared"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


class FlagReason(str, Enum):
    """Triage cause taxonomy.

    These five values must stay in sync with the Triage Agent's classification
    taxonomy (PRD Section 7.1) and the TICKET-9 hand-labeled eval set. Changing
    a value here is a cross-cutting change, not a local one.
    """

    MISSING_MALFORMED_FIELD = "missing_malformed_field"
    COMPLIANCE_HOLD = "compliance_hold"
    CORRIDOR_CURRENCY_ISSUE = "corridor_currency_issue"
    TIMEOUT = "timeout"
    DUPLICATE = "duplicate"


class ProcessingLogEntry(BaseModel):
    """A single entry in a payment's processing log."""

    timestamp: datetime
    stage: str
    detail: str


class Payment(BaseModel):
    """A flagged/stuck cross-border payment."""

    payment_id: str = Field(pattern=r"^PMT-\d{4}$")
    source_currency: str = Field(pattern=r"^[A-Z]{3}$")
    destination_currency: str = Field(pattern=r"^[A-Z]{3}$")
    corridor: str | None = None
    amount: Decimal = Field(gt=0)
    timestamp: datetime
    iso20022_xml: str
    status: PaymentStatus
    flag_reason: FlagReason | None = None
    processing_log: list[ProcessingLogEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_corridor(self) -> Payment:
        if self.corridor is None:
            self.corridor = f"{self.source_currency}-{self.destination_currency}"
        return self
