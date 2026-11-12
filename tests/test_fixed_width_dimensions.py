"""Fixed-width cloud models never receive an unsupported output width; no live calls."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from crg.embeddings import _cloud_storage_dimensions, _post_embeddings


@pytest.fixture(autouse=True)
def _embed_cell_key(monkeypatch, tmp_path):
    """Give the real ``_post_embeddings`` a host key without touching network."""
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("HULL_EMBED_API_KEY", "k-test")


@pytest.mark.parametrize("model", ["voyage-4-lite", "voyage/voyage-4-lite"])
def test_voyage_storage_width_is_an_accepted_output_width(model):
    assert _cloud_storage_dimensions(model) == 1024


def test_voyage_default_width_is_rejected_without_dispatch():
    with patch("crg.credentials.AttemptClient") as client_cls:
        with pytest.raises(ValueError, match="requires dimensions"):
            _post_embeddings(
                ["hello"],
                "voyage-4-lite",
                768,
                input_type="search_document",
                provider="openai",
            )
    client_cls.assert_not_called()
