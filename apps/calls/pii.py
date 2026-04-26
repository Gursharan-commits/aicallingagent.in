"""
PII masking for transcript text.

Applied before any transcript is persisted to the database.
Covers the most common PII patterns for India (IN) and UK tenants.

Patterns masked:
  - Phone numbers  (E.164, local Indian, UK)
  - Email addresses
  - Credit / debit card numbers (16-digit sequences)
  - Indian Aadhaar numbers (12-digit with optional spaces)
  - Indian PAN numbers      (AAAAA9999A format)
  - UK National Insurance   (XX 99 99 99 X)
  - UK sort codes + account numbers
  - Dates of birth (several common formats)
  - IP addresses
"""

import re
from typing import NamedTuple

__all__ = ["mask_pii", "PII_PATTERNS"]


class _Pattern(NamedTuple):
    name: str
    pattern: re.Pattern
    replacement: str


PII_PATTERNS: list[_Pattern] = [
    # ── Email ────────────────────────────────────────────────────────────────
    _Pattern(
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL]",
    ),
    # ── Phone numbers ────────────────────────────────────────────────────────
    # E.164 international
    _Pattern(
        "phone_e164",
        re.compile(r"\+\d{1,3}[\s\-]?\d[\d\s\-]{6,14}\d"),
        "[PHONE]",
    ),
    # Indian 10-digit mobile (starting with 6-9)
    _Pattern(
        "phone_india",
        re.compile(r"\b[6-9]\d{9}\b"),
        "[PHONE]",
    ),
    # UK landline / mobile (07xxx, 01xxx, 02xxx)
    _Pattern(
        "phone_uk",
        re.compile(r"\b0[1-9]\d{8,9}\b"),
        "[PHONE]",
    ),
    # ── Credit / debit card (Luhn-like 16-digit) ─────────────────────────────
    _Pattern(
        "card_number",
        re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
        "[CARD]",
    ),
    # ── Indian Aadhaar (12 digits, optionally space-separated in groups of 4) ─
    _Pattern(
        "aadhaar",
        re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
        "[AADHAAR]",
    ),
    # ── Indian PAN (AAAAA9999A) ───────────────────────────────────────────────
    _Pattern(
        "pan",
        re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
        "[PAN]",
    ),
    # ── UK National Insurance (AA 99 99 99 A) ────────────────────────────────
    _Pattern(
        "uk_ni",
        re.compile(
            r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
            re.IGNORECASE,
        ),
        "[NI]",
    ),
    # ── UK sort code + account (99-99-99  99999999) ──────────────────────────
    _Pattern(
        "uk_sort_account",
        re.compile(r"\b\d{2}-\d{2}-\d{2}\s+\d{8}\b"),
        "[BANK]",
    ),
    # ── Date of birth (common formats) ───────────────────────────────────────
    _Pattern(
        "dob",
        re.compile(
            r"\b(?:\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}"
            r"|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})\b"
        ),
        "[DOB]",
    ),
    # ── IP address ───────────────────────────────────────────────────────────
    _Pattern(
        "ip_address",
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "[IP]",
    ),
]


def mask_pii(text: str) -> str:
    """
    Apply all PII patterns to *text* and return the masked version.

    Patterns are applied in order; replacements from earlier patterns
    (e.g. [PHONE]) are not re-scanned by later patterns.
    """
    for p in PII_PATTERNS:
        text = p.pattern.sub(p.replacement, text)
    return text
