"""AP-18 audit tests: no Python semgrep dependency or legacy mcp==1.23.3 pin."""

from __future__ import annotations

import builtins
import re
import tomllib
from pathlib import Path

from crg.security.semgrep_engine import SemgrepScanner

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_and_lockfile_have_no_semgrep_or_legacy_mcp_pin() -> None:
    pyproject_data = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = pyproject_data["project"]
    all_deps: list[str] = list(project.get("dependencies", []))
    for extra_deps in project.get("optional-dependencies", {}).values():
        all_deps.extend(extra_deps)
    for dep in all_deps:
        assert not dep.lower().startswith("semgrep"), f"Unexpected semgrep dep: {dep}"
        assert "1.23.3" not in dep, f"Unexpected legacy mcp pin: {dep}"

    uv_lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert not re.search(r'^name\s*=\s*"semgrep"', uv_lock, re.MULTILINE)
    assert not re.search(
        r'^name\s*=\s*"mcp"\s*\nversion\s*=\s*"1\.23\.3"', uv_lock, re.MULTILINE
    )


def test_workflows_and_hooks_have_no_semgrep_or_mcp_1233_pin() -> None:
    for wf in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        assert "mcp==1.23.3" not in text, f"Legacy mcp pin in {wf.name}"
        assert "uv pip install semgrep" not in text, (
            f"Python semgrep install in {wf.name}"
        )
        assert "pip install semgrep" not in text, f"Python semgrep install in {wf.name}"

    for hook_file in (REPO_ROOT / "hooks").iterdir():
        if hook_file.is_file():
            text = hook_file.read_text(encoding="utf-8")
            assert "mcp==1.23.3" not in text
            assert "import semgrep" not in text


def test_semgrep_scanner_uses_cli_without_importing_semgrep_module(monkeypatch) -> None:
    real_import = builtins.__import__

    def _forbid_semgrep(name: str, *args, **kwargs):
        if name == "semgrep" or name.startswith("semgrep."):
            raise AssertionError(
                "SemgrepScanner must not import Python module semgrep by default"
            )
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _forbid_semgrep)
    scanner = SemgrepScanner(executable="/fake/semgrep")
    assert scanner._executable == "/fake/semgrep"
