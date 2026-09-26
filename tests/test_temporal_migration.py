"""Tests for the 005_temporal_columns alembic migration (Phase 3 Task 6).

Revision ``005`` is the v2.0.0 BREAKING migration. It adds two columns
to both ``nodes`` and ``edges``:

* ``valid_from_sha`` — TEXT, NOT NULL, backfilled with the current
  repo HEAD SHA at migration time. Becomes the DDL default for any
  future ``INSERT`` that omits the column.
* ``valid_to_sha`` — TEXT, NULLable. ``NULL`` means the row is still
  current; the v2 supersede path will set it to a later commit SHA.

It also creates ``idx_nodes_temporal(valid_from_sha, valid_to_sha)``
and the analogous ``idx_edges_temporal``.

Because the column is NOT NULL but no compile-time default exists,
the migration has to read the actual repo HEAD (by reading git's
on-disk refs — no ``git`` subprocess; see ``_read_head_sha``) and bake
it into the DDL default. These tests verify both the happy path (real
git fixture in tmp_path) and the no-git path (synthesized DB outside
any repo → migration aborts with an actionable :class:`RuntimeError`).

Test fixtures use real ``git init`` + ``git commit`` to produce a
genuine ``.git`` directory; the migration then resolves HEAD straight
from that directory's refs end-to-end.
"""

from __future__ import annotations

import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from better_code_review_graph.graph import GraphStore


def _alembic_config_for(db_path: Path) -> Config:
    """Build an Alembic Config bound to ``db_path`` using the project ini."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _table_info(db_path: Path, table: str) -> list[tuple]:
    """Return PRAGMA table_info rows as (name, type, notnull, dflt, pk)."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [
        (name, typ, notnull, dflt, pk) for (_cid, name, typ, notnull, dflt, pk) in rows
    ]


def _column_info(db_path: Path, table: str, column: str) -> tuple | None:
    for row in _table_info(db_path, table):
        if row[0] == column:
            return row
    return None


def _index_names(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(str(db_path))) as conn:
        return {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
            )
        }


