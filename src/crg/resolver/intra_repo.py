"""Intra-repository 3-phase call resolver (CRG-11, CRG-12, CRG-13).

Upgrades unresolved and bare ``CALLS`` edges within a single repository
through three ordered resolution phases:

1. **Import-traced resolution** (``resolution="import_traced"``, ``confidence=0.95``):
   Resolves imported symbols, module aliases, Python ``__all__`` exports, and
   TypeScript ``tsconfig.json`` path aliases to concrete same-repo nodes.
2. **Type-inferred resolution** (``resolution="type_inferred"``, ``confidence=0.85``):
   Infers receiver types from parameter annotations, return annotations,
   ``self.attr`` attributes, and local constructor assignments to bind
   ``receiver.method()`` calls.
3. **Dynamic dispatch propagation** (``resolution="dynamic_dispatch"``, ``confidence=0.75``):
   Propagates ``CALLS`` edges targeting base/interface methods across
   ``INHERITS`` and ``IMPLEMENTS`` subclasses (capped at 5 targets/callsite).
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from .typescript import _read_tsconfig_paths

if TYPE_CHECKING:
    from ..graph import GraphStore

_DYNAMIC_DISPATCH_CAP = 5

_PY_FROM_IMPORT_RE = re.compile(
    r"^\s*from\s+(\.{0,3}[\w.]*)\s+import\s+(.+?)\s*(?:#.*)?$"
)
_PY_IMPORT_RE = re.compile(r"^\s*import\s+(.+?)\s*(?:#.*)?$")
_PY_ALL_RE = re.compile(r"__all__\s*=\s*[\[\(](.*?)[\]\)]", re.DOTALL)
_TS_NAMED_RE = re.compile(r"^\s*import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]")
_TS_DEFAULT_RE = re.compile(r"^\s*import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]")
_TS_NS_RE = re.compile(r"^\s*import\s+\*\s+as\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]")
_TYPE_PARAM_RE = re.compile(r"\b([A-Za-z_]\w*)\s*:\s*([A-Z]\w*)")
_ATTR_TYPE_RE = re.compile(r"self\.([A-Za-z_]\w*)\s*:\s*([A-Z]\w*)")
_ATTR_INIT_RE = re.compile(
    r"(?:self|this)\.([A-Za-z_]\w*)\s*=\s*(?:new\s+)?([A-Z]\w*)\s*\("
)
_VAR_INIT_RE = re.compile(
    r"(?:^|\n)\s*(?:const|let|var)?\s*([A-Za-z_]\w*)\s*(?::\s*[A-Z]\w*)?\s*=\s*(?:new\s+)?([A-Z]\w*)\s*\("
)
_RET_TYPE_RE = re.compile(r"(?:->|:)\s*([A-Z]\w*)")


def _safe_extra(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _posix_rel(file_path: str, repo_root: Path | None) -> str:
    p = Path(file_path)
    if repo_root is not None:
        try:
            return p.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass
    return p.as_posix()


def _module_keys_for_rel(rel: str) -> list[str]:
    """Return dotted and slash module keys matching *rel*."""
    keys: list[str] = []
    norm = rel.lstrip("./")
    stem = norm
    for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".d.ts"):
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    keys.append(stem)
    dotted = stem.replace("/", ".")
    keys.append(dotted)
    if dotted.endswith(".__init__"):
        keys.append(dotted[: -len(".__init__")])
    if stem.endswith("/index"):
        keys.append(stem[: -len("/index")])
    if norm.startswith("src/"):
        sub = stem[len("src/") :]
        keys.append(sub)
        keys.append(sub.replace("/", "."))
        if sub.endswith("/index"):
            keys.append(sub[: -len("/index")])
    return [k for k in dict.fromkeys(keys) if k]


def _extract_python_all(source: str) -> set[str] | None:
    m = _PY_ALL_RE.search(source)
    if not m:
        return None
    items = re.findall(r"['\"]([A-Za-z_]\w*)['\"]", m.group(1))
    return set(items)


def _resolve_relative_module(importer_rel: str, spec: str) -> str:
    dots = len(spec) - len(spec.lstrip("."))
    rest = spec.lstrip(".")
    parts = Path(importer_rel).parent.as_posix().split("/")
    if parts == ["."]:
        parts = []
    if dots > 1:
        up = dots - 1
        parts = parts[: max(0, len(parts) - up)]
    base = ".".join(p for p in parts if p)
    if rest:
        return f"{base}.{rest}" if base else rest
    return base


def _resolve_ts_spec(
    importer_rel: str,
    spec: str,
    ts_paths: dict[str, list[str]],
) -> list[str]:
    candidates: list[str] = []
    if spec.startswith("."):
        joined = (Path(importer_rel).parent / spec).as_posix()
        parts: list[str] = []
        for part in joined.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(part)
        rel = "/".join(parts)
        candidates.extend([rel, f"{rel}/index"])
        return candidates
    for pattern, targets in ts_paths.items():
        if pattern.endswith("/*"):
            prefix = pattern[:-1]
            if spec.startswith(prefix):
                suffix = spec[len(prefix) :]
                for target in targets:
                    expanded = target[:-1] + suffix if target.endswith("/*") else target
                    expanded = expanded.lstrip("./")
                    candidates.extend([expanded, f"{expanded}/index"])
        elif spec == pattern:
            for target in targets:
                expanded = target.lstrip("./")
                candidates.extend([expanded, f"{expanded}/index"])
    candidates.append(spec)
    return candidates


def _collect_file_imports(
    file_path: str,
    rel: str,
    ts_paths: dict[str, list[str]],
) -> tuple[dict[str, tuple[str, str | None]], set[str] | None]:
    """Parse local import aliases and optional Python ``__all__`` from *file_path*.

    Returns ``(alias_map, py_all)`` where *alias_map* maps local name ->
    ``(module_key, exported_symbol_name | None)``.
    """
    p = Path(file_path)
    if not p.is_file():
        return {}, None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, None

    alias_map: dict[str, tuple[str, str | None]] = {}
    py_all = _extract_python_all(text) if rel.endswith(".py") else None
    suffix = p.suffix.lower()

    for line in text.splitlines():
        if suffix == ".py":
            m_from = _PY_FROM_IMPORT_RE.match(line)
            if m_from:
                raw_mod, names_part = m_from.group(1), m_from.group(2)
                mod_key = (
                    _resolve_relative_module(rel, raw_mod)
                    if raw_mod.startswith(".")
                    else raw_mod
                )
                for item in names_part.strip("()").split(","):
                    chunk = item.strip()
                    if not chunk or chunk == "*":
                        continue
                    if " as " in chunk:
                        orig, local = [x.strip() for x in chunk.split(" as ", 1)]
                    else:
                        orig = local = chunk
                    alias_map[local] = (mod_key, orig)
                continue
            m_imp = _PY_IMPORT_RE.match(line)
            if m_imp:
                for item in m_imp.group(1).split(","):
                    chunk = item.strip()
                    if not chunk:
                        continue
                    if " as " in chunk:
                        mod_name, local = [x.strip() for x in chunk.split(" as ", 1)]
                        alias_map[local] = (mod_name, None)
                    else:
                        alias_map[chunk.split(".")[0]] = (chunk, None)
        elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
            m_named = _TS_NAMED_RE.match(line)
            if m_named:
                specs = _resolve_ts_spec(rel, m_named.group(2), ts_paths)
                for item in m_named.group(1).split(","):
                    chunk = item.strip()
                    if not chunk:
                        continue
                    if " as " in chunk:
                        orig, local = [x.strip() for x in chunk.split(" as ", 1)]
                    else:
                        orig = local = chunk
                    if specs:
                        alias_map[local] = (specs[0], orig)
                continue
            m_ns = _TS_NS_RE.match(line)
            if m_ns:
                specs = _resolve_ts_spec(rel, m_ns.group(2), ts_paths)
                if specs:
                    alias_map[m_ns.group(1)] = (specs[0], None)
                continue
            m_def = _TS_DEFAULT_RE.match(line)
            if m_def:
                specs = _resolve_ts_spec(rel, m_def.group(2), ts_paths)
                if specs:
                    alias_map[m_def.group(1)] = (specs[0], m_def.group(1))

    return alias_map, py_all


def _phase1_import_traced(
    store: GraphStore,
    repo_root: Path | None,
    ts_paths: dict[str, list[str]],
) -> int:
    """Resolve bare/unresolved CALLS via module exports and import aliases."""
    # Index active symbols per (repo_id, file_path) and module key -> file_path
    symbols_by_file: dict[tuple[str | None, str], dict[str, str]] = defaultdict(dict)
    valid_qns: set[str] = set()
    for row in store._conn.execute(
        "SELECT repo_id, file_path, qualified_name, kind FROM nodes "
        "WHERE valid_to_sha IS NULL"
    ):
        qn = str(row["qualified_name"])
        valid_qns.add(qn)
        if row["kind"] in ("Function", "Test", "Class", "Type"):
            short = qn.rsplit("::", 1)[-1]
            key = (row["repo_id"], str(row["file_path"]))
            symbols_by_file[key][short] = qn
            if "." in short:
                symbols_by_file[key].setdefault(short.rsplit(".", 1)[-1], qn)

    module_to_file: dict[tuple[str | None, str], str] = {}
    file_imports: dict[str, dict[str, tuple[str, str | None]]] = {}
    file_all_exports: dict[str, set[str] | None] = {}
    file_repo: dict[str, str | None] = {}
    file_rel: dict[str, str] = {}

    for row in store._conn.execute(
        "SELECT repo_id, file_path FROM nodes WHERE kind = 'File' AND valid_to_sha IS NULL"
    ):
        fp = str(row["file_path"])
        rid = row["repo_id"]
        rel = _posix_rel(fp, repo_root)
        file_repo[fp] = rid
        file_rel[fp] = rel
        for mk in _module_keys_for_rel(rel):
            module_to_file.setdefault((rid, mk), fp)
        aliases, py_all = _collect_file_imports(fp, rel, ts_paths)
        file_imports[fp] = aliases
        file_all_exports[fp] = py_all

    # Also incorporate stored IMPORTS_FROM edges so synthetic/in-memory stores work
    for row in store._conn.execute(
        "SELECT repo_id, file_path, target_qualified, extra FROM edges "
        "WHERE kind = 'IMPORTS_FROM' AND valid_to_sha IS NULL"
    ):
        fp = str(row["file_path"])
        rid = row["repo_id"]
        tgt = str(row["target_qualified"])
        extra = _safe_extra(row["extra"])
        local = str(extra.get("alias") or extra.get("name") or tgt.rsplit(".", 1)[-1])
        sym = tgt.rsplit("::", 1)[-1] if "::" in tgt else local
        mod = tgt.rsplit("::", 1)[0] if "::" in tgt else tgt
        if fp not in file_imports:
            file_imports[fp] = {}
        file_imports[fp].setdefault(local, (mod, sym))

    # Build lookup helpers for each file's imports -> target file
    def resolve_module_file(
        rid: str | None, importer_fp: str, mod_spec: str
    ) -> str | None:
        if (rid, mod_spec) in module_to_file:
            return module_to_file[(rid, mod_spec)]
        rel = file_rel.get(importer_fp, _posix_rel(importer_fp, repo_root))
        for cand in _resolve_ts_spec(rel, mod_spec, ts_paths):
            for mk in _module_keys_for_rel(cand):
                if (rid, mk) in module_to_file:
                    return module_to_file[(rid, mk)]
        return None

    updates: list[tuple[str, float, str, int]] = []
    for row in store._conn.execute(
        "SELECT id, repo_id, file_path, target_qualified, extra FROM edges "
        "WHERE kind = 'CALLS' AND valid_to_sha IS NULL"
    ):
        tgt = str(row["target_qualified"])
        if tgt in valid_qns:
            continue
        fp = str(row["file_path"])
        rid = row["repo_id"]
        aliases = file_imports.get(fp, {})
        extra = _safe_extra(row["extra"])
        raw_candidates: list[str] = []
        if "bare_unresolved_target" in extra and isinstance(
            extra["bare_unresolved_target"], str
        ):
            raw_candidates.append(extra["bare_unresolved_target"])
        raw_candidates.append(tgt.rsplit("::", 1)[-1] if "::" in tgt else tgt)
        bare_list = extra.get("bare_targets")
        if isinstance(bare_list, list):
            raw_candidates.extend(c for c in bare_list if isinstance(c, str))

        resolved_qn: str | None = None
        for cand in raw_candidates:
            if "." in cand:
                head, member = cand.split(".", 1)
                if head in aliases:
                    mod_spec, orig = aliases[head]
                    if orig is None:
                        target_fp = resolve_module_file(rid, fp, mod_spec)
                        if target_fp:
                            allowed = file_all_exports.get(target_fp)
                            if allowed is None or member in allowed:
                                resolved_qn = symbols_by_file[(rid, target_fp)].get(
                                    member
                                )
                    else:
                        target_fp = resolve_module_file(rid, fp, mod_spec)
                        if target_fp:
                            resolved_qn = symbols_by_file[(rid, target_fp)].get(
                                f"{orig}.{member}"
                            )
            elif cand in aliases:
                mod_spec, orig = aliases[cand]
                target_fp = resolve_module_file(rid, fp, mod_spec)
                if target_fp:
                    lookup = orig or cand
                    allowed = file_all_exports.get(target_fp)
                    if allowed is None or lookup in allowed:
                        resolved_qn = symbols_by_file[(rid, target_fp)].get(lookup)
            if resolved_qn:
                break

        if resolved_qn and resolved_qn in valid_qns:
            updates.append((resolved_qn, 0.95, "import_traced", int(row["id"])))

    if updates:
        store._conn.executemany(
            "UPDATE edges SET target_qualified = ?, confidence = ?, resolution = ? "
            "WHERE id = ?",
            updates,
        )
    return len(updates)


def _infer_receiver_types(
    source_text: str | None,
    params: str | None,
) -> dict[str, str]:
    """Infer ``var -> ClassName`` and ``self.attr -> ClassName`` bindings."""
    env: dict[str, str] = {}
    if params:
        for name, cls_name in _TYPE_PARAM_RE.findall(params):
            env[name] = cls_name
    if source_text:
        for attr, cls_name in _ATTR_TYPE_RE.findall(source_text):
            env[f"self.{attr}"] = cls_name
            env[f"this.{attr}"] = cls_name
        for attr, cls_name in _ATTR_INIT_RE.findall(source_text):
            env.setdefault(f"self.{attr}", cls_name)
            env.setdefault(f"this.{attr}", cls_name)
        for var, cls_name in _VAR_INIT_RE.findall(source_text):
            if var not in {"self", "this"}:
                env.setdefault(var, cls_name)
    return env


def _phase2_type_inferred(store: GraphStore) -> int:
    """Resolve receiver.method calls using parameter/constructor type bindings."""
    class_methods: dict[tuple[str | None, str], dict[str, str]] = defaultdict(dict)
    node_envs: dict[str, dict[str, str]] = {}
    node_sources: dict[str, str] = {}
    valid_qns: set[str] = set()
    return_types: dict[tuple[str | None, str], str] = {}

    for row in store._conn.execute(
        "SELECT repo_id, qualified_name, kind, parent_name, params, return_type, source_text "
        "FROM nodes WHERE valid_to_sha IS NULL"
    ):
        qn = str(row["qualified_name"])
        rid = row["repo_id"]
        valid_qns.add(qn)
        short = qn.rsplit("::", 1)[-1]
        if row["kind"] == "Function" and "." in short:
            cls_name, meth = short.rsplit(".", 1)
            class_methods[(rid, cls_name)][meth] = qn
        elif row["kind"] == "Function" and row["parent_name"]:
            class_methods[(rid, str(row["parent_name"]))][short] = qn
        if row["return_type"]:
            m = _RET_TYPE_RE.search(str(row["return_type"]))
            if m:
                return_types[(rid, short)] = m.group(1)
        if row["kind"] in ("Function", "Test"):
            node_envs[qn] = _infer_receiver_types(row["source_text"], row["params"])
            if row["source_text"]:
                node_sources[qn] = str(row["source_text"])

    updates: list[tuple[str, float, str, int]] = []
    for row in store._conn.execute(
        "SELECT id, repo_id, source_qualified, target_qualified, extra FROM edges "
        "WHERE kind = 'CALLS' AND valid_to_sha IS NULL"
    ):
        tgt = str(row["target_qualified"])
        if tgt in valid_qns:
            continue
        caller = str(row["source_qualified"])
        env = node_envs.get(caller)
        if not env:
            continue
        rid = row["repo_id"]
        caller_src = node_sources.get(caller, "")
        extra = _safe_extra(row["extra"])
        cands = [tgt.rsplit("::", 1)[-1] if "::" in tgt else tgt]
        if isinstance(extra.get("bare_unresolved_target"), str):
            cands.insert(0, str(extra["bare_unresolved_target"]))
        bare_targets = extra.get("bare_targets")
        if isinstance(bare_targets, list):
            cands.extend(c for c in bare_targets if isinstance(c, str))

        resolved_qn: str | None = None
        for cand in cands:
            if "." in cand:
                recv, meth = cand.rsplit(".", 1)
                cls_name = env.get(recv)
                if cls_name is None and recv.endswith("()"):
                    fn_name = recv[:-2]
                    cls_name = return_types.get((rid, fn_name))
                if cls_name:
                    resolved_qn = class_methods.get((rid, cls_name), {}).get(meth)
                    if resolved_qn:
                        break
            elif caller_src:
                for recv, cls_name in env.items():
                    if re.search(
                        rf"\b{re.escape(recv)}\.{re.escape(cand)}\s*\(",
                        caller_src,
                    ):
                        resolved_qn = class_methods.get((rid, cls_name), {}).get(cand)
                        if resolved_qn:
                            break
                if resolved_qn:
                    break
        if resolved_qn and resolved_qn in valid_qns:
            updates.append((resolved_qn, 0.85, "type_inferred", int(row["id"])))

    if updates:
        store._conn.executemany(
            "UPDATE edges SET target_qualified = ?, confidence = ?, resolution = ? "
            "WHERE id = ?",
            updates,
        )
    return len(updates)


def _phase3_dynamic_dispatch(store: GraphStore) -> int:
    """Propagate base/interface method CALLS to concrete subclass overrides."""
    # Map class name & qualified name -> subclasses (via INHERITS / IMPLEMENTS)
    subclasses_by_base: dict[tuple[str | None, str], list[str]] = defaultdict(list)
    class_methods: dict[tuple[str | None, str], dict[str, str]] = defaultdict(dict)
    class_qns: dict[tuple[str | None, str], list[str]] = defaultdict(list)

    for row in store._conn.execute(
        "SELECT repo_id, qualified_name, kind, parent_name FROM nodes "
        "WHERE valid_to_sha IS NULL AND kind IN ('Class', 'Type', 'Function')"
    ):
        rid = row["repo_id"]
        qn = str(row["qualified_name"])
        short = qn.rsplit("::", 1)[-1]
        if row["kind"] in ("Class", "Type"):
            class_qns[(rid, short)].append(qn)
        elif row["kind"] == "Function" and "." in short:
            cls_name, meth = short.rsplit(".", 1)
            class_methods[(rid, cls_name)][meth] = qn
            file_prefix = qn.rsplit("::", 1)[0]
            class_methods[(rid, f"{file_prefix}::{cls_name}")][meth] = qn
        elif row["kind"] == "Function" and row["parent_name"]:
            class_methods[(rid, str(row["parent_name"]))][short] = qn

    for row in store._conn.execute(
        "SELECT repo_id, source_qualified, target_qualified FROM edges "
        "WHERE kind IN ('INHERITS', 'IMPLEMENTS') AND valid_to_sha IS NULL"
    ):
        rid = row["repo_id"]
        child_qn = str(row["source_qualified"])
        base_raw = str(row["target_qualified"])
        subclasses_by_base[(rid, base_raw)].append(child_qn)
        base_short = base_raw.rsplit("::", 1)[-1]
        if base_short != base_raw:
            subclasses_by_base[(rid, base_short)].append(child_qn)
        for full_base in class_qns.get((rid, base_short), []):
            subclasses_by_base[(rid, full_base)].append(child_qn)

    if not subclasses_by_base:
        return 0

    existing_calls: set[tuple[str, str]] = set()
    calls: list[tuple[str | None, str, str, str, int, str | None]] = []
    for row in store._conn.execute(
        "SELECT repo_id, source_qualified, target_qualified, file_path, line, valid_from_sha "
        "FROM edges WHERE kind = 'CALLS' AND valid_to_sha IS NULL"
    ):
        src = str(row["source_qualified"])
        tgt = str(row["target_qualified"])
        existing_calls.add((src, tgt))
        calls.append(
            (
                row["repo_id"],
                src,
                tgt,
                str(row["file_path"]),
                int(row["line"] or 0),
                row["valid_from_sha"],
            )
        )

    now_ts = time.time()
    inserts: list[
        tuple[str, str, str, str, int, str, str | None, str | None, float, str, float]
    ] = []
    for rid, src, tgt, fp, line, vf_sha in calls:
        if "::" not in tgt or "." not in tgt.rsplit("::", 1)[-1]:
            continue
        mod_part, sym_part = tgt.rsplit("::", 1)
        base_cls, meth = sym_part.rsplit(".", 1)
        base_qn = f"{mod_part}::{base_cls}"
        subs = list(
            dict.fromkeys(
                subclasses_by_base.get((rid, base_qn), [])
                + subclasses_by_base.get((rid, base_cls), [])
            )
        )
        added = 0
        for sub_qn in subs:
            if added >= _DYNAMIC_DISPATCH_CAP:
                break
            sub_short = sub_qn.rsplit("::", 1)[-1]
            sub_meth_qn = class_methods.get((rid, sub_qn), {}).get(
                meth
            ) or class_methods.get((rid, sub_short), {}).get(meth)
            if (
                not sub_meth_qn
                or sub_meth_qn == tgt
                or (src, sub_meth_qn) in existing_calls
            ):
                continue
            existing_calls.add((src, sub_meth_qn))
            extra = json.dumps({"dispatched_from": tgt}, separators=(",", ":"))
            inserts.append(
                (
                    "CALLS",
                    src,
                    sub_meth_qn,
                    fp,
                    line,
                    extra,
                    rid,
                    vf_sha,
                    0.75,
                    "dynamic_dispatch",
                    now_ts,
                )
            )
            added += 1

    if inserts:
        store._conn.executemany(
            "INSERT INTO edges "
            "(kind, source_qualified, target_qualified, file_path, line, "
            "extra, repo_id, valid_from_sha, valid_to_sha, confidence, resolution, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)",
            inserts,
        )
    return len(inserts)


def resolve_intra_repo_calls(
    store: GraphStore,
    repo_root: Path | None = None,
) -> dict[str, int]:
    """Run all three intra-repo call resolution phases and return counts."""
    ts_paths: dict[str, list[str]] = {}
    if repo_root is not None:
        tsconfig = repo_root / "tsconfig.json"
        if tsconfig.is_file():
            ts_paths = _read_tsconfig_paths(tsconfig)

    phase1 = _phase1_import_traced(store, repo_root, ts_paths)
    phase2 = _phase2_type_inferred(store)
    phase3 = _phase3_dynamic_dispatch(store)
    if phase1 or phase2 or phase3:
        store._invalidate_cache()
    return {
        "import_traced": phase1,
        "type_inferred": phase2,
        "dynamic_dispatch": phase3,
    }
