"""Tier-2 Semgrep security scanner (opt-in).

Wraps the Semgrep CLI (``semgrep --config p/auto --json``) to surface
the curated OWASP-style ruleset. Semgrep is not a crg dependency: its
releases pin dependencies that conflict with crg's, so install the CLI
in its own environment and keep it on ``PATH``::

    uv tool install semgrep

Without the CLI, importing this module is safe; the engine raises
:class:`SemgrepNotAvailable` when instantiated. Heuristic Tier-1
scanning (``HeuristicScanner``) remains fully functional regardless.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .heuristic import Tag

_SEMGREP_DEFAULT_CONFIG = "p/auto"
_OVERLAY_RULE_ID = re.compile(r"^\s*-\s*id:\s*([^\s#]+)", re.MULTILINE)


class SemgrepNotAvailable(RuntimeError):
    """Raised when semgrep is not installed, not on PATH, or fails to run."""


@dataclass(frozen=True)
class SemgrepResult:
    """Aggregated Semgrep scan result.

    ``tags`` is a flat list of :class:`Tag` objects (one per finding);
    ``raw_output`` preserves the full ``--json`` stdout so callers that
    need the structured Semgrep schema (file path, position spans, fix
    suggestions, ...) can parse it themselves.
    """

    tags: list[Tag]
    raw_output: str


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _semgrep_executable() -> str | None:
    """Return path to the ``semgrep`` CLI, or ``None`` if not on PATH."""

    return shutil.which("semgrep")


def _semgrep_python_module_available() -> bool:
    """Return ``True`` if the ``semgrep`` Python module is importable."""

    try:
        import semgrep  # noqa: F401
    except ImportError:
        return False
    return True


def _resolve_overlay_rules_dir() -> Path | None:
    """Return path to the bundled ``rules/semgrep/`` overlay, if present.

    First tries the wheel-installed location (top-level package
    ``crg_security_rules`` populated by the
    ``[tool.hatch.build.targets.wheel.force-include]`` mapping), then
    falls back to the repository checkout layout used during ``uv sync``.
    """

    try:
        ref = files("crg_security_rules").joinpath("semgrep")
        if isinstance(ref, Path) and ref.joinpath("curated.yaml").is_file():
            return ref
    except (ModuleNotFoundError, OSError):
        pass
    fallback = (
        Path(__file__).resolve().parent.parent.parent.parent / "rules" / "semgrep"
    )
    if fallback.is_dir():
        return fallback
    return None


def _overlay_rule_ids(rules_dir: Path | None) -> frozenset[str]:
    """Return the rule ids declared in the overlay ``*.yaml`` files."""

    if rules_dir is None:
        return frozenset()
    ids: set[str] = set()
    for path in sorted(rules_dir.glob("*.yaml")):
        ids.update(_OVERLAY_RULE_ID.findall(path.read_text(encoding="utf-8")))
    return frozenset(ids)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class SemgrepScanner:
    """Tier-2 Semgrep wrapper.

    Args:
        config: Semgrep ruleset to use. Defaults to ``p/auto`` (Semgrep's
            curated meta-pack). Can be a local rules dir, a registry URL,
            or a path to a single YAML file.
        executable: Override path to the ``semgrep`` binary. Defaults to
            ``shutil.which("semgrep")``.
        require_python_module: When ``True``, also requires that the
            ``semgrep`` Python module be importable. Defaults to ``False``
            (CLI-only check).
        include_overlay: When ``True`` (default), also passes the bundled
            ``rules/semgrep/`` curated overlay as a second ``--config`` so
            its rules run next to ``config``. Skipped when no overlay is
            bundled.

    Raises:
        SemgrepNotAvailable: If neither the CLI (always) nor the Python
            module (when ``require_python_module=True``) is available.
    """

    def __init__(
        self,
        config: str | Path = _SEMGREP_DEFAULT_CONFIG,
        executable: str | None = None,
        require_python_module: bool = False,
        include_overlay: bool = True,
    ) -> None:
        config_str = str(config)
        if config_str.startswith("-"):
            raise ValueError(f"Semgrep config cannot start with a hyphen: {config_str}")
        self._config = config_str
        resolved = executable or _semgrep_executable()
        if resolved is None:
            raise SemgrepNotAvailable(
                "semgrep CLI not found on PATH. Install with: uv tool install semgrep"
            )
        if resolved.startswith("-"):
            raise ValueError(
                f"Semgrep executable cannot start with a hyphen: {resolved}"
            )
        self._executable: str = resolved
        if require_python_module and not _semgrep_python_module_available():
            raise SemgrepNotAvailable(
                "semgrep Python module not importable in this environment. "
                "The scanner only needs the CLI: uv tool install semgrep"
            )
        self._overlay: Path | None = (
            _resolve_overlay_rules_dir() if include_overlay else None
        )
        self._overlay_ids = _overlay_rule_ids(self._overlay)

    def scan_path(
        self,
        target: Path,
        *,
        timeout: float = 300.0,
    ) -> SemgrepResult:
        """Run ``semgrep --config <config> --json <target>`` and parse output.

        Args:
            target: File or directory to scan.
            timeout: Maximum seconds to wait for ``semgrep`` to complete.

        Returns:
            A :class:`SemgrepResult` with one :class:`Tag` per finding plus
            the raw ``--json`` stdout for callers needing the full Semgrep
            schema.

        Raises:
            SemgrepNotAvailable: If ``semgrep`` exits with a code greater
                than ``1`` (``0`` = no findings, ``1`` = findings present
                are both treated as success), or if the JSON output cannot
                be parsed.
            subprocess.TimeoutExpired: If the scan exceeds ``timeout``.
        """

        cmd = [self._executable, f"--config={self._config}"]
        if self._overlay is not None:
            cmd.append(f"--config={self._overlay}")
        cmd += ["--json", "--quiet", "--", str(target)]
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        # Semgrep exit codes: 0 = no findings, 1 = findings, >1 = error.
        if proc.returncode > 1:
            raise SemgrepNotAvailable(
                f"semgrep exited with code {proc.returncode}: {proc.stderr.strip()}"
            )
        try:
            data = json.loads(proc.stdout) if proc.stdout else {"results": []}
        except json.JSONDecodeError as exc:
            raise SemgrepNotAvailable(
                f"semgrep JSON output parse failed: {exc}"
            ) from exc
        tags = _parse_semgrep_findings(data.get("results", []), self._overlay_ids)
        return SemgrepResult(tags=tags, raw_output=proc.stdout)


# ---------------------------------------------------------------------------
# Finding -> Tag translation
# ---------------------------------------------------------------------------


_SEMGREP_TO_CRG_SEVERITY = {"INFO": "LOW", "WARNING": "MEDIUM", "ERROR": "HIGH"}


def _parse_semgrep_findings(
    findings: list[dict], overlay_ids: frozenset[str] = frozenset()
) -> list[Tag]:
    """Translate semgrep ``--json`` result entries into :class:`Tag` objects.

    Semgrep prefixes rules loaded from a local file with that file's dotted
    path, so an overlay rule id is reduced to the id declared in the overlay
    to stay the same for every install location (and for suppressions).
    """

    out: list[Tag] = []
    for finding in findings:
        rule_id = str(finding.get("check_id") or "semgrep-rule")
        declared = rule_id.rsplit(".", 1)[-1]
        if declared in overlay_ids:
            rule_id = declared
        extra = finding.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}
        severity_raw = str(extra.get("severity") or "MEDIUM").upper()
        severity = _SEMGREP_TO_CRG_SEVERITY.get(severity_raw, severity_raw)
        message = str(extra.get("message") or "")
        start = finding.get("start")
        line = start.get("line") if isinstance(start, dict) else None
        out.append(
            Tag(
                rule_id=rule_id,
                severity=severity,
                message=message,
                line=line if isinstance(line, int) else None,
            )
        )
    return out
