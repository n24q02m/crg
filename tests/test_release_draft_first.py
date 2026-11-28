"""Contracts for publishing releases draft-first under GitHub immutable releases.

An immutable release refuses new assets once it is published, so the release
job may only create a draft, every asset job uploads into that draft, and a
final job publishes it after the last asset is attached.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "cd.yml"
_RECOVERY_DRAFT_GATE = "inputs.publish_existing_tag == '' || needs.release.outputs.release_state == 'draft'"


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


def _outputs(job: str) -> dict[str, str]:
    match = re.search(
        r"^    outputs:\n(?P<body>(?:^      .*\n)+)", job, flags=re.MULTILINE
    )
    assert match is not None
    pairs = re.findall(
        r"^      ([a-z_]+): (.+)$", match.group("body"), flags=re.MULTILINE
    )
    return dict(pairs)


def _run_script(step: str) -> str:
    match = re.search(r"^        run: \|\n(?P<body>.*)", step, re.MULTILINE | re.DOTALL)
    assert match is not None
    return textwrap.dedent(match.group("body"))


def _bash() -> str:
    bash = shutil.which("bash")
    # On Windows, System32\bash.exe is the WSL launcher, not a shell to drive here.
    if bash is None or Path(bash).parent.name.lower() == "system32":
        pytest.skip("bash is needed to execute the workflow step")
    return bash


def _run_recovery(
    tmp_path: Path,
    *,
    tag: str,
    pyproject_version: str,
    gh_view: str,
    tagged: bool = True,
) -> tuple[subprocess.CompletedProcess[str], dict[str, str], list[str]]:
    """Run the recovery step in a repo whose tag carries pyproject_version.

    gh_view is what the stubbed `gh release view --jq .isDraft` answers:
    "true" or "false", "missing" for a tag with no release, anything else for
    an API error.
    """
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = ci\n\temail = ci@example.invalid\n", encoding="utf-8"
    )
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "n24q02m-crg"\nversion = "{pyproject_version}"\n',
        encoding="utf-8",
    )
    git_steps = [["init", "-q"], ["add", "pyproject.toml"], ["commit", "-q", "-m", "r"]]
    if tagged:
        git_steps.append(["tag", tag])
    for args in git_steps:
        subprocess.run(
            ["git", *args], cwd=repo, env=env, check=True, capture_output=True
        )

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    calls = tmp_path / "gh-calls.txt"
    view = {
        "true": "echo true",
        "false": "echo false",
        "missing": "echo 'release not found' >&2; exit 1",
    }.get(gh_view, "echo 'HTTP 502: Bad Gateway' >&2; exit 1")
    (stubs / "gh").write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{calls.as_posix()}"\n{view}\n',
        encoding="utf-8",
        newline="\n",
    )
    # The runner's python3 has tomllib; so does the interpreter running this test.
    (stubs / "python3").write_text(
        f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    for stub in stubs.iterdir():
        stub.chmod(0o755)

    output = tmp_path / "github-output.txt"
    output.write_text("", encoding="utf-8")
    env.update(
        {
            "PUBLISH_EXISTING_TAG": tag,
            "GH_TOKEN": "placeholder",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(output),
            "RUNNER_TEMP": str(tmp_path),
            "PATH": f"{stubs}{os.pathsep}{env['PATH']}",
        }
    )
    release = _job_block(WORKFLOW.read_text(encoding="utf-8"), "release")
    script = tmp_path / "step.sh"
    script.write_text(
        _run_script(
            _step_block(release, "Use existing tag (immutable-release recovery)")
        ),
        encoding="utf-8",
        newline="\n",
    )
    result = subprocess.run(
        [_bash(), "-e", str(script)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    written = dict(
        line.split("=", 1)
        for line in output.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    seen = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, written, seen


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


def test_release_outputs_fall_back_to_the_recovery_step():
    outputs = _outputs(_job_block(WORKFLOW.read_text(encoding="utf-8"), "release"))

    # Without the fallback, publish_existing_tag leaves `released` empty and every
    # publish job gated on it is skipped.
    for key in ("released", "tag", "version", "is_prerelease"):
        assert outputs[key] == (
            f"${{{{ steps.release.outputs.{key} || steps.forced.outputs.{key} }}}}"
        )
    assert outputs["release_state"] == "${{ steps.forced.outputs.release_state }}"


@pytest.mark.parametrize("job", ["release-lock", "finalize-release"])
def test_recovery_touches_the_github_release_only_while_it_is_a_draft(job: str):
    # A published immutable release takes no new asset, and a tag reserved by a
    # deleted immutable release takes no new release, so recovery leaves both to
    # the registries. bump-taps needs finalize-release and follows it.
    assert _RECOVERY_DRAFT_GATE in _job_block(WORKFLOW.read_text(encoding="utf-8"), job)


@pytest.mark.parametrize(
    ("tag", "gh_view", "is_prerelease", "release_state"),
    [
        ("v3.38.0", "true", "false", "draft"),
        ("v3.38.0-beta.1", "true", "true", "draft"),
        ("v3.38.0", "false", "false", "published"),
        ("v3.38.0-beta.1", "missing", "true", "none"),
    ],
)
def test_recovery_reads_the_tag_and_its_release(
    tmp_path: Path, tag: str, gh_view: str, is_prerelease: str, release_state: str
):
    result, written, seen = _run_recovery(
        tmp_path, tag=tag, pyproject_version=tag[1:], gh_view=gh_view
    )

    assert result.returncode == 0, result.stderr
    assert written == {
        "released": "true",
        "tag": tag,
        "version": tag[1:],
        "is_prerelease": is_prerelease,
        "release_state": release_state,
    }
    assert seen == [
        f"release view {tag} --json isDraft --jq .isDraft --repo owner/repo"
    ]
    assert ("::notice::" in result.stdout) is (release_state != "draft")


def test_recovery_stops_on_any_other_release_lookup_error(tmp_path: Path):
    result, written, _ = _run_recovery(
        tmp_path, tag="v3.38.0", pyproject_version="3.38.0", gh_view="error"
    )

    assert result.returncode != 0
    assert "HTTP 502" in result.stderr
    assert written == {}


def test_recovery_refuses_a_tag_built_for_another_version(tmp_path: Path):
    # PyPI never takes a version twice: publishing the wrong one is permanent.
    result, written, seen = _run_recovery(
        tmp_path, tag="v3.38.0", pyproject_version="3.37.0", gh_view="true"
    )

    assert result.returncode != 0
    assert "3.37.0" in result.stdout
    assert written == {}
    assert seen == []


def test_recovery_refuses_a_tag_that_does_not_exist(tmp_path: Path):
    result, written, seen = _run_recovery(
        tmp_path,
        tag="v3.38.0",
        pyproject_version="3.38.0",
        gh_view="true",
        tagged=False,
    )

    assert result.returncode != 0
    assert written == {}
    assert seen == []
