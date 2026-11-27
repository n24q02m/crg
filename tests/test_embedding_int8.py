"""int8 embedding storage: quantisation accuracy, ranking agreement and migration.

Every vector in these tests is generated from a fixed NumPy seed, the
embedding backend is an in-process stub, and nothing touches the network.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from crg import embeddings as emb
from crg.embeddings import (
    EMBEDDING_FORMAT_METADATA_KEY,
    EMBEDDING_FORMAT_VERSION,
    EmbeddingStore,
    _dequantize_int8,
    _encode_vector,
    _quantize_rows,
)
from crg.graph import GraphNode, GraphStore
from crg.parser import NodeInfo

# Exact DDL written by the float32-only releases. Kept verbatim so the
# migration tests open a database in the byte layout those releases produced.
_LEGACY_EMBEDDINGS_DDL = """
CREATE TABLE IF NOT EXISTS embeddings (
    qualified_name TEXT PRIMARY KEY,
    vector BLOB NOT NULL,
    text_hash TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown'
);
"""

_PROVIDER = "fixed-test-backend"
_COSINE_TOLERANCE = 0.01


def _unit_vectors(count: int, dims: int, *, seed: int, outliers: bool = False):
    rng = np.random.default_rng(seed)
    mat = rng.standard_normal((count, dims)).astype(np.float32)
    if outliers:
        # Real embedding models have a few high-magnitude channels; they
        # widen the per-vector scale and are the hard case for int8.
        mat[:, :4] *= 8.0
    return mat / np.linalg.norm(mat, axis=1, keepdims=True)


def _queries_near(docs, count: int, *, seed: int):
    rng = np.random.default_rng(seed)
    picks = docs[rng.integers(0, len(docs), count)]
    noise = rng.standard_normal(picks.shape).astype(np.float32)
    mat = picks + 0.5 * noise / np.sqrt(docs.shape[1])
    return mat / np.linalg.norm(mat, axis=1, keepdims=True)


class _FixedBackend:
    """Embedding stub: node text and query text map to fixed vectors."""

    name = _PROVIDER

    def __init__(self, docs: dict[str, list[float]], queries: dict[str, list[float]]):
        self._docs = docs
        self._queries = queries

    def embed_texts(self, texts, dimensions: int | None = 768):
        return [self._docs[text.split()[0]] for text in texts]

    def embed_single(self, text, dimensions: int | None = 768):
        return self._queries[text]

    def embed_single_query(self, text, dimensions: int | None = 768):
        return self._queries[text]


def _node(name: str) -> GraphNode:
    return GraphNode(
        id=1,
        kind="Function",
        name=name,
        qualified_name=f"m.py::{name}",
        file_path="m.py",
        line_start=1,
        line_end=2,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )


@contextmanager
def _connect(path: Path) -> Generator[sqlite3.Connection]:
    """Open ``path``, commit on success, and always close the connection."""
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _write_legacy_graph_db(path: Path, docs) -> list[str]:
    """Create graph.db the way the float32-only releases left it."""
    names = [f"fn{i:05d}" for i in range(len(docs))]
    store = GraphStore(path)
    try:
        for name in names:
            store.upsert_node(NodeInfo("Function", name, "m.py", 1, 2, "python"))
        store.commit()
    finally:
        store.close()
    with _connect(path) as conn:
        conn.executescript(_LEGACY_EMBEDDINGS_DDL)
        conn.executemany(
            "INSERT OR REPLACE INTO embeddings "
            "(qualified_name, vector, text_hash, provider) VALUES (?, ?, ?, ?)",
            [
                (f"m.py::{name}", _encode_vector(vec.tolist()), "h", _PROVIDER)
                for name, vec in zip(names, docs, strict=True)
            ],
        )
    return [f"m.py::{name}" for name in names]


def _rows(path: Path) -> dict[str, tuple[bytes, str, float | None]]:
    with _connect(path) as conn:
        return {
            qn: (bytes(blob), fmt, scale)
            for qn, blob, fmt, scale in conn.execute(
                "SELECT qualified_name, vector, vector_format, vector_scale "
                "FROM embeddings"
            )
        }


def _vacuumed_size(path: Path) -> int:
    """Database size in bytes once free pages are reclaimed.

    Measured as ``page_count * page_size``: in WAL mode VACUUM output sits in
    the WAL until a checkpoint, so the file length alone can lag behind.
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    finally:
        conn.close()
    return pages * page_size


