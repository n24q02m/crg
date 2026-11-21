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


def _hook_commands() -> list[str]:
    manifest = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return [
        hook["command"]
        for groups in manifest["hooks"].values()
        for group in groups
        for hook in group["hooks"]
    ]


def test_plugin_server_launch_tracks_the_latest_release():
    """uvx keeps reusing the first cached environment of an unversioned spec,
    so without ``@latest`` a plugin install never picks up a new crg release."""
    manifest = json.loads(
        (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    server = manifest["mcpServers"]["crg"]
    assert server["command"] == "uvx"
    assert server["args"] == ["--python", "3.13", "n24q02m-crg@latest"]


def test_uvx_hooks_pin_the_interpreter_crg_requires():
    """crg supports Python 3.13 only. Without ``--python 3.13`` the hook uses
    the default interpreter: below 3.13 the install fails and the trailing
    ``|| true`` hides it; on 3.14 or newer uv ignores the ``<3.14`` bound and
    runs the hook on an unsupported Python, in a different environment from
    the server."""
    uvx = [c for c in _hook_commands() if c.split()[0] == "uvx"]
    assert uvx, "the incremental-update hook runs through uvx"
    for command in uvx:
        assert command.startswith("uvx --python 3.13 --from n24q02m-crg "), command


def test_smithery_launch_matches_the_plugin():
    """smithery.yaml spells out the same uvx launch as the plugin manifest,
    so a change to one must reach the other."""
    manifest = json.loads(
        (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    args = manifest["mcpServers"]["crg"]["args"]
    text = (ROOT / "smithery.yaml").read_text(encoding="utf-8")
    expected = "args: [" + ", ".join(f"'{a}'" for a in args) + "]"
    assert expected in text
