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
import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


# ---------------------------------------------------------------------------
# HTTP endpoint linking
# ---------------------------------------------------------------------------

# Endpoints declared on a router that no file mounts are reachable only if
# some file outside the graph mounts them, so their path is less certain.
_UNMOUNTED_ROUTER_FACTOR = 0.7
_MAX_MOUNT_DEPTH = 5
_HTTP_STAT_KEYS = (
    "endpoints",
    "calls",
    "linked",
    "cross_repo",
    "ambiguous",
    "unmatched",
    "dynamic",
    "external",
    "handlers_bound",
)


@dataclass
class _EndpointRow:
    row_id: int
    qualified_name: str
    file_path: str
    line: int
    repo_id: str
    method: str
    extra: dict[str, Any]
    factor: float


def _json_obj(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _segment_count(path: str) -> int:
    return len([segment for segment in path.split("/") if segment])


class _MountResolver:
    """Resolve the full URL prefixes of a router through its mounts."""

    def __init__(self, store: GraphStore, norm: Callable[[str], str]) -> None:
        self.routers: dict[str, dict[str, Any]] = {}
        self.mounts_into: dict[tuple[str, str], list[tuple[str, dict]]] = {}
        files = store._conn.execute(
            """SELECT file_path, extra FROM nodes
               WHERE kind = 'File' AND valid_to_sha IS NULL
                 AND (extra LIKE '%"http_mounts"%'
                      OR extra LIKE '%"http_routers"%')"""
        ).fetchall()
        parsed = [(norm(row["file_path"]), _json_obj(row["extra"])) for row in files]
        for file_path, extra in parsed:
            routers = extra.get("http_routers")
            if isinstance(routers, dict):
                self.routers[file_path] = routers
        for mount_file, extra in parsed:
            mounts = extra.get("http_mounts")
            for mount in mounts if isinstance(mounts, list) else []:
                if not isinstance(mount, dict):
                    continue
                child_file = mount.get("child_file")
                target_file = norm(child_file) if child_file else mount_file
                child = mount.get("child") or self._single_router(target_file)
                if isinstance(child, str):
                    key = (target_file, child)
                    self.mounts_into.setdefault(key, []).append((mount_file, mount))

    def _single_router(self, file_path: str) -> str | None:
        names = [
            name
            for name, info in self.routers.get(file_path, {}).items()
            if isinstance(info, dict) and info.get("kind") == "router"
        ]
        return names[0] if len(names) == 1 else None

    def _own_prefix(self, file_path: str, router: str) -> str | None:
        info = self.routers.get(file_path, {}).get(router)
        if not isinstance(info, dict):
            return ""
        prefix = info.get("prefix", "")
        return prefix if isinstance(prefix, str) else None

    def chain(
        self,
        file_path: str,
        router: str,
        seen: frozenset[tuple[str, str]] = frozenset(),
    ) -> list[tuple[str, bool]]:
        """Return ``(full prefix, mounted)`` for every way ``router`` is served.

        An empty list means the router is only served under a prefix that
        is not known statically, so its endpoints cannot be matched.
        """
        own = self._own_prefix(file_path, router)
        if own is None or len(seen) > _MAX_MOUNT_DEPTH:
            return []
        mounts = self.mounts_into.get((file_path, router))
        if not mounts:
            return [(own, False)]
        seen = seen | {(file_path, router)}
        out: list[tuple[str, bool]] = []
        for mount_file, mount in mounts:
            prefix = mount.get("prefix")
            parent = mount.get("parent")
            if (
                not isinstance(prefix, str)
                or not isinstance(parent, str)
                or (mount_file, parent) in seen
                or parent not in self.routers.get(mount_file, {})
            ):
                continue
            own_eff = prefix if mount.get("replaces_prefix") else f"{prefix}/{own}"
            for outer, _mounted in self.chain(mount_file, parent, seen):
                out.append((f"{outer}/{own_eff}", True))
        return out


def _effective_paths(
    resolver: _MountResolver, endpoint: _EndpointRow, norm: Callable[[str], str]
) -> tuple[list[str], bool]:
    from .http_endpoints import normalize_route_path

    router = endpoint.extra.get("router")
    path = endpoint.extra["path"]
    if not isinstance(router, str):
        return [path], False
    chain = resolver.chain(norm(endpoint.file_path), router)
    mounted = [prefix for prefix, flag in chain if flag]
    if mounted:
        raw_path = str(endpoint.extra.get("raw_path") or "")
        paths = {normalize_route_path(f"{prefix}/{raw_path}") for prefix in mounted}
        return sorted(paths), True
    return ([path] if chain else []), False


def _route_keys(paths: list[str]) -> list[str]:
    """Return the match keys of ``paths``, minus all-parameter routes.

    A route made only of parameters (``/{id}``) would match every call with
    the same number of segments, so it is never used for linking. The root
    route ``/`` is kept.
    """
    from .http_endpoints import path_key

    keys = set()
    for path in paths:
        key = path_key(path)
        if key == "/" or any(s != "{}" for s in key.split("/") if s):
            keys.add(key)
    return sorted(keys)


def _pick_endpoint(
    candidates: list[_EndpointRow], caller_repo: str, method: str
) -> _EndpointRow | None:
    """Choose the single best endpoint or None when the choice is a tie."""
    pool = candidates
    if len(pool) > 1:
        pool = [e for e in pool if e.repo_id == caller_repo] or pool
    if len(pool) > 1:
        pool = [e for e in pool if e.method == method] or pool
    return pool[0] if len(pool) == 1 else None


def link_http_endpoints(store: GraphStore) -> dict[str, int]:
    """Turn recorded HTTP client calls into ``CALLS_ENDPOINT`` edges.

    Runs after every file (and every federated repo) is parsed. Router
    mounts are resolved across files to give each Endpoint its effective
    paths (stored as ``extra["effective_paths"]``). A call links only when
    one endpoint matches its method and normalised path best; a tie is
    broken by preferring an endpoint in the caller's own repo, then an
    exact method over a catch-all route. Dynamic URLs, external hosts,
    ties and misses never produce an edge; they are only counted.

    The pass is idempotent: every run replaces all current
    ``CALLS_ENDPOINT`` edges and all cross-file handler bindings.
    """
    from .http_endpoints import ANY_METHOD, is_internal_host, match_score
    from .parser import EdgeInfo

    stats = dict.fromkeys(_HTTP_STAT_KEYS, 0)
    conn = store._conn
    conn.execute(
        "DELETE FROM edges WHERE kind = 'CALLS_ENDPOINT' AND valid_to_sha IS NULL"
    )
    conn.execute(
        "DELETE FROM edges WHERE kind = 'ROUTES_TO' "
        "AND resolution = 'http_handler' AND valid_to_sha IS NULL"
    )

    norm_cache: dict[str, str] = {}

    def norm(path: str) -> str:
        if path not in norm_cache:
            norm_cache[path] = os.path.normcase(str(Path(path).resolve()))
        return norm_cache[path]

    resolver = _MountResolver(store, norm)
    endpoints: list[_EndpointRow] = []
    by_segments: dict[int, list[tuple[str, _EndpointRow]]] = {}
    for row in conn.execute(
        """SELECT id, qualified_name, file_path, line_start, repo_id, extra
           FROM nodes WHERE kind = 'Endpoint' AND valid_to_sha IS NULL"""
    ).fetchall():
        extra = _json_obj(row["extra"])
        if not isinstance(extra.get("http_method"), str) or not isinstance(
            extra.get("path"), str
        ):
            continue
        endpoint = _EndpointRow(
            row_id=row["id"],
            qualified_name=row["qualified_name"],
            file_path=row["file_path"],
            line=row["line_start"] or 0,
            repo_id=row["repo_id"] or "",
            method=extra["http_method"],
            extra=extra,
            factor=1.0,
        )
        paths, mounted = _effective_paths(resolver, endpoint, norm)
        if not mounted and extra.get("router_kind") == "router":
            endpoint.factor = _UNMOUNTED_ROUTER_FACTOR
        if extra.get("effective_paths") != paths:
            extra["effective_paths"] = paths
            conn.execute(
                "UPDATE nodes SET extra = ? WHERE id = ?",
                (json.dumps(extra, separators=(",", ":")), row["id"]),
            )
        endpoints.append(endpoint)
        for key in _route_keys(paths):
            by_segments.setdefault(_segment_count(key), []).append((key, endpoint))
    stats["endpoints"] = len(endpoints)

    for caller in conn.execute(
        """SELECT qualified_name, file_path, repo_id, extra FROM nodes
           WHERE valid_to_sha IS NULL AND extra LIKE '%"http_calls"%'"""
    ).fetchall():
        calls = _json_obj(caller["extra"]).get("http_calls")
        caller_repo = caller["repo_id"] or ""
        for call in calls if isinstance(calls, list) else []:
            if not isinstance(call, dict):
                continue
            stats["calls"] += 1
            method, path, host = call.get("method"), call.get("path"), call.get("host")
            if call.get("dynamic") or not isinstance(path, str):
                stats["dynamic"] += 1
                continue
            if isinstance(host, str) and not is_internal_host(host):
                stats["external"] += 1
                continue
            best: dict[int, tuple[int, _EndpointRow]] = {}
            for key, endpoint in by_segments.get(_segment_count(path), []):
                if endpoint.method not in (method, ANY_METHOD):
                    continue
                score = match_score(path, key)
                previous = best.get(endpoint.row_id)
                if score is not None and (previous is None or score > previous[0]):
                    best[endpoint.row_id] = (score, endpoint)
            if not best:
                stats["unmatched"] += 1
                continue
            top = max(score for score, _endpoint in best.values())
            target = _pick_endpoint(
                [e for score, e in best.values() if score == top],
                caller_repo,
                str(method),
            )
            if target is None:
                stats["ambiguous"] += 1
                continue
            cross_repo = target.repo_id != caller_repo
            confidence = float(call.get("confidence") or 0.0) * target.factor
            store.upsert_edge(
                EdgeInfo(
                    kind="CALLS_ENDPOINT",
                    source=caller["qualified_name"],
                    target=target.qualified_name,
                    file_path=caller["file_path"],
                    line=int(call.get("line") or 0),
                    extra={
                        "http_method": method,
                        "path": path,
                        "endpoint_repo_id": target.repo_id,
                        "cross_repo": cross_repo,
                    },
                    repo_id=caller_repo,
                    confidence=round(confidence, 4),
                    resolution="http_route",
                )
            )
            stats["linked"] += 1
            stats["cross_repo"] += int(cross_repo)

    stats["handlers_bound"] = _bind_route_handlers(store, endpoints, norm)
    store._invalidate_cache()
    store.commit()
    return stats


def _bind_route_handlers(
    store: GraphStore, endpoints: list[_EndpointRow], norm: Callable[[str], str]
) -> int:
    """Bind route handlers imported from another file (``handler_ref``).

    The parser records the handler name and the file it was imported from;
    the edge is created only when that file defines exactly one Function
    with that name.
    """
    from .parser import EdgeInfo

    wanted: dict[tuple[str, str], list[_EndpointRow]] = {}
    for endpoint in endpoints:
        ref = endpoint.extra.get("handler_ref")
        if not isinstance(ref, dict):
            continue
        name, file_path = ref.get("name"), ref.get("file")
        if isinstance(name, str) and isinstance(file_path, str):
            wanted.setdefault((name, norm(file_path)), []).append(endpoint)
    if not wanted:
        return 0
    names = sorted({name for name, _file in wanted})
    placeholders = ",".join("?" for _ in names)
    matches: dict[tuple[str, str], list[str]] = {}
    for row in store._conn.execute(
        f"""SELECT name, file_path, qualified_name FROM nodes
            WHERE kind IN ('Function', 'Test') AND valid_to_sha IS NULL
              AND name IN ({placeholders})""",
        names,
    ):
        key = (row["name"], norm(row["file_path"]))
        if key in wanted:
            matches.setdefault(key, []).append(row["qualified_name"])
    bound = 0
    for key, qualified in matches.items():
        if len(qualified) != 1:
            continue
        for endpoint in wanted[key]:
            store.upsert_edge(
                EdgeInfo(
                    kind="ROUTES_TO",
                    source=endpoint.qualified_name,
                    target=qualified[0],
                    file_path=endpoint.file_path,
                    line=endpoint.line,
                    repo_id=endpoint.repo_id,
                    resolution="http_handler",
                )
            )
            bound += 1
    return bound