# ---------------------------------------------------------------------------
# Quantisation primitives
# ---------------------------------------------------------------------------


class TestQuantizeRows:
    def test_symmetric_scale_and_bounded_component_error(self):
        mat = _unit_vectors(64, 768, seed=1, outliers=True)
        codes, scales, ok = _quantize_rows(mat)
        assert codes.dtype == np.int8
        assert codes.shape == mat.shape
        assert ok.all()
        np.testing.assert_allclose(scales, np.abs(mat).max(axis=1) / 127.0, rtol=1e-6)
        assert int(np.abs(codes.astype(np.int16)).max()) == 127
        restored = codes.astype(np.float32) * scales[:, None]
        # Rounding to the nearest step bounds every component by half a step.
        assert np.all(np.abs(restored - mat) <= scales[:, None] / 2 + 1e-7)

    def test_zero_vector_quantises_to_zero(self):
        codes, scales, ok = _quantize_rows(np.zeros((1, 8), dtype=np.float32))
        assert ok.all()
        assert scales[0] == 0.0
        assert not codes.any()

    def test_non_finite_rows_are_flagged_not_quantised(self):
        mat = np.ones((3, 4), dtype=np.float32)
        mat[1, 2] = np.nan
        mat[2, 0] = np.inf
        _codes, _scales, ok = _quantize_rows(mat)
        assert ok.tolist() == [True, False, False]

    def test_dequantize_round_trip(self):
        mat = _unit_vectors(1, 1024, seed=2)
        codes, scales, _ok = _quantize_rows(mat)
        restored = np.asarray(
            _dequantize_int8(codes[0].tobytes(), float(scales[0])), dtype=np.float32
        )
        cosine = float(restored @ mat[0] / np.linalg.norm(restored))
        assert cosine > 0.9999


# ---------------------------------------------------------------------------
# Accuracy against the float32 reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dims", [768, 1024])
@pytest.mark.parametrize("outliers", [False, True])
def test_search_scores_match_float32_within_tolerance(tmp_path, dims, outliers):
    docs = _unit_vectors(1500, dims, seed=dims, outliers=outliers)
    queries = _queries_near(docs, 25, seed=dims + 1)
    names = [f"fn{i:05d}" for i in range(len(docs))]
    backend = _FixedBackend(
        {n: v.tolist() for n, v in zip(names, docs, strict=True)},
        {f"q{i}": q.tolist() for i, q in enumerate(queries)},
    )
    store = EmbeddingStore(tmp_path / "vectors.db", backend)
    store.dimensions = dims
    try:
        assert store.embed_nodes([_node(n) for n in names]) == len(names)
        reference = queries @ docs.T
        worst_error = 0.0
        overlaps = []
        for i in range(len(queries)):
            got = dict(store.search(f"q{i}", limit=len(names)))
            expected = {
                f"m.py::{n}": float(s) for n, s in zip(names, reference[i], strict=True)
            }
            assert got.keys() == expected.keys()
            worst_error = max(
                worst_error, max(abs(got[qn] - expected[qn]) for qn in expected)
            )
            top_got = [qn for qn, _ in store.search(f"q{i}", limit=10)]
            top_ref = sorted(expected, key=expected.__getitem__, reverse=True)[:10]
            assert top_got[0] == top_ref[0]
            overlaps.append(len(set(top_got) & set(top_ref)) / 10)
        assert worst_error <= _COSINE_TOLERANCE
        assert min(overlaps) >= 0.8
        assert sum(overlaps) / len(overlaps) >= 0.95
    finally:
        store.close()


