"""SOTA schema upgrades: commit_order, edge confidence/resolution, and nodes_fts.

Revision ID: 007
Revises: 006
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_columns(conn: sa.Connection, table_name: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _table_exists(conn: sa.Connection, table_name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name = :name"
        ),
        {"name": table_name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    """Apply CRG-5 (commit_order), CRG-7 (nodes_fts), CRG-10 (edge confidence)."""
    conn = op.get_bind()

    if _table_exists(conn, "commits") and "commit_order" not in _table_columns(
        conn, "commits"
    ):
        op.add_column(
            "commits",
            sa.Column("commit_order", sa.Integer(), nullable=True, server_default="0"),
        )
        conn.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_commits_repo_order "
                "ON commits(repo_id, commit_order)"
            )
        )

    if _table_exists(conn, "edges"):
        edge_cols = _table_columns(conn, "edges")
        if "confidence" not in edge_cols:
            op.add_column(
                "edges",
                sa.Column(
                    "confidence",
                    sa.Float(),
                    nullable=False,
                    server_default="1.0",
                ),
            )
        if "resolution" not in edge_cols:
            op.add_column(
                "edges",
                sa.Column(
                    "resolution",
                    sa.Text(),
                    nullable=False,
                    server_default="syntactic",
                ),
            )
        conn.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_edges_confidence ON edges(confidence)"
            )
        )

    if not _table_exists(conn, "nodes_fts"):
        conn.execute(
            sa.text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
                "qualified_name UNINDEXED, "
                "ident_tokens, "
                "signature, "
                "doc_comment"
                ")"
            )
        )


def downgrade() -> None:
    """Revert SOTA schema upgrades (best-effort on SQLite)."""
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS nodes_fts"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_edges_confidence"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_commits_repo_order"))
