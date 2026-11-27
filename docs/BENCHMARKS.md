# Benchmarks (`crg`)

All measurements below were produced deterministically offline via
`uv run python benchmarks/run_scip_benchmark.py` (no external network or LLM
calls) and recorded in `benchmarks/scip_benchmark_report.json`.

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
