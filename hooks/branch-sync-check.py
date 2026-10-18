"""PostToolUse hook: ask for a rebuild when a branch move outran the graph.

Runs after shell calls and reacts only to commands that move the branch
(``git pull``, ``git merge``). It deliberately does **not** re-index anything.

The bundled incremental hook already fires on the same event and widens its
diff base from ``HEAD~1`` to the commit recorded at the last build, so an
ordinary ``git pull`` -- however many commits it brings in -- is already
covered. Re-indexing here would spend a second process spawn on every shell
call for no additional coverage.

What the incremental pass cannot do is recover when the recorded commit is no
longer reachable. After a rebase, an amended history, or a force-pushed
branch, that base fails validation and the pass silently falls back to
``HEAD~1``, leaving everything else the branch move brought in unindexed. The
graph then looks current while describing code that no longer exists.

This hook detects exactly that case and asks for a full rebuild. Anything it
cannot prove, it stays quiet about: a false alarm on every pull would train
the reader to ignore it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _graph_state import (
    find_repo_root,
    git_dir,
    graph_db_path,
    read_head,
    read_metadata,
)

GIT_TIMEOUT = 5

# ``git`` plus its repo-selecting options, then pull/merge as the subcommand.
# Written to not fire on `git commit -m "merge the thing"` or `git log --merges`.
BRANCH_MOVING = re.compile(
    r"\bgit\b"
    r"(?:\s+(?:-C\s+\S+|-c\s+\S+|--git-dir=\S+|--work-tree=\S+))*"
    r"\s+(?:pull|merge)\b"
)


def is_valid_commit(repo_root: Path, sha: str) -> bool:
    """Whether ``sha`` still resolves to a commit in this repository.

    Returns ``True`` when the answer cannot be determined, so an unusual
    environment produces silence rather than a spurious rebuild request.
    """
    git_bin = shutil.which("git")
    if not git_bin:
        return True
    try:
        result = subprocess.run(
            [git_bin, "cat-file", "-e", "--end-of-options", f"{sha}^{{commit}}"],
            cwd=str(repo_root),
            capture_output=True,
            timeout=GIT_TIMEOUT,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return result.returncode == 0


def emit(text: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload))


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    tool_input = payload.get("tool_input")
    command = ""
    if isinstance(tool_input, dict):
        command = str(tool_input.get("command") or "")
    if not BRANCH_MOVING.search(command):
        return 0

    start = Path(str(payload.get("cwd") or os.getcwd()))
    repo_root = find_repo_root(start)
    if repo_root is None:
        return 0

    db_path = graph_db_path(repo_root)
    last_built = read_metadata(db_path, "last_built_head")
    if not last_built:
        # No recorded build point: there is no incremental base to lose.
        return 0

    gdir = git_dir(repo_root)
    head = read_head(gdir) if gdir is not None else None
    if head and head == last_built:
        # The graph already sits on the current commit.
        return 0

    if is_valid_commit(repo_root, last_built):
        # The incremental pass can widen its base to this commit and catch up.
        return 0

    emit(
        "[crg] The branch moved and the commit the graph "
        f"was built from ({last_built[:8]}) no longer exists in this "
        "repository, so the incremental update could not diff against it and "
        "indexed only the last commit. Graph answers about anything else the "
        "branch move brought in are unreliable until you run "
        'graph(action="build", full_rebuild=true).'
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # A hook must never break the tool call it is attached to.
        sys.exit(0)
