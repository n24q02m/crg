"""Call-graph taint source-to-sink path analysis (CRG-21)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import networkx as nx

if TYPE_CHECKING:
    from .graph import GraphStore

_SOURCE_PATTERNS = re.compile(
    r"(?:@app\.|@router\.|@mcp\.tool|\brequest\b|\breq\b|\bsys\.argv\b|"
    r"\bsys\.stdin\b|\bos\.environ\b|\binput\s*\(|\bread_body\b)",
    re.IGNORECASE,
)
_SOURCE_NAME_RE = re.compile(
    r"(?:^|[._])(handle|handler|route|endpoint|view|webhook|mcp_|cli_|main|parse_input|ingest)",
    re.IGNORECASE,
)
_SINK_PATTERNS = re.compile(
    r"(?:\bcursor\.execute\b|\.execute\s*\(|\bexecutemany\s*\(|"
    r"\bsubprocess\.\w+|\bos\.system\s*\(|\bos\.popen\s*\(|\beval\s*\(|"
    r"\bexec\s*\(|\bpickle\.loads?\s*\(|\byaml\.load\s*\(|"
    r"innerHTML|dangerouslySetInnerHTML)",
    re.IGNORECASE,
)
_SINK_NAME_RE = re.compile(
    r"(?:^|[._])(run_sql|execute_sql|run_shell|exec_cmd|write_file|eval_expr|sink)",
    re.IGNORECASE,
)
_TAINT_CWES = ("cwe-78", "cwe-89", "cwe-94", "cwe-22", "cwe-79", "cwe-502")


def _matches_filter(qn: str, name: str, needle: str) -> bool:
    low = needle.lower()
    return low in qn.lower() or low in name.lower()


def _parse_sec_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
        if isinstance(loaded, list):
            return [str(x) for x in loaded]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _is_source_node(qn: str, name: str, params: str, src: str) -> bool:
    if _SOURCE_NAME_RE.search(name):
        return True
    if _SOURCE_PATTERNS.search(src) or _SOURCE_PATTERNS.search(params):
        return True
    return "::" in qn and _SOURCE_NAME_RE.search(qn.rsplit("::", 1)[-1]) is not None


def _is_sink_node(qn: str, name: str, src: str, sec_tags: list[str]) -> bool:
    if any(any(cwe in tag.lower() for cwe in _TAINT_CWES) for tag in sec_tags):
        return True
    if _SINK_NAME_RE.search(name):
        return True
    return _SINK_PATTERNS.search(src) is not None


def find_taint_paths(
    store: GraphStore,
    *,
    max_depth: int = 5,
    source: str | None = None,
    sink: str | None = None,
    limit: int = 50,
    repo: str = "",
) -> dict[str, Any]:
    """Identify reachable call paths from input sources to dangerous sinks."""
    sql = (
        "SELECT qualified_name, name, file_path, kind, params, source_text, "
        "security_tags FROM nodes WHERE valid_to_sha IS NULL "
        "AND kind IN ('Function', 'Class', 'Method', 'Test')"
    )
    sql_params: tuple[Any, ...] = ()
    if repo:
        sql += " AND repo_id = ?"
        sql_params = (repo,)

    sources: list[str] = []
    sinks: list[str] = []
    node_meta: dict[str, dict[str, Any]] = {}

    for row in store._conn.execute(sql, sql_params):
        qn = str(row["qualified_name"])
        name = str(row["name"] or qn.rsplit("::", 1)[-1])
        params = str(row["params"] or "")
        src_text = str(row["source_text"] or "")
        sec_tags = _parse_sec_tags(row["security_tags"])
        node_meta[qn] = {
            "qualified_name": qn,
            "name": name,
            "file_path": str(row["file_path"]),
            "security_tags": sec_tags,
        }
        is_src = (
            _matches_filter(qn, name, source)
            if source
            else _is_source_node(qn, name, params, src_text)
        )
        is_snk = (
            _matches_filter(qn, name, sink)
            if sink
            else _is_sink_node(qn, name, src_text, sec_tags)
        )
        if is_src:
            sources.append(qn)
        if is_snk:
            sinks.append(qn)

    nxg = store._build_networkx_graph()
    call_graph = nx.DiGraph()
    for u, v, data in nxg.edges(data=True):
        kinds = data.get("kinds")
        if kinds and "CALLS" in kinds:
            call_graph.add_edge(u, v, confidence=float(data.get("confidence", 1.0)))
        elif data.get("kind") == "CALLS":
            call_graph.add_edge(u, v, confidence=float(data.get("confidence", 1.0)))

    paths: list[dict[str, Any]] = []
    sink_set = set(sinks)
    for src_qn in sources:
        if len(paths) >= limit:
            break
        if src_qn in sink_set:
            paths.append(
                {
                    "source": src_qn,
                    "sink": src_qn,
                    "hops": 0,
                    "confidence": 1.0,
                    "path": [src_qn],
                    "sink_tags": node_meta[src_qn]["security_tags"],
                }
            )
            continue
        if src_qn not in call_graph:
            continue
        lengths = nx.single_source_shortest_path_length(
            call_graph, src_qn, cutoff=max(1, max_depth)
        )
        for snk_qn in sinks:
            if len(paths) >= limit:
                break
            if snk_qn not in lengths:
                continue
            shortest = nx.shortest_path(call_graph, src_qn, snk_qn)
            edge_confs = [
                float(call_graph[shortest[i]][shortest[i + 1]].get("confidence", 1.0))
                for i in range(len(shortest) - 1)
            ]
            path_conf = min(edge_confs) if edge_confs else 1.0
            paths.append(
                {
                    "source": src_qn,
                    "sink": snk_qn,
                    "hops": len(shortest) - 1,
                    "confidence": round(path_conf, 4),
                    "path": shortest,
                    "sink_tags": node_meta.get(snk_qn, {}).get("security_tags", []),
                }
            )

    paths.sort(key=lambda p: (p["hops"], -p["confidence"], p["source"], p["sink"]))
    return {
        "status": "ok",
        "sources_count": len(sources),
        "sinks_count": len(sinks),
        "paths_count": len(paths),
        "max_depth": max_depth,
        "paths": paths[:limit],
    }
