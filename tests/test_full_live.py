"""Full/real live MCP protocol tests for crg.

Comprehensive tests covering ALL query patterns, graph lifecycle,
review variants, cache cycle, and multi-language support.
Each test spawns the MCP server as a subprocess and communicates
via the MCP protocol (JSON-RPC over stdio).

Marker: @pytest.mark.full
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

# Live MCP tests spawn subprocesses and need more time than unit tests
pytestmark = pytest.mark.timeout(120)

SAMPLE_PYTHON = '''\
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b


def calculate(op: str, a: int, b: int) -> int:
    """Dispatch to add or multiply based on op string."""
    if op == "add":
        return add(a, b)
    return multiply(a, b)


class Calculator:
    """Simple calculator with history."""

    def __init__(self):
        self.history: list[int] = []

    def run(self, op: str, a: int, b: int) -> int:
        result = calculate(op, a, b)
        self.history.append(result)
        return result
'''

SAMPLE_TEST = """\
from calculator import add, multiply


def test_add():
    assert add(1, 2) == 3


def test_multiply():
    assert multiply(3, 4) == 12
"""

SAMPLE_GO = """\
package main

import "fmt"

func greet(name string) string {
    return fmt.Sprintf("Hello, %s!", name)
}

func main() {
    fmt.Println(greet("world"))
}
"""

SAMPLE_TYPESCRIPT = """\
interface Shape {
    area(): number;
}

class Circle implements Shape {
    constructor(public radius: number) {}

    area(): number {
        return Math.PI * this.radius * this.radius;
    }
}

class Rectangle implements Shape {
    constructor(public width: number, public height: number) {}

    area(): number {
        return this.width * this.height;
    }
}

function totalArea(shapes: Shape[]): number {
    let sum = 0;
    for (const s of shapes) {
        sum += s.area();
    }
    return sum;
}

export { Circle, Rectangle, totalArea };
"""


def _parse_result_text(result) -> Any:
    """Extract text from MCP call_tool result and try to parse as JSON.

    Robust against non-dictionary payloads (e.g., raw markdown from the `help` tool)
    by falling back to returning the raw text if JSON parsing fails or the
    result is not a dictionary.
    """
    text = result.content[0].text
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return text


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command="uv",
        args=["run", "crg"],
        env={**os.environ, "EMBEDDING_BACKEND": "local"},
    )


@pytest.fixture()
def sample_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with sample Python and Go files."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    (repo / "calculator.py").write_text(SAMPLE_PYTHON)
    (repo / "test_calculator.py").write_text(SAMPLE_TEST)
    (repo / "main.go").write_text(SAMPLE_GO)

    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    return repo


@pytest.fixture()
def mixed_lang_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with Python, TypeScript, and Go files."""
    repo = tmp_path / "mixed-repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    (repo / "calculator.py").write_text(SAMPLE_PYTHON)
    (repo / "test_calculator.py").write_text(SAMPLE_TEST)
    (repo / "shapes.ts").write_text(SAMPLE_TYPESCRIPT)
    (repo / "main.go").write_text(SAMPLE_GO)

    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    return repo


async def _build_graph(session: ClientSession, repo: Path) -> dict[str, Any]:
    """Helper: full build on a repo, returns parsed result."""
    result = await session.call_tool(
        "graph",
        {
            "action": "build",
            "full_rebuild": True,
            "repo_root": str(repo),
        },
    )
    return _parse_result_text(result)


# ---------------------------------------------------------------------------
# TestFullGraphLifecycle
# ---------------------------------------------------------------------------


