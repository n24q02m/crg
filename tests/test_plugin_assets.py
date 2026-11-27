"""Tests for the shipped plugin assets: skills, the hook manifest, and the
behaviour of the two hook scripts.

The hooks run on the interactive path, so the properties that matter most are
negative ones: never block, never crash the session, and never cry wolf. Each
scenario below asserts a return code of 0 alongside the expected output.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / "hooks"
SKILLS_DIR = REPO_ROOT / "skills"
HOOKS_MANIFEST = HOOKS_DIR / "hooks.json"

EXPECTED_SKILLS = {
    "impact-audit",
    "onboard-repo",
    "refactor-check",
    "review-delta",
    "review-pr",
    "security-sweep",
}

FAKE_SHA = "a" * 40
OTHER_SHA = "b" * 40
DEAD_SHA = "deadbeef" * 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_hook(script: str, cwd: Path, stdin_text: str = "", **env_extra):
    env = dict(os.environ)
    env.pop("CRG_STALE_HOURS", None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        cwd=str(cwd),
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )


def _make_graph_db(repo_root: Path, last_built_head: str | None = None) -> Path:
    crg_dir = repo_root / ".crg"
    crg_dir.mkdir(parents=True, exist_ok=True)
    db_path = crg_dir / "graph.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        if last_built_head is not None:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("last_built_head", last_built_head),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _fake_git_head(repo_root: Path, sha: str) -> None:
    """Write a minimal git dir so HEAD resolves without invoking git."""
    refs = repo_root / ".git" / "refs" / "heads"
    refs.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (refs / "main").write_text(f"{sha}\n")


def _age_file(path: Path, hours: float) -> None:
    old = time.time() - hours * 3600
    os.utime(path, (old, old))


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, timeout=30
    )


def _real_repo(tmp_path: Path) -> str:
    """Init a real repo with one commit; return that commit's sha."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "first")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return result.stdout.strip()


def _post_tool_use(command: str, cwd: Path) -> str:
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(cwd),
        }
    )


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestSkills:
    def test_expected_skills_are_present(self):
        found = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
        assert found == EXPECTED_SKILLS

    @pytest.mark.parametrize("skill", sorted(EXPECTED_SKILLS))
    def test_frontmatter_name_matches_directory(self, skill):
        text = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        fields = {}
        for line in frontmatter.strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        assert fields.get("name") == skill
        assert fields.get("description")


# ---------------------------------------------------------------------------
# Hook manifest
# ---------------------------------------------------------------------------


class TestHookManifest:
    def _manifest(self) -> dict:
        return json.loads(HOOKS_MANIFEST.read_text(encoding="utf-8"))

    def _commands(self) -> list[str]:
        commands = []
        for groups in self._manifest()["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    commands.append(hook["command"])
        return commands

    def test_declares_the_three_lifecycle_events(self):
        assert set(self._manifest()["hooks"]) == {
            "PreToolUse",
            "SessionStart",
            "UserPromptSubmit",
            "PostToolUse",
        }

    def test_incremental_update_hook_is_preserved(self):
        groups = self._manifest()["hooks"]["PostToolUse"]
        matchers = [g.get("matcher") for g in groups]
        assert "Write|Edit|Bash" in matchers
        assert "Bash" in matchers

    def test_no_bare_script_command(self):
        """A bare .sh/.ps1 command opens an editor on Windows instead of running."""
        for command in self._commands():
            first = command.split()[0].strip('"')
            assert not first.endswith((".sh", ".ps1", ".py")), command

    def test_referenced_scripts_exist(self):
        for command in self._commands():
            if "CLAUDE_PLUGIN_ROOT" not in command:
                continue
            rel = command.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].strip('"')
            assert (REPO_ROOT / rel).is_file(), rel


def test_local_rerank_model_is_optional_and_forwarded():
    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    field = plugin["userConfig"]["LOCAL_RERANK_MODEL"]
    assert field["type"] == "string"
    assert field["required"] is False
    assert (
        plugin["mcpServers"]["crg"]["env"]["LOCAL_RERANK_MODEL"]
        == "${user_config.LOCAL_RERANK_MODEL}"
    )

    server = json.loads((REPO_ROOT / "server.json").read_text())
    names = {item["name"] for item in server["packages"][0]["environmentVariables"]}
    assert "LOCAL_RERANK_MODEL" in names


# ---------------------------------------------------------------------------
# UserPromptSubmit -- stale graph warning
# ---------------------------------------------------------------------------


