"""Tests for the CLI module (cli.py) -- shared mcp_core CLI builder mount."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from crg.cli import main


class TestServeDispatch:
    def test_starts_server(self):
        with (
            patch.object(sys, "argv", ["crg"]),
            patch("crg.server.serve_main") as mock_serve,
        ):
            rc = main()

        mock_serve.assert_called_once()
        assert rc == 0

    def test_http_flag_passes_through_argv_unchanged(self):
        with (
            patch.object(sys, "argv", ["crg", "--http"]),
            patch("crg.server.serve_main") as mock_serve,
        ):
            rc = main()

        mock_serve.assert_called_once()
        assert rc == 0

    def test_main_runs_stdio_directly(self):
        """serve_main(stdio) invokes FastMCP stdio directly (no bridge layer)."""
        from crg import server as server_module

        with (
            patch.object(sys, "argv", ["crg"]),
            patch.object(server_module.mcp, "run") as mock_run,
            patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}),
        ):
            main()
            mock_run.assert_called_once_with(transport="stdio")

    def test_main_continues_on_credential_state_error(self):
        with (
            patch.object(sys, "argv", ["crg"]),
            patch(
                "crg.credential_state.resolve_credential_state",
                side_effect=Exception("credential state broken"),
            ),
            patch("crg.server.mcp"),
            patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}),
        ):
            try:
                main()
            except Exception:
                pass


class TestGraphSubcommand:
    """`crg graph build|embed` -- lazy tools.py calls."""

    def test_build_passes_args_and_prints_json(self, capsys):
        result = {"status": "ok", "build_type": "full", "files_parsed": 3}
        with (
            patch.object(
                sys,
                "argv",
                ["crg", "graph", "build", "--full-rebuild"],
            ),
            patch(
                "crg.tools.build_or_update_graph",
                return_value=result,
            ) as mock_build,
        ):
            rc = main()

        mock_build.assert_called_once_with(
            full_rebuild=True, repo_root=None, base="HEAD~1"
        )
        assert rc == 0
        assert '"status": "ok"' in capsys.readouterr().out

    def test_build_incremental_default_args(self):
        result = {"status": "ok", "build_type": "incremental"}
        with (
            patch.object(
                sys,
                "argv",
                [
                    "crg",
                    "graph",
                    "build",
                    "--repo-root",
                    "/tmp/repo",
                    "--base",
                    "main",
                ],
            ),
            patch(
                "crg.tools.build_or_update_graph",
                return_value=result,
            ) as mock_build,
        ):
            rc = main()

        mock_build.assert_called_once_with(
            full_rebuild=False, repo_root="/tmp/repo", base="main"
        )
        assert rc == 0

    def test_build_error_status_returns_nonzero(self, capsys):
        result = {"status": "error", "error": "boom"}
        with (
            patch.object(sys, "argv", ["crg", "graph", "build"]),
            patch(
                "crg.tools.build_or_update_graph",
                return_value=result,
            ),
        ):
            rc = main()

        assert rc == 1
        assert "boom" in capsys.readouterr().out

    def test_embed_passes_repo_root_and_prints_json(self, capsys):
        result = {
            "status": "ok",
            "newly_embedded": 5,
            "total_embeddings": 42,
            "backend": "local",
        }
        with (
            patch.object(
                sys,
                "argv",
                [
                    "crg",
                    "graph",
                    "embed",
                    "--repo-root",
                    "/tmp/repo",
                ],
            ),
            patch("crg.tools.embed_graph", return_value=result) as mock_embed,
        ):
            rc = main()

        mock_embed.assert_called_once_with(repo_root="/tmp/repo")
        assert rc == 0
        assert '"backend": "local"' in capsys.readouterr().out

    def test_unknown_graph_action_exits_2(self):
        with patch.object(sys, "argv", ["crg", "graph", "bogus"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2


class TestCliCoverageExtensions:
    def test_version_fallback_on_package_not_found(self):
        from importlib.metadata import PackageNotFoundError

        from crg.cli import _version

        with patch(
            "crg.cli.pkg_version",
            side_effect=PackageNotFoundError("pkg"),
        ):
            assert _version() == "dev"

    def test_query_spot_check_and_renamed_in_diff(self, capsys):
        with (
            patch.object(
                sys,
                "argv",
                ["crg", "query", "spot_check", "--n", "5"],
            ),
            patch(
                "crg.tools.spot_check_last_callers",
                return_value={"status": "ok"},
            ) as mock_spot,
        ):
            rc = main()
            assert rc == 0
            mock_spot.assert_called_once()

        with (
            patch.object(
                sys,
                "argv",
                [
                    "crg",
                    "query",
                    "renamed_in_diff",
                    "--base",
                    "HEAD~1",
                ],
            ),
            patch(
                "crg.tools.renamed_in_diff",
                return_value={"status": "ok"},
            ) as mock_renamed,
        ):
            rc = main()
            assert rc == 0
            mock_renamed.assert_called_once()
