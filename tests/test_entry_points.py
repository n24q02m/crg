"""Pin console scripts and the plugin hook to the n24q02m-crg distribution (ADR 0001)."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]["scripts"]


def test_every_name_maps_to_the_cli_entry():
    for name in ("n24q02m-crg", "crg", "better-code-review-graph"):
        assert SCRIPTS[name] == "crg.cli:main"


def test_plugin_manifest_name_is_short():
    manifest = json.loads(
        (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "crg"


def test_hooks_use_the_new_distribution():
    text = (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
    assert "--from n24q02m-crg" in text
    assert "--from better-code-review-graph" not in text
