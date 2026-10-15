"""Temporal index for the code knowledge graph (Phase 3 Task 8).

Wraps :class:`GraphStore` upsert operations with close-out + supersede
semantics across commits. The legacy ``GraphStore.upsert_node`` path uses
``ON CONFLICT(qualified_name) DO UPDATE`` — overwriting in place, which
loses history. :class:`TemporalIndex` instead preserves prior versions
of every node by closing them out (``valid_to_sha = current_sha``) and
inserting a fresh row when the source text diverges.

The contract:

* A node is identified by (``qualified_name``, ``repo_id``) at any point
  in time.
* Each row also has (``valid_from_sha``, ``valid_to_sha``) — when
  ``valid_to_sha`` is NULL the row is currently-valid.
* When the parser re-emits a node at a new commit:

  * Source text diverged from the currently-valid row → close it out
    (set ``valid_to_sha = current_sha``) and INSERT a new row with
    ``valid_from_sha = current_sha``, ``valid_to_sha = NULL``.
  * Source text unchanged → leave the existing row's ``valid_from_sha``
    alone (the row is still the same logical version, we just observed
    it again). Other scalar metadata (line numbers, file path,
    ``repo_id``, …) is refreshed on the existing row.

Edges follow the same shape but are keyed by
(``source_qualified``, ``target_qualified``, ``kind``); they have no
``source_text`` so the divergence branch does not apply — repeat
observations are always treated as "unchanged" with metadata refresh.

The index is opt-in for now and is NOT yet wired into the parser /
incremental update paths; that's a follow-up task. Keeping it isolated
lets the v2 query layer (which depends on the temporal columns Task 6
landed) be exercised end-to-end without changing the legacy ingest
surface for callers that still want the fast overwrite-in-place
behaviour.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import GraphStore
    from .parser import EdgeInfo, NodeInfo


@dataclass(frozen=True)
class TemporalUpsertResult:
    """Outcome of a single :meth:`TemporalIndex.upsert_node` /
    :meth:`TemporalIndex.upsert_edge` call.

    Attributes:
        action: One of ``"inserted"`` (no prior currently-valid row,
            fresh INSERT), ``"unchanged"`` (prior row found, source
            identical or edge already present — metadata refreshed
            in place), or ``"superseded"`` (prior row closed out,
            new row INSERTed).
        closed_out_count: Number of rows whose ``valid_to_sha`` was
            set in this call. ``1`` on supersede, ``0`` otherwise —
            exposed as a count rather than a bool so callers can sum
            it across a scan to report "N rows closed at this commit".
    """

    action: str  # "inserted" | "superseded" | "unchanged"
    closed_out_count: int


def _hash_source(source_text: str | None) -> str:
    """Stable hash for source-text equality comparison.

    Matches the Phase 1 summarizer pattern: SHA-256 of the UTF-8
    encoded source slice. Empty / ``None`` source text both collapse
    to the empty string so two ``None``-source nodes (e.g. Class /
    File rows that don't carry source) compare equal.
    """
    if not source_text:
        return ""
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _quote_identifier(name: str) -> str:
    """Quote a SQL identifier (column or table name) for SQLite."""
    return '"' + name.replace('"', '""') + '"'


class TemporalIndex:
    """Temporal-aware upsert layer over :class:`GraphStore`.

    A new instance is constructed per "commit being ingested" so the
    ``current_sha`` carried by the index is unambiguous. Reusing the
    same instance across commits would silently mis-attribute the
    ``valid_from_sha`` / ``valid_to_sha`` writes — the constructor
    therefore takes the SHA as a required keyword.

    The index reaches into ``store._conn`` directly because the
    public :class:`GraphStore` surface intentionally does not expose
    raw temporal-aware INSERT/UPDATE — it's a back door used by the
    v2 ingest path only.
    """

    def __init__(self, store: GraphStore, *, current_sha: str) -> None:
        self._store = store
        self._current_sha = current_sha
        self._ensure_temporal_friendly_schema()

    def _ensure_temporal_friendly_schema(self) -> None:
        """Relax the legacy ``UNIQUE(qualified_name)`` constraint on ``nodes``.

        The Phase 1 schema declared ``qualified_name TEXT NOT NULL UNIQUE``
        because the legacy upsert path always overwrites in place. The
        temporal supersede semantics introduced here REQUIRE multiple
        rows to coexist with the same ``qualified_name`` — one currently-
        valid row plus N historical rows — so the column-level UNIQUE
        constraint must be lifted.

        SQLite implements column-level UNIQUE via an auto-generated
        index (``sqlite_autoindex_nodes_*``) that cannot be dropped
        directly. The only way to remove it is a table rebuild:

        1. Create ``nodes_new`` mirroring the current schema MINUS the
           UNIQUE constraint, plus a partial unique index on
           ``(qualified_name) WHERE valid_to_sha IS NULL`` so the
           "exactly one currently-valid row per qualified_name"
           invariant survives.
        2. Copy data over.
        3. Drop the old table; rename ``nodes_new`` to ``nodes``.
        4. Recreate the secondary indexes (other than the autoindex).

        Idempotent: a second call detects the absence of the autoindex
        and short-circuits. Safe across alembic upgrades because the
        partial unique index is created with ``IF NOT EXISTS``.
        """
        conn = self._store._conn

        # Detect the legacy autoindex. If it's gone we already migrated.
        legacy = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='nodes' "
            "AND name LIKE 'sqlite_autoindex_nodes_%'"
        ).fetchone()
        if legacy is None:
            # Already temporal-friendly; just make sure the partial
            # unique index exists so re-runs converge to the same state.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_qualified_active "
                "ON nodes(qualified_name) WHERE valid_to_sha IS NULL"
            )
            conn.commit()
            return

        # Read existing column list verbatim — we want to mirror whatever
        # alembic last left on the table (Phase 2/3 columns included).
        cols_info = conn.execute("PRAGMA table_info(nodes)").fetchall()
        col_names = [row[1] for row in cols_info]

        # Build the new-table DDL. ``id`` keeps its PK + AUTOINCREMENT;
        # ``qualified_name`` keeps NOT NULL but loses UNIQUE.
        column_defs: list[str] = []
        for cid, name, typ, notnull, dflt, pk in cols_info:  # noqa: B007
            # Security: Validate column names from PRAGMA (Bandit B608).
            # PRAGMA results are normally safe, but we verify they only contain
            # alphanumeric characters and underscores as a defense-in-depth.
            if not all(c.isalnum() or c == "_" for c in name):
                raise RuntimeError(f"Unsafe column name detected in schema: {name}")

            # Security: Validate type and default value (Bandit B608).
            if typ and not re.match(r"^[A-Za-z0-9\s()]*$", typ):
                raise RuntimeError(f"Unsafe column type detected in schema: {typ}")
            if dflt is not None:
                # Security: Stricter whitelist for default values.
                # Allows numbers, quoted strings, NULL, and simple parenthesized expressions.
                if not re.match(
                    r"^(?:-?\d+(?:\.\d+)?|'(?:[^']|'')*'|NULL|\([^()]*\))$",
                    dflt,
                    re.IGNORECASE,
                ):
                    raise RuntimeError(
                        f"Unsafe default value detected in schema: {dflt}"
                    )

            quoted_name = _quote_identifier(name)
            parts: list[str] = [quoted_name, typ or "TEXT"]
            if pk:
                parts.append("PRIMARY KEY AUTOINCREMENT")
            if notnull and not pk:
                parts.append("NOT NULL")
            if dflt is not None:
                parts.append(f"DEFAULT {dflt}")
            column_defs.append(" ".join(parts))

        # Drop conflicting helpers first so the rename succeeds without
        # collisions on a re-run that aborted mid-way.
        conn.execute("DROP TABLE IF EXISTS nodes_temporal_new")
        conn.execute(f"CREATE TABLE nodes_temporal_new ({', '.join(column_defs)})")

        col_list = ", ".join(_quote_identifier(c) for c in col_names)
        conn.execute(
            f"INSERT INTO nodes_temporal_new ({col_list}) SELECT {col_list} FROM nodes"  # noqa: S608 — quoted names
        )
        conn.execute("DROP TABLE nodes")
        conn.execute("ALTER TABLE nodes_temporal_new RENAME TO nodes")

        # Recreate the secondary indexes on ``nodes``. We deliberately
        # do NOT recreate the autoindex; the partial unique index below
        # replaces it for the temporal-aware invariant.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_qualified ON nodes(qualified_name)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_source_hash ON nodes(source_hash)"
        )
        if "repo_id" in col_names:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_repo_kind ON nodes(repo_id, kind)"
            )
        if "valid_from_sha" in col_names:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_temporal "
                "ON nodes(valid_from_sha, valid_to_sha)"
            )
        # Partial unique index — at most one currently-valid row per
        # qualified_name. Historical rows (valid_to_sha IS NOT NULL)
        # are NOT covered, so multiple supersede generations coexist.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_qualified_active "
            "ON nodes(qualified_name) WHERE valid_to_sha IS NULL"
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def upsert_node(
        self,
        node: NodeInfo,
        file_hash: str = "",
    ) -> TemporalUpsertResult:
        """Insert or supersede a node row.

        Returns a :class:`TemporalUpsertResult` describing which branch
        was taken. The three branches:

        * **No prior currently-valid row** → INSERT new with
          ``valid_from_sha = current_sha``, ``valid_to_sha = NULL``.
          Returns ``("inserted", 0)``.
        * **Prior currently-valid row, source unchanged** → UPDATE other
          fields in place but keep ``valid_from_sha``. Returns
          ``("unchanged", 0)``.
        * **Prior currently-valid row, source diverged** → close out
          (``UPDATE ... SET valid_to_sha = current_sha``) AND INSERT
          a new row. Returns ``("superseded", 1)``.

        Args:
            node: Parser-emitted :class:`NodeInfo`. Must carry
                ``source_text`` for the divergence branch to be
                meaningful; nodes without source text always collapse
                to the "unchanged" branch on re-observation because
                ``_hash_source`` returns the empty string for both.
            file_hash: Optional file-content hash, propagated to the
                ``file_hash`` column for incremental-build callers.
        """
        qualified = self._store._make_qualified(node)
        new_hash = _hash_source(getattr(node, "source_text", "") or "")

        # Find the currently-valid row, if any.
        row = self._store._conn.execute(
            "SELECT id, source_hash FROM nodes "
            "WHERE qualified_name = ? AND valid_to_sha IS NULL",
            (qualified,),
        ).fetchone()

        now = time.time()
        if row is None:
            # No prior currently-valid row → fresh insert.
            self._insert_node_row(node, qualified, file_hash, new_hash, now)
            self._store._conn.commit()
            return TemporalUpsertResult(action="inserted", closed_out_count=0)

        prior_id, prior_hash = row[0], row[1]
        if prior_hash == new_hash:
            # Source unchanged → keep valid_from_sha, refresh metadata.
            self._store._conn.execute(
                "UPDATE nodes SET kind=?, name=?, file_path=?, line_start=?, "
                "line_end=?, language=?, parent_name=?, params=?, return_type=?, "
                "modifiers=?, is_test=?, file_hash=?, extra=?, updated_at=?, "
                "source_text=?, repo_id=? "
                "WHERE id = ?",
                (
                    node.kind,
                    node.name,
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
                    json.dumps(node.extra, separators=(",", ":"))
                    if node.extra
                    else "{}",
                    now,
                    getattr(node, "source_text", None),
                    getattr(node, "repo_id", "") or "",
                    prior_id,
                ),
            )
            self._store._conn.commit()
            return TemporalUpsertResult(action="unchanged", closed_out_count=0)

        # Source diverged → close out + insert new.
        self._store._conn.execute(
            "UPDATE nodes SET valid_to_sha = ? WHERE id = ?",
            (self._current_sha, prior_id),
        )
        self._insert_node_row(node, qualified, file_hash, new_hash, now)
        self._store._conn.commit()
        return TemporalUpsertResult(action="superseded", closed_out_count=1)

    def _insert_node_row(
        self,
        node: NodeInfo,
        qualified: str,
        file_hash: str,
        new_hash: str,
        now: float,
    ) -> None:
        """Insert a new currently-valid node row at ``self._current_sha``.

        Shared between the "no prior row" + "supersede" branches of
        :meth:`upsert_node` so the column list lives in exactly one
        place. ``valid_to_sha`` is always NULL at INSERT time — the
        close-out path mutates it later via UPDATE.
        """
        self._store._conn.execute(
            "INSERT INTO nodes "
            "(kind, name, qualified_name, file_path, line_start, line_end, language, "
            "parent_name, params, return_type, modifiers, is_test, file_hash, extra, "
            "updated_at, source_text, source_hash, repo_id, valid_from_sha, valid_to_sha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
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
                json.dumps(node.extra, separators=(",", ":")) if node.extra else "{}",
                now,
                getattr(node, "source_text", None),
                new_hash,
                getattr(node, "repo_id", "") or "",
                self._current_sha,
            ),
        )

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def upsert_edge(
        self,
        edge: EdgeInfo,
        file_hash: str = "",  # noqa: ARG002 — kept for symmetry with upsert_node
    ) -> TemporalUpsertResult:
        """Insert or refresh an edge row.

        Edges are keyed by (``source_qualified``, ``target_qualified``,
        ``kind``). They carry no ``source_text`` so the supersede
        branch does not apply: a repeat observation always lands in
        the "unchanged" branch with a metadata refresh (line, extra,
        repo_id). The branch tag is still useful — callers can
        distinguish "first observation at this commit" (``inserted``)
        from "edge was already there" (``unchanged``).
        """
        # Find the currently-valid row, if any.
        row = self._store._conn.execute(
            "SELECT id FROM edges "
            "WHERE source_qualified = ? AND target_qualified = ? AND kind = ? "
            "AND valid_to_sha IS NULL",
            (edge.source, edge.target, edge.kind),
        ).fetchone()

        now = time.time()
        if row is None:
            self._store._conn.execute(
                "INSERT INTO edges "
                "(kind, source_qualified, target_qualified, file_path, line, extra, "
                "updated_at, repo_id, valid_from_sha, valid_to_sha) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    edge.kind,
                    edge.source,
                    edge.target,
                    edge.file_path,
                    edge.line,
                    json.dumps(edge.extra, separators=(",", ":"))
                    if edge.extra
                    else "{}",
                    now,
                    getattr(edge, "repo_id", "") or "",
                    self._current_sha,
                ),
            )
            self._store._conn.commit()
            return TemporalUpsertResult(action="inserted", closed_out_count=0)
        # Edge already exists at current state — refresh metadata in place.
        # Edges don't have source_text divergence semantics; kind + endpoints
        # define identity, so we never close-out + insert here.
        self._store._conn.execute(
            "UPDATE edges SET file_path = ?, line = ?, extra = ?, updated_at = ?, repo_id = ? "
            "WHERE id = ?",
            (
                edge.file_path,
                edge.line,
                json.dumps(edge.extra, separators=(",", ":")) if edge.extra else "{}",
                now,
                getattr(edge, "repo_id", "") or "",
                row[0],
            ),
        )
        self._store._conn.commit()
        return TemporalUpsertResult(action="unchanged", closed_out_count=0)

    # ------------------------------------------------------------------
    # File-scoped sweeps
    # ------------------------------------------------------------------

    def close_missing_nodes(
        self,
        file_path: str,
        observed_qualified: set[str],
    ) -> int:
        """Close out currently-valid nodes for ``file_path`` not in ``observed_qualified``.

        Used when re-parsing a file: any node previously visible in the
        file but not produced by the new parse is treated as deleted —
        close it out with ``valid_to_sha = current_sha``. The row is
        not deleted from the table; historical queries can still find
        it via ``WHERE valid_to_sha IS NOT NULL``.

        Args:
            file_path: The file being re-scanned.
            observed_qualified: Qualified names produced by the current
                parse of ``file_path``. Anything currently-valid in
                ``file_path`` and NOT in this set is closed out.

        Returns:
            Number of nodes whose ``valid_to_sha`` was set in this call.
        """
        cursor = self._store._conn.execute(
            "UPDATE nodes SET valid_to_sha = ? "
            "WHERE file_path = ? AND valid_to_sha IS NULL "
            "AND qualified_name NOT IN (SELECT value FROM json_each(?))",
            (
                self._current_sha,
                file_path,
                json.dumps(list(observed_qualified), separators=(",", ":")),
            ),
        )
        closed = cursor.rowcount
        if closed:
            self._store._conn.commit()
        return closed
