# Benchmarks (`crg`)

All measurements below were produced deterministically offline via
`uv run python benchmarks/run_scip_benchmark.py` (no external network or LLM
calls) and recorded in `benchmarks/scip_benchmark_report.json`.

## Offline SCIP Ground-Truth Call Resolution (`CRG-28`)

The benchmark evaluates resolved intra-repository `CALLS` edges across three
pipeline stages on a multi-file Python + TypeScript fixture repository containing
aliased imports (`from pkg.alpha import shared_helper as alpha_helper`),
typed receivers (`engine: Engine -> engine.run()`), and `tsconfig.json` path
mappings (`@lib/math`):

| Stage | True Positives | False Positives | False Negatives | Precision | Recall | F1 |
|-------|---------------:|----------------:|----------------:|----------:|-------:|---:|
| `syntactic_baseline` | 1 | 0 | 2 | 1.0000 | 0.3333 | 0.5000 |
| `intra_repo_3phase` | 3 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| `scip_import` | 3 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |

`intra_repo_3phase` breakdown on the fixture: `import_traced = 1`,
`type_inferred = 1`, `dynamic_dispatch = 0`.
`scip_import` breakdown on the fixture: `documents = 4`, `nodes_upserted = 10`,
`edges_upserted = 9`.

To reproduce:

```bash
uv run python benchmarks/run_scip_benchmark.py
```
