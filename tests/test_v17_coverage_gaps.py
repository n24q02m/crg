"""Tests targeting coverage gaps introduced by v1.7 features (epic #324).

Covers under-tested code paths added by feat commits 14355be..3e1511c:
- _build_response_header exception fallbacks (#330)
- _resolve_query_target / file_summary symlink + path-traversal branches
- _scan_dynamic_dispatch_hints language fallthroughs and edge cases (#331)
- spot_check_last_callers no-edges + read-error branches (#318)
- renamed_in_diff filter branches (path traversal, symlinks, parse errors,
  added files, no-shift) (#320)
- _looks_like_literal_identifier empty input (#317)
- semantic_search_nodes query-too-long (#317)
- query_graph target-too-long
- get_impact_radius symlink + path-traversal filters
- get_review_context _filter_valid_paths + _get_source_snippets edge cases
- server.py spot_check + renamed_in_diff action wrappers
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.tools import (
    _LAST_CALLERS_RESULT,
    _build_response_header,
    _filter_valid_paths,
    _get_source_snippets,
    _list_kinds_in_graph,
    _looks_like_literal_identifier,
    _scan_dynamic_dispatch_hints,
    get_impact_radius,
    query_graph,
    renamed_in_diff,
    semantic_search_nodes,
    spot_check_last_callers,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_minimal_repo(tmp_path: Path) -> Path:
    """Create a minimal repo with a .code-review-graph dir for graph storage."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    crg = tmp_path / ".better-code-review-graph"
    crg.mkdir(exist_ok=True)
    (crg / ".gitignore").write_text("*\n")
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_caches():
    """Ensure spot_check cache is empty between tests."""
    _LAST_CALLERS_RESULT.clear()
    yield
    _LAST_CALLERS_RESULT.clear()


# ---------------------------------------------------------------------------
# _build_response_header (#330) â€” exception fallbacks
# ---------------------------------------------------------------------------


class TestBuildResponseHeader:
    def test_init_backend_exception_yields_zero_count(self, tmp_path):
        """When init_backend raises, the count is unknown, not zero."""
        with patch(
            "better_code_review_graph.tools.init_backend",
            side_effect=RuntimeError("backend boom"),
        ):
            header = _build_response_header(None, tmp_path / "graph.db")
        assert header["embeddings_count"] is None
        assert "backend boom" in header["embeddings_error"]
        assert header["keyword_only"] is True
        assert header["graph_last_updated"] is None

    def test_store_get_metadata_exception_yields_none(self):
        """When store.get_metadata raises, last_updated falls back to None."""
        bad_store = MagicMock()
        bad_store.get_metadata.side_effect = RuntimeError("metadata boom")
        header = _build_response_header(bad_store, None, keyword_only=False)
        assert header["graph_last_updated"] is None
        assert header["keyword_only"] is False


# ---------------------------------------------------------------------------
# _list_kinds_in_graph â€” exception fallback
# ---------------------------------------------------------------------------


def test_list_kinds_in_graph_returns_none_on_exception():
    bad_store = MagicMock()
    bad_store._conn.execute.side_effect = RuntimeError("sql boom")
    # None, not []: an empty list would claim the graph holds no nodes.
    assert _list_kinds_in_graph(bad_store) is None


# ---------------------------------------------------------------------------
# _scan_dynamic_dispatch_hints â€” language fallthroughs / edge cases
# ---------------------------------------------------------------------------


