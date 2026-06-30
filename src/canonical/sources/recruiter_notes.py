"""Recruiter notes adapter (unstructured source: free-text .txt).

The messiest source: hand-typed notes. We pull labeled values ("Email: ...")
as LABELED_PROSE and free-floating patterns as REGEX_PROSE. This is where the
"wrong-but-confident is worse than empty" principle gets exercised: a typo'd
email here should *not* override a clean CSV email, and an unparseable value
should drop to nothing rather than poison the profile.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Method, Observation

SOURCE = "recruiter_notes"

_LABELED = {
    "email": ("emails", Method.LABELED_PROSE),
    "phone": ("phones", Method.LABELED_PROSE),
    "cell": ("phones", Method.LABELED_PROSE),
    "name": ("full_name", Method.LABELED_PROSE),
    "location": ("location", Method.LABELED_PROSE),
    "title": ("headline", Method.LABELED_PROSE),
}
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(\+?\d[\d\s().\-]{7,}\d)")
_URL = re.compile(r"((?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com)/[^\s,;|]+)", re.IGNORECASE)


class RecruiterNotesAdapter:
    name = SOURCE

    def extract(self, path: Path) -> list[Observation]:
        text = Path(path).read_text(encoding="utf-8")
        out: list[Observation] = []

        for line in text.splitlines():
            if ":" in line:
                label, _, rest = line.partition(":")
                key = label.strip().lower()
                rest = rest.strip()
                if key in _LABELED and rest:
                    field, method = _LABELED[key]
                    value = {"city": None, "region": None, "country": rest} if field == "location" else rest
                    out.append(Observation(field=field, value=value, raw_value=rest,
                                           source=SOURCE, method=method))

        # Catch free-floating contacts not on a labeled line (lowest trust).
        labeled_text = "\n".join(l for l in text.splitlines() if ":" in l)
        for m in _EMAIL.findall(text):
            if m not in labeled_text:
                out.append(Observation(field="emails", value=m, raw_value=m,
                                       source=SOURCE, method=Method.REGEX_PROSE))
        for m in _PHONE.findall(text):
            if len(re.sub(r"\D", "", m)) >= 10 and m not in labeled_text:
                out.append(Observation(field="phones", value=m, raw_value=m,
                                       source=SOURCE, method=Method.REGEX_PROSE))
        for m in _URL.findall(text):
            out.append(Observation(field="links", value=m.rstrip(".,;"), raw_value=m,
                                   source=SOURCE, method=Method.REGEX_PROSE))
        return out
