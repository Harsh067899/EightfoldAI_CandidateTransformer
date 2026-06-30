"""Validation stage.

After projection we validate the result against the *requested* schema: the
types and required-ness the config asked for. This keeps a clean separation —
the internal canonical record is validated by its pydantic model; the projected
output is validated here against whatever the caller declared. A mismatch is
surfaced explicitly rather than shipped silently.
"""

from __future__ import annotations

from typing import Any

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "string[]": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    "object": lambda v: isinstance(v, dict),
    "object[]": lambda v: isinstance(v, list) and all(isinstance(x, dict) for x in v),
}


def validate(output: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems (empty == valid)."""
    problems: list[str] = []
    fields = config.get("fields") or []
    for spec in fields:
        key = spec["path"]
        declared = spec.get("type")
        required = spec.get("required", False)
        present = key in output and output[key] is not None

        if required and not present:
            problems.append(f"required field '{key}' is missing/null")
            continue
        if present and declared and declared in _TYPE_CHECKS:
            if not _TYPE_CHECKS[declared](output[key]):
                problems.append(
                    f"field '{key}' expected {declared}, got {type(output[key]).__name__}"
                )
    return problems
