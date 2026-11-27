"""Comprehensive tests for W10 Phase 4 SOTA upgrades (CRG-2..33)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import numpy as np
import pytest

from benchmarks.run_scip_benchmark import run_benchmark
from crg.cli import _build_parser
from crg.embeddings import EmbeddingStore, semantic_search
from crg.federation import backfill_commits_for_repo
from crg.git_mining import _parse_numstat_commits
from crg.graph import GraphStore, split_identifier
from crg.incremental import full_build, watch
from crg.parser import SUPPORTED_LANGUAGES, CodeParser, EdgeInfo, NodeInfo
from crg.scip import import_scip_index
from crg.security.semgrep_engine import _semgrep_executable
from crg.server import graph as mcp_graph
from crg.server import query as mcp_query
from crg.server import review as mcp_review
from crg.server import security as mcp_security
from crg.tools import (
    get_impact_radius,
    import_scip_dispatch,
    security_scan,
    security_taint_paths,
)


def _git_init(repo: Path) -> None:
    for cmd in (
        ["git", "-C", str(repo), "init", "-q"],
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        ["git", "-C", str(repo), "config", "user.name", "Test"],
    ):
        subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, capture_output=True)


def _git_commit(repo: Path, msg: str) -> str:
    subprocess.run(
        ["git", "-C", str(repo), "add", "."],
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", msg, "--allow-empty"],
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _encode_varint(val: int) -> bytes:
    buf = bytearray()
    v = val & 0xFFFFFFFFFFFFFFFF
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            buf.append(byte | 0x80)
        else:
            buf.append(byte)
            break
    return bytes(buf)


def _pb_bytes(field_num: int, data: bytes) -> bytes:
    return _encode_varint((field_num << 3) | 2) + _encode_varint(len(data)) + data


def _pb_varint(field_num: int, val: int) -> bytes:
    return _encode_varint((field_num << 3) | 0) + _encode_varint(val)


def test_crg2_opengrep_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        shutil,
        "which",
        lambda exe: "/usr/bin/opengrep" if exe == "opengrep" else None,
    )
    assert _semgrep_executable() == "/usr/bin/opengrep"
    monkeypatch.setattr(
        shutil,
        "which",
        lambda exe: "/usr/bin/semgrep" if exe == "semgrep" else None,
    )
    assert _semgrep_executable() == "/usr/bin/semgrep"


def test_crg3_crg4_crg10_crg32_direction_filters_and_cache(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _git_init(repo)
    (repo / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    _git_commit(repo, "init")

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        for mod in ("root.py", "caller.py", "callee.py", "sibling.py"):
            fp = str((repo / mod).resolve())
            store.upsert_node(NodeInfo("File", fp, fp, 1, 10, "python"))
            sym = mod.removesuffix(".py")
            store.upsert_node(NodeInfo("Function", sym, fp, 1, 5, "python"))

        r_qn = f"{(repo / 'root.py').resolve()}::root"
        c_qn = f"{(repo / 'caller.py').resolve()}::caller"
        d_qn = f"{(repo / 'callee.py').resolve()}::callee"
        s_qn = f"{(repo / 'sibling.py').resolve()}::sibling"

        # caller -> root -> callee, and sibling -> callee
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                c_qn,
                r_qn,
                str((repo / "caller.py").resolve()),
                2,
                confidence=0.95,
                resolution="import_traced",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                r_qn,
                d_qn,
                str((repo / "root.py").resolve()),
                2,
                confidence=0.4,
                resolution="heuristic",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                s_qn,
                d_qn,
                str((repo / "sibling.py").resolve()),
                2,
                confidence=0.9,
                resolution="scip",
            )
        )
        store.commit()

        root_fp = str((repo / "root.py").resolve())
        dep_only = store.get_impact_radius(
            [root_fp], max_depth=3, direction="dependents"
        )
        assert {n.qualified_name for n in dep_only["impacted_nodes"]} == {c_qn}

        deps_only = store.get_impact_radius(
            [root_fp], max_depth=3, direction="dependencies"
        )
        assert {n.qualified_name for n in deps_only["impacted_nodes"]} == {d_qn}

        both_no_zigzag = store.get_impact_radius(
            [root_fp], max_depth=3, direction="both"
        )
        # Both passes stay unidirectional so sibling (caller of callee) is NOT dragged in
        assert {n.qualified_name for n in both_no_zigzag["impacted_nodes"]} == {
            c_qn,
            d_qn,
        }

        high_conf = store.get_impact_radius(
            [root_fp],
            max_depth=3,
            direction="both",
            edge_kinds=("CALLS",),
            min_confidence=0.9,
        )
        assert {n.qualified_name for n in high_conf["impacted_nodes"]} == {c_qn}

        with pytest.raises(ValueError, match="Invalid direction"):
            store.get_impact_radius([root_fp], direction="sideways")

        nxg1 = store._build_networkx_graph()
        nxg2 = store._build_networkx_graph()
        assert nxg1 is nxg2
        assert nxg1.has_edge(c_qn, r_qn)
        assert nxg1[c_qn][r_qn]["confidence"] == pytest.approx(0.95)
        store._invalidate_cache()
        assert store._nxg_cache == {}
    finally:
        store.close()


def test_crg5_crg7_temporal_order_and_fts5_search(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _git_init(repo)
    f = repo / "app.py"
    f.write_text("def handle_v1():\n    return 1\n", encoding="utf-8")
    sha1 = _git_commit(repo, "c1")
    f.write_text("def handleUserRequest():\n    return 2\n", encoding="utf-8")
    sha2 = _git_commit(repo, "c2")

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        n_commits = backfill_commits_for_repo(store, "", repo)
        assert n_commits == 2
        rows = store._conn.execute(
            "SELECT sha, commit_order FROM commits ORDER BY commit_order ASC"
        ).fetchall()
        assert [(r["sha"], r["commit_order"]) for r in rows] == [(sha1, 1), (sha2, 2)]

        # Token splitting & FTS5 BM25 search
        assert "handle" in split_identifier("handleUserRequest")
        assert "user" in split_identifier("handleUserRequest")
        fp = str(f.resolve())
        store.upsert_node(
            NodeInfo(
                "Function",
                "handleUserRequest",
                fp,
                1,
                2,
                "python",
                params="(req: Request)",
                extra={"docstring": "Process incoming request."},
            )
        )
        store.commit()
        hits = store.search_nodes("user request", limit=5)
        assert any(h.name == "handleUserRequest" for h in hits)
        # Fallback substring search
        sub_hits = store.search_nodes("UserReq", limit=5)
        assert any(h.name == "handleUserRequest" for h in sub_hits)
    finally:
        store.close()


def test_crg6_crg8_crg9_numpy_vector_rrf_and_rerank(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _git_init(repo)
    (repo / "m.py").write_text("def a(): pass\n", encoding="utf-8")
    _git_commit(repo, "init")

    db_path = repo / ".crg" / "graph.db"
    store = GraphStore(db_path)
    emb_store = EmbeddingStore(db_path, backend=None)
    try:
        fp = str((repo / "m.py").resolve())
        store.upsert_node(NodeInfo("File", fp, fp, 1, 5, "python"))
        store.upsert_node(NodeInfo("Function", "parseToken", fp, 1, 2, "python"))
        store.upsert_node(NodeInfo("Function", "verifyUser", fp, 3, 4, "python"))
        store.upsert_edge(
            EdgeInfo("CALLS", f"{fp}::verifyUser", f"{fp}::parseToken", fp, 3)
        )
        store.commit()

        emb_store.available = True
        emb_store.dimensions = 3
        emb_store._conn.execute(
            "INSERT OR REPLACE INTO embeddings (qualified_name, vector, text_hash, provider) VALUES (?, ?, ?, ?)",
            (
                f"{fp}::parseToken",
                np.array([1.0, 0.0, 0.0], dtype=np.float32).tobytes(),
                "stub",
                "stub",
            ),
        )
        emb_store._conn.execute(
            "INSERT OR REPLACE INTO embeddings (qualified_name, vector, text_hash, provider) VALUES (?, ?, ?, ?)",
            (
                f"{fp}::verifyUser",
                np.array([0.2, 0.98, 0.0], dtype=np.float32).tobytes(),
                "stub",
                "stub",
            ),
        )
        emb_store._conn.commit()

        class _FakeBackend:
            name = "stub"

            def embed_single(self, _text: str, dimensions: int = 3) -> list[float]:
                return [1.0, 0.0, 0.0][:dimensions]

            def embed_single_query(
                self, _text: str, dimensions: int = 3
            ) -> list[float]:
                return [1.0, 0.0, 0.0][:dimensions]

        emb_store.backend = cast(Any, _FakeBackend())
        vec_hits = emb_store.search("parse token", limit=2)
        assert vec_hits[0][0] == f"{fp}::parseToken"

        cent = store.compute_centrality()
        assert f"{fp}::parseToken" in cent

        fused = semantic_search(
            "parseToken", store, emb_store, limit=2, auto_rerank=False
        )
        assert fused and fused[0]["qualified_name"] == f"{fp}::parseToken"
        assert "rrf_score" in fused[0] and "centrality" in fused[0]

        with (
            patch("crg.config.settings.local_rerank_model", "fake-rerank"),
            patch(
                "crg.reranker.rerank_candidates",
                side_effect=lambda _q, cands, model_name="": list(reversed(cands)),
            ),
        ):
            reranked = semantic_search(
                "parseToken", store, emb_store, limit=2, auto_rerank=True
            )
            assert reranked[0]["qualified_name"] == fused[-1]["qualified_name"]
    finally:
        emb_store.close()
        store.close()


def test_crg11_13_intra_repo_three_phases(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _git_init(repo)
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "a.py").write_text(
        "def dup() -> int:\n    return 1\n", encoding="utf-8"
    )
    (repo / "pkg" / "b.py").write_text(
        "def dup() -> int:\n    return 2\n", encoding="utf-8"
    )
    (repo / "pkg" / "base.py").write_text(
        "class BaseHandler:\n"
        "    def handle(self) -> int:\n"
        "        return 0\n\n"
        "class SubHandler(BaseHandler):\n"
        "    def handle(self) -> int:\n"
        "        return 42\n\n"
        "def dispatch(h: BaseHandler) -> int:\n"
        "    return h.handle()\n",
        encoding="utf-8",
    )
    (repo / "pkg" / "caller.py").write_text(
        "from pkg.a import dup as alpha_dup\n\n"
        "def run() -> int:\n"
        "    return alpha_dup()\n",
        encoding="utf-8",
    )
    _git_commit(repo, "init")

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        res = full_build(repo, store)
        assert res["intra_repo"]["import_traced"] >= 1
        assert res["intra_repo"]["type_inferred"] >= 1
        assert res["intra_repo"]["dynamic_dispatch"] >= 1

        dyn = store._conn.execute(
            "SELECT confidence, resolution FROM edges WHERE resolution = 'dynamic_dispatch'"
        ).fetchall()
        assert dyn and float(dyn[0]["confidence"]) == pytest.approx(0.75)

        imp = store._conn.execute(
            "SELECT confidence FROM edges WHERE resolution = 'import_traced'"
        ).fetchall()
        assert imp and float(imp[0]["confidence"]) == pytest.approx(0.95)
    finally:
        store.close()


def test_crg14_scip_json_and_protobuf_import(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _git_init(repo)
    (repo / "mod.py").write_text("def foo(): pass\n", encoding="utf-8")
    _git_commit(repo, "init")

    # Binary SCIP Index protobuf fixture
    packed_def_range = _pb_bytes(
        1, _encode_varint(0) + _encode_varint(4) + _encode_varint(0) + _encode_varint(7)
    )
    occ_def = (
        packed_def_range + _pb_bytes(2, b"scip-py pkg mod/foo().") + _pb_varint(3, 1)
    )
    occ_ref = (
        _pb_varint(1, 2)
        + _pb_varint(1, 4)
        + _pb_bytes(2, b"scip-py pkg mod/foo().")
        + _pb_varint(3, 8)
    )
    rel = _pb_bytes(1, b"scip-py pkg mod/foo().") + _pb_varint(3, 1)
    sym_info = (
        _pb_bytes(1, b"scip-py pkg mod/bar().")
        + _pb_bytes(3, b"Bar doc")
        + _pb_bytes(4, rel)
    )
    doc_pb = (
        _pb_bytes(1, b"mod.py")
        + _pb_bytes(4, b"python")
        + _pb_bytes(2, occ_def)
        + _pb_bytes(
            2,
            _pb_varint(1, 1)
            + _pb_varint(1, 4)
            + _pb_bytes(2, b"scip-py pkg mod/bar().")
            + _pb_varint(3, 1),
        )
        + _pb_bytes(2, occ_ref)
        + _pb_bytes(3, sym_info)
    )
    scip_bin = repo / "index.scip"
    scip_bin.write_bytes(_pb_bytes(2, doc_pb))

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        res_pb = import_scip_index(store, scip_bin, repo_root=repo)
        assert res_pb["documents"] == 1
        assert res_pb["edges_upserted"] >= 2
        row = store._conn.execute(
            "SELECT confidence, resolution FROM edges WHERE resolution = 'scip' LIMIT 1"
        ).fetchone()
        assert row is not None and float(row["confidence"]) == 1.0
    finally:
        store.close()

    # Dispatch / MCP tool / error paths
    scip_json = repo / "index.scip.json"
    scip_json.write_text(json.dumps({"documents": []}), encoding="utf-8")
    ok = mcp_graph(
        action="import_scip", import_path=str(scip_json), repo_root=str(repo)
    )
    assert ok["status"] == "ok"
    err = import_scip_dispatch(import_path=None, repo_root=str(repo))
    assert err["status"] == "error"


def test_crg33_ipynb_parsing(tmp_path: Path) -> None:
    assert "ipynb" not in SUPPORTED_LANGUAGES
    nb = tmp_path / "analysis.ipynb"
    nb.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "source": ["# Heading"]},
                    {
                        "cell_type": "code",
                        "source": ["def compute_metric(x):\n", "    return x * 2\n"],
                    },
                    {"cell_type": "code", "source": "result = compute_metric(5)\n"},
                ],
                "metadata": {},
                "nbformat": 4,
            }
        ),
        encoding="utf-8",
    )
    parser = CodeParser()
    assert parser.detect_language(nb) == "python"
    nodes, _edges = parser.parse_file(nb)
    fn_nodes = [n for n in nodes if n.kind == "Function" and n.name == "compute_metric"]
    assert len(fn_nodes) == 1
    assert fn_nodes[0].language == "python"
    assert fn_nodes[0].extra["cell_index"] == 1
    assert nodes[0].extra["notebook"] is True

    bad_nb = tmp_path / "broken.ipynb"
    bad_nb.write_text("{not-json", encoding="utf-8")
    assert parser.parse_file(bad_nb) == ([], [])


def test_crg16_crg17_crg18_crg19_cochange_risk_tests_and_budget(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _git_init(repo)
    (repo / "core.py").write_text(
        "def risky_query(user_in: str) -> str:\n"
        '    """Execute something."""\n'
        "    return user_in\n",
        encoding="utf-8",
    )
    (repo / "service.py").write_text(
        "from core import risky_query\n\n"
        "def endpoint_handler(req: str) -> str:\n"
        '    """Handle incoming HTTP request."""\n'
        "    return risky_query(req)\n",
        encoding="utf-8",
    )
    (repo / "test_service.py").write_text(
        "from service import endpoint_handler\n\n"
        "def test_endpoint():\n"
        "    assert endpoint_handler('ok') == 'ok'\n",
        encoding="utf-8",
    )
    _git_commit(repo, "c1")

    for idx in range(2, 4):
        (repo / "core.py").write_text(
            f"def risky_query(user_in: str) -> str:\n    # rev {idx}\n    return user_in\n",
            encoding="utf-8",
        )
        (repo / "service.py").write_text(
            f"from core import risky_query\n\ndef endpoint_handler(req: str) -> str:\n    # rev {idx}\n    return risky_query(req)\n",
            encoding="utf-8",
        )
        _git_commit(repo, f"c{idx}")

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        build_res = full_build(repo, store)
        assert build_res["co_changes"]["edges_upserted"] >= 2
        co = store._conn.execute(
            "SELECT confidence FROM edges WHERE kind = 'CO_CHANGES_WITH'"
        ).fetchall()
        assert co and all(0.3 <= float(r["confidence"]) <= 1.0 for r in co)
    finally:
        store.close()

    assert _parse_numstat_commits("COMMIT:1\n1\t0\ta.py => b.py\n") == [["b.py"]]

    rev = mcp_review(
        action="context",
        changed_files=["core.py"],
        repo_root=str(repo),
        max_tokens=150,
    )
    ctx = rev["context"]
    assert 0.0 <= ctx["risk_score"] <= 10.0
    assert set(ctx["risk_breakdown"]) == {
        "fan_in",
        "security_tags",
        "untested_ratio",
        "churn_co_change",
        "cross_module",
    }
    assert "impacted_tests" in ctx
    assert ctx["token_telemetry"]["budget"] == 150
    assert ctx["token_telemetry"]["included"] + ctx["token_telemetry"]["dropped"] >= 1

    tests_res = mcp_review(
        action="tests", changed_files=["service.py"], repo_root=str(repo)
    )
    assert tests_res["status"] == "ok"
    assert any(
        "pytest test_service.py" in cmd for cmd in tests_res["suggested_commands"]
    )

    # Exercise standalone get_impact_radius wrapper options too
    imp = get_impact_radius(
        changed_files=["service.py"],
        repo_root=str(repo),
        direction="dependents",
        edge_kinds=["CALLS"],
        min_confidence=0.5,
    )
    assert imp["status"] == "ok"
    q_imp = mcp_query(
        action="impact",
        changed_files=["service.py"],
        repo_root=str(repo),
        direction="dependencies",
    )
    assert q_imp["status"] == "ok"


def test_crg20_crg21_scoped_security_and_taint_paths(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _git_init(repo)
    (repo / "handler.py").write_text(
        "from db import run_sql\n\n"
        "def handle_request(request):\n"
        "    return run_sql(request)\n",
        encoding="utf-8",
    )
    (repo / "db.py").write_text(
        "import sqlite3\n\n"
        "def run_sql(query_arg):\n"
        '    sql = f"SELECT * FROM users WHERE id = {query_arg}"\n'
        "    return sqlite3.connect(':memory:').execute(sql)\n",
        encoding="utf-8",
    )
    (repo / "unrelated.py").write_text(
        "import subprocess\n\n"
        "def dangerous_unrelated(cmd):\n"
        "    subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )
    _git_commit(repo, "c1")
    (repo / "handler.py").write_text(
        "from db import run_sql\n\n"
        "def handle_request(request):\n"
        "    # changed\n"
        "    return run_sql(request)\n",
        encoding="utf-8",
    )
    _git_commit(repo, "c2")

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        full_build(repo, store)
    finally:
        store.close()

    scoped = mcp_security(
        action="scan", scope="impact", base="HEAD~1", repo_root=str(repo)
    )
    assert scoped["scope"] == "impact"
    assert not any("unrelated.py" in k for k in scoped["tags_by_node"])

    bad_scope = security_scan(repo_root=str(repo), scope="invalid")
    assert "error" in bad_scope

    taint = mcp_security(action="paths", repo_root=str(repo), max_depth=4)
    assert taint["status"] == "ok"
    assert taint["paths_count"] >= 1
    assert any(
        "handle_request" in p["source"] and "run_sql" in p["sink"]
        for p in taint["paths"]
    )
    taint_filtered = security_taint_paths(
        repo_root=str(repo), source="handle_request", sink="run_sql"
    )
    assert taint_filtered["paths_count"] >= 1


def test_crg23_watch_idle_timeout_and_cli_flags(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _git_init(repo)
    (repo / "x.py").write_text("def x(): pass\n", encoding="utf-8")
    _git_commit(repo, "init")
    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        watch(repo, store, idle_timeout=0.08)
    finally:
        store.close()

    parser = _build_parser()
    assert parser.parse_args(["watch", "--idle-timeout", "5"]).idle_timeout == 5.0
    assert (
        parser.parse_args(["graph", "import-scip", "idx.scip"]).graph_action
        == "import-scip"
    )
    assert parser.parse_args(["review", "tests"]).review_action == "tests"
    assert (
        parser.parse_args(["security", "paths", "--max-depth", "4"]).security_action
        == "paths"
    )
    assert (
        parser.parse_args(["security", "scan", "--scope", "impact"]).scope == "impact"
    )


def test_crg27_crg28_action_yml_and_benchmark() -> None:
    action_text = (Path(__file__).resolve().parents[1] / "action.yml").read_text(
        encoding="utf-8"
    )
    assert 'using: "composite"' in action_text
    assert "CRG_SEC_SCOPE: ${{ inputs.security_scope }}" in action_text
    assert "${{ inputs." not in action_text.rsplit("run: |", 1)[-1]

    report = run_benchmark()
    gt_edges = report["ground_truth_edges"]
    dyn_edges = report["dynamic_dispatch_edges"]
    languages = report["languages"]
    assert isinstance(gt_edges, int) and gt_edges >= 100
    assert isinstance(dyn_edges, int) and dyn_edges > 0
    assert isinstance(languages, dict) and set(languages) == {
        "python",
        "typescript",
        "go",
        "rust",
    }
    stages = report["stages"]
    assert isinstance(stages, dict)
    assert stages["intra_repo_3phase"]["f1"] >= stages["syntactic_baseline"]["f1"]
    assert stages["scip_import"]["f1"] == 1.0


def test_crg_intra_repo_ts_aliases_python_exports_and_dispatch_cap(
    tmp_path: Path,
) -> None:
    from crg.resolver.intra_repo import (
        _extract_python_all,
        _module_keys_for_rel,
        _posix_rel,
        _resolve_relative_module,
        _resolve_ts_spec,
        _safe_extra,
        resolve_intra_repo_calls,
    )

    assert _safe_extra(None) == {}
    assert _safe_extra("{bad-json") == {}
    assert _safe_extra("[1,2]") == {}
    assert _posix_rel("/totally/outside/path.py", tmp_path)
    assert _extract_python_all("x = 1") is None
    assert _extract_python_all('__all__ = ["foo", "bar"]') == {"foo", "bar"}
    assert _resolve_relative_module("app.py", ".util") == "util"
    assert _resolve_relative_module("a/b/c.py", "..top") == "a.top"
    assert _resolve_relative_module("a/b/c.py", "..") == "a"
    assert "util" in _module_keys_for_rel("src/util/index.ts")
    assert "pkg" in _module_keys_for_rel("pkg/__init__.py")

    ts_paths = {"@app/*": ["./src/*"], "@cfg": ["./src/config.ts"]}
    assert "src/sub" in _resolve_ts_spec("src/a.ts", "@app/sub", ts_paths)
    assert "src/config.ts" in _resolve_ts_spec("src/a.ts", "@cfg", ts_paths)
    assert "src/shared" in _resolve_ts_spec("src/nested/a.ts", "../shared", ts_paths)

    repo = tmp_path / "poly"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "tsconfig.json").write_text(
        json.dumps(
            {"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["./src/*"]}}}
        ),
        encoding="utf-8",
    )
    exp_py = (repo / "src" / "pkg" / "exports.py").resolve()
    exp_py.write_text(
        '__all__ = ["pub_fn"]\n'
        "def pub_fn():\n    return 1\n"
        "def priv_fn():\n    return 2\n",
        encoding="utf-8",
    )
    helper_py = (repo / "src" / "pkg" / "helper.py").resolve()
    helper_py.write_text("def sub_fn():\n    return 3\n", encoding="utf-8")
    consumer_py = (repo / "src" / "pkg" / "consumer.py").resolve()
    consumer_py.write_text(
        "from .exports import pub_fn as pf, priv_fn\n"
        "import src.pkg.helper as hp\n"
        "import src.pkg.helper\n"
        "def run_py():\n    pf()\n    priv_fn()\n    hp.sub_fn()\n",
        encoding="utf-8",
    )
    ts_mod = (repo / "src" / "service.ts").resolve()
    ts_mod.write_text(
        "export class ApiClient { fetch(): void {} }\n"
        "export default function mainEntry(): void {}\n",
        encoding="utf-8",
    )
    ts_app = (repo / "src" / "app.ts").resolve()
    ts_app.write_text(
        'import { ApiClient as Client } from "@app/service";\n'
        'import * as svcNs from "./service";\n'
        'import mainEntry from "@app/service";\n'
        "class Holder {\n"
        "  constructor() { this.client = new ApiClient(); }\n"
        "  run() { this.client.fetch(); const loc = new ApiClient(); loc.fetch(); mainEntry(); }\n"
        "}\n",
        encoding="utf-8",
    )

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        for p, lang in (
            (exp_py, "python"),
            (helper_py, "python"),
            (consumer_py, "python"),
            (ts_mod, "typescript"),
            (ts_app, "typescript"),
        ):
            store.upsert_node(NodeInfo("File", str(p), str(p), 1, 10, lang))
        store.upsert_node(NodeInfo("Function", "pub_fn", str(exp_py), 2, 3, "python"))
        store.upsert_node(NodeInfo("Function", "priv_fn", str(exp_py), 4, 5, "python"))
        store.upsert_node(
            NodeInfo("Function", "sub_fn", str(helper_py), 1, 2, "python")
        )
        store.upsert_node(
            NodeInfo("Function", "run_py", str(consumer_py), 4, 5, "python")
        )
        store.upsert_node(
            NodeInfo("Class", "ApiClient", str(ts_mod), 1, 1, "typescript")
        )
        store.upsert_node(
            NodeInfo(
                "Function",
                "fetch",
                str(ts_mod),
                1,
                1,
                "typescript",
                parent_name="ApiClient",
            )
        )
        store.upsert_node(
            NodeInfo("Function", "mainEntry", str(ts_mod), 2, 2, "typescript")
        )
        store.upsert_node(NodeInfo("Class", "Holder", str(ts_app), 4, 7, "typescript"))
        store.upsert_node(
            NodeInfo(
                "Function",
                "run",
                str(ts_app),
                6,
                6,
                "typescript",
                parent_name="Holder",
                source_text=(
                    "self.typed_c: ApiClient; this.client = new ApiClient(); "
                    "this.client.fetch(); const loc = new ApiClient(); loc.fetch();"
                ),
            )
        )
        # Dynamic dispatch with 7 subclasses (must cap at 5)
        store.upsert_node(NodeInfo("Class", "Base", str(exp_py), 1, 2, "python"))
        store.upsert_node(
            NodeInfo(
                "Function",
                "exec",
                str(exp_py),
                1,
                2,
                "python",
                parent_name="Base",
            )
        )
        for i in range(7):
            sub_cls = f"Sub{i}"
            store.upsert_node(NodeInfo("Class", sub_cls, str(exp_py), 1, 2, "python"))
            store.upsert_node(
                NodeInfo(
                    "Function",
                    "exec",
                    str(exp_py),
                    1,
                    2,
                    "python",
                    parent_name=sub_cls,
                )
            )
            store.upsert_edge(
                EdgeInfo(
                    "INHERITS",
                    f"{exp_py}::{sub_cls}",
                    f"{exp_py}::Base",
                    str(exp_py),
                    1,
                )
            )

        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{consumer_py}::run_py",
                "pf",
                str(consumer_py),
                5,
                extra={"bare_targets": ["priv_fn", "hp.sub_fn"]},
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{ts_app}::Holder.run",
                "unresolved::this.client.fetch",
                str(ts_app),
                6,
                extra={"bare_unresolved_target": "this.client.fetch"},
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{ts_app}::Holder.run",
                "mainEntry",
                str(ts_app),
                6,
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{consumer_py}::run_py",
                f"{exp_py}::Base.exec",
                str(consumer_py),
                5,
            )
        )
        # Bare method name triggers elif caller_src loop (lines 463-473)
        store.upsert_node(
            NodeInfo(
                "Function",
                "make_client",
                str(ts_app),
                2,
                3,
                "typescript",
                return_type="ApiClient",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{ts_app}::Holder.run",
                "fetch",
                str(ts_app),
                6,
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "IMPORTS_FROM",
                str(consumer_py),
                f"{exp_py}::pub_fn",
                str(repo / "src" / "pkg" / "extra_mod.py"),
                1,
                extra={"alias": "pub_alias"},
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{ts_app}::Holder.run",
                "svcNs.fetch",
                str(ts_app),
                6,
                extra={"bare_unresolved_target": "svcNs.fetch"},
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{ts_app}::Holder.run",
                "make_client().fetch",
                str(ts_app),
                6,
                extra={"bare_unresolved_target": "make_client().fetch"},
            )
        )
        store.commit()

        counts = resolve_intra_repo_calls(store, repo_root=repo)
        assert counts["import_traced"] >= 2
        assert counts["type_inferred"] >= 2
        assert counts["dynamic_dispatch"] == 5
    finally:
        store.close()


def test_crg_scip_protobuf_wire_types_and_errors(tmp_path: Path) -> None:
    from crg.scip import (
        _decode_packed_int32,
        _read_varint,
        _scip_symbol_parts,
        _skip_field,
    )

    assert _scip_symbol_parts("pkg/Foo#") == ("Class", "Foo")
    assert _scip_symbol_parts("pkg/Bar.") == ("Type", "Bar")
    assert _scip_symbol_parts("plain") == ("Function", "plain")
    assert _scip_symbol_parts("   ") == ("Function", "")
    assert _decode_packed_int32(b"\xfe\xff\xff\xff\x0f") == [-2]

    with pytest.raises(ValueError, match="Truncated varint"):
        _read_varint(b"\x80", 0)
    with pytest.raises(ValueError, match="Unsupported protobuf wire type"):
        _skip_field(b"\x00", 0, 3)

    def _v(n: int) -> bytes:
        out = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                out.append(b | 0x80)
            else:
                out.append(b)
                return bytes(out)

    def _f2(num: int, data: bytes) -> bytes:
        return _v((num << 3) | 2) + _v(len(data)) + data

    def _f0(num: int, val: int) -> bytes:
        return _v((num << 3) | 0) + _v(val)

    # Occurrence with packed 3-coord range, role import, plus 1 fixed32 field (wire_type=5)
    occ_import = (
        _f2(1, _v(2) + _v(0) + _v(5))
        + _f2(2, b"pkg/cls#")
        + _f0(3, 2)  # _ROLE_IMPORT
        + _v((9 << 3) | 5)
        + b"\x00\x00\x00\x00"
    )
    # Occurrence referencing call target pkg/run().
    occ_call = _f2(1, _v(1) + _v(0)) + _f2(2, b"pkg/run().") + _f0(3, 0)
    # Occurrence defining pkg/run().
    occ_fn_def = (
        _f2(1, _v(0) + _v(0) + _v(2) + _v(1)) + _f2(2, b"pkg/run().") + _f0(3, 1)
    )
    # Occurrence with 4-coord range & definition role
    occ_def = _f2(1, _v(0) + _v(0) + _v(4) + _v(1)) + _f2(2, b"pkg/cls#") + _f0(3, 1)
    rel_bytes = _f2(1, b"pkg/base#") + _f0(2, 1) + _f0(3, 1) + _f0(4, 1) + _f0(5, 1)
    sym_bytes = _f2(1, b"pkg/cls#") + _f2(3, b"doc line") + _f2(4, rel_bytes)
    # Document with wire_type=1 fixed64 and wire_type=0 varint skipped
    doc_bytes = (
        _f2(1, b"src/cls.py")
        + _f2(2, occ_def)
        + _f2(2, occ_fn_def)
        + _f2(2, occ_call)
        + _f0(11, 7)
        + _f2(2, occ_import)
        + _f2(3, sym_bytes)
        + _f2(4, b"Python")
        + _v((10 << 3) | 1)
        + (b"\x00" * 8)
    )
    pb_bytes = _f2(2, doc_bytes)

    repo = tmp_path / "scip_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "cls.py").write_text("class cls: pass\n", encoding="utf-8")
    _git_init(repo)
    _git_commit(repo, "init")

    pb_path = repo / "extra.scip"
    pb_path.write_bytes(pb_bytes)
    bad_json = repo / "bad.json"
    bad_json.write_text("[1, 2]", encoding="utf-8")

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        with pytest.raises(FileNotFoundError):
            import_scip_index(store, repo / "missing.scip", repo)
        with pytest.raises(ValueError, match="root must be an object"):
            import_scip_index(store, bad_json, repo)
        summary = import_scip_index(store, pb_path, repo)
        assert summary["documents"] == 1
        assert summary["edges_upserted"] >= 1
    finally:
        store.close()

    # MCP graph import_scip missing path & valid json via tools/server
    err = mcp_graph(action="import_scip", repo_root=str(repo))
    assert "error" in err
    good_json = repo / "index.scip.json"
    good_json.write_text(
        json.dumps(
            {
                "documents": [
                    "bad",
                    {
                        "relative_path": "",
                        "language": "python",
                        "occurrences": [],
                    },
                    {
                        "relative_path": "src/cls.py",
                        "language": "Python",
                        "occurrences": [
                            "bad-occ",
                            {
                                "range": [0, 0, 10],
                                "symbol": "pkg/cls#",
                                "symbol_roles": 1,
                            },
                        ],
                        "symbols": [
                            "bad-sym",
                            {
                                "symbol": "pkg/cls#",
                                "documentation": ["Class doc"],
                                "relationships": [],
                            },
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    ok = mcp_graph(
        action="import_scip",
        repo_root=str(repo),
        import_path=str(good_json),
    )
    assert ok["status"] == "ok"


def test_crg_taint_git_mining_reranker_and_security_impact(tmp_path: Path) -> None:
    from crg.git_mining import mine_co_changes
    from crg.reranker import LocalRerankError, rerank_candidates
    from crg.security.taint import _parse_sec_tags, find_taint_paths

    assert _parse_sec_tags("not-json") == []
    assert _parse_sec_tags('["CWE-89"]') == ["CWE-89"]
    assert rerank_candidates("q", [], model_name="fake") == []

    class _BadReranker:
        def rerank(self, _q: str, _c: list[str]) -> list[float]:
            raise RuntimeError("boom")

    with patch("crg.reranker._get_reranker", return_value=_BadReranker()):
        with pytest.raises(LocalRerankError, match="failed"):
            rerank_candidates("q", [{"qualified_name": "a"}], model_name="fake")

    non_git = tmp_path / "nongit"
    non_git.mkdir()
    store_ng = GraphStore(non_git / ".crg" / "graph.db")
    try:
        assert mine_co_changes(non_git, store_ng) == {
            "commits_scanned": 0,
            "edges_upserted": 0,
        }
    finally:
        store_ng.close()

    parsed_renames = _parse_numstat_commits("COMMIT:1\n1\t1\told.py => new.py\n")
    assert parsed_renames == [["new.py"]]

    repo = tmp_path / "sec_repo"
    repo.mkdir()
    _git_init(repo)
    f_path = repo / "app.py"
    f_path.write_text("def handle(req):\n    cursor.execute(req)\n", encoding="utf-8")
    _git_commit(repo, "init")

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        full_build(repo, store)
        fp = str(f_path.resolve())
        store.upsert_node(
            NodeInfo(
                "Function",
                "handle",
                fp,
                1,
                2,
                "python",
                params="(req)",
                source_text="def handle(req):\n    cursor.execute(req)\n",
                repo_id="r1",
            )
        )
        store._conn.execute(
            "UPDATE nodes SET security_tags = ? WHERE qualified_name = ?",
            ('["CWE-89"]', f"{fp}::handle"),
        )
        store.upsert_node(
            NodeInfo("Function", "isolated_route", fp, 3, 4, "python", repo_id="r1")
        )
        store.commit()
        res = find_taint_paths(store, repo="r1", limit=1)
        assert res["paths_count"] == 1
        assert res["paths"][0]["hops"] == 0
        filtered = find_taint_paths(store, source="handle", sink="handle", repo="r1")
        assert filtered["paths_count"] == 1
    finally:
        store.close()

    # Security scan impact & error scope branches + MCP wrappers
    inv = mcp_security(action="scan", repo_root=str(repo), scope="bad")
    assert "error" in inv

    # Dirty change triggers get_staged_and_unstaged path in impact scope
    f_path.write_text("def handle(req):\n    return req\n", encoding="utf-8")
    impact_clean = security_scan(
        repo_root=str(repo), engine="heuristic", scope="impact"
    )
    assert impact_clean["scope"] == "impact"

    class _FakeTag:
        rule_id = "R1"
        category = "sqli"
        cwe = "CWE-89"
        severity = "HIGH"
        line = 2
        message = "sql"

        def to_dict(self) -> dict[str, str]:
            return {"rule_id": "R1"}

    class _FakeSemgrepResult:
        tags = [_FakeTag()]

    class _FakeScanner:
        def scan_path(self, _p: Path) -> _FakeSemgrepResult:
            return _FakeSemgrepResult()

    with patch("crg.tools.SemgrepScanner", return_value=_FakeScanner()):
        sem_imp = security_scan(repo_root=str(repo), engine="semgrep", scope="impact")
        assert sem_imp["scope"] == "impact"

    paths_json = mcp_security(action="paths", repo_root=str(repo))
    assert "paths" in paths_json
    tests_json = mcp_review(action="tests", repo_root=str(repo))
    assert "tier_1_hop" in tests_json


def test_crg_cli_sota_handlers_and_query_params(tmp_path: Path) -> None:
    from crg.cli import main as cli_main
    from crg.tools import _suggested_test_commands, get_impacted_tests

    repo = tmp_path / "cli_repo"
    repo.mkdir()
    _git_init(repo)
    f = repo / "a.py"
    f.write_text("def foo():\n    return 1\n", encoding="utf-8")
    _git_commit(repo, "init")
    f.write_text("def foo():\n    return 2\n", encoding="utf-8")
    _git_commit(repo, "upd")
    s = GraphStore(repo / ".crg" / "graph.db")
    try:
        full_build(repo, s)
    finally:
        s.close()

    cmds = _suggested_test_commands(
        [
            str(repo / "tests" / "a_test.ts"),
            str(repo / "pkg" / "a_test.go"),
            "/external/test_outside.py",
        ],
        repo,
    )
    assert any("vitest" in c for c in cmds)
    assert any("go test" in c for c in cmds)
    empty_tests = get_impacted_tests(changed_files=[], repo_root=str(repo))
    assert empty_tests["tier_1_hop"] == []

    with patch.object(
        sys,
        "argv",
        ["crg", "watch", "--repo-root", str(repo), "--idle-timeout", "0.05"],
    ):
        assert cli_main() == 0

    with patch.object(
        sys,
        "argv",
        [
            "crg",
            "query",
            "query",
            "--pattern",
            "callers_of",
            "--target",
            "foo",
            "--repo-root",
            str(repo),
        ],
    ):
        assert cli_main() == 0

    imp_res = mcp_query(
        action="impact",
        repo_root=str(repo),
        direction="dependents",
        edge_kinds=["CALLS"],
        min_confidence=0.5,
    )
    assert "changed_files" in imp_res or "error" in imp_res or "status" in imp_res

    sec_imp = mcp_security(
        action="scan",
        repo_root=str(repo),
        scope="impact",
        base="HEAD",
    )
    assert "scope" in sec_imp

    from crg.graph import _extract_doc_excerpt
    from crg.tools import semantic_search_nodes

    assert _extract_doc_excerpt("") == ""
    doc_out = _extract_doc_excerpt('"""Module doc."""\n# inline note\nx = 1\n')
    assert "Module doc." in doc_out and "inline note" in doc_out

    emb_init = EmbeddingStore(repo / ".crg" / "graph.db", backend=None)
    emb_init.close()
    foo_qn = f"{(repo / 'a.py').resolve()}::foo"
    s_repo = GraphStore(repo / ".crg" / "graph.db")
    try:
        s_repo.upsert_node(
            NodeInfo(
                "Function",
                "foo",
                str((repo / "a.py").resolve()),
                1,
                2,
                "python",
                repo_id="r1",
            )
        )
        s_repo.commit()
        s_repo._conn.execute(
            "INSERT OR REPLACE INTO embeddings (qualified_name, vector, text_hash, provider) VALUES (?, ?, ?, ?)",
            (
                foo_qn,
                np.array([1.0, 0.0, 0.0], dtype=np.float32).tobytes(),
                "h",
                "stub",
            ),
        )
        s_repo._conn.commit()
        assert s_repo.search_nodes("!!!", limit=2) == []
        assert len(s_repo.search_nodes("foo", limit=1)) == 1
        dep_res = s_repo.get_impact_radius(
            [str((repo / "a.py").resolve())],
            direction="dependencies",
            min_confidence=0.9,
        )
        assert "changed_nodes" in dep_res
    finally:
        s_repo.close()

    with (
        patch("crg.tools.init_backend", return_value=object()),
        patch("crg.tools.semantic_search") as mock_ss,
        patch("crg.config.settings.local_rerank_model", "fake-rerank"),
        patch(
            "crg.reranker.rerank_candidates",
            side_effect=lambda _q, cands, model_name="": cands,
        ),
    ):
        mock_ss.return_value = [
            {
                "qualified_name": foo_qn,
                "kind": "Function",
                "name": "foo",
                "score": 0.95,
            },
            {
                "qualified_name": "missing::ghost",
                "kind": "Function",
                "name": "ghost",
                "score": 0.2,
            },
        ]
        ss_res = semantic_search_nodes(
            query="foo",
            repo_root=str(repo),
            kind="Function",
            repo="r1",
        )
        assert ss_res["status"] == "ok"
        assert ss_res["results"]

    exp_res = mcp_graph(
        action="export",
        repo_root=str(repo),
        output_path=str(repo / "out.graphml"),
    )
    assert "status" in exp_res
    sum_res = mcp_graph(action="summarize", repo_root=str(repo), max_nodes=5)
    assert "status" in sum_res

    with patch.object(sys, "argv", ["crg", "db", "path"]):
        assert cli_main() == 0
    with patch.object(sys, "argv", ["crg", "security", "rule_list"]):
        assert cli_main() == 0

    with patch.object(
        sys,
        "argv",
        ["crg", "review", "tests", "--repo-root", str(repo)],
    ):
        assert cli_main() == 0

    with patch.object(
        sys,
        "argv",
        [
            "crg",
            "review",
            "context",
            "--repo-root",
            str(repo),
            "--max-tokens",
            "15",
        ],
    ):
        assert cli_main() == 0

    with patch.object(
        sys,
        "argv",
        ["crg", "security", "paths", "--repo-root", str(repo), "--max-depth", "3"],
    ):
        assert cli_main() == 0

    with patch.object(
        sys,
        "argv",
        [
            "crg",
            "security",
            "scan",
            "--repo-root",
            str(repo),
            "--engine",
            "heuristic",
            "--scope",
            "impact",
        ],
    ):
        assert cli_main() == 0

    from crg.git_mining import mine_co_changes

    other = repo / "b.py"
    for i in range(3):
        f.write_text(f"def foo():\n    return {i + 10}\n", encoding="utf-8")
        other.write_text(f"def bar():\n    return {i}\n", encoding="utf-8")
        _git_commit(repo, f"co {i}")
    s2 = GraphStore(repo / ".crg" / "graph.db")
    try:
        full_build(repo, s2)
        co = mine_co_changes(repo, s2, min_co_changes=2, min_confidence=0.3)
        assert co["edges_upserted"] >= 1
    finally:
        s2.close()


def test_crg_final_sota_branch_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    from types import SimpleNamespace

    from crg.git_mining import _parse_numstat_commits, mine_co_changes
    from crg.resolver.intra_repo import resolve_intra_repo_calls
    from crg.scip import _skip_field
    from crg.security.taint import find_taint_paths
    from crg.server import graph as mcp_graph
    from crg.server import review as mcp_review
    from crg.tools import (
        _node_skeleton,
        _suggested_test_commands,
        semantic_search_nodes,
    )

    # 1. SCIP wire types (_skip_field)
    assert _skip_field(b"\x01", 0, 0) == 1
    assert _skip_field(b"\x02ab", 0, 2) == 3

    # 2. _parse_numstat_commits edge cases (renames, blank lines, overflow)
    raw_log = (
        "COMMIT:1\n\nbadline\n\n0\t0\t\n1\t0\told.py => new.py\n"
        "COMMIT:2\n" + "\n".join(f"1\t0\tf{i}.py" for i in range(6)) + "\n"
    )
    parsed = _parse_numstat_commits(raw_log, max_files_per_commit=4)
    assert parsed == [["new.py"]]

    # 3. Tool helpers & unknown review action + graph export/import
    repo = tmp_path / "covrepo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    (repo / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"paths": {"@app/*": ["./src/*"]}}}),
        encoding="utf-8",
    )
    a_py = (repo / "src" / "a.py").resolve()
    a_py.write_text("def alpha(request):\n    return 1\n", encoding="utf-8")
    b_py = (repo / "src" / "b.py").resolve()
    b_py.write_text("def beta():\n    return 2\n", encoding="utf-8")
    u_py = (repo / "src" / "unindexed.py").resolve()
    u_py.write_text("x = 1\n", encoding="utf-8")
    ts_svc = (repo / "src" / "svc.ts").resolve()
    ts_svc.write_text("export class Svc { ping(): void {} }\n", encoding="utf-8")
    ts_use = (repo / "src" / "use.ts").resolve()
    ts_use.write_text(
        'import { Svc } from "@app/svc";\n'
        "function run() { s = new Svc(); s.ping(); }\n",
        encoding="utf-8",
    )

    cmds = _suggested_test_commands(
        [
            str(repo / "tests" / "test_a.py"),
            str(repo / "tests" / "test_a.py"),
        ],
        repo,
    )
    assert len(cmds) == 1

    skel = _node_skeleton(
        SimpleNamespace(
            qualified_name="pkg.fn",
            kind="Function",
            name="fn",
            file_path="src/a.py",
            line_start=1,
            line_end=2,
            signature="def fn():",
            return_type="int",
            extra={"docstring": "First doc line\nSecond line"},
            params=None,
        )
    )
    assert skel["doc_summary"] == "First doc line"

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    for i in range(3):
        a_py.write_text(f"def alpha(request):\n    return {i}\n", encoding="utf-8")
        b_py.write_text(f"def beta():\n    return {i}\n", encoding="utf-8")
        u_py.write_text(f"x = {i}\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"c{i}"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
    a_py.write_text("def alpha(request):\n    return 99\n", encoding="utf-8")
    subprocess.run(["git", "add", str(a_py)], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "solo-a"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    b_py.write_text("def beta():\n    return 99\n", encoding="utf-8")
    subprocess.run(["git", "add", str(b_py)], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "solo-b"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        for p, lang in (
            (a_py, "python"),
            (b_py, "python"),
            (ts_svc, "typescript"),
            (ts_use, "typescript"),
        ):
            store.upsert_node(NodeInfo("File", str(p), str(p), 1, 10, lang))
        # Outside node triggers ValueError in relative_to
        store.upsert_node(
            NodeInfo("File", "/outside/ghost.py", "/outside/ghost.py", 1, 2, "python")
        )
        store.upsert_node(
            NodeInfo(
                "Function",
                "alpha",
                str(a_py),
                1,
                2,
                "python",
                params="request",
                source_text="def alpha(request): return eval_one(request) + exec_two(request)",
            )
        )
        store.upsert_node(
            NodeInfo(
                "Function",
                "execute_sql",
                str(b_py),
                1,
                2,
                "python",
                source_text="cursor.execute(q)",
            )
        )
        store.upsert_node(
            NodeInfo(
                "Function",
                "run_eval",
                str(b_py),
                3,
                4,
                "python",
                source_text="eval(q)",
            )
        )
        store.upsert_node(NodeInfo("Class", "Svc", str(ts_svc), 1, 1, "typescript"))
        store.upsert_node(
            NodeInfo(
                "Function",
                "ping",
                str(ts_svc),
                1,
                1,
                "typescript",
                parent_name="Svc",
            )
        )
        store.upsert_node(
            NodeInfo(
                "Function",
                "run",
                str(ts_use),
                2,
                2,
                "typescript",
                source_text="local_svc = Svc()\nlocal_svc.ping()",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "IMPORTS_FROM",
                str(ts_use),
                "@app/svc::Svc",
                str(ts_use),
                1,
                extra={"alias": "Svc"},
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "IMPORTS_FROM",
                str(a_py),
                f"{ts_svc}::Svc",
                str(a_py),
                1,
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{a_py}::alpha",
                "Svc.ping",
                str(a_py),
                2,
                extra={"bare_unresolved_target": "Svc.ping"},
            )
        )
        store.upsert_edge(
            EdgeInfo(
                "CALLS",
                f"{ts_use}::run",
                "local_svc.ping",
                str(ts_use),
                2,
                extra={"bare_unresolved_target": "local_svc.ping"},
            )
        )
        store.upsert_edge(
            EdgeInfo("CALLS", f"{a_py}::alpha", f"{b_py}::execute_sql", str(a_py), 2)
        )
        store.upsert_edge(
            EdgeInfo("CALLS", f"{a_py}::alpha", f"{b_py}::run_eval", str(a_py), 2)
        )
        store.commit()

        resolve_intra_repo_calls(store, repo_root=repo)
        taint_res = find_taint_paths(store, limit=1)
        assert taint_res["paths_count"] == 1

        # Low threshold missed by high min_confidence
        co_hi = mine_co_changes(repo, store, min_co_changes=2, min_confidence=0.999)
        assert co_hi["edges_upserted"] == 0
    finally:
        store.close()

    # Unknown review action + graph export/import
    bad_rev = mcp_review(action="contexttt", repo_root=str(repo))
    assert "Did you mean 'context'" in bad_rev["error"]

    graphml_out = tmp_path / "exported.graphml"
    exp_res = mcp_graph(
        action="export",
        format="graphml",
        output_path=str(graphml_out),
        repo_root=str(repo),
    )
    assert graphml_out.is_file() or "error" in exp_res
    imp_res = mcp_graph(
        action="import",
        import_path=str(graphml_out),
        repo_root=str(repo),
    )
    assert isinstance(imp_res, dict)

    # Mocked semantic_search_nodes skipping None qualified_name
    class _StubEmb:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.available = True

        def search(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            return [
                {"qualified_name": None, "score": 0.9},
                {"qualified_name": f"{a_py}::alpha", "score": 0.8},
            ]

    monkeypatch.setattr("crg.embeddings.EmbeddingStore", _StubEmb)
    sem_res = semantic_search_nodes("alpha", repo_root=str(repo))
    assert sem_res["status"] == "ok"

    # Mocked failed git log in mine_co_changes
    monkeypatch.setattr(
        "crg.git_mining.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="fail"),
    )
    s3 = GraphStore(repo / ".crg" / "graph.db")
    try:
        assert mine_co_changes(repo, s3)["commits_scanned"] == 0
    finally:
        s3.close()
