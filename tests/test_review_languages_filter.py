"""Tests for D16 — `languages` filter on review/tests_for.

Per issue #340, the untested-function list over-reports on cross-language
repos (Python implementation + JS/TS tests) and integration-style coverage.
This module verifies a new ``languages`` parameter filters the untested list
to only the requested language(s).
"""

from __future__ import annotations

import pytest

from crg.graph import GraphStore
from crg.parser import EdgeInfo, NodeInfo
from crg.tools import get_review_context, query_graph


@pytest.fixture
def mixed_lang_repo(tmp_path, monkeypatch):
    """Repo with a Python function + a TSX function, both flagged as untested."""
    (tmp_path / ".git").mkdir()
    crg_dir = tmp_path / ".crg"
    crg_dir.mkdir()
    (crg_dir / ".gitignore").write_text("*\n")

    py_file = tmp_path / "service.py"
    py_file.write_text("def py_func():\n    return 1\n")

    ts_file = tmp_path / "Component.tsx"
    ts_file.write_text("export function tsxFunc(): number {\n  return 1;\n}\n")

    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))

    abs_py = str(py_file)
    abs_ts = str(ts_file)

    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_py,
            file_path=abs_py,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="py_func",
            file_path=abs_py,
            line_start=1,
            line_end=2,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_ts,
            file_path=abs_ts,
            line_start=1,
            line_end=3,
            language="typescript",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="tsxFunc",
            file_path=abs_ts,
            line_start=1,
            line_end=3,
            language="typescript",
        )
    )
    store.commit()
    store.close()

    # Stub git diff so review_context picks both files as "changed" without
    # actually creating a git commit history.
    from crg import tools as _tools

    def _fake_changed_files(root, base):
        return ["service.py", "Component.tsx"]

    def _fake_staged(root):
        return []

    monkeypatch.setattr(_tools, "get_changed_files", _fake_changed_files)
    monkeypatch.setattr(_tools, "get_staged_and_unstaged", _fake_staged)
    return tmp_path


class TestReviewLanguagesFilter:
    def test_no_languages_param_returns_both_languages(self, mixed_lang_repo):
        """Backward compat: review without languages includes all langs."""
        result = get_review_context(
            repo_root=str(mixed_lang_repo),
            include_source=False,
        )
        assert result["status"] == "ok"
        # New structured field: untested_functions list (was only text guidance)
        untested = result["context"].get("untested_functions", [])
        names = {fn["name"] for fn in untested}
        assert "py_func" in names
        assert "tsxFunc" in names

    def test_languages_python_only_excludes_typescript(self, mixed_lang_repo):
        """languages=['python'] filter excludes TSX from untested list."""
        result = get_review_context(
            repo_root=str(mixed_lang_repo),
            include_source=False,
            languages=["python"],
        )
        assert result["status"] == "ok"
        untested = result["context"].get("untested_functions", [])
        for fn in untested:
            assert fn["language"] == "python", f"Expected python only, got {fn}"
        names = {fn["name"] for fn in untested}
        assert "py_func" in names
        assert "tsxFunc" not in names

    def test_languages_typescript_only_excludes_python(self, mixed_lang_repo):
        result = get_review_context(
            repo_root=str(mixed_lang_repo),
            include_source=False,
            languages=["typescript"],
        )
        untested = result["context"].get("untested_functions", [])
        names = {fn["name"] for fn in untested}
        assert "tsxFunc" in names
        assert "py_func" not in names

    def test_languages_multi_python_typescript(self, mixed_lang_repo):
        result = get_review_context(
            repo_root=str(mixed_lang_repo),
            include_source=False,
            languages=["python", "typescript"],
        )
        untested = result["context"].get("untested_functions", [])
        names = {fn["name"] for fn in untested}
        assert "py_func" in names
        assert "tsxFunc" in names

    def test_languages_invalid_returns_error(self, mixed_lang_repo):
        """Invalid language values return status=error, do NOT raise."""
        result = get_review_context(
            repo_root=str(mixed_lang_repo),
            include_source=False,
            languages=["klingon"],
        )
        assert result["status"] == "error"
        assert "invalid_languages" in result.get("error", "")

    def test_languages_dart_is_accepted(self, mixed_lang_repo):
        """Dart is a parser language, so filtering by it is not an error."""
        result = get_review_context(
            repo_root=str(mixed_lang_repo),
            include_source=False,
            languages=["dart"],
        )
        assert result["status"] == "ok"
        assert result["context"].get("untested_functions", []) == []