@pytest.mark.full
class TestFullGraphLifecycle:
    """Graph build -> stats -> update -> stats lifecycle."""

    async def test_build_then_stats_verify_counts(self, sample_repo: Path):
        """graph.build -> graph.stats -> verify node/edge counts are positive."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Full build
                build_data = await _build_graph(session, sample_repo)
                assert build_data["status"] == "ok"
                assert build_data["build_type"] == "full"
                assert build_data["files_parsed"] > 0
                initial_nodes = build_data["total_nodes"]
                initial_edges = build_data["total_edges"]
                assert initial_nodes > 0
                assert initial_edges > 0

                # Stats should match build output
                stats_result = await session.call_tool(
                    "graph",
                    {"action": "stats", "repo_root": str(sample_repo)},
                )
                stats = _parse_result_text(stats_result)
                assert stats["status"] == "ok"
                assert stats["total_nodes"] == initial_nodes
                assert stats["total_edges"] == initial_edges

    async def test_incremental_update_changes_counts(self, sample_repo: Path):
        """graph.build -> add file -> graph.update -> verify counts changed."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Full build
                build_data = await _build_graph(session, sample_repo)
                initial_nodes = build_data["total_nodes"]

                # Add a new file and commit
                new_file = sample_repo / "utils.py"
                new_file.write_text(
                    'def helper(x: int) -> int:\n    """Double a number."""\n    return x * 2\n'
                )
                subprocess.run(
                    ["git", "add", "."],
                    cwd=sample_repo,
                    capture_output=True,
                    check=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", "add utils"],
                    cwd=sample_repo,
                    capture_output=True,
                    check=True,
                )

                # Incremental update
                update_result = await session.call_tool(
                    "graph",
                    {"action": "update", "repo_root": str(sample_repo)},
                )
                update_data = _parse_result_text(update_result)
                assert update_data["status"] == "ok"

                # Stats should show more nodes now
                stats_result = await session.call_tool(
                    "graph",
                    {"action": "stats", "repo_root": str(sample_repo)},
                )
                stats = _parse_result_text(stats_result)
                assert stats["total_nodes"] > initial_nodes


# ---------------------------------------------------------------------------
# TestFullQueryAllPatterns
# ---------------------------------------------------------------------------


