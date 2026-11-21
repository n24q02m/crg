"""The alembic upgrade runs as one SQLite transaction.

pysqlite's legacy transaction handling commits before every DDL statement, so the
migration chain used to land as one durable commit per CREATE/ALTER: a fresh graph DB
took 31 WAL commits, each flushed to disk, which is the setup cost every test that
builds a ``GraphStore`` pays. An upgrade that failed half-way also left the DB with
part of a revision applied and the version row of the revision before it, so the next
start re-ran DDL that had already landed.
"""

from __future__ import annotations

import sqlite3
import struct
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.ddl.sqlite import SQLiteImpl

from crg.graph import GraphStore


def _upgrade_config(db_path: Path) -> Config:
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _wal_commit_frames(db_path: Path) -> int:
    """Count commit frames in the live WAL of ``db_path``.

    WAL layout: a 32-byte header (page size at bytes 8-12, salts at 16-24), then
    frames of a 24-byte header plus one page. A frame header carries the database
    size after the commit at bytes 4-8 on commit frames and 0 on the others; frames
    whose salts differ from the header are left over from an earlier WAL generation.
    """
    data = Path(f"{db_path}-wal").read_bytes()
    if len(data) < 32:
        return 0
    page_size = struct.unpack(">I", data[8:12])[0]
    salt = data[16:24]
    commits = 0
    offset = 32
    while offset + 24 + page_size <= len(data):
        header = data[offset : offset + 24]
        if header[8:16] != salt:
            break
        if struct.unpack(">I", header[4:8])[0]:
            commits += 1
        offset += 24 + page_size
    return commits


def test_upgrade_chain_lands_as_one_commit(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    with closing(sqlite3.connect(db_path)) as holder:
        # WAL mode as GraphStore uses it. The read opens the WAL index, so this
        # connection keeps the WAL on disk after the migration connection closes.
        holder.execute("PRAGMA journal_mode=WAL")
        holder.execute("SELECT count(*) FROM sqlite_master").fetchone()

        command.upgrade(_upgrade_config(db_path), "head")

        assert _wal_commit_frames(db_path) == 1


def test_failed_upgrade_leaves_no_partial_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_create_index = SQLiteImpl.create_index

    def create_index_failing_in_006(self, index, **kw):
        # Revision 006 creates the ``commits`` table, then this index.
        if index.name == "idx_commits_repo_time":
            raise RuntimeError("injected failure inside revision 006")
        return real_create_index(self, index, **kw)

    monkeypatch.setattr(SQLiteImpl, "create_index", create_index_failing_in_006)
    db_path = tmp_path / "g.db"

    with pytest.raises(RuntimeError, match="injected failure inside revision 006"):
        GraphStore(db_path)

    with closing(sqlite3.connect(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert tables == set()
