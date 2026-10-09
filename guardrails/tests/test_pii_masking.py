import xml.etree.ElementTree as ET

import pytest

from data.loader import load_all, load_by_flag_reason
from data.models import FlagReason
from data.pain001_generator import NAMESPACE
from guardrails.pii_masking import (
    PartyRole,
    ScreeningHit,
    TokenVault,
    find_iban_spans,
    find_pii,
    iban_checksum_valid,
    mask_payment,
    mask_text,
)
from guardrails.tests._helpers import leaked, raw_values


def _find(xml: str, *tags: str) -> str | None:
    element = ET.fromstring(xml).find(".//" + "/".join(f"{{{NAMESPACE}}}{t}" for t in tags))
    return None if element is None else element.text


@pytest.mark.parametrize("payment", load_all(), ids=lambda p: p.payment_id)
def test_no_raw_value_survives_masking(payment):
    masked, _ = mask_payment(payment)
    assert leaked(raw_values(payment), masked.model_dump_json()) == []


def test_compliance_hold_tokens_are_role_based_and_keep_country():
    masked, _ = mask_payment(load_by_flag_reason(FlagReason.COMPLIANCE_HOLD))
    xml = masked.iso20022_xml
    assert _find(xml, "Cdtr", "Nm") == "[CREDITOR_NAME]"
    assert _find(xml, "CdtrAcct", "Id", "IBAN") == "[CREDITOR_IBAN:AE]"
    assert _find(xml, "CdtrAgt", "FinInstnId", "BIC") == "[CREDITOR_BIC:AE]"
    assert _find(xml, "Dbtr", "Nm") == "[DEBTOR_NAME]"
    assert _find(xml, "DbtrAcct", "Id", "IBAN") == "[DEBTOR_IBAN:NL]"
    assert _find(xml, "DbtrAgt", "FinInstnId", "BIC") == "[DEBTOR_BIC:NL]"


def test_initiating_party_with_same_name_as_debtor_reuses_debtor_token():
    masked, vault = mask_payment(load_by_flag_reason(FlagReason.COMPLIANCE_HOLD))
    assert _find(masked.iso20022_xml, "InitgPty", "Nm") == "[DEBTOR_NAME]"
    assert "[INITIATING_PARTY_NAME]" not in vault.tokens()


def test_non_pii_fields_are_preserved():
    payment = load_by_flag_reason(FlagReason.DUPLICATE)
    masked, _ = mask_payment(payment)
    for tags in [("MsgId",), ("EndToEndId",), ("InstdAmt",), ("Ustrd",)]:
        assert _find(masked.iso20022_xml, *tags) == _find(payment.iso20022_xml, *tags)
    for field in ["payment_id", "amount", "corridor", "flag_reason", "status", "timestamp"]:
        assert getattr(masked, field) == getattr(payment, field)
    assert [e.detail for e in masked.processing_log] == [e.detail for e in payment.processing_log]


def test_vault_reveals_real_value_but_repr_hides_it():
    masked, vault = mask_payment(load_by_flag_reason(FlagReason.COMPLIANCE_HOLD))
    assert vault.reveal("[CREDITOR_NAME]") == "Zed Trading Consolidated"
    assert vault.payment_id == masked.payment_id
    assert "Zed" not in repr(vault)
    assert "AE07" not in repr(vault)


def test_masking_is_deterministic():
    payment = load_by_flag_reason(FlagReason.TIMEOUT)
    assert mask_payment(payment)[0] == mask_payment(payment)[0]


def test_tokens_are_not_linkable_across_payments():
    first, _ = mask_payment(load_by_flag_reason(FlagReason.TIMEOUT))
    second, _ = mask_payment(load_by_flag_reason(FlagReason.DUPLICATE))
    assert _find(first.iso20022_xml, "Cdtr", "Nm") == "[CREDITOR_NAME]"
    assert _find(second.iso20022_xml, "Cdtr", "Nm") == "[CREDITOR_NAME]"


