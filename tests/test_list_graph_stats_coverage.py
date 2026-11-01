import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to sys.path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Surgical mocking only during import to avoid poisoning CI environment
modules_to_mock = [
    "networkx",
    "tree_sitter",
    "tree_sitter_language_pack",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "mcp",
    "mcp.server",
    "mcp.server.fastmcp",
    "fastmcp",
    "fastretrieval",
    "cohere",
    "google.genai",
    "openai",
    "httpx",
    "pydantic_settings",
    "n24q02m_mcp_core",
    "n24q02m_mcp_core.storage",
    "n24q02m_mcp_core.storage.per_plugin_store",
    "pygments",
    "pygments.lexers",
    "pygments.formatters",
    "alembic",
    "alembic.config",
    "alembic.command",
]


class MockModule(MagicMock):
    def __getattr__(self, name):
        return MagicMock()


def _get_tools_module():
    # Mock only the missing ones
    mocks = {}
    for mod in modules_to_mock:
        if mod not in sys.modules:
            mocks[mod] = MockModule()

    with patch.dict(sys.modules, mocks):
        import crg.tools as tools_mod
        from crg.graph import GraphStats as stats_class

        return tools_mod, stats_class


tools, GraphStats = _get_tools_module()


def test_list_graph_stats_populated():
    with (
        patch.object(tools, "_get_store") as mock_get_store,
        patch.object(tools, "init_backend"),
        patch.object(tools, "EmbeddingStore") as mock_emb_store_class,
        patch.object(tools, "get_db_path") as mock_get_db_path,
        patch.object(tools, "resolve_backend") as mock_resolve_backend,
    ):
        # Setup mock store
        mock_store = MagicMock()
        mock_root = MagicMock()
        mock_root.name = "test-repo"
        mock_get_store.return_value = (mock_store, mock_root)

        # Setup mock stats
        stats = GraphStats(
            total_nodes=100,
            total_edges=200,
            nodes_by_kind={"Function": 60, "Class": 40},
            edges_by_kind={"CALLS": 150, "CONTAINS": 50},
            languages=["python", "typescript"],
            files_count=10,
            last_updated="2023-10-27T10:00:00",
        )
        mock_store.get_stats.return_value = stats

        # Setup mock embedding store
        mock_emb_store = MagicMock()
        mock_emb_store.count.return_value = 50
        mock_emb_store_class.return_value = mock_emb_store

        mock_resolve_backend.return_value = "local"
        mock_get_db_path.return_value = Path("/tmp/fake.db")

        result = tools.list_graph_stats("/fake/repo")

        assert result["status"] == "ok"
        assert result["total_nodes"] == 100
        assert result["embeddings_count"] == 50
        assert "Graph statistics for test-repo:" in result["summary"]
        assert "python, typescript" in result["summary"]
        assert "2023-10-27T10:00:00" in result["summary"]
        assert "Function: 60" in result["summary"]
        assert "CALLS: 150" in result["summary"]
        assert "Embeddings: 50 nodes embedded (backend: local)" in result["summary"]

        mock_store.close.assert_called_once()
        mock_emb_store.close.assert_called_once()


def test_list_graph_stats_empty():
    with (
        patch.object(tools, "_get_store") as mock_get_store,
        patch.object(tools, "init_backend"),
        patch.object(tools, "EmbeddingStore") as mock_emb_store_class,
        patch.object(tools, "get_db_path") as mock_get_db_path,
        patch.object(tools, "resolve_backend") as mock_resolve_backend,
    ):
        # Setup mock store
        mock_store = MagicMock()
        mock_root = MagicMock()
        mock_root.name = "empty-repo"
        mock_get_store.return_value = (mock_store, mock_root)

        # Setup mock stats
        stats = GraphStats(
            total_nodes=0,
            total_edges=0,
            nodes_by_kind={},
            edges_by_kind={},
            languages=[],
            files_count=0,
            last_updated=None,
        )
        mock_store.get_stats.return_value = stats

        # Setup mock embedding store
        mock_emb_store = MagicMock()
        mock_emb_store.count.return_value = 0
        mock_emb_store_class.return_value = mock_emb_store

        mock_resolve_backend.return_value = "cloud"
        mock_get_db_path.return_value = Path("/tmp/fake.db")

        result = tools.list_graph_stats(None)

        assert result["status"] == "ok"
        assert "Languages: none" in result["summary"]
        assert "Last updated: never" in result["summary"]
        assert "Embeddings: 0 nodes embedded (backend: cloud)" in result["summary"]


if __name__ == "__main__":
    try:
        test_list_graph_stats_populated()
        test_list_graph_stats_empty()
        print("All isolated tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
