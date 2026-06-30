"""Confidence scoring.

A field's confidence answers: "how much should a downstream hiring decision
trust this value?" It is built from three signals:

* **source trust** — how reliable the source is in general
* **method reliability** — how the value was extracted (clean column vs regex)
* **corroboration** — how many independent sources agree

We combine agreeing evidence with a **noisy-OR**:

    confidence = 1 - Π (1 - strength_i)

where ``strength_i = source_trust_i * method_reliability_i``. This has the
properties we want: a single strong source already yields high confidence,
multiple agreeing sources push it higher (but never above 1), and weak sources
contribute little. When there is *conflicting* evidence, the winner's
confidence is discounted by the strength of the dissenting camp — disagreement
should make us less sure, in the spirit of "wrong-but-confident is worse than
empty."
"""

from __future__ import annotations

from .models import Observation
from .sources import SOURCE_TRUST

# How much a dissenting (losing) camp drags down the winner's confidence.
CONFLICT_PENALTY = 0.45
# Below this, a single-value field is emitted as null rather than a low-trust guess.
MIN_CONFIDENCE_TO_EMIT = 0.30


def strength(obs: Observation) -> float:
    return SOURCE_TRUST.get(obs.source, 0.5) * obs.reliability()


def noisy_or(strengths: list[float]) -> float:
    prod = 1.0
    for s in strengths:
        prod *= (1.0 - s)
    return round(1.0 - prod, 4)


def combine(agreeing: list[Observation], dissenting: list[Observation]) -> float:
    base = noisy_or([strength(o) for o in agreeing])
    if dissenting:
        dissent = noisy_or([strength(o) for o in dissenting])
        base *= (1.0 - CONFLICT_PENALTY * dissent)
    return round(base, 4)
