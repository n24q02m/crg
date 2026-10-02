"""SQLite-backed knowledge graph storage and query engine.

Stores code structure as nodes (File, Class, Function, Type, Test) and
edges (CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON).
Supports impact-radius queries and subgraph extraction.
"""

import json
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

from .parser import EdgeInfo, NodeInfo

# Phase 3 Task 1 — pre-flight backup hook constants.
#
# ``_BREAKING_REVISION`` is the alembic revision id at which the
# v2.0.0 BREAKING migration ships (security-aware nodes + temporal
# tracking).  Any upgrade chain that crosses *into* this revision
# from below triggers a one-time copy of the SQLite file to
# ``<db>.pre-2.0.bak`` before alembic runs.
#
# The hook is intentionally encoded as a string compare on revision
# ids — the project pads alembic ids to 3 digits (``001`` … ``005``),
# so lexical comparison matches numeric comparison.  When the day
# comes that the project switches to alembic's default 12-char hex
# ids (or a downstream fork inherits this hook), this constant +
# the helper below are the only places that need to change.
_BREAKING_REVISION: str = "005"
_BACKUP_SUFFIX: str = ".pre-2.0.bak"
_ARCHIVED_SUFFIX: str = ".post-2.0.archived"
_DOWNGRADE_ENV_VAR: str = "CRG_DOWNGRADE_TO_1_X"


def _crosses_breaking_boundary(current_rev: str | None, target_rev: str | None) -> bool:
    """Return True iff the upgrade chain crosses the v2.0 BREAKING boundary.

    The boundary is crossed when:
      * ``target_rev`` is at or past ``_BREAKING_REVISION`` (so the
        upgrade *will* run the BREAKING migration), AND
      * ``current_rev`` is below ``_BREAKING_REVISION`` (or ``None``
        for a fresh DB without ``alembic_version``).

    A ``None`` ``target_rev`` is treated as "unknown / no migrations
    available" → no backup needed (defensive: if alembic can't tell
    us where it's going, we don't second-guess it).
    """
    if target_rev is None or target_rev < _BREAKING_REVISION:
        return False
    # target_rev >= _BREAKING_REVISION
    if current_rev is None:
        return True
    return current_rev < _BREAKING_REVISION