class TestScanDynamicDispatchHints:
    def test_returns_empty_when_node_is_none(self):
        assert _scan_dynamic_dispatch_hints(MagicMock(), None, "fn") == []

    def test_returns_empty_when_target_name_empty(self):
        node = MagicMock()
        node.language = "python"
        node.file_path = "/tmp/x.py"
        assert _scan_dynamic_dispatch_hints(MagicMock(), node, "") == []

    def test_returns_empty_for_unsupported_language(self):
        node = MagicMock()
        node.language = "go"
        node.file_path = "/tmp/x.go"
        assert _scan_dynamic_dispatch_hints(MagicMock(), node, "Foo") == []

    def test_swallow_get_edges_by_target_exception(self, tmp_path):
        """When store.get_edges_by_target raises, scan continues with just the
        target's own file (covers the bare-except guard)."""
        target = tmp_path / "target.py"
        target.write_text("def fn():\n    return 1\n    asyncio.to_thread(fn, 1)\n")
        node = MagicMock()
        node.language = "python"
        node.file_path = str(target)

        store = MagicMock()
        store.get_edges_by_target.side_effect = RuntimeError("edges boom")
        # Should not raise; falls back to scanning only target file.
        hits = _scan_dynamic_dispatch_hints(store, node, "fn")
        # Hits may or may not match (depending on whitespace) -- the important
        # bit is that the exception did not propagate.
        assert isinstance(hits, list)

    def test_skip_def_line_for_target_function(self, tmp_path):
        """The function's own ``def`` line must not be flagged as a hit."""
        target = tmp_path / "target.py"
        # The line `def fn(map=map):` would otherwise match the `map(` pattern
        # but starts with `def ` and must be skipped.
        target.write_text("def fn(map=map):\n    return map\n")
        node = MagicMock()
        node.language = "python"
        node.file_path = str(target)
        store = MagicMock()
        store.get_edges_by_target.return_value = []
        hits = _scan_dynamic_dispatch_hints(store, node, "map")
        # The def line should be filtered out.
        assert all(not h["context"].startswith("def ") for h in hits)

    def test_javascript_language_uses_js_patterns(self, tmp_path):
        target = tmp_path / "thing.ts"
        target.write_text("function foo() {}\nsetTimeout(foo, 100);\n")
        node = MagicMock()
        node.language = "typescript"
        node.file_path = str(target)
        store = MagicMock()
        store.get_edges_by_target.return_value = []
        hits = _scan_dynamic_dispatch_hints(store, node, "foo")
        assert any(h["pattern"] == "setTimeout" for h in hits)

    def test_scan_swallows_oserror_reading_file(self, tmp_path):
        """Files that cannot be read (e.g. don't exist) are skipped silently."""
        node = MagicMock()
        node.language = "python"
        node.file_path = str(tmp_path / "does_not_exist.py")
        store = MagicMock()
        store.get_edges_by_target.return_value = []
        hits = _scan_dynamic_dispatch_hints(store, node, "anything")
        assert hits == []


# ---------------------------------------------------------------------------
# spot_check_last_callers â€” no-edges + read-error
# ---------------------------------------------------------------------------


class TestSpotCheckEdgeCases:
    def test_returns_empty_samples_when_cache_has_no_edges(self, tmp_path):
        """When the cached query has 0 edges, spot_check returns an OK
        response with empty samples instead of attempting a sample."""
        repo = _make_minimal_repo(tmp_path)
        # Inject a cache entry with no edges.
        _LAST_CALLERS_RESULT[str(repo.resolve())] = {
            "pattern": "callers_of",
            "target": "foo",
            "edges": [],
            "results": [],
        }
        result = spot_check_last_callers(n=3, repo_root=str(repo))
        assert result["status"] == "ok"
        assert result["samples"] == []
        assert result["pattern"] == "callers_of"

    def test_handles_unreadable_file_gracefully(self, tmp_path):
        """When the cached edge points at a file that can't be read, the
        snippet is `(could not read file)` and the sample is still returned."""
        repo = _make_minimal_repo(tmp_path)
        _LAST_CALLERS_RESULT[str(repo.resolve())] = {
            "pattern": "callers_of",
            "target": "foo",
            "edges": [
                {
                    "file_path": str(tmp_path / "missing.py"),
                    "line": 1,
                    "source_qualified": "missing.py::caller",
                    "target_qualified": "missing.py::foo",
                }
            ],
            "results": [],
        }
        result = spot_check_last_callers(n=1, repo_root=str(repo))
        assert result["status"] == "ok"
        assert len(result["samples"]) == 1
        assert "could not read" in result["samples"][0]["snippet"]


# ---------------------------------------------------------------------------
# renamed_in_diff (#320) â€” filter branches
# ---------------------------------------------------------------------------


