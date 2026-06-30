"""Merge stage — per-field conflict resolution.

Consumes all (normalized, non-dropped) observations for one person and produces
one resolved ``Field_`` per canonical field, carrying value + confidence +
provenance.

Two field shapes:

* **single-valued** (full_name, headline, location, years_experience,
  candidate_id): group observations by value, pick the camp with the strongest
  combined evidence, discount confidence by any dissent, and record who agreed
  / who conflicted and *why* the winner won.
* **multi-valued** (emails, phones, skills, links, experience, education):
  union and dedupe across all sources; confidence reflects the aggregate
  evidence. Conflicting alternates are not "losers" here — more emails is just
  more emails — so these don't take a conflict penalty.

Determinism: grouping and tie-breaks use stable, content-based sort keys, so
the same inputs always yield the same winner.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from .confidence import MIN_CONFIDENCE_TO_EMIT, combine, noisy_or, strength
from .models import CanonicalProfile, Field_, Method, Observation, Provenance
from .sources import SOURCE_TRUST

SINGLE_VALUED = {"candidate_id", "full_name", "headline", "location", "years_experience"}
MULTI_VALUED = {"emails", "phones", "skills", "experience", "education"}
# links is multi-source but resolves to a fixed OBJECT shape, not a list.


def _value_key(value) -> str:
    """Stable hashable key for grouping observation values."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value).strip().lower()


def _resolve_single(field: str, obs: list[Observation]) -> Field_:
    if not obs:
        return Field_(value=None, confidence=0.0)

    # Group by value.
    by_value: dict[str, list[Observation]] = defaultdict(list)
    for o in obs:
        by_value[_value_key(o.value)].append(o)

    # Winner = camp with strongest combined evidence; deterministic tie-break.
    def camp_score(item):
        _key, group = item
        return (noisy_or([strength(g) for g in group]),
                max(SOURCE_TRUST.get(g.source, 0.5) for g in group),
                -len(item[0]))  # shorter key wins ties, for stability
    winner_key, winner_group = max(by_value.items(), key=camp_score)

    dissent = [o for k, grp in by_value.items() if k != winner_key for o in grp]
    conf = combine(winner_group, dissent)

    if conf < MIN_CONFIDENCE_TO_EMIT:
        return Field_(value=None, confidence=round(conf, 4))

    best = max(winner_group, key=strength)
    agree_sources = sorted({o.source for o in winner_group} - {best.source})
    conflict_sources = sorted({o.source for o in dissent})
    decision = (
        f"chose value from {best.source} ({best.method.value})"
        + (f"; corroborated by {', '.join(agree_sources)}" if agree_sources else "")
        + (f"; outranked {', '.join(conflict_sources)} on source/method trust"
           if conflict_sources else "")
    )
    prov = Provenance(
        source=best.source, method=best.method, raw_value=best.raw_value,
        corroborated_by=agree_sources, conflicted_with=conflict_sources,
        decision=decision,
    )
    return Field_(value=winner_group[0].value, confidence=conf, provenance=[prov])


def _resolve_multi(field: str, obs: list[Observation]) -> Field_:
    if not obs:
        return Field_(value=[], confidence=0.0)

    by_value: dict[str, list[Observation]] = defaultdict(list)
    for o in obs:
        by_value[_value_key(o.value)].append(o)

    values = []
    provs: list[Provenance] = []
    confs: list[float] = []
    for key in sorted(by_value):                     # deterministic ordering
        group = by_value[key]
        best = max(group, key=strength)
        c = noisy_or([strength(g) for g in group])
        confs.append(c)
        values.append(best.value)
        others = sorted({g.source for g in group} - {best.source})
        provs.append(Provenance(
            source=best.source, method=best.method, raw_value=best.raw_value,
            corroborated_by=others,
            decision=f"included from {best.source}"
                     + (f"; also in {', '.join(others)}" if others else ""),
        ))

    if field == "emails":
        values, confs, provs = _suppress_typos(values, confs, provs)

    agg = round(sum(confs) / len(confs), 4) if confs else 0.0
    return Field_(value=values, confidence=agg, provenance=provs, item_confidences=confs)


# Likely-typo threshold: a low-confidence value this similar to a higher-confidence
# one is almost certainly a corruption of it, not a genuine second address.
_TYPO_SIMILARITY = 88.0