class TestStaleGraphCheck:
    SCRIPT = "stale-graph-check.py"

    def test_silent_without_a_graph(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = _run_hook(self.SCRIPT, tmp_path)
        assert result.returncode == 0
        assert result.stdout == ""

    def test_silent_when_current(self, tmp_path):
        _make_graph_db(tmp_path, FAKE_SHA)
        _fake_git_head(tmp_path, FAKE_SHA)
        result = _run_hook(self.SCRIPT, tmp_path)
        assert result.returncode == 0
        assert result.stdout == ""

    def test_warns_when_head_moved(self, tmp_path):
        _make_graph_db(tmp_path, FAKE_SHA)
        _fake_git_head(tmp_path, OTHER_SHA)
        result = _run_hook(self.SCRIPT, tmp_path)
        assert result.returncode == 0
        assert "HEAD is" in result.stdout
        assert OTHER_SHA[:8] in result.stdout

    def test_warns_when_index_is_old(self, tmp_path):
        db_path = _make_graph_db(tmp_path, FAKE_SHA)
        _fake_git_head(tmp_path, FAKE_SHA)
        _age_file(db_path, hours=48)
        result = _run_hook(self.SCRIPT, tmp_path)
        assert result.returncode == 0
        assert "last indexed" in result.stdout

    def test_age_threshold_is_configurable(self, tmp_path):
        db_path = _make_graph_db(tmp_path, FAKE_SHA)
        _fake_git_head(tmp_path, FAKE_SHA)
        _age_file(db_path, hours=48)

        quiet = _run_hook(self.SCRIPT, tmp_path, CRG_STALE_HOURS="72")
        assert quiet.stdout == ""

        loud = _run_hook(self.SCRIPT, tmp_path, CRG_STALE_HOURS="1")
        assert "last indexed" in loud.stdout

    def test_age_signal_can_be_disabled(self, tmp_path):
        db_path = _make_graph_db(tmp_path, FAKE_SHA)
        _fake_git_head(tmp_path, FAKE_SHA)
        _age_file(db_path, hours=999)
        result = _run_hook(self.SCRIPT, tmp_path, CRG_STALE_HOURS="0")
        assert result.returncode == 0
        assert result.stdout == ""

    def test_survives_an_unreadable_graph(self, tmp_path):
        crg_dir = tmp_path / ".crg"
        crg_dir.mkdir()
        (crg_dir / "graph.db").write_text("not a database")
        _fake_git_head(tmp_path, FAKE_SHA)
        result = _run_hook(self.SCRIPT, tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# PostToolUse -- branch move outran the graph
# ---------------------------------------------------------------------------


class TestBranchSyncCheck:
    SCRIPT = "branch-sync-check.py"

    def test_silent_on_empty_stdin(self, tmp_path):
        result = _run_hook(self.SCRIPT, tmp_path)
        assert result.returncode == 0
        assert result.stdout == ""

    def test_silent_on_unrelated_command(self, tmp_path):
        _make_graph_db(tmp_path, DEAD_SHA)
        _fake_git_head(tmp_path, FAKE_SHA)
        result = _run_hook(self.SCRIPT, tmp_path, _post_tool_use("ls -la", tmp_path))
        assert result.returncode == 0
        assert result.stdout == ""

    @pytest.mark.parametrize(
        "command",
        ['git commit -m "merge the thing"', "git log --merges", "git status"],
    )
    def test_does_not_fire_on_lookalike_commands(self, tmp_path, command):
        _make_graph_db(tmp_path, DEAD_SHA)
        _fake_git_head(tmp_path, FAKE_SHA)
        result = _run_hook(self.SCRIPT, tmp_path, _post_tool_use(command, tmp_path))
        assert result.returncode == 0
        assert result.stdout == ""

    def test_silent_when_graph_is_on_current_commit(self, tmp_path):
        head = _real_repo(tmp_path)
        _make_graph_db(tmp_path, head)
        result = _run_hook(self.SCRIPT, tmp_path, _post_tool_use("git pull", tmp_path))
        assert result.returncode == 0
        assert result.stdout == ""

    def test_silent_when_incremental_can_catch_up(self, tmp_path):
        """Recorded commit still exists -- the incremental pass widens to it."""
        first = _real_repo(tmp_path)
        (tmp_path / "b.py").write_text("y = 2\n")
        _git(tmp_path, "add", "b.py")
        _git(tmp_path, "commit", "-q", "-m", "second")
        _make_graph_db(tmp_path, first)
        result = _run_hook(self.SCRIPT, tmp_path, _post_tool_use("git pull", tmp_path))
        assert result.returncode == 0
        assert result.stdout == ""

    @pytest.mark.parametrize("command", ["git pull", "git merge origin/main"])
    def test_asks_for_rebuild_when_base_is_gone(self, tmp_path, command):
        _real_repo(tmp_path)
        _make_graph_db(tmp_path, DEAD_SHA)
        result = _run_hook(self.SCRIPT, tmp_path, _post_tool_use(command, tmp_path))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "full_rebuild=true" in context

    def test_silent_without_a_recorded_build(self, tmp_path):
        _real_repo(tmp_path)
        _make_graph_db(tmp_path, None)
        result = _run_hook(self.SCRIPT, tmp_path, _post_tool_use("git pull", tmp_path))
        assert result.returncode == 0
        assert result.stdout == ""
