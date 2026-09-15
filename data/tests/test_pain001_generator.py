import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

from data.pain001_generator import NAMESPACE, build_pain001_xml

NS = {"p": NAMESPACE}


def _build(**overrides):
    defaults = {
        "msg_id": "M1",
        "payment_info_id": "P1",
        "end_to_end_id": "E1",
        "execution_date": date(2026, 1, 15),
        "debtor_name": "Acme",
        "debtor_iban": "DE89370400440532013000",
        "debtor_bic": "DEUTDEFF",
        "creditor_name": "Beta",
        "creditor_iban": "GB29NWBK60161331926819",
        "creditor_bic": "NWBKGB2L",
        "amount": Decimal("1000.00"),
        "currency": "EUR",
    }
    defaults.update(overrides)
    return build_pain001_xml(**defaults)


def test_root_tag_and_namespace():
    root = ET.fromstring(_build())
    assert root.tag == f"{{{NAMESPACE}}}Document"


def test_msg_id_present():
    root = ET.fromstring(_build(msg_id="MSG-42"))
    msg_id = root.find("p:CstmrCdtTrfInitn/p:GrpHdr/p:MsgId", NS)
    assert msg_id is not None
    assert msg_id.text == "MSG-42"


def test_instd_amt_currency_and_value():
    root = ET.fromstring(_build(amount=Decimal("250.50"), currency="GBP"))
    instd_amt = root.find("p:CstmrCdtTrfInitn/p:PmtInf/p:CdtTrfTxInf/p:Amt/p:InstdAmt", NS)
    assert instd_amt is not None
    assert instd_amt.get("Ccy") == "GBP"
    assert instd_amt.text == "250.50"


def test_remittance_info_none_omits_rmtinf_entirely():
    root = ET.fromstring(_build(remittance_info=None))
    rmt_inf = root.find(".//p:RmtInf", NS)
    assert rmt_inf is None


def test_remittance_info_present_when_given():
    root = ET.fromstring(_build(remittance_info="Invoice 123"))
    ustrd = root.find("p:CstmrCdtTrfInitn/p:PmtInf/p:CdtTrfTxInf/p:RmtInf/p:Ustrd", NS)
    assert ustrd is not None
    assert ustrd.text == "Invoice 123"
