"""Tests for the MCP server module (server.py) — 5-tool architecture."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import patch

import pytest
import uvicorn

from crg.config import ServerConfigError
from crg.server import (
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
        assert mcp.name == "crg"

    def test_mcp_instructions_present(self):
        instructions = getattr(mcp, "instructions", None) or getattr(
            mcp, "_instructions", None
        )
        if instructions is None:
            instructions = getattr(getattr(mcp, "settings", None), "instructions", None)
        if instructions is None:
            assert mcp.name == "crg"
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
    @patch("crg.server.build_or_update_graph")
    def test_build_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "build_type": "full"}
        result = graph(action="build", full_rebuild=True, repo_root="/test")
        mock_fn.assert_called_once_with(
            full_rebuild=True, repo_root="/test", base="HEAD~1", roots=None
        )
        assert result["status"] == "ok"

    @patch("crg.server.build_or_update_graph")
    def test_update_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "build_type": "incremental"}
        result = graph(action="update", repo_root="/test")
        mock_fn.assert_called_once_with(
            full_rebuild=False, repo_root="/test", base="HEAD~1"
        )
        assert result["status"] == "ok"

    @patch("crg.server.list_graph_stats")
    def test_stats_action(self, mock_fn):
        mock_fn.return_value = {"status": "ok", "total_nodes": 42}
        result = graph(action="stats", repo_root="/test")
        mock_fn.assert_called_once_with(repo_root="/test")
        assert result["status"] == "ok"

    @patch("crg.server.embed_graph")
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
    @patch("crg.server.query_graph")
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

    @patch("crg.server.semantic_search_nodes")
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

    @patch("crg.server.get_impact_radius")
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

    @patch("crg.server.find_large_functions")
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
    @patch("crg.server.get_review_context")
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

    @patch("crg.server.get_review_context")
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
    from crg.graph import GraphStore
    from crg.incremental import full_build, get_db_path

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
            "crg.embeddings.init_backend",
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
            "crg.embeddings.init_backend",
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
            "crg.tools._get_store",
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
            "crg.tools._get_store",
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
        and no ``<PUBLIC_URL>/authorize`` page: end users never supply
        keys, the host configures ``[models.<task>]`` cells instead.
        """
        from crg import credential_state as cs

        monkeypatch.setattr(cs, "_state", cs.CredentialState.LOCAL)
        monkeypatch.setenv("PUBLIC_URL", "https://crg.example.com")

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

    @patch("crg.server.files")
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
        import crg.server as server_module
        from crg.tools import get_default_repo_root, set_default_repo_root

        try:
            with patch.object(server_module.mcp, "run") as mock_run:
                serve_main(repo_root="/my/repo")
            assert server_module._default_repo_root == "/my/repo"
            # The default must propagate to tools so repo_root-less tool
            # calls resolve to it instead of the process cwd.
            assert get_default_repo_root() == "/my/repo"
            mock_run.assert_called_once_with(transport="stdio")
        finally:
            set_default_repo_root(None)

    @patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"})
    def test_serve_main_none_repo_root(self):
        """serve_main(stdio) routes to FastMCP stdio server directly (no bridge)."""
        import crg.server as server_module
        from crg.tools import set_default_repo_root

        try:
            with patch.object(server_module.mcp, "run") as mock_run:
                serve_main(repo_root=None)
            assert server_module._default_repo_root is None
            mock_run.assert_called_once_with(transport="stdio")
        finally:
            set_default_repo_root(None)

    @patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"})
    def test_serve_main_survives_missing_numpy(self):
        """The main-thread numpy warm-up is best-effort: a missing numpy must
        not abort startup (the import is only there to dodge a worker-thread
        C-extension import deadlock, not a hard requirement to serve)."""
        import sys

        import crg.server as server_module

        # ``sys.modules[name] = None`` makes ``import name`` raise ImportError.
        with patch.dict(sys.modules, {"numpy": None}):
            with patch.object(server_module.mcp, "run") as mock_run:
                serve_main(repo_root=None)
        mock_run.assert_called_once_with(transport="stdio")


