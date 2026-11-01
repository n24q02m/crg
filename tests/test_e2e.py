"""E2E test for crg -- all tools except embed."""

import json
import os
import subprocess

import pytest
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.timeout(180)


@pytest.mark.full
async def test_all_tools(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init"], cwd=r, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=r, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=r, capture_output=True, check=True
    )
    (r / "calc.py").write_text(
        "def add(a,b): return a+b\ndef mul(a,b): return a*b\ndef calc(op,a,b):\n  if op=='add': return add(a,b)\n  return mul(a,b)\nclass C:\n  def run(self,op,a,b): return calc(op,a,b)\n"
    )
    (r / "test_calc.py").write_text(
        "from calc import add\ndef test_add(): assert add(1,2)==3\n"
    )
    subprocess.run(["git", "add", "."], cwd=r, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "i"], cwd=r, capture_output=True, check=True)
    rp = str(r)
    sp = StdioServerParameters(
        command="uv",
        args=["run", "crg"],
        env={**os.environ, "EMBEDDING_BACKEND": "local"},
    )
    async with stdio_client(sp) as (rd, wr):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            assert {t.name for t in (await s.list_tools()).tools} == {
                "graph",
                "query",
                "review",
                "config",
                "help",
                "security",
            }
            d = json.loads(
                (
                    await s.call_tool(
                        "graph",
                        {"action": "build", "full_rebuild": True, "repo_root": rp},
                    )
                )
                .content[0]
                .text
            )
            assert d["status"] == "ok" and d["total_nodes"] > 0
            assert (
                json.loads(
                    (await s.call_tool("graph", {"action": "update", "repo_root": rp}))
                    .content[0]
                    .text
                )["status"]
                == "ok"
            )
            assert (
                json.loads(
                    (await s.call_tool("graph", {"action": "stats", "repo_root": rp}))
                    .content[0]
                    .text
                )["total_nodes"]
                > 0
            )
            assert (
                (
                    await s.call_tool(
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
            assert (
                (
                    await s.call_tool(
                        "query",
                        {
                            "action": "query",
                            "pattern": "callees_of",
                            "target": "calc",
                            "repo_root": rp,
                        },
                    )
                )
                .content[0]
                .text
            )
            assert (
                (
                    await s.call_tool(
                        "query",
                        {"action": "search", "search_query": "calc", "repo_root": rp},
                    )
                )
                .content[0]
                .text
            )
            assert (
                (
                    await s.call_tool(
                        "query",
                        {
                            "action": "impact",
                            "changed_files": ["calc.py"],
                            "repo_root": rp,
                        },
                    )
                )
                .content[0]
                .text
            )
            assert (
                (
                    await s.call_tool(
                        "query",
                        {"action": "large_functions", "min_lines": 2, "repo_root": rp},
                    )
                )
                .content[0]
                .text
            )
            assert (
                len(
                    (
                        await s.call_tool(
                            "review", {"changed_files": ["calc.py"], "repo_root": rp}
                        )
                    )
                    .content[0]
                    .text
                )
                > 10
            )
            security_result = json.loads(
                (
                    await s.call_tool(
                        "security",
                        {"action": "scan", "engine": "heuristic", "repo_root": rp},
                    )
                )
                .content[0]
                .text
            )
            assert security_result["engine"] == "heuristic"
            assert isinstance(security_result["total"], int)
            assert isinstance(security_result["tags_by_node"], dict)
            assert json.loads(
                (await s.call_tool("config", {"action": "status", "repo_root": rp}))
                .content[0]
                .text
            )
            assert json.loads(
                (
                    await s.call_tool(
                        "config",
                        {"action": "set", "key": "log_level", "value": "WARNING"},
                    )
                )
                .content[0]
                .text
            )
            assert json.loads(
                (
                    await s.call_tool(
                        "config", {"action": "cache_clear", "repo_root": rp}
                    )
                )
                .content[0]
                .text
            )
            for topic in ["graph", "query", "review", "config"]:
                assert (
                    topic
                    in (await s.call_tool("help", {"topic": topic}))
                    .content[0]
                    .text.lower()
                )
            assert (
                "error"
                in (await s.call_tool("graph", {"action": "nonexistent"}))
                .content[0]
                .text.lower()
            )
