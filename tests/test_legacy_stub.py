"""The legacy stub must stay a thin pointer at the renamed distribution."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUB = tomllib.loads(
    (ROOT / "legacy" / "better-code-review-graph" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
)["project"]
MAIN = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_stub_depends_on_renamed_distribution():
    assert STUB["name"] == "better-code-review-graph"
    assert any(dep.startswith(MAIN["name"]) for dep in STUB["dependencies"])
    assert MAIN["name"] == "n24q02m-crg"


def test_stub_is_inactive_and_keeps_legacy_command():
    assert "Development Status :: 7 - Inactive" in STUB["classifiers"]
    assert STUB["scripts"] == {
        "better-code-review-graph": MAIN["scripts"]["better-code-review-graph"]
    }
