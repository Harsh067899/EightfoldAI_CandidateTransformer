"""Recruiter CSV export adapter (structured source).

Clean tabular data: one row per candidate, named columns. This is our
highest-trust structured source, so values come out as STRUCTURED_FIELD. A
malformed row is skipped individually rather than failing the whole file.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import Method, Observation

SOURCE = "recruiter_csv"

# Maps CSV header -> canonical field name + whether it is multi-valued.
_COLUMN_MAP = {
    "candidate_id": ("candidate_id", False),
    "id": ("candidate_id", False),
    "name": ("full_name", False),
    "full_name": ("full_name", False),
    "email": ("emails", True),
    "phone": ("phones", True),
    "company": ("_company", False),
    "current_company": ("_company", False),
    "title": ("headline", False),
}


class RecruiterCsvAdapter:
    name = SOURCE

    def extract(self, path: Path) -> list[Observation]:
        out: list[Observation] = []
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                company = (row.get("company") or row.get("current_company") or "").strip()
                title = (row.get("title") or "").strip()
                for header, value in row.items():
                    if header is None:
                        continue
                    key = header.strip().lower()
                    if key not in _COLUMN_MAP:
                        continue
                    field, _multi = _COLUMN_MAP[key]
                    if field.startswith("_"):
                        continue
                    value = (value or "").strip()
                    if not value:
                        continue
                    # Build a richer headline if we have both title and company.
                    if field == "headline" and company:
                        value = f"{title} at {company}"
                    out.append(Observation(
                        field=field, value=value, raw_value=row.get(header),
                        source=SOURCE, method=Method.STRUCTURED_FIELD,
                    ))
        return out