class TestAllowedLanguagesMatchParser:
    def test_every_parser_language_is_accepted(self):
        """The filter accepts every language the parser stores on nodes."""
        from crg.parser import SUPPORTED_LANGUAGES
        from crg.tools import _validate_languages

        assert _validate_languages(sorted(SUPPORTED_LANGUAGES)) is None


class TestTestsForLanguagesFilter:
    def test_tests_for_no_languages_returns_all(self, tmp_path):
        """tests_for without languages returns all test nodes (existing behavior)."""
        (tmp_path / ".git").mkdir()
        crg_dir = tmp_path / ".crg"
        crg_dir.mkdir()

        impl_py = tmp_path / "impl.py"
        impl_py.write_text("def my_func():\n    return 1\n")
        test_py = tmp_path / "test_impl.py"
        test_py.write_text("def test_my_func():\n    pass\n")
        test_ts = tmp_path / "impl.test.ts"
        test_ts.write_text("test('my_func', () => {});\n")

        db_path = crg_dir / "graph.db"
        store = GraphStore(str(db_path))
        abs_impl = str(impl_py)
        abs_test_py = str(test_py)
        abs_test_ts = str(test_ts)

        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="my_func",
                file_path=abs_impl,
                line_start=1,
                line_end=2,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Test",
                name="test_my_func",
                file_path=abs_test_py,
                line_start=1,
                line_end=2,
                language="python",
                is_test=True,
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Test",
                name="test_my_func_ts",
                file_path=abs_test_ts,
                line_start=1,
                line_end=1,
                language="typescript",
                is_test=True,
            )
        )
        # Wire a TESTED_BY edge from impl to the python test
        store.upsert_edge(
            EdgeInfo(
                kind="TESTED_BY",
                source=f"{abs_test_py}::test_my_func",
                target=f"{abs_impl}::my_func",
                file_path=abs_test_py,
                line=1,
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="tests_for",
            target=f"{abs_impl}::my_func",
            repo_root=str(tmp_path),
        )
        assert result["status"] == "ok"
        langs = {r.get("language") for r in result["results"]}
        # Without filter, naming-convention search may pick up TS as well
        assert "python" in langs

    def test_tests_for_languages_python_filter(self, tmp_path):
        (tmp_path / ".git").mkdir()
        crg_dir = tmp_path / ".crg"
        crg_dir.mkdir()

        impl_py = tmp_path / "impl.py"
        impl_py.write_text("def my_func():\n    return 1\n")
        test_py = tmp_path / "test_impl.py"
        test_py.write_text("def test_my_func():\n    pass\n")
        test_ts = tmp_path / "impl.test.ts"
        test_ts.write_text("test('my_func', () => {});\n")

        db_path = crg_dir / "graph.db"
        store = GraphStore(str(db_path))
        abs_impl = str(impl_py)
        abs_test_py = str(test_py)
        abs_test_ts = str(test_ts)

        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="my_func",
                file_path=abs_impl,
                line_start=1,
                line_end=2,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Test",
                name="test_my_func",
                file_path=abs_test_py,
                line_start=1,
                line_end=2,
                language="python",
                is_test=True,
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Test",
                name="test_my_func",
                file_path=abs_test_ts,
                line_start=1,
                line_end=1,
                language="typescript",
                is_test=True,
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="TESTED_BY",
                source=f"{abs_test_py}::test_my_func",
                target=f"{abs_impl}::my_func",
                file_path=abs_test_py,
                line=1,
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="TESTED_BY",
                source=f"{abs_test_ts}::test_my_func",
                target=f"{abs_impl}::my_func",
                file_path=abs_test_ts,
                line=1,
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="tests_for",
            target=f"{abs_impl}::my_func",
            repo_root=str(tmp_path),
            languages=["python"],
        )
        assert result["status"] == "ok"
        for r in result["results"]:
            assert r.get("language") == "python"

    def test_tests_for_invalid_language_returns_error(self, tmp_path):
        (tmp_path / ".git").mkdir()
        crg_dir = tmp_path / ".crg"
        crg_dir.mkdir()
        db_path = crg_dir / "graph.db"
        store = GraphStore(str(db_path))
        store.commit()
        store.close()

        result = query_graph(
            pattern="tests_for",
            target="anything",
            repo_root=str(tmp_path),
            languages=["klingon"],
        )
        assert result["status"] == "error"
        assert "invalid_languages" in result.get("error", "")
