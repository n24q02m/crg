"""Concurrent GraphStore opens on one fresh DB must not race alembic's proxy."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from crg.graph import GraphStore


def test_concurrent_graph_store_open_on_fresh_db(tmp_path):
    db = tmp_path / "graph.db"

    def open_and_close() -> None:
        GraphStore(db).close()

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(open_and_close) for _ in range(16)]
        for future in futures:
            future.result()