class TestDefaultRepoRootResolution:
    """``_get_store`` must prefer the server-installed default over cwd.

    Regression coverage for the stdio wiring bug where ``serve_main``
    recorded ``_default_repo_root`` but every tool call that omitted
    ``repo_root`` still resolved the graph DB from the process cwd via
    ``find_project_root()``.
    """

    def _make_repo(self, base, name: str, marker_file: str, marker_func: str):
        """Create a plausible repo root with a uniquely-marked graph DB."""
        from crg.graph import GraphStore
        from crg.parser import NodeInfo

        repo = base / name
        repo.mkdir()
        # A bare .git dir is not enough: GraphStore's alembic migration
        # backfills valid_from_sha from .git/HEAD, so seed a minimal but
        # resolvable HEAD (symref + loose ref).
        gitdir = repo / ".git"
        (gitdir / "refs" / "heads").mkdir(parents=True)
        (gitdir / "HEAD").write_text("ref: refs/heads/main\n")
        (gitdir / "refs" / "heads" / "main").write_text("a" * 40 + "\n")
        (repo / ".crg").mkdir()
        (repo / marker_file).write_text(f"def {marker_func}():\n    pass\n")

        abs_marker = str((repo / marker_file).resolve())
        store = GraphStore(str(repo / ".crg" / "graph.db"))
        try:
            store.upsert_node(
                NodeInfo(
                    kind="File",
                    name=abs_marker,
                    file_path=abs_marker,
                    line_start=1,
                    line_end=2,
                    language="python",
                ),
                file_hash="h",
            )
            store.upsert_node(
                NodeInfo(
                    kind="Function",
                    name=marker_func,
                    file_path=abs_marker,
                    line_start=1,
                    line_end=2,
                    language="python",
                ),
                file_hash="h",
            )
            store.commit()
        finally:
            store.close()
        return repo, abs_marker, marker_func

    def test_default_root_wins_over_cwd(self, tmp_path, monkeypatch):
        """Default set to A while cwd sits inside B: repo_root-less calls
        must read A's database."""
        from crg.tools import list_graph_stats, query_graph, set_default_repo_root

        repo_a, marker_a, func_a = self._make_repo(
            tmp_path, "repo_a", "only_in_a.py", "func_only_in_a"
        )
        self._make_repo(tmp_path, "repo_b", "only_in_b.py", "func_only_in_b")
        monkeypatch.chdir(tmp_path / "repo_b")
        set_default_repo_root(str(repo_a))
        try:
            stats = list_graph_stats()
            assert stats["status"] == "ok", stats
            assert f"for {repo_a.name}" in stats["summary"]
            assert stats["total_nodes"] == 2

            result = query_graph(pattern="file_summary", target=marker_a)
            assert result["status"] == "ok", result
            assert func_a in [r["name"] for r in result["results"]]
        finally:
            set_default_repo_root(None)

    def test_explicit_repo_root_wins_over_default(self, tmp_path, monkeypatch):
        """An explicit ``repo_root`` argument takes precedence over the
        server-installed default."""
        from crg.tools import list_graph_stats, query_graph, set_default_repo_root

        repo_a, _, _ = self._make_repo(
            tmp_path, "repo_a", "only_in_a.py", "func_only_in_a"
        )
        repo_b, marker_b, func_b = self._make_repo(
            tmp_path, "repo_b", "only_in_b.py", "func_only_in_b"
        )
        monkeypatch.chdir(repo_a)
        set_default_repo_root(str(repo_a))
        try:
            stats = list_graph_stats(repo_root=str(repo_b))
            assert stats["status"] == "ok", stats
            assert f"for {repo_b.name}" in stats["summary"]
            assert stats["nodes_by_kind"] == {"File": 1, "Function": 1}

            result = query_graph(
                pattern="file_summary", target=marker_b, repo_root=str(repo_b)
            )
            assert result["status"] == "ok", result
            assert func_b in [r["name"] for r in result["results"]]
        finally:
            set_default_repo_root(None)

    def test_unset_default_falls_back_to_cwd(self, tmp_path, monkeypatch):
        """With no server default installed, repo_root-less calls keep the
        legacy behaviour of resolving from the process cwd."""
        from crg.tools import query_graph, set_default_repo_root

        repo_b, marker_b, func_b = self._make_repo(
            tmp_path, "repo_b", "only_in_b.py", "func_only_in_b"
        )
        set_default_repo_root(None)
        monkeypatch.chdir(repo_b)
        result = query_graph(pattern="file_summary", target=marker_b)
        assert result["status"] == "ok", result
        assert func_b in [r["name"] for r in result["results"]]

    def test_invalid_default_raises_through_validation(self, tmp_path, monkeypatch):
        """A server-installed default still goes through
        ``_validate_repo_root``: a path with no .git/.crg must error, not
        silently fall back to cwd."""
        import pytest

        from crg.tools import _get_store, set_default_repo_root

        bogus = tmp_path / "not_a_repo"
        bogus.mkdir()
        set_default_repo_root(str(bogus))
        try:
            with pytest.raises(ValueError, match="project root"):
                _get_store()
        finally:
            set_default_repo_root(None)