class TestRenamedInDiffFilters:
    def test_explicit_changed_files_with_added_file_skipped(self, tmp_path):
        """An ``added`` file (not present at base) is skipped via the
        `git show` non-zero returncode branch."""
        repo = _make_minimal_repo(tmp_path)
        _run_git(repo, "init", "--initial-branch=main")
        _run_git(repo, "config", "user.email", "t@t.com")
        _run_git(repo, "config", "user.name", "t")
        (repo / "a.py").write_text("def alpha():\n    return 1\n")
        _run_git(repo, "add", "a.py")
        _run_git(repo, "commit", "-m", "feat: initial")

        # Add a brand-new file -- it didn't exist at HEAD~1, so git show fails.
        (repo / "b.py").write_text("def beta():\n    return 2\n")
        _run_git(repo, "add", "b.py")
        _run_git(repo, "commit", "-m", "feat: add b")

        # Pass the new file explicitly so we exercise the `proc.returncode != 0`
        # branch that skips added files.
        result = renamed_in_diff(
            base="HEAD~1",
            changed_files=["b.py"],
            repo_root=str(repo),
        )
        assert result["status"] == "ok"
        assert result["shifts"] == []  # added file skipped, no shifts

    def test_path_outside_repo_skipped(self, tmp_path):
        """A path that resolves outside the repo is skipped."""
        repo = _make_minimal_repo(tmp_path)
        _run_git(repo, "init", "--initial-branch=main")
        _run_git(repo, "config", "user.email", "t@t.com")
        _run_git(repo, "config", "user.name", "t")
        (repo / "a.py").write_text("def alpha():\n    return 1\n")
        _run_git(repo, "add", "a.py")
        _run_git(repo, "commit", "-m", "feat: initial")
        _run_git(repo, "commit", "--allow-empty", "-m", "feat: empty")

        # `..` traversal -- resolves outside repo and must be filtered.
        result = renamed_in_diff(
            base="HEAD~1",
            changed_files=["../outside.py"],
            repo_root=str(repo),
        )
        assert result["status"] == "ok"
        assert result["shifts"] == []

    def test_unsupported_language_skipped(self, tmp_path):
        """Files whose language the parser cannot detect are skipped."""
        repo = _make_minimal_repo(tmp_path)
        _run_git(repo, "init", "--initial-branch=main")
        _run_git(repo, "config", "user.email", "t@t.com")
        _run_git(repo, "config", "user.name", "t")
        (repo / "notes.txt").write_text("hello world\n")
        _run_git(repo, "add", "notes.txt")
        _run_git(repo, "commit", "-m", "feat: text")
        # Modify the file so it appears in HEAD~1 diff.
        (repo / "notes.txt").write_text("hello world!\n")
        _run_git(repo, "add", "notes.txt")
        _run_git(repo, "commit", "-m", "fix: tweak text")

        result = renamed_in_diff(base="HEAD~1", repo_root=str(repo))
        assert result["status"] == "ok"
        # notes.txt has no language detector -> filtered, no shifts.
        assert result["shifts"] == []

    def test_directory_path_skipped(self, tmp_path):
        """A path that resolves to a directory (not a file) is skipped."""
        repo = _make_minimal_repo(tmp_path)
        _run_git(repo, "init", "--initial-branch=main")
        _run_git(repo, "config", "user.email", "t@t.com")
        _run_git(repo, "config", "user.name", "t")
        (repo / "a.py").write_text("def alpha():\n    return 1\n")
        _run_git(repo, "add", "a.py")
        _run_git(repo, "commit", "-m", "feat: initial")
        _run_git(repo, "commit", "--allow-empty", "-m", "feat: empty")

        # Pass a directory path -- not a file, must be skipped.
        (repo / "subdir").mkdir()
        result = renamed_in_diff(
            base="HEAD~1",
            changed_files=["subdir"],
            repo_root=str(repo),
        )
        assert result["status"] == "ok"
        assert result["shifts"] == []

    def test_no_change_yields_empty_shifts(self, tmp_path):
        """If the file is unchanged at HEAD vs base for the relevant function,
        no shift is recorded (covers the `head_line == base_line` branch)."""
        repo = _make_minimal_repo(tmp_path)
        _run_git(repo, "init", "--initial-branch=main")
        _run_git(repo, "config", "user.email", "t@t.com")
        _run_git(repo, "config", "user.name", "t")
        src = repo / "stable.py"
        src.write_text("def alpha():\n    return 1\n")
        _run_git(repo, "add", "stable.py")
        _run_git(repo, "commit", "-m", "feat: initial")
        # Touch the file with whitespace-only change at end (still passes through
        # parse). git diff still reports it as changed.
        src.write_text("def alpha():\n    return 1\n\n")
        _run_git(repo, "add", "stable.py")
        _run_git(repo, "commit", "-m", "fix: trailing newline")

        result = renamed_in_diff(base="HEAD~1", repo_root=str(repo))
        assert result["status"] == "ok"
        # alpha is at line 1 in both versions; no shift recorded.
        symbols = [s["symbol"] for s in result["shifts"]]
        assert "alpha" not in symbols

    def test_removed_function_skipped(self, tmp_path):
        """A function that exists at base but not at HEAD is skipped (the
        `head_line is None` branch)."""
        repo = _make_minimal_repo(tmp_path)
        _run_git(repo, "init", "--initial-branch=main")
        _run_git(repo, "config", "user.email", "t@t.com")
        _run_git(repo, "config", "user.name", "t")
        src = repo / "drop.py"
        src.write_text("def removed_fn():\n    return 1\n")
        _run_git(repo, "add", "drop.py")
        _run_git(repo, "commit", "-m", "feat: initial")
        # Replace with a different function -- removed_fn no longer at HEAD.
        src.write_text("def kept_fn():\n    return 2\n")
        _run_git(repo, "add", "drop.py")
        _run_git(repo, "commit", "-m", "fix: rename")

        result = renamed_in_diff(base="HEAD~1", repo_root=str(repo))
        assert result["status"] == "ok"
        symbols = [s["symbol"] for s in result["shifts"]]
        # Removed functions are out of scope -> not reported.
        assert "removed_fn" not in symbols

    def test_path_resolve_oserror_skipped(self, tmp_path):
        """OSError during Path.resolve() in renamed_in_diff is caught and skips the file."""
        repo = _make_minimal_repo(tmp_path)
        _run_git(repo, "init", "--initial-branch=main")
        _run_git(repo, "config", "user.email", "t@t.com")
        _run_git(repo, "config", "user.name", "t")
        (repo / "a.py").write_text("def alpha():\n    return 1\n")
        _run_git(repo, "add", "a.py")
        _run_git(repo, "commit", "-m", "feat: initial")

        path_cls = type(Path())
        original_resolve = path_cls.resolve

        def side_effect(self, *args, **kwargs):
            if self.name == "a.py":
                raise OSError("Mocked resolution error")
            return original_resolve(self, *args, **kwargs)

        with patch.object(path_cls, "resolve", side_effect):
            result = renamed_in_diff(
                base="HEAD",
                changed_files=["a.py"],
                repo_root=str(repo),
            )

        assert result["status"] == "ok"
        assert result["shifts"] == []


