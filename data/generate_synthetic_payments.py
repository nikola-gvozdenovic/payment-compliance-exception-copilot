"""Generates the 5 committed synthetic payment fixtures.

One payment per FlagReason, covering the Triage Agent's full classification
taxonomy (PRD Section 7.1). Every scenario below uses fixed, hardcoded
timestamps -- never `datetime.now()` -- so re-running this script reproduces
byte-identical JSON in data/synthetic_payments/. This is a deliberate
trade-off: these fixtures favor being a stable, diffable, reviewable dataset
over looking like "live" data. Do not switch to `datetime.now()`.

Run as: `uv run python -m data.generate_synthetic_payments`

Scope note: the compliance_hold and corridor_currency_issue scenarios only
need to *look* plausible to a human reviewer at this stage. They do not
reference or depend on TICKET-2's sanctions/policy document corpus, which
does not exist yet.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from data.models import FlagReason, Payment, PaymentStatus, ProcessingLogEntry
from data.pain001_generator import build_pain001_xml

SYNTHETIC_PAYMENTS_DIR = Path(__file__).parent / "synthetic_payments"


def _build_payments() -> list[Payment]:
    payments: list[Payment] = []

    # PMT-0001 -- missing_malformed_field: RmtInf omitted entirely.
    ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    xml = build_pain001_xml(
        msg_id="MSG-0001",
        payment_info_id="PMTINF-0001",
        end_to_end_id="E2E-0001",
        execution_date=ts.date(),
        debtor_name="Acme Exports GmbH",
        debtor_iban="DE89370400440532013000",
        debtor_bic="DEUTDEFF",
        creditor_name="Riviera Imports SARL",
        creditor_iban="FR1420041010050500013M02606",
        creditor_bic="PSSTFRPP",
        amount=Decimal("4250.00"),
        currency="EUR",
        remittance_info=None,
    )
    payments.append(
        Payment(
            payment_id="PMT-0001",
            source_currency="EUR",
            destination_currency="EUR",
            amount=Decimal("4250.00"),
            timestamp=ts,
            iso20022_xml=xml,
            status=PaymentStatus.FLAGGED,
            flag_reason=FlagReason.MISSING_MALFORMED_FIELD,
            processing_log=[
                ProcessingLogEntry(
                    timestamp=ts,
                    stage="ingestion",
                    detail="payment received and parsed",
                ),
                ProcessingLogEntry(
                    timestamp=ts,
                    stage="validation",
                    detail=(
                        "missing RmtInf: remittance information required by "
                        "policy but absent from payload"
                    ),
                ),
            ],
        )
    )

    # PMT-0002 -- compliance_hold: fictional sanctioned-sounding creditor name.
    ts = datetime(2026, 1, 15, 11, 30, 0, tzinfo=UTC)
    xml = build_pain001_xml(
        msg_id="MSG-0002",
        payment_info_id="PMTINF-0002",
        end_to_end_id="E2E-0002",
        execution_date=ts.date(),
        debtor_name="Northwind Trading Co",
        debtor_iban="NL91ABNA0417164300",
        debtor_bic="ABNANL2A",
        creditor_name="Zed Trading Consolidated",  # fictional, no real entity
        creditor_iban="AE070331234567890123456",
        creditor_bic="EBILAEAD",
        amount=Decimal("18900.00"),
        currency="USD",
        remittance_info="Consulting services Q1",
    )
    payments.append(
        Payment(
            payment_id="PMT-0002",
            source_currency="USD",
            destination_currency="USD",
            amount=Decimal("18900.00"),
            timestamp=ts,
            iso20022_xml=xml,
            status=PaymentStatus.FLAGGED,
            flag_reason=FlagReason.COMPLIANCE_HOLD,
            processing_log=[
                ProcessingLogEntry(
                    timestamp=ts,
                    stage="ingestion",
                    detail="payment received and parsed",
                ),
                ProcessingLogEntry(
                    timestamp=ts,
                    stage="compliance_screen",
                    detail="creditor name matched a watchlist-style entry pending review",
                ),
            ],
        )
    )

    # PMT-0003 -- corridor_currency_issue: EUR->GBP corridor (PRD's own example).
    ts = datetime(2026, 1, 15, 13, 0, 0, tzinfo=UTC)
    xml = build_pain001_xml(
        msg_id="MSG-0003",
        payment_info_id="PMTINF-0003",
        end_to_end_id="E2E-0003",
        execution_date=ts.date(),
        debtor_name="Continental Freight Ltd",
        debtor_iban="BE68539007547034",
        debtor_bic="GEBABEBB",
        creditor_name="Harborview Logistics PLC",
        creditor_iban="GB29NWBK60161331926819",
        creditor_bic="NWBKGB2L",
        amount=Decimal("7600.50"),
        currency="EUR",
        remittance_info="Freight invoice 9981",
    )
    payments.append(
        Payment(
            payment_id="PMT-0003",
            source_currency="EUR",
            destination_currency="GBP",
            amount=Decimal("7600.50"),
            timestamp=ts,
            iso20022_xml=xml,
            status=PaymentStatus.FLAGGED,
            flag_reason=FlagReason.CORRIDOR_CURRENCY_ISSUE,
            processing_log=[
                ProcessingLogEntry(
                    timestamp=ts,
                    stage="ingestion",
                    detail="payment received and parsed",
                ),
                ProcessingLogEntry(
                    timestamp=ts,
                    stage="corridor_check",
                    detail="EUR-GBP corridor flagged for manual policy review",
                ),
            ],
        )
    )

    # PMT-0004 -- timeout: stuck, no rail acknowledgement after 48h.
    ts = datetime(2026, 1, 13, 9, 0, 0, tzinfo=UTC)
    xml = build_pain001_xml(
        msg_id="MSG-0004",
        payment_info_id="PMTINF-0004",
        end_to_end_id="E2E-0004",
        execution_date=ts.date(),
        debtor_name="Solara Manufacturing Inc",
        debtor_iban="US64SVBKUS6S3300958879",
        debtor_bic="SVBKUS6S",
        creditor_name="Delta Components AG",
        creditor_iban="CH9300762011623852957",
        creditor_bic="UBSWCHZH80A",
        amount=Decimal("52300.00"),
        currency="USD",
        remittance_info="PO 44210 components",
    )
    payments.append(
        Payment(
            payment_id="PMT-0004",
            source_currency="USD",
            destination_currency="CHF",
            amount=Decimal("52300.00"),
            timestamp=ts,
            iso20022_xml=xml,
            status=PaymentStatus.STUCK,
            flag_reason=FlagReason.TIMEOUT,
            processing_log=[
                ProcessingLogEntry(
                    timestamp=ts,
                    stage="ingestion",
                    detail="payment received and parsed",
                ),
                ProcessingLogEntry(
                    timestamp=datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC),
                    stage="processing",
                    detail="no rail acknowledgement received after 48h",
                ),
            ],
        )
    )

    # PMT-0005 -- duplicate: matches an earlier payment's EndToEndId/amount/creditor.
    ts = datetime(2026, 1, 15, 14, 2, 0, tzinfo=UTC)
    xml = build_pain001_xml(
        msg_id="MSG-0005",
        payment_info_id="PMTINF-0005",
        end_to_end_id="E2E-0005",
        execution_date=ts.date(),
        debtor_name="Meridian Retail Group",
        debtor_iban="ES9121000418450200051332",
        debtor_bic="CAIXESBB",
        creditor_name="Vantage Supply Partners",
        creditor_iban="IT60X0542811101000000123456",
        creditor_bic="BAPPIT21",
        amount=Decimal("3120.75"),
        currency="EUR",
        remittance_info="Order 55231 restock",
    )
    payments.append(
        Payment(
            payment_id="PMT-0005",
            source_currency="EUR",
            destination_currency="EUR",
            amount=Decimal("3120.75"),
            timestamp=ts,
            iso20022_xml=xml,
            status=PaymentStatus.FLAGGED,
            flag_reason=FlagReason.DUPLICATE,
            processing_log=[
                ProcessingLogEntry(
                    timestamp=ts,
                    stage="ingestion",
                    detail="payment received and parsed",
                ),
                ProcessingLogEntry(
                    timestamp=datetime(2026, 1, 15, 14, 2, 30, tzinfo=UTC),
                    stage="duplicate_check",
                    detail=(
                        "matches EndToEndId/amount/creditor of a payment "
                        "processed 2 minutes earlier"
                    ),
                ),
            ],
        )
    )

    return payments


def main() -> None:
    SYNTHETIC_PAYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    for payment in _build_payments():
        out_path = SYNTHETIC_PAYMENTS_DIR / f"{payment.flag_reason.value}.json"
        out_path.write_text(payment.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
