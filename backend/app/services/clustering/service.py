from typing import Any


def cluster_approved_pairs(
    approved_candidates: list[dict[str, Any]],
) -> dict[int, list[int]]:
    """
    Group approved material candidate pairs into clusters using Union-Find.
    
    Returns a mapping of root_id -> list of material IDs in that cluster.
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        if parent.setdefault(x, x) != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    for c in approved_candidates:
        union(c["source_material_id"], c["target_material_id"])

    clusters: dict[int, list[int]] = {}
    all_ids = {c["source_material_id"] for c in approved_candidates} | {
        c["target_material_id"] for c in approved_candidates
    }
    for mid in all_ids:
        root = find(mid)
        clusters.setdefault(root, []).append(mid)

    return clusters
