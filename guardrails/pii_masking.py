"""PII masking at the data-ingestion boundary (PRD Section 6.2, TICKET-8).

`mask_payment()` is the gate every payment passes through before any agent sees
it. It swaps every name, IBAN and BIC for a role-based placeholder and returns
two things that must never travel together into a prompt:

- `MaskedPayment` -- what agents receive. Contains placeholders only.
- `TokenVault` -- the private placeholder -> real value lookup. In memory only,
  lives for one payment's processing run, never persisted, never put in a
  prompt. `reveal()` exists for plain-code consumers (e.g. the TICKET-7 audit
  report shown to a human), never for LLM input.

Masking runs in three layers, because any single layer misses something:

1. Structured fields -- Nm/IBAN/BIC elements read straight from the pain.001 XML.
2. Known values in free text -- every value from layer 1 is also searched for
   anywhere else (remittance info, processing-log details), ignoring case and
   whitespace.
3. IBAN-shaped strings in free text -- anything that looks like an IBAN *and*
   passes the ISO 13616 mod-97 check digits becomes `[PII_n]`. BICs are not
   pattern-searched: any 8-letter uppercase word (e.g. "SANCTION") has the BIC
   shape, so it would only add noise. Known BICs are covered by layer 2.

Tokens are role-based and bracketed (`[CREDITOR_NAME]`, `[CREDITOR_IBAN:AE]`).
The country code is kept because jurisdiction rules depend on it. Tokens are
deterministic within one payment (the same value always gets the same token)
but deliberately carry nothing derived from the value, so two payments to the
same company can't be linked by their tokens. MsgId/EndToEndId are internal
transaction references, not PII, and stay unmasked (duplicate detection needs
them).

Sanctions screening needs the *real* payee name, so it runs in plain code
before masking (TICKET-6). This module only provides the slot: pass the
resulting `ScreeningHit`s to `mask_payment()` and the LLM sees
"[CREDITOR_NAME] matched sanctions entry SANC-0001", never the name.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from data.models import FlagReason, Payment, PaymentStatus, ProcessingLogEntry
from data.pain001_generator import NAMESPACE

_IBAN_SHAPE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
# Zero-width lookahead so every possible start position is tried, including
# ones inside a failed candidate.
_IBAN_START = re.compile(r"(?=\b[A-Za-z]{2}\d{2})")
_IBAN_MIN_LEN = 15
_IBAN_MAX_LEN = 34


class PartyRole(str, Enum):
    """Which party in the payment a value belongs to."""

    DEBTOR = "debtor"
    CREDITOR = "creditor"
    INITIATING_PARTY = "initiating_party"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


class TokenVault:
    """Private placeholder -> real value lookup for one payment.

    Deliberately a plain class, not a pydantic model: the decision log's JSON
    encoder raises on non-BaseModel objects, so accidentally logging a vault
    fails loudly instead of writing real values to disk.
    """

    def __init__(self, payment_id: str) -> None:
        self.payment_id = payment_id
        self._by_token: dict[str, str] = {}
        self._by_value: dict[str, str] = {}
        self._pii_count = 0

    def token_for(self, value: str, label: str) -> str:
        """Return the token for `value`, registering it under `label` if new."""
        key = _normalize(value)
        if key in self._by_value:
            return self._by_value[key]
        token = label
        suffix = 2
        while token in self._by_token:
            token = f"{label[:-1]}_{suffix}]"
            suffix += 1
        self._by_token[token] = value
        self._by_value[key] = token
        return token

    def next_pii_token(self, value: str) -> str:
        """Register a value found only by pattern search as `[PII_n]`."""
        key = _normalize(value)
        if key in self._by_value:
            return self._by_value[key]
        self._pii_count += 1
        return self.token_for(value, f"[PII_{self._pii_count}]")

    def reveal(self, token: str) -> str:
        """Return the real value behind a token. Plain-code consumers only, never prompts."""
        return self._by_token[token]

    def tokens(self) -> list[str]:
        return list(self._by_token)

    def items(self) -> list[tuple[str, str]]:
        return list(self._by_token.items())

    def __repr__(self) -> str:
        # Never include values: pytest assertion output and tracebacks call repr.
        return f"TokenVault(payment_id={self.payment_id!r}, tokens={len(self._by_token)})"


def iban_checksum_valid(candidate: str) -> bool:
    """ISO 13616 mod-97 check: move the first 4 chars to the end, letters -> 10..35."""
    iban = candidate.replace(" ", "").upper()
    if not _IBAN_SHAPE.match(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def find_iban_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of checksum-valid IBANs in free text.

    A greedy regex would swallow the words after a spaced IBAN ("... 0130 00 for
    invoice" -> includes "for"), the checksum would then fail and the IBAN would
    be missed. Instead, from each candidate start, collect up to 34 alphanumerics
    (single spaces allowed between them) and keep the longest prefix whose check
    digits are valid.
    """
    spans: list[tuple[int, int]] = []
    covered_until = -1
    for match in _IBAN_START.finditer(text):
        start = match.start()
        if start < covered_until:
            continue
        chars: list[str] = []
        ends: list[int] = []
        i = start
        while i < len(text) and len(chars) < _IBAN_MAX_LEN:
            c = text[i]
            if c.isascii() and c.isalnum():
                chars.append(c)
                ends.append(i + 1)
            elif not (
                c == " " and i + 1 < len(text) and text[i + 1].isascii() and text[i + 1].isalnum()
            ):
                break
            i += 1
        for length in range(len(chars), _IBAN_MIN_LEN - 1, -1):
            if iban_checksum_valid("".join(chars[:length])):
                spans.append((start, ends[length - 1]))
                covered_until = ends[length - 1]
                break
    return spans