def _suppress_typos(values, confs, provs):
    """Drop emails that are near-duplicates of a higher-confidence email.

    Directly serves "wrong-but-confident is worse than empty": a one-character
    typo of a verified address ("...@exmaple.con") would otherwise ship as a
    real contact and silently break outreach. We keep the high-confidence
    address and annotate the suppressed one rather than emitting both.
    """
    from rapidfuzz import fuzz

    order = sorted(range(len(values)), key=lambda i: confs[i], reverse=True)
    kept_idx: list[int] = []
    keep_flags = [True] * len(values)
    for i in order:
        for k in kept_idx:
            if confs[i] < confs[k] and fuzz.ratio(str(values[i]), str(values[k])) >= _TYPO_SIMILARITY:
                keep_flags[i] = False
                provs[k].decision += f"; suppressed likely typo '{values[i]}'"
                break
        if keep_flags[i]:
            kept_idx.append(i)

    nv = [values[i] for i in range(len(values)) if keep_flags[i]]
    nc = [confs[i] for i in range(len(values)) if keep_flags[i]]
    npv = [provs[i] for i in range(len(values)) if keep_flags[i]]
    return nv, nc, npv


def _resolve_links(obs: list[Observation]) -> Field_:
    """Resolve link URLs into the schema's object shape
    ``{linkedin, github, portfolio, other[]}``.

    URLs are classified by host. linkedin/github/portfolio are single-valued
    (highest-strength wins); anything unrecognised lands in ``other``. The field
    is always emitted with the full object so the output matches the schema even
    when no source supplied a link.
    """
    shape = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    if not obs:
        return Field_(value=shape, confidence=0.0)

    def classify(url: str) -> str:
        u = url.lower()
        if "linkedin.com" in u:
            return "linkedin"
        if "github.com" in u:
            return "github"
        if any(t in u for t in ("portfolio", "behance", "dribbble")):
            return "portfolio"
        return "other"

    provs: list[Provenance] = []
    confs: list[float] = []
    buckets: dict[str, list[Observation]] = defaultdict(list)
    for o in obs:
        buckets[classify(str(o.value))].append(o)

    for slot in ("linkedin", "github", "portfolio"):
        if buckets.get(slot):
            best = max(buckets[slot], key=strength)
            shape[slot] = best.value
            confs.append(strength(best))
            provs.append(Provenance(source=best.source, method=best.method,
                                    raw_value=best.raw_value,
                                    decision=f"{slot} link from {best.source}"))
    for o in sorted(buckets.get("other", []), key=lambda x: str(x.value)):
        if o.value not in shape["other"]:
            shape["other"].append(o.value)
            confs.append(strength(o))
            provs.append(Provenance(source=o.source, method=o.method,
                                    raw_value=o.raw_value, decision="other link"))

    agg = round(sum(confs) / len(confs), 4) if confs else 0.0
    return Field_(value=shape, confidence=agg, provenance=provs)


def merge(observations: list[Observation]) -> CanonicalProfile:
    live = [o for o in observations if not o.dropped]
    by_field: dict[str, list[Observation]] = defaultdict(list)
    for o in live:
        by_field[o.field].append(o)

    resolved: dict[str, Field_] = {}
    for name in CanonicalProfile.field_names():
        fobs = by_field.get(name, [])
        if name == "links":
            resolved[name] = _resolve_links(fobs)
        elif name in MULTI_VALUED:
            resolved[name] = _resolve_multi(name, fobs)
        else:
            resolved[name] = _resolve_single(name, fobs)

    # candidate_id fallback: if no source supplied one, derive a STABLE id from
    # the strongest identifying key so records remain addressable. It is marked
    # INFERRED in provenance — an identifier, not an invented fact about the person.
    if resolved["candidate_id"].value is None:
        key = None
        if resolved["emails"].value:
            key = f"email:{resolved['emails'].value[0]}"
        elif resolved["phones"].value:
            key = f"phone:{resolved['phones'].value[0]}"
        if key:
            digest = hashlib.sha1(key.encode()).hexdigest()[:12]
            resolved["candidate_id"] = Field_(
                value=f"gen-{digest}", confidence=0.3,
                provenance=[Provenance(source="derived", method=Method.INFERRED,
                                       raw_value=key,
                                       decision="generated from strongest match key (no source id)")],
            )

    # Overall confidence: mean over fields that actually carry a value.
    populated = [f.confidence for f in resolved.values()
                 if f.value not in (None, [], {}) and f.value != _EMPTY_LINKS]
    overall = round(sum(populated) / len(populated), 4) if populated else 0.0

    return CanonicalProfile(overall_confidence=overall, **resolved)


_EMPTY_LINKS = {"linkedin": None, "github": None, "portfolio": None, "other": []}
