import math

import numpy as np

from app.services.similarity import build_families, cosine_matrix, nearest

SIM_EDGE = 0.86
SIM_MEMBER = 0.82
MIN_FAMILY = 3


def _unit_vector_at_degrees(angle_degrees: float) -> np.ndarray:
    radians = math.radians(angle_degrees)
    return np.array([math.cos(radians), math.sin(radians)], dtype=np.float64)


def test_cosine_matrix_identical_vectors_is_one() -> None:
    vectors = np.array([[1.0, 0.0], [1.0, 0.0]])
    sim = cosine_matrix(vectors)
    assert np.allclose(sim, 1.0)


def test_cosine_matrix_orthogonal_vectors_is_zero() -> None:
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]])
    sim = cosine_matrix(vectors)
    assert math.isclose(sim[0, 1], 0.0, abs_tol=1e-9)


def test_build_families_groups_a_tight_cluster_and_drops_a_chained_outlier() -> None:
    # A dense cluster of 5 near-identical vectors, a bridge member just inside SIM_EDGE
    # of the cluster, and a lone outlier connected only through the bridge. The outlier's
    # similarity to the eventual medoid (a core cluster member) falls well under
    # SIM_MEMBER even though it's still in the same connected component as the bridge.
    angles = [0.0, 0.2, -0.2, 0.4, -0.4, 29.0, 58.0]
    labels = ["A", "B", "C", "D", "E", "bridge", "outlier"]
    vectors = np.stack([_unit_vector_at_degrees(a) for a in angles])

    families, similarity = build_families(vectors, SIM_EDGE, SIM_MEMBER, MIN_FAMILY)

    assert len(families) == 1
    family = families[0]

    outlier_index = labels.index("outlier")
    bridge_index = labels.index("bridge")
    core_indices = {labels.index(l) for l in ("A", "B", "C", "D", "E")}

    assert outlier_index not in family.members
    assert bridge_index in family.members
    assert core_indices.issubset(set(family.members))
    assert len(family.members) == 6

    # the medoid must be a core cluster member, not the bridge or the dropped outlier
    assert family.medoid in core_indices

    # sanity: the outlier really was connected to the component before the guard ran
    # (it has an edge to the bridge), proving it was dropped by the chaining guard,
    # not simply never clustered in the first place.
    assert similarity[bridge_index, outlier_index] >= SIM_EDGE
    assert similarity[family.medoid, outlier_index] < SIM_MEMBER


def test_build_families_drops_families_under_min_family() -> None:
    # Two vectors tightly clustered (edge exists) but below MIN_FAMILY=3.
    vectors = np.stack([_unit_vector_at_degrees(a) for a in (0.0, 1.0)])
    families, _ = build_families(vectors, SIM_EDGE, SIM_MEMBER, MIN_FAMILY)
    assert families == []


def test_build_families_two_unrelated_clusters_stay_separate() -> None:
    angles = [0.0, 0.5, -0.5, 90.0, 90.5, 89.5]
    vectors = np.stack([_unit_vector_at_degrees(a) for a in angles])
    families, _ = build_families(vectors, SIM_EDGE, SIM_MEMBER, MIN_FAMILY)
    assert len(families) == 2
    all_members = {m for family in families for m in family.members}
    assert all_members == {0, 1, 2, 3, 4, 5}


def test_nearest_returns_best_first_and_respects_min_sim_and_k() -> None:
    query = _unit_vector_at_degrees(0.0)
    angles = [1.0, 5.0, 10.0, 45.0, 89.0]
    vectors = np.stack([_unit_vector_at_degrees(a) for a in angles])

    results = nearest(query, vectors, k=2, min_sim=0.5)

    assert [r.index for r in results] == [0, 1]  # closest (1deg) then next (5deg)
    assert results[0].similarity > results[1].similarity


def test_nearest_returns_empty_when_nothing_meets_min_sim() -> None:
    query = _unit_vector_at_degrees(0.0)
    vectors = np.stack([_unit_vector_at_degrees(a) for a in (90.0, 95.0)])
    assert nearest(query, vectors, k=5, min_sim=0.82) == []
