"""WP2 acceptance e2e (dehost plan): lifecycle ``server start`` + HTTP MCP.

Chain under test:
  1. tmp instance config (``CRG_CONFIG_DIR``) in token mode, hash produced by
     hull-core's ``hash_token`` (same primitive as the ``token hash`` CLI).
  2. ``python -m crg server start`` subprocess (host
     control plane restored on wp2-wip).
  3. streamable-http MCP client: initialize / list_tools / graph build /
     query callers_of over ``/mcp`` with a bearer token.
  4. Negative: no bearer -> handshake fails (auth middleware rejects).

Data dir is redirected via ``CRG_DATA_DIR`` so the per-sub graph.db stays in
tmp (mode-3 isolation path is unit-covered in test_credential_state.py).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from hull_core.auth.tokens import hash_token
from mcp import ClientSession
from mcp.client.streamable_http import (
    create_mcp_http_client,
    streamable_http_client,
)
from tree_sitter_language_pack import cache_dir

_TIMEOUT_S = 90.0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    pytest.fail(f"server did not open port {port} within {timeout}s")


@pytest.fixture()
def seeded_repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    for cmd in (
        ["git", "init"],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(cmd, cwd=r, capture_output=True, check=True)
    (r / "calc.py").write_text(
        "def add(a,b): return a+b\ndef mul(a,b): return a*b\n"
        "def calc(op,a,b):\n  if op=='add': return add(a,b)\n  return mul(a,b)\n"
    )
    subprocess.run(["git", "add", "."], cwd=r, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "i"], cwd=r, capture_output=True, check=True)
    return r


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
        f'token_hash = "{hash_token(token)}"\n'
    )
    env = {
        **os.environ,
        "CRG_CONFIG_DIR": str(cfg_dir),
        "CRG_DATA_DIR": str(tmp_path / "crg-data"),
        "EMBEDDING_BACKEND": "local",
        # The spawned server cannot auto-resolve the language pack's cache
        # location (platform detection reports none in that process), which
        # makes it re-download grammars at build time. The env var is the
        # BASE dir — the pack appends tree-sitter-language-pack/<ver>/libs
        # itself — so pass the parent of cache_dir()'s leaf, not the leaf.
        "TREE_SITTER_LANGUAGE_PACK_CACHE_DIR": str(Path(cache_dir()).parents[2]),
    }
    server_log = tmp_path / "server.log"
    with open(server_log, "w") as log_fh:
        proc = subprocess.Popen(
            # main's CLI: bare/leading-dash invocation starts the server
            # (no `server start` subcommand on this line); --http selects
            # the streamable-HTTP transport over the default stdio.
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
            if server_log.exists():
                print(
                    "\n=== server.log ===\n"
                    + server_log.read_text(encoding="utf-8", errors="replace")[-2000:]
                )


@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_http_mcp_e2e_build_query_auth(
    http_server: tuple[int, str], seeded_repo: Path
) -> None:
    port, token = http_server
    url = f"http://127.0.0.1:{port}/mcp"
    rp = str(seeded_repo)
    async with (
        create_mcp_http_client(
            headers={"Authorization": f"Bearer {token}"}
        ) as http_client,
        streamable_http_client(url, http_client=http_client) as (rd, wr),
    ):
        async with ClientSession(rd, wr) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            assert {"graph", "query", "review", "config", "help"} <= names

            build = json.loads(
                (
                    await session.call_tool(
                        "graph",
                        {"action": "build", "full_rebuild": True, "repo_root": rp},
                    )
                )
                .content[0]
                .text
            )
            assert build["status"] == "ok", build

            # Build may queue indexing work (summarize queue); poll stats
            # until the graph is populated.
            stats: dict = {}
            total = 0
            for _ in range(40):
                stats = json.loads(
                    (
                        await session.call_tool(
                            "graph", {"action": "stats", "repo_root": rp}
                        )
                    )
                    .content[0]
                    .text
                )
                total = stats.get("total_nodes", 0)
                if total > 0:
                    break
                await asyncio.sleep(0.5)
            assert total > 0, f"build={build} last_stats={stats}"

            callers = (
                (
                    await session.call_tool(
                        "query",
                        {
                            "action": "query",
                            "pattern": "callers_of",
                            "target": "add",
                            "repo_root": rp,
                        },
                    )
                )
                .content[0]
                .text
            )
            assert callers, "expected non-empty callers_of result"


@pytest.mark.e2e
async def test_http_mcp_rejects_missing_bearer(
    http_server: tuple[int, str], seeded_repo: Path
) -> None:
    port, _token = http_server
    url = f"http://127.0.0.1:{port}/mcp"
    # anyio task groups wrap the transport error (401 -> HTTPStatusError)
    # in an ExceptionGroup; assert the group rather than bare Exception.
    with pytest.raises(BaseExceptionGroup):
        async with streamable_http_client(url) as (rd, wr):
            async with ClientSession(rd, wr) as session:
                await session.initialize()
