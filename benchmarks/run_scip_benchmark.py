"""Offline SCIP ground-truth call resolution benchmark (CRG-28).

Builds a deterministic temporary Python + TypeScript fixture repository with
cross-module imports, aliased symbols, typed receivers, and polymorphic
inheritance, then compares call-edge precision and recall across:

1. ``syntactic_baseline``: Tree-sitter parse + ``resolve_bare_calls()``.
2. ``intra_repo_3phase``: Baseline + ``resolve_intra_repo_calls()``.
3. ``scip_import``: Ground-truth SCIP index ingestion via ``import_scip_index()``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from crg.graph import GraphStore  # noqa: E402
from crg.parser import CodeParser  # noqa: E402
from crg.resolver.intra_repo import resolve_intra_repo_calls  # noqa: E402
from crg.scip import import_scip_index  # noqa: E402


def _create_fixture_repo(
    root: Path,
) -> tuple[Path, set[tuple[str, str]], dict[str, object]]:
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "ts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / "ts" / "app").mkdir(parents=True, exist_ok=True)

    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "alpha.py").write_text(
        "def shared_helper() -> int:\n"
        "    return 1\n\n"
        "class Engine:\n"
        "    def run(self) -> int:\n"
        "        return 10\n",
        encoding="utf-8",
    )
    (root / "pkg" / "beta.py").write_text(
        "def shared_helper() -> int:\n"
        "    return 2\n\n"
        "class SubEngine:\n"
        "    def run(self) -> int:\n"
        "        return 20\n",
        encoding="utf-8",
    )
    (root / "pkg" / "service.py").write_text(
        "from pkg.alpha import shared_helper as alpha_helper\n"
        "from pkg.alpha import Engine\n\n"
        "def execute(engine: Engine) -> int:\n"
        "    base_val = alpha_helper()\n"
        "    return base_val + engine.run()\n",
        encoding="utf-8",
    )

    (root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {"@lib/*": ["ts/lib/*"]},
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "ts" / "lib" / "math.ts").write_text(
        "export function normalizeScore(x: number): number {\n  return x / 10;\n}\n",
        encoding="utf-8",
    )
    (root / "ts" / "app" / "main.ts").write_text(
        "import { normalizeScore } from '@lib/math';\n\n"
        "export function runApp(v: number): number {\n"
        "  return normalizeScore(v);\n"
        "}\n",
        encoding="utf-8",
    )

    alpha_fp = str((root / "pkg" / "alpha.py").resolve())
    service_fp = str((root / "pkg" / "service.py").resolve())
    ts_lib_fp = str((root / "ts" / "lib" / "math.ts").resolve())
    ts_app_fp = str((root / "ts" / "app" / "main.ts").resolve())

    expected_calls = {
        (f"{service_fp}::execute", f"{alpha_fp}::shared_helper"),
        (f"{service_fp}::execute", f"{alpha_fp}::Engine.run"),
        (f"{ts_app_fp}::runApp", f"{ts_lib_fp}::normalizeScore"),
    }

    scip_payload: dict[str, object] = {
        "documents": [
            {
                "relative_path": "pkg/alpha.py",
                "language": "python",
                "occurrences": [
                    {
                        "range": [0, 4, 0, 17],
                        "symbol": "scip-python pkg alpha/shared_helper().",
                        "symbol_roles": 1,
                    },
                    {
                        "range": [3, 6, 3, 12],
                        "symbol": "scip-python pkg alpha/Engine#",
                        "symbol_roles": 1,
                    },
                    {
                        "range": [4, 8, 4, 11],
                        "symbol": "scip-python pkg alpha/Engine#run().",
                        "symbol_roles": 1,
                    },
                ],
            },
            {
                "relative_path": "pkg/service.py",
                "language": "python",
                "occurrences": [
                    {
                        "range": [3, 4, 3, 11],
                        "symbol": "scip-python pkg service/execute().",
                        "symbol_roles": 1,
                    },
                    {
                        "range": [4, 15, 4, 27],
                        "symbol": "scip-python pkg alpha/shared_helper().",
                        "symbol_roles": 0,
                    },
                    {
                        "range": [5, 29, 5, 32],
                        "symbol": "scip-python pkg alpha/Engine#run().",
                        "symbol_roles": 0,
                    },
                ],
            },
            {
                "relative_path": "ts/lib/math.ts",
                "language": "typescript",
                "occurrences": [
                    {
                        "range": [0, 16, 0, 30],
                        "symbol": "scip-ts ts lib/math/normalizeScore().",
                        "symbol_roles": 1,
                    }
                ],
            },
            {
                "relative_path": "ts/app/main.ts",
                "language": "typescript",
                "occurrences": [
                    {
                        "range": [2, 16, 2, 22],
                        "symbol": "scip-ts ts app/main/runApp().",
                        "symbol_roles": 1,
                    },
                    {
                        "range": [3, 9, 3, 23],
                        "symbol": "scip-ts ts lib/math/normalizeScore().",
                        "symbol_roles": 0,
                    },
                ],
            },
        ]
    }
    return root, expected_calls, scip_payload


def _score(
    predicted: set[tuple[str, str]], ground_truth: set[tuple[str, str]]
) -> dict[str, float | int]:
    tp = len(predicted & ground_truth)
    fp = len(predicted - ground_truth)
    fn = len(ground_truth - predicted)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    )
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _collect_resolved_calls(store: GraphStore) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    rows = store._conn.execute(
        "SELECT e.source_qualified, e.target_qualified "
        "FROM edges e "
        "JOIN nodes n ON e.target_qualified = n.qualified_name AND n.valid_to_sha IS NULL "
        "WHERE e.kind = 'CALLS' AND e.valid_to_sha IS NULL"
    )
    for row in rows:
        pairs.add((str(row["source_qualified"]), str(row["target_qualified"])))
    return pairs


def _populate_parsed_repo(store: GraphStore, root: Path) -> None:
    parser = CodeParser()
    for path in sorted(root.rglob("*")):
        if path.is_file() and parser.detect_language(path) is not None:
            nodes, edges = parser.parse_file(path)
            store.store_file_nodes_edges(str(path), nodes, edges)
    store.resolve_bare_calls()
    store.commit()


def _init_git_repo(root: Path) -> None:
    for cmd in (
        ["git", "-C", str(root), "init", "-q"],
        ["git", "-C", str(root), "config", "user.email", "bench@example.invalid"],
        ["git", "-C", str(root), "config", "user.name", "Bench"],
        ["git", "-C", str(root), "add", "."],
        ["git", "-C", str(root), "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, capture_output=True)


def run_benchmark(output_path: Path | None = None) -> dict[str, object]:
    """Execute the deterministic offline benchmark and return metrics."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp).resolve()
        _, ground_truth, scip_payload = _create_fixture_repo(root)
        _init_git_repo(root)

        # Stage 1: syntactic baseline
        db1 = GraphStore(root / "baseline.db")
        try:
            _populate_parsed_repo(db1, root)
            baseline_calls = _collect_resolved_calls(db1)
            baseline_metrics = _score(baseline_calls, ground_truth)
        finally:
            db1.close()

        # Stage 2: 3-phase intra-repo resolution
        db2 = GraphStore(root / "intra.db")
        try:
            _populate_parsed_repo(db2, root)
            resolution_counts = resolve_intra_repo_calls(db2, root)
            intra_calls = _collect_resolved_calls(db2)
            intra_metrics = _score(intra_calls, ground_truth)
        finally:
            db2.close()

        # Stage 3: exact SCIP index import
        scip_file = root / "index.scip.json"
        scip_file.write_text(json.dumps(scip_payload), encoding="utf-8")
        db3 = GraphStore(root / "scip.db")
        try:
            scip_summary = import_scip_index(db3, scip_file, repo_root=root)
            scip_summary = {**scip_summary, "scip_path": scip_file.name}
            scip_calls = _collect_resolved_calls(db3)
            scip_metrics = _score(scip_calls, ground_truth)
        finally:
            db3.close()

    report: dict[str, object] = {
        "benchmark": "scip_call_resolution_offline",
        "ground_truth_edges": len(ground_truth),
        "stages": {
            "syntactic_baseline": baseline_metrics,
            "intra_repo_3phase": {
                **intra_metrics,
                "resolution_counts": resolution_counts,
            },
            "scip_import": {
                **scip_metrics,
                "import_summary": scip_summary,
            },
        },
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    out = _REPO_ROOT / "benchmarks" / "scip_benchmark_report.json"
    report = run_benchmark(output_path=out)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
