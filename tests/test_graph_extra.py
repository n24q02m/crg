"""Additional tests for graph.py to cover edge cases and missing lines."""

from __future__ import annotations

from crg.graph import (
    GraphStore,
    _sanitize_name,
    edge_to_dict,
    node_to_dict,
)
from crg.parser import EdgeInfo, NodeInfo

# ---------------------------------------------------------------------------
# _sanitize_name
# ---------------------------------------------------------------------------


class TestSanitizeName:
    def test_normal_name(self):
        assert _sanitize_name("hello_world") == "hello_world"

    def test_control_chars_stripped(self):
        assert _sanitize_name("hello\x00world") == "helloworld"
        assert _sanitize_name("test\x01\x02\x03name") == "testname"

    def test_tab_and_newline_preserved(self):
        assert _sanitize_name("hello\tworld") == "hello\tworld"
        assert _sanitize_name("hello\nworld") == "hello\nworld"

    def test_truncation(self):
        long = "x" * 300
        assert len(_sanitize_name(long)) == 256

    def test_custom_max_len(self):
        assert _sanitize_name("abcdef", max_len=3) == "abc"

    def test_empty_string(self):
        assert _sanitize_name("") == ""


# ---------------------------------------------------------------------------
# node_to_dict and edge_to_dict
# ---------------------------------------------------------------------------


class TestConversions:
    def test_node_to_dict_with_parent(self, tmp_path):
        db = GraphStore(str(tmp_path / "t.db"))
        db.upsert_node(
            NodeInfo(
                kind="Function",
                name="method",
                file_path="/f.py",
                line_start=1,
                line_end=5,
                language="python",
                parent_name="MyClass",
            )
        )
        node = db.get_node("/f.py::MyClass.method")
        assert node is not None
        d = node_to_dict(node)
        assert d["parent_name"] == "MyClass"
        assert d["kind"] == "Function"
        db.close()

    def test_node_to_dict_without_parent(self, tmp_path):
        db = GraphStore(str(tmp_path / "t.db"))
        db.upsert_node(
            NodeInfo(
                kind="Function",
                name="func",
                file_path="/f.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        node = db.get_node("/f.py::func")
        assert node is not None
        d = node_to_dict(node)
        assert d["parent_name"] is None
        db.close()

    def test_edge_to_dict(self, tmp_path):
        db = GraphStore(str(tmp_path / "t.db"))
        db.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/a.py::foo",
                target="/b.py::bar",
                file_path="/a.py",
                line=10,
            )
        )
        edges = db.get_edges_by_source("/a.py::foo")
        assert len(edges) == 1
        d = edge_to_dict(edges[0])
        assert d["kind"] == "CALLS"
        assert d["line"] == 10
        db.close()


# ---------------------------------------------------------------------------
# GraphStore edge cases
# ---------------------------------------------------------------------------


