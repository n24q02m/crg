"""Cross-repo federation registry (Phase 2 Task 2).

Maintains a registry of federated repos backed by the ``repos`` table
(added in alembic revision ``003_federation``). Generates stable,
path-derived ``repo_id`` values and provides :meth:`RepoRegistry.assign`
for parsers / incremental update to map a filesystem path back to its
owning repo.

The registry is intentionally a thin layer on top of the SQLite
connection owned by :class:`~crg.graph.GraphStore`.
Federation concerns live here rather than in ``GraphStore`` so the
public graph API stays focused on nodes / edges; the connection access
is package-private (``store._conn``).
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import GraphStore


@dataclass(frozen=True)
class RepoEntry:
    """In-memory snapshot of a row in the ``repos`` table."""

    repo_id: str
    path: Path
    remote_url: str | None
    last_indexed_sha: str | None
    first_indexed_at: int
    last_indexed_at: int


def derive_repo_id(path: Path) -> str:
    """Deterministic ``<basename>-<sha256[:8]>`` of the absolute path.

    The id is stable across machines and across time because it depends
    only on the resolved path, never on filesystem metadata. Empty,
    ``.``, or ``..`` basenames (which happen for filesystem roots like
    ``/`` or ``C:\\``) normalise to ``"root"`` so the id stays
    well-formed.
    """
    abs_path = str(path.resolve())
    basename = path.resolve().name
    if basename in ("", ".", ".."):
        basename = "root"
    digest = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:8]
    return f"{basename}-{digest}"


class RepoRegistry:
    """In-memory + DB-backed cross-repo registry.

    Parameters
    ----------
    store:
        The :class:`GraphStore` whose SQLite connection backs the
        ``repos`` table.
    repo_id_map:
        Optional caller-supplied overrides keyed by absolute path. When
        :meth:`add` is called with a path present in this map, the
        mapped value wins over the derived id. The keys are normalised
        through ``Path.resolve`` on construction so callers may pass
        either resolved or unresolved paths.
    """

    def __init__(
        self,
        store: GraphStore,
        *,
        repo_id_map: dict[Path, str] | None = None,
    ) -> None:
        self._store = store
        self._user_overrides: dict[Path, str] = {
            p.resolve(): rid for p, rid in (repo_id_map or {}).items()
        }
        self._entries: dict[str, RepoEntry] = {}
        # Path-keyed cache for fast assign() lookups.
        self._by_path: dict[Path, str] = {}
        self._load_from_store()

    # --- Construction helper ---

    def _load_from_store(self) -> None:
        """Populate the in-memory caches from the ``repos`` table."""
        cursor = self._store._conn.execute(
            "SELECT repo_id, path, remote_url, last_indexed_sha, "
            "first_indexed_at, last_indexed_at FROM repos"
        )
        for row in cursor:
            entry = RepoEntry(
                repo_id=row["repo_id"],
                path=Path(row["path"]),
                remote_url=row["remote_url"],
                last_indexed_sha=row["last_indexed_sha"],
                first_indexed_at=row["first_indexed_at"],
                last_indexed_at=row["last_indexed_at"],
            )
            self._entries[entry.repo_id] = entry
            self._by_path[entry.path] = entry.repo_id

    # --- Public API ---

    def add(
        self,
        path: Path,
        *,
        remote_url: str | None = None,
    ) -> str:
        """Register a repo at ``path``. Returns its ``repo_id`` (idempotent).

        Re-adding an existing path keeps ``first_indexed_at`` intact and
        bumps ``last_indexed_at`` to the current wall clock. User
        overrides supplied via the constructor's ``repo_id_map`` take
        precedence over the derived id.
        """
        abs_path = path.resolve()
        repo_id = self._user_overrides.get(abs_path) or derive_repo_id(path)
        now = int(time.time())

        existing = self._entries.get(repo_id)
        if existing is not None:
            self._store._conn.execute(
                "UPDATE repos SET last_indexed_at = ?, "
                "remote_url = COALESCE(?, remote_url) WHERE repo_id = ?",
                (now, remote_url, repo_id),
            )
            self._store._conn.commit()
            updated = RepoEntry(
                repo_id=repo_id,
                path=existing.path,
                remote_url=remote_url or existing.remote_url,
                last_indexed_sha=existing.last_indexed_sha,
                first_indexed_at=existing.first_indexed_at,
                last_indexed_at=now,
            )
            self._entries[repo_id] = updated
            return repo_id

        self._store._conn.execute(
            "INSERT INTO repos (repo_id, path, remote_url, last_indexed_sha, "
            "first_indexed_at, last_indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (repo_id, str(abs_path), remote_url, None, now, now),
        )
        self._store._conn.commit()
        self._entries[repo_id] = RepoEntry(
            repo_id=repo_id,
            path=abs_path,
            remote_url=remote_url,
            last_indexed_sha=None,
            first_indexed_at=now,
            last_indexed_at=now,
        )
        self._by_path[abs_path] = repo_id
        return repo_id

    def assign(self, file_path: Path) -> str:
        """Return the ``repo_id`` whose root contains ``file_path``.

        The longest matching root wins so a child repo registered under
        a parent (e.g. a vendored fork inside a monorepo) takes
        precedence over the parent for files within the child.

        Raises
        ------
        ValueError
            When no registered repo is an ancestor of ``file_path``.
        """
        abs_file = file_path.resolve()
        best: tuple[Path, str] | None = None
        for root, rid in self._by_path.items():
            try:
                abs_file.relative_to(root)
            except ValueError:
                continue
            if best is None or len(root.parts) > len(best[0].parts):
                best = (root, rid)
        if best is None:
            raise ValueError(
                f"No registered repo contains {abs_file}. "
                f"Registered roots: {sorted(self._by_path)}"
            )
        return best[1]

    def update_last_indexed_sha(self, repo_id: str, sha: str) -> None:
        """Record the last commit SHA indexed for ``repo_id``."""
        if repo_id not in self._entries:
            raise ValueError(f"Unknown repo_id: {repo_id}")
        now = int(time.time())
        self._store._conn.execute(
            "UPDATE repos SET last_indexed_sha = ?, last_indexed_at = ? "
            "WHERE repo_id = ?",
            (sha, now, repo_id),
        )
        self._store._conn.commit()
        existing = self._entries[repo_id]
        self._entries[repo_id] = RepoEntry(
            repo_id=repo_id,
            path=existing.path,
            remote_url=existing.remote_url,
            last_indexed_sha=sha,
            first_indexed_at=existing.first_indexed_at,
            last_indexed_at=now,
        )

    def entries(self) -> list[RepoEntry]:
        """Return all registered entries (a copy of the in-memory state)."""
        return list(self._entries.values())


# ---------------------------------------------------------------------------
# Phase 3 Task 7: first-parent commit backfill
# ---------------------------------------------------------------------------


# git log --format placeholders separated by NUL bytes so the columns
# survive commit messages containing tabs / pipes / other delimiters
# people occasionally use. The trailing ``%s`` is the subject line; we
# deliberately do NOT use ``%B`` (full body) — the ``commits`` table is
# meant for fast SHA→timestamp lookup, not full-text search.
#
# Layout (split by ``\x00``):
#   parts[0] = sha           (%H)
#   parts[1] = parents       (%P, space-separated; empty for root commit)
#   parts[2] = commit time   (%ct, unix timestamp as decimal string)
#   parts[3] = subject line  (%s)
_GIT_LOG_FORMAT: str = "%H%x00%P%x00%ct%x00%s"

# Hard upper bound on git subprocess execution. A 60s timeout is plenty
# for repos with hundreds of thousands of commits and bounds the worst
# case if ``git`` hangs (corrupt index, hung pager, FUSE mount stall).
_GIT_LOG_TIMEOUT_SECONDS: int = 60


def backfill_commits_for_repo(
    store: GraphStore,
    repo_id: str,
    repo_root: Path,
) -> int:
    """Walk ``git log --first-parent`` and populate the ``commits`` table.

    Parameters
    ----------
    store:
        The :class:`GraphStore` whose SQLite connection backs the
        ``commits`` table (created by alembic revision 006).
    repo_id:
        The registry id assigned to ``repo_root``. Every inserted row is
        tagged with this value so the FK to ``repos.repo_id`` resolves.
    repo_root:
        Filesystem path of the git working tree to walk.

    Returns
    -------
    int
        The number of commit rows actually inserted (0 if ``repo_root``
        is not a git repo, ``git`` is missing, the subprocess fails, or
        every commit was already present).

    Notes
    -----
    The walk uses ``--first-parent`` so merge commits collapse to the
    mainline; merged feature-branch commits are intentionally excluded
    (the table is for "what landed on the trunk" lookups, not full
    history). Existing rows are preserved via ``INSERT OR IGNORE``, so
    calling the function repeatedly is safe and idempotent.

    The helper is best-effort: any failure path returns ``0`` rather
    than raising so a non-git directory or a transient ``git`` failure
    on a single root never aborts a federated build.
    """
    if not (repo_root / ".git").exists():
        return 0
    try:
        import shutil

        git_bin = shutil.which("git") or "git"
        proc = subprocess.run(
            [
                git_bin,
                "log",
                "--first-parent",
                f"--format={_GIT_LOG_FORMAT}",
                "--",
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_LOG_TIMEOUT_SECONDS,
            # Detach stdin: an inherited stdio pipe stalls the output reader in
            # the MCP server's worker thread on Windows. See incremental.py.
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0:
        return 0

    to_insert = []
    for line in proc.stdout.splitlines():
        # Each row is exactly 4 NUL-separated columns; anything else
        # signals a malformed line (e.g. truncated output) and we skip
        # rather than insert garbage.
        parts = line.split("\x00")
        if len(parts) < 4:
            continue
        sha, parents, timestamp, message = parts[0], parts[1], parts[2], parts[3]
        # First-parent only: take the head of the parents list. Root
        # commit has no parents (empty string) → ``parent_sha`` is NULL.
        parent_sha = parents.split()[0] if parents.strip() else None
        try:
            ts = int(timestamp)
        except ValueError:
            # Defensive: ``%ct`` is always a decimal int, but a corrupt
            # or future git version that emits something else should
            # not blow up the backfill. Skip the row instead.
            continue
        to_insert.append((sha, repo_id, parent_sha, ts, message))

    if not to_insert:
        return 0

    # Assign monotonic chronological order (root = 1 .. HEAD = N) for temporal
    # range queries (`CRG-5`). `git log` emits newest-first, so reverse index.
    total = len(to_insert)
    ordered_rows = [
        (sha, rid, parent_sha, ts, msg, total - idx)
        for idx, (sha, rid, parent_sha, ts, msg) in enumerate(to_insert)
    ]

    cursor = store._conn.executemany(
        "INSERT OR IGNORE INTO commits "
        "(sha, repo_id, parent_sha, timestamp, message, commit_order) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ordered_rows,
    )
    inserted = cursor.rowcount
    store._conn.commit()
    return inserted
