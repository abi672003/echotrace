from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Family:
    medoid: int
    members: list[int]


@dataclass(frozen=True)
class Neighbor:
    index: int
    similarity: float


def cosine_matrix(vectors: np.ndarray) -> np.ndarray:
    """`vectors`: (n, d) L2-normalised rows. Returns the (n, n) cosine similarity matrix."""
    return vectors @ vectors.T


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def connected_components(similarity: np.ndarray, sim_edge: float) -> list[list[int]]:
    """Union-find over edges where `similarity >= sim_edge` (§4.4 step 1-2)."""
    n = similarity.shape[0]
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if similarity[i, j] >= sim_edge:
                uf.union(i, j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    return list(groups.values())


def find_medoid(indices: list[int], similarity: np.ndarray) -> int:
    """The member of `indices` with the highest mean similarity to the others."""
    best_index = indices[0]
    best_score = -1.0
    for i in indices:
        others = [j for j in indices if j != i]
        score = 1.0 if not others else float(np.mean([similarity[i, j] for j in others]))
        if score > best_score:
            best_score = score
            best_index = i
    return best_index


def apply_chaining_guard(
    indices: list[int], similarity: np.ndarray, sim_member: float
) -> Family:
    """Picks the medoid, then drops members whose similarity to it falls below
    `sim_member` back to singletons (§4.4 step 3)."""
    medoid = find_medoid(indices, similarity)
    kept = [i for i in indices if i == medoid or similarity[medoid, i] >= sim_member]
    return Family(medoid=medoid, members=kept)


def build_families(
    vectors: np.ndarray,
    sim_edge: float,
    sim_member: float,
    min_family: int,
) -> tuple[list[Family], np.ndarray]:
    """Cluster `vectors` per §4.4. Returns `(families, similarity_matrix)`; singletons
    and families under `min_family` are dropped entirely (not stored as clusters)."""
    similarity = cosine_matrix(vectors)
    families: list[Family] = []
    for component in connected_components(similarity, sim_edge):
        if len(component) < 2:
            continue
        family = apply_chaining_guard(component, similarity, sim_member)
        if len(family.members) >= min_family:
            families.append(family)
    return families, similarity


def nearest(query: np.ndarray, vectors: np.ndarray, k: int, min_sim: float) -> list[Neighbor]:
    """Cosine similarity of L2-normalised `query` against every row of L2-normalised
    `vectors`, returning up to `k` neighbours with `similarity >= min_sim`, best first."""
    if vectors.shape[0] == 0:
        return []
    sims = vectors @ query
    order = np.argsort(-sims)
    results: list[Neighbor] = []
    for i in order:
        if sims[i] < min_sim:
            break
        results.append(Neighbor(index=int(i), similarity=float(sims[i])))
        if len(results) >= k:
            break
    return results
