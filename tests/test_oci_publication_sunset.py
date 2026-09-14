"""Contracts for retiring new public OCI publication without retiring CRG."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "cd.yml"


def _job_block(workflow: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, name
    return match.group("body")


def test_release_workflow_keeps_packages_without_public_oci_jobs():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "  publish-pypi:" in workflow
    assert "  publish-mcp-registry:" in workflow
    assert "  build-docker:" not in workflow
    assert "  merge-docker:" not in workflow
    assert "DOCKERHUB_IMAGE" not in workflow
    assert "GHCR_IMAGE" not in workflow
    assert "packages: write" not in workflow
    assert "needs: [release, publish-pypi]" in _job_block(
        workflow, "publish-mcp-registry"
    )


def _named_run_steps(workflow: str, job: str) -> list[tuple[str, str | None]]:
    """Return named release steps and their single-line ``run`` commands."""
    block = _job_block(workflow, job)
    steps = []
    for match in re.finditer(
        r"^      - name: (?P<name>[^\n]+)\n"
        r"(?P<body>.*?)(?=^      - (?:name|uses):|\Z)",
        block,
        flags=re.MULTILINE | re.DOTALL,
    ):
        run_match = re.search(
            r"^        run: (?P<command>[^\n]+)",
            match.group("body"),
            flags=re.MULTILINE,
        )
        steps.append(
            (
                match.group("name"),
                run_match.group("command") if run_match else None,
            )
        )
    return steps


def test_registry_metadata_is_pypi_only():
    metadata = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))

    assert [package["registryType"] for package in metadata["packages"]] == ["pypi"]
    serialized = json.dumps(metadata)
    assert "docker.io/n24q02m/better-code-review-graph" not in serialized
    assert "ghcr.io/n24q02m/better-code-review-graph" not in serialized


def test_registry_description_matches_project_metadata_and_limit():
    metadata = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]

    description = metadata["description"]
    assert description == project["description"]
    assert 0 < len(description) <= 100


def test_embedding_dependencies_and_lock_use_stable_releases():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {package["name"]: package for package in lock["package"]}

    requirements = project["dependencies"]
    fr_reqs = [r for r in requirements if r.startswith("fastretrieval")]
    assert len(fr_reqs) == 1, fr_reqs
    assert fr_reqs[0].startswith("fastretrieval>=")
    assert fr_reqs[0].endswith(",<2")
    fr_floor = Version(fr_reqs[0].split(">=")[1].split(",")[0])
    assert fr_floor >= Version("1.4.0"), fr_reqs[0]
    assert "n24q02m-mcp-core[llm]==1.24.6" in requirements
    legacy_distribution = "qwen" + "3-embed"
    assert not any(
        legacy_distribution in requirement.casefold() for requirement in requirements
    )
    locked_fr = Version(packages["fastretrieval"]["version"])
    assert locked_fr >= fr_floor, locked_fr
    assert locked_fr < Version("2"), locked_fr
    assert packages["n24q02m-mcp-core"]["version"] == "1.24.6"
    assert legacy_distribution not in packages


def test_registry_manifest_validation_precedes_authentication_and_publish():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    steps = _named_run_steps(workflow, "publish-mcp-registry")
    names = [name for name, _ in steps]
    commands = dict(steps)

    install = names.index("Install MCP Publisher")
    validate = names.index("Validate MCP Registry manifest")
    login = names.index("Login to MCP Registry")
    publish = names.index("Publish to MCP Registry")

    assert install < validate < login < publish
    assert commands["Validate MCP Registry manifest"] == (
        "./mcp-publisher validate server.json"
    )
    assert commands["Login to MCP Registry"] == "./mcp-publisher login github-oidc"
    assert commands["Publish to MCP Registry"] == "./mcp-publisher publish"


def test_docs_keep_source_self_hosting_but_mark_public_oci_historical():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert (ROOT / "Dockerfile").is_file()
    assert "Historical public OCI tags are retained" in readme
    assert re.search(
        r"new\s+public Docker Hub/GHCR images are no longer\s+published", readme
    )
    assert "img.shields.io/docker" not in readme
    for guidance in (agents, claude):
        assert "new public OCI images do not" in guidance
        assert "eligible stable releases -> MCP Registry" in guidance
