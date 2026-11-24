"""Guard: the test session must never touch the real home directory.

``conftest._isolate_per_plugin_home`` redirects ``HOME`` / ``USERPROFILE`` so
anything resolving ``Path.home()`` -- most importantly
``credential_state._sub_data_dir``'s ``~/.crg`` default -- writes into a
tmp dir. These tests fail loudly if that fixture is ever removed, renamed,
or stops being ``autouse``, instead of the failure showing up as mysterious
``subs/`` directories appearing in a developer's real home.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import tree_sitter_language_pack as tslp

from crg.credential_state import db_path_for_sub
from crg.parser import CodeParser

from .conftest import REAL_HOME

_FIXTURE_HINT = (
    "conftest._isolate_per_plugin_home is not in force -- tests are running "
    "against the real home directory and will read/write the developer's "
    "live ~/.crg data."
)


def test_path_home_is_redirected_away_from_the_real_home() -> None:
    """``Path.home()`` inside a test must not be the real home."""
    assert Path.home() != REAL_HOME, _FIXTURE_HINT


def test_home_env_vars_point_at_the_isolated_home() -> None:
    """Both POSIX ``HOME`` and Windows ``USERPROFILE`` must be redirected.

    Setting only one of them silently leaves the other platform unprotected,
    so assert on both regardless of which one this platform's
    ``Path.home()`` actually consults.
    """
    assert Path(os.environ["HOME"]) != REAL_HOME, _FIXTURE_HINT
    assert Path(os.environ["USERPROFILE"]) != REAL_HOME, _FIXTURE_HINT
    assert os.environ["HOME"] == str(Path.home()), _FIXTURE_HINT
    assert os.environ["USERPROFILE"] == str(Path.home()), _FIXTURE_HINT


def test_per_sub_data_dir_writes_land_outside_the_real_home() -> None:
    """A per-sub data dir must land under the isolated home, never the real one.

    The guard assertion runs *before* the write so that a broken fixture
    can never cause this test itself to pollute the real home.
    """
    assert Path.home() != REAL_HOME, _FIXTURE_HINT

    db_path = db_path_for_sub("home-isolation-guard")
    assert (
        db_path.parent.parent == (Path.home() / ".n24q02m" / "crg" / "subs").resolve()
    ), "per-sub data dir did not land under the isolated home's ~/.n24q02m/crg"
    assert db_path.parent.is_dir(), "per-sub directory was not created for the subject"


def test_isolated_home_is_empty_per_test() -> None:
    """Each test gets a fresh home, so no state leaks between tests.

    ``test_per_sub_data_dir_writes_land_outside_the_real_home`` creates a
    subs/<uid>/graph.db; if the fixture were session-scoped that directory
    would still be visible here.
    """
    assert Path.home() != REAL_HOME, _FIXTURE_HINT
    assert not (Path.home() / ".n24q02m" / "crg" / "subs").exists()


def test_legacy_crg_migrates_once_to_n24q02m(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy ~/.crg migrates once non-destructively to ~/.n24q02m/crg."""
    monkeypatch.delenv("CRG_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CRG_DATA_DIR", raising=False)
    monkeypatch.delenv("N24Q02M_HOME", raising=False)
    monkeypatch.delenv("N24Q02M_USE_XDG", raising=False)
    monkeypatch.delenv("CRG_PROFILE", raising=False)
    legacy = Path.home() / ".crg"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "config.toml").write_text("[server]\nport = 8123\n", encoding="utf-8")

    from crg.config import crg_config_dir

    target = crg_config_dir()
    assert target == Path.home() / ".n24q02m" / "crg"
    assert (target / "config.toml").read_text(
        encoding="utf-8"
    ) == "[server]\nport = 8123\n"
    assert (legacy / "config.toml").exists()

    (legacy / "config.toml").write_text("[server]\nport = 9999\n", encoding="utf-8")
    assert (crg_config_dir() / "config.toml").read_text(
        encoding="utf-8"
    ) == "[server]\nport = 8123\n"


