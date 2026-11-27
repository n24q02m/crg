# Benchmarks (`crg`)

The SCIP measurements below were produced deterministically offline via
`uv run python benchmarks/run_scip_benchmark.py` (no external network or LLM
calls) and recorded in `benchmarks/scip_benchmark_report.json`. The embedding
storage and community detection sections were produced the same way by their
own scripts, named in each section.

## Offline SCIP Ground-Truth Call Resolution (`CRG-28` / `A11.8`)

The benchmark evaluates resolved intra-repository `CALLS` edges across three
pipeline stages on a deterministic 4-language corpus (**Python, TypeScript, Go,
Rust**) comprising **121** ground-truth edges (including **32** polymorphic
dynamic-dispatch edges, aliased module imports, `tsconfig.json` path mappings,
typed receivers, embedded Go structs, and Rust trait implementations).

### Stage Summary

| Stage | True Positives | False Positives | False Negatives | Precision | Recall | F1 | Runtime (ms) |
|-------|---------------:|----------------:|----------------:|----------:|-------:|---:|-------------:|
| `syntactic_baseline` | 55 | 0 | 66 | 1.0000 | 0.4545 | 0.6250 | 835.48 |
| `intra_repo_3phase` | 93 | 0 | 28 | 1.0000 | 0.7686 | 0.8692 | 143.54 |
| `scip_import` | 121 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | 163.83 |

Total benchmark wall-clock time (fixture generation + 3 stages): `1863.13 ms`.

`intra_repo_3phase` resolution breakdown: `import_traced = 18`,
`type_inferred = 12`, `dynamic_dispatch = 12`.
`scip_import` breakdown: `documents = 12`, `nodes_upserted = 92`,
`edges_upserted = 201`.

### Per-Language Ground-Truth & F1 Breakdown

| Language | Ground-Truth Edges | Dynamic Dispatch Edges | `syntactic_baseline` F1 | `intra_repo_3phase` F1 | `scip_import` F1 |
|----------|-------------------:|-----------------------:|------------------------:|-----------------------:|-----------------:|
| Python | 30 | 8 | 0.4615 | 0.9655 | 1.0000 |
| TypeScript | 30 | 8 | 0.4615 | 0.9655 | 1.0000 |
| Go | 30 | 8 | 0.7500 | 0.7500 | 1.0000 |
| Rust | 31 | 8 | 0.7600 | 0.7600 | 1.0000 |
| **Total** | **121** | **32** | **0.6250** | **0.8692** | **1.0000** |

To reproduce:

```bash
uv run python benchmarks/run_scip_benchmark.py
```

## int8 Embedding Storage

Measured by `benchmarks/run_embedding_storage_benchmark.py` and recorded in
`benchmarks/embedding_storage_report.json`. For each stored width, 5,000 unit
vectors (Gaussian, with four channels scaled by 8 to imitate the outlier
dimensions of real embedding models, seed = width) are written as float32 rows
in the layout older releases used, next to 5,000 graph nodes. Opening the
database with `EmbeddingStore` then converts them to int8 in place. Accuracy is
compared against exact float32 cosine for 100 queries, top 10.

### Database Size (bytes)

| State | 768 dimensions | 1024 dimensions |
|-------|---------------:|----------------:|
| Graph only, no embeddings | 1,966,080 | 1,966,080 |
| float32 rows (older releases) | 22,605,824 | 25,128,960 |
| After in-place conversion, before `VACUUM` | 22,605,824 | 25,128,960 |
| After conversion and `VACUUM` | 7,213,056 | 8,925,184 |
| int8 rows written by a fresh embed | 7,213,056 | 8,925,184 |
| **Whole database, int8 / float32** | **0.319** | **0.355** |
| **Embedding rows only, int8 / float32** | **0.254** | **0.300** |

The conversion rewrites rows inside the existing file, so SQLite keeps the freed
pages until `sqlite3 .crg/graph.db "VACUUM"` is run; after that the converted
database is byte-for-byte the size of one embedded as int8 from the start.

### Accuracy Against float32

| Metric | 768 dimensions | 1024 dimensions |
|--------|---------------:|----------------:|
| Max absolute cosine error | 0.00599 | 0.00553 |
| Mean absolute cosine error | 0.00064 | 0.00057 |
| Top-1 agreement | 100% | 100% |
| Top-10 overlap, mean (min) | 0.972 (0.9) | 0.976 (0.9) |
| Conversion time for 5,000 rows | 0.53 s | 0.44 s |

To reproduce:

```bash
uv run python benchmarks/run_embedding_storage_benchmark.py
```

## Leiden Community Detection

Measured by `benchmarks/run_leiden_benchmark.py` and recorded in
`benchmarks/leiden_benchmark_report.json` (Python 3.14.6, NetworkX 3.7). Every
graph comes from a fixed seed. Timings were taken on a shared, busy machine, so
read them as relative; every other number is identical between runs.

### Modularity on Reference Graphs (10 seeds, best / mean)

| Graph | Nodes | Edges | `crg` Leiden | NetworkX Louvain | NetworkX Leiden | Communities (`crg`) |
|-------|------:|------:|-------------:|-----------------:|----------------:|--------------------:|
| Zachary karate club | 34 | 78 | 0.4198 / 0.4198 | 0.4198 / 0.4177 | 0.4198 / 0.4185 | 4 |
| Karate club, weighted | 34 | 78 | 0.4449 / 0.4448 | 0.4449 / 0.4413 | 0.4449 / 0.4442 | 4 |
| Ring of 8 cliques of 5 | 40 | 88 | 0.7841 / 0.7841 | 0.7841 / 0.7841 | 0.7841 / 0.7841 | 8 |
| Les Miserables, weighted | 77 | 254 | 0.5667 / 0.5666 | 0.5667 / 0.5657 | 0.5667 / 0.5664 | 6 |

The modularity `crg` reports for its partitions matches
`networkx.community.modularity` to within `1e-12` on every graph above.

### Connected Communities

On 20 `powerlaw_cluster_graph(1000, 2, 0.1)` graphs (seeds 0-19), `crg` found
396 communities and none was internally disconnected. NetworkX Louvain found
402 communities on the same graphs and also returned none disconnected there,
so this benchmark does not separate the two; the connectivity guarantee comes
from the refinement phase and is checked by the test suite, including a case
where refinement must split a community into its two connected halves.

### Scaling (`barabasi_albert_graph(n, 3, seed=1)`)

| Nodes | Edges | 10-pass limit (default): s / modularity / passes | Until converged: s / modularity / passes | NetworkX Louvain: s / modularity |
|------:|------:|-------------------------------------------------:|-----------------------------------------:|---------------------------------:|
| 1,000 | 2,991 | 0.44 / 0.4191 / 10 | 0.55 / 0.4199 / 16 | 0.41 / 0.3888 |
| 10,000 | 29,991 | 5.78 / 0.4200 / 10 | 16.91 / 0.4215 / 33 | 14.74 / 0.3874 |
| 50,000 | 149,991 | 43.80 / 0.4179 / 10 | not run | not run |

`query communities` uses the 10-pass limit and reports `converged: false` when
the limit stopped a search that was still improving.

To reproduce:

```bash
uv run python benchmarks/run_leiden_benchmark.py
```