def _git_init_with_commit(repo_root: Path) -> str:
    """Initialize a git repo at ``repo_root`` with a single commit.

    Returns the resulting HEAD SHA. We use ``-c`` to inline a stable
    user identity so the commit succeeds regardless of the operator's
    global git config.
    """
    repo_root.mkdir(parents=True, exist_ok=True)
    env_args = [
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "-c",
        "init.defaultBranch=main",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run(
        ["git", *env_args, "init"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )
    # Empty commit — sufficient for ``git rev-parse HEAD`` to resolve.
    subprocess.run(
        ["git", *env_args, "commit", "--allow-empty", "-m", "initial"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert len(sha) == 40, f"unexpected HEAD shape: {sha!r}"
    return sha


@pytest.fixture
def repo_with_db(tmp_path: Path) -> tuple[Path, Path, str]:
    """Build a real git repo containing a CRG-style ``graph.db`` location.

    Layout mirrors production: ``<repo>/.better-code-review-graph/graph.db``.
    Returns ``(db_path, repo_root, head_sha)``.
    """
    repo_root = tmp_path / "myrepo"
    head_sha = _git_init_with_commit(repo_root)
    crg_dir = repo_root / ".better-code-review-graph"
    crg_dir.mkdir()
    db_path = crg_dir / "graph.db"
    return db_path, repo_root, head_sha


# ---------------------------------------------------------------------------
# (1) valid_from_sha column added — NOT NULL on both nodes + edges
# ---------------------------------------------------------------------------


def test_temporal_migration_adds_valid_from_sha_column(
    repo_with_db: tuple[Path, Path, str],
) -> None:
    """``valid_from_sha`` exists after upgrade — TEXT, NOT NULL, has default."""
    db_path, _repo, head_sha = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    for table in ("nodes", "edges"):
        info = _column_info(db_path, table, "valid_from_sha")
        assert info is not None, f"{table}.valid_from_sha missing after upgrade"
        name, typ, notnull, dflt, pk = info
        assert name == "valid_from_sha"
        assert typ.upper() == "TEXT"
        assert notnull == 1, (
            f"{table}.valid_from_sha must be NOT NULL, got notnull={notnull}"
        )
        # Default is the HEAD SHA wrapped in single quotes (SQLite stores
        # the literal text used in the DDL DEFAULT clause).
        assert dflt is not None, f"{table}.valid_from_sha must have a default; got NULL"
        assert head_sha in dflt, (
            f"{table}.valid_from_sha default should embed HEAD SHA "
            f"{head_sha!r}, got {dflt!r}"
        )
        assert pk == 0


# ---------------------------------------------------------------------------
# (2) valid_to_sha column added — NULL allowed
# ---------------------------------------------------------------------------


def test_temporal_migration_adds_valid_to_sha_column(
    repo_with_db: tuple[Path, Path, str],
) -> None:
    """``valid_to_sha`` exists after upgrade — TEXT, NULLable, no default."""
    db_path, _repo, _sha = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    for table in ("nodes", "edges"):
        info = _column_info(db_path, table, "valid_to_sha")
        assert info is not None, f"{table}.valid_to_sha missing after upgrade"
        name, typ, notnull, dflt, pk = info
        assert name == "valid_to_sha"
        assert typ.upper() == "TEXT"
        assert notnull == 0, (
            f"{table}.valid_to_sha must be NULLable, got notnull={notnull}"
        )
        assert dflt is None, f"{table}.valid_to_sha must have no default, got {dflt!r}"
        assert pk == 0


# ---------------------------------------------------------------------------
# (3) Indexes created
# ---------------------------------------------------------------------------


def test_temporal_migration_creates_indexes(
    repo_with_db: tuple[Path, Path, str],
) -> None:
    """``idx_nodes_temporal`` + ``idx_edges_temporal`` exist after upgrade."""
    db_path, _repo, _sha = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    indexes = _index_names(db_path)
    assert "idx_nodes_temporal" in indexes, (
        f"idx_nodes_temporal missing; got {sorted(indexes)}"
    )
    assert "idx_edges_temporal" in indexes, (
        f"idx_edges_temporal missing; got {sorted(indexes)}"
    )


# ---------------------------------------------------------------------------
# (4) Pre-existing rows backfilled with HEAD SHA
# ---------------------------------------------------------------------------


def test_temporal_migration_backfills_with_current_head(
    repo_with_db: tuple[Path, Path, str],
) -> None:
    """Rows inserted at rev 004 get ``valid_from_sha = HEAD`` after upgrade.

    Sequence:
      1. Stamp DB to rev 004 (pre-005 state).
      2. Insert a node + edge via raw SQL (the columns don't exist yet).
      3. Upgrade head → migration should backfill both rows.
      4. Read back: ``valid_from_sha == head_sha``, ``valid_to_sha IS NULL``.
    """
    db_path, _repo, head_sha = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "004")

    # Insert a pre-existing node + edge before the temporal migration runs.
    # ``nodes.updated_at`` and ``edges.updated_at`` are NOT NULL with no
    # default; ``edges.kind`` likewise. We supply them explicitly so the
    # raw-SQL inserts succeed against the post-004 schema.
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(
            """INSERT INTO nodes
               (kind, name, qualified_name, file_path, line_start, line_end,
                language, updated_at)
               VALUES ('Function', 'pre_existing', 'src/pre.py::pre_existing',
                       'src/pre.py', 1, 5, 'python', 0)"""
        )
        conn.execute(
            """INSERT INTO edges
               (kind, source_qualified, target_qualified, file_path, updated_at)
               VALUES ('CALLS', 'src/pre.py::pre_existing',
                       'src/pre.py::callee', 'src/pre.py', 0)"""
        )
        conn.commit()

    # Run the BREAKING migration.
    command.upgrade(cfg, "head")

    # Read back. SQLite ALTER TABLE ADD COLUMN ... DEFAULT '<v>' applies
    # the default value to existing rows during the ALTER, so the
    # pre-existing node now reports ``valid_from_sha = head_sha``.
    with closing(sqlite3.connect(str(db_path))) as conn:
        node_row = conn.execute(
            "SELECT valid_from_sha, valid_to_sha FROM nodes "
            "WHERE qualified_name = 'src/pre.py::pre_existing'"
        ).fetchone()
        edge_row = conn.execute(
            "SELECT valid_from_sha, valid_to_sha FROM edges "
            "WHERE source_qualified = 'src/pre.py::pre_existing'"
        ).fetchone()

    assert node_row is not None
    assert node_row[0] == head_sha, (
        f"node.valid_from_sha should be {head_sha!r} (HEAD at migration), "
        f"got {node_row[0]!r}"
    )
    assert node_row[1] is None, (
        f"node.valid_to_sha should be NULL on pre-existing rows, got {node_row[1]!r}"
    )

    assert edge_row is not None
    assert edge_row[0] == head_sha, (
        f"edge.valid_from_sha should be {head_sha!r}, got {edge_row[0]!r}"
    )
    assert edge_row[1] is None, f"edge.valid_to_sha should be NULL, got {edge_row[1]!r}"


# ---------------------------------------------------------------------------
# (5) Migration aborts when no .git is reachable
# ---------------------------------------------------------------------------


def test_temporal_migration_aborts_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DB outside any git repo → migration aborts with actionable message.

    The session-scoped autouse conftest sets ``CRG_TEST_ALLOW_NO_GIT=1``
    so legacy tests can run without a git ancestor; we explicitly
    unset that env var here to exercise the production abort path.
    The ``_find_repo_root`` helper is then invoked end-to-end via
    ``command.upgrade``: alembic loads the migration which calls
    ``_resolve_head_sha`` which calls ``_find_repo_root`` which
    raises with the documented message.
    """
    monkeypatch.delenv("CRG_TEST_ALLOW_NO_GIT", raising=False)

    # Synthesise a path whose parents have no ``.git`` (filesystem root
    # has no .git on the test host).
    no_git_dir = tmp_path / "outside_any_repo"
    no_git_dir.mkdir()
    db_path = no_git_dir / "graph.db"

    cfg = _alembic_config_for(db_path)
    # Bring the DB up to rev 004 first so the chain has somewhere to start.
    command.upgrade(cfg, "004")

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(cfg, "head")

    msg = str(excinfo.value)
    assert "git" in msg.lower(), f"error message should mention git: {msg!r}"
    assert "valid_from_sha" in msg, (
        f"error message should reference the column being backfilled: {msg!r}"
    )
    assert "CRG_DOWNGRADE_TO_1_X" in msg, (
        f"error message should advertise the downgrade escape hatch: {msg!r}"
    )


def test_temporal_migration_uses_sentinel_with_test_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CRG_TEST_ALLOW_NO_GIT=1`` + no ``.git`` → sentinel SHA + clean upgrade.

    Pins the test-suite escape hatch documented on
    ``_TEST_ALLOW_NO_GIT_ENV_VAR``. The conftest sets it for the whole
    session; this test pins the contract so accidental removal of the
    env var lookup in the migration breaks here first.
    """
    monkeypatch.setenv("CRG_TEST_ALLOW_NO_GIT", "1")

    no_git_dir = tmp_path / "outside_any_repo"
    no_git_dir.mkdir()
    db_path = no_git_dir / "graph.db"

    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    # Schema landed cleanly with the sentinel SHA as the DDL default.
    info = _column_info(db_path, "nodes", "valid_from_sha")
    assert info is not None
    _name, _typ, notnull, dflt, _pk = info
    assert notnull == 1
    assert dflt is not None
    assert "0" * 40 in dflt, (
        f"DDL default should embed the in-memory sentinel SHA, got {dflt!r}"
    )


# ---------------------------------------------------------------------------
# (5b) Per-subject data-dir stores skip the git requirement (hull mode-3)
# ---------------------------------------------------------------------------


def test_temporal_migration_sentinel_for_data_dir_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``<CRG_DATA_DIR>/subs/<sub>/graph.db`` → sentinel SHA + clean upgrade.

    Multi-user (hull mode-3) deployments scope each namespace's graph to a
    data-directory DB that intentionally lives OUTSIDE every repo, so the
    git walk-up must not run for it (regression: the guard used to abort
    the whole GraphStore construction with ``005_temporal_columns
    requires git in repo``). No ``CRG_TEST_ALLOW_NO_GIT`` involved — this
    is the production mode-3 path.
    """
    monkeypatch.delenv("CRG_TEST_ALLOW_NO_GIT", raising=False)
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "data" / "subs" / "alice" / "graph.db"
    db_path.parent.mkdir(parents=True)  # production: GraphStore.__init__ does this

    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    info = _column_info(db_path, "nodes", "valid_from_sha")
    assert info is not None
    _name, _typ, notnull, dflt, _pk = info
    assert notnull == 1
    assert dflt is not None
    assert "0" * 40 in dflt, (
        f"data-dir store should backfill with the sentinel SHA, got {dflt!r}"
    )


def test_temporal_migration_still_aborts_for_repo_less_non_data_dir_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-data-dir DB without ``.git`` still aborts (guard not weakened).

    The data-dir exemption is scoped to the ``subs/`` subtree of the crg
    data directory. A repo-less DB anywhere else (e.g. a scratch tmp dir)
    keeps the actionable RuntimeError when the test escape hatch is unset.
    """
    monkeypatch.delenv("CRG_TEST_ALLOW_NO_GIT", raising=False)
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "outside_any_repo" / "graph.db"
    db_path.parent.mkdir(parents=True)

    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "004")

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(cfg, "head")
    assert "git" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# (6) Round-trip upgrade -> downgrade -> upgrade
# ---------------------------------------------------------------------------


def test_temporal_migration_round_trip_upgrade_downgrade_upgrade(
    repo_with_db: tuple[Path, Path, str],
) -> None:
    """upgrade(head) -> downgrade("004") -> upgrade(head) leaves no orphans.

    SQLite < 3.35 lacks native ``ALTER TABLE DROP COLUMN``; the
    migration uses ``op.batch_alter_table`` for the downgrade path.
    """
    db_path, _repo, _sha = repo_with_db
    cfg = _alembic_config_for(db_path)

    # Up — temporal columns + indexes present.
    command.upgrade(cfg, "head")
    assert _column_info(db_path, "nodes", "valid_from_sha") is not None
    assert _column_info(db_path, "edges", "valid_from_sha") is not None
    indexes_after_up = _index_names(db_path)
    assert "idx_nodes_temporal" in indexes_after_up
    assert "idx_edges_temporal" in indexes_after_up

    # Down to 004 — temporal columns + indexes gone, security_tags survives.
    command.downgrade(cfg, "004")
    assert _column_info(db_path, "nodes", "valid_from_sha") is None, (
        "nodes.valid_from_sha leaked through downgrade"
    )
    assert _column_info(db_path, "edges", "valid_from_sha") is None
    assert _column_info(db_path, "nodes", "valid_to_sha") is None
    assert _column_info(db_path, "edges", "valid_to_sha") is None
    indexes_after_down = _index_names(db_path)
    assert "idx_nodes_temporal" not in indexes_after_down
    assert "idx_edges_temporal" not in indexes_after_down
    # Phase 3 Task 2 column survives the partial downgrade.
    assert _column_info(db_path, "nodes", "security_tags") is not None
    # Phase 2 federation pieces also survive.
    assert _column_info(db_path, "nodes", "repo_id") is not None
    assert _column_info(db_path, "edges", "repo_id") is not None

    # Up again — temporal columns + indexes restored.
    command.upgrade(cfg, "head")
    assert _column_info(db_path, "nodes", "valid_from_sha") is not None
    assert _column_info(db_path, "edges", "valid_from_sha") is not None
    indexes_redo = _index_names(db_path)
    assert "idx_nodes_temporal" in indexes_redo
    assert "idx_edges_temporal" in indexes_redo


# ---------------------------------------------------------------------------
# (7) Default value applies to inserts that omit the column
# ---------------------------------------------------------------------------


def test_temporal_columns_default_for_new_inserts(
    repo_with_db: tuple[Path, Path, str],
) -> None:
    """Post-migration ``INSERT`` without valid_from_sha gets the migration default.

    The DDL default is the HEAD SHA at migration time; new git commits
    do NOT auto-update this default. The v2 ingest path is expected to
    set the column explicitly per-commit; this test pins the fallback
    behaviour for callers that don't.
    """
    db_path, _repo, head_sha = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(
            """INSERT INTO nodes
               (kind, name, qualified_name, file_path, line_start, line_end,
                language, updated_at)
               VALUES ('Function', 'after_migration',
                       'src/post.py::after_migration', 'src/post.py',
                       10, 20, 'python', 0)"""
        )
        conn.commit()
        row = conn.execute(
            "SELECT valid_from_sha, valid_to_sha FROM nodes "
            "WHERE qualified_name = 'src/post.py::after_migration'"
        ).fetchone()

    assert row is not None
    assert row[0] == head_sha, (
        f"new INSERT should inherit migration-time default {head_sha!r}, got {row[0]!r}"
    )
    assert row[1] is None, f"new row valid_to_sha should default NULL, got {row[1]!r}"


# ---------------------------------------------------------------------------
# (8) Pre-2.0 backup hook fires when crossing 005
# ---------------------------------------------------------------------------


def test_pre_2_0_backup_fires_when_crossing_005(
    repo_with_db: tuple[Path, Path, str],
) -> None:
    """Synthetic DB at rev 004 → backup is created BEFORE the upgrade chain.

    Once 005 is the real shipped head, the Phase 3 Task 1 hook in
    ``GraphStore._run_alembic_upgrade`` actually fires (no monkeypatch
    needed). The backup file must exist before the BREAKING migration
    runs, so the operator can roll back via ``CRG_DOWNGRADE_TO_1_X=1``
    if the migration produces a worse outcome than expected.
    """
    db_path, _repo, _sha = repo_with_db
    cfg = _alembic_config_for(db_path)
    # Bring DB to rev 004 (pre-BREAKING).
    command.upgrade(cfg, "004")

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    assert not backup_path.exists()

    # GraphStore brings the DB to head — this triggers the backup hook
    # because the chain crosses 004→005.
    store = GraphStore(db_path)
    try:
        assert backup_path.exists(), (
            f"backup {backup_path} should be taken when crossing 004→005"
        )
        # The backup is from BEFORE the upgrade — should report rev 004.
        with closing(sqlite3.connect(str(backup_path))) as conn:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert row is not None
        assert row[0] == "004", (
            f"backup should preserve pre-005 state (rev 004); got {row[0]!r}"
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Helper coverage — extracted helpers for unit testing the pure parts
# ---------------------------------------------------------------------------


def _load_migration_module():
    """Load the 005 migration as a regular Python module for direct testing."""
    import importlib.util

    repo_root = Path(__file__).resolve().parent.parent
    mig_file = repo_root / "migrations" / "versions" / "005_temporal_columns.py"
    spec = importlib.util.spec_from_file_location("crg_mig_005", mig_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_db_path_returns_none_for_memory_url() -> None:
    """``:memory:`` URLs return ``None`` so the caller can use the sentinel SHA.

    In-memory DBs don't survive the process so the SHA we bake into
    the DDL default is only the value for transient test rows; we
    therefore short-circuit the git lookup rather than abort.
    """
    module = _load_migration_module()
    assert module._extract_db_path_from_url("sqlite:///:memory:") is None
    assert module._extract_db_path_from_url("sqlite://:memory:") is None


def test_resolve_head_sha_uses_sentinel_for_memory_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_resolve_head_sha`` returns the in-memory sentinel for ``:memory:`` URLs."""
    module = _load_migration_module()

    class _FakeContext:
        class config:
            @staticmethod
            def get_main_option(name: str) -> str:
                assert name == "sqlalchemy.url"
                return "sqlite:///:memory:"

    monkeypatch.setattr(module.op, "get_context", lambda: _FakeContext)
    sha = module._resolve_head_sha()
    assert sha == module._IN_MEMORY_SENTINEL_SHA
    assert sha == "0" * 40


def test_extract_db_path_rejects_unrecognized_url() -> None:
    """Non-sqlite URLs raise with a clear message."""
    module = _load_migration_module()
    with pytest.raises(RuntimeError, match="unrecognized SQLAlchemy URL"):
        module._extract_db_path_from_url("postgres://wrong")


def test_find_repo_root_detects_dot_git_file(tmp_path: Path) -> None:
    """A ``.git`` file (worktree / submodule pattern) qualifies as a repo root."""
    module = _load_migration_module()
    repo_root = tmp_path / "fake_worktree"
    repo_root.mkdir()
    (repo_root / ".git").write_text("gitdir: /elsewhere\n")  # file, not dir
    nested = repo_root / "sub" / "graph.db"
    nested.parent.mkdir(parents=True)

    found = module._find_repo_root(nested)
    assert found == repo_root


def test_read_head_sha_loose_ref(tmp_path: Path) -> None:
    """HEAD -> loose ref -> SHA (the regular-clone path)."""
    module = _load_migration_module()
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    sha = "a" * 40
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text(sha + "\n")
    assert module._read_head_sha(tmp_path) == sha


def test_read_head_sha_detached(tmp_path: Path) -> None:
    """A detached HEAD stores the raw object name directly in ``HEAD``."""
    module = _load_migration_module()
    git = tmp_path / ".git"
    git.mkdir()
    sha = "b" * 40
    (git / "HEAD").write_text(sha + "\n")
    assert module._read_head_sha(tmp_path) == sha


def test_read_head_sha_packed_refs(tmp_path: Path) -> None:
    """HEAD ref absent as a loose file but present in ``packed-refs``."""
    module = _load_migration_module()
    git = tmp_path / ".git"
    git.mkdir()
    sha = "c" * 40
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{sha} refs/heads/main\n"
        f"^{'0' * 40}\n"  # peeled tag line — must be ignored
    )
    assert module._read_head_sha(tmp_path) == sha


def test_read_head_sha_worktree_pointer(tmp_path: Path) -> None:
    """A ``.git`` file ``gitdir:`` pointer (worktree) resolves via commondir."""
    module = _load_migration_module()
    # Common repo dir holds the shared refs.
    common = tmp_path / "main" / ".git"
    (common / "refs" / "heads").mkdir(parents=True)
    sha = "d" * 40
    (common / "refs" / "heads" / "feature").write_text(sha + "\n")
    # Linked-worktree private gitdir: per-worktree HEAD + commondir pointer.
    wt_gitdir = common / "worktrees" / "wt1"
    wt_gitdir.mkdir(parents=True)
    (wt_gitdir / "HEAD").write_text("ref: refs/heads/feature\n")
    (wt_gitdir / "commondir").write_text("../..\n")  # -> common
    # The worktree checkout dir with the ``.git`` text-file pointer.
    repo_root = tmp_path / "wt"
    repo_root.mkdir()
    (repo_root / ".git").write_text(f"gitdir: {wt_gitdir}\n")
    assert module._read_head_sha(repo_root) == sha


def test_read_head_sha_unresolvable_ref(tmp_path: Path) -> None:
    """HEAD points at a ref with no loose/packed entry (no commits yet)."""
    module = _load_migration_module()
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    with pytest.raises(RuntimeError, match="could not resolve HEAD ref"):
        module._read_head_sha(tmp_path)


def test_read_head_sha_no_git(tmp_path: Path) -> None:
    """No ``.git`` at the repo root → actionable RuntimeError."""
    module = _load_migration_module()
    with pytest.raises(RuntimeError, match="CRG_DOWNGRADE_TO_1_X"):
        module._read_head_sha(tmp_path)


def test_read_head_sha_unrecognized_head(tmp_path: Path) -> None:
    """A HEAD file that is neither a ref nor a SHA → RuntimeError."""
    module = _load_migration_module()
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("garbage contents\n")
    with pytest.raises(RuntimeError, match="unrecognized HEAD"):
        module._read_head_sha(tmp_path)


def test_read_head_sha_bad_git_file(tmp_path: Path) -> None:
    """A ``.git`` file without a ``gitdir:`` prefix → RuntimeError."""
    module = _load_migration_module()
    (tmp_path / ".git").write_text("not a gitdir pointer\n")
    with pytest.raises(RuntimeError, match="unrecognized .git file"):
        module._read_head_sha(tmp_path)
