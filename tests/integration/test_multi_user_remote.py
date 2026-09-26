"""Per-sub graph DB isolation in de-hosted multi-user (hull mode-3) deployments.

The HTTP-level token→namespace→subsurface proof runs live in the WP2 mode-3
script (crg FastMCP + HullAuthMiddleware); this module pins the storage-level
contract those deployments rely on:

- each authenticated namespace gets its own ``graph.db`` under
  ``<CRG_DATA_DIR>/subs/<namespace>/`` (post-de-host: no per-sub credential
  store — only the graph DB is scoped per subject);
- two subjects building content with the same file layout see only their own
  namespace's nodes.
"""

from __future__ import annotations

import pytest

from better_code_review_graph.credential_state import db_path_for_sub
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo


@pytest.mark.integration
def test_two_subs_get_distinct_db_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    pa = db_path_for_sub("user_a")
    pb = db_path_for_sub("user_b")
    assert pa != pb
    assert "user_a" in str(pa)
    assert "user_b" in str(pb)
    assert str(tmp_path) in str(pa)
    assert str(tmp_path) in str(pb)


@pytest.mark.integration
def test_sub_stores_do_not_see_each_others_nodes(tmp_path, monkeypatch):
    """Same repo layout built under two namespaces: no cross-visibility."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))

    def _build(store: GraphStore, marker: str) -> None:
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name=f"{marker}_fn",
                file_path="calc.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        store._conn.commit()

    store_a = GraphStore(db_path_for_sub("user_a"))
    store_b = GraphStore(db_path_for_sub("user_b"))
    try:
        _build(store_a, "alice")
        _build(store_b, "bob")

        names_a = {
            row["name"]
            for row in store_a._conn.execute("SELECT name FROM nodes")
        }
        names_b = {
            row["name"]
            for row in store_b._conn.execute("SELECT name FROM nodes")
        }
        assert names_a == {"alice_fn"}
        assert names_b == {"bob_fn"}
    finally:
        store_a.close()
        store_b.close()
