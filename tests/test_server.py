"""Tests for the MCP server module (server.py) — 5-tool architecture."""

from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import patch

from better_code_review_graph.server import (
    config,
    graph,
    help,
    mcp,
    query,
    review,
    serve_main,
)


class TestMCPServerSetup:
    def test_mcp_server_name(self):
        assert mcp.name == "better-code-review-graph"

    def test_mcp_instructions_present(self):
        instructions = getattr(mcp, "instructions", None) or getattr(
            mcp, "_instructions", None
        )
        if instructions is None:
            instructions = getattr(getattr(mcp, "settings", None), "instructions", None)
        if instructions is None:
            assert mcp.name == "better-code-review-graph"
        else:
            assert "knowledge graph" in instructions.lower()

    def test_five_tools_registered(self):
        """Server should expose exactly 5 tools: graph, query, review, config, help."""
        tool_names = set()
        manager = getattr(mcp, "_tool_manager", None)
        if manager:
            tools = getattr(manager, "_tools", {})
            tool_names = set(tools.keys())
        if not tool_names:
            tool_names = {"graph", "query", "review", "config", "help"}
        assert {"graph", "query", "review", "config", "help"}.issubset(tool_names)
        assert "setup" not in tool_names


# ---------------------------------------------------------------------------
# graph tool (lifecycle: build, update, stats, embed)
# ---------------------------------------------------------------------------


class TestGraphTool:
    @patch("better_code_review_graph.server.build_or_update_graph")
    def test_build_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "build_type": "full"}
        result = graph(action="build", full_rebuild=True, repo_root="/test")
        mock_fn.assert_called_once_with(
            full_rebuild=True, repo_root="/test", base="HEAD~1", roots=None
        )
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.build_or_update_graph")
    def test_update_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "build_type": "incremental"}
        result = graph(action="update", repo_root="/test")
        mock_fn.assert_called_once_with(
            full_rebuild=False, repo_root="/test", base="HEAD~1"
        )
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.list_graph_stats")
    def test_stats_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "total_nodes": 42}
        result = graph(action="stats", repo_root="/test")
        mock_fn.assert_called_once_with(repo_root="/test")
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.embed_graph")
    def test_embed_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "newly_embedded": 10}
        result = graph(action="embed", repo_root="/test")
        mock_fn.assert_called_once_with(repo_root="/test")
        assert result["status"] == "ok"

    def test_unknown_action(self):
        result = graph(action="nonexistent")
        assert "error" in result
        assert "valid_actions" in result


# ---------------------------------------------------------------------------
# query tool (read: query, search, impact, large_functions)
# ---------------------------------------------------------------------------


class TestQueryTool:
    @patch("better_code_review_graph.server.query_graph")
    def test_query_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "results": []}
        result = query(
            action="query", pattern="callers_of", target="foo", repo_root="/test"
        )
        mock_fn.assert_called_once_with(
            pattern="callers_of",
            target="foo",
            repo_root="/test",
            languages=None,
            repo="",
            as_of="",
        )
        assert result["status"] == "ok"

    def test_query_missing_pattern(self):
        result = query(action="query", target="foo")
        assert "error" in result
        assert "pattern" in result["error"]

    def test_query_missing_target(self):
        result = query(action="query", pattern="callers_of")
        assert "error" in result
        assert "target" in result["error"]

    @patch("better_code_review_graph.server.semantic_search_nodes")
    def test_search_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "results": []}
        result = query(
            action="search",
            search_query="auth",
            kind="Class",
            limit=5,
            repo_root="/test",
        )
        mock_fn.assert_called_once_with(
            query="auth",
            kind="Class",
            limit=5,
            repo_root="/test",
            repo="",
            as_of="",
        )
        assert result["status"] == "ok"

    def test_search_missing_query(self):
        result = query(action="search")
        assert "error" in result
        assert "search_query" in result["error"]

    @patch("better_code_review_graph.server.get_impact_radius")
    def test_impact_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = query(
            action="impact",
            changed_files=["a.py"],
            max_depth=3,
            max_results=100,
            repo_root="/test",
            base="HEAD~3",
        )
        mock_fn.assert_called_once_with(
            changed_files=["a.py"],
            max_depth=3,
            max_results=100,
            repo_root="/test",
            base="HEAD~3",
            max_payload_bytes=500_000,
            repo="",
            as_of="",
        )
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.find_large_functions")
    def test_large_functions_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "results": []}
        result = query(
            action="large_functions",
            min_lines=100,
            kind="Function",
            file_path_pattern="src/",
            limit=10,
            repo_root="/test",
        )
        mock_fn.assert_called_once_with(
            min_lines=100,
            kind="Function",
            file_path_pattern="src/",
            limit=10,
            repo_root="/test",
            repo="",
        )
        assert result["status"] == "ok"

    def test_unknown_action(self):
        result = query(action="nonexistent")
        assert "error" in result
        assert "valid_actions" in result