def _value_pattern(value: str) -> re.Pattern[str]:
    """Match `value` ignoring case and any whitespace between its characters."""
    chars = [re.escape(c) for c in value if not c.isspace()]
    return re.compile(r"\s*".join(chars), re.IGNORECASE)


def mask_text(text: str, vault: TokenVault) -> str:
    """Mask free text: known vault values first (layer 2), then IBAN-shaped strings (layer 3)."""
    result = text
    # Longest first, so a value containing another registered value is replaced whole.
    for token, value in sorted(vault.items(), key=lambda item: len(item[1]), reverse=True):
        result = _value_pattern(value).sub(token, result)
    for start, end in reversed(find_iban_spans(result)):
        result = result[:start] + vault.next_pii_token(result[start:end]) + result[end:]
    return result


def _path(*tags: str) -> str:
    return ".//" + "/".join(f"{{{NAMESPACE}}}{tag}" for tag in tags)


# Fixed order: debtor before initiating party, so when InitgPty/Nm == Dbtr/Nm
# (true in every committed fixture) the initiating party reuses [DEBTOR_NAME].
_STRUCTURED_FIELDS: list[tuple[PartyRole, str, tuple[str, ...]]] = [
    (PartyRole.DEBTOR, "NAME", ("Dbtr", "Nm")),
    (PartyRole.DEBTOR, "IBAN", ("DbtrAcct", "Id", "IBAN")),
    (PartyRole.DEBTOR, "BIC", ("DbtrAgt", "FinInstnId", "BIC")),
    (PartyRole.CREDITOR, "NAME", ("Cdtr", "Nm")),
    (PartyRole.CREDITOR, "IBAN", ("CdtrAcct", "Id", "IBAN")),
    (PartyRole.CREDITOR, "BIC", ("CdtrAgt", "FinInstnId", "BIC")),
    (PartyRole.INITIATING_PARTY, "NAME", ("InitgPty", "Nm")),
]


