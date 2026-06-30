"""Normalize stage.

Takes raw observations from the adapters and rewrites each ``value`` into its
canonical form. If a value cannot be normalized, the observation is marked
``dropped`` (with a note) and contributes nothing downstream — we stay empty
rather than invent.
"""

from __future__ import annotations

from .models import Observation
from .normalize import (
    canonicalize_skill,
    normalize_country,
    normalize_phone,
    normalize_month,
)


def normalize_observation(obs: Observation) -> Observation:
    f = obs.field

    if f == "phones":
        norm = normalize_phone(obs.value if isinstance(obs.value, str) else str(obs.value))
        if norm is None:
            return obs.model_copy(update={"dropped": True, "note": "unparseable phone"})
        return obs.model_copy(update={"value": norm})

    if f == "skills":
        norm = canonicalize_skill(obs.value if isinstance(obs.value, str) else str(obs.value))
        if not norm:
            return obs.model_copy(update={"dropped": True, "note": "empty skill"})
        return obs.model_copy(update={"value": norm})

    if f == "location":
        loc = obs.value if isinstance(obs.value, dict) else {"country": obs.value}
        country = normalize_country(loc.get("country")) if loc.get("country") else None
        return obs.model_copy(update={"value": {
            "city": loc.get("city"),
            "region": loc.get("region"),
            "country": country,
        }})

    if f == "experience" and isinstance(obs.value, dict):
        v = dict(obs.value)
        if v.get("start"):
            v["start"] = normalize_month(v["start"]) or v["start"]
        if v.get("end") and v["end"] != "present":
            v["end"] = normalize_month(v["end"]) or v["end"]
        v.setdefault("summary", None)
        return obs.model_copy(update={"value": v})

    if f == "education" and isinstance(obs.value, dict):
        v = dict(obs.value)
        if v.get("degree"):
            v["degree"] = _canon_degree(v["degree"])
        if v.get("end_year"):
            v["end_year"] = str(v["end_year"]).strip() or None
        return obs.model_copy(update={"value": v})

    if f == "emails":
        email = str(obs.value).strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            return obs.model_copy(update={"dropped": True, "note": "malformed email"})
        return obs.model_copy(update={"value": email})

    if f == "years_experience":
        try:
            return obs.model_copy(update={"value": float(obs.value)})
        except (ValueError, TypeError):
            return obs.model_copy(update={"dropped": True, "note": "non-numeric years"})

    if isinstance(obs.value, str):
        return obs.model_copy(update={"value": obs.value.strip()})
    return obs


def normalize_all(observations: list[Observation]) -> list[Observation]:
    return [normalize_observation(o) for o in observations]


# Canonical degree forms, so "B.S", "BS", "bs" all reconcile to one value and
# education entries from different sources corroborate instead of duplicating.
_DEGREE_CANON = {
    "BS": "B.S.", "BSC": "B.S.", "BACHELOROFSCIENCE": "B.S.",
    "BA": "B.A.", "MS": "M.S.", "MSC": "M.S.", "MA": "M.A.",
    "PHD": "Ph.D.", "MBA": "MBA", "BTECH": "B.Tech", "MTECH": "M.Tech",
}


def _canon_degree(raw: str) -> str:
    key = "".join(ch for ch in str(raw).upper() if ch.isalnum())
    return _DEGREE_CANON.get(key, str(raw).strip())