def test_n24q02m_home_xdg_and_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Honor N24Q02M_HOME, N24Q02M_USE_XDG=1, and Tier-2 profile isolation."""
    from crg.config import crg_config_dir

    custom = tmp_path / "custom-n24"
    monkeypatch.delenv("CRG_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CRG_DATA_DIR", raising=False)
    monkeypatch.setenv("N24Q02M_HOME", str(custom))
    monkeypatch.setenv("CRG_PROFILE", "work")
    assert crg_config_dir() == custom / "crg" / "profiles" / "work"
    assert (
        db_path_for_sub("u1").parent.parent
        == (custom / "crg" / "profiles" / "work" / "subs").resolve()
    )

    monkeypatch.delenv("N24Q02M_HOME", raising=False)
    monkeypatch.delenv("CRG_PROFILE", raising=False)
    monkeypatch.setenv("N24Q02M_USE_XDG", "1")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert crg_config_dir() == tmp_path / "xdg" / "n24q02m" / "crg"


def test_repo_local_crg_dir_preserved(tmp_path: Path) -> None:
    """Repo-local <repo>/.crg/graph.db remains at the repository root."""
    from crg.incremental import get_db_path

    repo = tmp_path / "repo"
    repo.mkdir()
    assert get_db_path(repo) == repo / ".crg" / "graph.db"


def test_cli_profile_flag_sets_and_restores_env(monkeypatch, tmp_path: Path) -> None:
    """CLI --profile and --profile= set CRG_PROFILE for dispatch and restore it."""
    import os
    import sys

    from crg.cli import main

    seen: list[str | None] = []

    def fake_dispatch(argv: list[str]) -> int:
        seen.append(os.environ.get("CRG_PROFILE"))
        assert argv == ["status"]
        return 0

    monkeypatch.setattr("crg.cli._dispatch_argv", fake_dispatch)

    monkeypatch.delenv("CRG_PROFILE", raising=False)
    monkeypatch.setattr(sys, "argv", ["crg", "--profile", "work", "status"])
    assert main() == 0
    assert seen[-1] == "work"
    assert "CRG_PROFILE" not in os.environ

    monkeypatch.setenv("CRG_PROFILE", "existing")
    monkeypatch.setattr(sys, "argv", ["crg", "--profile=staging", "status"])
    assert main() == 0
    assert seen[-1] == "staging"
    assert os.environ.get("CRG_PROFILE") == "existing"


def test_cli_profile_flag_errors(monkeypatch, capsys) -> None:
    """CLI --profile without a value or with an invalid profile returns exit code 2."""
    import sys

    from crg.cli import main

    monkeypatch.setattr(sys, "argv", ["crg", "--profile"])
    assert main() == 2
    assert "--profile requires a value" in capsys.readouterr().err

    monkeypatch.setattr(sys, "argv", ["crg", "--profile", "../bad"])
    assert main() == 2
    assert "Invalid" in capsys.readouterr().err or capsys.readouterr().err == ""


def test_tree_sitter_grammar_cache_survives_the_isolated_home() -> None:
    """Redirecting HOME must not drag the tree-sitter grammar cache with it.

    ``tree_sitter_language_pack`` resolves its grammar cache from the
    environment (``$HOME`` / ``$XDG_CACHE_HOME`` on Linux, ``LOCALAPPDATA``
    on Windows) and memoises the result on first use. If the first resolution
    happens inside a test, it lands in that test's empty tmp home and grammar
    loading fails. That used to be invisible: ``CodeParser._get_parser``
    swallowed the error and returned ``None``, ``parse_bytes`` yielded an
    empty result, and the suite parsed zero nodes everywhere instead of
    erroring. A supported language whose grammar will not load now raises
    ``GrammarUnavailableError``, so the same breakage reports itself.

    ``conftest._pin_tree_sitter_grammar_cache`` is still what keeps the
    grammars reachable: it forces that first resolution to happen at session
    start, with the real environment still in place. ``cache_dir()`` raises
    outright when unresolvable, so this asserts both that it resolves and
    that it did not follow the redirect. The parse below then confirms the
    grammars genuinely load, rather than trusting the path check alone.
    """
    assert Path.home() != REAL_HOME, _FIXTURE_HINT

    cache = Path(tslp.cache_dir())
    assert not cache.is_relative_to(Path.home()), (
        f"tree-sitter grammar cache followed the isolated home ({cache}) -- "
        "see conftest._pin_tree_sitter_grammar_cache"
    )

    nodes, _edges = CodeParser().parse_bytes(
        Path("sample.py"), b"def outer():\n    return 1\n"
    )
    assert [n for n in nodes if n.kind == "Function"], (
        "tree-sitter returned no Function nodes -- grammar loading is broken "
        "under the isolated HOME (see conftest._pin_tree_sitter_grammar_cache)"
    )