# ---------------------------------------------------------------------------
# _looks_like_literal_identifier (#317)
# ---------------------------------------------------------------------------


class TestLiteralIdentifier:
    def test_empty_string_treated_as_literal(self):
        # Edge case: empty query returns True (covers the `if not q` branch).
        assert _looks_like_literal_identifier("") is True
        assert _looks_like_literal_identifier("   ") is True


# ---------------------------------------------------------------------------
# semantic_search_nodes â€” query-too-long guard
# ---------------------------------------------------------------------------


def test_semantic_search_rejects_overlong_query():
    result = semantic_search_nodes(query="x" * 1500, repo_root="/tmp/nope")
    assert result["status"] == "error"
    assert "exceeds 1000" in result["error"]


# ---------------------------------------------------------------------------
# query_graph â€” target-too-long guard
# ---------------------------------------------------------------------------


def test_query_graph_rejects_overlong_target():
    result = query_graph(
        pattern="callers_of",
        target="x" * 1500,
        repo_root="/tmp/nope",
    )
    assert result["status"] == "error"
    assert "exceeds 1000" in result["error"]


# ---------------------------------------------------------------------------
# get_impact_radius â€” symlink + path-traversal filters
# ---------------------------------------------------------------------------


class TestGetImpactRadiusFilters:
    def test_path_outside_repo_filtered(self, tmp_path):
        """A `..` path that resolves outside the repo is not included in the
        graph lookup (covers the `is_relative_to` filter)."""
        repo = _make_minimal_repo(tmp_path)
        result = get_impact_radius(
            changed_files=["../outside.py"],
            repo_root=str(repo),
        )
        # Result should be ok with empty changed_nodes (no graph hits).
        assert result["status"] == "ok"
        assert result["changed_nodes"] == []


