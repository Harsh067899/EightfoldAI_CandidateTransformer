"""Projection layer — the configurable output.

This is the architectural crux of the brief: the engine builds one rich,
fixed ``CanonicalProfile``; this layer is the *only* thing that knows about the
requested output shape. The engine never sees the config. Swapping output
shapes is pure config, no engine changes.

It does two things:

1. Build a stable **canonical dict view** of the profile — the full default
   schema, with per-item confidences and a provenance block.
2. **Project** that view per a runtime config: select a subset of fields,
   rename/remap via ``from`` paths (``emails[0]``, ``skills[].name``),
   toggle provenance/confidence, and apply the per-field missing-value policy
   (``null`` | ``omit`` | ``error``).

Path mini-language for ``from``:
    ``emails``           whole list / scalar
    ``emails[0]``        indexed element
    ``location.city``    nested key
    ``skills[].name``    map a key across a list of objects
"""

from __future__ import annotations

import re
from typing import Any

from .models import CanonicalProfile


class MissingFieldError(Exception):
    pass


# ---------- canonical dict view ----------

def canonical_view(profile: CanonicalProfile) -> dict[str, Any]:
    """Full, fixed-shape representation with confidence + provenance."""

    def skills_objs():
        f = profile.skills
        return [
            {"name": name,
             "confidence": (f.item_confidences[i] if i < len(f.item_confidences) else f.confidence),
             "sources": sorted({f.provenance[i].source, *f.provenance[i].corroborated_by})
                        if i < len(f.provenance) else []}
            for i, name in enumerate(f.value or [])
        ]

    view = {
        "candidate_id": profile.candidate_id.value,
        "full_name": profile.full_name.value,
        "emails": profile.emails.value or [],
        "phones": profile.phones.value or [],
        "location": profile.location.value or {"city": None, "region": None, "country": None},
        "links": profile.links.value or {"linkedin": None, "github": None, "portfolio": None, "other": []},
        "headline": profile.headline.value,
        "years_experience": profile.years_experience.value,
        "skills": skills_objs(),
        "experience": profile.experience.value or [],
        "education": profile.education.value or [],
        "overall_confidence": profile.overall_confidence,
    }

    # Provenance + per-field confidence kept in a sidecar so the core view stays clean.
    prov = {}
    flat_prov = []   # default-schema provenance: [{field, source, method}]
    for name in CanonicalProfile.field_names():
        fld = getattr(profile, name)
        prov[name] = {
            "confidence": fld.confidence,
            "provenance": [p.model_dump() for p in fld.provenance],
        }
        for p in fld.provenance:
            flat_prov.append({"field": name, "source": p.source,
                              "method": p.method.value})
    view["provenance"] = flat_prov
    view["_meta"] = prov
    return view


# ---------- path resolution ----------

_INDEX = re.compile(r"^(?P<key>\w+)\[(?P<idx>\d+)\]$")
_MAP = re.compile(r"^(?P<key>\w+)\[\]$")


def resolve_path(view: dict[str, Any], path: str) -> tuple[Any, bool]:
    """Return (value, found). ``found`` is False when the path leads to a
    genuinely absent value, which drives the on_missing policy."""
    cur: Any = view
    for part in path.split("."):
        if cur is None:
            return None, False
        m_idx = _INDEX.match(part)
        m_map = _MAP.match(part)
        if m_idx:
            key, idx = m_idx.group("key"), int(m_idx.group("idx"))
            seq = cur.get(key) if isinstance(cur, dict) else None
            if not isinstance(seq, list) or idx >= len(seq):
                return None, False
            cur = seq[idx]
        elif m_map:
            key = m_map.group("key")
            seq = cur.get(key) if isinstance(cur, dict) else None
            if not isinstance(seq, list):
                return None, False
            return ("__MAP__", key, seq), True  # handled by caller with remaining path
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None, False
            cur = cur[part]
    found = not (cur is None or cur == [] or cur == {})
    return cur, found


def _apply_map(seq: list, subkey: str | None) -> list:
    if subkey is None:
        return seq
    return [item.get(subkey) if isinstance(item, dict) else item for item in seq]


# ---------- projection ----------

def project(profile: CanonicalProfile, config: dict[str, Any]) -> dict[str, Any]:
    view = canonical_view(profile)
    include_conf = config.get("include_confidence", False)
    include_prov = config.get("include_provenance", False)
    on_missing_default = config.get("on_missing", "null")

    out: dict[str, Any] = {}
    fields = config.get("fields")

    # No field list => emit the full default schema.
    if not fields:
        out = {k: v for k, v in view.items() if k != "_meta"}
        if not include_conf:
            out.pop("overall_confidence", None)
        if not include_prov:
            out.pop("provenance", None)
        return out

    for spec in fields:
        out_key = spec["path"]
        src_path = spec.get("from", out_key)
        on_missing = spec.get("on_missing", on_missing_default)

        # Handle the map form: "skills[].name"
        if "[]" in src_path:
            head, _, tail = src_path.partition("[].")
            base, found = resolve_path(view, head + "[]")
            if found and isinstance(base, tuple) and base[0] == "__MAP__":
                value = _apply_map(base[2], tail or None)
                found = len(value) > 0
            else:
                value, found = None, False
        else:
            value, found = resolve_path(view, src_path)

        if not found:
            if on_missing == "omit":
                continue
            if on_missing == "error":
                if spec.get("required"):
                    raise MissingFieldError(f"required field '{out_key}' missing (from '{src_path}')")
                value = None
            else:  # null
                value = None

        out[out_key] = value

        if include_conf:
            root = src_path.split(".")[0].split("[")[0]
            meta = view["_meta"].get(root)
            if meta:
                out.setdefault("_confidence", {})[out_key] = meta["confidence"]

    if include_conf and "overall_confidence" not in out:
        out["overall_confidence"] = view["overall_confidence"]
    return out
