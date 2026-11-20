"""Tests for the Tier-2 Semgrep security scanner.

These tests never invoke real ``semgrep``: ``shutil.which`` and
``subprocess.run`` are patched throughout so the suite stays fast and
does not require the optional ``[security]`` extra to be installed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from crg.security import (
    SemgrepNotAvailable,
    SemgrepResult,
    SemgrepScanner,
    Tag,
)
from crg.security.semgrep_engine import (
    _overlay_rule_ids,
    _parse_semgrep_findings,
    _resolve_overlay_rules_dir,
    _semgrep_executable,
    _semgrep_python_module_available,
)

# ---------------------------------------------------------------------------
# Constructor / executable discovery
# ---------------------------------------------------------------------------


def test_semgrep_scanner_raises_when_cli_not_found():
    with patch(
        "crg.security.semgrep_engine.shutil.which",
        return_value=None,
    ):
        with pytest.raises(SemgrepNotAvailable, match="semgrep CLI not found"):
            SemgrepScanner()


def test_semgrep_executable_found():
    with patch(
        "crg.security.semgrep_engine.shutil.which",
        return_value="/usr/bin/semgrep",
    ):
        assert _semgrep_executable() == "/usr/bin/semgrep"


def test_semgrep_executable_not_found():
    with patch(
        "crg.security.semgrep_engine.shutil.which",
        return_value=None,
    ):
        assert _semgrep_executable() is None


def test_semgrep_scanner_uses_provided_executable():
    scanner = SemgrepScanner(executable="/usr/local/bin/semgrep-fake")
    assert scanner._executable == "/usr/local/bin/semgrep-fake"


def test_semgrep_scanner_uses_default_config():
    scanner = SemgrepScanner(executable="/fake/semgrep")
    assert scanner._config == "p/auto"


def test_semgrep_scanner_uses_custom_config():
    scanner = SemgrepScanner(config="./rules/semgrep", executable="/fake/semgrep")
    assert (
        scanner._config == "rules/semgrep"
        or scanner._config.endswith("rules/semgrep")
        or scanner._config.endswith("rules\\semgrep")
    )


def test_semgrep_scanner_uses_path_object_config():
    scanner = SemgrepScanner(
        config=Path("custom-config.yaml"), executable="/fake/semgrep"
    )
    assert "custom-config.yaml" in scanner._config


def test_scanner_python_module_check_raises_when_missing():
    with patch(
        "crg.security.semgrep_engine._semgrep_python_module_available",
        return_value=False,
    ):
        with pytest.raises(SemgrepNotAvailable, match="Python module not importable"):
            SemgrepScanner(executable="/fake/semgrep", require_python_module=True)


def test_scanner_python_module_check_passes_when_present():
    with patch(
        "crg.security.semgrep_engine._semgrep_python_module_available",
        return_value=True,
    ):
        scanner = SemgrepScanner(executable="/fake/semgrep", require_python_module=True)
        assert scanner._executable == "/fake/semgrep"


def test_semgrep_python_module_helper_returns_bool():
    # Real probe: result depends on environment but must be boolean.
    assert isinstance(_semgrep_python_module_available(), bool)


def test_semgrep_python_module_available_true():
    with patch.dict(sys.modules, {"semgrep": MagicMock()}):
        assert _semgrep_python_module_available() is True


def test_semgrep_python_module_available_false():
    with patch.dict(sys.modules, {"semgrep": None}):
        # When set to None, it raises ImportError on import
        assert _semgrep_python_module_available() is False


# ---------------------------------------------------------------------------
# Overlay rules dir resolution
# ---------------------------------------------------------------------------


def test_resolve_overlay_rules_dir_returns_bundled_path():
    # In the source checkout the ``rules/semgrep`` directory exists.
    result = _resolve_overlay_rules_dir()
    assert result is not None
    assert result.is_dir()
    assert result.name == "semgrep"


def test_resolve_overlay_rules_dir_returns_none_when_missing(tmp_path, monkeypatch):
    # Force both the importlib.resources path AND the source-checkout
    # fallback to point at empty directories so the helper returns None.
    fake_module_root = tmp_path / "fake-module-root"
    fake_module_root.mkdir()

    def fake_files(_pkg):
        return fake_module_root

    monkeypatch.setattr(
        "crg.security.semgrep_engine.files",
        fake_files,
    )
    fake_repo_root = tmp_path / "fake-repo"
    fake_repo_root.mkdir()
    fake_engine_file = fake_repo_root / "src" / "crg" / "security" / "semgrep_engine.py"
    fake_engine_file.parent.mkdir(parents=True)
    fake_engine_file.write_text("# placeholder")
    # Point ``__file__`` at the fake checkout so the fallback resolves to a
    # missing ``rules/semgrep`` directory.
    monkeypatch.setattr(
        "crg.security.semgrep_engine.__file__",
        str(fake_engine_file),
    )
    assert _resolve_overlay_rules_dir() is None


def test_resolve_overlay_rules_dir_handles_module_not_found(tmp_path, monkeypatch):
    def raise_not_found(_pkg):
        raise ModuleNotFoundError("no such package")

    monkeypatch.setattr(
        "crg.security.semgrep_engine.files",
        raise_not_found,
    )
    # Source checkout fallback should still locate the real rules dir.
    result = _resolve_overlay_rules_dir()
    assert result is not None
    assert result.name == "semgrep"


# ---------------------------------------------------------------------------
# _parse_semgrep_findings
# ---------------------------------------------------------------------------


def test_parse_semgrep_findings_empty_input():
    assert _parse_semgrep_findings([]) == []


def test_parse_semgrep_findings_basic_finding():
    findings = [
        {
            "check_id": "test-rule",
            "extra": {"severity": "ERROR", "message": "bad sink"},
            "start": {"line": 42},
        }
    ]
    tags = _parse_semgrep_findings(findings)
    assert len(tags) == 1
    tag = tags[0]
    assert isinstance(tag, Tag)
    assert tag.rule_id == "test-rule"
    assert tag.severity == "HIGH"
    assert tag.message == "bad sink"
    assert tag.line == 42


def test_parse_semgrep_findings_unknown_severity_default():
    findings = [{"check_id": "r", "extra": {}, "start": {"line": 1}}]
    tags = _parse_semgrep_findings(findings)
    assert tags[0].severity == "MEDIUM"


def test_parse_semgrep_findings_translates_semgrep_severity_levels():
    findings = [
        {
            "check_id": "info-rule",
            "extra": {"severity": "INFO", "message": ""},
            "start": {"line": 1},
        },
        {
            "check_id": "warning-rule",
            "extra": {"severity": "WARNING", "message": ""},
            "start": {"line": 2},
        },
        {
            "check_id": "error-rule",
            "extra": {"severity": "ERROR", "message": ""},
            "start": {"line": 3},
        },
    ]
    tags = _parse_semgrep_findings(findings)
    assert [t.severity for t in tags] == ["LOW", "MEDIUM", "HIGH"]


def test_parse_semgrep_findings_handles_missing_line():
    findings = [{"check_id": "r", "extra": {"severity": "ERROR"}, "start": {}}]
    tags = _parse_semgrep_findings(findings)
    assert tags[0].line is None


def test_parse_semgrep_findings_handles_non_dict_start():
    findings = [{"check_id": "r", "extra": {"severity": "ERROR"}, "start": None}]
    tags = _parse_semgrep_findings(findings)
    assert tags[0].line is None


def test_parse_semgrep_findings_handles_missing_check_id():
    findings = [{"extra": {"severity": "ERROR"}, "start": {"line": 5}}]
    tags = _parse_semgrep_findings(findings)
    assert tags[0].rule_id == "semgrep-rule"


def test_parse_semgrep_findings_handles_non_dict_extra():
    findings = [{"check_id": "r", "extra": "oops-not-a-dict", "start": {"line": 5}}]
    tags = _parse_semgrep_findings(findings)
    # Falls back to MEDIUM (default) when ``extra`` is the wrong shape.
    assert tags[0].severity == "MEDIUM"
    assert tags[0].message == ""
    assert tags[0].line == 5


def test_parse_semgrep_findings_keeps_non_standard_severity_uppercased():
    findings = [
        {
            "check_id": "r",
            "extra": {"severity": "critical"},
            "start": {"line": 1},
        }
    ]
    tags = _parse_semgrep_findings(findings)
    # CRITICAL is not in the INFO/WARNING/ERROR map, so it passes through
    # uppercased.
    assert tags[0].severity == "CRITICAL"


# ---------------------------------------------------------------------------
# scan_path() -- subprocess fully mocked
# ---------------------------------------------------------------------------


def _mock_completed(returncode: int, stdout: str = "", stderr: str = ""):
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def test_scan_path_returns_tags_on_findings(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("import os\n")
    payload = {
        "results": [
            {
                "check_id": "demo-rule",
                "extra": {"severity": "ERROR", "message": "demo"},
                "start": {"line": 1},
            }
        ]
    }
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(1, stdout=json.dumps(payload)),
    ) as run_mock:
        result = scanner.scan_path(target)
    assert isinstance(result, SemgrepResult)
    assert len(result.tags) == 1
    assert result.tags[0].rule_id == "demo-rule"
    assert result.tags[0].severity == "HIGH"
    assert json.loads(result.raw_output) == payload
    cmd = run_mock.call_args[0][0]
    assert cmd[0] == "/fake/semgrep"
    assert "--config=p/auto" in cmd
    assert "--json" in cmd
    assert str(target) in cmd


def test_scan_path_adds_bundled_overlay_config(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("import os\n")
    overlay = _resolve_overlay_rules_dir()
    assert overlay is not None
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout='{"results": []}'),
    ) as run_mock:
        scanner.scan_path(target)
    cmd = run_mock.call_args[0][0]
    assert "--config=p/auto" in cmd
    assert f"--config={overlay}" in cmd
    assert cmd.index(f"--config={overlay}") < cmd.index("--")


def test_scan_path_skips_overlay_when_disabled(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("import os\n")
    scanner = SemgrepScanner(executable="/fake/semgrep", include_overlay=False)
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout='{"results": []}'),
    ) as run_mock:
        scanner.scan_path(target)
    cmd = run_mock.call_args[0][0]
    assert [arg for arg in cmd if arg.startswith("--config=")] == ["--config=p/auto"]


def test_scan_path_skips_overlay_when_not_bundled(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "crg.security.semgrep_engine._resolve_overlay_rules_dir",
        lambda: None,
    )
    target = tmp_path / "src.py"
    target.write_text("import os\n")
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout='{"results": []}'),
    ) as run_mock:
        scanner.scan_path(target)
    cmd = run_mock.call_args[0][0]
    assert [arg for arg in cmd if arg.startswith("--config=")] == ["--config=p/auto"]


def test_overlay_rule_ids_reads_bundled_rules():
    assert _overlay_rule_ids(_resolve_overlay_rules_dir()) == frozenset(
        {
            "crg-cwe-89-python-format-execute",
            "crg-cwe-78-python-shell-true",
            "crg-cwe-95-python-dynamic-eval-input",
        }
    )


def test_overlay_rule_ids_empty_without_overlay():
    assert _overlay_rule_ids(None) == frozenset()


def test_scan_path_strips_install_prefix_from_overlay_rule_ids(tmp_path):
    # Semgrep prefixes rules loaded from a local config file with the dotted
    # path of that file, so the same overlay rule gets a different id per
    # install location. Registry rule ids are already stable and stay as-is.
    target = tmp_path / "src.py"
    target.write_text("import os\n")
    registry_id = "python.lang.security.audit.subprocess-shell-true"
    payload = {
        "results": [
            {
                "check_id": (
                    "venv.lib.python3.13.site-packages.crg_security_rules."
                    "semgrep.crg-cwe-78-python-shell-true"
                ),
                "extra": {"severity": "ERROR", "message": "shell"},
                "start": {"line": 3},
            },
            {
                "check_id": registry_id,
                "extra": {"severity": "ERROR", "message": "shell"},
                "start": {"line": 3},
            },
        ]
    }
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(1, stdout=json.dumps(payload)),
    ):
        result = scanner.scan_path(target)
    assert [t.rule_id for t in result.tags] == [
        "crg-cwe-78-python-shell-true",
        registry_id,
    ]


def test_scan_path_returns_empty_tags_on_no_findings(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("# clean\n")
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout='{"results": []}'),
    ):
        result = scanner.scan_path(target)
    assert result.tags == []


def test_scan_path_handles_empty_stdout(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("# clean\n")
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout=""),
    ):
        result = scanner.scan_path(target)
    assert result.tags == []
    assert result.raw_output == ""


def test_scan_path_raises_on_semgrep_error_code(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("import os\n")
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(2, stdout="", stderr="boom"),
    ):
        with pytest.raises(SemgrepNotAvailable, match="exited with code 2"):
            scanner.scan_path(target)


def test_scan_path_raises_on_invalid_json(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("import os\n")
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout="not valid json"),
    ):
        with pytest.raises(SemgrepNotAvailable, match="JSON output parse failed"):
            scanner.scan_path(target)


def test_scan_path_passes_timeout_to_subprocess(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("import os\n")
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout='{"results": []}'),
    ) as run_mock:
        scanner.scan_path(target, timeout=12.5)
    assert run_mock.call_args.kwargs["timeout"] == 12.5


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------


def test_security_module_reexports_semgrep_symbols():
    from crg import security

    assert hasattr(security, "SemgrepScanner")
    assert hasattr(security, "SemgrepResult")
    assert hasattr(security, "SemgrepNotAvailable")
    assert "SemgrepScanner" in security.__all__
    assert "SemgrepResult" in security.__all__
    assert "SemgrepNotAvailable" in security.__all__


# ---------------------------------------------------------------------------
# Security: Argument Injection
# ---------------------------------------------------------------------------


def test_scan_path_uses_double_dash_separator(tmp_path):
    target = tmp_path / "--version"
    target.write_text("print(1)")
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout='{"results": []}'),
    ) as run_mock:
        scanner.scan_path(target)

    cmd = run_mock.call_args[0][0]
    assert "--" in cmd
    assert cmd.index("--") == cmd.index(str(target)) - 1


def test_init_raises_on_config_starting_with_hyphen():
    with pytest.raises(ValueError, match="Semgrep config cannot start with a hyphen"):
        SemgrepScanner(config="--some-flag", executable="/fake/semgrep")


def test_scan_path_with_registry_config(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("print(1)")
    # Using a registry-like config string
    scanner = SemgrepScanner(config="p/python", executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout='{"results": []}'),
    ) as run_mock:
        scanner.scan_path(target)

    cmd = run_mock.call_args[0][0]
    # Verify --config <config> is still correct
    assert "--config=p/python" in cmd
    # Verify -- is still before target
    assert "--" in cmd
    assert cmd.index("--") == cmd.index(str(target)) - 1


def test_scan_path_uses_devnull_stdin(tmp_path):
    target = tmp_path / "src.py"
    target.write_text("print(1)")
    scanner = SemgrepScanner(executable="/fake/semgrep")
    with patch(
        "crg.security.semgrep_engine.subprocess.run",
        return_value=_mock_completed(0, stdout='{"results": []}'),
    ) as run_mock:
        scanner.scan_path(target)

    assert run_mock.call_args.kwargs["stdin"] == subprocess.DEVNULL
