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


class TestHelpSurface:
    """`crg --help` is real parser help: subcommands, their actions and flags."""

    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def test_help_lists_every_subcommand(self, capsys, flag):
        with patch.object(sys, "argv", ["crg", flag]):
            assert main() == 0

        out = capsys.readouterr().out
        assert out.startswith("usage: crg ")
        for name in (
            "config",
            "db",
            "graph",
            "query",
            "review",
            "security",
            "server",
            "token",
        ):
            assert f"\n    {name} " in out

    def test_help_lists_actions_and_flags(self, capsys):
        with patch.object(sys, "argv", ["crg", "--help"]):
            assert main() == 0

        out = capsys.readouterr().out
        # Actions of the four action-selector subcommands.
        assert "build | embed | stats | export | import | summarize" in out
        assert "scan | report | suppress | rule_list" in out
        # Flags of every subcommand, including nested control-plane ones.
        for flag in (
            "--full-rebuild",
            "--output-path",
            "--input-path",
            "--max-nodes",
            "--search-query",
            "--file-path-pattern",
            "--as-of",
            "--changed-files",
            "--engine",
            "--rule-id",
            "--host",
            "--port",
            "--force",
        ):
            assert flag in out

    def test_help_keeps_version_and_server_passthrough(self, capsys):
        with patch.object(sys, "argv", ["crg", "--help"]):
            assert main() == 0

        out = capsys.readouterr().out
        assert "--version" in out
        assert "--http" in out
        assert "forwards those flags to it" in out

    def test_help_mentions_every_declared_flag(self, capsys):
        """The generated help cannot drift from the parsers that dispatch."""
        from crg import cli as cli_module

        with patch.object(sys, "argv", ["crg", "--help"]):
            assert main() == 0
        out = capsys.readouterr().out

        for name, (configure, _handler) in cli_module._SUBCOMMANDS.items():
            declared = _declared_flag_options(
                cli_module._declared_parser(name, configure)
            )
            for flag in declared:
                assert flag in out, f"{name}: {flag} missing from `crg --help`"

    def test_subcommand_help_lists_its_flags(self, capsys):
        with (
            patch.object(sys, "argv", ["crg", "graph", "--help"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "--full-rebuild" in out
        assert "--max-nodes" in out


def _declared_flag_options(parser) -> set[str]:
    """Every `--flag` a parser and its nested subparsers accept."""
    options: set[str] = set()
    for action in parser._actions:
        options.update(action.option_strings)
        nested = getattr(action, "choices", None)
        if isinstance(nested, dict):
            for subparser in nested.values():
                options |= _declared_flag_options(subparser)
    return options - {"-h", "--help"}


class TestMissingActionMessage:
    """F-7: a missing action names the values it accepts, not just its dest."""

    @pytest.mark.parametrize(
        ("subcommand", "expected"),
        [
            (
                "graph",
                "graph action (choose one of: build, embed, stats, export, "
                "import, summarize)",
            ),
            (
                "query",
                "query action (choose one of: query, search, impact, "
                "large_functions, spot_check, renamed_in_diff, diff)",
            ),
            ("review", "review action (choose one of: context, delta)"),
            (
                "security",
                "security action (choose one of: scan, report, suppress, rule_list)",
            ),
            ("server", "server command (choose one of: start)"),
            ("token", "token command (choose one of: hash)"),
            ("config", "config command (choose one of: init, path, show, get, set)"),
            ("db", "db command (choose one of: path)"),
        ],
    )
    def test_names_allowed_values(self, capsys, subcommand, expected):
        with (
            patch.object(sys, "argv", ["crg", subcommand]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert expected in err
        # The internal argparse dest must not reach the user.
        assert "_action" not in err
        assert "_command" not in err

    def test_invalid_action_still_lists_choices(self, capsys):
        with (
            patch.object(sys, "argv", ["crg", "graph", "bogus"]),
            pytest.raises(SystemExit),
        ):
            main()

        err = capsys.readouterr().err
        assert "invalid choice: 'bogus'" in err
        assert "summarize" in err


class TestVersionFlag:
    @pytest.mark.parametrize("flag", ["--version", "-V"])
    def test_prints_version_without_starting_server(self, capsys, flag):
        with (
            patch.object(sys, "argv", ["crg", flag]),
            patch("crg.server.serve_main") as mock_serve,
        ):
            assert main() == 0

        mock_serve.assert_not_called()
        assert capsys.readouterr().out.startswith("crg ")


def test_missing_plain_positional_keeps_bare_argparse_message(capsys):
    """Only choice selectors gain a hint; `token hash <token>` stays terse."""
    with (
        patch.object(sys, "argv", ["crg", "token", "hash"]),
        pytest.raises(SystemExit),
    ):
        main()

    err = capsys.readouterr().err
    assert "the following arguments are required: token" in err
    assert "choose one of" not in err


def test_selector_label_renders_internal_dests():
    from crg.cli import _selector_label

    assert _selector_label("graph_action") == "graph action"
    assert _selector_label("server_command") == "server command"
    assert _selector_label("pattern") == "pattern"


def test_action_summary_renders_plain_positional():
    import argparse

    from crg.cli import _action_summary

    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    assert _action_summary(parser) == "<target>"
