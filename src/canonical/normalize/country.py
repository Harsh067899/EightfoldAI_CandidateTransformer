"""Country normalization to ISO-3166-1 alpha-2.

Optimization note: a small hand-built alias map handles the overwhelmingly
common cases ("USA", "United States", "UK") in a single O(1) dict lookup
before we ever touch ``pycountry``'s fuzzy search, which is comparatively
expensive. This is the right kind of optimization — the common path is hot and
cheap, the rare path is correct — rather than premature micro-tuning.
"""

from __future__ import annotations

import pycountry

# Common aliases that pycountry's fuzzy search gets wrong or slow on.
_ALIAS = {
    "usa": "US", "u.s.a.": "US", "u.s.": "US", "us": "US",
    "united states": "US", "united states of america": "US", "america": "US",
    "uk": "GB", "u.k.": "GB", "united kingdom": "GB", "great britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB",
    "uae": "AE", "south korea": "KR", "north korea": "KP",
    "russia": "RU", "iran": "IR", "vietnam": "VN", "czechia": "CZ",
    "czech republic": "CZ", "ivory coast": "CI",
}


def normalize_country(raw: str) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    key = text.lower()
    if key in _ALIAS:
        return _ALIAS[key]

    # Already a valid 2-letter code?
    if len(text) == 2:
        match = pycountry.countries.get(alpha_2=text.upper())
        if match:
            return match.alpha_2

    # Exact name / common-name lookup is cheap and unambiguous.
    try:
        match = pycountry.countries.lookup(text)
        return match.alpha_2
    except LookupError:
        return None
