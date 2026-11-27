"""Offline benchmark for the pure-Python Leiden community detection.

Measures, on graphs with a known community structure and on synthetic graphs
of growing size:

* modularity reached by ``crg.communities.leiden`` over ten seeds, next to
  NetworkX Louvain and, when the installed NetworkX ships one, NetworkX Leiden;
* how many returned communities are internally disconnected (Leiden must
  report zero; Louvain gives no such guarantee);
* wall-clock time with the pass limit used by ``GraphStore.detect_communities``
  and without any limit.

All graphs are generated from fixed seeds and nothing touches the network.
Timings depend on the machine; every other number is identical between runs.
Run::

    uv run python benchmarks/run_leiden_benchmark.py
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from pathlib import Path

import networkx as nx

from crg.communities import leiden_partition, modularity
from crg.graph import COMMUNITY_MAX_PASSES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = ROOT / "benchmarks" / "leiden_benchmark_report.json"
REPRODUCIBLE_COMMAND = "uv run python benchmarks/run_leiden_benchmark.py"
SEEDS = range(10)


def _reference_graphs() -> dict[str, tuple[nx.Graph, str | None]]:
    return {
        "karate_club_unweighted": (nx.Graph(nx.karate_club_graph().edges()), None),
        "karate_club_weighted": (nx.karate_club_graph(), "weight"),
        "ring_of_cliques_8x5": (nx.ring_of_cliques(8, 5), None),
        "les_miserables_weighted": (nx.les_miserables_graph(), "weight"),
    }


def _networkx_leiden(graph: nx.Graph, weight: str | None, seed: int):
    """NetworkX's own Leiden, or None where the installed release lacks one."""
    try:
        return nx.community.leiden_communities(
            graph, weight=weight, seed=seed, metric="modularity"
        )
    except (AttributeError, NotImplementedError, TypeError):
        return None


def _disconnected(graph: nx.Graph, communities) -> int:
    return sum(1 for c in communities if not nx.is_connected(graph.subgraph(c)))


def _quality_section() -> dict:
    section: dict = {}
    for name, (graph, weight) in _reference_graphs().items():
        attr = weight or "weight"
        runs = [leiden_partition(graph, seed=s, weight=attr) for s in SEEDS]
        scores = [r.modularity for r in runs]
        best = runs[scores.index(max(scores))]
        louvain = [
            nx.community.modularity(
                graph,
                nx.community.louvain_communities(graph, weight=weight, seed=s),
                weight=weight,
            )
            for s in SEEDS
        ]
        nx_leiden = [_networkx_leiden(graph, weight, s) for s in SEEDS]
        entry = {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "crg_leiden": {
                "modularity_best": round(max(scores), 6),
                "modularity_mean": round(statistics.fmean(scores), 6),
                "modularity_min": round(min(scores), 6),
                "communities_in_best": len(best.communities),
                "passes_median": statistics.median(r.passes for r in runs),
                "disconnected_communities": sum(
                    _disconnected(graph, r.communities) for r in runs
                ),
                "check_vs_networkx_modularity": round(
                    abs(
                        modularity(graph, best.communities, weight=attr)
                        - nx.community.modularity(
                            graph, best.communities, weight=weight
                        )
                    ),
                    12,
                ),
            },
            "networkx_louvain": {
                "modularity_best": round(max(louvain), 6),
                "modularity_mean": round(statistics.fmean(louvain), 6),
            },
        }
        if all(part is not None for part in nx_leiden):
            nx_scores = [
                nx.community.modularity(graph, part, weight=weight)
                for part in nx_leiden
            ]
            entry["networkx_leiden"] = {
                "modularity_best": round(max(nx_scores), 6),
                "modularity_mean": round(statistics.fmean(nx_scores), 6),
            }
        else:
            entry["networkx_leiden"] = None
        section[name] = entry
    return section


def _connectivity_section() -> dict:
    leiden_bad = 0
    louvain_bad = 0
    total_leiden = 0
    total_louvain = 0
    graphs = 20
    for seed in range(graphs):
        graph = nx.powerlaw_cluster_graph(1000, 2, 0.1, seed=seed)
        ours = leiden_partition(graph, seed=seed).communities
        theirs = nx.community.louvain_communities(graph, seed=seed)
        leiden_bad += _disconnected(graph, ours)
        louvain_bad += _disconnected(graph, theirs)
        total_leiden += len(ours)
        total_louvain += len(theirs)
    return {
        "graphs": f"{graphs} powerlaw_cluster_graph(1000, 2, 0.1), seeds 0-{graphs - 1}",
        "crg_leiden": {"communities": total_leiden, "disconnected": leiden_bad},
        "networkx_louvain": {"communities": total_louvain, "disconnected": louvain_bad},
    }


def _timed(graph: nx.Graph, max_passes: int | None) -> dict:
    started = time.perf_counter()
    result = leiden_partition(graph, seed=0, max_passes=max_passes)
    elapsed = time.perf_counter() - started
    return {
        "seconds": round(elapsed, 2),
        "modularity": round(result.modularity, 6),
        "communities": len(result.communities),
        "passes": result.passes,
        "converged": result.converged,
    }


def _scaling_section() -> list[dict]:
    rows = []
    for nodes in (1000, 10000, 50000):
        graph = nx.barabasi_albert_graph(nodes, 3, seed=1)
        row = {
            "graph": f"barabasi_albert_graph({nodes}, 3, seed=1)",
            "nodes": nodes,
            "edges": graph.number_of_edges(),
            "crg_leiden_default_pass_limit": _timed(graph, COMMUNITY_MAX_PASSES),
        }
        if nodes <= 10000:
            row["crg_leiden_until_converged"] = _timed(graph, None)
            started = time.perf_counter()
            louvain = nx.community.louvain_communities(graph, seed=0)
            row["networkx_louvain"] = {
                "seconds": round(time.perf_counter() - started, 2),
                "modularity": round(nx.community.modularity(graph, louvain), 6),
            }
        rows.append(row)
    return rows


def run_benchmark(output_path: Path | None = DEFAULT_REPORT_PATH) -> dict:
    report = {
        "benchmark": "leiden_communities_offline",
        "reproducible_command": REPRODUCIBLE_COMMAND,
        "environment": {
            "python": platform.python_version(),
            "networkx": nx.__version__,
        },
        "default_pass_limit": COMMUNITY_MAX_PASSES,
        "quality": _quality_section(),
        "connectivity": _connectivity_section(),
        "scaling": _scaling_section(),
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    out = Path(argv[1]) if argv and len(argv) > 1 else DEFAULT_REPORT_PATH
    print(json.dumps(run_benchmark(out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
