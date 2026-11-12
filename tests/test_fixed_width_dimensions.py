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


def test_store_width_follows_the_model_the_cell_sends(tmp_path):
    """The store must request the cell model's width, not the selection's."""
    from crg.embeddings import CloudEmbeddingBackend, EmbeddingStore

    class _Cell:
        model = "voyage-4-lite"

    class _Pooled:
        cell = _Cell()

    backend = CloudEmbeddingBackend(model="openai/text-embedding-3-small")
    with patch("crg.credentials.resolve_pool", return_value=_Pooled()):
        store = EmbeddingStore(tmp_path / "graph.db", backend)
    try:
        assert store.dimensions == 1024
    finally:
        store.close()
