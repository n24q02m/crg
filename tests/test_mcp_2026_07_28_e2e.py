"""Real E2E tests for MCP 2026-07-28 over stdio and Streamable HTTP transports.

Exercises:
  - Skills extension (`skills/list`, `skills/get`, `skill://<name>/SKILL.md`)
  - Tasks extension (`ClientCreateTaskResult` -> `_drive_to_terminal` completion)
  - Graceful fallback when a client does NOT advertise task support (both
    2026-07-28 clients without TasksClientExtension and legacy 2025-11-25 clients)
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import mcp.types as mt
import pytest
from fastmcp.skills.extension import (
    GetSkillParams,
    GetSkillResult,
    ListSkillsParams,
    ListSkillsResult,
)
from fastmcp_tasks.client import TasksClientExtension, _drive_to_terminal
from fastmcp_tasks.client_models import ClientCreateTaskResult
from hull_core.auth.tokens import hash_token
from mcp import ClientSession, StdioServerParameters
from mcp.client._probe import negotiate_auto
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import (
    create_mcp_http_client,
    streamable_http_client,
)
from mcp.types import CallToolResult, TextContent
from tree_sitter_language_pack import cache_dir

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

_TIMEOUT_S = 90.0
_EXPECTED_SKILL_URIS = {
    "skill://impact-audit/SKILL.md",
    "skill://onboard-repo/SKILL.md",
    "skill://refactor-check/SKILL.md",
    "skill://review-delta/SKILL.md",
    "skill://review-pr/SKILL.md",
    "skill://security-sweep/SKILL.md",
}


def _text(result: CallToolResult) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent), block
    return block.text


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_port(port: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    pytest.fail(f"server did not open port {port} within {timeout}s")


def _base_env(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "CRG_DATA_DIR": str(tmp_path / "crg-data"),
        "EMBEDDING_BACKEND": "local",
        "TREE_SITTER_LANGUAGE_PACK_CACHE_DIR": str(Path(cache_dir()).parents[2]),
    }


@pytest.fixture()
def seeded_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init"],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(cmd, cwd=repo, capture_output=True, check=True)
    (repo / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n"
        "def calc(op, a, b):\n    return add(a, b)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True
    )
    return repo


@pytest.fixture()
def http_server(tmp_path: Path, seeded_repo: Path) -> Iterator[tuple[int, str]]:
    port = _free_port()
    token = "e2e-" + os.urandom(8).hex()
    cfg_dir = tmp_path / "crg-config"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        "[server]\n"
        'host = "127.0.0.1"\n'
        f"port = {port}\n"
        'auth = "token"\n'
        f'token_hash = "{hash_token(token)}"\n',
        encoding="utf-8",
    )
    env = {
        **_base_env(tmp_path),
        "CRG_CONFIG_DIR": str(cfg_dir),
    }
    server_log = tmp_path / "http_server.log"
    with open(server_log, "w", encoding="utf-8") as log_fh:
        proc = subprocess.Popen(
            [sys.executable, "-m", "crg", "--http"],
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_port(port, _TIMEOUT_S)
            yield port, token
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


async def _assert_skills_surface(session: ClientSession) -> None:
    """Assert `skills/list`, `skills/get`, and `skill://` resource reads."""
    listed = await session.send_request(
        mt.Request(method="skills/list", params=ListSkillsParams()),
        ListSkillsResult,
    )
    uris = {skill.uri for skill in listed.skills}
    assert uris == _EXPECTED_SKILL_URIS

    fetched = await session.send_request(
        mt.Request(
            method="skills/get",
            params=GetSkillParams(uri="skill://review-pr/SKILL.md"),
        ),
        GetSkillResult,
    )
    assert fetched.skill.uri == "skill://review-pr/SKILL.md"

    resource = await session.read_resource("skill://review-pr/SKILL.md")
    assert resource.contents
    first_content = resource.contents[0]
    assert isinstance(first_content, mt.TextResourceContents)
    assert "review-pr" in first_content.text


async def _run_task_and_assert_completed(
    session: ClientSession, tool_name: str, arguments: dict[str, object]
) -> dict[str, object]:
    created = await session.call_tool(tool_name, arguments, allow_claimed=True)
    assert isinstance(created, ClientCreateTaskResult), (
        f"expected task, got {created!r}"
    )
    assert created.result_type == "task"

    final = await _drive_to_terminal(session, created.task_id, None)
    assert final.status == "completed", final
    assert final.result is not None
    content = final.result.get("content", [])
    assert content and "text" in content[0], final.result
    return json.loads(content[0]["text"])


async def test_stdio_mcp_2026_07_28_skills_and_tasks(
    tmp_path: Path, seeded_repo: Path
) -> None:
    """Real stdio ClientSession tests Skills extension and Tasks execution."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "crg"],
        env=_base_env(tmp_path),
    )
    repo_str = str(seeded_repo)

    ext = TasksClientExtension()
    async with stdio_client(params) as (rd, wr):
        async with ClientSession(
            rd,
            wr,
            extensions={ext.identifier: ext.settings()},
            result_claims={ext.identifier: list(ext.claims())},
        ) as session:
            await negotiate_auto(session)
            assert session.protocol_version == "2026-07-28"
            caps_ext = getattr(session.server_capabilities, "extensions", None) or {}
            assert "io.modelcontextprotocol/skills" in caps_ext
            assert "io.modelcontextprotocol/tasks" in caps_ext

            await _assert_skills_surface(session)

            build_payload = await _run_task_and_assert_completed(
                session,
                "graph",
                {"action": "build", "full_rebuild": True, "repo_root": repo_str},
            )
            assert build_payload["status"] == "ok", build_payload

            sec_payload = await _run_task_and_assert_completed(
                session,
                "security",
                {"action": "rule_list", "engine": "heuristic"},
            )
            assert sec_payload["engine"] == "heuristic", sec_payload
            assert sec_payload["rules"], sec_payload


