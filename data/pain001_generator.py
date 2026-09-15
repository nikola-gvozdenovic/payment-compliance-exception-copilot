"""Synthetic ISO 20022 pain.001.001.03 (Customer Credit Transfer Initiation) XML generator.

Builds a single-transaction pain.001.001.03 message using only the standard
library. This produces structurally valid, correctly-ordered XML for the
`pain.001.001.03` namespace -- it does not validate against a real XSD (no XSD
is bundled in this repo). `RmtInf` is genuinely optional and last-in-sequence
per the schema, so omitting it (via `remittance_info=None`) is a schema-valid
way to model a "missing remittance field" business-rule violation without
producing malformed XML.

Output is pretty-printed via `xml.dom.minidom` for human readability when
fixtures are committed to the repo. `toprettyxml()` inserts whitespace text
nodes, so the output is not a byte-minimal serialization -- don't assert on
exact byte output, assert on parsed structure instead.
"""

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from xml.dom import minidom

NAMESPACE = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"


def build_pain001_xml(
    *,
    msg_id: str,
    payment_info_id: str,
    end_to_end_id: str,
    execution_date: date,
    debtor_name: str,
    debtor_iban: str,
    debtor_bic: str,
    creditor_name: str,
    creditor_iban: str,
    creditor_bic: str,
    amount: Decimal,
    currency: str,
    remittance_info: str | None = None,
) -> str:
    """Build a single-transaction pain.001.001.03 XML message.

    Element order within GrpHdr, PmtInf, and CdtTrfTxInf follows the
    pain.001.001.03 schema sequence exactly. Do not reorder the ET.SubElement
    calls below "for readability" -- ElementTree preserves insertion order and
    an out-of-sequence document is schema-invalid even though ElementTree
    itself won't complain at build time.
    """
    ET.register_namespace("", NAMESPACE)
    document = ET.Element(f"{{{NAMESPACE}}}Document")
    cstmr_cdt_trf_initn = ET.SubElement(document, f"{{{NAMESPACE}}}CstmrCdtTrfInitn")

    amount_str = str(amount)

    # GrpHdr, in schema order: MsgId, CreDtTm, NbOfTxs, CtrlSum, InitgPty/Nm
    grp_hdr = ET.SubElement(cstmr_cdt_trf_initn, f"{{{NAMESPACE}}}GrpHdr")
    ET.SubElement(grp_hdr, f"{{{NAMESPACE}}}MsgId").text = msg_id
    ET.SubElement(grp_hdr, f"{{{NAMESPACE}}}CreDtTm").text = execution_date.isoformat()
    ET.SubElement(grp_hdr, f"{{{NAMESPACE}}}NbOfTxs").text = "1"
    ET.SubElement(grp_hdr, f"{{{NAMESPACE}}}CtrlSum").text = amount_str
    initg_pty = ET.SubElement(grp_hdr, f"{{{NAMESPACE}}}InitgPty")
    ET.SubElement(initg_pty, f"{{{NAMESPACE}}}Nm").text = debtor_name

    # PmtInf, in schema order: PmtInfId, PmtMtd, NbOfTxs, CtrlSum, ReqdExctnDt,
    # Dbtr/Nm, DbtrAcct/Id/IBAN, DbtrAgt/FinInstnId/BIC, ChrgBr, CdtTrfTxInf
    pmt_inf = ET.SubElement(cstmr_cdt_trf_initn, f"{{{NAMESPACE}}}PmtInf")
    ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}PmtInfId").text = payment_info_id
    ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}PmtMtd").text = "TRF"
    ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}NbOfTxs").text = "1"
    ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}CtrlSum").text = amount_str

    reqd_exctn_dt = ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}ReqdExctnDt")
    ET.SubElement(reqd_exctn_dt, f"{{{NAMESPACE}}}Dt").text = execution_date.isoformat()

    dbtr = ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}Dbtr")
    ET.SubElement(dbtr, f"{{{NAMESPACE}}}Nm").text = debtor_name

    dbtr_acct = ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}DbtrAcct")
    dbtr_acct_id = ET.SubElement(dbtr_acct, f"{{{NAMESPACE}}}Id")
    ET.SubElement(dbtr_acct_id, f"{{{NAMESPACE}}}IBAN").text = debtor_iban

    dbtr_agt = ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}DbtrAgt")
    dbtr_agt_fin_instn_id = ET.SubElement(dbtr_agt, f"{{{NAMESPACE}}}FinInstnId")
    ET.SubElement(dbtr_agt_fin_instn_id, f"{{{NAMESPACE}}}BIC").text = debtor_bic

    ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}ChrgBr").text = "SLEV"

    # CdtTrfTxInf, in schema order: PmtId/EndToEndId, Amt/InstdAmt, CdtrAgt,
    # Cdtr, CdtrAcct, then optionally RmtInf
    cdt_trf_tx_inf = ET.SubElement(pmt_inf, f"{{{NAMESPACE}}}CdtTrfTxInf")

    pmt_id = ET.SubElement(cdt_trf_tx_inf, f"{{{NAMESPACE}}}PmtId")
    ET.SubElement(pmt_id, f"{{{NAMESPACE}}}EndToEndId").text = end_to_end_id

    amt = ET.SubElement(cdt_trf_tx_inf, f"{{{NAMESPACE}}}Amt")
    instd_amt = ET.SubElement(amt, f"{{{NAMESPACE}}}InstdAmt")
    instd_amt.set("Ccy", currency)
    instd_amt.text = amount_str

    cdtr_agt = ET.SubElement(cdt_trf_tx_inf, f"{{{NAMESPACE}}}CdtrAgt")
    cdtr_agt_fin_instn_id = ET.SubElement(cdtr_agt, f"{{{NAMESPACE}}}FinInstnId")
    ET.SubElement(cdtr_agt_fin_instn_id, f"{{{NAMESPACE}}}BIC").text = creditor_bic

    cdtr = ET.SubElement(cdt_trf_tx_inf, f"{{{NAMESPACE}}}Cdtr")
    ET.SubElement(cdtr, f"{{{NAMESPACE}}}Nm").text = creditor_name

    cdtr_acct = ET.SubElement(cdt_trf_tx_inf, f"{{{NAMESPACE}}}CdtrAcct")
    cdtr_acct_id = ET.SubElement(cdtr_acct, f"{{{NAMESPACE}}}Id")
    ET.SubElement(cdtr_acct_id, f"{{{NAMESPACE}}}IBAN").text = creditor_iban

    if remittance_info is not None:
        rmt_inf = ET.SubElement(cdt_trf_tx_inf, f"{{{NAMESPACE}}}RmtInf")
        ET.SubElement(rmt_inf, f"{{{NAMESPACE}}}Ustrd").text = remittance_info

    raw_xml = ET.tostring(document, encoding="unicode")
    return minidom.parseString(raw_xml).toprettyxml(indent="  ")