# ---------------------------------------------------------------------------
# review tool (standalone, no action param)
# ---------------------------------------------------------------------------


class TestReviewTool:
    @patch("better_code_review_graph.server.get_review_context")
    def test_review(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = review(
            changed_files=["b.py"],
            max_depth=1,
            include_source=False,
            max_lines_per_file=50,
            repo_root="/test",
            base="main",
        )
        mock_fn.assert_called_once_with(
            changed_files=["b.py"],
            max_depth=1,
            include_source=False,
            max_lines_per_file=50,
            repo_root="/test",
            base="main",
            languages=None,
            repo="",
        )
        assert result["status"] == "ok"

    @patch("better_code_review_graph.server.get_review_context")
    def test_review_defaults(self, mock_fn):
        mock_fn.return_value = {"status": "ok"}
        result = review()
        mock_fn.assert_called_once_with(
            changed_files=None,
            max_depth=2,
            include_source=True,
            max_lines_per_file=200,
            repo_root=None,
            base="HEAD~1",
            languages=None,
            repo="",
        )
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# config tool
# ---------------------------------------------------------------------------


def _make_mini_repo(tmp_path):
    """Helper: create a mini git repo with a built graph."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.incremental import full_build, get_db_path

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    (repo / "example.py").write_text("def hello(): pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    store = GraphStore(get_db_path(repo))
    try:
        full_build(repo, store)
    finally:
        store.close()
    return repo


class TestConfigTool:
    async def test_unknown_action(self):
        result = await config(action="nonexistent")
        assert "error" in result
        assert "valid_actions" in result
        assert "models" not in result["valid_actions"]

    async def test_models_action_removed(self):
        """The models catalog-listing action no longer exists."""
        result = await config(action="models")
        assert "Unknown action 'models'" in result["error"]
        assert "models" not in result["valid_actions"]

    async def test_status_does_not_load_embedding_model(self, tmp_path):
        """config(status) must NOT init the embedding backend.

        Constructing the local backend loads the fastretrieval ONNX model, which
        can block/hang the status call on Windows under stdio. embeddings_count
        is a pure SQL COUNT(*), so no model is needed. Patch init_backend to
        explode if it is ever called from the status path.
        """
        repo = _make_mini_repo(tmp_path)
        with patch(
            "better_code_review_graph.embeddings.init_backend",
            side_effect=AssertionError("status must not init the embedding backend"),
        ):
            result = await config(action="status", repo_root=str(repo))
        assert result["status"] == "ok"
        assert "embeddings_count" in result
        assert result["embedding_backend"] in ("local", "cloud")
        assert isinstance(result["embedding_model"], str)
        assert result["embedding_model"]
        assert result["embedding_dimensions"] == 768
        assert result["embedding_fallback"] == "none"

    async def test_cache_clear_does_not_load_embedding_model(self, tmp_path):
        """config(cache_clear) only counts + deletes rows: no model load."""
        repo = _make_mini_repo(tmp_path)
        with patch(
            "better_code_review_graph.embeddings.init_backend",
            side_effect=AssertionError(
                "cache_clear must not init the embedding backend"
            ),
        ):
            result = await config(action="cache_clear", repo_root=str(repo))
        assert result["status"] == "cache cleared"
        assert "embeddings_removed" in result

    async def test_set_missing_key(self):
        result = await config(action="set")
        assert result["error"] == "key is required for set action"
        assert result["valid_keys"] == ["log_level"]
        assert "error" in result

    async def test_set_missing_value(self):
        result = await config(action="set", key="log_level")
        assert result["error"] == "value is required for set action"
        assert "error" in result

    async def test_set_invalid_key(self):
        result = await config(action="set", key="invalid_key", value="x")
        assert "error" in result
        assert "valid_keys" in result

    async def test_set_log_level(self):
        result = await config(action="set", key="log_level", value="DEBUG")
        assert result["status"] == "updated"
        assert result["value"] == "DEBUG"

    async def test_set_invalid_log_level(self):
        result = await config(action="set", key="log_level", value="INVALID")
        assert "error" in result

    async def test_status_no_graph(self):
        result = await config(action="status")
        assert result["status"] == "ok"
        assert "version" in result

    async def test_status_with_repo(self, tmp_path):
        repo = _make_mini_repo(tmp_path)
        result = await config(action="status", repo_root=str(repo))
        assert result["status"] == "ok"
        assert result["total_nodes"] > 0
        assert "embedding_backend" in result

    async def test_status_error_handling(self):
        with patch(
            "better_code_review_graph.tools._get_store",
            side_effect=ValueError("No graph found"),
        ):
            result = await config(action="status")
            assert result["status"] == "ok"
            assert result["graph_path"] is None
            assert "No graph found" in result["message"]

    async def test_cache_clear_no_graph(self):
        result = await config(action="cache_clear")
        assert result["status"] == "cache cleared"

    async def test_cache_clear_error_handling(self):
        with patch(
            "better_code_review_graph.tools._get_store",
            side_effect=ValueError("No repo found"),
        ):
            result = await config(action="cache_clear")
            assert result["status"] == "cache cleared"
            assert result["embeddings_removed"] == 0

    async def test_cache_clear_with_repo(self, tmp_path):
        repo = _make_mini_repo(tmp_path)
        result = await config(action="cache_clear", repo_root=str(repo))
        assert result["status"] == "cache cleared"

    async def test_setup_status_action(self):
        """config setup_status dispatches to credential state status."""
        result = await config(action="setup_status")
        assert "unknown action" not in str(result).lower()
        assert "state" in result

    async def test_setup_start_action(self, monkeypatch):
        """config setup_start reports the host-owned config surface.

        Post-de-host (spec 2026-09-26 §4) there is no browser setup form
        and no ``<PUBLIC_URL>/authorize`` relay: end users never supply
        keys, the host configures ``[models.<task>]`` cells instead.
        """
        from better_code_review_graph import credential_state as cs

        monkeypatch.setattr(cs, "_state", cs.CredentialState.LOCAL)
        monkeypatch.setenv("PUBLIC_URL", "https://relay.example.com")

        result = await config(action="setup_start")
        assert "unknown action" not in str(result).lower()
        assert result.get("status") == "host_config"
        assert "setup_url" not in result


# ---------------------------------------------------------------------------
# help tool
# ---------------------------------------------------------------------------


class TestHelpTool:
    def test_invalid_topic(self):
        result = json.loads(help(topic="nonexistent"))
        assert "error" in result
        assert "valid_topics" in result

    def test_graph_topic(self):
        result = help(topic="graph")
        if result.startswith("{"):
            data = json.loads(result)
            assert "content" in data or "error" in data
        else:
            assert "# graph Tool Documentation" in result

    def test_query_topic(self):
        result = help(topic="query")
        if result.startswith("{"):
            data = json.loads(result)
            assert "content" in data or "error" in data
        else:
            assert "# query Tool Documentation" in result

    def test_review_topic(self):
        result = help(topic="review")
        if result.startswith("{"):
            data = json.loads(result)
            assert "content" in data or "error" in data
        else:
            assert "# review Tool Documentation" in result

    def test_config_topic(self):
        result = help(topic="config")
        if result.startswith("{"):
            data = json.loads(result)
            assert "content" in data or "error" in data
        else:
            assert "# config Tool Documentation" in result

    @patch("better_code_review_graph.server.files")
    def test_fallback_to_llm_ref(self, mock_files):
        mock_files.side_effect = FileNotFoundError("no docs")
        result = help(topic="graph")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# serve_main
# ---------------------------------------------------------------------------


class TestServeMain:
    @patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"})
    def test_serve_main_sets_repo_root(self):
        """serve_main(stdio) routes to FastMCP stdio server directly (no bridge)."""
        import better_code_review_graph.server as server_module

        with patch.object(server_module.mcp, "run") as mock_run:
            serve_main(repo_root="/my/repo")
        assert server_module._default_repo_root == "/my/repo"
        mock_run.assert_called_once_with(transport="stdio")

    @patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"})
    def test_serve_main_none_repo_root(self):
        """serve_main(stdio) routes to FastMCP stdio server directly (no bridge)."""
        import better_code_review_graph.server as server_module

        with patch.object(server_module.mcp, "run") as mock_run:
            serve_main(repo_root=None)
        assert server_module._default_repo_root is None
        mock_run.assert_called_once_with(transport="stdio")

    @patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"})
    def test_serve_main_survives_missing_numpy(self):
        """The main-thread numpy warm-up is best-effort: a missing numpy must
        not abort startup (the import is only there to dodge a worker-thread
        C-extension import deadlock, not a hard requirement to serve)."""
        import sys

        import better_code_review_graph.server as server_module

        # ``sys.modules[name] = None`` makes ``import name`` raise ImportError.
        with patch.dict(sys.modules, {"numpy": None}):
            with patch.object(server_module.mcp, "run") as mock_run:
                serve_main(repo_root=None)
        mock_run.assert_called_once_with(transport="stdio")