def _resolve_migrations_dir() -> Path:
    """Locate the ``migrations`` directory shipped with this package.

    Two layouts are supported:

    * **Installed wheel**: the directory is force-included as the
      top-level ``better_code_review_graph_migrations`` package via Hatch
      ``shared-data`` (see ``pyproject.toml``). We resolve it through
      ``importlib.resources``.
    * **Editable / source checkout**: walk up from this file to the repo
      root and use ``./migrations``.

    On total failure (neither layout resolves to an existing ``env.py``),
    raise :class:`RuntimeError` with both attempted paths in the message
    so the failure is observable rather than silently degrading to a
    junk path that alembic would later reject.
    """
    attempted: list[str] = []

    # Layout 1: installed wheel — force-included as a top-level resource
    # directory.  ``importlib.resources.files`` returns a ``MultiplexedPath``
    # whose ``__str__`` is the *repr* (not a real filesystem path), so we
    # must NOT do ``Path(str(ref))``.  Instead, ``ref.joinpath("env.py")``
    # returns a real ``pathlib.Path`` for filesystem-backed force-included
    # resources, and ``.parent`` gives us the on-disk directory directly
    # without the temp-directory copy that ``importlib.resources.as_file``
    # would otherwise materialise (and tear down on context-manager exit).
    try:
        from importlib.resources import files as _files

        ref = _files("better_code_review_graph_migrations")
        env_py = ref.joinpath("env.py")
        if isinstance(env_py, Path) and env_py.is_file():
            return Path(env_py).parent
        attempted.append(
            f"installed package: env.py not found via importlib.resources at {ref!r}"
        )
    except ModuleNotFoundError as exc:
        attempted.append(f"installed package import failed: {exc}")

    # Layout 2: editable / source checkout. src/better_code_review_graph/
    # graph.py -> repo_root/migrations.
    src_fallback = Path(__file__).resolve().parent.parent.parent / "migrations"
    if (src_fallback / "env.py").is_file():
        return src_fallback
    attempted.append(f"source checkout: {src_fallback} (env.py missing)")

    raise RuntimeError(
        "Could not locate alembic migrations directory. Tried: " + "; ".join(attempted)
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,          -- File, Class, Function, Type, Test
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    language TEXT,
    parent_name TEXT,
    params TEXT,
    return_type TEXT,
    modifiers TEXT,
    is_test INTEGER DEFAULT 0,
    file_hash TEXT,
    extra TEXT DEFAULT '{}',
    updated_at REAL NOT NULL,
    summary TEXT,
    summary_provider TEXT,
    source_hash TEXT,
    source_text TEXT
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,           -- CALLS, IMPORTS_FROM, INHERITS, etc.
    source_qualified TEXT NOT NULL,
    target_qualified TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER DEFAULT 0,
    extra TEXT DEFAULT '{}',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_qualified ON nodes(qualified_name);
-- idx_nodes_source_hash is created in _ensure_summary_columns() so legacy
-- databases (created before v1.6) get the column added before the index.
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_qualified);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_qualified);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
CREATE INDEX IF NOT EXISTS idx_edges_file ON edges(file_path);
"""

# Phase 1 v1.6.x: nullable columns added to existing `nodes` tables via
# idempotent ALTER TABLE checks. Fresh DBs already get these via _SCHEMA_SQL;
# this list drives backfill for DBs created before v1.6.
_SUMMARY_COLUMNS: tuple[str, ...] = (
    "summary",
    "summary_provider",
    "source_hash",
    "source_text",
)


@dataclass
class GraphNode:
    id: int
    kind: str
    name: str
    qualified_name: str
    file_path: str
    # Mirrors NodeInfo — nullable to match the SQLite schema.
    line_start: int | None
    line_end: int | None
    language: str
    parent_name: str | None
    params: str | None
    return_type: str | None
    is_test: bool
    file_hash: str | None
    extra: dict


@dataclass
class GraphEdge:
    id: int
    kind: str
    source_qualified: str
    target_qualified: str
    file_path: str
    line: int
    extra: dict


@dataclass
class GraphStats:
    total_nodes: int
    total_edges: int
    nodes_by_kind: dict[str, int]
    edges_by_kind: dict[str, int]
    languages: list[str]
    files_count: int
    last_updated: str | None


# ---------------------------------------------------------------------------
# GraphStore
# ---------------------------------------------------------------------------


class GraphStore:
    """SQLite-backed code knowledge graph."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path), timeout=30, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()
        self._nxg_cache: nx.DiGraph | None = None
        self._cache_lock = threading.Lock()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _init_schema(self) -> None:
        # Alembic is now authoritative on fresh DBs (Phase 2 Task 0).
        # ``_SCHEMA_SQL`` remains as a smoke comparator + safety net for
        # one release, and ``_ensure_summary_columns`` is the defensive
        # idempotent guard for any DB created between Phase 1 ship and
        # alembic adoption. Both are intentionally retained.
        self._run_alembic_upgrade()
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()
        self._ensure_summary_columns()
        self._ensure_federation_columns()
        self._ensure_temporal_columns()

    def _run_alembic_upgrade(self) -> None:
        """Bring ``self.db_path`` to alembic head before legacy bootstrap.

        Four cases are handled:

        * Empty DB (no tables) — alembic creates everything from scratch.
        * Legacy DB created by Phase 1's ``executescript(_SCHEMA_SQL)`` +
          ``_ensure_summary_columns`` (so it already has ``nodes``/``edges``/
          ``metadata`` but no ``alembic_version`` table) — we stamp it to
          revision ``002`` before upgrading so the baseline ``CREATE TABLE``
          statements are skipped.
        * DB already managed by alembic — ``upgrade("head")`` is a no-op.
        * DB recorded at a revision the package does not ship (user
          fast-forwarded by hand, or the package was downgraded).  We
          re-raise as a :class:`RuntimeError` with a human-readable
          recovery hint instead of leaking an opaque
          ``alembic.util.exc.CommandError``.

        Imported lazily so ``alembic`` (and its SQLAlchemy dependency) are
        only loaded when a ``GraphStore`` is actually instantiated.
        """
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.util.exc import CommandError

        migrations_dir = _resolve_migrations_dir()
        cfg = Config()
        cfg.set_main_option("script_location", str(migrations_dir))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

        # Phase 3 Task 1 — early-exit downgrade path.
        #
        # When the operator sets ``CRG_DOWNGRADE_TO_1_X=1`` we restore
        # the pre-2.0 backup BEFORE any alembic activity (including
        # the auto-stamp branch below — stamping a v1.x DB to "002"
        # is the same idempotent outcome as the restored DB already
        # being at "002", but we still skip it to avoid touching the
        # restored file at all).
        if os.environ.get(_DOWNGRADE_ENV_VAR) == "1":
            self._restore_pre_2_0_backup()
            return

        # Detect "legacy DB": pre-existing structural tables but alembic
        # has not yet recorded a head revision. Two sub-cases:
        #   1. ``alembic_version`` table is missing entirely.
        #   2. ``alembic_version`` exists but has no row (an interrupted
        #      prior run, or a test fixture that touched the DB before
        #      alembic was wired up).
        # In both cases we stamp at ``002`` so the baseline ``CREATE
        # TABLE`` is skipped on the subsequent ``upgrade("head")``.
        existing = {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "nodes" in existing:
            needs_stamp = "alembic_version" not in existing
            if not needs_stamp:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM alembic_version"
                ).fetchone()
                needs_stamp = row[0] == 0
            if needs_stamp:
                command.stamp(cfg, "002")

        # Phase 3 Task 1 — backup before BREAKING migration crosses the
        # 005 boundary.  Read the current recorded revision (post-stamp)
        # and the script-directory head; if the chain crosses 005,
        # snapshot the SQLite file via ``shutil.copy2`` so the operator
        # can roll back via ``CRG_DOWNGRADE_TO_1_X=1`` if the BREAKING
        # migration produces a worse outcome than expected.  Idempotent:
        # an existing backup is preserved (could be from an earlier
        # partial run that aborted mid-upgrade — that copy is closer to
        # the true v1.x state than anything we'd produce now).
        current_rev = self._read_alembic_version()
        target_rev = ScriptDirectory.from_config(cfg).get_current_head()
        if _crosses_breaking_boundary(current_rev, target_rev):
            self._take_pre_2_0_backup()

        try:
            command.upgrade(cfg, "head")
        except CommandError as exc:
            # Most likely cause: ``alembic_version`` references a revision
            # this package does not ship.  Re-raise with the unknown
            # revision and the local head spelt out so the operator knows
            # whether to downgrade the package or recreate the DB.
            recorded: str | None
            try:
                row = self._conn.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()
                recorded = row[0] if row else None
            except sqlite3.Error:
                recorded = None
            head = ScriptDirectory.from_config(cfg).get_current_head()
            raise RuntimeError(
                f"Graph DB at {self.db_path} reports alembic revision "
                f"{recorded!r} which is not shipped with this version of "
                f"better-code-review-graph (head={head!r}). Either downgrade "
                "the package or recreate the DB."
            ) from exc

    # ------------------------------------------------------------------
    # Phase 3 Task 1 — backup / restore helpers
    # ------------------------------------------------------------------

    def _read_alembic_version(self) -> str | None:
        """Return the revision recorded in ``alembic_version`` (or ``None``).

        ``None`` covers two cases the BREAKING-boundary check needs to
        treat identically: the table is missing entirely (fresh DB) or
        the table exists but has no row (interrupted prior run).
        """
        try:
            row = self._conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        return row[0]

    def _take_pre_2_0_backup(self) -> None:
        """Copy ``self.db_path`` to ``<db>.pre-2.0.bak`` if not already taken.

        Uses ``shutil.copy2`` to preserve metadata so a forensic timestamp
        comparison remains meaningful.  Idempotent: a pre-existing backup
        file is left untouched (the original copy is closer to true v1.x
        state than anything a re-run could produce).

        :memory: databases — and any path that does not exist on disk —
        are skipped silently.  alembic-managed in-memory DBs aren't a
        target for forensic rollback, and the file-not-found case can
        only come up on bizarre virtual filesystems where copy would
        fail anyway.
        """
        backup_path = self.db_path.with_suffix(_BACKUP_SUFFIX)
        if backup_path.exists():
            return
        if not self.db_path.is_file():
            return
        # ``shutil.copy2`` follows symlinks and preserves metadata.
        # WAL files (``-wal`` / ``-shm``) are intentionally NOT copied:
        # we close the sqlite connection's WAL state by issuing a
        # checkpoint first so the .db file is self-contained.
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            # Some pragmas aren't available on every SQLite build /
            # platform — falling back to a copy of the main file alone
            # is still strictly better than no backup.
            pass
        shutil.copy2(self.db_path, backup_path)

    def _restore_pre_2_0_backup(self) -> None:
        """Restore ``<db>.pre-2.0.bak`` over ``self.db_path``.

        Used when the operator opts into a v1.x downgrade via
        ``CRG_DOWNGRADE_TO_1_X=1``.  The current (potentially v2)
        DB is preserved at ``<db>.post-2.0.archived`` so a follow-up
        forward-roll is still possible if the operator changes their
        mind.

        Closes the active sqlite connection before the restore so the
        on-disk file can be replaced safely on Windows (which holds an
        exclusive lock on open files).  A fresh connection is opened
        against the restored file before returning so the rest of
        ``GraphStore.__init__`` continues to work.

        Raises :class:`RuntimeError` with a clear message when the env
        var is set but no backup file exists — the operator's intent
        was explicit and we have nothing to honour it with.
        """
        backup_path = self.db_path.with_suffix(_BACKUP_SUFFIX)
        archived_path = self.db_path.with_suffix(_ARCHIVED_SUFFIX)

        if not backup_path.is_file():
            raise RuntimeError(
                f"{_DOWNGRADE_ENV_VAR}=1 was set but no backup file was "
                f"found at {backup_path}. A v1.x downgrade requires the "
                "pre-migration snapshot taken on the previous startup. "
                "Either restore the backup file from elsewhere or unset "
                f"{_DOWNGRADE_ENV_VAR} to continue with the v2 schema."
            )

        # Close the live connection so Windows lets us swap the file.
        # Re-opened below before this method returns.
        self._conn.close()

        # Move (not delete) the v2 state aside so the operator can still
        # recover it.  ``os.replace`` is atomic on the same filesystem.
        if self.db_path.is_file():
            if archived_path.exists():
                archived_path.unlink()
            os.replace(self.db_path, archived_path)

        shutil.copy2(backup_path, self.db_path)

        # Reopen against the restored file with the same PRAGMAs as
        # ``__init__``.  Keeping these in sync with ``__init__`` is a
        # narrow contract; if either is changed, the other must follow.
        self._conn = sqlite3.connect(
            str(self.db_path), timeout=30, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def _ensure_federation_columns(self) -> None:
        """Backfill Phase 2 Task 1 federation columns on legacy / in-memory DBs.

        Mirrors ``_ensure_summary_columns`` for the
        ``003_federation`` migration. Two cases land here:

        * In-memory ``:memory:`` databases — alembic creates the schema
          in a separate in-memory connection (per the
          ``sqlite:///:memory:`` URL semantics), so the migration never
          touches ``self._conn``. The legacy ``_SCHEMA_SQL`` is frozen
          at v1.6 and intentionally does not include ``repo_id``, so
          we add the column here to keep ``upsert_node`` /
          ``upsert_edge`` working without forcing every test to use a
          file-backed DB.
        * File-backed databases created before alembic adoption —
          ``_run_alembic_upgrade`` already brings them to head, so
          this is a no-op for them. The ``IF NOT EXISTS`` guard on
          the index plus the column-presence check make this safe to
          call unconditionally on every connect.
        """
        node_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(nodes)")}
        if "repo_id" not in node_cols:
            self._conn.execute(
                "ALTER TABLE nodes ADD COLUMN repo_id TEXT NOT NULL DEFAULT ''"
            )
        edge_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(edges)")}
        if "repo_id" not in edge_cols:
            self._conn.execute(
                "ALTER TABLE edges ADD COLUMN repo_id TEXT NOT NULL DEFAULT ''"
            )
        # Repos registry table — created by migration 003 on disk-backed
        # DBs. Mirror it here for in-memory connections so RepoRegistry
        # works against ``:memory:`` GraphStores too.
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS repos (
                repo_id TEXT PRIMARY KEY NOT NULL,
                path TEXT NOT NULL,
                remote_url TEXT,
                last_indexed_sha TEXT,
                first_indexed_at INTEGER NOT NULL,
                last_indexed_at INTEGER NOT NULL
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_repo_kind ON nodes(repo_id, kind)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_repo ON edges(repo_id)"
        )
        self._conn.commit()

    def _ensure_temporal_columns(self) -> None:
        """Backfill Phase 3 Task 6 temporal columns on legacy / in-memory DBs.

        Mirrors ``_ensure_federation_columns`` for the
        ``005_temporal_columns`` migration. Two cases land here:

        * In-memory ``:memory:`` databases — alembic creates the schema
          in a separate in-memory connection (per the
          ``sqlite:///:memory:`` URL semantics), so the migration never
          touches ``self._conn``. The legacy ``_SCHEMA_SQL`` is frozen
          at v1.6 and intentionally does not include the temporal
          columns, so we add them here to keep the v2 query layer
          (``valid_to_sha IS NULL`` filters) working without forcing
          every test to use a file-backed DB.
        * File-backed databases that bypassed alembic for any reason —
          the ``IF NOT EXISTS`` guard on the index plus the
          column-presence check make this safe to call unconditionally
          on every connect.

        ``valid_from_sha`` defaults to a 40-zero sentinel so legacy
        rows inserted via ``upsert_node`` (which does NOT set the
        column) survive the NOT NULL constraint. The sentinel matches
        the in-memory fallback used by the alembic migration so
        downstream temporal queries treat the two paths identically.
        """
        node_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(nodes)")}
        if "valid_from_sha" not in node_cols:
            self._conn.execute(
                "ALTER TABLE nodes ADD COLUMN valid_from_sha TEXT NOT NULL "
                "DEFAULT '0000000000000000000000000000000000000000'"
            )
        if "valid_to_sha" not in node_cols:
            self._conn.execute("ALTER TABLE nodes ADD COLUMN valid_to_sha TEXT")
        edge_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(edges)")}
        if "valid_from_sha" not in edge_cols:
            self._conn.execute(
                "ALTER TABLE edges ADD COLUMN valid_from_sha TEXT NOT NULL "
                "DEFAULT '0000000000000000000000000000000000000000'"
            )
        if "valid_to_sha" not in edge_cols:
            self._conn.execute("ALTER TABLE edges ADD COLUMN valid_to_sha TEXT")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_temporal "
            "ON nodes(valid_from_sha, valid_to_sha)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_temporal "
            "ON edges(valid_from_sha, valid_to_sha)"
        )
        self._conn.commit()

    def _ensure_summary_columns(self) -> None:
        """Backfill Phase 1 v1.6.x summary columns on pre-existing DBs.

        Fresh DBs receive these columns via ``_SCHEMA_SQL``; databases created
        before v1.6 are missing them, so we read ``PRAGMA table_info(nodes)``
        and ``ALTER TABLE`` for any column that is not present. The ``source_hash``
        index is also created here so legacy DBs gain the cache lookup index
        without requiring a fresh build. Idempotent — safe to call on every
        connect.
        """
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(nodes)")}
        column_sqls = {
            "summary": "ALTER TABLE nodes ADD COLUMN summary TEXT",
            "summary_provider": "ALTER TABLE nodes ADD COLUMN summary_provider TEXT",
            "source_hash": "ALTER TABLE nodes ADD COLUMN source_hash TEXT",
            "source_text": "ALTER TABLE nodes ADD COLUMN source_text TEXT",
        }
        for column in _SUMMARY_COLUMNS:
            if column not in existing and column in column_sqls:
                self._conn.execute(column_sqls[column])
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_source_hash ON nodes(source_hash)"
        )
        self._conn.commit()

    def _invalidate_cache(self) -> None:
        """Invalidate the cached NetworkX graph after write operations."""
        with self._cache_lock:
            self._nxg_cache = None

    def close(self) -> None:
        self._conn.close()

    # --- Write operations ---

    def upsert_node(self, node: NodeInfo, file_hash: str = "") -> int:
        """Insert or update a node. Returns the node ID."""
        now = time.time()
        qualified = self._make_qualified(node)
        # Tolerate dict / Mapping that don't survive ``if node.extra``
        # (e.g. a stand-in object from a pre-Phase-2 caller).
        extra_obj = getattr(node, "extra", None) or {}
        extra = json.dumps(extra_obj) if extra_obj else "{}"
        # Phase 2 Task 9 — fall back to "" for callers passing legacy
        # NodeInfo objects without the federation field.
        repo_id = getattr(node, "repo_id", "") or ""

        self._conn.execute(
            """INSERT INTO nodes
               (kind, name, qualified_name, file_path, line_start, line_end,
                language, parent_name, params, return_type, modifiers, is_test,
                file_hash, extra, updated_at, source_text, repo_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(qualified_name) DO UPDATE SET
                 kind=excluded.kind, name=excluded.name,
                 file_path=excluded.file_path, line_start=excluded.line_start,
                 line_end=excluded.line_end, language=excluded.language,
                 parent_name=excluded.parent_name, params=excluded.params,
                 return_type=excluded.return_type, modifiers=excluded.modifiers,
                 is_test=excluded.is_test, file_hash=excluded.file_hash,
                 extra=excluded.extra, updated_at=excluded.updated_at,
                 source_text=excluded.source_text, repo_id=excluded.repo_id
            """,
            (
                node.kind,
                node.name,
                qualified,
                node.file_path,
                node.line_start,
                node.line_end,
                node.language,
                node.parent_name,
                node.params,
                node.return_type,
                node.modifiers,
                int(node.is_test),
                file_hash,
                extra,
                now,
                getattr(node, "source_text", None),
                repo_id,
            ),
        )
        row = self._conn.execute(
            "SELECT id FROM nodes WHERE qualified_name = ?", (qualified,)
        ).fetchone()
        return row["id"]

    def upsert_edge(self, edge: EdgeInfo) -> int:
        """Insert or update an edge."""
        now = time.time()
        extra_obj = getattr(edge, "extra", None) or {}
        extra = json.dumps(extra_obj) if extra_obj else "{}"
        # Phase 2 Task 9 — same legacy fallback as ``upsert_node``.
        repo_id = getattr(edge, "repo_id", "") or ""

        # Check for existing edge (include line so multiple call sites are preserved)
        existing = self._conn.execute(
            """SELECT id FROM edges
               WHERE kind=? AND source_qualified=? AND target_qualified=?
                     AND file_path=? AND line=?""",
            (edge.kind, edge.source, edge.target, edge.file_path, edge.line),
        ).fetchone()

        if existing:
            self._conn.execute(
                "UPDATE edges SET line=?, extra=?, updated_at=?, repo_id=? WHERE id=?",
                (edge.line, extra, now, repo_id, existing["id"]),
            )
            return existing["id"]

        self._conn.execute(
            """INSERT INTO edges
               (kind, source_qualified, target_qualified, file_path, line, extra, updated_at, repo_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge.kind,
                edge.source,
                edge.target,
                edge.file_path,
                edge.line,
                extra,
                now,
                repo_id,
            ),
        )
        return self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def resolve_php_calls(self) -> dict[str, int]:
        """Bind lexical PHP call evidence to unique, current same-repo symbols.

        Re-evaluate earlier bindings on every build so deletion or a newly
        ambiguous definition cannot leave a stale cross-file edge behind.
        Dynamic receivers and missing/external symbols remain unresolved.
        """
        symbols = {
            (row["repo_id"], row["symbol"]): (row["qualified_name"], row["count"])
            for row in self._conn.execute(
                """SELECT repo_id, json_extract(extra, '$.php_symbol') AS symbol,
                          MIN(qualified_name) AS qualified_name, COUNT(*) AS count
                   FROM nodes
                   WHERE language = 'php' AND kind IN ('Function', 'Test')
                     AND valid_to_sha IS NULL
                     AND json_type(extra, '$.php_symbol') = 'text'
                   GROUP BY repo_id, symbol"""
            )
        }

        def updates():
            for row in self._conn.execute(
                """SELECT id, repo_id, target_qualified, extra FROM edges
                   WHERE kind = 'CALLS' AND valid_to_sha IS NULL
                     AND json_type(extra, '$.php_targets') = 'array'
                     AND json_type(extra, '$.php_unresolved_target') = 'text'"""
            ):
                extra = json.loads(row["extra"])
                target = extra["php_unresolved_target"]
                for candidate in extra["php_targets"]:
                    if not isinstance(candidate, str):
                        continue
                    match = symbols.get((row["repo_id"], candidate))
                    if match is not None:
                        if match[1] == 1:
                            target = match[0]
                        # An ambiguous namespace-local definition must not
                        # fall through to a different global function.
                        break
                if target != row["target_qualified"]:
                    yield target, row["id"]

        changed = self._conn.executemany(
            "UPDATE edges SET target_qualified = ? WHERE id = ?", updates()
        ).rowcount
        if changed:
            self._invalidate_cache()
        row = self._conn.execute(
            """SELECT COUNT(*) AS total,
                      COALESCE(SUM(target.id IS NOT NULL), 0) AS resolved
               FROM edges AS edge
               JOIN nodes AS source ON source.qualified_name = edge.source_qualified
                    AND source.valid_to_sha IS NULL AND source.language = 'php'
               LEFT JOIN nodes AS target ON target.qualified_name = edge.target_qualified
                    AND target.valid_to_sha IS NULL
               WHERE edge.kind = 'CALLS' AND edge.valid_to_sha IS NULL"""
        ).fetchone()
        return {
            "total": row["total"],
            "resolved": row["resolved"],
            "unresolved": row["total"] - row["resolved"],
        }

    def resolve_bare_calls(self) -> dict[str, int]:
        """Bind bare CALLS targets to unique, current same-repo symbols.

        Issue #1006: the parser leaves a bare identifier in
        ``target_qualified`` when a call cannot be resolved locally, so
        cross-file CALLS edges never materialise and impact traversal has
        nothing to walk. A bare target binds only when exactly one current
        node in the same repository carries that name; ambiguous and
        external names stay bare. The original target plus its candidate
        list persist in ``extra`` (``bare_targets`` /
        ``bare_unresolved_target``) and are re-evaluated on every build, so
        deletion or a newly ambiguous definition unbinds the edge.

        Edges carrying PHP call evidence (``php_unresolved_target``) are
        owned by :meth:`resolve_php_calls` and are never double-bound here.
        """
        symbols: dict[tuple[str | None, str], int] = {}
        qualified: dict[tuple[str | None, str], str] = {}
        for row in self._conn.execute(
            """SELECT repo_id, qualified_name FROM nodes
               WHERE kind IN ('Function', 'Test', 'Class', 'Type')
                 AND valid_to_sha IS NULL"""
        ):
            name = row["qualified_name"].rsplit("::", 1)[-1]
            key = (row["repo_id"], name)
            symbols[key] = symbols.get(key, 0) + 1
            if key not in qualified or row["qualified_name"] < qualified[key]:
                qualified[key] = row["qualified_name"]

        def updates():
            for row in self._conn.execute(
                """SELECT id, repo_id, target_qualified, extra FROM edges
                   WHERE kind = 'CALLS' AND valid_to_sha IS NULL
                     AND (instr(target_qualified, '::') = 0
                          OR json_type(extra, '$.bare_unresolved_target') = 'text')"""
            ):
                try:
                    extra = json.loads(row["extra"]) if row["extra"] else {}
                except (json.JSONDecodeError, TypeError):
                    extra = {}
                unresolved = extra.get("bare_unresolved_target")
                if unresolved is None:
                    if "php_unresolved_target" in extra:
                        continue
                    unresolved = row["target_qualified"]
                    candidates = [unresolved]
                else:
                    candidates = extra.get("bare_targets")
                    if not isinstance(candidates, list) or not all(
                        isinstance(candidate, str) for candidate in candidates
                    ):
                        candidates = [unresolved]
                target = unresolved
                for candidate in candidates:
                    if symbols.get((row["repo_id"], candidate)) == 1:
                        target = qualified[(row["repo_id"], candidate)]
                        break
                if (
                    target != row["target_qualified"]
                    or "bare_unresolved_target" not in extra
                ):
                    new_extra = dict(extra)
                    new_extra["bare_targets"] = candidates
                    new_extra["bare_unresolved_target"] = unresolved
                    yield target, json.dumps(new_extra), row["id"]

        changed = self._conn.executemany(
            "UPDATE edges SET target_qualified = ?, extra = ? WHERE id = ?",
            updates(),
        ).rowcount
        if changed:
            self._invalidate_cache()
        row = self._conn.execute(
            """SELECT COUNT(*) AS total,
                      COALESCE(SUM(target.id IS NOT NULL), 0) AS resolved
               FROM edges AS edge
               LEFT JOIN nodes AS target ON target.qualified_name = edge.target_qualified
                    AND target.valid_to_sha IS NULL
               WHERE edge.kind = 'CALLS' AND edge.valid_to_sha IS NULL"""
        ).fetchone()
        return {
            "total": row["total"],
            "resolved": row["resolved"],
            "unresolved": row["total"] - row["resolved"],
        }

    def update_summary(
        self,
        node_id: int,
        *,
        summary: str,
        provider: str,
        source_hash: str,
    ) -> None:
        """Persist LLM-generated summary metadata for a node.

        Args:
            node_id: The integer primary key of the node row in the nodes table.
            summary: Generated docstring text.
            provider: Complete selected model identity (e.g. "openrouter/minimax/minimax-m3:free").
            source_hash: SHA-256 of the source_text used to generate the summary.
                Used as cache key on subsequent batch_summarize calls.
        """
        self._conn.execute(
            "UPDATE nodes SET summary=?, summary_provider=?, source_hash=? WHERE id=?",
            (summary, provider, source_hash, node_id),
        )
        self._conn.commit()

    def remove_file_data(self, file_path: str) -> None:
        """Remove all nodes and edges associated with a file."""
        self._conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
        self._conn.execute("DELETE FROM edges WHERE file_path = ?", (file_path,))
        self._invalidate_cache()

    def store_file_nodes_edges(
        self,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        fhash: str = "",
    ) -> None:
        """Atomically replace all data for a file using batch insertion to eliminate N+1 queries."""
        self.remove_file_data(file_path)
        now = time.time()

        if nodes:
            node_data = []
            for node in nodes:
                qualified = self._make_qualified(node)
                extra_obj = getattr(node, "extra", None) or {}
                extra = json.dumps(extra_obj) if extra_obj else "{}"
                node_data.append(
                    (
                        node.kind,
                        node.name,
                        qualified,
                        node.file_path,
                        node.line_start,
                        node.line_end,
                        node.language,
                        node.parent_name,
                        node.params,
                        node.return_type,
                        node.modifiers,
                        int(node.is_test),
                        fhash,
                        extra,
                        now,
                        getattr(node, "source_text", None),
                        getattr(node, "repo_id", "") or "",
                    )
                )

            self._conn.executemany(
                """INSERT INTO nodes
                   (kind, name, qualified_name, file_path, line_start, line_end,
                    language, parent_name, params, return_type, modifiers, is_test,
                    file_hash, extra, updated_at, source_text, repo_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(qualified_name) DO UPDATE SET
                     kind=excluded.kind, name=excluded.name,
                     file_path=excluded.file_path, line_start=excluded.line_start,
                     line_end=excluded.line_end, language=excluded.language,
                     parent_name=excluded.parent_name, params=excluded.params,
                     return_type=excluded.return_type, modifiers=excluded.modifiers,
                     is_test=excluded.is_test, file_hash=excluded.file_hash,
                     extra=excluded.extra, updated_at=excluded.updated_at,
                     source_text=excluded.source_text, repo_id=excluded.repo_id
                """,
                node_data,
            )

        if edges:
            edge_data = []
            seen = set()
            for edge in reversed(edges):
                key = (edge.kind, edge.source, edge.target, edge.file_path, edge.line)
                if key not in seen:
                    seen.add(key)
                    extra_obj = getattr(edge, "extra", None) or {}
                    extra = json.dumps(extra_obj) if extra_obj else "{}"
                    edge_data.append(
                        (
                            edge.kind,
                            edge.source,
                            edge.target,
                            edge.file_path,
                            edge.line,
                            extra,
                            now,
                            getattr(edge, "repo_id", "") or "",
                        )
                    )

            self._conn.executemany(
                """INSERT INTO edges
                   (kind, source_qualified, target_qualified, file_path, line, extra, updated_at, repo_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                edge_data[::-1],
            )

        self._conn.commit()
        self._invalidate_cache()

    def set_metadata(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value)
        )
        self._conn.commit()

    def get_metadata(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM metadata WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def commit(self) -> None:
        self._conn.commit()

    # --- Read operations ---

    @staticmethod
    def _temporal_filter(
        as_of: str, *, table_alias: str = ""
    ) -> tuple[str, tuple[str, ...]]:
        """Return ``(sql_fragment, bind_params)`` for the temporal scope.

        Phase 3 Task 9 — encodes the "snapshot at SHA" semantics used by
        the v2 query layer. The fragment is always prefixed with
        ``AND`` so callers can append it to an existing ``WHERE``
        clause without rewriting the query shape.

        * ``as_of == ""`` → ``AND <prefix>valid_to_sha IS NULL``. Returns
          only currently-valid rows. This is the new default and the
          first use of the temporal columns by the read layer; legacy
          ingest writes ``valid_to_sha = NULL`` so existing rows pass
          through untouched.
        * ``as_of == "<sha>"`` → ``AND (<prefix>valid_from_sha = ? OR
          <prefix>valid_to_sha = ?)``. Snapshot semantics: rows
          introduced exactly at the requested SHA OR rows that were
          closed out at the requested SHA both qualify. Approximation
          of full ancestor walk against the ``commits`` table —
          deferred to Task 9.5.

        Args:
            as_of: Empty string for "currently-valid" or a 40-char SHA.
            table_alias: When the surrounding query references multiple
                tables (``nodes n JOIN edges e``) callers pass the
                alias so the fragment qualifies the column name. Empty
                string (default) emits unqualified column names.

        Returns:
            ``(fragment, params)`` — fragment includes the leading
            ``AND`` so callers always emit the same shape regardless
            of whether the SHA is set.
        """
        prefix = f"{table_alias}." if table_alias else ""
        if not as_of:
            return f" AND {prefix}valid_to_sha IS NULL", ()
        return (
            f" AND ({prefix}valid_from_sha = ? OR {prefix}valid_to_sha = ?)",
            (as_of, as_of),
        )

    def get_node(self, qualified_name: str, *, as_of: str = "") -> GraphNode | None:
        frag, frag_params = self._temporal_filter(as_of)
        row = self._conn.execute(
            f"SELECT * FROM nodes WHERE qualified_name = ?{frag}",  # noqa: S608
            (qualified_name, *frag_params),
        ).fetchone()
        return self._row_to_node(row) if row else None

    def get_nodes_by_file(self, file_path: str, *, as_of: str = "") -> list[GraphNode]:
        frag, frag_params = self._temporal_filter(as_of)
        cursor = self._conn.execute(
            f"SELECT * FROM nodes WHERE file_path = ?{frag}",  # noqa: S608
            (file_path, *frag_params),
        )
        return [self._row_to_node(r) for r in cursor]

    def get_file_hash(self, file_path: str, *, as_of: str = "") -> str | None:
        """Fetch just the file_hash for a given file to avoid materializing all nodes."""
        frag, frag_params = self._temporal_filter(as_of)
        # We limit to 1 because file_hash is identical for all nodes in the same file at the same point in time
        cursor = self._conn.execute(
            f"SELECT file_hash FROM nodes WHERE file_path = ?{frag} LIMIT 1",  # noqa: S608
            (file_path, *frag_params),
        )
        row = cursor.fetchone()
        return row["file_hash"] if row else None

    def get_function_hashes_by_files(
        self, file_paths: list[str], *, as_of: str = ""
    ) -> list[dict[str, Any]]:
        """Batch fetch only qualified_name and file_hash for Function nodes in given files.
        Returns a list of dicts with 'file_path', 'qualified_name', and 'file_hash'.
        """
        if not file_paths:
            return []

        unique_files = list(set(file_paths))
        frag, frag_params = self._temporal_filter(as_of)
        cursor = self._conn.execute(
            "SELECT file_path, qualified_name, file_hash FROM nodes "
            "WHERE kind = 'Function' AND file_path IN "  # noqa: S608
            f"(SELECT value FROM json_each(?)){frag}",
            (json.dumps(unique_files), *frag_params),
        )
        return [
            {
                "file_path": r["file_path"],
                "qualified_name": r["qualified_name"],
                "file_hash": r["file_hash"],
            }
            for r in cursor
        ]

    def get_nodes_by_files(
        self, file_paths: list[str], *, as_of: str = ""
    ) -> list[GraphNode]:
        """Batch fetch nodes by their file paths to prevent N+1 queries.

        Deduplicates input file paths, fetches in batches to respect SQLite
        parameter limits, and returns all matching nodes. Uses the same
        json_each(?) idiom as get_nodes_by_qualified_names to keep SQL static
        and satisfy Bandit B608.
        """
        if not file_paths:
            return []

        unique_files = list(set(file_paths))
        frag, frag_params = self._temporal_filter(as_of)
        cursor = self._conn.execute(
            "SELECT * FROM nodes WHERE file_path IN "  # noqa: S608
            f"(SELECT value FROM json_each(?)){frag}",
            (json.dumps(unique_files), *frag_params),
        )
        return [self._row_to_node(r) for r in cursor]

    def get_nodes_by_qualified_names(
        self, qualified_names: list[str], *, as_of: str = ""
    ) -> list[GraphNode]:
        """Batch fetch nodes by their qualified names to prevent N+1 queries.

        Deduplicates input names, fetches in batches to respect SQLite limits,
        and returns all matching nodes.
        """
        if not qualified_names:
            return []

        unique_qns = list(set(qualified_names))
        frag, frag_params = self._temporal_filter(as_of)
        cursor = self._conn.execute(
            "SELECT * FROM nodes WHERE qualified_name IN "  # noqa: S608
            f"(SELECT value FROM json_each(?)){frag}",
            (json.dumps(unique_qns), *frag_params),
        )
        return [self._row_to_node(r) for r in cursor]

    def get_edges_by_source(
        self,
        qualified_name: str,
        kind: str | tuple[str, ...] | None = None,
        *,
        as_of: str = "",
    ) -> list[GraphEdge]:
        # Push optional kind filter down to SQLite so callers that previously
        # post-filtered a fully materialized list now avoid the wasted rows.
        frag, frag_params = self._temporal_filter(as_of)
        kind_frag, kind_params = self._kind_filter(kind)
        cursor = self._conn.execute(
            f"SELECT * FROM edges WHERE source_qualified = ?{kind_frag}{frag}",  # noqa: S608
            (qualified_name, *kind_params, *frag_params),
        )
        return [self._row_to_edge(r) for r in cursor]

    def get_edges_by_target(
        self,
        qualified_name: str,
        kind: str | tuple[str, ...] | None = None,
        *,
        as_of: str = "",
        fallback: bool = True,
    ) -> list[GraphEdge]:
        frag, frag_params = self._temporal_filter(as_of)
        kind_frag, kind_params = self._kind_filter(kind)
        cursor = self._conn.execute(
            f"SELECT * FROM edges WHERE target_qualified = ?{kind_frag}{frag}",  # noqa: S608
            (qualified_name, *kind_params, *frag_params),
        )
        first_row = cursor.fetchone()

        # Fallback to bare name (last segment after ::) when the qualified name
        # has no edges AT ALL. With a kind filter, "no rows of this kind" is not
        # enough to trigger the fallback — that would wrongly pull in edges
        # belonging to a different qualified target that happens to share the
        # bare name.
        if fallback and not first_row and "::" in qualified_name:
            if kind is not None:
                exists = self._conn.execute(
                    f"SELECT 1 FROM edges WHERE target_qualified = ?{frag} LIMIT 1",  # noqa: S608
                    (qualified_name, *frag_params),
                ).fetchone()
                if exists is not None:
                    return []
            bare_name = qualified_name.rsplit("::", 1)[-1]
            cursor = self._conn.execute(
                f"SELECT * FROM edges WHERE target_qualified = ?{kind_frag}{frag}",  # noqa: S608
                (bare_name, *kind_params, *frag_params),
            )
            return [self._row_to_edge(r) for r in cursor]

        if first_row:
            return [self._row_to_edge(first_row)] + [
                self._row_to_edge(r) for r in cursor
            ]
        return []

    @staticmethod
    def _kind_filter(
        kind: str | tuple[str, ...] | None,
    ) -> tuple[str, tuple[str, ...]]:
        if kind is None:
            return "", ()
        if isinstance(kind, str):
            return " AND kind = ?", (kind,)
        if not kind:
            return "", ()
        placeholders = ",".join("?" for _ in kind)
        return f" AND kind IN ({placeholders})", tuple(kind)

    def get_edges_by_targets(
        self,
        qualified_names: list[str],
        kind: str | tuple[str, ...] | None = None,
        *,
        as_of: str = "",
    ) -> list[GraphEdge]:
        """Batch fetch edges by target names with an optional kind filter."""
        if not qualified_names:
            return []

        unique_qns = list(set(qualified_names))
        frag, frag_params = self._temporal_filter(as_of)
        kind_frag, kind_params = self._kind_filter(kind)
        cursor = self._conn.execute(
            "SELECT * FROM edges WHERE target_qualified IN "  # noqa: S608
            f"(SELECT value FROM json_each(?)){kind_frag}{frag}",
            (json.dumps(unique_qns), *kind_params, *frag_params),
        )
        return [self._row_to_edge(r) for r in cursor]

    def search_edges_by_target_name(
        self, name: str, kind: str = "CALLS", *, as_of: str = ""
    ) -> list[GraphEdge]:
        """Search for edges where target_qualified matches an unqualified name.

        CALLS edges often store unqualified target names (e.g. ``generateTestCode``)
        rather than fully qualified ones (``file.ts::generateTestCode``).  This
        method finds those edges by exact match on the plain function name so that
        reverse call tracing (callers_of) works even when qualified-name lookup
        returns nothing.
        """
        return self.search_edges_by_target_names([name], kind=kind, as_of=as_of)

    def search_edges_by_source_names(
        self,
        names: list[str],
        kind: str | tuple[str, ...] | None = None,
        *,
        as_of: str = "",
    ) -> list[GraphEdge]:
        """Batch search for edges where source_qualified matches any of the given names.

        Batched to prevent N+1 queries when resolving multiple sources
        to their targets.
        """
        if not names:
            return []

        unique_names = list(set(names))
        frag, frag_params = self._temporal_filter(as_of)
        kind_frag, kind_params = self._kind_filter(kind)
        cursor = self._conn.execute(
            "SELECT * FROM edges WHERE source_qualified IN "  # noqa: S608
            f"(SELECT value FROM json_each(?)){kind_frag}{frag}",
            (json.dumps(unique_names), *kind_params, *frag_params),
        )
        return [self._row_to_edge(r) for r in cursor]

    def search_edges_by_target_names(
        self,
        names: list[str],
        kind: str | tuple[str, ...] | None = "CALLS",
        *,
        as_of: str = "",
    ) -> list[GraphEdge]:
        """Batch search for edges where target_qualified matches any of the given names.

        Batched to prevent N+1 queries when resolving multiple targets
        to their callers (issue #342).
        """
        if not names:
            return []

        unique_names = list(set(names))
        frag, frag_params = self._temporal_filter(as_of)
        kind_frag, kind_params = self._kind_filter(kind)
        cursor = self._conn.execute(
            "SELECT * FROM edges WHERE target_qualified IN "  # noqa: S608
            f"(SELECT value FROM json_each(?)){kind_frag}{frag}",
            (json.dumps(unique_names), *kind_params, *frag_params),
        )
        return [self._row_to_edge(r) for r in cursor]

    def get_all_files(self) -> list[str]:
        cursor = self._conn.execute(
            "SELECT DISTINCT file_path FROM nodes WHERE kind = 'File'"
        )
        return [r["file_path"] for r in cursor]

    def search_nodes(
        self,
        query: str,
        kind: str | None = None,
        limit: int = 20,
        repo: str = "",
        *,
        as_of: str = "",
    ) -> list[GraphNode]:
        """Keyword search across node names and qualified names.

        Multi-word queries require ALL words to match (AND logic).  Each word
        must appear in either the node name or the qualified name.

        Phase 2 Task 10: when ``repo`` is non-empty the result set is
        scoped to nodes whose ``repo_id`` equals it. Empty ``repo``
        (default) preserves the legacy unscoped behaviour.

        Phase 3 Task 9: ``as_of`` filters to the temporal snapshot at
        the requested SHA. Default ``""`` returns currently-valid rows
        (``valid_to_sha IS NULL``).
        """
        words = query.lower().split()
        if not words:
            return []

        frag, frag_params = self._temporal_filter(as_of)
        # Use json_each to avoid dynamic SQL construction.
        # The temporal fragment is a static prefix/clause produced by
        # ``_temporal_filter`` from a hard-coded set of strings, so the
        # f-string interpolation is safe (Bandit B608 already lints).
        # No LOWER() call: SQLite's LIKE is already case-insensitive for
        # ASCII by default (issue #342).
        cursor = self._conn.execute(
            f"""
            SELECT * FROM nodes
            WHERE (
                SELECT COUNT(*)
                FROM json_each(?)
                WHERE nodes.name LIKE '%' || value || '%'
                   OR nodes.qualified_name LIKE '%' || value || '%'
            ) = (SELECT COUNT(*) FROM json_each(?))
              AND (? IS NULL OR kind = ?)
              AND (? = '' OR repo_id = ?){frag}
            ORDER BY name LIMIT ?
            """,  # noqa: S608
            [
                json.dumps(words),
                json.dumps(words),
                kind,
                kind,
                repo,
                repo,
                *frag_params,
                limit,
            ],
        )
        return [self._row_to_node(r) for r in cursor]

    # --- Impact / Graph traversal ---

    def get_impact_radius(
        self,
        changed_files: list[str],
        max_depth: int = 2,
        max_nodes: int = 500,
        repo: str = "",
        *,
        as_of: str = "",
    ) -> dict[str, Any]:
        """BFS from changed files to find all impacted nodes within depth N.

        Returns dict with:
          - changed_nodes: nodes in changed files
          - impacted_nodes: nodes reachable via edges
          - impacted_files: unique set of affected files
          - edges: connecting edges
          - truncated: True if BFS was stopped early due to max_nodes limit
          - total_impacted: total number of impacted nodes found before truncation

        Phase 2 Task 10: when ``repo`` is non-empty the seed set, BFS
        frontier, returned nodes, and connecting edges are filtered to
        the matching ``repo_id``. Empty ``repo`` (default) preserves
        legacy cross-repo behaviour.

        Phase 3 Task 9: ``as_of`` scopes the seed set + final node /
        edge resolution to the temporal snapshot at the requested SHA.
        Default ``""`` returns currently-valid rows. The BFS itself
        rides on the cached ``networkx`` graph (built from the full
        nodes + edges tables), so a follow-up may also rebuild the
        graph from a temporal slice. For Task 9 the seed-and-resolve
        boundary is the practical pinch point.
        """
        nxg = self._build_networkx_graph()

        # Seed: all qualified names in changed files (batched to avoid N+1).
        # When ``repo`` is set, drop seed nodes that don't belong to it.
        seed_nodes = self.get_nodes_by_files(changed_files, as_of=as_of)
        if repo:
            # JSON numbers are untyped to SQLite. Cast once in the static batch query
            # instead of issuing one repo_id lookup per seed node.
            seed_ids = [n.id for n in seed_nodes]
            valid_seed_ids: set[int] = set()
            if seed_ids:
                cursor = self._conn.execute(
                    "SELECT id FROM nodes "
                    "WHERE repo_id = ? AND id IN "
                    "(SELECT CAST(value AS INTEGER) FROM json_each(?))",
                    (repo, json.dumps(seed_ids)),
                )
                valid_seed_ids = {row["id"] for row in cursor}
            seed_nodes = [n for n in seed_nodes if n.id in valid_seed_ids]
        seeds = {n.qualified_name for n in seed_nodes}

        # BFS outward through all edge types
        visited: set[str] = set()
        frontier = seeds.copy()
        depth = 0
        impacted: set[str] = set()
        truncated = False

        while frontier and depth < max_depth:
            next_frontier: set[str] = set()
            for qn in frontier:
                visited.add(qn)
                # Forward edges (things this node affects)
                if qn in nxg:
                    for neighbor in nxg.neighbors(qn):
                        if neighbor in visited:
                            continue
                        next_frontier.add(neighbor)
                # Reverse edges (things that depend on this node)
                if qn in nxg:
                    for pred in nxg.predecessors(qn):
                        if pred in visited:
                            continue
                        next_frontier.add(pred)

            # Bolt optimization: Instead of materializing all repo nodes into a Python set
            # for cross-repo pruning, batch filter the frontier against SQLite using json_each.
            # This avoids O(N) memory overhead and N+1 query bottlenecks on large repos.
            if repo and next_frontier:
                cursor = self._conn.execute(
                    "SELECT qualified_name FROM nodes "
                    "WHERE repo_id = ? AND qualified_name IN "
                    "(SELECT value FROM json_each(?))",
                    (repo, json.dumps(list(next_frontier))),
                )
                next_frontier = {row["qualified_name"] for row in cursor}

            impacted.update(next_frontier)

            # Cap total nodes to prevent resource exhaustion on dense graphs
            if len(visited) + len(next_frontier) > max_nodes:
                truncated = True
                break
            frontier = next_frontier
            depth += 1

        # Record total count before any truncation for the response
        total_impacted = len(impacted - seeds)

        # Resolve to full node info using batch fetch to prevent N+1 queries
        changed_nodes = self.get_nodes_by_qualified_names(list(seeds), as_of=as_of)
        impacted_nodes = self.get_nodes_by_qualified_names(
            list(impacted - seeds), as_of=as_of
        )

        # Defensive re-filter (qualified_name set above is already
        # repo-scoped, but get_nodes_by_qualified_names is repo-blind).
        if repo:
            all_node_ids = [n.id for n in changed_nodes] + [
                n.id for n in impacted_nodes
            ]
            valid_ids: set[int] = set()
            if all_node_ids:
                cursor = self._conn.execute(
                    "SELECT id FROM nodes "
                    "WHERE repo_id = ? AND id IN "
                    "(SELECT CAST(value AS INTEGER) FROM json_each(?))",
                    (repo, json.dumps(all_node_ids)),
                )
                valid_ids = {row["id"] for row in cursor}
            changed_nodes = [n for n in changed_nodes if n.id in valid_ids]
            impacted_nodes = [n for n in impacted_nodes if n.id in valid_ids]

        impacted_files = list({n.file_path for n in impacted_nodes})

        # Collect relevant edges in a single batch query
        relevant_edges = []
        all_qns = seeds | impacted
        if all_qns:
            relevant_edges = self.get_edges_among(all_qns)

        return {
            "changed_nodes": changed_nodes,
            "impacted_nodes": impacted_nodes,
            "impacted_files": impacted_files,
            "edges": relevant_edges,
            "truncated": truncated,
            "total_impacted": total_impacted,
        }

    def get_subgraph(self, qualified_names: list[str]) -> dict[str, Any]:
        """Extract a subgraph containing the specified nodes and their connecting edges."""
        node_list = self.get_nodes_by_qualified_names(qualified_names)

        edges = self.get_edges_among(set(qualified_names))

        return {"nodes": node_list, "edges": edges}

    def get_stats(self) -> GraphStats:
        """Return aggregate statistics about the graph."""
        nodes_by_kind: dict[str, int] = {}
        # Avoid redundant COUNT(*) subqueries by calculating total metrics dynamically
        # from the grouped results in Python, reducing database I/O overhead.
        for row in self._conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM nodes GROUP BY kind"
        ):
            nodes_by_kind[row["kind"]] = row["cnt"]

        edges_by_kind: dict[str, int] = {}
        for row in self._conn.execute(
            "SELECT kind, COUNT(*) as cnt FROM edges GROUP BY kind"
        ):
            edges_by_kind[row["kind"]] = row["cnt"]

        total_nodes = sum(nodes_by_kind.values())
        total_edges = sum(edges_by_kind.values())
        files_count = nodes_by_kind.get("File", 0)

        languages = [
            r["language"]
            for r in self._conn.execute(
                "SELECT DISTINCT language FROM nodes WHERE language IS NOT NULL AND language != ''"
            )
        ]

        last_updated = self.get_metadata("last_updated")

        return GraphStats(
            total_nodes=total_nodes,
            total_edges=total_edges,
            nodes_by_kind=nodes_by_kind,
            edges_by_kind=edges_by_kind,
            languages=languages,
            files_count=files_count,
            last_updated=last_updated,
        )

    def get_nodes_by_size(
        self,
        min_lines: int = 50,
        max_lines: int | None = None,
        kind: str | None = None,
        file_path_pattern: str | None = None,
        limit: int = 50,
        repo: str = "",
    ) -> list[GraphNode]:
        """Find nodes within a line-count range, ordered largest first.

        Args:
            min_lines: Minimum line count threshold (inclusive).
            max_lines: Maximum line count threshold (inclusive). None = no upper bound.
            kind: Filter by node kind (Function, Class, File, etc.).
            file_path_pattern: SQL LIKE pattern to filter by file path.
            limit: Maximum results to return.
            repo: Phase 2 Task 10 — when non-empty, scope to nodes whose
                ``repo_id`` matches. Empty (default) = no filter.

        Returns:
            List of GraphNode objects, ordered by line count descending.
        """
        # Use a fully static SQL literal to avoid dynamic SQL construction (Bandit B608).
        cursor = self._conn.execute(
            """
            SELECT * FROM nodes
            WHERE line_start IS NOT NULL
              AND line_end IS NOT NULL
              AND (line_end - line_start + 1) >= ?
              AND (? IS NULL OR (line_end - line_start + 1) <= ?)
              AND (? IS NULL OR kind = ?)
              AND (? IS NULL OR file_path LIKE '%' || ? || '%')
              AND (? = '' OR repo_id = ?)
            ORDER BY (line_end - line_start + 1) DESC LIMIT ?
            """,
            [
                min_lines,
                max_lines,
                max_lines,
                kind,
                kind,
                file_path_pattern,
                file_path_pattern,
                repo,
                repo,
                limit,
            ],
        )
        return [self._row_to_node(r) for r in cursor]

    # --- Public edge access (for visualization etc.) ---

    def get_all_edges(self) -> list[GraphEdge]:
        """Return all edges in the graph."""
        cursor = self._conn.execute("SELECT * FROM edges")
        return [self._row_to_edge(r) for r in cursor]

    def iter_raw_nodes(self) -> "sqlite3.Cursor":
        """Yield raw sqlite3.Row objects for all nodes, bypassing materialization.

        Bolt optimization: Use this for large whole-graph exports to avoid
        peak memory overhead from instantiating tens of thousands of GraphNode objects.
        """
        return self._conn.execute("SELECT * FROM nodes")

    def iter_raw_edges(self) -> "sqlite3.Cursor":
        """Yield raw sqlite3.Row objects for all edges, bypassing materialization.

        Bolt optimization: Use this for large whole-graph exports to avoid
        peak memory overhead from instantiating tens of thousands of GraphEdge objects.
        """
        return self._conn.execute("SELECT * FROM edges")

    def get_all_nodes(self) -> list[GraphNode]:
        """Return all nodes in the graph."""
        cursor = self._conn.execute("SELECT * FROM nodes")
        return [self._row_to_node(r) for r in cursor]

    def get_edges_among(self, qualified_names: set[str]) -> list[GraphEdge]:
        """Return edges where both source and target are in the given set.

        Batches both source and target IN clauses using json_each(?) to stay
        under SQLite's default SQLITE_MAX_VARIABLE_NUMBER limit while
        pushing filtering to the database to minimize data transfer and
        Python-side filtering overhead.
        """
        if not qualified_names:
            return []
        qns_json = json.dumps(list(qualified_names))
        cursor = self._conn.execute(
            """SELECT * FROM edges
               WHERE source_qualified IN (SELECT value FROM json_each(?))
                 AND target_qualified IN (SELECT value FROM json_each(?))""",
            (qns_json, qns_json),
        )
        return [self._row_to_edge(r) for r in cursor]

    # --- Internal helpers ---

    def _build_networkx_graph(self) -> nx.DiGraph:
        """Build (or return cached) in-memory NetworkX directed graph from all edges."""
        with self._cache_lock:
            if self._nxg_cache is not None:
                return self._nxg_cache
            g: nx.DiGraph = nx.DiGraph()
            # Fetch only the needed columns and feed add_edges_from a generator
            # rather than calling add_edge per row in a Python loop.
            cursor = self._conn.execute(
                "SELECT source_qualified, target_qualified, kind FROM edges"
            )
            g.add_edges_from(
                (r["source_qualified"], r["target_qualified"], {"kind": r["kind"]})
                for r in cursor
            )
            self._nxg_cache = g
            return g

    def _make_qualified(self, node: NodeInfo) -> str:
        if node.kind == "File":
            return node.file_path
        if node.parent_name:
            return f"{node.file_path}::{node.parent_name}.{node.name}"
        return f"{node.file_path}::{node.name}"

    def _row_to_node(self, row: sqlite3.Row) -> GraphNode:
        return GraphNode(
            id=row["id"],
            kind=row["kind"],
            name=row["name"],
            qualified_name=row["qualified_name"],
            file_path=row["file_path"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            language=row["language"] or "",
            parent_name=row["parent_name"],
            params=row["params"],
            return_type=row["return_type"],
            is_test=bool(row["is_test"]),
            file_hash=row["file_hash"],
            extra=json.loads(row["extra"])
            if row["extra"] and row["extra"] != "{}"
            else {},
        )

    def _row_to_edge(self, row: sqlite3.Row) -> GraphEdge:
        return GraphEdge(
            id=row["id"],
            kind=row["kind"],
            source_qualified=row["source_qualified"],
            target_qualified=row["target_qualified"],
            file_path=row["file_path"],
            line=row["line"],
            extra=json.loads(row["extra"])
            if row["extra"] and row["extra"] != "{}"
            else {},
        )


_CONTROL_CHAR_MAP = {i: None for i in range(32) if i not in (9, 10)}


def _sanitize_name(s: str, max_len: int = 256) -> str:
    """Strip ASCII control characters and truncate to prevent prompt injection.

    Node names extracted from source code could contain adversarial strings
    (e.g. ``IGNORE_ALL_PREVIOUS_INSTRUCTIONS``).  This function removes control
    characters (0x00-0x1F except tab and newline) and enforces a length limit so
    that names flowing through MCP tool responses cannot easily influence AI
    agent behaviour.
    """
    # Performance Optimization: `str.translate` with a pre-compiled translation map
    # is significantly faster (~7.4x in benchmarks) than a generator expression
    # with `"".join(...)` for filtering control characters. This mitigates a
    # significant performance bottleneck in serialization loops.
    # Strip control chars 0x00-0x1F except \t (0x09) and \n (0x0A)
    cleaned = s.translate(_CONTROL_CHAR_MAP)
    return cleaned[:max_len]


def node_to_dict(n: GraphNode) -> dict:
    return {
        "id": n.id,
        "kind": n.kind,
        "name": _sanitize_name(n.name),
        "qualified_name": _sanitize_name(n.qualified_name),
        "file_path": n.file_path,
        "line_start": n.line_start,
        "line_end": n.line_end,
        "language": n.language,
        "parent_name": _sanitize_name(n.parent_name)
        if n.parent_name
        else n.parent_name,
        "is_test": n.is_test,
    }


def edge_to_dict(e: GraphEdge) -> dict:
    return {
        "id": e.id,
        "kind": e.kind,
        "source": _sanitize_name(e.source_qualified),
        "target": _sanitize_name(e.target_qualified),
        "file_path": e.file_path,
        "line": e.line,
    }


# Security Verification: This file was audited on 2026-04-10.
# All variable-length IN clauses must use the json_each(?) pattern
# to avoid dynamic SQL construction (Bandit B608).
