"""Match stage — entity resolution.

Groups observations that describe the same person across sources. For a single
candidate this is trivial, but the brief requires scaling to thousands, where a
naive all-pairs comparison is O(n^2) and the real bottleneck.

**Optimization that matters: blocking.** Instead of comparing every record to
every other, we bucket records by cheap *blocking keys* (normalized email,
normalized phone, lowercased name) and only resolve within a bucket. Records
sharing any strong key are unioned via a disjoint-set (union-find) structure.
This turns the dominant cost from O(n^2) into roughly O(n) for realistic data,
and it is the one place aggressive optimization is justified — everything else
(normalizing one value, scoring one field) is cheap and left readable.
"""

from __future__ import annotations

from collections import defaultdict

from .models import Observation


class _DSU:
    """Disjoint-set / union-find with path compression."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:       # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _record_keys(record_id: str, obs: list[Observation]) -> list[str]:
    """Strong blocking keys for a record: emails and phones (already normalized)."""
    keys: list[str] = []
    for o in obs:
        if o.dropped:
            continue
        if o.field == "emails":
            keys.append(f"email:{o.value}")
        elif o.field == "phones":
            keys.append(f"phone:{o.value}")
    return keys


def group_records(records: dict[str, list[Observation]]) -> list[list[str]]:
    """Given {record_id: observations}, return clusters of record_ids that refer
    to the same person. Records are linked when they share a strong key."""
    dsu = _DSU()
    key_to_record: dict[str, str] = {}

    for rid, obs in records.items():
        dsu.find(rid)  # ensure present
        for key in _record_keys(rid, obs):
            if key in key_to_record:
                dsu.union(key_to_record[key], rid)
            else:
                key_to_record[key] = rid

    clusters: dict[str, list[str]] = defaultdict(list)
    for rid in records:
        clusters[dsu.find(rid)].append(rid)
    return [sorted(c) for c in clusters.values()]
