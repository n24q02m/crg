"""Tests for the incremental graph update module."""

import subprocess
from unittest.mock import MagicMock, patch

from crg.graph import GraphStore
from crg.incremental import (
    _is_binary,
    _load_ignore_patterns,
    _should_ignore,
    find_project_root,
    find_repo_root,
    full_build,
    get_all_tracked_files,
    get_changed_files,
    get_db_path,
    get_head_sha,
    get_staged_and_unstaged,
    incremental_update,
    incremental_update_from_hook,
)


class TestFindRepoRoot:
    def test_finds_git_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert find_repo_root(tmp_path) == tmp_path

    def test_finds_parent_git_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        assert find_repo_root(sub) == tmp_path

    def test_returns_none_without_git(self, tmp_path):
        sub = tmp_path / "no_git"
        sub.mkdir()
        assert find_repo_root(sub) is None


class TestFindProjectRoot:
    def test_returns_git_root(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert find_project_root(tmp_path) == tmp_path

    def test_falls_back_to_start(self, tmp_path):
        sub = tmp_path / "no_git"
        sub.mkdir()
        assert find_project_root(sub) == sub


class TestGetDbPath:
    def test_creates_directory_and_db_path(self, tmp_path):
        db_path = get_db_path(tmp_path)
        assert db_path == tmp_path / ".crg" / "graph.db"
        assert (tmp_path / ".crg").is_dir()

    def test_creates_gitignore(self, tmp_path):
        get_db_path(tmp_path)
        gi = tmp_path / ".crg" / ".gitignore"
        assert gi.exists()
        assert "*\n" in gi.read_text()

    def test_does_not_adopt_or_modify_another_packages_database(self, tmp_path):
        shared = tmp_path / ".code-review-graph"
        shared.mkdir()
        old_paths = [
            shared / "graph.db",
            shared / "graph.db-wal",
            tmp_path / ".code-review-graph.db",
            tmp_path / ".code-review-graph.db-wal",
            tmp_path / ".code-review-graph.db-shm",
        ]
        for old_path in old_paths:
            old_path.write_bytes(b"owned by another package")

        db_path = get_db_path(tmp_path)

        assert db_path == tmp_path / ".crg" / "graph.db"
        assert not db_path.exists()
        for old_path in old_paths:
            assert old_path.read_bytes() == b"owned by another package"


class TestIgnorePatterns:
    def test_default_patterns_loaded(self, tmp_path):
        patterns = _load_ignore_patterns(tmp_path)
        assert "node_modules/**" in patterns
        assert ".git/**" in patterns
        assert "__pycache__/**" in patterns

    def test_custom_ignore_file(self, tmp_path):
        ignore = tmp_path / ".code-review-graphignore"
        ignore.write_text("custom/**\n# comment\n\nvendor/**\n")
        patterns = _load_ignore_patterns(tmp_path)
        assert "custom/**" in patterns
        assert "vendor/**" in patterns
        # Comments and blanks should be skipped
        assert "# comment" not in patterns
        assert "" not in patterns

    def test_should_ignore_matches(self):
        patterns = ["node_modules/**", "*.pyc", ".git/**"]
        assert _should_ignore("node_modules/foo/bar.js", patterns)
        assert _should_ignore("test.pyc", patterns)
        assert _should_ignore(".git/HEAD", patterns)
        assert not _should_ignore("src/main.py", patterns)


class TestIsBinary:
    def test_text_file_is_not_binary(self, tmp_path):
        f = tmp_path / "text.py"
        f.write_text("print('hello')\n")
        assert not _is_binary(f)

    def test_binary_file_is_binary(self, tmp_path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"header\x00binary data")
        assert _is_binary(f)

    def test_missing_file_is_binary(self, tmp_path):
        f = tmp_path / "missing.txt"
        assert _is_binary(f)

    def test_is_binary_permission_error(self, tmp_path):
        f = tmp_path / "protected.txt"
        f.write_text("secret")
        with patch("pathlib.Path.read_bytes", side_effect=PermissionError):
            assert _is_binary(f)

    def test_is_binary_os_error(self, tmp_path):
        f = tmp_path / "broken.txt"
        f.write_text("data")
        with patch("pathlib.Path.read_bytes", side_effect=OSError):
            assert _is_binary(f)


class TestGitOperations:
    @patch("crg.incremental.shutil.which", return_value="git")
    @patch("crg.incremental.subprocess.run")
    def test_get_changed_files(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/a.py\nsrc/b.py\n",
        )
        result = get_changed_files(tmp_path)
        assert result == ["src/a.py", "src/b.py"]
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert any("git" in arg for arg in call_args[0][0])
        assert call_args[1].get("timeout") == 30

    @patch("crg.incremental.shutil.which", return_value="git")
    @patch("crg.incremental.subprocess.run")
    def test_get_changed_files_fallback(self, mock_run, mock_which, tmp_path):
        # First call fails, second succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout=""),
            MagicMock(returncode=0, stdout="staged.py\n"),
        ]
        result = get_changed_files(tmp_path)
        assert result == ["staged.py"]
        assert mock_run.call_count == 2

    @patch("crg.incremental.shutil.which", return_value="git")
    @patch("crg.incremental.subprocess.run")
    def test_get_changed_files_timeout(self, mock_run, mock_which, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 30)
        result = get_changed_files(tmp_path)
        assert result == []

    @patch("crg.incremental.shutil.which", return_value="git")
    @patch("crg.incremental.subprocess.run")
    def test_get_staged_and_unstaged(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M src/a.py\n?? new.py\nR  old.py -> new_name.py\n",
        )
        result = get_staged_and_unstaged(tmp_path)
        assert "src/a.py" in result
        assert "new.py" in result
        assert "new_name.py" in result
        # old.py should NOT be in results (renamed away)
        assert "old.py" not in result

    @patch("crg.incremental.shutil.which", return_value="git")
    @patch("crg.incremental.subprocess.run")
    def test_get_all_tracked_files(self, mock_run, mock_which, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="a.py\nb.py\nc.go\n",
        )
        result = get_all_tracked_files(tmp_path)
        assert result == ["a.py", "b.py", "c.go"]

    @patch("crg.incremental.shutil.which", return_value="git")
    @patch("crg.incremental.subprocess.run")
    def test_git_calls_detach_stdin(self, mock_run, mock_which, tmp_path):
        """Every git subprocess passes stdin=DEVNULL so an inherited stdio pipe
        cannot stall the output reader inside the MCP worker thread on Windows."""
        # Text-mode calls get str output, the others bytes, as from git itself.
        mock_run.side_effect = lambda *_a, **kw: MagicMock(
            returncode=0,
            stdout="" if kw.get("text") else b"",
            stderr="" if kw.get("text") else b"",
        )
        for invoke in (
            lambda: get_changed_files(tmp_path),
            lambda: get_staged_and_unstaged(tmp_path),
            lambda: get_all_tracked_files(tmp_path),
            lambda: get_head_sha(tmp_path),
        ):
            mock_run.reset_mock()
            invoke()
            assert mock_run.call_args.kwargs.get("stdin") is subprocess.DEVNULL, (
                f"git call is missing stdin=DEVNULL: {mock_run.call_args}"
            )


