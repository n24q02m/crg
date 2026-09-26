"""G6 UX accuracy — setup_status derives state from host model cells.

Bug (pre-de-host): setup_status returned stale module-level _state /
ambient per-user credential stores instead of the credentials that would
actually serve the next provider call.

Fix (post-de-host): there is no browser setup flow and no per-user store;
status reports the host-owned per-task model cells (instance
``config.toml`` ``[models.<task>]`` or ``HULL_<TASK>_API_KEY`` env), and
ambient provider env keys from the BYOK era no longer count.
"""

from __future__ import annotations

from typing import Any

import pytest


def _call_config_setup_status_sync() -> dict[str, Any]:
    """Invoke the async server config action and return parsed dict."""
    import asyncio

    from better_code_review_graph.server import config

    return asyncio.run(config(action="setup_status"))


def _clear_cell_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every key that could configure a model cell."""
    for k in (
        "HULL_EMBED_API_KEY",
        "HULL_RERANK_API_KEY",
        "HULL_CHAT_API_KEY",
        "HULL_JEV_SCORE_API_KEY",
        # BYOK-era ambient keys must no longer influence the status.
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "JINA_AI_API_KEY",
        "OPENAI_API_KEY",
        "COHERE_API_KEY",
        "CO_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _hermetic_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Point the instance config at an empty per-test dir (no real ~/.crg).

    Also pins credential state LOCAL: the suite-wide conftest fixture pins
    CONFIGURED, which would mask the cell-derived status semantics under
    test here.
    """
    from better_code_review_graph import credential_state as cs
    from better_code_review_graph.credential_state import CredentialState

    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
    _clear_cell_env(monkeypatch)
    monkeypatch.setattr(cs, "_state", CredentialState.LOCAL)


class TestSetupStatusCellDerived:
    """setup_status reports the host model cells, never ambient state."""

    def test_ambient_provider_env_keys_do_not_configure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BYOK-era provider env keys must not report the server configured.

        The de-hosted analog of the old 'ignores ambient store' guarantee:
        only per-task cells (HULL_<TASK>_API_KEY / config.toml) configure.
        """
        monkeypatch.setenv("GEMINI_API_KEY", "ambient-gemini")
        monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai")

        result = _call_config_setup_status_sync()

        assert result["state"] == "local"
        assert result["providers_configured"] == []

    def test_unconfigured_cells_report_local(self) -> None:
        """No configured cells -> state falls back to the credential state."""
        result = _call_config_setup_status_sync()

        assert result["state"] == "local"
        assert result["providers_configured"] == []

    def test_env_cell_key_reports_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HULL_EMBED_API_KEY (host-injected) -> configured, embed listed."""
        monkeypatch.setenv("HULL_EMBED_API_KEY", "sk-host-injected")

        result = _call_config_setup_status_sync()

        assert result["state"] == "configured"
        assert result["providers_configured"] == ["embed"]

    def test_response_always_includes_providers_configured(self) -> None:
        """providers_configured is always present (and a list)."""
        result = _call_config_setup_status_sync()

        assert "providers_configured" in result
        assert isinstance(result["providers_configured"], list)

    def test_no_duplicate_task_between_env_and_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Same task configured via env AND config.toml is listed once."""
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            '[models.embed]\napi_key = "from-file"\n', encoding="utf-8"
        )
        monkeypatch.setenv("HULL_EMBED_API_KEY", "from-env")

        result = _call_config_setup_status_sync()

        assert result["providers_configured"].count("embed") == 1
