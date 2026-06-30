"""Skill canonicalization.

Maps surface forms ("JS", "react.js", "node") to canonical skill names
("JavaScript", "React", "Node.js").

Two-tier lookup, fast path first:

1. **Exact alias map** — an O(1) dict lookup on the lowercased token. Handles
   the bulk of real traffic instantly and *deterministically*.
2. **Fuzzy fallback** — only if the exact lookup misses do we run rapidfuzz
   (C-backed, far faster than pure-Python edit distance) against the set of
   canonical names. We require a high score threshold; below it we return the
   cleaned original rather than forcing a wrong match. Confidently mapping
   "Java" to "JavaScript" would be exactly the wrong-but-confident failure the
   brief warns against, so the bar is set high and ties stay unmatched.
"""

from __future__ import annotations

from rapidfuzz import fuzz, process

# Canonical name -> list of known aliases (all compared lowercased).
_CANON: dict[str, list[str]] = {
    "JavaScript": ["js", "javascript", "java script", "ecmascript"],
    "TypeScript": ["ts", "typescript", "type script"],
    "Python": ["python", "py", "python3"],
    "Java": ["java"],
    "React": ["react", "react.js", "reactjs"],
    "Node.js": ["node", "node.js", "nodejs"],
    "PostgreSQL": ["postgres", "postgresql", "psql"],
    "Kubernetes": ["k8s", "kubernetes", "kube"],
    "Docker": ["docker"],
    "AWS": ["aws", "amazon web services"],
    "Go": ["go", "golang"],
    "C++": ["c++", "cpp", "cplusplus"],
    "SQL": ["sql"],
    "Machine Learning": ["ml", "machine learning"],
    "REST APIs": ["rest", "rest api", "rest apis", "restful"],
    "GraphQL": ["graphql", "graph ql"],
}

# Flattened alias -> canonical, built once at import.
_ALIAS_TO_CANON: dict[str, str] = {
    alias: canon for canon, aliases in _CANON.items() for alias in aliases
}
_CANON_NAMES = list(_CANON.keys())

# Below this rapidfuzz score we refuse to map — better unmatched than wrong.
_FUZZY_THRESHOLD = 88.0


def canonicalize_skill(raw: str) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    key = text.lower()
    if key in _ALIAS_TO_CANON:          # fast, exact, deterministic
        return _ALIAS_TO_CANON[key]

    # Fuzzy fallback against canonical names only.
    match = process.extractOne(text, _CANON_NAMES, scorer=fuzz.ratio)
    if match and match[1] >= _FUZZY_THRESHOLD:
        return match[0]

    # Unknown skill: keep it, title-cased, rather than discard or mis-map.
    return text if not text.islower() else text.title()


def canonicalize_skills(raws: list[str]) -> list[str]:
    """Canonicalize a list and dedupe, preserving first-seen order
    (determinism: same input -> same output ordering)."""
    seen: dict[str, None] = {}
    for r in raws:
        c = canonicalize_skill(r)
        if c and c not in seen:
            seen[c] = None
    return list(seen.keys())
