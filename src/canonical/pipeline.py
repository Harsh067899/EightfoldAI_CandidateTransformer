"""Pipeline orchestration.

Wires the stages in order:

    detect -> extract -> normalize -> match -> merge -> project -> validate

``run`` takes a set of named sources (field -> file path), an optional output
config, and returns the projected profile(s) plus validation results. Multiple
records are matched/clustered so the same engine handles one candidate or
thousands.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .match import group_records
from .merge import merge
from .models import Observation
from .normalize_stage import normalize_all
from .project import project
from .sources import ADAPTERS, safe_extract
from .validate import validate

log = logging.getLogger("canonical.pipeline")


def extract_sources(sources: dict[str, str | Path]) -> list[Observation]:
    """Run every named source through its adapter (crash-safe) and collect
    normalized observations. ``sources`` maps adapter name -> file path."""
    raw: list[Observation] = []
    for name, path in sources.items():
        adapter = ADAPTERS.get(name)
        if adapter is None:
            log.warning("no adapter registered for source '%s' — skipping", name)
            continue
        raw.extend(safe_extract(adapter, Path(path)))
    return normalize_all(raw)


def run(
    sources: dict[str, str | Path],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single-candidate convenience path: all sources describe one person."""
    observations = extract_sources(sources)
    profile = merge(observations)
    cfg = config or {}
    output = project(profile, cfg)
    problems = validate(output, cfg)
    return {"profile": output, "valid": not problems, "problems": problems,
            "internal": profile}


def run_batch(
    record_sources: dict[str, dict[str, str | Path]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Scale path: ``record_sources`` maps record_id -> {source_name: path}.

    Each record is extracted independently, then matching clusters records that
    refer to the same person before merging. Demonstrates the engine scaling
    past a single candidate.
    """
    per_record: dict[str, list[Observation]] = {
        rid: extract_sources(srcs) for rid, srcs in record_sources.items()
    }
    clusters = group_records(per_record)

    results = []
    cfg = config or {}
    for cluster in clusters:
        obs: list[Observation] = []
        for rid in cluster:
            obs.extend(per_record[rid])
        profile = merge(obs)
        output = project(profile, cfg)
        problems = validate(output, cfg)
        results.append({"cluster": cluster, "profile": output,
                        "valid": not problems, "problems": problems})
    return results
