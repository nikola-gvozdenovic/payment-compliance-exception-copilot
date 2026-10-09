"""Shared helpers for the guardrail tests.

These read raw values straight from the original XML with ElementTree, an
independent oracle: they never use the masking module's own field list or
detector, so a bug there can't hide itself.
"""

import re
import xml.etree.ElementTree as ET

from data.models import Payment

_PII_TAGS = ("Nm", "IBAN", "BIC")


def raw_values(payment: Payment) -> list[str]:
    """Every name, IBAN and BIC in the payment's original XML."""
    root = ET.fromstring(payment.iso20022_xml)
    return sorted(
        {
            element.text.strip()
            for element in root.iter()
            if element.tag.split("}")[-1] in _PII_TAGS and element.text
        }
    )


def squash(text: str) -> str:
    """Lowercase and strip all whitespace, so spaced/lowercase variants still match."""
    return re.sub(r"\s+", "", text).lower()


def leaked(values: list[str], text: str) -> list[str]:
    """Which of `values` appear in `text`, ignoring case and whitespace."""
    return [value for value in values if squash(value) in squash(text)]
