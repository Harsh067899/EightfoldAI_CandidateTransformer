"""ATS JSON blob adapter (semi-structured source).

Real ATS exports have their own field names that rarely match your schema
(``phoneNumber`` not ``phone``, ``jobTitle`` not ``title``), nested objects,
and inconsistent typing. This adapter maps known keys to canonical fields and
emits SEMI_STRUCTURED observations (trusted, but a notch below a clean CSV
column).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import Method, Observation

SOURCE = "ats_json"


class AtsJsonAdapter:
    name = SOURCE

    def extract(self, path: Path) -> list[Observation]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        out: list[Observation] = []

        def add(field: str, value, raw=None):
            if value is None:
                return
            if isinstance(value, str) and not value.strip():
                return
            out.append(Observation(
                field=field, value=value, raw_value=raw if raw is not None else value,
                source=SOURCE, method=Method.SEMI_STRUCTURED,
            ))

        add("candidate_id", data.get("candidateId") or data.get("id"))
        # Name may be split into parts.
        name = data.get("fullName")
        if not name and (data.get("firstName") or data.get("lastName")):
            name = " ".join(p for p in [data.get("firstName"), data.get("lastName")] if p)
        add("full_name", name)

        add("emails", data.get("emailAddress") or data.get("email"))
        add("phones", data.get("phoneNumber") or data.get("phone"))
        add("headline", data.get("jobTitle") or data.get("title"))

        loc = data.get("location") or {}
        if isinstance(loc, dict) and loc:
            add("location", {
                "city": loc.get("city"),
                "region": loc.get("state") or loc.get("region"),
                "country": loc.get("country"),
            }, raw=loc)
        elif isinstance(loc, str):
            add("location", {"city": None, "region": None, "country": loc}, raw=loc)

        for skill in data.get("skills", []) or []:
            add("skills", skill)

        # Work history / experience (real ATS exports usually carry this).
        for exp in (data.get("workHistory") or data.get("experience") or []):
            if isinstance(exp, dict):
                add("experience", {
                    "title": exp.get("title") or exp.get("jobTitle"),
                    "company": exp.get("company") or exp.get("employer"),
                    "start": exp.get("start") or exp.get("startDate"),
                    "end": exp.get("end") or exp.get("endDate"),
                    "summary": exp.get("summary"),
                }, raw=exp)

        # Education.
        for edu in (data.get("education") or []):
            if isinstance(edu, dict):
                add("education", {
                    "institution": edu.get("institution") or edu.get("school"),
                    "degree": edu.get("degree"),
                    "field": edu.get("field") or edu.get("major"),
                    "end_year": str(edu.get("endYear") or edu.get("year") or "") or None,
                }, raw=edu)

        # Links / social profiles.
        for key in ("linkedin", "linkedInUrl", "github", "githubUrl", "portfolio"):
            if data.get(key):
                add("links", data[key])

        yexp = data.get("yearsExperience") or data.get("years_experience")
        if yexp is not None:
            add("years_experience", yexp)

        return out
