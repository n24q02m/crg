"""Leiden community detection: quality, connectivity, determinism, tool surface."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest

from crg import communities as communities_module
from crg.communities import _refine_partition, leiden, leiden_partition, modularity
from crg.graph import GraphStore
from crg.parser import EdgeInfo, NodeInfo


def _canonical(communities) -> list[list]:
    return sorted(sorted(c, key=repr) for c in communities)


def _assert_partition(graph, communities) -> None:
    seen = [n for c in communities for n in c]
    assert sorted(seen, key=repr) == sorted(graph.nodes, key=repr)
    assert len(seen) == len(set(seen))
    for community in communities:
        assert community
        assert nx.is_connected(graph.subgraph(community))


# ---------------------------------------------------------------------------
# Quality on graphs with known structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_ring_of_cliques_recovers_every_clique(seed):
    graph = nx.ring_of_cliques(8, 5)
    communities = leiden(graph, seed=seed)
    cliques = [set(range(i * 5, i * 5 + 5)) for i in range(8)]
    assert _canonical(communities) == _canonical(cliques)
    assert modularity(graph, communities) == pytest.approx(0.7841, abs=1e-4)


def test_karate_club_modularity_in_reference_range():
    graph = nx.Graph(nx.karate_club_graph().edges())
    scores = []
    for seed in range(10):
        communities = leiden(graph, seed=seed)
        _assert_partition(graph, communities)
        scores.append(modularity(graph, communities))
    # 0.4198 is the proven optimum for the unweighted karate club graph.
    assert max(scores) == pytest.approx(0.4198, abs=1e-4)
    assert min(scores) >= 0.41
    assert all(s <= 0.41979 + 1e-9 for s in scores)


def test_weighted_karate_club_uses_edge_weights():
    graph = nx.karate_club_graph()
    communities = leiden(graph, seed=0)
    weighted = modularity(graph, communities)
    assert weighted >= 0.44
    assert weighted == pytest.approx(
        nx.community.modularity(graph, communities, weight="weight"), abs=1e-12
    )


@pytest.mark.parametrize("resolution", [0.5, 1.0, 2.0])
def test_modularity_matches_networkx_reference(resolution):
    graph = nx.les_miserables_graph()
    communities = leiden(graph, resolution=resolution, seed=3)
    assert modularity(graph, communities, resolution=resolution) == pytest.approx(
        nx.community.modularity(
            graph, communities, weight="weight", resolution=resolution
        ),
        abs=1e-12,
    )


def test_resolution_controls_granularity():
    graph = nx.les_miserables_graph()
    coarse = leiden(graph, resolution=0.3, seed=0)
    fine = leiden(graph, resolution=3.0, seed=0)
    assert len(coarse) < len(fine)


def test_matches_or_beats_louvain_on_les_miserables():
    graph = nx.les_miserables_graph()
    ours = max(modularity(graph, leiden(graph, seed=s)) for s in range(5))
    louvain = max(
        nx.community.modularity(graph, nx.community.louvain_communities(graph, seed=s))
        for s in range(5)
    )
    assert ours >= louvain - 1e-3


# ---------------------------------------------------------------------------
# Structural guarantees
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(12))
def test_every_community_is_connected_on_random_graphs(seed):
    graph = nx.powerlaw_cluster_graph(300, 2, 0.3, seed=seed)
    rng = random.Random(seed)
    for u, v in graph.edges:
        graph[u][v]["weight"] = rng.choice([1.0, 2.0, 5.0])
    graph.add_nodes_from(["isolated-a", "isolated-b"])
    communities = leiden(graph, seed=seed, resolution=rng.choice([0.5, 1.0, 1.5]))
    _assert_partition(graph, communities)
    assert {"isolated-a"} in communities
    assert {"isolated-b"} in communities


def test_refinement_splits_a_disconnected_community():
    """Refinement never keeps a disconnected group together (unlike Louvain)."""
    graph = nx.disjoint_union(nx.complete_graph(4), nx.complete_graph(4))
    adjacency: list[dict[int, float]] = [{} for _ in graph.nodes]
    for u, v in graph.edges:
        adjacency[u][v] = 1.0
        adjacency[v][u] = 1.0
    degrees = [sum(a.values()) for a in adjacency]
    # Start from one coarse community that spans both cliques.
    refined = _refine_partition(
        adjacency,
        degrees,
        [0] * graph.number_of_nodes(),
        total=sum(degrees),
        resolution=1.0,
        theta=0.01,
        rng=random.Random(0),
    )
    groups: dict[int, set[int]] = {}
    for node, label in enumerate(refined):
        groups.setdefault(label, set()).add(node)
    assert len(groups) >= 2
    assert len(groups) < graph.number_of_nodes()
    for members in groups.values():
        assert members <= set(range(4)) or members <= set(range(4, 8))
        assert nx.is_connected(graph.subgraph(members))


def test_deterministic_for_a_fixed_seed():
    graph = nx.powerlaw_cluster_graph(400, 3, 0.2, seed=11)
    first = leiden(graph, seed=42)
    for _ in range(3):
        assert leiden(graph, seed=42) == first


def test_different_seeds_still_yield_valid_partitions():
    graph = nx.powerlaw_cluster_graph(200, 2, 0.4, seed=5)
    for seed in (1, 2, 3):
        _assert_partition(graph, leiden(graph, seed=seed))


def test_empty_and_singleton_graphs():
    assert leiden(nx.Graph()) == []
    assert modularity(nx.Graph(), []) == 0.0
    single = nx.Graph()
    single.add_node("only")
    assert leiden(single) == [{"only"}]
    assert modularity(single, [{"only"}]) == 0.0
    edgeless = nx.empty_graph(3)
    assert _canonical(leiden(edgeless)) == [[0], [1], [2]]


def test_self_loops_and_parallel_directions_are_accepted():
    graph = nx.DiGraph()
    graph.add_edge("a", "b")
    graph.add_edge("b", "a")
    graph.add_edge("a", "a")
    graph.add_edge("c", "d")
    communities = leiden(graph, seed=0)
    assert _canonical(communities) == [["a", "b"], ["c", "d"]]


def test_passes_repeat_until_modularity_stops_improving():
    graph = nx.powerlaw_cluster_graph(400, 3, 0.2, seed=11)
    full = leiden_partition(graph, seed=1)
    assert full.converged is True
    assert full.passes >= 2
    assert full.modularity == pytest.approx(modularity(graph, full.communities))
    capped = leiden_partition(graph, seed=1, max_passes=1)
    assert capped.passes == 1
    assert capped.converged is False
    assert capped.modularity <= full.modularity + 1e-12
    _assert_partition(graph, capped.communities)
    assert leiden(graph, seed=1, max_passes=1) == capped.communities


def test_edgeless_graph_result_is_trivially_converged():
    result = leiden_partition(nx.empty_graph(2))
    assert result.passes == 0
    assert result.converged is True
    assert result.modularity == 0.0


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"resolution": -1.0}, "resolution"),
        ({"resolution": float("nan")}, "resolution"),
        ({"theta": 0.0}, "theta"),
        ({"max_passes": 0}, "max_passes"),
    ],
)
def test_invalid_parameters_are_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        leiden(nx.path_graph(3), **kwargs)


def test_negative_edge_weight_is_rejected():
    graph = nx.Graph()
    graph.add_edge(0, 1, weight=-1.0)
    with pytest.raises(ValueError, match="weight"):
        leiden(graph)


def test_modularity_rejects_a_partition_missing_nodes():
    with pytest.raises(ValueError, match="cover every node"):
        modularity(nx.path_graph(3), [{0, 1}])


def test_zero_weight_edges_are_ignored():
    graph = nx.Graph()
    graph.add_edge("a", "b", weight=1.0)
    graph.add_edge("c", "d", weight=1.0)
    graph.add_edge("b", "c", weight=0.0)
    communities = leiden(graph, seed=0)
    assert _canonical(communities) == [["a", "b"], ["c", "d"]]
    assert modularity(graph, communities) == pytest.approx(
        nx.community.modularity(graph, communities, weight="weight"), abs=1e-12
    )


def test_refinement_leaves_poorly_connected_nodes_alone():
    # With a high resolution no merge inside this community can raise
    # modularity, so refinement keeps every node in its own sub-community.
    graph = nx.Graph([(0, 1), (1, 2), (1, 3), (2, 3)])
    adjacency: list[dict[int, float]] = [{} for _ in graph.nodes]
    for u, v in graph.edges:
        adjacency[u][v] = 1.0
        adjacency[v][u] = 1.0
    degrees = [sum(a.values()) for a in adjacency]
    refined = _refine_partition(
        adjacency,
        degrees,
        [0, 0, 0, 0],
        total=sum(degrees),
        resolution=1.5,
        theta=0.01,
        rng=random.Random(0),
    )
    assert refined == [0, 1, 2, 3]


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_tiny_edge_weights_still_recover_every_clique(seed):
    # With weights this small every refinement gain is far below theta, so
    # some levels merge nothing and aggregation falls back to the connected
    # pieces of each community.
    graph = nx.ring_of_cliques(8, 5)
    for u, v in graph.edges:
        graph[u][v]["weight"] = 1e-6
    communities = leiden(graph, seed=seed)
    _assert_partition(graph, communities)
    assert len(communities) == 8
    assert modularity(graph, communities) == pytest.approx(0.784091, abs=1e-6)


def test_pass_splits_a_community_of_unreachable_nodes():
    # Two separate edges, 0-1 and 2-3, but local moving reports {0, 2} and
    # {1, 3}: neither group can be refined or split into connected parts that
    # merge anything, so the pass returns every node on its own.
    adjacency: list[dict[int, float]] = [{1: 1.0}, {0: 1.0}, {3: 1.0}, {2: 1.0}]
    degrees = [1.0, 1.0, 1.0, 1.0]
    with patch.object(
        communities_module, "_move_nodes_fast", lambda *args: [0, 1, 0, 1]
    ):
        labels = communities_module._leiden_pass(
            adjacency,
            [0.0] * 4,
            degrees,
            [0, 1, 2, 3],
            4.0,
            1.0,
            0.01,
            random.Random(0),
        )
    assert labels == [0, 1, 2, 3]


def test_draw_falls_back_to_the_last_choice_on_rounding():
    class _TopOfRange(random.Random):
        def random(self) -> float:
            return 1.0

    choice = communities_module._draw([7, 8], [0.0, 0.0], 0.01, _TopOfRange())
    assert choice == 8


# ---------------------------------------------------------------------------
# GraphStore and tool surface
# ---------------------------------------------------------------------------


def _two_module_repo(tmp_path):
    """Two tightly knit modules joined by one call edge."""
    db = tmp_path / ".crg" / "graph.db"
    db.parent.mkdir(parents=True)
    store = GraphStore(db)
    for module in ("auth", "billing"):
        path = f"{module}.py"
        store.upsert_node(NodeInfo("File", path, path, 1, 50, "python"))
        names = [f"{module}_{i}" for i in range(4)]
        for name in names:
            store.upsert_node(NodeInfo("Function", name, path, 1, 2, "python"))
            store.upsert_edge(EdgeInfo("CONTAINS", path, f"{path}::{name}", path, 1))
        for a in names:
            for b in names:
                if a < b:
                    store.upsert_edge(
                        EdgeInfo("CALLS", f"{path}::{a}", f"{path}::{b}", path, 1)
                    )
    store.upsert_edge(
        EdgeInfo("CALLS", "auth.py::auth_0", "billing.py::billing_0", "auth.py", 1)
    )
    # Edges to symbols that are not indexed nodes are left out of the projection.
    store.upsert_edge(EdgeInfo("CALLS", "auth.py::auth_1", "os.getenv", "auth.py", 1))
    store.commit()
    return store, db


def test_graph_store_detects_module_communities(tmp_path):
    store, _db = _two_module_repo(tmp_path)
    try:
        detection = store.detect_communities(seed=0)
    finally:
        store.close()
    assert detection.node_count == 10
    assert detection.edge_count == 21
    assert detection.modularity > 0.3
    assert detection.converged is True
    assert 1 <= detection.passes <= 10
    assert [sorted(c) for c in detection.communities] == [
        sorted(["auth.py", *(f"auth.py::auth_{i}" for i in range(4))]),
        sorted(["billing.py", *(f"billing.py::billing_{i}" for i in range(4))]),
    ]


def test_communities_tool_payload(tmp_path):
    from crg.tools import get_communities

    store, _db = _two_module_repo(tmp_path)
    store.close()
    with patch("crg.tools._COMMUNITY_MEMBER_SAMPLE", 2):
        result = get_communities(repo_root=str(tmp_path), limit=1)
    assert result["status"] == "ok"
    assert result["algorithm"] == "leiden"
    assert result["total_communities"] == 2
    assert result["truncated"] is True
    assert len(result["communities"]) == 1
    first = result["communities"][0]
    assert first["size"] == 5
    # Members are listed by weighted degree: auth_0 also calls into billing.
    assert first["members"] == ["auth.py::auth_0", "auth.py"]
    assert first["members_truncated"] is True
    assert first["files"] == ["auth.py"]
    assert "modularity" in result["summary"]
    assert result["converged"] is True
    assert result["passes"] >= 1


def test_communities_tool_lists_files_relative_to_repo_root(tmp_path):
    from crg.tools import get_communities

    db = tmp_path / ".crg" / "graph.db"
    db.parent.mkdir(parents=True)
    store = GraphStore(db)
    inside = str(tmp_path / "pkg" / "auth.py")
    outside = str(tmp_path.parent / "vendored.py")
    for path in (inside, outside):
        store.upsert_node(NodeInfo("Function", "f", path, 1, 2, "python"))
    store.upsert_edge(EdgeInfo("CALLS", f"{inside}::f", f"{outside}::f", inside, 1))
    store.commit()
    store.close()
    result = get_communities(repo_root=str(tmp_path))
    assert result["status"] == "ok"
    (community,) = result["communities"]
    assert sorted(community["files"]) == sorted([str(Path("pkg") / "auth.py"), outside])


def test_detect_communities_caps_passes(tmp_path):
    store, _db = _two_module_repo(tmp_path)
    try:
        detection = store.detect_communities(seed=0, max_passes=1)
    finally:
        store.close()
    assert detection.passes == 1
    assert detection.converged is False


def test_communities_tool_rejects_bad_resolution(tmp_path):
    from crg.tools import get_communities

    store, _db = _two_module_repo(tmp_path)
    store.close()
    result = get_communities(repo_root=str(tmp_path), resolution=-2.0)
    assert result["status"] == "error"
    assert "resolution" in result["error"]


def test_communities_tool_on_empty_graph(tmp_path):
    from crg.tools import get_communities

    db = tmp_path / ".crg" / "graph.db"
    db.parent.mkdir(parents=True)
    GraphStore(db).close()
    result = get_communities(repo_root=str(tmp_path))
    assert result["status"] == "ok"
    assert result["communities"] == []
    assert result["modularity"] == 0.0


def test_query_tool_dispatches_communities():
    from crg.server import query

    payload = {"status": "ok", "communities": []}
    with patch("crg.server.get_communities", return_value=payload) as mock_tool:
        assert (
            query(action="communities", resolution=1.5, seed=7, limit=3, repo_root="/r")
            == payload
        )
    mock_tool.assert_called_once_with(
        resolution=1.5, seed=7, limit=3, repo_root="/r", as_of=""
    )
    unknown = query(action="communitys")
    assert "communities" in unknown["valid_actions"]
    assert "Did you mean 'communities'" in unknown["error"]


def test_cli_query_communities(capsys):
    from crg.cli import main

    payload = {"status": "ok", "communities": []}
    with (
        patch("crg.tools.get_communities", return_value=payload) as mock_tool,
        patch.object(
            sys,
            "argv",
            [
                "crg",
                "query",
                "communities",
                "--resolution",
                "0.8",
                "--seed",
                "3",
                "--limit",
                "5",
                "--repo-root",
                "/tmp/repo",
            ],
        ),
    ):
        assert main() == 0
    mock_tool.assert_called_once_with(
        resolution=0.8, seed=3, limit=5, repo_root="/tmp/repo", as_of=""
    )
    assert json.loads(capsys.readouterr().out) == payload
