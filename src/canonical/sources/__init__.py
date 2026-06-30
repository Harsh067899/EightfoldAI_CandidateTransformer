"""Source registry + per-source trust weights.

Trust weight reflects how much we believe a source *in general*, independent of
the extraction method. A recruiter CSV is curated; hand-typed notes are not.
Final reliability of any observation combines source trust with method
reliability (see ``confidence.py`` / ``merge.py``).
"""

from __future__ import annotations

from .base import safe_extract, SourceAdapter
from .recruiter_csv import RecruiterCsvAdapter
from .ats_json import AtsJsonAdapter
from .resume_pdf import ResumeAdapter
from .recruiter_notes import RecruiterNotesAdapter

SOURCE_TRUST: dict[str, float] = {
    "recruiter_csv": 1.00,
    "ats_json": 0.90,
    "resume": 0.65,
    "recruiter_notes": 0.55,
}

ADAPTERS: dict[str, SourceAdapter] = {
    "recruiter_csv": RecruiterCsvAdapter(),
    "ats_json": AtsJsonAdapter(),
    "resume": ResumeAdapter(),
    "recruiter_notes": RecruiterNotesAdapter(),
}

__all__ = ["safe_extract", "SOURCE_TRUST", "ADAPTERS", "SourceAdapter"]