class TestFullBuild:
    def test_full_build_parses_files(self, tmp_path):
        # Create a simple Python file
        py_file = tmp_path / "sample.py"
        py_file.write_text("def hello():\n    pass\n")
        (tmp_path / ".git").mkdir()

        db_path = tmp_path / "test.db"
        store = GraphStore(db_path)
        try:
            mock_target = "crg.incremental.get_all_tracked_files"
            with patch(mock_target, return_value=["sample.py"]):
                result = full_build(tmp_path, store)
            assert result["files_parsed"] == 1
            assert result["total_nodes"] > 0
            assert result["errors"] == []
            assert store.get_metadata("last_build_type") == "full"
        finally:
            store.close()


class TestIncrementalUpdate:
    def test_incremental_with_no_changes(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = GraphStore(db_path)
        try:
            result = incremental_update(tmp_path, store, changed_files=[])
            assert result["files_updated"] == 0
        finally:
            store.close()

    def test_incremental_with_changed_file(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text("def greet():\n    return 'hi'\n")

        db_path = tmp_path / "test.db"
        store = GraphStore(db_path)
        try:
            result = incremental_update(tmp_path, store, changed_files=["mod.py"])
            assert result["files_updated"] >= 1
            assert result["total_nodes"] > 0
        finally:
            store.close()

    def test_incremental_deleted_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = GraphStore(db_path)
        try:
            # Pre-populate with a file
            py_file = tmp_path / "old.py"
            py_file.write_text("x = 1\n")
            result = incremental_update(tmp_path, store, changed_files=["old.py"])
            assert result["total_nodes"] > 0

            # Now delete the file and run incremental
            py_file.unlink()
            incremental_update(tmp_path, store, changed_files=["old.py"])
            # File should have been removed from graph
            nodes = store.get_nodes_by_file(str(tmp_path / "old.py"))
            assert len(nodes) == 0
        finally:
            store.close()


class TestIncrementalUpdateFromHook:
    def test_no_repo_returns_silently(self, tmp_path, monkeypatch):
        """Hook entry point should return silently when no git repo found."""
        monkeypatch.chdir(tmp_path)
        incremental_update_from_hook()  # Should not raise

    def test_with_repo(self, tmp_path, monkeypatch):
        """Hook entry point runs incremental update in a git repo."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "sample.py").write_text("def foo(): pass\n")
        subprocess.run(
            ["git", "add", "."], cwd=tmp_path, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        monkeypatch.chdir(tmp_path)
        incremental_update_from_hook()  # Should not raise
        # Verify graph was created
        db_path = tmp_path / ".crg" / "graph.db"
        assert db_path.exists()


# ---------------------------------------------------------------------------
# Phase 2 Task 9: incremental_update refreshes repos.last_indexed_sha
# ---------------------------------------------------------------------------


class TestIncrementalUpdateRefreshesLastIndexedSha:
    def _git_init_with_commit(self, repo_root):
        """Init a git repo with one committed file and return the HEAD SHA."""
        subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
        (repo_root / "sample.py").write_text("def foo():\n    pass\n")
        subprocess.run(
            ["git", "add", "."], cwd=repo_root, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return head.stdout.strip()

    def test_refreshes_last_indexed_sha_in_git_repo(self, tmp_path):
        """When repo_registry is provided + git is available, write HEAD SHA."""
        from crg.federation import RepoRegistry

        head_sha = self._git_init_with_commit(tmp_path)

        db_path = tmp_path / "graph.db"
        store = GraphStore(db_path)
        try:
            registry = RepoRegistry(store)
            rid = registry.add(tmp_path)

            incremental_update(
                tmp_path,
                store,
                changed_files=["sample.py"],
                repo_registry=registry,
            )

            row = store._conn.execute(
                "SELECT last_indexed_sha FROM repos WHERE repo_id = ?", (rid,)
            ).fetchone()
            assert row is not None
            assert row["last_indexed_sha"] == head_sha
        finally:
            store.close()

    def test_skips_sha_refresh_when_no_registry(self, tmp_path):
        """Without a repo_registry, last_indexed_sha is left unchanged."""
        # Plain incremental_update (existing callers) is unaffected.
        py_file = tmp_path / "mod.py"
        py_file.write_text("def greet():\n    return 'hi'\n")

        db_path = tmp_path / "graph.db"
        store = GraphStore(db_path)
        try:
            result = incremental_update(tmp_path, store, changed_files=["mod.py"])
            assert result["files_updated"] >= 1
        finally:
            store.close()

    def test_skips_sha_refresh_without_git(self, tmp_path):
        """Non-git directory: no SHA available, last_indexed_sha stays None."""
        from crg.federation import RepoRegistry

        # NOTE: tmp_path has NO .git directory.
        py_file = tmp_path / "mod.py"
        py_file.write_text("def greet():\n    return 'hi'\n")

        db_path = tmp_path / "graph.db"
        store = GraphStore(db_path)
        try:
            registry = RepoRegistry(store)
            rid = registry.add(tmp_path)

            # Should not raise even though git is unavailable.
            incremental_update(
                tmp_path,
                store,
                changed_files=["mod.py"],
                repo_registry=registry,
            )

            row = store._conn.execute(
                "SELECT last_indexed_sha FROM repos WHERE repo_id = ?", (rid,)
            ).fetchone()
            assert row is not None
            assert row["last_indexed_sha"] is None
        finally:
            store.close()

    def test_no_changes_path_still_refreshes_sha_with_registry(self, tmp_path):
        """Even on the early-return ``no changes`` path, SHA is refreshed."""
        from crg.federation import RepoRegistry

        head_sha = self._git_init_with_commit(tmp_path)

        db_path = tmp_path / "graph.db"
        store = GraphStore(db_path)
        try:
            registry = RepoRegistry(store)
            rid = registry.add(tmp_path)

            # Pass an empty changed_files list -> the function returns
            # early. With a registry wired in, last_indexed_sha should
            # still be bumped to HEAD.
            result = incremental_update(
                tmp_path,
                store,
                changed_files=[],
                repo_registry=registry,
            )
            assert result["files_updated"] == 0

            row = store._conn.execute(
                "SELECT last_indexed_sha FROM repos WHERE repo_id = ?", (rid,)
            ).fetchone()
            assert row is not None
            assert row["last_indexed_sha"] == head_sha
        finally:
            store.close()

    def test_no_changes_path_skips_sha_refresh_when_repo_not_registered(self, tmp_path):
        """Early-return path with registry but unregistered root: silent skip."""
        from crg.federation import RepoRegistry

        self._git_init_with_commit(tmp_path)

        # Build a registry that is NOT pointed at tmp_path.
        elsewhere = tmp_path.parent / (tmp_path.name + "-other")
        elsewhere.mkdir(exist_ok=True)

        db_path = tmp_path / "graph.db"
        store = GraphStore(db_path)
        try:
            registry = RepoRegistry(store)
            registry.add(elsewhere)

            # Should not raise — registry.assign(tmp_path) yields ValueError
            # which the helper swallows.
            result = incremental_update(
                tmp_path,
                store,
                changed_files=[],
                repo_registry=registry,
            )
            assert result["files_updated"] == 0
        finally:
            store.close()


class TestPhpCallResolution:
    def test_cross_file_aliases_and_same_class_calls_survive_reopen(self, tmp_path):
        definitions = tmp_path / "definitions.php"
        definitions.write_text(
            "<?php\nnamespace Library;\n"
            "class Worker { public static function commit() {} }\n"
            "function save() {}\n"
        )
        caller = tmp_path / "caller.php"
        caller.write_text(
            "<?php\nnamespace App;\n"
            "use Library\\Worker as W;\n"
            "use function Library\\save as persist;\n"
            "class Service {\n"
            " public function local() {}\n"
            " public function run($unknown) {\n"
            "  $this->local();\n"
            "  self::local();\n"
            "  W::commit();\n"
            "  persist();\n"
            "  $unknown->commit();\n"
            "  $unknown?->commit();\n"
            " }\n}\n"
        )
        db_path = get_db_path(tmp_path)
        store = GraphStore(db_path)
        try:
            result = full_build(tmp_path, store)
            assert result["errors"] == []
            assert result["php_calls"] == {"total": 6, "resolved": 4, "unresolved": 2}
        finally:
            store.close()

        store = GraphStore(db_path)
        try:
            calls = store.get_edges_by_source(f"{caller}::Service.run", kind="CALLS")
            targets = [edge.target_qualified for edge in calls]
            assert targets.count(f"{caller}::Service.local") == 2
            assert targets.count(f"{definitions}::Worker.commit") == 1
            assert targets.count(f"{definitions}::save") == 1
            assert targets.count("commit") == 2
        finally:
            store.close()

    def test_php_cross_file_impact_and_legacy_state_isolation(self, tmp_path):
        """Issue #1006: PHP CALLS resolve and old upstream state survives."""
        definitions = tmp_path / "src" / "Repository"
        controllers = tmp_path / "src" / "Controller"
        definitions.mkdir(parents=True)
        controllers.mkdir()
        legacy_db = tmp_path / ".code-review-graph" / "graph.db"
        legacy_db.parent.mkdir()
        legacy_db.write_bytes(b"upstream-state")
        definition = definitions / "UserRepository.php"
        definition.write_text(
            "<?php namespace App\\Repository; "
            "class UserRepository { public static function find() {} }"
        )
        caller = controllers / "UserController.php"
        caller.write_text(
            "<?php namespace App\\Controller; "
            "use App\\Repository\\UserRepository; "
            "class UserController { "
            "public function index() { UserRepository::find(); } }"
        )

        store = GraphStore(get_db_path(tmp_path))
        try:
            result = full_build(tmp_path, store)
            calls = store.get_all_edges()
            php_calls = [
                edge
                for edge in calls
                if edge.kind == "CALLS"
                and edge.source_qualified.endswith("UserController.index")
            ]
            assert result["php_calls"] == {"total": 1, "resolved": 1, "unresolved": 0}
            assert len(php_calls) == 1
            assert php_calls[0].target_qualified.endswith("UserRepository.find")
        finally:
            store.close()

        from crg.tools import get_impact_radius

        impact = get_impact_radius(
            changed_files=[str(caller)], repo_root=str(tmp_path), max_depth=2
        )
        assert any(
            path.endswith("UserRepository.php") for path in impact["impacted_files"]
        )
        assert legacy_db.read_bytes() == b"upstream-state"

    def test_incremental_ambiguity_invalidates_then_restores_binding(self, tmp_path):
        definition = tmp_path / "worker.php"
        definition.write_text(
            "<?php namespace Library; class Worker { public static function commit() {} }"
        )
        caller = tmp_path / "caller.php"
        caller.write_text(
            "<?php namespace App; use Library\\Worker; "
            "function run() { Worker::commit(); }"
        )
        duplicate = tmp_path / "duplicate.php"
        store = GraphStore(get_db_path(tmp_path))
        try:
            full_build(tmp_path, store)
            source = f"{caller}::run"
            assert store.get_edges_by_source(source, kind="CALLS")[
                0
            ].target_qualified == (f"{definition}::Worker.commit")
            duplicate.write_text(definition.read_text())
            result = incremental_update(
                tmp_path, store, changed_files=["duplicate.php"]
            )
            assert result["php_calls"]["unresolved"] == 1
            assert (
                store.get_edges_by_source(source, kind="CALLS")[0].target_qualified
                == "commit"
            )

            duplicate.unlink()
            result = incremental_update(
                tmp_path, store, changed_files=["duplicate.php"]
            )
            assert result["php_calls"]["resolved"] == 1
            assert store.get_edges_by_source(source, kind="CALLS")[
                0
            ].target_qualified == (f"{definition}::Worker.commit")
        finally:
            store.close()

    def test_php_symbols_remain_repo_scoped_after_incremental_update(self, tmp_path):
        from crg.federation import RepoRegistry

        root_a, root_b = tmp_path / "a", tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        worker_a, worker_b = root_a / "worker.php", root_b / "worker.php"
        definition = "<?php class Worker { public static function commit() {} }"
        worker_a.write_text(definition)
        worker_b.write_text(definition)
        caller = root_a / "caller.php"
        caller.write_text("<?php function run() { Worker::commit(); }")
        store = GraphStore(get_db_path(tmp_path))
        try:
            registry = RepoRegistry(store)
            repo_a = registry.add(root_a)
            registry.add(root_b)
            result = full_build(tmp_path, store)
            assert result["php_calls"] == {"total": 1, "resolved": 1, "unresolved": 0}
            worker_a.write_text(
                definition.replace("commit() {}", "commit() { return 1; }")
            )
            incremental_update(tmp_path, store, changed_files=["a/worker.php"])
            call = store.get_edges_by_source(f"{caller}::run", kind="CALLS")[0]
            assert call.target_qualified == f"{worker_a}::Worker.commit"
            assert (
                store._conn.execute(
                    "SELECT repo_id FROM nodes WHERE qualified_name = ?",
                    (call.target_qualified,),
                ).fetchone()[0]
                == repo_a
            )
        finally:
            store.close()


class TestBareCallResolution:
    """Issue #1006: bare CALLS targets bind to unique same-repo symbols."""

    def test_unique_bare_js_target_binds_and_impact_walks(self, tmp_path):
        store_js = tmp_path / "store.js"
        store_js.write_text("export function commit() {}\n")
        actions_js = tmp_path / "actions.js"
        actions_js.write_text(
            "export function logout() { commit(); }\n"  # no import: bare target
        )
        store = GraphStore(get_db_path(tmp_path))
        try:
            result = full_build(tmp_path, store)
            assert result["errors"] == []
            calls = store.get_edges_by_source(f"{actions_js}::logout", kind="CALLS")
            assert [edge.target_qualified for edge in calls] == [f"{store_js}::commit"]
            assert result["bare_calls"]["resolved"] >= 1
        finally:
            store.close()

        from crg.tools import get_impact_radius

        impact = get_impact_radius(
            changed_files=[str(store_js)], repo_root=str(tmp_path), max_depth=2
        )
        assert any(path.endswith("actions.js") for path in impact["impacted_files"])

    def test_ambiguous_stays_bare_then_binds_after_dedup(self, tmp_path):
        store_js = tmp_path / "store.js"
        store_js.write_text("export function commit() {}\n")
        duplicate_js = tmp_path / "duplicate.js"
        duplicate_js.write_text("export function commit() {}\n")
        actions_js = tmp_path / "actions.js"
        actions_js.write_text("export function logout() { commit(); }\n")
        store = GraphStore(get_db_path(tmp_path))
        try:
            result = full_build(tmp_path, store)
            assert result["bare_calls"]["unresolved"] >= 1
            source = f"{actions_js}::logout"
            assert (
                store.get_edges_by_source(source, kind="CALLS")[0].target_qualified
                == "commit"
            )

            duplicate_js.unlink()
            result = incremental_update(tmp_path, store, changed_files=["duplicate.js"])
            assert result["bare_calls"]["resolved"] >= 1
            assert (
                store.get_edges_by_source(source, kind="CALLS")[0].target_qualified
                == f"{store_js}::commit"
            )
        finally:
            store.close()

    def test_php_dynamic_receivers_are_not_double_bound(self, tmp_path):
        definitions = tmp_path / "definitions.php"
        definitions.write_text(
            "<?php\nnamespace Library;\n"
            "class Worker { public static function commit() {} }\n"
        )
        caller = tmp_path / "caller.php"
        caller.write_text(
            "<?php\nnamespace App;\n"
            "class Service {\n"
            " public function run($unknown) {\n"
            "  $unknown->commit();\n"
            " }\n}\n"
        )
        store = GraphStore(get_db_path(tmp_path))
        try:
            full_build(tmp_path, store)
            calls = store.get_edges_by_source(f"{caller}::Service.run", kind="CALLS")
            assert [edge.target_qualified for edge in calls] == ["commit"]
        finally:
            store.close()

    def test_bare_symbols_remain_repo_scoped(self, tmp_path):
        from crg.federation import RepoRegistry

        root_a, root_b = tmp_path / "a", tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        (root_a / "store.js").write_text("export function commit() {}\n")
        (root_b / "store.js").write_text("export function commit() {}\n")
        caller = root_a / "actions.js"
        caller.write_text("export function logout() { commit(); }\n")
        store = GraphStore(get_db_path(tmp_path))
        try:
            registry = RepoRegistry(store)
            repo_a = registry.add(root_a)
            registry.add(root_b)
            full_build(tmp_path, store)
            call = store.get_edges_by_source(f"{caller}::logout", kind="CALLS")[0]
            assert call.target_qualified == f"{root_a / 'store.js'}::commit"
            assert (
                store._conn.execute(
                    "SELECT repo_id FROM nodes WHERE qualified_name = ?",
                    (call.target_qualified,),
                ).fetchone()[0]
                == repo_a
            )
        finally:
            store.close()
