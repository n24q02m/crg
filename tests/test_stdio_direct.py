"""Verify crg runs in stdio direct mode (no smart_stdio bridge).

Spawns ``python -m crg`` with ``MCP_TRANSPORT=stdio`` and
exercises the JSON-RPC handshake plus ``tools/list`` to prove the FastMCP stdio
server is wired directly (no daemon-spawn bridge layer in front of it).

Marked ``full`` because it spawns a real subprocess and speaks the MCP
protocol; excluded from the default ``pytest`` invocation but runs under
``uv run pytest -m full``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.full, pytest.mark.timeout(60)]


def _spawn_stdio_server() -> subprocess.Popen[str]:
    """Start ``python -m crg`` with stdio transport.

    Returns the running subprocess. Caller is responsible for terminating it.
    """
    env = {**os.environ, "MCP_TRANSPORT": "stdio"}
    return subprocess.Popen(
        [sys.executable, "-m", "crg"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
    )


def _read_response(proc: subprocess.Popen[str]) -> dict:
    """Read one JSON-RPC line from stdout, parsed as dict."""
    assert proc.stdout is not None and proc.stderr is not None
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read()
        raise RuntimeError(
            f"server closed stdout without sending a response. stderr=\n{stderr}"
        )
    return json.loads(line)


def test_stdio_direct_init_responds():
    """Spawn the server with MCP_TRANSPORT=stdio; verify init response shape."""
    proc = _spawn_stdio_server()
    assert proc.stdin is not None
    init_request = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
        )
        + "\n"
    )
    try:
        proc.stdin.write(init_request)
        proc.stdin.flush()
        response = _read_response(proc)
        assert response["id"] == 1
        assert "result" in response, f"unexpected response: {response}"
        # FastMCP negotiates protocol version; just assert it returned one.
        assert "protocolVersion" in response["result"]
        assert response["result"]["serverInfo"]["name"] == "crg"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_stdio_direct_tools_list_returns_expected_tools():
    """Verify tools/list returns the expected crg tool set over stdio."""
    proc = _spawn_stdio_server()
    assert (
        proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    )
    requests = [
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
        ),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
    ]
    try:
        for r in requests:
            proc.stdin.write(r + "\n")
            proc.stdin.flush()
        responses: dict[int, dict] = {}
        while len(responses) < 2:
            line = proc.stdout.readline()
            if not line:
                stderr = proc.stderr.read()
                raise RuntimeError(
                    f"server closed stdout before tools/list response. "
                    f"stderr=\n{stderr}"
                )
            data = json.loads(line)
            if "id" in data:
                responses[data["id"]] = data
        assert 2 in responses, f"missing tools/list response: {responses}"
        tools = responses[2]["result"]["tools"]
        tool_names = {t["name"] for t in tools}
        # Core crg tools that must be exposed in stdio mode.
        expected = {"graph", "query", "review", "config", "help"}
        assert expected.issubset(tool_names), (
            f"missing tools: {expected - tool_names}; got: {tool_names}"
        )
        assert len(tools) >= 4
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