class TestGraphStoreExtra:
    def test_context_manager(self, tmp_path):
        with GraphStore(str(tmp_path / "t.db")) as store:
            store.upsert_node(
                NodeInfo(
                    kind="File",
                    name="/f.py",
                    file_path="/f.py",
                    line_start=1,
                    line_end=10,
                    language="python",
                )
            )
            store.commit()
        # Should be closed after context manager

    def test_get_node_not_found(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        assert store.get_node("nonexistent") is None
        store.close()

    def test_get_subgraph(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="a",
                file_path="/f.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="b",
                file_path="/f.py",
                line_start=6,
                line_end=10,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/f.py::a",
                target="/f.py::b",
                file_path="/f.py",
                line=3,
            )
        )
        store.commit()

        sub = store.get_subgraph(["/f.py::a", "/f.py::b"])
        assert len(sub["nodes"]) == 2
        assert len(sub["edges"]) == 1
        store.close()

    def test_get_subgraph_excludes_outside_edges(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="a",
                file_path="/f.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="b",
                file_path="/f.py",
                line_start=6,
                line_end=10,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="c",
                file_path="/g.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/f.py::a",
                target="/g.py::c",
                file_path="/f.py",
                line=3,
            )
        )
        store.commit()

        # Only request a, edges to c should be excluded
        sub = store.get_subgraph(["/f.py::a"])
        assert len(sub["edges"]) == 0
        store.close()

    def test_get_nodes_by_size_with_max_lines(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="small",
                file_path="/f.py",
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="big",
                file_path="/f.py",
                line_start=1,
                line_end=200,
                language="python",
            )
        )
        store.commit()

        nodes = store.get_nodes_by_size(min_lines=5, max_lines=50)
        names = [n.name for n in nodes]
        assert "small" in names
        assert "big" not in names
        store.close()

    def test_get_edges_by_target_bare_name_fallback(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/a.py::foo",
                target="bar",
                file_path="/a.py",
                line=5,
            )
        )
        store.commit()

        # Search by qualified name should fallback to bare name
        edges = store.get_edges_by_target("/x.py::bar")
        assert len(edges) == 1
        assert edges[0].target_qualified == "bar"
        store.close()

    def test_get_all_files(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_node(
            NodeInfo(
                kind="File",
                name="/a.py",
                file_path="/a.py",
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="File",
                name="/b.py",
                file_path="/b.py",
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.commit()

        files = store.get_all_files()
        assert "/a.py" in files
        assert "/b.py" in files
        store.close()

    def test_get_all_edges(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/a.py::x",
                target="/b.py::y",
                file_path="/a.py",
                line=1,
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="IMPORTS_FROM",
                source="/c.py",
                target="/d.py",
                file_path="/c.py",
                line=1,
            )
        )
        store.commit()

        edges = store.get_all_edges()
        assert len(edges) == 2
        store.close()

    def test_get_all_nodes(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_node(
            NodeInfo(
                kind="File",
                name="/a.py",
                file_path="/a.py",
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="foo",
                file_path="/a.py",
                line_start=2,
                line_end=5,
                language="python",
            )
        )
        store.commit()

        nodes = store.get_all_nodes()
        assert len(nodes) == 2
        names = [n.name for n in nodes]
        assert "/a.py" in names
        assert "foo" in names
        store.close()

    def test_get_edges_among_empty_set(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        assert store.get_edges_among(set()) == []
        store.close()

    def test_get_edges_among_large_batch(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        # Create enough nodes to test batching (>450)
        qns = set()
        for i in range(500):
            qn = f"/f.py::func_{i}"
            store.upsert_node(
                NodeInfo(
                    kind="Function",
                    name=f"func_{i}",
                    file_path="/f.py",
                    line_start=1,
                    line_end=5,
                    language="python",
                )
            )
            qns.add(qn)
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/f.py::func_0",
                target="/f.py::func_1",
                file_path="/f.py",
                line=1,
            )
        )
        store.commit()

        edges = store.get_edges_among(qns)
        assert len(edges) == 1
        store.close()

    def test_upsert_edge_updates_existing(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        eid1 = store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/a.py::x",
                target="/b.py::y",
                file_path="/a.py",
                line=5,
            )
        )
        store.commit()
        # Upsert same edge again
        eid2 = store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/a.py::x",
                target="/b.py::y",
                file_path="/a.py",
                line=5,
            )
        )
        store.commit()
        assert eid1 == eid2
        store.close()

    def test_search_edges_by_target_name(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/a.py::foo",
                target="helper",
                file_path="/a.py",
                line=10,
            )
        )
        store.commit()

        edges = store.search_edges_by_target_name("helper")
        assert len(edges) == 1
        assert edges[0].target_qualified == "helper"

        # Wrong kind should return empty
        edges2 = store.search_edges_by_target_name("helper", kind="IMPORTS_FROM")
        assert len(edges2) == 0
        store.close()

    def test_metadata_round_trip(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.set_metadata("test_key", "test_value")
        assert store.get_metadata("test_key") == "test_value"
        assert store.get_metadata("missing_key") is None
        store.close()

    def test_search_nodes_empty_query(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        assert store.search_nodes("") == []
        store.close()

    def test_search_nodes_with_kind(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="foo",
                file_path="/f.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Class",
                name="Foo",
                file_path="/f.py",
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.commit()

        results = store.search_nodes("foo", kind="Function")
        assert all(r.kind == "Function" for r in results)
        store.close()

    def test_store_file_nodes_edges_replaces(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="old_func",
                file_path="/f.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.commit()

        # Replace with new data
        store.store_file_nodes_edges(
            "/f.py",
            [
                NodeInfo(
                    kind="Function",
                    name="new_func",
                    file_path="/f.py",
                    line_start=1,
                    line_end=5,
                    language="python",
                )
            ],
            [],
        )

        nodes = store.get_nodes_by_file("/f.py")
        names = [n.name for n in nodes]
        assert "new_func" in names
        assert "old_func" not in names
        store.close()

    def test_node_extra_field(self, tmp_path):
        store = GraphStore(str(tmp_path / "t.db"))
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="/f.py",
                line_start=1,
                line_end=5,
                language="python",
                extra={"decorator": "@property"},
            )
        )
        store.commit()
        node = store.get_node("/f.py::f")
        assert node is not None
        assert node.extra == {"decorator": "@property"}
        store.close()
