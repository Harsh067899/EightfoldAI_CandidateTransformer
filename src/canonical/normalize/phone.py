"""Phone normalization to E.164.

Returns ``None`` when the input cannot be parsed into a valid number. That
``None`` is load-bearing: a garbage phone string becomes an empty value, never
a confidently-wrong one.
"""

from __future__ import annotations

import phonenumbers


def normalize_phone(raw: str, default_region: str = "US") -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        # If the string carries a country code ("+44..."), region is ignored;
        # otherwise we fall back to default_region to interpret it.
        parsed = phonenumbers.parse(text, None if text.startswith("+") else default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
