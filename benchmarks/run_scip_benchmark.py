"""Reproducible offline SCIP call-resolution benchmark across 4 languages.

Measures precision, recall, F1, and wall-clock latency across three call
resolution stages on a deterministic multilingual corpus (**Python, TypeScript,
Go, Rust**) with ``>= 100`` ground-truth ``CALLS`` edges including cross-file
imports, aliased symbols, typed receivers, and polymorphic dynamic dispatch:

1. ``syntactic_baseline``: tree-sitter AST extraction + same-file name match.
2. ``intra_repo_3phase``: 3-phase intra-repo resolver (imports + types +
   dynamic dispatch).
3. ``scip_import``: deterministic SCIP compiler-index import into the graph.

Run directly with::

    uv run python benchmarks/run_scip_benchmark.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from crg.graph import GraphStore
from crg.parser import CodeParser
from crg.resolver.intra_repo import resolve_intra_repo_calls
from crg.scip import import_scip_index

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = ROOT / "benchmarks" / "scip_benchmark_report.json"
REPRODUCIBLE_COMMAND = "uv run python benchmarks/run_scip_benchmark.py"


@dataclass(frozen=True)
class _GroundTruthEdge:
    language: str
    caller_file: str
    caller_symbol: str
    callee_file: str
    callee_symbol: str
    is_dynamic_dispatch: bool = False

    def scip_symbol(self, file_rel: str, sym: str) -> str:
        mod = file_rel.rsplit(".", 1)[0]
        if "." in sym:
            cls, method = sym.split(".", 1)
            return f"scip-bench pkg {mod} {cls}#{method}()."
        return f"scip-bench pkg {mod} {sym}()."


def _score(
    predicted: set[tuple[str, str]], ground_truth: set[tuple[str, str]]
) -> dict[str, float | int]:
    tp = len(predicted & ground_truth)
    fp = len(predicted - ground_truth)
    fn = len(ground_truth - predicted)
    precision = round(tp / (tp + fp), 4) if (tp + fp) else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) else 0.0
    f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if (precision + recall)
        else 0.0
    )
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def _collect_resolved_calls(store: GraphStore) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    rows = store._conn.execute(
        "SELECT e.source_qualified, e.target_qualified "
        "FROM edges e "
        "JOIN nodes n ON e.target_qualified = n.qualified_name AND n.valid_to_sha IS NULL "
        "WHERE e.kind = 'CALLS' AND e.valid_to_sha IS NULL AND n.kind = 'Function'"
    )
    for row in rows:
        pairs.add((str(row["source_qualified"]), str(row["target_qualified"])))
    return pairs


def _populate_parsed_repo(repo_root: Path, store: GraphStore) -> None:
    parser = CodeParser()
    for file_path in sorted(repo_root.rglob("*")):
        if not file_path.is_file() or file_path.suffix not in {
            ".py",
            ".ts",
            ".go",
            ".rs",
        }:
            continue
        nodes, edges = parser.parse_file(file_path)
        store.store_file_nodes_edges(str(file_path), nodes, edges)


def _init_git_repo(repo_root: Path) -> None:
    import subprocess

    subprocess.run(
        ["git", "init"],
        cwd=str(repo_root),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "config", "user.email", "bench@example.com"],
        cwd=str(repo_root),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "config", "user.name", "Benchmark"],
        cwd=str(repo_root),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=str(repo_root),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo_root),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _find_line(text: str, marker: str) -> int:
    for idx, line in enumerate(text.splitlines()):
        if marker in line:
            return idx
    raise ValueError(f"Marker {marker!r} not found in generated corpus file")


def _build_python_corpus(files: dict[str, str]) -> list[_GroundTruthEdge]:
    edges: list[_GroundTruthEdge] = []
    helpers = "\n".join(
        f"def py_h{i}(v: int) -> int:\n    return v + {i}\n" for i in range(1, 9)
    )
    files["py_mod/__init__.py"] = ""
    files["py_mod/helpers.py"] = helpers + "\n"

    contracts_lines = [
        "from py_mod.helpers import py_h1, py_h2, py_h3, py_h4, py_h5, py_h6",
        "",
        "class PyHandler:",
        "    def handle(self, v: int) -> int:",
        "        return v",
        "",
        "    def validate(self, v: int) -> bool:",
        "        return v >= 0",
        "",
    ]
    subclasses = [
        ("FastPyHandler", 1, 2),
        ("SafePyHandler", 3, 4),
        ("AuditPyHandler", 5, 6),
    ]
    for cls_name, h_a, h_b in subclasses:
        contracts_lines.extend(
            [
                f"class {cls_name}(PyHandler):",
                "    def handle(self, v: int) -> int:",
                f"        return py_h{h_a}(v)",
                "",
                "    def validate(self, v: int) -> bool:",
                f"        return py_h{h_b}(v) > 0",
                "",
            ]
        )
        edges.append(
            _GroundTruthEdge(
                "python",
                "py_mod/contracts.py",
                f"{cls_name}.handle",
                "py_mod/helpers.py",
                f"py_h{h_a}",
            )
        )
        edges.append(
            _GroundTruthEdge(
                "python",
                "py_mod/contracts.py",
                f"{cls_name}.validate",
                "py_mod/helpers.py",
                f"py_h{h_b}",
            )
        )
    files["py_mod/contracts.py"] = "\n".join(contracts_lines)

    alias_imports = ", ".join(f"py_h{i} as ph{i}" for i in range(1, 9))
    direct_calls = "\n".join(f"    total += ph{i}(x)" for i in range(1, 9))
    pipeline_text = (
        f"from py_mod.helpers import {alias_imports}\n"
        "from py_mod.contracts import (\n"
        "    AuditPyHandler,\n"
        "    FastPyHandler,\n"
        "    PyHandler,\n"
        "    SafePyHandler,\n"
        ")\n\n"
        "def run_py_direct(x: int) -> int:\n"
        "    total = 0\n"
        f"{direct_calls}\n"
        "    return total\n\n"
        "def run_py_typed(x: int) -> int:\n"
        "    fast = FastPyHandler()\n"
        "    safe = SafePyHandler()\n"
        "    a = fast.handle(x)\n"
        "    b = fast.validate(x)\n"
        "    c = safe.handle(x)\n"
        "    d = safe.validate(x)\n"
        "    return a + c + (1 if (b and d) else 0)\n\n"
        "def dispatch_py_all(handler: PyHandler, x: int) -> int:\n"
        "    res = handler.handle(x)\n"
        "    ok = handler.validate(x)\n"
        "    return res if ok else 0\n\n"
        "def orchestrate_py(x: int) -> int:\n"
        "    d = run_py_direct(x)\n"
        "    t = run_py_typed(x)\n"
        "    p1 = dispatch_py_all(FastPyHandler(), x)\n"
        "    p2 = dispatch_py_all(SafePyHandler(), x)\n"
        "    p3 = dispatch_py_all(AuditPyHandler(), x)\n"
        "    return d + t + p1 + p2 + p3 + ph1(x)\n"
    )
    files["py_mod/pipeline.py"] = pipeline_text

    for i in range(1, 9):
        edges.append(
            _GroundTruthEdge(
                "python",
                "py_mod/pipeline.py",
                "run_py_direct",
                "py_mod/helpers.py",
                f"py_h{i}",
            )
        )
    for cls_name, m_name in [
        ("FastPyHandler", "handle"),
        ("FastPyHandler", "validate"),
        ("SafePyHandler", "handle"),
        ("SafePyHandler", "validate"),
    ]:
        edges.append(
            _GroundTruthEdge(
                "python",
                "py_mod/pipeline.py",
                "run_py_typed",
                "py_mod/contracts.py",
                f"{cls_name}.{m_name}",
            )
        )
    for cls_name in ["PyHandler", "FastPyHandler", "SafePyHandler", "AuditPyHandler"]:
        for m_name in ["handle", "validate"]:
            edges.append(
                _GroundTruthEdge(
                    "python",
                    "py_mod/pipeline.py",
                    "dispatch_py_all",
                    "py_mod/contracts.py",
                    f"{cls_name}.{m_name}",
                    is_dynamic_dispatch=True,
                )
            )
    for callee_f, callee_s in [
        ("py_mod/pipeline.py", "run_py_direct"),
        ("py_mod/pipeline.py", "run_py_typed"),
        ("py_mod/pipeline.py", "dispatch_py_all"),
        ("py_mod/helpers.py", "py_h1"),
    ]:
        edges.append(
            _GroundTruthEdge(
                "python", "py_mod/pipeline.py", "orchestrate_py", callee_f, callee_s
            )
        )
    return edges


def _build_typescript_corpus(files: dict[str, str]) -> list[_GroundTruthEdge]:
    edges: list[_GroundTruthEdge] = []
    files["tsconfig.json"] = json.dumps(
        {
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {"@ts/*": ["./ts_mod/*"]},
            }
        }
    )
    files["ts_mod/helpers.ts"] = (
        "\n".join(
            f"export function tsH{i}(v: number): number {{\n  return v + {i};\n}}\n"
            for i in range(1, 9)
        )
        + "\n"
    )

    contracts_lines = [
        "import { tsH1, tsH2, tsH3, tsH4, tsH5, tsH6 } from '@ts/helpers';",
        "",
        "export class TsEngine {",
        "  run(v: number): number {",
        "    return v;",
        "  }",
        "  check(v: number): boolean {",
        "    return v >= 0;",
        "  }",
        "}",
        "",
    ]
    for cls_name, h_a, h_b in [
        ("TurboTsEngine", 1, 2),
        ("EcoTsEngine", 3, 4),
        ("SafeTsEngine", 5, 6),
    ]:
        contracts_lines.extend(
            [
                f"export class {cls_name} extends TsEngine {{",
                "  run(v: number): number {",
                f"    return tsH{h_a}(v);",
                "  }",
                "  check(v: number): boolean {",
                f"    return tsH{h_b}(v) > 0;",
                "  }",
                "}",
                "",
            ]
        )
        edges.append(
            _GroundTruthEdge(
                "typescript",
                "ts_mod/contracts.ts",
                f"{cls_name}.run",
                "ts_mod/helpers.ts",
                f"tsH{h_a}",
            )
        )
        edges.append(
            _GroundTruthEdge(
                "typescript",
                "ts_mod/contracts.ts",
                f"{cls_name}.check",
                "ts_mod/helpers.ts",
                f"tsH{h_b}",
            )
        )
    files["ts_mod/contracts.ts"] = "\n".join(contracts_lines)

    alias_imports = ", ".join(f"tsH{i} as th{i}" for i in range(1, 9))
    direct_calls = "\n".join(f"  total += th{i}(x);" for i in range(1, 9))
    files["ts_mod/service.ts"] = (
        f"import {{ {alias_imports} }} from '@ts/helpers';\n"
        "import { EcoTsEngine, SafeTsEngine, TsEngine, TurboTsEngine } from '@ts/contracts';\n\n"
        "export function runTsDirect(x: number): number {\n"
        "  let total = 0;\n"
        f"{direct_calls}\n"
        "  return total;\n"
        "}\n\n"
        "export function runTsTyped(x: number): number {\n"
        "  const turbo = new TurboTsEngine();\n"
        "  const eco = new EcoTsEngine();\n"
        "  const a = turbo.run(x);\n"
        "  const b = turbo.check(x);\n"
        "  const c = eco.run(x);\n"
        "  const d = eco.check(x);\n"
        "  return a + c + (b && d ? 1 : 0);\n"
        "}\n\n"
        "export function dispatchTsAll(engine: TsEngine, x: number): number {\n"
        "  const res = engine.run(x);\n"
        "  const ok = engine.check(x);\n"
        "  return ok ? res : 0;\n"
        "}\n\n"
        "export function orchestrateTs(x: number): number {\n"
        "  return (\n"
        "    runTsDirect(x) +\n"
        "    runTsTyped(x) +\n"
        "    dispatchTsAll(new SafeTsEngine(), x) +\n"
        "    th1(x)\n"
        "  );\n"
        "}\n"
    )

    for i in range(1, 9):
        edges.append(
            _GroundTruthEdge(
                "typescript",
                "ts_mod/service.ts",
                "runTsDirect",
                "ts_mod/helpers.ts",
                f"tsH{i}",
            )
        )
    for cls_name, m_name in [
        ("TurboTsEngine", "run"),
        ("TurboTsEngine", "check"),
        ("EcoTsEngine", "run"),
        ("EcoTsEngine", "check"),
    ]:
        edges.append(
            _GroundTruthEdge(
                "typescript",
                "ts_mod/service.ts",
                "runTsTyped",
                "ts_mod/contracts.ts",
                f"{cls_name}.{m_name}",
            )
        )
    for cls_name in ["TsEngine", "TurboTsEngine", "EcoTsEngine", "SafeTsEngine"]:
        for m_name in ["run", "check"]:
            edges.append(
                _GroundTruthEdge(
                    "typescript",
                    "ts_mod/service.ts",
                    "dispatchTsAll",
                    "ts_mod/contracts.ts",
                    f"{cls_name}.{m_name}",
                    is_dynamic_dispatch=True,
                )
            )
    for callee_f, callee_s in [
        ("ts_mod/service.ts", "runTsDirect"),
        ("ts_mod/service.ts", "runTsTyped"),
        ("ts_mod/service.ts", "dispatchTsAll"),
        ("ts_mod/helpers.ts", "tsH1"),
    ]:
        edges.append(
            _GroundTruthEdge(
                "typescript", "ts_mod/service.ts", "orchestrateTs", callee_f, callee_s
            )
        )
    return edges


def _build_go_corpus(files: dict[str, str]) -> list[_GroundTruthEdge]:
    edges: list[_GroundTruthEdge] = []
    files["go_mod/helpers.go"] = "package gomod\n\n" + "\n".join(
        f"func goH{i}(v int) int {{\n\treturn v + {i}\n}}\n" for i in range(1, 9)
    )

    contracts_lines = [
        "package gomod",
        "",
        "type GoCodec struct{}",
        "",
        "func (b GoCodec) Encode(v int) int {",
        "\treturn v",
        "}",
        "",
        "func (b GoCodec) Verify(v int) bool {",
        "\treturn v >= 0",
        "}",
        "",
    ]
    for cls_name, h_a, h_b in [
        ("JsonCodec", 1, 2),
        ("XmlCodec", 3, 4),
        ("MsgCodec", 5, 6),
    ]:
        contracts_lines.extend(
            [
                f"type {cls_name} struct {{",
                "\tGoCodec",
                "}",
                "",
                f"func (c {cls_name}) Encode(v int) int {{",
                f"\treturn goH{h_a}(v)",
                "}",
                "",
                f"func (c {cls_name}) Verify(v int) bool {{",
                f"\treturn goH{h_b}(v) > 0",
                "}",
                "",
            ]
        )
        edges.append(
            _GroundTruthEdge(
                "go",
                "go_mod/contracts.go",
                f"{cls_name}.Encode",
                "go_mod/helpers.go",
                f"goH{h_a}",
            )
        )
        edges.append(
            _GroundTruthEdge(
                "go",
                "go_mod/contracts.go",
                f"{cls_name}.Verify",
                "go_mod/helpers.go",
                f"goH{h_b}",
            )
        )
    files["go_mod/contracts.go"] = "\n".join(contracts_lines)

    direct_calls = "\n".join(f"\ttotal += goH{i}(x)" for i in range(1, 9))
    files["go_mod/runner.go"] = (
        "package gomod\n\n"
        "func RunGoDirect(x int) int {\n"
        "\ttotal := 0\n"
        f"{direct_calls}\n"
        "\treturn total\n"
        "}\n\n"
        "func RunGoTyped(j JsonCodec, xm XmlCodec, x int) int {\n"
        "\ta := j.Encode(x)\n"
        "\tb := j.Verify(x)\n"
        "\tc := xm.Encode(x)\n"
        "\td := xm.Verify(x)\n"
        "\tif b && d {\n\t\treturn a + c\n\t}\n"
        "\treturn a\n"
        "}\n\n"
        "func DispatchGoAll(c GoCodec, x int) int {\n"
        "\tres := c.Encode(x)\n"
        "\tif c.Verify(x) {\n\t\treturn res\n\t}\n"
        "\treturn 0\n"
        "}\n\n"
        "func OrchestrateGo(x int) int {\n"
        "\treturn RunGoDirect(x) + RunGoTyped(JsonCodec{}, XmlCodec{}, x) + DispatchGoAll(GoCodec{}, x) + goH1(x)\n"
        "}\n"
    )

    for i in range(1, 9):
        edges.append(
            _GroundTruthEdge(
                "go", "go_mod/runner.go", "RunGoDirect", "go_mod/helpers.go", f"goH{i}"
            )
        )
    for cls_name, m_name in [
        ("JsonCodec", "Encode"),
        ("JsonCodec", "Verify"),
        ("XmlCodec", "Encode"),
        ("XmlCodec", "Verify"),
    ]:
        edges.append(
            _GroundTruthEdge(
                "go",
                "go_mod/runner.go",
                "RunGoTyped",
                "go_mod/contracts.go",
                f"{cls_name}.{m_name}",
            )
        )
    for cls_name in ["GoCodec", "JsonCodec", "XmlCodec", "MsgCodec"]:
        for m_name in ["Encode", "Verify"]:
            edges.append(
                _GroundTruthEdge(
                    "go",
                    "go_mod/runner.go",
                    "DispatchGoAll",
                    "go_mod/contracts.go",
                    f"{cls_name}.{m_name}",
                    is_dynamic_dispatch=True,
                )
            )
    for callee_f, callee_s in [
        ("go_mod/runner.go", "RunGoDirect"),
        ("go_mod/runner.go", "RunGoTyped"),
        ("go_mod/runner.go", "DispatchGoAll"),
        ("go_mod/helpers.go", "goH1"),
    ]:
        edges.append(
            _GroundTruthEdge(
                "go", "go_mod/runner.go", "OrchestrateGo", callee_f, callee_s
            )
        )
    return edges


def _build_rust_corpus(files: dict[str, str]) -> list[_GroundTruthEdge]:
    edges: list[_GroundTruthEdge] = []
    files["rs_mod/helpers.rs"] = (
        "\n".join(
            f"pub fn rs_h{i}(v: i32) -> i32 {{\n    v + {i}\n}}\n" for i in range(1, 9)
        )
        + "\n"
    )

    contracts_lines = [
        "use crate::helpers::{rs_h1, rs_h2, rs_h3, rs_h4, rs_h5, rs_h6, rs_h7, rs_h8};",
        "",
        "pub trait RsPolicy {",
        "    fn apply(&self, v: i32) -> i32;",
        "    fn audit(&self, v: i32) -> bool;",
        "}",
        "",
    ]
    for cls_name, h_a, h_b in [
        ("DefaultPolicy", 1, 2),
        ("FastPolicy", 3, 4),
        ("StrictPolicy", 5, 6),
        ("SafePolicy", 7, 8),
    ]:
        contracts_lines.extend(
            [
                f"pub struct {cls_name};",
                f"impl RsPolicy for {cls_name} {{",
                "    fn apply(&self, v: i32) -> i32 {",
                f"        rs_h{h_a}(v)",
                "    }",
                "    fn audit(&self, v: i32) -> bool {",
                f"        rs_h{h_b}(v) > 0",
                "    }",
                "}",
                "",
            ]
        )
        edges.append(
            _GroundTruthEdge(
                "rust",
                "rs_mod/contracts.rs",
                f"{cls_name}.apply",
                "rs_mod/helpers.rs",
                f"rs_h{h_a}",
            )
        )
        edges.append(
            _GroundTruthEdge(
                "rust",
                "rs_mod/contracts.rs",
                f"{cls_name}.audit",
                "rs_mod/helpers.rs",
                f"rs_h{h_b}",
            )
        )
    files["rs_mod/contracts.rs"] = "\n".join(contracts_lines)

    direct_calls = "\n".join(f"    total += rs_h{i}(x);" for i in range(1, 9))
    files["rs_mod/pipeline.rs"] = (
        "use crate::contracts::{DefaultPolicy, FastPolicy, RsPolicy, SafePolicy, StrictPolicy};\n"
        "use crate::helpers::{rs_h1, rs_h2, rs_h3, rs_h4, rs_h5, rs_h6, rs_h7, rs_h8};\n\n"
        "pub fn run_rs_direct(x: i32) -> i32 {\n"
        "    let mut total = 0;\n"
        f"{direct_calls}\n"
        "    total\n"
        "}\n\n"
        "pub fn run_rs_typed(d: &DefaultPolicy, f: &FastPolicy, x: i32) -> i32 {\n"
        "    let a = d.apply(x);\n"
        "    let b = d.audit(x);\n"
        "    let c = f.apply(x);\n"
        "    let e = f.audit(x);\n"
        "    if b && e { a + c } else { a }\n"
        "}\n\n"
        "pub fn dispatch_rs_all(policy: &dyn RsPolicy, x: i32) -> i32 {\n"
        "    let res = policy.apply(x);\n"
        "    if policy.audit(x) { res } else { 0 }\n"
        "}\n\n"
        "pub fn orchestrate_rs(x: i32) -> i32 {\n"
        "    let d = DefaultPolicy;\n"
        "    let f = FastPolicy;\n"
        "    let s = StrictPolicy;\n"
        "    let sf = SafePolicy;\n"
        "    run_rs_direct(x) + run_rs_typed(&d, &f, x) + dispatch_rs_all(&s, x) + dispatch_rs_all(&sf, x)\n"
        "}\n"
    )

    for i in range(1, 9):
        edges.append(
            _GroundTruthEdge(
                "rust",
                "rs_mod/pipeline.rs",
                "run_rs_direct",
                "rs_mod/helpers.rs",
                f"rs_h{i}",
            )
        )
    for cls_name, m_name in [
        ("DefaultPolicy", "apply"),
        ("DefaultPolicy", "audit"),
        ("FastPolicy", "apply"),
        ("FastPolicy", "audit"),
    ]:
        edges.append(
            _GroundTruthEdge(
                "rust",
                "rs_mod/pipeline.rs",
                "run_rs_typed",
                "rs_mod/contracts.rs",
                f"{cls_name}.{m_name}",
            )
        )
    for cls_name in ["DefaultPolicy", "FastPolicy", "StrictPolicy", "SafePolicy"]:
        for m_name in ["apply", "audit"]:
            edges.append(
                _GroundTruthEdge(
                    "rust",
                    "rs_mod/pipeline.rs",
                    "dispatch_rs_all",
                    "rs_mod/contracts.rs",
                    f"{cls_name}.{m_name}",
                    is_dynamic_dispatch=True,
                )
            )
    for callee_s in ["run_rs_direct", "run_rs_typed", "dispatch_rs_all"]:
        edges.append(
            _GroundTruthEdge(
                "rust",
                "rs_mod/pipeline.rs",
                "orchestrate_rs",
                "rs_mod/pipeline.rs",
                callee_s,
            )
        )
    return edges


def _def_marker(language: str, sym: str) -> str:
    bare = sym.split(".", 1)[-1]
    if language == "python":
        return f"def {bare}("
    if language == "typescript":
        if "." in sym:
            return f"  {bare}("
        return f"export function {bare}("
    if language == "go":
        if "." in sym:
            cls, method = sym.split(".", 1)
            return f" {cls}) {method}("
        return f"func {bare}("
    if language == "rust":
        return f"fn {bare}("
    raise ValueError(f"Unsupported language {language}")


def _build_scip_payload(
    files: dict[str, str], gt_edges: list[_GroundTruthEdge]
) -> dict[str, object]:
    """Generate a deterministic SCIP JSON payload matching every ground-truth edge."""
    docs: dict[str, list[dict[str, object]]] = {}

    defs_by_file: dict[str, dict[str, tuple[str, int]]] = {}
    for edge in gt_edges:
        for file_rel, sym in [
            (edge.caller_file, edge.caller_symbol),
            (edge.callee_file, edge.callee_symbol),
        ]:
            file_defs = defs_by_file.setdefault(file_rel, {})
            if sym not in file_defs:
                text = files[file_rel]
                marker = _def_marker(edge.language, sym)
                if "." in sym and edge.language in {"python", "typescript", "rust"}:
                    cls_name = sym.split(".", 1)[0]
                    lines = text.splitlines()
                    cls_line = _find_line(
                        text,
                        f" {cls_name}"
                        if edge.language != "rust"
                        else f"for {cls_name}",
                    )
                    line_idx = cls_line + next(
                        i for i, ln in enumerate(lines[cls_line:]) if marker in ln
                    )
                else:
                    line_idx = _find_line(text, marker)
                file_defs[sym] = (edge.scip_symbol(file_rel, sym), line_idx)

    for file_rel, file_defs in defs_by_file.items():
        occs = docs.setdefault(file_rel, [])
        for _sym, (scip_sym, line_idx) in sorted(
            file_defs.items(), key=lambda item: item[1][1]
        ):
            occs.append(
                {
                    "range": [line_idx, 0, line_idx, 4],
                    "symbol": scip_sym,
                    "symbol_roles": 1,
                }
            )

    for edge in gt_edges:
        _, caller_def_line = defs_by_file[edge.caller_file][edge.caller_symbol]
        ref_line = caller_def_line + 1
        docs[edge.caller_file].append(
            {
                "range": [ref_line, 4, ref_line, 12],
                "symbol": edge.scip_symbol(edge.callee_file, edge.callee_symbol),
                "symbol_roles": 0,
            }
        )

    return {
        "metadata": {
            "tool_info": {"name": "scip-multilingual-bench", "version": "1.0.0"}
        },
        "documents": [
            {"relative_path": rel, "occurrences": occs}
            for rel, occs in sorted(docs.items())
        ],
    }


def _create_fixture_repo(
    repo_root: Path,
) -> tuple[list[_GroundTruthEdge], set[tuple[str, str]], Path]:
    files: dict[str, str] = {}
    gt_edges: list[_GroundTruthEdge] = []
    gt_edges.extend(_build_python_corpus(files))
    gt_edges.extend(_build_typescript_corpus(files))
    gt_edges.extend(_build_go_corpus(files))
    gt_edges.extend(_build_rust_corpus(files))

    for rel_path, content in files.items():
        target = repo_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    scip_payload = _build_scip_payload(files, gt_edges)
    scip_file = repo_root / "index.scip.json"
    scip_file.write_text(json.dumps(scip_payload, indent=2), encoding="utf-8")

    _init_git_repo(repo_root)

    ground_truth = {
        (
            f"{(repo_root / e.caller_file).resolve()}::{e.caller_symbol}",
            f"{(repo_root / e.callee_file).resolve()}::{e.callee_symbol}",
        )
        for e in gt_edges
    }
    return gt_edges, ground_truth, scip_file


def _language_breakdown(
    gt_edges: list[_GroundTruthEdge],
    repo_root: Path,
    stage_predictions: dict[str, set[tuple[str, str]]],
) -> dict[str, object]:
    summary: dict[str, object] = {}
    for lang in ("python", "typescript", "go", "rust"):
        lang_edges = [e for e in gt_edges if e.language == lang]
        lang_gt = {
            (
                f"{(repo_root / e.caller_file).resolve()}::{e.caller_symbol}",
                f"{(repo_root / e.callee_file).resolve()}::{e.callee_symbol}",
            )
            for e in lang_edges
        }
        dyn_count = sum(1 for e in lang_edges if e.is_dynamic_dispatch)
        summary[lang] = {
            "ground_truth_edges": len(lang_gt),
            "dynamic_dispatch_edges": dyn_count,
            "stages": {
                stage: _score(pred & lang_gt, lang_gt)["f1"]
                for stage, pred in stage_predictions.items()
            },
        }
    return summary


def run_benchmark(output_path: Path | None = None) -> dict[str, object]:
    """Run the 3-stage offline benchmark and optionally persist the JSON report."""
    total_start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="crg-scip-bench-") as tmp:
        root = Path(tmp).resolve()
        gt_edges, ground_truth, scip_file = _create_fixture_repo(root)

        # Stage 1: syntactic parser baseline
        t0 = time.perf_counter()
        db1 = root / "stage1.db"
        store1 = GraphStore(db1)
        try:
            _populate_parsed_repo(root, store1)
            store1.resolve_bare_calls()
            baseline_calls = _collect_resolved_calls(store1)
        finally:
            store1.close()
        baseline_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        baseline_metrics = {
            **_score(baseline_calls, ground_truth),
            "elapsed_ms": baseline_ms,
        }

        # Stage 2: 3-phase intra-repo resolution
        t1 = time.perf_counter()
        db2 = root / "stage2.db"
        store2 = GraphStore(db2)
        try:
            _populate_parsed_repo(root, store2)
            store2.resolve_bare_calls()
            resolution_counts = resolve_intra_repo_calls(store2, root)
            intra_calls = _collect_resolved_calls(store2)
        finally:
            store2.close()
        intra_ms = round((time.perf_counter() - t1) * 1000.0, 2)
        intra_metrics = {**_score(intra_calls, ground_truth), "elapsed_ms": intra_ms}

        # Stage 3: SCIP compiler-index import
        t2 = time.perf_counter()
        db3 = root / "stage3.db"
        store3 = GraphStore(db3)
        try:
            _populate_parsed_repo(root, store3)
            scip_summary = import_scip_index(store3, scip_file, repo_root=root)
            scip_calls = _collect_resolved_calls(store3)
        finally:
            store3.close()
        scip_ms = round((time.perf_counter() - t2) * 1000.0, 2)
        scip_metrics = {**_score(scip_calls, ground_truth), "elapsed_ms": scip_ms}

        dynamic_gt_count = sum(1 for e in gt_edges if e.is_dynamic_dispatch)
        languages = _language_breakdown(
            gt_edges,
            root,
            {
                "syntactic_baseline": baseline_calls,
                "intra_repo_3phase": intra_calls,
                "scip_import": scip_calls,
            },
        )

    total_ms = round((time.perf_counter() - total_start) * 1000.0, 2)
    report: dict[str, object] = {
        "benchmark": "scip_call_resolution_offline",
        "reproducible_command": REPRODUCIBLE_COMMAND,
        "ground_truth_edges": len(ground_truth),
        "dynamic_dispatch_edges": dynamic_gt_count,
        "total_elapsed_ms": total_ms,
        "languages": languages,
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


def main(argv: list[str] | None = None) -> int:
    out = Path(argv[1]) if argv and len(argv) > 1 else DEFAULT_REPORT_PATH
    report = run_benchmark(out)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
