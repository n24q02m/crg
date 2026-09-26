"""Exact Cohere dimensions and persisted index/query compatibility; no live calls.

Ported to the post-de-host transport: ``CloudEmbeddingBackend`` dispatches
through ``_post_embeddings`` (hull ``[models.embed]`` cell, plain-HTTP
OpenAI-spec), so the dispatch seam is that module function. The
storage-level contracts — width mismatch must never coerce or persist,
incompatible persisted widths refuse queries, asymmetric ``input_type`` —
are unchanged.
"""

from __future__ import annotations

import os
import sqlite3
from unittest.mock import patch

import pytest

from better_code_review_graph.embeddings import (
    CloudEmbeddingBackend,
    EmbeddingStore,
    _encode_vector,
    _post_embeddings,
)
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo


@pytest.fixture(autouse=True)
def _embed_cell_key(monkeypatch, tmp_path):
    """Give the real ``_post_embeddings`` a host key without touching network."""
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("HULL_EMBED_API_KEY", "k-test")


def _dispatch(*vectors):
    """Patch the dispatch seam to return pre-baked vectors."""
    return patch(
        "better_code_review_graph.embeddings._post_embeddings",
        return_value=list(vectors),
    )


def test_unsupported_cohere_width_is_rejected_without_dispatch():
    # The width-selection guard lives inside _post_embeddings and must fire
    # BEFORE any client is constructed / request is spent.
    with patch(
        "hull_core.providers.openai_spec.OpenAICompatClient"
    ) as client_cls:
        with pytest.raises(ValueError, match="requires dimensions"):
            _post_embeddings(
                ["hello"],
                "cohere/embed-v4.0",
                768,
                input_type="search_document",
                provider="cohere",
            )
    client_cls.assert_not_called()


@pytest.mark.parametrize("wrong_width", [768, 1536])
def test_provider_width_mismatch_never_coerces_or_persists(tmp_path, wrong_width):
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
    graph = GraphStore(str(tmp_path / "graph.db"))
    store = EmbeddingStore(tmp_path / "graph.db", backend)
    try:
        graph.upsert_node(
            NodeInfo(
                kind="Function",
                name="first",
                file_path="a.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="a",
        )
        graph.upsert_node(
            NodeInfo(
                kind="Function",
                name="second",
                file_path="a.py",
                line_start=4,
                line_end=5,
                language="python",
            ),
            file_hash="a",
        )
        graph.commit()
        nodes = graph.get_nodes_by_files(["a.py"])
        with _dispatch([1.0] * 1024, [1.0] * wrong_width):
            with pytest.raises(ValueError, match="dimensional vector per node"):
                store.embed_nodes(nodes)
        assert store.count() == 0
    finally:
        store.close()
        graph.close()


def test_cohere_reopen_reembed_legacy_width_and_query(tmp_path):
    db = tmp_path / "graph.db"
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
    graph = GraphStore(str(db))
    try:
        graph.upsert_node(
            NodeInfo(
                kind="Function",
                name="authenticate",
                file_path="auth.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="a",
        )
        graph.commit()
        nodes = graph.get_nodes_by_files(["auth.py"])
        qn = nodes[0].qualified_name
        store = EmbeddingStore(db, backend)
        try:
            with patch(
                "better_code_review_graph.embeddings._post_embeddings",
                return_value=[[1.0] * 1024],
            ) as dispatch:
                assert store.embed_nodes(nodes) == 1
                assert dispatch.call_args.kwargs["input_type"] == "search_document"
                assert dispatch.call_args.args[2] == 1024  # dimensions (positional)
        finally:
            store.close()

        # A pre-upgrade row has the same model and text hash but a sliced vector.
        with sqlite3.connect(db) as conn:
            conn.execute(
                "UPDATE embeddings SET vector = ?", (_encode_vector([1.0] * 768),)
            )

        store = EmbeddingStore(db, backend)
        try:
            with _dispatch() as dispatch:
                with pytest.raises(ValueError, match="incompatible"):
                    store.search("authenticate a user")
                dispatch.assert_not_called()
            with patch(
                "better_code_review_graph.embeddings._post_embeddings",
                return_value=[[1.0] * 1024],
            ) as dispatch:
                assert store.embed_nodes(nodes) == 1
                assert store.embed_nodes(nodes) == 0
                assert store.search("authenticate a user", limit=1) == [
                    (qn, pytest.approx(1.0))
                ]
                assert [
                    call.kwargs["input_type"] for call in dispatch.call_args_list
                ] == ["search_document", "search_query"]
                assert all(
                    call.args[2] == 1024 for call in dispatch.call_args_list
                )
        finally:
            store.close()
        with sqlite3.connect(db) as conn:
            assert (
                conn.execute("SELECT length(vector) FROM embeddings").fetchone()[0]
                == 4096
            )
    finally:
        graph.close()