@pytest.mark.parametrize("payment", load_all(), ids=lambda p: p.payment_id)
def test_fixture_ibans_pass_checksum(payment):
    ibans = [e.text for e in ET.fromstring(payment.iso20022_xml).iter(f"{{{NAMESPACE}}}IBAN")]
    assert len(ibans) == 2
    assert all(iban_checksum_valid(iban) for iban in ibans)


def test_iban_with_one_digit_changed_fails_checksum():
    assert iban_checksum_valid("DE89370400440532013000")
    assert not iban_checksum_valid("DE89370400440532013001")


def test_spaced_iban_followed_by_words_is_found_exactly():
    text = "pay DE89 3704 0044 0532 0130 00 for invoice"
    assert [text[a:b] for a, b in find_iban_spans(text)] == ["DE89 3704 0044 0532 0130 00"]


def test_lowercase_spaced_iban_is_found():
    text = "resend to de89 3704 0044 0532 0130 00 please"
    assert len(find_iban_spans(text)) == 1


def test_text_without_iban_has_no_spans():
    assert find_iban_spans("EUR-GBP corridor flagged, MSG-0003, E2E-0003, 7600.50") == []


def test_mask_text_replaces_known_value_with_different_case_and_spacing():
    vault = TokenVault("PMT-0001")
    vault.token_for("Zed Trading Consolidated", "[CREDITOR_NAME]")
    assert mask_text("payee is ZED  trading consolidated", vault) == "payee is [CREDITOR_NAME]"


def test_mask_text_tokenizes_unknown_iban_as_pii():
    vault = TokenVault("PMT-0001")
    masked = mask_text("send to GB82 WEST 1234 5698 7654 32 today", vault)
    assert masked == "send to [PII_1] today"
    assert vault.reveal("[PII_1]") == "GB82 WEST 1234 5698 7654 32"


def test_same_label_for_different_values_gets_suffix():
    vault = TokenVault("PMT-0001")
    assert vault.token_for("Alpha Ltd", "[CREDITOR_NAME]") == "[CREDITOR_NAME]"
    assert vault.token_for("Beta Ltd", "[CREDITOR_NAME]") == "[CREDITOR_NAME_2]"
    assert vault.token_for("alpha  ltd", "[DEBTOR_NAME]") == "[CREDITOR_NAME]"


def test_screening_hit_becomes_masked_summary():
    masked, _ = mask_payment(
        load_by_flag_reason(FlagReason.COMPLIANCE_HOLD),
        screening_hits=[ScreeningHit(party_role=PartyRole.CREDITOR, sanctions_doc_id="SANC-0001")],
    )
    assert masked.screening_summary == ["[CREDITOR_NAME] matched sanctions entry SANC-0001"]


def test_payment_with_missing_creditor_element_still_masks_the_rest():
    payment = load_by_flag_reason(FlagReason.TIMEOUT)
    root = ET.fromstring(payment.iso20022_xml)
    tx = root.find(f".//{{{NAMESPACE}}}CdtTrfTxInf")
    tx.remove(tx.find(f"{{{NAMESPACE}}}Cdtr"))
    broken = payment.model_copy(update={"iso20022_xml": ET.tostring(root, encoding="unicode")})

    masked, vault = mask_payment(broken)

    assert "[CREDITOR_NAME]" not in vault.tokens()
    assert leaked(raw_values(broken), masked.model_dump_json()) == []


def test_find_pii_returns_labels_never_values():
    _, vault = mask_payment(load_by_flag_reason(FlagReason.COMPLIANCE_HOLD))
    labels = find_pii("creditor is zed trading consolidated", vault)
    assert labels == ["[CREDITOR_NAME]"]


def test_find_pii_flags_unregistered_iban():
    assert find_pii("GB82WEST12345698765432", TokenVault("PMT-0001")) == ["unregistered IBAN"]


def test_find_pii_on_masked_payment_is_clean():
    masked, vault = mask_payment(load_by_flag_reason(FlagReason.COMPLIANCE_HOLD))
    assert find_pii(masked.model_dump_json(), vault) == []