def test_new_rows_are_written_as_int8(tmp_path):
    docs = _unit_vectors(3, 1024, seed=3)
    backend = _FixedBackend(
        {f"fn{i}": v.tolist() for i, v in enumerate(docs)}, {"q": docs[0].tolist()}
    )
    store = EmbeddingStore(tmp_path / "vectors.db", backend)
    store.dimensions = 1024
    try:
        store.embed_nodes([_node(f"fn{i}") for i in range(3)])
        # Width is checked on the stored dimension, so an unchanged row is reused.
        assert store.embed_nodes([_node(f"fn{i}") for i in range(3)]) == 0
        assert store.search("q", limit=1)[0] == (
            "m.py::fn0",
            pytest.approx(1.0, abs=1e-3),
        )
    finally:
        store.close()
    rows = _rows(tmp_path / "vectors.db")
    assert {fmt for _blob, fmt, _scale in rows.values()} == {"i8"}
    assert {len(blob) for blob, _fmt, _scale in rows.values()} == {1024}
    assert all(scale and scale > 0 for _blob, _fmt, scale in rows.values())


def test_non_finite_vector_is_kept_as_float32(tmp_path):
    vec = [0.5] * 768
    vec[3] = float("nan")
    backend = _FixedBackend({"fn0": vec}, {})
    store = EmbeddingStore(tmp_path / "vectors.db", backend)
    try:
        store.embed_nodes([_node("fn0")])
    finally:
        store.close()
    blob, fmt, scale = _rows(tmp_path / "vectors.db")["m.py::fn0"]
    assert fmt == "f32"
    assert scale is None
    assert len(blob) == 768 * 4


def test_incompatible_int8_width_is_refused(tmp_path):
    docs = _unit_vectors(1, 768, seed=4)
    backend = _FixedBackend({"fn0": docs[0].tolist()}, {"q": docs[0].tolist()})
    store = EmbeddingStore(tmp_path / "vectors.db", backend)
    try:
        store.embed_nodes([_node("fn0")])
        store.dimensions = 1024
        with pytest.raises(ValueError, match="incompatible"):
            store.search("q")
    finally:
        store.close()


def test_float32_rows_from_older_writers_are_still_searchable(tmp_path):
    """A writer that omits the format columns gets the float32 default."""
    docs = _unit_vectors(2, 768, seed=5)
    backend = _FixedBackend({"fn0": docs[0].tolist()}, {"q": docs[1].tolist()})
    store = EmbeddingStore(tmp_path / "vectors.db", backend)
    try:
        store.embed_nodes([_node("fn0")])
        store._conn.execute(
            "INSERT OR REPLACE INTO embeddings "
            "(qualified_name, vector, text_hash, provider) VALUES (?, ?, ?, ?)",
            ("m.py::fn1", _encode_vector(docs[1].tolist()), "h", _PROVIDER),
        )
        store._conn.commit()
        scores = dict(store.search("q", limit=5))
        assert scores["m.py::fn1"] == pytest.approx(1.0, abs=1e-6)
        assert scores["m.py::fn0"] == pytest.approx(float(docs[0] @ docs[1]), abs=0.01)
    finally:
        store.close()
    assert _rows(tmp_path / "vectors.db")["m.py::fn1"][1] == "f32"


# ---------------------------------------------------------------------------
# Migration of float32 databases
# ---------------------------------------------------------------------------


