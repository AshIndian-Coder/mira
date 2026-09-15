"""Duplicate group detection via connected components.

Materials are nodes; accepted similarity edges (confidence >= threshold)
are weighted edges. Each connected component is a candidate duplicate
group -> one CNMC candidate.

Union-Find (disjoint set) is used: O(n alpha(n)), no external dependency.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.utils.constants import HIGH_CONFIDENCE_THRESHOLD


class _UnionFind:
    def __init__(self) -> None:
        self._parent: Dict[int, int] = {}
        self._rank: Dict[int, int] = {}

    def add(self, node: int) -> None:
        node = int(node)
        if node not in self._parent:
            self._parent[node] = node
            self._rank[node] = 0

    def find(self, node: int) -> int:
        self.add(node)
        root = node
        while self._parent[root] != root:
            root = self._parent[root]
        # path compression
        while self._parent[node] != root:
            self._parent[node], node = root, self._parent[node]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def groups(self) -> Dict[int, List[int]]:
        result: Dict[int, List[int]] = {}
        for node in self._parent:
            result.setdefault(self.find(node), []).append(node)
        return result


def find_duplicate_clusters(
    pairs: Iterable[Sequence],
    threshold: float = HIGH_CONFIDENCE_THRESHOLD,
) -> List[List[int]]:
    """Group material ids into duplicate clusters.

    ``pairs`` is an iterable of (id_a, id_b) or (id_a, id_b, score).
    Edges below ``threshold`` are ignored.
    Returns a list of clusters (each a sorted list of ids, >1 member only).
    """
    uf = _UnionFind()
    for pair in pairs:
        id_a, id_b = int(pair[0]), int(pair[1])
        score = float(pair[2]) if len(pair) > 2 else 1.0
        if score < threshold:
            continue
        uf.add(id_a)
        uf.add(id_b)
        uf.union(id_a, id_b)

    clusters = sorted(
        (sorted(nodes) for nodes in uf.groups().values() if len(nodes) > 1),
        key=lambda nodes: nodes[0],
    )
    return clusters


def cluster_pairs(
    pairs: Sequence[Tuple[int, int, float]],
    high_confidence_threshold: float = HIGH_CONFIDENCE_THRESHOLD,
    review_threshold: float = 0.45,
) -> Dict[str, List[List[int]]]:
    """Cluster at both confidence bands.

    Returns:
        {
          "high_confidence": [...],  # exact-duplicate candidates (auto-CNMC ready)
          "review": [...],           # near-duplicate candidates (human check)
        }
    """
    high = find_duplicate_clusters(pairs, threshold=high_confidence_threshold)
    review = find_duplicate_clusters(pairs, threshold=review_threshold)
    return {"high_confidence": high, "review": review}


def describe_cluster(member_ids: Sequence[int], materials_by_id: Dict[int, Any]) -> Dict[str, Any]:
    """Summarize a cluster: representative member, category, codes."""
    materials = [materials_by_id[mid] for mid in member_ids if mid in materials_by_id]
    if not materials:
        return {"member_ids": list(member_ids), "representative": None, "category": None}

    # Representative: longest cleaned description (most informative).
    representative = max(
        materials,
        key=lambda m: len((m.get("cleaned_description") or m.get("description") or "")),
    )
    categories = [m.get("category") for m in materials if m.get("category")]
    from collections import Counter

    category = Counter(categories).most_common(1)[0][0] if categories else None
    return {
        "member_ids": sorted(int(mid) for mid in member_ids),
        "representative": representative,
        "category": category,
        "cpse_ids": sorted({m.get("cpse_id") for m in materials if m.get("cpse_id") is not None}),
    }

