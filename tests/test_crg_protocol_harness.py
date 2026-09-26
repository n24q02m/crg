"""Real stdio MCP protocol and CLI parity tests for CRG local harness.

Exercises:
1. Direct stdio FastMCP transport session via MCP ClientSession / stdio_client
2. Representative domain calls: graph, query, review, security, help, config
3. Structural output assertions, repository scoping, and error handling
4. Parity check between CLI and MCP outputs on a real repository fixture
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


def _json_payload(content: object) -> dict[str, Any]:
    """Decode the text payload returned by the MCP test server."""
    assert isinstance(content, TextContent)
    payload = json.loads(content.text)
    assert isinstance(payload, dict)
    return payload


@pytest.fixture
def repo_fixture(tmp_path: Path) -> Path:
    """Create a git repository fixture with multiple connected Python symbols."""
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True
    )

    # Initial file: auth.py
    auth_py = repo_dir / "auth.py"
    auth_py.write_text(
        "def verify_token(token: str) -> bool:\n"
        "    if not token:\n"
        "        return False\n"
        "    return True\n\n"
        "def authenticate_user(username: str, token: str) -> dict:\n"
        "    if verify_token(token):\n"
        "        return {'user': username, 'authenticated': True}\n"
        "    return {'user': username, 'authenticated': False}\n",
        encoding="utf-8",
    )

    # Initial file: app.py
    app_py = repo_dir / "app.py"
    app_py.write_text(
        "from auth import authenticate_user\n\n"
        "def handle_login(request: dict) -> dict:\n"
        "    user = request.get('user', '')\n"
        "    token = request.get('token', '')\n"
        "    return authenticate_user(user, token)\n\n"
        "def main():\n"
        "    res = handle_login({'user': 'alice', 'token': 'secret123'})\n"
        "    print(res)\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True)

    # Second commit modifying app.py
    app_py.write_text(
        "from auth import authenticate_user\n\n"
        "def handle_login(request: dict) -> dict:\n"
        "    user = request.get('user', '')\n"
        "    token = request.get('token', '')\n"
        "    # Added audit log\n"
        "    return authenticate_user(user, token)\n\n"
        "def main():\n"
        "    res = handle_login({'user': 'alice', 'token': 'secret123'})\n"
        "    print(res)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "app.py"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Update app.py"], cwd=repo_dir, check=True)

    return repo_dir


async def _run_cli(*args: str) -> tuple[int, str, str]:
    """Run a CLI subcommand without blocking the MCP event loop."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "better_code_review_graph.cli",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise AssertionError(f"CLI timed out: {args}") from exc
    return proc.returncode or 0, stdout.decode(), stderr.decode()