async def test_stdio_mcp_2026_07_28_non_task_fallback(
    tmp_path: Path, seeded_repo: Path
) -> None:
    """Stdio clients without task capability fall back to inline tool execution."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "crg"],
        env=_base_env(tmp_path),
    )
    repo_str = str(seeded_repo)

    # 1. Modern 2026-07-28 client WITHOUT TasksClientExtension -> inline fallback
    async with stdio_client(params) as (rd, wr):
        async with ClientSession(rd, wr) as session:
            await negotiate_auto(session)
            assert session.protocol_version == "2026-07-28"
            inline_res = await session.call_tool(
                "graph",
                {"action": "build", "full_rebuild": True, "repo_root": repo_str},
            )
            assert isinstance(inline_res, CallToolResult)
            build = json.loads(_text(inline_res))
            assert build["status"] == "ok", build

    # 2. Legacy 2025-11-25 client -> inline fallback
    async with stdio_client(params) as (rd, wr):
        async with ClientSession(rd, wr) as session:
            init = await session.initialize()
            assert init.protocol_version == "2025-11-25"
            legacy_res = await session.call_tool(
                "graph", {"action": "stats", "repo_root": repo_str}
            )
            assert isinstance(legacy_res, CallToolResult)
            assert json.loads(_text(legacy_res)).get("total_nodes", 0) > 0


async def test_streamable_http_mcp_2026_07_28_skills_tasks_and_fallback(
    http_server: tuple[int, str], seeded_repo: Path
) -> None:
    """Real Streamable HTTP ClientSession tests Skills, Tasks, and fallback."""
    port, token = http_server
    url = f"http://127.0.0.1:{port}/mcp"
    headers = {"Authorization": f"Bearer {token}"}
    repo_str = str(seeded_repo)

    # 1. Task-capable 2026-07-28 client over Streamable HTTP
    ext = TasksClientExtension()
    async with (
        create_mcp_http_client(headers=headers) as http_client,
        streamable_http_client(url, http_client=http_client) as (rd, wr),
    ):
        async with ClientSession(
            rd,
            wr,
            extensions={ext.identifier: ext.settings()},
            result_claims={ext.identifier: list(ext.claims())},
        ) as session:
            await negotiate_auto(session)
            assert session.protocol_version == "2026-07-28"
            caps_ext = getattr(session.server_capabilities, "extensions", None) or {}
            assert "io.modelcontextprotocol/skills" in caps_ext
            assert "io.modelcontextprotocol/tasks" in caps_ext

            await _assert_skills_surface(session)

            build_payload = await _run_task_and_assert_completed(
                session,
                "graph",
                {"action": "build", "full_rebuild": True, "repo_root": repo_str},
            )
            assert build_payload["status"] == "ok", build_payload

            scan_payload = await _run_task_and_assert_completed(
                session,
                "security",
                {"action": "scan", "engine": "heuristic", "repo_root": repo_str},
            )
            assert scan_payload["engine"] == "heuristic", scan_payload
            assert "total" in scan_payload, scan_payload

    # 2. Client WITHOUT TasksClientExtension over Streamable HTTP -> inline fallback
    async with (
        create_mcp_http_client(headers=headers) as http_client,
        streamable_http_client(url, http_client=http_client) as (rd, wr),
    ):
        async with ClientSession(rd, wr) as session:
            await negotiate_auto(session)
            inline_res = await session.call_tool(
                "graph", {"action": "stats", "repo_root": repo_str}
            )
            assert isinstance(inline_res, CallToolResult)
            stats = json.loads(_text(inline_res))
            assert stats.get("total_nodes", 0) > 0, stats
