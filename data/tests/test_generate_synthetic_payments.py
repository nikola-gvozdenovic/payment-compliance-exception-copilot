import xml.etree.ElementTree as ET

from data.loader import load_all
from data.models import FlagReason


def test_exactly_five_payments_load():
    assert len(load_all()) == 5


def test_all_flag_reasons_covered_exactly_once():
    reasons = [p.flag_reason for p in load_all()]
    assert sorted(reasons, key=lambda r: r.value) == sorted(FlagReason, key=lambda r: r.value)
    assert len(set(reasons)) == len(reasons)


def test_pmt_0001_is_missing_malformed_field_with_no_rmtinf():
    payment = next(p for p in load_all() if p.payment_id == "PMT-0001")
    assert payment.flag_reason == FlagReason.MISSING_MALFORMED_FIELD
    assert "RmtInf" not in payment.iso20022_xml


def test_every_payment_xml_reparses_cleanly():
    for payment in load_all():
        ET.fromstring(payment.iso20022_xml)