class TestFloat32Migration:
    def test_migrates_every_vector_in_place(self, tmp_path):
        db = tmp_path / "graph.db"
        docs = _unit_vectors(1200, 768, seed=6, outliers=True)
        qns = _write_legacy_graph_db(db, docs)

        backend = _FixedBackend({}, {"q": docs[7].tolist()})
        store = EmbeddingStore(db, backend)
        try:
            assert store.migrated_vectors == len(qns)
            assert store.count() == len(qns)
            assert store.search("q", limit=1)[0][0] == qns[7]
        finally:
            store.close()

        rows = _rows(db)
        assert sorted(rows) == sorted(qns)
        for qn, original in zip(qns, docs, strict=True):
            blob, fmt, scale = rows[qn]
            assert fmt == "i8"
            assert len(blob) == 768
            assert scale is not None
            restored = np.asarray(_dequantize_int8(blob, scale), dtype=np.float32)
            np.testing.assert_allclose(restored, original, atol=scale / 2 + 1e-7)
        with _connect(db) as conn:
            version = conn.execute(
                "SELECT value FROM metadata WHERE key = ?",
                (EMBEDDING_FORMAT_METADATA_KEY,),
            ).fetchone()
            providers = {
                r[0] for r in conn.execute("SELECT DISTINCT provider FROM embeddings")
            }
        assert version == (EMBEDDING_FORMAT_VERSION,)
        assert providers == {_PROVIDER}

    def test_migration_is_idempotent(self, tmp_path):
        db = tmp_path / "graph.db"
        _write_legacy_graph_db(db, _unit_vectors(50, 1024, seed=7))
        EmbeddingStore(db).close()
        first = _rows(db)

        store = EmbeddingStore(db)
        try:
            assert store.migrated_vectors == 0
            assert store._migrate_float32_vectors() == 0
        finally:
            store.close()
        assert _rows(db) == first

    def test_failed_migration_rolls_back_and_keeps_float32(self, tmp_path, caplog):
        db = tmp_path / "graph.db"
        docs = _unit_vectors(1300, 768, seed=8)
        qns = _write_legacy_graph_db(db, docs)
        with _connect(db) as conn:
            legacy = {
                qn: bytes(blob)
                for qn, blob in conn.execute(
                    "SELECT qualified_name, vector FROM embeddings"
                )
            }

        real = emb._quantize_rows
        calls = {"n": 0}

        def _fail_on_second_chunk(mat):
            calls["n"] += 1
            if calls["n"] == 2:
                raise sqlite3.OperationalError("disk I/O error")
            return real(mat)

        backend = _FixedBackend({}, {"q": docs[3].tolist()})
        with (
            patch.object(emb, "_quantize_rows", _fail_on_second_chunk),
            caplog.at_level(logging.WARNING, logger="crg.embeddings"),
        ):
            store = EmbeddingStore(db, backend)
        try:
            assert calls["n"] == 2
            assert store.migrated_vectors == 0
            assert "float32" in caplog.text
            # Nothing was lost: the original float32 rows are intact and served.
            assert store.search("q", limit=1)[0] == (qns[3], pytest.approx(1.0))
        finally:
            store.close()
        rows = _rows(db)
        assert {qn: blob for qn, (blob, _f, _s) in rows.items()} == legacy
        assert {fmt for _b, fmt, _s in rows.values()} == {"f32"}
        with _connect(db) as conn:
            assert (
                conn.execute(
                    "SELECT 1 FROM metadata WHERE key = ?",
                    (EMBEDDING_FORMAT_METADATA_KEY,),
                ).fetchone()
                is None
            )

        store = EmbeddingStore(db, backend)
        try:
            assert store.migrated_vectors == len(qns)
        finally:
            store.close()

    def test_unconvertible_rows_are_preserved(self, tmp_path):
        db = tmp_path / "vectors.db"
        nan_vec = [0.25] * 768
        nan_vec[0] = float("nan")
        with _connect(db) as conn:
            conn.executescript(_LEGACY_EMBEDDINGS_DDL)
            conn.executemany(
                "INSERT INTO embeddings (qualified_name, vector, text_hash, provider) "
                "VALUES (?, ?, ?, ?)",
                [
                    ("nan", _encode_vector(nan_vec), "h", _PROVIDER),
                    ("ragged", b"\x00" * 10, "h", _PROVIDER),
                    ("empty", b"", "h", _PROVIDER),
                    ("ok", _encode_vector([0.5] * 768), "h", _PROVIDER),
                ],
            )
            before = {
                qn: bytes(blob)
                for qn, blob in conn.execute(
                    "SELECT qualified_name, vector FROM embeddings"
                )
            }
        store = EmbeddingStore(db)
        try:
            assert store.migrated_vectors == 1
            assert store.count() == 4
        finally:
            store.close()
        rows = _rows(db)
        for qn in ("nan", "ragged", "empty"):
            assert rows[qn] == (before[qn], "f32", None)
        assert rows["ok"][1] == "i8"

    def test_only_unconvertible_rows_leave_the_database_unchanged(self, tmp_path):
        db = tmp_path / "vectors.db"
        inf_vec = [0.25] * 768
        inf_vec[5] = float("inf")
        with _connect(db) as conn:
            conn.executescript(_LEGACY_EMBEDDINGS_DDL)
            conn.executemany(
                "INSERT INTO embeddings (qualified_name, vector, text_hash, provider) "
                "VALUES (?, ?, ?, ?)",
                [
                    ("inf", _encode_vector(inf_vec), "h", _PROVIDER),
                    ("ragged", b"\x00" * 6, "h", _PROVIDER),
                ],
            )
            legacy = {
                qn: bytes(blob)
                for qn, blob in conn.execute(
                    "SELECT qualified_name, vector FROM embeddings"
                )
            }
        for _ in range(2):
            store = EmbeddingStore(db)
            try:
                assert store.migrated_vectors == 0
                assert store.count() == 2
            finally:
                store.close()
            assert _rows(db) == {qn: (blob, "f32", None) for qn, blob in legacy.items()}

    def test_ragged_float32_rows_are_reembedded(self, tmp_path):
        db = tmp_path / "vectors.db"
        with _connect(db) as conn:
            conn.executescript(_LEGACY_EMBEDDINGS_DDL)
        docs = _unit_vectors(1, 768, seed=9)
        backend = _FixedBackend({"fn0": docs[0].tolist()}, {"q": docs[0].tolist()})
        store = EmbeddingStore(db, backend)
        try:
            store._conn.execute(
                "INSERT INTO embeddings (qualified_name, vector, text_hash, provider) "
                "VALUES (?, ?, ?, ?)",
                ("m.py::fn0", b"\x00" * 10, "stale", _PROVIDER),
            )
            store._conn.commit()
            with pytest.raises(ValueError, match="incompatible"):
                store.search("q")
            assert store.embed_nodes([_node("fn0")]) == 1
            assert store.search("q", limit=1)[0][1] == pytest.approx(1.0, abs=1e-3)
        finally:
            store.close()

    def test_no_metadata_table_is_created_for_bare_vector_stores(self, tmp_path):
        db = tmp_path / "vectors.db"
        EmbeddingStore(db).close()
        with _connect(db) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "metadata" not in tables

    def test_version_recorded_on_fresh_graph_db(self, tmp_path):
        db = tmp_path / "graph.db"
        GraphStore(db).close()
        EmbeddingStore(db).close()
        EmbeddingStore(db).close()
        with _connect(db) as conn:
            rows = conn.execute(
                "SELECT value FROM metadata WHERE key = ?",
                (EMBEDDING_FORMAT_METADATA_KEY,),
            ).fetchall()
        assert rows == [(EMBEDDING_FORMAT_VERSION,)]

    def test_migration_shrinks_the_database(self, tmp_path):
        db = tmp_path / "graph.db"
        _write_legacy_graph_db(db, _unit_vectors(1000, 768, seed=10))
        before = _vacuumed_size(db)
        EmbeddingStore(db).close()
        after = _vacuumed_size(db)
        assert after <= 0.4 * before
