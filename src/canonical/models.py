"""Core data models for the candidate transformer.

Two layers live here, kept deliberately separate:

1. ``Observation`` — the atomic unit flowing through the engine. Every source
   adapter emits a stream of these. Nothing downstream ever sees a raw source
   again; it only sees observations. This is what makes the engine
   source-agnostic: adding a new source means writing one adapter that emits
   observations, and zero changes anywhere else.

2. ``CanonicalProfile`` — the single, rich, internal record the engine builds.
   It always has the same fixed shape, always carries full provenance and
   confidence. The *output* the user asked for is a separate projection of this
   (see ``project.py``); the engine never knows the output config exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Method(str, Enum):
    """How a value was extracted. Ordered loosely from most to least reliable.

    The method matters as much as the source: a phone number sitting in a
    dedicated CSV column is far more trustworthy than one scraped out of resume
    prose with a regex, even if the resume is otherwise a fine source.
    """

    STRUCTURED_FIELD = "structured_field"   # a named column / JSON key
    SEMI_STRUCTURED = "semi_structured"     # blob with its own keys, loosely typed
    LABELED_PROSE = "labeled_prose"         # "Email: x@y.com" in free text
    REGEX_PROSE = "regex_prose"             # pattern-matched out of free text
    INFERRED = "inferred"                   # derived, not stated


# Reliability weight per extraction method, in [0, 1]. Conservative on purpose:
# prose extraction is never treated as gospel.
METHOD_RELIABILITY: dict[Method, float] = {
    Method.STRUCTURED_FIELD: 1.00,
    Method.SEMI_STRUCTURED: 0.85,
    Method.LABELED_PROSE: 0.70,
    Method.REGEX_PROSE: 0.50,
    Method.INFERRED: 0.30,
}


class Observation(BaseModel):
    """One claim about one field, from one source, by one method.

    ``value`` is the *normalized* value once it passes through the normalize
    stage; ``raw_value`` always preserves what the source actually said, so the
    profile is fully traceable back to the original text.
    """

    field: str
    value: Any
    raw_value: Any
    source: str                       # e.g. "recruiter_csv", "ats_json"
    method: Method
    # Set True by the normalizer when it could not make sense of raw_value.
    # A dropped observation never contributes a value — we stay empty rather
    # than invent. It is kept around only so we can explain the gap.
    dropped: bool = False
    note: str | None = None

    def reliability(self) -> float:
        return METHOD_RELIABILITY[self.method]


class Provenance(BaseModel):
    """Where a final field value came from and how it was decided."""

    source: str
    method: Method
    raw_value: Any
    # Other sources that independently agreed with the winning value.
    corroborated_by: list[str] = Field(default_factory=list)
    # Sources that disagreed (lost the conflict). Kept for explainability.
    conflicted_with: list[str] = Field(default_factory=list)
    decision: str = ""                # human-readable "why this won"


class Field_(BaseModel):
    """A resolved field: its value, how confident we are, and where it came from.

    For multi-valued fields (emails, skills, ...), ``item_confidences`` holds the
    per-entry confidence aligned positionally with ``value`` and ``provenance``,
    so the default output can present each skill/email with its own score.
    """

    value: Any
    confidence: float
    provenance: list[Provenance] = Field(default_factory=list)
    item_confidences: list[float] = Field(default_factory=list)


class CanonicalProfile(BaseModel):
    """The fixed internal record. Every field is a ``Field_`` so value,
    confidence and provenance always travel together."""

    candidate_id: Field_
    full_name: Field_
    emails: Field_
    phones: Field_
    location: Field_
    links: Field_
    headline: Field_
    years_experience: Field_
    skills: Field_
    experience: Field_
    education: Field_
    overall_confidence: float = 0.0
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def field_names() -> list[str]:
        return [
            "candidate_id", "full_name", "emails", "phones", "location",
            "links", "headline", "years_experience", "skills",
            "experience", "education",
        ]
