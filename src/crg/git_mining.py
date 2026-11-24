"""Git co-change edge mining (CRG-16).

Mines temporal co-change probabilities ``P(B | A) = co_changes(A, B) / commits(A)``
from ``git log --numstat`` and stores directed ``CO_CHANGES_WITH`` edges in
``GraphStore`` with ``confidence = P(B | A)`` and ``resolution = "heuristic"``.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING

from .parser import EdgeInfo

if TYPE_CHECKING:
    from .graph import GraphStore

_COMMIT_MARKER = "COMMIT:"


def _parse_numstat_commits(
    stdout: str, *, max_files_per_commit: int = 50
) -> list[list[str]]:
    commits: list[list[str]] = []
    current: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line.startswith(_COMMIT_MARKER):
            if 1 <= len(current) <= max_files_per_commit:
                commits.append(list(dict.fromkeys(current)))
            current = []
            continue
        if not line:
            continue
        parts = raw_line.split("\t")
        if len(parts) >= 3:
            file_part = parts[-1].strip()
            if "=>" in file_part and "{" not in file_part:
                file_part = file_part.split("=>")[-1].strip()
            if file_part:
                current.append(file_part.replace("\\", "/"))
    if 1 <= len(current) <= max_files_per_commit:
        commits.append(list(dict.fromkeys(current)))
    return commits


def mine_co_changes(
    repo_root: Path,
    store: GraphStore,
    *,
    max_commits: int = 1000,
    min_confidence: float = 0.3,
    min_co_changes: int = 2,
) -> dict[str, int]:
    """Compute conditional file co-change probabilities and store CO_CHANGES_WITH edges."""
    root = repo_root.resolve()
    git_check = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if git_check.returncode != 0:
        return {"commits_scanned": 0, "edges_upserted": 0}

    log_proc = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            f"-n{max_commits}",
            "--numstat",
            f"--format={_COMMIT_MARKER}%H",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if log_proc.returncode != 0 or not log_proc.stdout.strip():
        return {"commits_scanned": 0, "edges_upserted": 0}

    commits = _parse_numstat_commits(log_proc.stdout)
    file_counts: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    for touched in commits:
        for f in touched:
            file_counts[f] += 1
        if len(touched) >= 2:
            for a, b in combinations(sorted(touched), 2):
                pair_counts[(a, b)] += 1

    # Map normalized relative paths -> graph File qualified_names
    file_lookup: dict[str, str] = {}
    for fp in store.get_all_files():
        p = Path(fp)
        file_lookup[p.as_posix()] = fp
        try:
            rel = p.resolve().relative_to(root).as_posix()
            file_lookup[rel] = fp
        except ValueError:
            pass

    edges_upserted = 0
    for (a, b), co_count in pair_counts.items():
        if co_count < min_co_changes:
            continue
        qa = file_lookup.get(a) or file_lookup.get(str((root / a).resolve().as_posix()))
        qb = file_lookup.get(b) or file_lookup.get(str((root / b).resolve().as_posix()))
        if not qa or not qb:
            continue
        for src_rel, src_qn, dst_qn in ((a, qa, qb), (b, qb, qa)):
            denom = file_counts[src_rel]
            if denom <= 0:
                continue
            conf = co_count / denom
            if conf < min_confidence:
                continue
            store.upsert_edge(
                EdgeInfo(
                    kind="CO_CHANGES_WITH",
                    source=src_qn,
                    target=dst_qn,
                    file_path=src_qn,
                    line=1,
                    extra={
                        "co_changes": co_count,
                        "commits": denom,
                    },
                    confidence=round(conf, 4),
                    resolution="heuristic",
                )
            )
            edges_upserted += 1

    if edges_upserted:
        store.commit()
    return {
        "commits_scanned": len(commits),
        "edges_upserted": edges_upserted,
    }