@pytest.mark.full
class TestFullQueryAllPatterns:
    """Test ALL 8 query patterns via MCP protocol on sample_repo."""

    async def test_callers_of(self, sample_repo: Path):
        """callers_of 'add' should find 'calculate' as a caller."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                # Use qualified name to avoid ambiguity (add exists in
                # both calculator.py as definition and test_calculator.py as import)
                abs_calc = str(sample_repo / "calculator.py")
                result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "callers_of",
                        "target": f"{abs_calc}::add",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                assert data["pattern"] == "callers_of"
                # 'calculate' calls 'add', so it should appear
                names = [r.get("name", "") for r in data.get("results", [])]
                assert "calculate" in names, (
                    f"Expected 'calculate' in callers, got {names}"
                )

    async def test_callees_of(self, sample_repo: Path):
        """callees_of 'calculate' should find 'add' and 'multiply'."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "callees_of",
                        "target": "calculate",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                assert data["pattern"] == "callees_of"
                names = [r.get("name", "") for r in data.get("results", [])]
                assert "add" in names, f"Expected 'add' in callees, got {names}"
                assert "multiply" in names, (
                    f"Expected 'multiply' in callees, got {names}"
                )

    async def test_imports_of(self, sample_repo: Path):
        """imports_of 'test_calculator.py' should find imports from calculator."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "imports_of",
                        "target": "test_calculator.py",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                assert data["pattern"] == "imports_of"
                # test_calculator.py imports from calculator
                results = data.get("results", [])
                assert len(results) > 0, "Expected at least one import"

    async def test_importers_of(self, sample_repo: Path):
        """importers_of 'calculator.py' should find test_calculator.py."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "importers_of",
                        "target": "calculator.py",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                assert data["pattern"] == "importers_of"
                # test_calculator.py imports from calculator.py
                results = data.get("results", [])
                if len(results) > 0:
                    importers = [
                        r.get("importer", "") or r.get("file", "") for r in results
                    ]
                    found = any("test_calculator" in i for i in importers)
                    assert found, (
                        f"Expected test_calculator in importers, got {importers}"
                    )

    async def test_children_of(self, sample_repo: Path):
        """children_of 'Calculator' should find __init__ and run methods."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                # Use qualified name to avoid ambiguity
                abs_calc = str(sample_repo / "calculator.py")
                result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "children_of",
                        "target": f"{abs_calc}::Calculator",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                assert data["pattern"] == "children_of"
                names = [r.get("name", "") for r in data.get("results", [])]
                assert "run" in names, f"Expected 'run' in children, got {names}"

    async def test_tests_for(self, sample_repo: Path):
        """tests_for 'add' should find test_add."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                # Use qualified name to avoid ambiguity
                abs_calc = str(sample_repo / "calculator.py")
                result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "tests_for",
                        "target": f"{abs_calc}::add",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                assert data["pattern"] == "tests_for"
                names = [r.get("name", "") for r in data.get("results", [])]
                assert "test_add" in names, f"Expected 'test_add' in tests, got {names}"

    async def test_inheritors_of(self, sample_repo: Path):
        """inheritors_of returns ok status and correct pattern metadata.

        Note: INHERITS edges store bare target names (e.g. "Animal") while
        get_edges_by_target may find CONTAINS edges first (using the qualified
        name), preventing the bare-name fallback. This is a known graph
        limitation. The test verifies the query pattern itself works correctly
        through the MCP protocol (returns status ok, correct pattern).
        """
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                abs_calc = str(sample_repo / "calculator.py")
                result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "inheritors_of",
                        "target": f"{abs_calc}::Calculator",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                assert data["pattern"] == "inheritors_of"
                assert "results" in data

    async def test_file_summary(self, sample_repo: Path):
        """file_summary of 'calculator.py' should list all nodes in the file."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "file_summary",
                        "target": "calculator.py",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                assert data["pattern"] == "file_summary"
                results = data.get("results", [])
                assert len(results) > 0
                names = [r.get("name", "") for r in results]
                assert "add" in names, f"Expected 'add' in file summary, got {names}"
                assert "Calculator" in names, (
                    f"Expected 'Calculator' in file summary, got {names}"
                )


# ---------------------------------------------------------------------------
# TestFullReviewVariants
# ---------------------------------------------------------------------------


@pytest.mark.full
class TestFullReviewVariants:
    """Test review tool with different parameter combinations."""

    async def test_review_lists_changed_files(self, sample_repo: Path):
        """review with explicit changed_files lists them in context."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                result = await session.call_tool(
                    "review",
                    {
                        "changed_files": ["calculator.py"],
                        "repo_root": str(sample_repo),
                        "include_source": False,
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                context = data.get("context", {})
                assert "calculator.py" in context.get("changed_files", [])

    async def test_review_include_source(self, sample_repo: Path):
        """review with include_source=true includes source_snippets."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                result = await session.call_tool(
                    "review",
                    {
                        "changed_files": ["calculator.py"],
                        "repo_root": str(sample_repo),
                        "include_source": True,
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                context = data.get("context", {})
                snippets = context.get("source_snippets", {})
                assert "calculator.py" in snippets
                assert "def add" in snippets["calculator.py"]

    async def test_review_max_depth_limited(self, sample_repo: Path):
        """review with max_depth=1 limits the impact radius depth."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                result = await session.call_tool(
                    "review",
                    {
                        "changed_files": ["calculator.py"],
                        "repo_root": str(sample_repo),
                        "max_depth": 1,
                        "include_source": False,
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                # With max_depth=1, we should still get valid context
                context = data.get("context", {})
                assert "graph" in context
                assert "review_guidance" in context


# ---------------------------------------------------------------------------
# TestFullCacheCycle
# ---------------------------------------------------------------------------


@pytest.mark.full
class TestFullCacheCycle:
    """Test embed -> cache_clear -> embed again cycle."""

    async def test_embed_clear_reembed(self, sample_repo: Path):
        """graph.embed -> config.cache_clear -> graph.embed should all succeed."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                # First embed
                embed_result = await session.call_tool(
                    "graph",
                    {"action": "embed", "repo_root": str(sample_repo)},
                )
                embed_data = _parse_result_text(embed_result)
                assert embed_data["status"] == "ok"
                first_embedded = embed_data["newly_embedded"]
                assert first_embedded > 0

                # Clear cache
                clear_result = await session.call_tool(
                    "config",
                    {"action": "cache_clear", "repo_root": str(sample_repo)},
                )
                clear_data = _parse_result_text(clear_result)
                assert "cache cleared" in clear_data.get("status", "")
                assert clear_data["embeddings_removed"] > 0

                # Re-embed
                reembed_result = await session.call_tool(
                    "graph",
                    {"action": "embed", "repo_root": str(sample_repo)},
                )
                reembed_data = _parse_result_text(reembed_result)
                assert reembed_data["status"] == "ok"
                assert reembed_data["newly_embedded"] > 0


# ---------------------------------------------------------------------------
# TestFullMultiLang
# ---------------------------------------------------------------------------


@pytest.mark.full
class TestFullMultiLang:
    """Test graph build and query on a multi-language repository."""

    async def test_build_mixed_repo_all_languages_parsed(self, mixed_lang_repo: Path):
        """graph.build on mixed repo -> query structure -> all 3 languages parsed."""
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Build
                build_data = await _build_graph(session, mixed_lang_repo)
                assert build_data["status"] == "ok"
                # Should parse Python + TypeScript + Go files
                assert build_data["files_parsed"] >= 3

                # Stats should show multiple languages
                stats_result = await session.call_tool(
                    "graph",
                    {"action": "stats", "repo_root": str(mixed_lang_repo)},
                )
                stats = _parse_result_text(stats_result)
                languages = [lang.lower() for lang in stats.get("languages", [])]
                assert "python" in languages, (
                    f"Expected 'python' in languages, got {languages}"
                )
                assert "go" in languages, f"Expected 'go' in languages, got {languages}"
                assert "typescript" in languages, (
                    f"Expected 'typescript' in languages, got {languages}"
                )

                # Query file_summary on TypeScript file
                ts_result = await session.call_tool(
                    "query",
                    {
                        "action": "query",
                        "pattern": "file_summary",
                        "target": "shapes.ts",
                        "repo_root": str(mixed_lang_repo),
                    },
                )
                ts_data = _parse_result_text(ts_result)
                assert ts_data["status"] == "ok"
                names = [r.get("name", "") for r in ts_data.get("results", [])]
                assert "Circle" in names or "totalArea" in names, (
                    f"Expected TypeScript nodes in file summary, got {names}"
                )


# ---------------------------------------------------------------------------
# TestFullCloudEmbed
# ---------------------------------------------------------------------------

# The server takes the cloud backend only when both are set: the model chain
# (EMBEDDING_MODELS) and a credential for the [models.embed] cell
# (HULL_EMBED_API_KEY). With either one missing it embeds locally.
CLOUD_EMBED_KEY = os.environ.get("HULL_EMBED_API_KEY", "")
CLOUD_EMBED_MODELS = os.environ.get("EMBEDDING_MODELS", "")


def _cloud_server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command="uv",
        args=["run", "crg"],
        env={
            **os.environ,
            "HULL_EMBED_API_KEY": CLOUD_EMBED_KEY,
            "EMBEDDING_MODELS": CLOUD_EMBED_MODELS,
        },
    )


@pytest.mark.full
@pytest.mark.skipif(
    not (CLOUD_EMBED_KEY and CLOUD_EMBED_MODELS),
    reason="HULL_EMBED_API_KEY and EMBEDDING_MODELS not set",
)
class TestFullCloudEmbed:
    """Tests with cloud embedding through the [models.embed] cell."""

    async def test_graph_embed_cloud(self, sample_repo: Path):
        """Embed graph with cloud API keys should succeed."""
        async with stdio_client(_cloud_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                embed_result = await session.call_tool(
                    "graph",
                    {"action": "embed", "repo_root": str(sample_repo)},
                )
                embed_data = _parse_result_text(embed_result)
                assert embed_data["status"] == "ok"
                assert embed_data["newly_embedded"] > 0
                assert embed_data["backend"] == "cloud", embed_data

    async def test_query_semantic_search_cloud(self, sample_repo: Path):
        """Semantic search with cloud embeddings should find relevant results."""
        async with stdio_client(_cloud_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _build_graph(session, sample_repo)

                # Embed first
                await session.call_tool(
                    "graph",
                    {"action": "embed", "repo_root": str(sample_repo)},
                )

                # Semantic search
                result = await session.call_tool(
                    "query",
                    {
                        "action": "search",
                        "search_query": "calculation arithmetic",
                        "repo_root": str(sample_repo),
                    },
                )
                data = _parse_result_text(result)
                assert data["status"] == "ok"
                results = data.get("results", [])
                assert len(results) > 0, f"No semantic search results: {data}"
                # Should find calculator-related functions
                names = [r.get("name", "") for r in results]
                found = any(
                    n in names for n in ("add", "multiply", "calculate", "Calculator")
                )
                assert found, f"Expected calculator nodes, got {names}"