@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_mcp_protocol_and_cli_parity(repo_fixture: Path):
    """Test full MCP stdio protocol and assert parity with CLI subcommands."""
    env = {
        **os.environ,
        "MCP_TRANSPORT": "stdio",
        "PYTHONUNBUFFERED": "1",
    }
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "better_code_review_graph"],
        env=env,
    )

    repo_str = str(repo_fixture.resolve())

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # 1. Tools list
            tools_result = await session.list_tools()
            tool_names = {t.name for t in tools_result.tools}
            expected_tools = {
                "graph",
                "query",
                "review",
                "config",
                "help",
                "security",
            }
            assert expected_tools.issubset(tool_names), (
                f"Missing tools: {expected_tools - tool_names}"
            )

            # 2. graph(action="build", full_rebuild=True)
            res_build = await session.call_tool(
                "graph",
                {"action": "build", "full_rebuild": True, "repo_root": repo_str},
            )
            assert len(res_build.content) > 0
            build_payload = _json_payload(res_build.content[0])
            assert (
                build_payload.get("status") in ("ok", "success")
                or "files_parsed" in build_payload
                or "total_nodes" in build_payload
            )

            # 3. graph(action="stats")
            res_stats = await session.call_tool(
                "graph", {"action": "stats", "repo_root": repo_str}
            )
            stats_mcp = _json_payload(res_stats.content[0])
            assert stats_mcp.get("total_nodes", 0) > 0

            # 4. query(action="query", pattern="callers_of", target="verify_token")
            res_query = await session.call_tool(
                "query",
                {
                    "action": "query",
                    "pattern": "callers_of",
                    "target": "verify_token",
                    "repo_root": repo_str,
                },
            )
            query_mcp = _json_payload(res_query.content[0])
            assert len(query_mcp.get("results", [])) > 0
            caller_names_mcp = [r.get("name") for r in query_mcp["results"]]
            assert "authenticate_user" in caller_names_mcp
            assert all(
                str(result["file_path"]).lower().startswith(repo_str.lower())
                for result in query_mcp["results"]
                if result.get("file_path")
            )

            # Explicit structured error path: oversized target is rejected.
            res_error = await session.call_tool(
                "query",
                {
                    "action": "query",
                    "pattern": "callers_of",
                    "target": "x" * 1001,
                    "repo_root": repo_str,
                },
            )
            error_payload = _json_payload(res_error.content[0])
            assert error_payload["status"] == "error"
            assert "1000" in error_payload["error"]

            # 5. query(action="search", search_query="authenticate_user")
            res_search = await session.call_tool(
                "query",
                {
                    "action": "search",
                    "search_query": "authenticate_user",
                    "repo_root": repo_str,
                },
            )
            search_mcp = _json_payload(res_search.content[0])
            assert len(search_mcp.get("results", [])) > 0
            assert any(
                "authenticate_user" in r.get("name", "") for r in search_mcp["results"]
            )

            # 6. review(action="context", base="HEAD~1")
            res_rev = await session.call_tool(
                "review",
                {
                    "action": "context",
                    "base": "HEAD~1",
                    "repo_root": repo_str,
                },
            )
            rev_mcp = _json_payload(res_rev.content[0])
            assert "changed_files" in rev_mcp or "summary" in rev_mcp

            # 7. security(action="scan", engine="heuristic")
            res_sec = await session.call_tool(
                "security",
                {
                    "action": "scan",
                    "engine": "heuristic",
                    "repo_root": repo_str,
                },
            )
            sec_mcp = _json_payload(res_sec.content[0])
            assert "total" in sec_mcp

            # 8. config(action="status")
            res_cfg = await session.call_tool(
                "config", {"action": "status", "repo_root": repo_str}
            )
            cfg_mcp = _json_payload(res_cfg.content[0])
            assert "status" in cfg_mcp or "files_count" in cfg_mcp

            # 9. help(topic="graph")
            res_help = await session.call_tool("help", {"topic": "graph"})
            help_content = res_help.content[0]
            assert isinstance(help_content, TextContent)
            help_text = help_content.text
            assert "graph" in help_text.lower()
    # Run CLI in a clean process after the stdio server has released its DB.
    cli_rc, cli_stdout, cli_stderr = await _run_cli(
        "graph",
        "stats",
        "--repo-root",
        repo_str,
    )
    assert cli_rc == 0, cli_stderr
    stats_cli = json.loads(cli_stdout)
    assert stats_cli["total_nodes"] == stats_mcp["total_nodes"]
    assert stats_cli["files_count"] == stats_mcp["files_count"]

    cli_rc, cli_stdout, cli_stderr = await _run_cli(
        "query",
        "query",
        "--pattern",
        "callers_of",
        "--target",
        "verify_token",
        "--repo-root",
        repo_str,
    )
    assert cli_rc == 0, cli_stderr
    query_cli = json.loads(cli_stdout)
    assert "results" in query_cli, query_cli
    caller_names_cli = [r.get("name") for r in query_cli["results"]]
    assert caller_names_cli == caller_names_mcp
    cli_rc, cli_stdout, cli_stderr = await _run_cli(
        "query",
        "impact",
        "--repo-root",
        repo_str,
        "--max-depth",
        "2",
    )
    assert cli_rc == 0, cli_stderr
    impact_cli = json.loads(cli_stdout)
    assert impact_cli["status"] == "ok"
    assert "impacted_files" in impact_cli

    cli_rc, cli_stdout, cli_stderr = await _run_cli(
        "review",
        "context",
        "--base",
        "HEAD~1",
        "--repo-root",
        repo_str,
    )
    assert cli_rc == 0, cli_stderr
    rev_cli = json.loads(cli_stdout)
    assert ("changed_files" in rev_cli) == ("changed_files" in rev_mcp)

    cli_rc, cli_stdout, cli_stderr = await _run_cli(
        "security",
        "scan",
        "--engine",
        "heuristic",
        "--repo-root",
        repo_str,
    )
    assert cli_rc == 0, cli_stderr
    sec_cli = json.loads(cli_stdout)
    assert sec_cli["total"] == sec_mcp["total"]
