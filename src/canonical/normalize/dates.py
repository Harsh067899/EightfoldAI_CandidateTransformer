"""Date normalization to ``YYYY-MM``.

Handles the messy date shapes that show up in resumes: "Jan 2021",
"2021-03", "March 2021", "01/2021". Recognizes "Present"/"Current" as an
open-ended end date (returns the sentinel ``"present"``). Anything it cannot
confidently parse returns ``None`` rather than a guessed date.
"""

from __future__ import annotations

import re

from dateutil import parser as dateparser

_PRESENT = re.compile(r"^\s*(present|current|now|ongoing)\s*$", re.IGNORECASE)


def normalize_month(raw: str) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if _PRESENT.match(text):
        return "present"
    try:
        # default fills in a day so day-less strings ("Jan 2021") parse, but we
        # only ever emit year-month so the day is discarded.
        dt = dateparser.parse(text, default=dateparser.parse("2000-01-01"))
    except (ValueError, OverflowError, TypeError):
        return None
    if dt is None:
        return None
    return f"{dt.year:04d}-{dt.month:02d}"


def normalize_date_range(raw: str) -> tuple[str | None, str | None]:
    """Split a range like 'Jan 2021 - Present' into (start, end)."""
    if raw is None:
        return None, None
    parts = re.split(r"\s*(?:-|–|—|to)\s*", str(raw), maxsplit=1)
    if len(parts) == 1:
        return normalize_month(parts[0]), None
    return normalize_month(parts[0]), normalize_month(parts[1])
