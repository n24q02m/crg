"""Offline benchmark for int8 embedding storage in ``.crg/graph.db``.

For 768 and 1024 dimensions it builds a graph.db in the float32 layout of
earlier releases, opens it with the current ``EmbeddingStore`` (which converts
every vector to int8 in place), and records:

* database size before and after the conversion, and after ``VACUUM``;
* the size of a graph.db written as int8 from the start;
* the size of the same graph without any embeddings, so the bytes used by
  the vectors themselves can be separated from the rest of the graph;
* how far int8 cosine scores drift from exact float32 cosine, and how often
  the top-k results agree.

Vectors come from a fixed NumPy seed and an in-process embedding stub, so the
run makes no network calls and the sizes are identical on every run. Run::

    uv run python benchmarks/run_embedding_storage_benchmark.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from crg.embeddings import EmbeddingStore, _encode_vector
from crg.graph import GraphNode, GraphStore
from crg.parser import NodeInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = ROOT / "benchmarks" / "embedding_storage_report.json"
REPRODUCIBLE_COMMAND = "uv run python benchmarks/run_embedding_storage_benchmark.py"

VECTOR_COUNT = 5000
QUERY_COUNT = 100
TOP_K = 10
DIMENSIONS = (768, 1024)
PROVIDER = "benchmark-fixed-backend"
# Detached HEAD for the throwaway repository that holds each graph.db.
_FIXTURE_HEAD = "0123456789abcdef0123456789abcdef01234567"

# Layout written by the float32-only releases.
_LEGACY_EMBEDDINGS_DDL = """
CREATE TABLE IF NOT EXISTS embeddings (
    qualified_name TEXT PRIMARY KEY,
    vector BLOB NOT NULL,
    text_hash TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown'
);
"""


class _FixedBackend:
    """Embedding stub mapping node and query text to fixed vectors."""

    name = PROVIDER

    def __init__(self, docs: dict[str, list[float]], queries: dict[str, list[float]]):
        self._docs = docs
        self._queries = queries

    def embed_texts(self, texts, dimensions: int | None = 768):
        return [self._docs[text.split()[0]] for text in texts]

    def embed_single(self, text, dimensions: int | None = 768):
        return self._queries[text]

    def embed_single_query(self, text, dimensions: int | None = 768):
        return self._queries[text]


def _vectors(count: int, dims: int, *, seed: int, outliers: bool) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mat = rng.standard_normal((count, dims)).astype(np.float32)
    if outliers:
        # A few dominant channels, as real embedding models have.
        mat[:, :4] *= 8.0
    return mat / np.linalg.norm(mat, axis=1, keepdims=True)


def _queries(docs: np.ndarray, count: int, *, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    picks = docs[rng.integers(0, len(docs), count)]
    noise = rng.standard_normal(picks.shape).astype(np.float32)
    mat = picks + 0.5 * noise / np.sqrt(docs.shape[1])
    return mat / np.linalg.norm(mat, axis=1, keepdims=True)


def _names(count: int) -> list[str]:
    return [f"fn{i:05d}" for i in range(count)]


def _graph_node(name: str) -> GraphNode:
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


def _new_repo(base: Path, label: str) -> Path:
    repo = base / label
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text(_FIXTURE_HEAD + "\n", encoding="utf-8")
    (repo / ".crg").mkdir()
    return repo / ".crg" / "graph.db"


def _graph_only(db: Path, names: list[str]) -> None:
    store = GraphStore(db)
    try:
        for name in names:
            store.upsert_node(NodeInfo("Function", name, "m.py", 1, 2, "python"))
        store.commit()
    finally:
        store.close()


def _write_legacy(db: Path, names: list[str], docs: np.ndarray) -> None:
    _graph_only(db, names)
    with sqlite3.connect(db) as conn:
        conn.executescript(_LEGACY_EMBEDDINGS_DDL)
        conn.executemany(
            "INSERT INTO embeddings (qualified_name, vector, text_hash, provider) "
            "VALUES (?, ?, ?, ?)",
            [
                (f"m.py::{name}", _encode_vector(vec.tolist()), "h", PROVIDER)
                for name, vec in zip(names, docs, strict=True)
            ],
        )


def _size(db: Path, *, vacuum: bool) -> int:
    """Bytes used by the database; WAL content is checkpointed first."""
    conn = sqlite3.connect(db)
    try:
        if vacuum:
            conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    finally:
        conn.close()
    return int(pages * page_size)


def _formats(db: Path) -> dict[str, int]:
    with sqlite3.connect(db) as conn:
        return dict(
            conn.execute(
                "SELECT vector_format, COUNT(*) FROM embeddings GROUP BY vector_format"
            ).fetchall()
        )


def _accuracy(store: EmbeddingStore, docs: np.ndarray, queries: np.ndarray) -> dict:
    names = [f"m.py::{n}" for n in _names(len(docs))]
    reference = queries @ docs.T
    max_error = 0.0
    error_sum = 0.0
    error_count = 0
    top1_hits = 0
    overlaps: list[float] = []
    for i in range(len(queries)):
        got = dict(store.search(f"q{i}", limit=len(docs)))
        expected = dict(zip(names, reference[i].tolist(), strict=True))
        errors = [abs(got[qn] - expected[qn]) for qn in names]
        max_error = max(max_error, max(errors))
        error_sum += sum(errors)
        error_count += len(errors)
        top_got = sorted(got, key=got.__getitem__, reverse=True)[:TOP_K]
        top_ref = sorted(expected, key=expected.__getitem__, reverse=True)[:TOP_K]
        top1_hits += top_got[0] == top_ref[0]
        overlaps.append(len(set(top_got) & set(top_ref)) / TOP_K)
    return {
        "max_abs_cosine_error": round(max_error, 6),
        "mean_abs_cosine_error": round(error_sum / error_count, 7),
        "top1_agreement": round(top1_hits / len(queries), 4),
        f"top{TOP_K}_overlap_mean": round(sum(overlaps) / len(overlaps), 4),
        f"top{TOP_K}_overlap_min": round(min(overlaps), 4),
    }


def _run_dims(base: Path, dims: int) -> dict:
    names = _names(VECTOR_COUNT)
    docs = _vectors(VECTOR_COUNT, dims, seed=dims, outliers=True)
    queries = _queries(docs, QUERY_COUNT, seed=dims + 1)
    backend = _FixedBackend(
        {n: v.tolist() for n, v in zip(names, docs, strict=True)},
        {f"q{i}": q.tolist() for i, q in enumerate(queries)},
    )

    graph_db = _new_repo(base, f"graph-{dims}")
    _graph_only(graph_db, names)
    graph_bytes = _size(graph_db, vacuum=True)

    legacy_db = _new_repo(base, f"legacy-{dims}")
    _write_legacy(legacy_db, names, docs)
    legacy_bytes = _size(legacy_db, vacuum=True)

    started = time.perf_counter()
    store = EmbeddingStore(legacy_db, backend)
    migration_seconds = time.perf_counter() - started
    store.dimensions = dims
    try:
        migrated = store.migrated_vectors
        accuracy = _accuracy(store, docs, queries)
    finally:
        store.close()
    in_place_bytes = _size(legacy_db, vacuum=False)
    formats = _formats(legacy_db)
    vacuumed_bytes = _size(legacy_db, vacuum=True)

    fresh_db = _new_repo(base, f"fresh-{dims}")
    _graph_only(fresh_db, names)
    store = EmbeddingStore(fresh_db, backend)
    store.dimensions = dims
    try:
        store.embed_nodes([_graph_node(n) for n in names])
    finally:
        store.close()
    fresh_bytes = _size(fresh_db, vacuum=True)

    f32_payload = legacy_bytes - graph_bytes
    i8_payload = vacuumed_bytes - graph_bytes
    return {
        "dimensions": dims,
        "vectors": VECTOR_COUNT,
        "vectors_migrated": migrated,
        "rows_by_format_after_migration": formats,
        "migration_seconds": round(migration_seconds, 3),
        "bytes": {
            "graph_without_embeddings": graph_bytes,
            "float32_before_migration": legacy_bytes,
            "int8_after_migration_before_vacuum": in_place_bytes,
            "int8_after_migration_and_vacuum": vacuumed_bytes,
            "int8_written_fresh": fresh_bytes,
        },
        "database_size_ratio": round(vacuumed_bytes / legacy_bytes, 4),
        "embedding_bytes": {
            "float32": f32_payload,
            "int8": i8_payload,
            "ratio": round(i8_payload / f32_payload, 4),
        },
        "accuracy_vs_float32": accuracy,
    }


def run_benchmark(output_path: Path | None = DEFAULT_REPORT_PATH) -> dict:
    base = Path(tempfile.mkdtemp(prefix="crg-embedding-bench-"))
    try:
        results = [_run_dims(base, dims) for dims in DIMENSIONS]
    finally:
        shutil.rmtree(base, ignore_errors=True)
    report = {
        "benchmark": "embedding_int8_storage_offline",
        "reproducible_command": REPRODUCIBLE_COMMAND,
        "vector_generator": "unit Gaussian, 4 channels scaled x8, seed = dimensions",
        "queries": QUERY_COUNT,
        "results": results,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    out = Path(argv[1]) if argv and len(argv) > 1 else DEFAULT_REPORT_PATH
    print(json.dumps(run_benchmark(out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