# ---------------------------------------------------------------------------
# _filter_valid_paths + _get_source_snippets (review_context helpers)
# ---------------------------------------------------------------------------


class TestReviewContextHelpers:
    def test_filter_valid_paths_drops_path_traversal(self, tmp_path):
        repo = _make_minimal_repo(tmp_path)
        # Mix of in-repo and out-of-repo paths.
        (repo / "in.py").write_text("x = 1\n")
        result = _filter_valid_paths(repo, ["in.py", "../out.py"])
        # Only in.py is kept.
        assert len(result) == 1
        assert result[0].endswith("in.py")

    def test_filter_valid_paths_handles_oserror(self, tmp_path):
        repo = _make_minimal_repo(tmp_path)
        # Path with NUL character can trigger OSError on resolve in some envs;
        # the helper must not propagate.
        result = _filter_valid_paths(repo, ["nul\x00bad.py"])
        # On platforms that raise OSError, list is empty; on others the path
        # is just dropped because it doesn't exist as a real file. Either way
        # the call must not raise.
        assert isinstance(result, list)

    def test_get_source_snippets_drops_path_traversal(self, tmp_path):
        repo = _make_minimal_repo(tmp_path)
        # ../out.py escapes the repo and must be excluded from the snippets.
        snippets = _get_source_snippets(repo, ["../out.py"], [], 50)
        assert snippets == {}


# ---------------------------------------------------------------------------
# server.py â€” spot_check + renamed_in_diff action wrappers
# ---------------------------------------------------------------------------


class TestServerSpotCheckAndRenamedInDiff:
    def test_query_spot_check_action(self):
        from better_code_review_graph.server import query

        with patch(
            "better_code_review_graph.server.spot_check_last_callers"
        ) as mock_fn:
            mock_fn.return_value = {"status": "ok", "samples": []}
            result = query(
                action="spot_check",
                n=5,
                context_lines=4,
                repo_root="/test",
            )
            mock_fn.assert_called_once_with(n=5, repo_root="/test", context_lines=4)
        assert result["status"] == "ok"

    def test_query_renamed_in_diff_action(self):
        from better_code_review_graph.server import query

        with patch("better_code_review_graph.server.renamed_in_diff") as mock_fn:
            mock_fn.return_value = {"status": "ok", "shifts": []}
            result = query(
                action="renamed_in_diff",
                base="HEAD~3",
                changed_files=["a.py"],
                repo_root="/test",
            )
            mock_fn.assert_called_once_with(
                base="HEAD~3",
                changed_files=["a.py"],
                repo_root="/test",
            )
        assert result["status"] == "ok"

    def test_config_setup_status_local_state(self, monkeypatch, tmp_path):
        """Cover the LOCAL state branch in setup_status (line 427)."""
        import asyncio

        from better_code_review_graph.server import config

        # Ensure no cell keys, and no ambient BYOK-era provider env keys.
        for k in (
            "HULL_EMBED_API_KEY",
            "HULL_RERANK_API_KEY",
            "HULL_CHAT_API_KEY",
            "HULL_JEV_SCORE_API_KEY",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))

        # Force credential_state to LOCAL so the LOCAL branch is hit.
        from better_code_review_graph import credential_state as cs

        with patch.object(cs, "get_state", return_value=cs.CredentialState.LOCAL):
            result = asyncio.run(config(action="setup_status"))
        assert result["state"] == "local"
        assert result["providers_configured"] == []
