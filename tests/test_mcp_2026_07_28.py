"""Unit tests for MCP 2026-07-28 upgrades (Skills provider, Tasks extension, wheel bundling)."""

from __future__ import annotations

import inspect
import json
import tomllib
from pathlib import Path
from unittest.mock import patch

import mcp.types as mt
from fastmcp import Client, FastMCP
from fastmcp.skills.extension import (
    GetSkillParams,
    GetSkillResult,
    ListSkillsParams,
    ListSkillsResult,
)
from fastmcp_tasks.client import call_tool_task
from hull_core.server import SKILLS_EXTENSION_ID, TASKS_EXTENSION_ID

from crg import server as crg_server


def test_pyproject_bundles_skills_into_wheel() -> None:
    """pyproject.toml packages ``skills/`` inside the built wheel."""
    repo_root = Path(__file__).resolve().parent.parent
    pyproject = tomllib.loads(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]
    assert force_include.get("skills") == "crg/skills"
    deps = pyproject["project"]["dependencies"]
    assert not any(d.lower().startswith("semgrep") for d in deps)
    assert not any("1.23.3" in d for d in deps)
    assert any(d.startswith("fastmcp[tasks]") for d in deps)
    assert any(d.startswith("n24q02m-hull>=0.12.0") for d in deps)


def test_resolve_skills_dir_repo_fallback() -> None:
    """_resolve_skills_dir resolves repo ``skills/`` when wheel resource is missing."""
    with patch("crg.server.files", side_effect=ModuleNotFoundError("no wheel")):
        resolved = crg_server._resolve_skills_dir()
    assert resolved is not None
    assert resolved.is_dir()
    assert (resolved / "review-pr" / "SKILL.md").is_file()


def test_resolve_skills_dir_packaged_resource(tmp_path: Path) -> None:
    """_resolve_skills_dir prefers packaged ``crg/skills`` resource when present."""
    pkg_skills = tmp_path / "crg" / "skills"
    pkg_skills.mkdir(parents=True)
    with patch("crg.server.files") as mock_files:
        mock_files.return_value.joinpath.return_value = pkg_skills
        resolved = crg_server._resolve_skills_dir()
    assert resolved == pkg_skills


def test_resolve_skills_dir_missing_returns_none(tmp_path: Path) -> None:
    """_resolve_skills_dir returns None when neither wheel nor repo skills exists."""
    fake_server_file = tmp_path / "src" / "crg" / "server.py"
    fake_server_file.parent.mkdir(parents=True)
    fake_server_file.write_text("", encoding="utf-8")
    with (
        patch("crg.server.files", side_effect=OSError("not found")),
        patch("crg.server.__file__", str(fake_server_file)),
    ):
        assert crg_server._resolve_skills_dir() is None


def test_register_mcp_extensions_skips_missing_skills(caplog) -> None:
    """_register_mcp_extensions registers Tasks even if skills dir is absent."""
    test_mcp = FastMCP("crg-test")
    with (
        patch("crg.server._resolve_skills_dir", return_value=None),
        caplog.at_level("WARNING"),
    ):
        crg_server._register_mcp_extensions(test_mcp)
    assert TASKS_EXTENSION_ID in test_mcp._extensions
    assert SKILLS_EXTENSION_ID not in test_mcp._extensions
    assert "Skills directory not found" in caplog.text


async def test_mcp_server_registers_skills_and_optional_tasks() -> None:
    """Default ``crg.server.mcp`` exposes Skills + Tasks on long-running tools."""
    assert SKILLS_EXTENSION_ID in crg_server.mcp._extensions
    assert TASKS_EXTENSION_ID in crg_server.mcp._extensions

    tools = {tool.name: tool for tool in await crg_server.mcp.list_tools()}
    assert tools["graph"].task_config.mode == "optional"
    assert tools["security"].task_config.mode == "optional"
    for fast_tool in ("query", "review", "config", "help"):
        assert tools[fast_tool].task_config.mode == "forbidden"


async def test_in_memory_skills_and_task_execution(tmp_path: Path) -> None:
    """In-memory FastMCP Client exercises skills/list, skill://, and Tasks."""
    async with Client(crg_server.mcp) as client:
        skills_res = await client.session.send_request(
            mt.Request(method="skills/list", params=ListSkillsParams()),
            ListSkillsResult,
        )
        uris = {entry.uri for entry in skills_res.skills}
        assert "skill://review-pr/SKILL.md" in uris
        assert "skill://security-sweep/SKILL.md" in uris
        assert len(uris) == 6

        get_res = await client.session.send_request(
            mt.Request(
                method="skills/get",
                params=GetSkillParams(uri="skill://review-pr/SKILL.md"),
            ),
            GetSkillResult,
        )
        assert get_res.skill.uri == "skill://review-pr/SKILL.md"

        contents = await client.read_resource("skill://review-pr/SKILL.md")
        assert contents
        first_res = contents[0]
        assert isinstance(first_res, mt.TextResourceContents)
        assert "review-pr" in first_res.text

        with patch(
            "crg.server.list_graph_stats",
            return_value={"status": "ok", "total_nodes": 3},
        ):
            task = await call_tool_task(
                client, "graph", {"action": "stats", "repo_root": str(tmp_path)}
            )
            task_result = await task.result()
        task_block = task_result.content[0]
        assert isinstance(task_block, mt.TextContent)
        assert json.loads(task_block.text)["total_nodes"] == 3

        with patch(
            "crg.server.security_rule_list",
            return_value={"status": "ok", "engine": "heuristic", "rules": []},
        ):
            sec_task = await call_tool_task(
                client,
                "security",
                {"action": "rule_list", "engine": "heuristic"},
            )
            sec_result = await sec_task.result()
        sec_block = sec_result.content[0]
        assert isinstance(sec_block, mt.TextContent)
        assert json.loads(sec_block.text)["engine"] == "heuristic"


async def test_async_wrappers_delegate_to_sync_handlers() -> None:
    """_graph_mcp_tool and _security_mcp_tool forward arguments cleanly."""
    with patch("crg.server.graph", return_value={"status": "ok"}) as mock_graph:
        out = await crg_server._graph_mcp_tool(action="stats", repo_root="/tmp/r")
    assert out == {"status": "ok"}
    mock_graph.assert_called_once()

    with patch("crg.server.security", return_value={"status": "ok"}) as mock_sec:
        sec_out = await crg_server._security_mcp_tool(
            action="rule_list", engine="heuristic"
        )
    assert sec_out == {"status": "ok"}
    mock_sec.assert_called_once()
    assert inspect.iscoroutinefunction(crg_server._graph_mcp_tool)
    assert inspect.iscoroutinefunction(crg_server._security_mcp_tool)