# ---------------------------------------------------------------------------
# no-auth loopback guard on the shared HTTP path (run_http)
# ---------------------------------------------------------------------------


class _RecordingServer:
    """Stands in for ``uvicorn.Server`` and records the bind it was given."""

    attempts: list[tuple[str | None, int]] = []

    def __init__(self, config_obj):
        self.config = config_obj
        _RecordingServer.attempts.append((config_obj.host, config_obj.port))

    async def serve(self) -> None:
        return None


class TestHttpEntryNoAuthLoopbackGuard:
    """Regression: the no-auth→loopback enforcement must live on the shared
    ``run_http`` path so EVERY HTTP entry gets it — the alternate entries
    (``python -m crg --http``, ``MCP_TRANSPORT=http``, ``TRANSPORT_MODE=http``)
    bypass the ``server start`` CLI pre-check and used to bind unauthenticated
    off-loopback.
    """

    @staticmethod
    def _arm_http_entry(monkeypatch, tmp_path, *, host) -> list:
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            f'[server]\nhost = "{host}"\nport = 61000\nauth = "no-auth"\n'
        )
        monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
        monkeypatch.delenv("MCP_TRANSPORT", raising=False)
        monkeypatch.delenv("TRANSPORT_MODE", raising=False)
        monkeypatch.delenv("MCP_PORT", raising=False)  # other tests leak it
        monkeypatch.setenv("MCP_HOST", host)
        monkeypatch.setattr(sys, "argv", ["crg"])
        _RecordingServer.attempts = []
        monkeypatch.setattr(uvicorn, "Server", _RecordingServer)
        return _RecordingServer.attempts

    @pytest.mark.parametrize(
        ("http_entry", "argv"),
        [
            ("mcp_transport", None),
            ("transport_mode", None),
            ("argv_flag", ["crg", "--http"]),
        ],
    )
    def test_no_auth_off_loopback_refused_on_every_http_entry(
        self, monkeypatch, tmp_path, http_entry, argv
    ):
        attempts = self._arm_http_entry(monkeypatch, tmp_path, host="0.0.0.0")
        if http_entry == "mcp_transport":
            monkeypatch.setenv("MCP_TRANSPORT", "http")
        elif http_entry == "transport_mode":
            monkeypatch.setenv("TRANSPORT_MODE", "http")
        else:
            monkeypatch.setattr(sys, "argv", argv)

        with pytest.raises(ServerConfigError, match="loopback"):
            serve_main()

        assert attempts == []  # the unauthenticated bind must never be attempted

    def test_no_auth_loopback_bind_allowed(self, monkeypatch, tmp_path):
        attempts = self._arm_http_entry(monkeypatch, tmp_path, host="127.0.0.1")
        monkeypatch.setenv("MCP_TRANSPORT", "http")

        serve_main()

        assert attempts == [("127.0.0.1", 61000)]
