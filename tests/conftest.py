"""Shared fixtures and test helpers for better-code-review-graph tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

#: The developer's / CI runner's genuine home directory, captured at conftest
#: import time -- i.e. before any fixture has had a chance to redirect it.
#: ``tests/test_home_isolation.py`` compares against this to prove the
#: ``_isolate_per_plugin_home`` fixture below is still in force.
REAL_HOME = Path.home()


def pytest_addoption(parser):
    """Add --setup and --browser CLI options for E2E tests."""
    parser.addoption("--setup", choices=["relay", "env", "plugin"], default="env")
    parser.addoption("--browser", choices=["chrome", "brave", "edge"], default="chrome")


from better_code_review_graph.graph import GraphStore  # noqa: E402
from better_code_review_graph.parser import EdgeInfo, NodeInfo  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolate_global_git_config() -> None:
    """Isolate test-created git repos from the ambient git environment.

    Without this, tests that ``git init`` a throwaway repo and run
    ``git commit`` inherit the developer/CI ``commit.gpgsign``,
    ``gpg.format``, and ``user.signingkey`` from ``~/.gitconfig``.
    When the signing program is not actually wired up for the
    sandboxed test environment (e.g. inside a CI runner image that
    pre-configures SSH signing), the commit aborts with a confusing
    "signing failed" error unrelated to the test logic.

    We also strip the per-invocation ``GIT_*`` location vars that ``git``
    injects into hook processes (``GIT_DIR`` / ``GIT_INDEX_FILE`` /
    ``GIT_WORK_TREE`` / ``GIT_PREFIX`` / ``GIT_OBJECT_DIRECTORY`` /
    ``GIT_COMMON_DIR``). Otherwise, when the suite runs as the ``pytest``
    pre-commit hook, those vars point every ``git`` subprocess in
    ``test_temporal_migration`` back at the parent repo's (locked) index
    instead of the tmp repo it just created -> ``git commit`` exits 1 and
    the tests error. Popping them makes the git-subprocess tests hermetic.
    """
    os.environ.setdefault("GIT_CONFIG_GLOBAL", "/dev/null")
    for var in (
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_WORK_TREE",
        "GIT_PREFIX",
        "GIT_OBJECT_DIRECTORY",
        "GIT_COMMON_DIR",
    ):
        os.environ.pop(var, None)


@pytest.fixture(scope="session", autouse=True)
def _allow_temporal_migration_without_git() -> None:
    """Opt the test session into the no-git fallback path of migration 005.

    The Phase 3 Task 6 BREAKING migration (``005_temporal_columns``)
    reads ``git rev-parse HEAD`` from the repo containing the graph DB
    so it can backfill ``valid_from_sha``. Production deployments
    always satisfy this invariant — CRG only indexes git repos. The
    test suite, however, creates throwaway DBs in ``tmp_path`` /
    ``tempfile.NamedTemporaryFile`` paths that live outside any git
    repo, and many legacy tests deliberately probe code paths that
    assume those tmp dirs are NOT inside a git repo (see
    ``test_incremental.py::TestFindRepoRoot::test_returns_none_without_git``).

    Setting ``CRG_TEST_ALLOW_NO_GIT=1`` flips migration 005 to use the
    documented in-memory sentinel SHA (40 zeros) when no ``.git``
    ancestor is reachable. The migration still aborts with the
    actionable :class:`RuntimeError` in production code paths where
    the env var is unset. Tests that exercise the abort path
    explicitly clear this env var via ``monkeypatch.delenv``.
    """
    os.environ["CRG_TEST_ALLOW_NO_GIT"] = "1"


@pytest.fixture(scope="session", autouse=True)
def _pin_tree_sitter_grammar_cache() -> None:
    """Pin the tree-sitter grammar cache to its real location.

    MUST run before ``_isolate_per_plugin_home`` redirects HOME -- session
    scope guarantees that, since pytest sets higher-scoped fixtures up first.

    ``tree_sitter_language_pack`` keeps its downloaded grammar shared
    libraries in an OS cache dir derived from the environment (``$HOME`` /
    ``$XDG_CACHE_HOME`` on Linux, ``LOCALAPPDATA`` on Windows). Redirecting
    HOME per-test moves that cache to an empty tmp dir, so every
    ``get_parser`` call has to re-download the grammar; on a network-
    restricted CI runner that raises
    ``RuntimeError: Download error: Could not determine system cache
    directory``. This fixture is what stops that happening, and it is still
    required: without it the grammars are unreachable and nothing parses.

    What changed is only how that unreachability *presents*.
    ``CodeParser._get_parser`` used to catch the error and return ``None``,
    which ``parse_bytes`` turned into an empty result, so the whole suite
    silently parsed zero nodes instead of erroring -- which is exactly what
    happened on ubuntu-latest, while Windows stayed green because its cache
    follows LOCALAPPDATA rather than the redirected home. A supported
    language whose grammar will not load now raises
    ``GrammarUnavailableError`` instead, so removing this fixture fails the
    suite loudly with the reason attached rather than quietly emptying it.

    Resolving the path here and handing it straight back via ``configure``
    is idempotent (verified: ``cache_dir()`` is unchanged afterwards) and
    keeps grammar loading working identically to a run with no fixtures at
    all. The grammar cache is a downloaded build artifact, not developer
    state, so sharing it is the same deliberate carve-out as
    ``GIT_CONFIG_GLOBAL`` above -- credential isolation is unaffected because
    ``PerPluginStore`` resolves from ``Path.home()``, not this cache.
    """
    import tree_sitter_language_pack as tslp

    tslp.configure(tslp.PackConfig(cache_dir=tslp.cache_dir()))


@pytest.fixture(autouse=True)
def _isolate_per_plugin_home(tmp_path_factory, monkeypatch):
    """Redirect ``~`` to a per-test tmp dir so credential-store writes stay
    out of the developer's real home directory.

    ``mcp_core.storage.per_plugin_store.PerPluginStore`` resolves every path
    from ``Path.home()``: the encrypted config lands in
    ``~/.better-code-review-graph-mcp/config.json`` and the AES-GCM machine
    key in ``~/.better-code-review-graph-mcp/.secret``. Tests that exercise
    the ``config`` tool end-to-end (e.g.
    ``test_server.py::TestConfigTool::test_setup_status_action``) reach the
    real store unmocked, so on a machine where the developer actually uses
    CRG a plain ``uv run pytest`` reads their live credentials and
    ``_load_or_generate_machine_key`` mints a fresh ``.secret`` into their
    home. ``credential_state._sub_data_dir`` has the same problem via its
    ``~/.crg`` default. In CI with parallel workers those writes race on one
    shared home.

    ``Path.home()`` reads ``HOME`` on POSIX and ``USERPROFILE`` on Windows,
    so both are set. This is function-scoped on purpose: neither
    session-scoped autouse fixture above resolves a home path (they only set
    ``GIT_CONFIG_GLOBAL`` and ``CRG_TEST_ALLOW_NO_GIT``), so there is nothing
    that needs the redirect earlier than per-test setup, and function scope
    keeps the plain ``monkeypatch`` fixture usable.
    """
    fake_home = tmp_path_factory.mktemp("crg_test_home")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))


@pytest.fixture(autouse=True)
def force_local_embeddings(monkeypatch):
    """Force tests to use the local ONNX embedding backend.

    Prevents tests from attempting to hit Cohere/LiteLLM APIs if API keys
    happen to be present in the CI environment.
    """
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")


@pytest.fixture(autouse=True)
def mock_credential_state(monkeypatch):
    """Keep tests off real cloud dispatch paths.

    resolve_credential_state is pinned to CONFIGURED so no test triggers a
    relay session. (The pre-de-host ``_maybe_include_setup_hint`` patch is
    gone: the BYOK cut removed the browser setup flow and its hint hook.)
    """
    from better_code_review_graph.credential_state import CredentialState

    monkeypatch.setattr(
        "better_code_review_graph.credential_state._state",
        CredentialState.CONFIGURED,
    )


@pytest.fixture
def tmp_graph_store(tmp_path):
    """Create a temporary GraphStore for testing."""
    db_path = tmp_path / "graph.db"
    store = GraphStore(str(db_path))
    yield store
    store.close()


def _make_node(
    name: str,
    kind: str,
    qualified_name: str,
    **kwargs,
) -> NodeInfo:
    """Helper to create a NodeInfo for testing.

    The ``qualified_name`` is only used to derive defaults for ``file_path``
    (everything before ``::``).  The actual qualified name stored in the DB is
    computed by ``GraphStore._make_qualified()`` from the NodeInfo fields.

    Common kwargs: file_path, line_start, line_end, language, parent_name,
    params, return_type, modifiers, is_test, extra.
    """
    # Derive file_path from qualified_name if not provided
    if "::" in qualified_name:
        default_file_path = qualified_name.split("::")[0]
    else:
        default_file_path = "test.py"

    return NodeInfo(
        kind=kind,
        name=name,
        file_path=kwargs.get("file_path", default_file_path),
        line_start=kwargs.get("line_start", 1),
        line_end=kwargs.get("line_end", 10),
        language=kwargs.get("language", "python"),
        parent_name=kwargs.get("parent_name"),
        params=kwargs.get("params"),
        return_type=kwargs.get("return_type"),
        modifiers=kwargs.get("modifiers"),
        is_test=kwargs.get("is_test", False),
        extra=kwargs.get("extra", {}),
    )


def _make_edge(
    kind: str,
    source: str,
    target: str,
    file_path: str,
    line: int = 1,
    **kwargs,
) -> EdgeInfo:
    """Helper to create an EdgeInfo for testing.

    ``source`` and ``target`` map to EdgeInfo.source and EdgeInfo.target
    (which are stored as source_qualified / target_qualified in the DB).
    """
    return EdgeInfo(
        kind=kind,
        source=source,
        target=target,
        file_path=file_path,
        line=line,
        extra=kwargs.get("extra", {}),
    )
