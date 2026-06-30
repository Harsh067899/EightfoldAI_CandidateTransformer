"""Source adapter base + safety wrapper.

Every adapter implements ``extract(path) -> list[Observation]``. The contract is
narrow on purpose: an adapter's only job is to turn one raw source into typed
observations. It does not normalize, merge, or score — those are later stages.

``safe_extract`` wraps any adapter so that a malformed or garbage source can
never crash the pipeline. It catches everything, logs a warning, and returns an
empty list. This is the engine-level guarantee behind the brief's "robust"
constraint: a bad source degrades to *no contribution*, never to a failure and
never to an invented value.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from ..models import Observation

log = logging.getLogger("canonical.sources")


class SourceAdapter(Protocol):
    name: str

    def extract(self, path: Path) -> list[Observation]:
        ...


def safe_extract(adapter: SourceAdapter, path: Path) -> list[Observation]:
    try:
        if not Path(path).exists():
            log.warning("source %s: file not found at %s — skipping", adapter.name, path)
            return []
        obs = adapter.extract(Path(path))
        log.info("source %s: %d observations", adapter.name, len(obs))
        return obs
    except Exception as exc:  # noqa: BLE001 — deliberate: no source may crash the run
        log.warning("source %s: failed to parse (%s) — skipping, no values taken", adapter.name, exc)
        return []