def _label(role: PartyRole, kind: str, value: str) -> str:
    prefix = role.value.upper()
    if kind == "IBAN":
        return f"[{prefix}_IBAN:{value[:2].upper()}]"
    if kind == "BIC":
        return f"[{prefix}_BIC:{value[4:6].upper()}]"
    return f"[{prefix}_NAME]"


def _mask_xml(xml: str, vault: TokenVault) -> tuple[str, dict[PartyRole, str]]:
    """Mask structured PII fields (layer 1), then run free-text masking over the whole XML.

    Returns the masked XML and the name token assigned to each party role.
    Missing elements are skipped, so a malformed payment still gets masked
    instead of crashing. Output is re-indented with `ET.indent` and has no XML
    declaration; assert on parsed structure, not exact bytes.
    """
    ET.register_namespace("", NAMESPACE)
    root = ET.fromstring(xml)
    name_tokens: dict[PartyRole, str] = {}
    for role, kind, tags in _STRUCTURED_FIELDS:
        element = root.find(_path(*tags))
        if element is None or not element.text or not element.text.strip():
            continue
        value = element.text.strip()
        token = vault.token_for(value, _label(role, kind, value))
        element.text = token
        if kind == "NAME":
            name_tokens[role] = token
    ET.indent(root, space="  ")
    return mask_text(ET.tostring(root, encoding="unicode"), vault), name_tokens


class ScreeningHit(BaseModel):
    """One sanctions match, found by TICKET-6's deterministic screener on real names.

    Produced in plain code *before* masking. This ticket only defines the slot.
    """

    party_role: PartyRole
    sanctions_doc_id: str


class MaskedPayment(BaseModel):
    """A `Payment` with every name, IBAN and BIC replaced by a placeholder.

    This, never `Payment`, is what agents receive.
    """

    model_config = ConfigDict(frozen=True)

    payment_id: str
    source_currency: str
    destination_currency: str
    corridor: str
    amount: Decimal
    timestamp: datetime
    iso20022_xml: str
    status: PaymentStatus
    flag_reason: FlagReason | None = None
    processing_log: list[ProcessingLogEntry]
    screening_summary: list[str] = []


def mask_payment(
    payment: Payment, *, screening_hits: Sequence[ScreeningHit] = ()
) -> tuple[MaskedPayment, TokenVault]:
    """Mask a payment at the data-ingestion boundary.

    The XML is masked first so its structured values are in the vault before
    free text (processing-log details) is scanned.
    """
    vault = TokenVault(payment.payment_id)
    masked_xml, name_tokens = _mask_xml(payment.iso20022_xml, vault)
    masked_log = [
        ProcessingLogEntry(
            timestamp=entry.timestamp, stage=entry.stage, detail=mask_text(entry.detail, vault)
        )
        for entry in payment.processing_log
    ]

    screening_summary = []
    for hit in screening_hits:
        if hit.party_role not in name_tokens:
            raise ValueError(
                f"Screening hit for {hit.party_role.value}, but that party has no name"
            )
        screening_summary.append(
            f"{name_tokens[hit.party_role]} matched sanctions entry {hit.sanctions_doc_id}"
        )

    masked = MaskedPayment(
        **payment.model_dump(exclude={"iso20022_xml", "processing_log"}),
        iso20022_xml=masked_xml,
        processing_log=masked_log,
        screening_summary=screening_summary,
    )
    return masked, vault


def find_pii(text: str, vault: TokenVault) -> list[str]:
    """Return labels (never values) for every raw PII value found in `text`.

    Checks every vault value (ignoring case and whitespace) plus any
    checksum-valid IBAN. Very short values could in theory match by accident;
    that errs on the side of blocking (fail-closed), which is acceptable.
    An empty list means the text is clean.
    """
    normalized = _normalize(text)
    labels = [token for token, value in vault.items() if _normalize(value) in normalized]
    labels.extend("unregistered IBAN" for _ in find_iban_spans(text))
    return labels
