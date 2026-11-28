"""Contracts for publishing releases draft-first under GitHub immutable releases.

An immutable release refuses new assets once it is published, so the release
job may only create a draft, every asset job uploads into that draft, and a
final job publishes it after the last asset is attached.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def _step_block(job: str, name: str) -> str:
    match = re.search(
        rf"^      - (?:name: {re.escape(name)}|uses: [^\n]+\n        id: {re.escape(name)})\n"
        r"(?P<body>.*?)(?=^      - |\Z)",
        job,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, name
    return match.group("body")


def _needs(job: str) -> set[str]:
    match = re.search(r"^    needs: \[(?P<needs>[^\]]*)\]", job, flags=re.MULTILINE)
    assert match is not None
    return {need.strip() for need in match.group("needs").split(",")}


def test_semantic_release_tags_without_publishing_a_release():
    release = _job_block(WORKFLOW.read_text(encoding="utf-8"), "release")
    real_run = _step_block(release, "release")

    assert "vcs_release: false" in real_run
    # The upstream publish action looks the release up by tag, which never finds
    # a draft, and the release job builds nothing for it to upload.
    assert "python-semantic-release/publish-action" not in release


def test_release_job_creates_the_release_as_a_draft():
    release = _job_block(WORKFLOW.read_text(encoding="utf-8"), "release")
    draft = _step_block(release, "Create the draft GitHub release")

    assert "steps.release.outputs.released == 'true'" in draft
    assert "gh release create" in draft
    assert "--draft" in draft
    assert "--verify-tag" in draft
    assert "steps.release.outputs.release_notes" in draft
    assert "steps.release.outputs.is_prerelease" in draft


def test_assets_upload_before_the_release_is_published():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    finalize = _job_block(workflow, "finalize-release")

    assert {"release", "publish-pypi", "release-lock"} <= _needs(finalize)
    assert "needs.release.outputs.released == 'true'" in finalize
    assert "--draft=false" in finalize
    assert "isImmutable" in finalize
    assert "requirements.lock" in finalize


def test_tap_bump_waits_for_the_published_release():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    # The tap and bucket download requirements.lock from the public release URL,
    # which a draft does not serve.
    assert "finalize-release" in _needs(_job_block(workflow, "bump-taps"))


def test_pypi_publish_blocks_unlisted_egress():
    publish = _job_block(WORKFLOW.read_text(encoding="utf-8"), "publish-pypi")
    harden = _step_block(publish, "Harden Runner")

    assert "egress-policy: block" in harden
    # harden-runner splits the allowlist on spaces: a literal block (|) keeps the
    # newlines and collapses the list into one unusable entry.
    assert "allowed-endpoints: >\n" in harden
    for endpoint in (
        "github.com:443",
        "api.github.com:443",
        "release-assets.githubusercontent.com:443",
        "token.actions.githubusercontent.com:443",
        "releases.astral.sh:443",
        "pypi.org:443",
        "files.pythonhosted.org:443",
        "upload.pypi.org:443",
    ):
        assert re.search(
            rf"^            {re.escape(endpoint)}$", harden, re.MULTILINE
        ), endpoint
