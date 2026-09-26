"""MCP tool definitions for the Code Review Graph server.

Exposes 9 tools:
1. build_or_update_graph  - full or incremental build
2. get_impact_radius      - blast radius from changed files
3. query_graph            - predefined graph queries
4. get_review_context     - focused subgraph + review prompt
5. semantic_search_nodes  - keyword + vector search across nodes
6. list_graph_stats       - aggregate statistics
7. embed_graph            - compute vector embeddings for semantic search
8. get_docs_section       - token-optimized documentation retrieval
9. find_large_functions   - find oversized functions/classes by line count
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from .config import settings
from .embeddings import (
    EmbeddingStore,
    embed_all_nodes,
    init_backend,
    resolve_backend,
    semantic_search,
)
from .graph import GraphStore, _sanitize_name, edge_to_dict, node_to_dict
from .incremental import (
    collect_all_files,
    find_project_root,
    full_build,
    get_changed_files,
    get_db_path,
    get_staged_and_unstaged,
    incremental_update,
)
from .security import HeuristicScanner, Tag
from .security.semgrep_engine import (
    SemgrepNotAvailable,
    SemgrepScanner,
    _resolve_overlay_rules_dir,
)
from .xpia import build_external_tool_result, wrap_external_content

logger = logging.getLogger(__name__)

# Common JS/TS builtin method names filtered from callers_of results.
# "Who calls .map()?" returns hundreds of hits and is never useful.
# These are kept in the graph (callees_of still shows them) but excluded
# when doing reverse call tracing to reduce noise.
_BUILTIN_CALL_NAMES: set[str] = {
    "map",
    "filter",
    "reduce",
    "reduceRight",
    "forEach",
    "find",
    "findIndex",
    "some",
    "every",
    "includes",
    "indexOf",
    "lastIndexOf",
    "push",
    "pop",
    "shift",
    "unshift",
    "splice",
    "slice",
    "concat",
    "join",
    "flat",
    "flatMap",
    "sort",
    "reverse",
    "fill",
    "keys",
    "values",
    "entries",
    "from",
    "isArray",
    "of",
    "at",
    "trim",
    "trimStart",
    "trimEnd",
    "split",
    "replace",
    "replaceAll",
    "match",
    "matchAll",
    "search",
    "substring",
    "substr",
    "toLowerCase",
    "toUpperCase",
    "startsWith",
    "endsWith",
    "padStart",
    "padEnd",
    "repeat",
    "charAt",
    "charCodeAt",
    "assign",
    "freeze",
    "defineProperty",
    "getOwnPropertyNames",
    "hasOwnProperty",
    "create",
    "is",
    "fromEntries",
    "log",
    "warn",
    "error",
    "info",
    "debug",
    "trace",
    "dir",
    "table",
    "time",
    "timeEnd",
    "assert",
    "clear",
    "count",
    "then",
    "catch",
    "finally",
    "resolve",
    "reject",
    "all",
    "allSettled",
    "race",
    "any",
    "parse",
    "stringify",
    "floor",
    "ceil",
    "round",
    "random",
    "max",
    "min",
    "abs",
    "pow",
    "sqrt",
    "addEventListener",
    "removeEventListener",
    "querySelector",
    "querySelectorAll",
    "getElementById",
    "createElement",
    "appendChild",
    "removeChild",
    "setAttribute",
    "getAttribute",
    "preventDefault",
    "stopPropagation",
    "setTimeout",
    "clearTimeout",
    "setInterval",
    "clearInterval",
    "toString",
    "valueOf",
    "toJSON",
    "toISOString",
    "getTime",
    "getFullYear",
    "now",
    "isNaN",
    "parseInt",
    "parseFloat",
    "toFixed",
    "encodeURIComponent",
    "decodeURIComponent",
    "call",
    "apply",
    "bind",
    "next",
    "emit",
    "on",
    "off",
    "once",
    "pipe",
    "write",
    "read",
    "end",
    "close",
    "destroy",
    "send",
    "status",
    "json",
    "redirect",
    "set",
    "get",
    "delete",
    "has",
    "findUnique",
    "findFirst",
    "findMany",
    "createMany",
    "update",
    "updateMany",
    "deleteMany",
    "upsert",
    "aggregate",
    "groupBy",
    "transaction",
    "describe",
    "it",
    "test",
    "expect",
    "beforeEach",
    "afterEach",
    "beforeAll",
    "afterAll",
    "mock",
    "spyOn",
    "require",
    "fetch",
}


def _build_response_header(
    store: GraphStore | None,
    db_path: Path | None,
    *,
    keyword_only: bool | None = None,
) -> dict[str, Any]:
    """Build a metadata header for ``search`` / ``query`` responses (#330).

    Surfaces ``embeddings_count`` and the derived ``keyword_only`` flag so
    consumers know whether the results came from semantic-similarity search
    (``embeddings_count > 0``) or keyword-substring fallback. Plus
    ``graph_last_updated`` when available.

    The header never raises -- it is metadata, not query correctness -- but a
    read that fails is reported as ``null`` plus an explicit ``*_error`` key
    rather than as a plausible-looking value. ``embeddings_count: 0`` in
    particular is documented advice (``docs/recipes.md``: "if
    ``embeddings_count == 0`` ... run ``graph action=embed`` first"), and
    embedding cannot fix a store that will not open.

    Args:
        store: Open ``GraphStore`` (used for ``last_updated`` metadata).
        db_path: Path to the graph DB (used to open an EmbeddingStore).
        keyword_only: Optional explicit override (e.g. ``search`` already
            knows whether it ran semantic vs keyword). When ``None`` the
            flag is derived from ``embeddings_count``.
    """
    emb_count: int | None = None
    emb_error: str | None = None
    if db_path is not None:
        try:
            backend = init_backend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                emb_count = emb_store.count()
            finally:
                emb_store.close()
        except Exception as e:
            emb_error = f"{type(e).__name__}: {e}"
            emb_count = None
            logger.warning(
                "Embedding store at %s could not be read (%s); reporting "
                "embeddings_count as null rather than 0, because 0 means "
                "'no embeddings yet, run graph action=embed' and that will "
                "not fix an unreadable store.",
                db_path,
                emb_error,
            )

    last_updated: str | None = None
    meta_error: str | None = None
    if store is not None:
        try:
            last_updated = store.get_metadata("last_updated")
        except Exception as e:
            meta_error = f"{type(e).__name__}: {e}"
            last_updated = None
            logger.warning(
                "Graph metadata could not be read (%s); graph_last_updated "
                "is null because the read failed, not because the graph was "
                "never built.",
                meta_error,
            )

    if keyword_only is None:
        # An unreadable embedding store cannot serve semantic search either,
        # so keyword_only is true whether the count is zero or unknown.
        keyword_only = (emb_count is None) or (emb_count == 0)

    header: dict[str, Any] = {
        # Zero only when a read succeeded and found nothing, or when there
        # was no db_path to read in the first place. Never as a stand-in for
        # "could not tell".
        "embeddings_count": None if emb_error else (emb_count or 0),
        "keyword_only": bool(keyword_only),
        "graph_last_updated": last_updated,
    }
    if emb_error:
        header["embeddings_error"] = emb_error
    if meta_error:
        header["graph_last_updated_error"] = meta_error
    return header


def _validate_repo_root(path: Path) -> Path:
    """Validate that a path is a plausible project root.

    Ensures the path is an existing directory that contains a ``.git``
    or ``.better-code-review-graph`` directory, preventing arbitrary file-system
    traversal via the ``repo_root`` parameter.
    """
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"repo_root is not an existing directory: {resolved}")
    if (
        not (resolved / ".git").exists()
        and not (resolved / ".better-code-review-graph").exists()
    ):
        raise ValueError(
            f"repo_root does not look like a project root (no .git or "
            f".better-code-review-graph directory found): {resolved}"
        )
    return resolved


def _get_store(repo_root: str | None = None) -> tuple[GraphStore, Path]:
    """Resolve repo root and open the graph store."""
    root = _validate_repo_root(Path(repo_root)) if repo_root else find_project_root()
    db_path = get_db_path(root)
    return GraphStore(db_path), root


# ---------------------------------------------------------------------------
# Tool 1: build_or_update_graph
# ---------------------------------------------------------------------------


def _php_call_warnings(coverage: dict[str, int]) -> list[str]:
    unresolved = coverage.get("unresolved", 0)
    if not unresolved:
        return []
    return [
        f"{unresolved} of {coverage['total']} PHP CALLS targets are unresolved; "
        "callers and impact results are partial. Dynamic receivers, ambiguous "
        "definitions, external libraries, and inherited methods may require "
        "manual inspection."
    ]


def _bare_call_warnings(coverage: dict[str, int]) -> list[str]:
    unresolved = coverage.get("unresolved", 0)
    if not unresolved:
        return []
    return [
        f"{unresolved} of {coverage['total']} CALLS targets are unresolved; "
        "callers and impact results are partial. Dynamic receivers, ambiguous "
        "definitions, and external libraries may require manual inspection."
    ]


def build_or_update_graph(
    full_rebuild: bool = False,
    repo_root: str | None = None,
    base: str = "HEAD~1",
    roots: list[str] | None = None,
) -> dict[str, Any]:
    """Build or incrementally update the code knowledge graph.

    Args:
        full_rebuild: If True, re-parse every file. If False (default),
                      only re-parse files changed since `base`.
        repo_root: Path to the repository root. Auto-detected if omitted.
        base: Git ref for incremental diff (default: HEAD~1).
        roots: Phase 2 Task 10 — optional list of additional repo roots
            to register and parse alongside ``repo_root``. Each entry is
            registered with :class:`RepoRegistry` and contributes nodes
            tagged with that repo's ``repo_id``. ``None`` (default) =
            single-root build using only ``repo_root``.

    Returns:
        Summary with files_parsed/updated, node/edge counts, and errors.
    """
    store, root = _get_store(repo_root)
    try:
        if roots:
            return _full_build_federated(store, root, [Path(r) for r in roots])

        if full_rebuild:
            result = full_build(root, store)
            return {
                "status": "ok",
                "build_type": "full",
                "summary": (
                    f"Full build complete: parsed {result['files_parsed']} files, "
                    f"created {result['total_nodes']} nodes and {result['total_edges']} edges."
                ),
                **result,
                "warnings": _php_call_warnings(result.get("php_calls", {}))
                + _bare_call_warnings(result.get("bare_calls", {})),
            }
        else:
            result = incremental_update(root, store, base=base)
            if result["files_updated"] == 0:
                return {
                    "status": "ok",
                    "build_type": "incremental",
                    "summary": "No changes detected. Graph is up to date.",
                    **result,
                    "warnings": _php_call_warnings(result.get("php_calls", {}))
                    + _bare_call_warnings(result.get("bare_calls", {})),
                }
            # #329: surface reviewer-oriented summary alongside raw counts.
            reviewer_summary = result.get("reviewer_summary") or {}
            summary_lines = [
                f"Incremental update: {result['files_updated']} files re-parsed, "
                f"{result['total_nodes']} nodes and {result['total_edges']} edges updated.",
                f"Changed: {result['changed_files']}. "
                f"Dependents also updated: {result['dependent_files']}.",
            ]
            if reviewer_summary:
                added = reviewer_summary.get("functions_added") or []
                removed = reviewer_summary.get("functions_removed") or []
                modified = reviewer_summary.get("functions_modified") or []
                impacted = reviewer_summary.get("modules_newly_impacted") or []
                summary_lines.append(
                    f"Reviewer summary: +{len(added)} / -{len(removed)} / "
                    f"~{len(modified)} functions, "
                    f"{len(impacted)} module(s) newly impacted."
                )
            return {
                "status": "ok",
                "build_type": "incremental",
                "summary": " ".join(summary_lines),
                **result,
                "warnings": _php_call_warnings(result.get("php_calls", {}))
                + _bare_call_warnings(result.get("bare_calls", {})),
            }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Graph build/update failed: {e}",
        }
    finally:
        store.close()


def _setup_federated_repos(
    store: GraphStore, primary_root: Path, roots: list[Path]
) -> tuple[Any, list[Any]]:
    """Register all roots and backfill commits (Task 10)."""
    from .federation import RepoRegistry, backfill_commits_for_repo
    from .resolver import TargetRepo

    registry = RepoRegistry(store)
    # Register primary first so it's always present, then each extra
    # root supplied by the caller. ``add`` is idempotent on re-add.
    primary_repo_id = registry.add(primary_root)
    extra_repo_ids: list[tuple[Path, str]] = []
    for r in roots:
        extra_repo_ids.append((r, registry.add(r)))

    # Phase 3 Task 7: first-parent commit backfill. Runs once per
    # registered root after the registry is set up so the FK to
    # ``repos.repo_id`` resolves. The helper is best-effort — non-git
    # roots return 0 silently; we don't surface per-root counts in the
    # build summary because the caller only cares about node/edge
    # counts. Errors are swallowed by the helper itself, so a failure
    # to walk one repo's history does not abort the whole build.
    backfill_commits_for_repo(store, primary_repo_id, primary_root)
    for root, rid in extra_repo_ids:
        backfill_commits_for_repo(store, rid, root)

    # Phase 2 Task 12: build ``target_repos`` from the registry so the
    # parser's cross-repo IMPORTS_FROM rewrite actually fires. Without
    # this, ``_apply_federation`` early-returns at the ``if not
    # target_repos`` guard and edges stay as bare local references
    # (e.g. ``py_lib.retry``) instead of resolving to
    # ``<repo_id>:src/py_lib/retry.py::retry``.
    target_repos = [
        TargetRepo(repo_id=entry.repo_id, root=entry.path)
        for entry in registry.entries()
    ]
    return registry, target_repos


def _run_federated_parse_loop(
    store: GraphStore,
    primary_root: Path,
    roots: list[Path],
    registry: Any,
    target_repos: list[Any],
) -> dict[str, Any]:
    """Walk all roots and parse files (Task 10)."""
    from .parser import CodeParser

    parser = CodeParser()
    total_files = 0
    total_nodes = 0
    total_edges = 0
    errors: list[dict[str, Any]] = []

    visited_files: set[Path] = set()
    for r in [primary_root, *roots]:
        r_resolved = r.resolve()
        try:
            files = collect_all_files(r)
        except Exception as e:
            errors.append({"root": str(r), "error": str(e)})
            continue
        for rel_path in files:
            full_path = (r / rel_path).resolve()
            if not full_path.is_relative_to(r_resolved):
                continue
            if full_path in visited_files:
                # A child root inside the primary would otherwise be
                # parsed twice; the registry's longest-match-wins means
                # the child wins for assign(), so we skip on the second
                # encounter.
                continue
            visited_files.add(full_path)
            try:
                source = full_path.read_bytes()
                fhash = hashlib.sha256(source).hexdigest()
                nodes, edges = parser.parse_bytes(
                    full_path,
                    source,
                    repo_registry=registry,
                    target_repos=target_repos,
                )
                store.store_file_nodes_edges(str(full_path), nodes, edges, fhash)
                total_nodes += len(nodes)
                total_edges += len(edges)
                total_files += 1
            except Exception as e:
                errors.append({"file": str(full_path), "error": str(e)})

    return {
        "total_files": total_files,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "errors": errors,
    }


def _full_build_federated(
    store: GraphStore, primary_root: Path, roots: list[Path]
) -> dict[str, Any]:
    """Federated full build over multiple registered roots (Task 10).

    Each entry in ``roots`` is registered with :class:`RepoRegistry` so
    nodes/edges parsed under it inherit the matching ``repo_id``. The
    primary ``repo_root`` (the one whose ``.better-code-review-graph`` dir backs
    the DB) is registered too so its files don't fall outside every
    root and lose their ``repo_id``.
    """
    registry, target_repos = _setup_federated_repos(store, primary_root, roots)
    stats = _run_federated_parse_loop(
        store, primary_root, roots, registry, target_repos
    )

    php_calls = store.resolve_php_calls()
    bare_calls = store.resolve_bare_calls()
    store.set_metadata("last_updated", time.strftime("%Y-%m-%dT%H:%M:%S"))
    store.set_metadata("last_build_type", "full_federated")
    store.commit()

    total_files = stats["total_files"]
    total_nodes = stats["total_nodes"]
    total_edges = stats["total_edges"]
    return {
        "status": "ok",
        "build_type": "full_federated",
        "summary": (
            f"Federated build over {len(roots) + 1} root(s): parsed "
            f"{total_files} files, created {total_nodes} nodes and "
            f"{total_edges} edges."
        ),
        "files_parsed": total_files,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "roots": [str(r) for r in [primary_root, *roots]],
        "errors": stats["errors"],
        "php_calls": php_calls,
        "bare_calls": bare_calls,
        "warnings": _php_call_warnings(php_calls) + _bare_call_warnings(bare_calls),
    }


_DEFAULT_IMPACT_PAYLOAD_BYTES = 500_000  # #315: ~500KB ceiling on impact JSON


def _estimate_payload_bytes(*payloads: list[dict] | dict) -> int:
    """Cheap upper-bound estimator for serialized JSON size.

    Bolt optimization: Using json.dumps() with C-level optimizations is measurably
    faster (approx. 30-40%) than Python's native repr() when serializing large arrays
    of dictionary objects for truncation limits, minimizing string overhead.
    """
    return sum(len(json.dumps(p, separators=(",", ":"))) for p in payloads)


# ---------------------------------------------------------------------------
# Tool 2: get_impact_radius
# ---------------------------------------------------------------------------


def get_impact_radius(
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    max_results: int = 500,
    repo_root: str | None = None,
    base: str = "HEAD~1",
    max_payload_bytes: int = _DEFAULT_IMPACT_PAYLOAD_BYTES,
    repo: str = "",
    *,
    as_of: str = "",
) -> dict[str, Any]:
    """Analyze the blast radius of changed files.

    Args:
        changed_files: Explicit list of changed file paths (relative to repo root).
                       If omitted, auto-detects from git diff.
        max_depth: How many hops to traverse in the graph (default: 2).
        max_results: Maximum number of impacted nodes to return (default: 500).
                     Maps to the BFS max_nodes parameter.
        repo_root: Repository root path. Auto-detected if omitted.
        base: Git ref for auto-detecting changes (default: HEAD~1).
        max_payload_bytes: Soft cap on serialized response size in bytes
            (default 500_000). When exceeded the impacted_nodes / edges
            arrays are truncated and ``results_truncated=True`` is set on
            the response with a hint suggesting ``max_depth=1`` or a
            narrower file scope. (#315.)
        repo: Phase 2 Task 10 — when non-empty, scope the BFS to nodes
            belonging to the given ``repo_id``. Empty (default) =
            traverse across every federated repo.
        as_of: Phase 3 Task 9 — temporal snapshot SHA. Default ``""``
            returns currently-valid rows (``valid_to_sha IS NULL``);
            non-empty returns rows where ``valid_from_sha == as_of``
            OR ``valid_to_sha == as_of``. Threaded into the seed
            ``get_nodes_by_files`` and the final
            ``get_nodes_by_qualified_names`` resolves; the BFS itself
            still runs against the cached full-graph (Task 9.5).

    Returns:
        Changed nodes, impacted nodes, impacted files, connecting edges,
        plus truncated flag and total_impacted count.
    """
    store, root = _get_store(repo_root)
    try:
        if changed_files is None:
            changed_files = get_changed_files(root, base)
            if not changed_files:
                changed_files = get_staged_and_unstaged(root)

        if not changed_files:
            return {
                "status": "ok",
                "summary": "No changed files detected.",
                "changed_nodes": [],
                "impacted_nodes": [],
                "impacted_files": [],
                "truncated": False,
                "total_impacted": 0,
            }

        # Convert to absolute paths for graph lookup
        abs_files = []
        root_resolved = root.resolve()
        for f in changed_files:
            full_path_raw = root / f
            full_path = full_path_raw.resolve()
            if not full_path.is_relative_to(root_resolved):
                continue
            if full_path_raw.is_symlink() or full_path.is_symlink():
                continue
            abs_files.append(str(full_path))

        result = store.get_impact_radius(
            abs_files,
            max_depth=max_depth,
            max_nodes=max_results,
            repo=repo,
            as_of=as_of,
        )

        changed_dicts = [node_to_dict(n) for n in result["changed_nodes"]]
        impacted_dicts = [node_to_dict(n) for n in result["impacted_nodes"]]
        edge_dicts = [edge_to_dict(e) for e in result["edges"]]
        truncated = result["truncated"]
        total_impacted = result["total_impacted"]

        summary_parts = [
            f"Blast radius for {len(changed_files)} changed file(s):",
            f"  - {len(changed_dicts)} nodes directly changed",
            f"  - {len(impacted_dicts)} nodes impacted (within {max_depth} hops)",
            f"  - {len(result['impacted_files'])} additional files affected",
        ]
        if truncated:
            summary_parts.append(
                f"  - TRUNCATED: results capped at {max_results} nodes"
                f" ({total_impacted} total impacted)"
            )

        # #315: payload-size auto-truncation. Even with max_results=500 the
        # impacted_nodes + edges arrays can blow past the conversation
        # token budget for shared utils (observed: 7.6MB, 12MB). Trim
        # iteratively until the rough JSON size fits under the soft cap.
        results_truncated = False
        results_truncated_reason: str | None = None
        original_impacted_count = len(impacted_dicts)
        original_edges_count = len(edge_dicts)
        if max_payload_bytes and max_payload_bytes > 0:
            estimated = _estimate_payload_bytes(
                changed_dicts, impacted_dicts, edge_dicts
            )
            if estimated > max_payload_bytes:
                results_truncated = True
                # Halve until we fit (or down to a minimum sample of 10 each).
                while _estimate_payload_bytes(
                    changed_dicts, impacted_dicts, edge_dicts
                ) > max_payload_bytes and (
                    len(impacted_dicts) > 10 or len(edge_dicts) > 10
                ):
                    impacted_dicts = impacted_dicts[: max(10, len(impacted_dicts) // 2)]
                    edge_dicts = edge_dicts[: max(10, len(edge_dicts) // 2)]
                results_truncated_reason = (
                    f"impact payload exceeded {max_payload_bytes} bytes "
                    f"(was approximately {estimated})"
                )
                summary_parts.append(
                    f"  - PAYLOAD TRUNCATED: kept {len(impacted_dicts)} of "
                    f"{original_impacted_count} impacted nodes / "
                    f"{len(edge_dicts)} of {original_edges_count} edges"
                )

        response: dict[str, Any] = {
            "status": "ok",
            "summary": "\n".join(summary_parts),
            "changed_files": changed_files,
            "changed_nodes": changed_dicts,
            "impacted_nodes": impacted_dicts,
            "impacted_files": result["impacted_files"],
            "edges": edge_dicts,
            "truncated": truncated,
            "total_impacted": total_impacted,
        }
        if results_truncated:
            response["results_truncated"] = True
            response["reason"] = results_truncated_reason
            response["hint"] = (
                "rerun with max_depth=1, narrow changed_files scope, or "
                "raise max_payload_bytes if you can handle a larger response"
            )
            response["original_impacted_count"] = original_impacted_count
            response["original_edges_count"] = original_edges_count
        return response
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 3: query_graph
# ---------------------------------------------------------------------------

_QUERY_PATTERNS = {
    "callers_of": "Find all functions that call a given function",
    "callees_of": "Find all functions called by a given function",
    "imports_of": "Find all imports of a given file or module",
    "importers_of": "Find all files that import a given file or module",
    "children_of": "Find all nodes contained in a file or class",
    "tests_for": "Find all tests for a given function or class",
    "inheritors_of": "Find all classes that inherit from a given class",
    "file_summary": "Get a summary of all nodes in a file",
}

# #318: cache of the last call-graph query response per repo_root so the
# spot_check action can fetch source snippets for N random callsites
# without re-running the query. Keyed by ``str(root.resolve())``.
_LAST_CALLERS_RESULT: dict[str, dict[str, Any]] = {}


def _list_kinds_in_graph(store: Any) -> list[str] | None:
    """Return distinct node kinds present in the graph (for D15 hints).

    Returns ``None`` -- not ``[]`` -- when the graph cannot be queried. An
    empty list is a factual claim that nothing is indexed, and the caller
    turns that claim into "rebuild your graph"; a failed read cannot
    support it.
    """
    try:
        cursor = store._conn.execute("SELECT DISTINCT kind FROM nodes ORDER BY kind")
        return [r["kind"] for r in cursor]
    except Exception as e:
        logger.warning(
            "Could not list node kinds from the graph (%s: %s); reporting "
            "them as unknown rather than as an empty graph.",
            type(e).__name__,
            e,
        )
        return None


def _lookup_node_directly(
    store: Any, root: Any, target: str, *, as_of: str = ""
) -> Any | None:
    """Attempt to find a node by its qualified name or file path."""
    node = store.get_node(target, as_of=as_of)
    if not node:
        full_target_raw = root / target
        try:
            root_resolved = root.resolve()
            full_target = full_target_raw.resolve()
            if (
                full_target.is_relative_to(root_resolved)
                and not full_target_raw.is_symlink()
                and not full_target.is_symlink()
            ):
                abs_target = str(full_target)
                node = store.get_node(abs_target, as_of=as_of)
        except (OSError, ValueError):
            pass
    return node


def _resolve_search_candidates(
    store: Any,
    target: str,
    pattern: str,
    original_target: str,
    repo: str = "",
    *,
    as_of: str = "",
) -> tuple[Any | None, str, dict[str, Any] | None, list[str]]:
    """Search for nodes by name and handle ambiguity/promotion."""
    candidates = store.search_nodes(target, limit=5, repo=repo, as_of=as_of)
    promoted_indexed_under: list[str] = []

    # #316: when the pattern is call-graph oriented and the only ambiguity
    # is between a File and a Function (common when a module name equals
    # a function name), the File target is meaningless -- callers_of /
    # callees_of want the Function. Auto-pick.
    if (
        len(candidates) > 1
        and pattern in ("callers_of", "callees_of")
        and "::" not in original_target
    ):
        functions = [c for c in candidates if c.kind == "Function"]
        files = [c for c in candidates if c.kind == "File"]
        non_call_kinds = [c for c in candidates if c.kind not in ("Function", "File")]
        if len(functions) == 1 and len(files) >= 1 and not non_call_kinds:
            candidates = [functions[0]]

    if len(candidates) == 1:
        node = candidates[0]
        # Bare-name target was promoted to a qualified node; surface this
        # via the D15 advisory fields when the bare target differs from
        # the resolved qualified_name.
        if "::" not in original_target and "::" in node.qualified_name:
            promoted_indexed_under = [node.qualified_name]
        return node, node.qualified_name, None, promoted_indexed_under

    if len(candidates) > 1:
        # D15: distinguish ambiguous unqualified bare-name lookup from a
        # genuine "not_found". Keep status="ambiguous" for backward compat
        # but add reason="ambiguous_unqualified" + indexed_kinds + hint.
        return (
            None,
            target,
            {
                "status": "ambiguous",
                "reason": "ambiguous_unqualified",
                "summary": (
                    f"Multiple matches for {target!r}. Please use a qualified name."
                ),
                "candidates": [node_to_dict(c) for c in candidates],
                "indexed_kinds": sorted({c.kind for c in candidates}),
                "indexed_under": [c.qualified_name for c in candidates],
                "hint": (
                    f"Multiple symbols match {target!r}. "
                    "Try qualifying with namespace from indexed_under."
                ),
            },
            [],
        )

    return None, target, None, []


def _resolve_path_fallback(
    root: Any,
    target: str,
    pattern: str,
) -> tuple[Any | None, str | None, dict[str, Any] | None]:
    """Handle path-only resolution for file-centric queries."""
    if pattern in ("file_summary", "importers_of"):
        full_target_raw = root / target
        try:
            root_resolved = root.resolve()
            full_target = full_target_raw.resolve()
            if (
                not full_target.is_relative_to(root_resolved)
                or full_target_raw.is_symlink()
                or full_target.is_symlink()
            ):
                return (
                    None,
                    target,
                    {
                        "status": "error",
                        "summary": "Invalid target path",
                    },
                )
            return None, str(full_target), None
        except (OSError, ValueError):
            return (
                None,
                target,
                {
                    "status": "error",
                    "summary": "Invalid target path",
                },
            )
    return None, None, None


def _handle_not_found(store: Any, target: str) -> dict[str, Any]:
    """Generate the not_found error response for D15."""
    indexed_kinds = _list_kinds_in_graph(store)
    response: dict[str, Any] = {
        "status": "not_found",
        "reason": "no_such_symbol",
        "summary": f"No node found matching {target!r}.",
        "indexed_kinds": indexed_kinds,
        "hint": (
            f"Symbol {target!r} not indexed in graph. "
            "Verify name spelling or pass a qualified form "
            "('file_path::Class.method')."
        ),
    }
    if indexed_kinds is None:
        # The symbol genuinely was not found, so ``not_found`` still holds --
        # but we cannot also claim the graph is empty. Saying
        # ``indexed_kinds: []`` here would send the caller off to rebuild a
        # graph whose real problem is that it will not answer queries.
        response["indexed_kinds_error"] = (
            "The graph could not be queried for its indexed node kinds, so "
            "this is 'unknown', not 'nothing indexed'. See the server log "
            "for the underlying error."
        )
    return response


def _resolve_query_target(
    store: Any,
    root: Any,
    target: str,
    pattern: str,
    repo: str = "",
    *,
    as_of: str = "",
) -> tuple[Any | None, str, dict[str, Any] | None]:
    """Resolve the query target to a node or path.

    Returns:
        tuple: (node, resolved_qn_or_path, error_response)
    """
    original_target = target

    # 1. Direct lookup (qualified name or absolute path)
    node = _lookup_node_directly(store, root, target, as_of=as_of)
    # Phase 2 Task 10: drop direct hits that don't belong to the
    # requested repo so the search-by-name fallback below can pick a
    # repo-scoped candidate instead of returning the cross-repo match.
    if node is not None and repo:
        row = store._conn.execute(
            "SELECT repo_id FROM nodes WHERE qualified_name = ?",
            (node.qualified_name,),
        ).fetchone()
        if row is None or (row["repo_id"] or "") != repo:
            node = None

    # 2. Search by name if not found directly
    promoted_indexed_under: list[str] = []
    if not node:
        node, target, error_resp, promoted_indexed_under = _resolve_search_candidates(
            store, target, pattern, original_target, repo=repo, as_of=as_of
        )
        if error_resp:
            return None, target, error_resp

    # 3. Final fallbacks if still no node
    if not node:
        node, path_target, error_resp = _resolve_path_fallback(root, target, pattern)
        if error_resp:
            return None, target, error_resp
        if path_target:
            return None, path_target, None

        # D15: bare not_found
        return None, target, _handle_not_found(store, target)

    if pattern == "importers_of":
        return node, node.file_path, None

    if promoted_indexed_under:
        # Stash advisory info on the store object as a simple side-channel.
        # query_graph() will read and propagate to the response.
        store._d15_promoted_indexed_under = promoted_indexed_under  # type: ignore[attr-defined]

    return node, node.qualified_name, None


_DYNAMIC_DISPATCH_PATTERNS_PYTHON: tuple[tuple[str, str], ...] = (
    ("asyncio.to_thread", "asyncio.to_thread("),
    ("asyncio.ensure_future", "asyncio.ensure_future("),
    ("asyncio.create_task", "asyncio.create_task("),
    ("functools.partial", "functools.partial("),
    ("partial", "partial("),
    ("map", "map("),
    ("filter", "filter("),
    ("getattr-call", "getattr("),
)

_DYNAMIC_DISPATCH_PATTERNS_JS_TS: tuple[tuple[str, str], ...] = (
    (".bind", ".bind("),
    ("setTimeout", "setTimeout("),
    ("setInterval", "setInterval("),
)


def _scan_dynamic_dispatch_hints(
    store: Any,
    node: Any,
    target_name: str,
) -> list[dict[str, Any]]:
    """Scan files in the graph that mention the target name via known
    dynamic-dispatch patterns (#331).

    Best-effort textual scan of the same file as the target plus any file
    in the graph that imports it. Returns a list of ``{file, line,
    pattern, context}`` hits suitable for surfacing in the
    ``dynamic_dispatch_hints`` field of the ``callers_of`` response.
    """
    if node is None or not target_name:
        return []
    language = (getattr(node, "language", "") or "").lower()
    if language == "python":
        patterns = _DYNAMIC_DISPATCH_PATTERNS_PYTHON
    elif language in ("javascript", "typescript"):
        patterns = _DYNAMIC_DISPATCH_PATTERNS_JS_TS
    else:
        # Heuristic only implemented for Python + JS/TS today; other
        # languages return empty rather than guessing.
        return []

    target_file = node.file_path
    candidate_files: set[str] = {target_file}
    # Add same-package siblings that the graph already indexed as files that
    # import the target's file -- those are the most likely sites for
    # asyncio.to_thread(<target>) / functools.partial(<target>).
    try:
        for e in store.get_edges_by_target(target_file, kind="IMPORTS_FROM"):  # type: ignore[attr-defined]
            candidate_files.add(e.file_path)
    except Exception as e:
        # Deliberately non-fatal: the scan still covers the target's own
        # file, which is where most dynamic-dispatch sites live. But the
        # caller gets a narrower hint set than it asked for, so say so --
        # at debug this was indistinguishable from "no importers found".
        logger.warning(
            "Could not list importers of %s (%s: %s); dynamic-dispatch hints "
            "cover only that file, so the hint list may be incomplete.",
            target_file,
            type(e).__name__,
            e,
        )

    hits: list[dict[str, Any]] = []
    for fp in candidate_files:
        try:
            text = Path(fp).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if target_name not in line:
                continue
            for label, marker in patterns:
                if marker in line and target_name in line:
                    # Avoid trivially flagging the function's own def line.
                    stripped = line.lstrip()
                    if stripped.startswith(("def ", "async def ", "class ")):
                        continue
                    hits.append(
                        {
                            "file": fp,
                            "line": line_no,
                            "pattern": label,
                            "context": line.strip()[:160],
                        }
                    )
                    break  # one hit per line is enough
    return hits


def _handle_callers_of(
    store: Any,
    node: Any,
    qn: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    # Batched search to avoid N+1 queries when resolving callers (issue #342).
    # We look for CALLS edges targeting either the qualified name or the bare name.
    search_targets = [qn]
    if node and node.name and node.name != qn:
        search_targets.append(node.name)

    edges = store.search_edges_by_target_names(
        search_targets, kind="CALLS", as_of=as_of
    )

    qns = []
    for e in edges:
        qns.append(e.source_qualified)
        edges_out.append(edge_to_dict(e))

    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))


def _handle_callees_of(
    store: Any,
    qn: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    # Batched search to avoid N+1 queries when resolving callees
    edges = store.search_edges_by_source_names([qn], kind="CALLS", as_of=as_of)
    qns = []
    for e in edges:
        qns.append(e.target_qualified)
        edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))


def _handle_imports_of(
    store: Any,
    qn: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    # Batched search to avoid N+1 queries when resolving imports
    edges = store.search_edges_by_source_names([qn], kind="IMPORTS_FROM", as_of=as_of)
    qns = []
    for e in edges:
        qns.append(e.target_qualified)
        edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                r = node_to_dict(node_map[qn_tgt])
                # Legacy key for backward compatibility
                r["import_target"] = qn_tgt
                results.append(r)
            else:
                # Fallback for external nodes not in the 'nodes' table
                results.append({"import_target": qn_tgt})


def _handle_importers_of(
    store: Any,
    abs_target: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    # Batched search to avoid N+1 queries when resolving importers
    edges = store.search_edges_by_target_names(
        [abs_target], kind="IMPORTS_FROM", as_of=as_of
    )
    # Filter out fallback bare name matches since the original call used fallback=False
    edges = [e for e in edges if e.target_qualified == abs_target]

    qns = []
    for e in edges:
        qns.append(e.source_qualified)
        edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                r = node_to_dict(node_map[qn_src])
                # Legacy keys for backward compatibility
                r["importer"] = qn_src
                r["file"] = r.get("file_path")
                results.append(r)
            else:
                # Fallback for external nodes not in the 'nodes' table
                results.append({"importer": qn_src})


def _handle_children_of(
    store: Any, qn: str, results: list[dict], edges_out: list[dict], *, as_of: str = ""
) -> None:
    # Batched search to avoid N+1 queries when resolving children
    edges = store.search_edges_by_source_names([qn], kind="CONTAINS", as_of=as_of)
    qns = []
    for e in edges:
        qns.append(e.target_qualified)
        edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))


def _handle_tests_for(
    store: Any,
    node: Any,
    target: str,
    qn: str,
    results: list[dict],
    *,
    as_of: str = "",
) -> None:
    # Batched search to avoid N+1 queries when resolving tests
    edges = store.search_edges_by_target_names([qn], kind="TESTED_BY", as_of=as_of)
    # Filter out fallback bare name matches since the original call used fallback=False
    edges = [e for e in edges if e.target_qualified == qn]

    qns = []
    for e in edges:
        qns.append(e.source_qualified)
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))
    # Also search by naming convention
    name = node.name if node else target
    test_nodes = store.search_nodes(f"test_{name}", limit=10, as_of=as_of)
    test_nodes += store.search_nodes(f"Test{name}", limit=10, as_of=as_of)
    seen = {r.get("qualified_name") for r in results}
    for t in test_nodes:
        if t.qualified_name not in seen and t.is_test:
            results.append(node_to_dict(t))


def _handle_inheritors_of(
    store: Any,
    qn: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    # Batched search to avoid N+1 queries when resolving inheritors
    edges = store.search_edges_by_target_names(
        [qn], kind=("INHERITS", "IMPLEMENTS"), as_of=as_of
    )
    # Filter out fallback bare name matches since the original call used fallback=False
    edges = [e for e in edges if e.target_qualified == qn]

    qns = []
    for e in edges:
        qns.append(e.source_qualified)
        edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))


def _handle_file_summary(
    store: Any, abs_path: str, results: list[dict], *, as_of: str = ""
) -> None:
    file_nodes = store.get_nodes_by_file(abs_path, as_of=as_of)
    for n in file_nodes:
        results.append(node_to_dict(n))


# D16: allowed languages for the languages filter parameter.
# Mirrors the parser's supported language set (see CLAUDE.md "Supported languages").
_ALLOWED_LANGUAGES: set[str] = {
    "python",
    "typescript",
    "javascript",
    "go",
    "rust",
    "java",
    "csharp",
    "ruby",
    "kotlin",
    "swift",
    "php",
    "c",
    "cpp",
    "solidity",
}


def _validate_languages(languages: list[str] | None) -> dict[str, Any] | None:
    """Validate languages filter values; return error dict or None."""
    if languages is None:
        return None
    invalid = sorted(set(languages) - _ALLOWED_LANGUAGES)
    if invalid:
        return {
            "status": "error",
            "error": (
                f"invalid_languages: {invalid}; allowed: {sorted(_ALLOWED_LANGUAGES)}"
            ),
        }
    return None


def _add_query_response_decorations(
    store: "GraphStore",
    root: Path,
    response: dict[str, Any],
    pattern: str,
    target: str,
    node: Any,
    results: list[dict],
    edges_out: list[dict],
) -> None:
    """Add promotion hints, dynamic dispatch hints, and cache results."""
    # D15: surface bare-name -> qualified-name promotion (issue #339).
    promoted = getattr(store, "_d15_promoted_indexed_under", None)
    if promoted:
        response["resolved_from_unqualified"] = True
        response["indexed_under"] = list(promoted)
        response["hint"] = (
            f"Bare name '{target}' was auto-resolved to "
            f"{promoted[0]}. Pass the qualified form to disambiguate."
        )

    # #331: dynamic-dispatch blind-spot warning for callers_of /
    # callees_of. Surfaces same-file references via patterns
    # (asyncio.to_thread, functools.partial, decorator, etc.) that
    # the AST CALLS edge does not capture.
    if pattern in ("callers_of", "callees_of") and node is not None:
        hits = _scan_dynamic_dispatch_hints(store, node, node.name)
        if hits:
            response["dynamic_dispatch_hints"] = {
                "target_file": node.file_path,
                "same_file_references": hits[:50],
                "note": (
                    "These are likely additional callers the AST "
                    "edge does not link. Grep before concluding the "
                    "caller list is complete."
                ),
            }

    # #318: cache callsite-shaped results so `spot_check` can pull a
    # random sample of N source snippets without re-running the query.
    if pattern in (
        "callers_of",
        "callees_of",
        "inheritors_of",
        "importers_of",
    ):
        _LAST_CALLERS_RESULT[str(root.resolve())] = {
            "pattern": pattern,
            "target": target,
            "edges": list(edges_out),
            "results": list(results),
        }


def _filter_results_by_repo(
    store: "GraphStore",
    repo: str,
    results: list[dict],
    edges_out: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Narrow results and edges to the requested repo_id (Phase 2 Task 10)."""
    if not repo:
        return results, edges_out

    qns_to_check: list[str] = []
    for r in results:
        qn = r.get("qualified_name")
        if qn is None:
            # importers_of / imports_of dicts use importer /
            # import_target keys instead of qualified_name.
            # Fall back to the most likely qualified field.
            qn = r.get("importer") or r.get("import_target")
        if qn is not None:
            qns_to_check.append(qn)

    repo_map: dict[str, str] = {}
    if qns_to_check:
        cursor = store._conn.execute(
            "SELECT n.qualified_name, n.repo_id FROM nodes n "
            "JOIN json_each(?) j ON n.qualified_name = j.value",
            (json.dumps(qns_to_check),),
        )
        repo_map = {row["qualified_name"]: row["repo_id"] for row in cursor}

    kept_qns: set[str] = set()
    filtered_results = []
    for r in results:
        qn = r.get("qualified_name")
        if qn is None:
            qn = r.get("importer") or r.get("import_target")
        if qn is None:
            filtered_results.append(r)
            continue
        r_repo = repo_map.get(qn)
        if r_repo is not None and (r_repo or "") == repo:
            kept_qns.add(qn)
            filtered_results.append(r)

    results = filtered_results
    edges_out = [
        e
        for e in edges_out
        if e.get("source") in kept_qns or e.get("target") in kept_qns
    ]
    return results, edges_out


def _dispatch_query_pattern(
    store: "GraphStore",
    pattern: str,
    target: str,
    node: Any,
    resolved_qn_or_path: str,
    results: list[dict],
    edges_out: list[dict],
    languages: list[str] | None = None,
    as_of: str = "",
) -> list[dict]:
    """Execute the core logic for the requested query pattern."""
    if pattern == "callers_of":
        _handle_callers_of(
            store, node, resolved_qn_or_path, results, edges_out, as_of=as_of
        )
    elif pattern == "callees_of":
        _handle_callees_of(store, resolved_qn_or_path, results, edges_out, as_of=as_of)
    elif pattern == "imports_of":
        _handle_imports_of(store, resolved_qn_or_path, results, edges_out, as_of=as_of)
    elif pattern == "importers_of":
        _handle_importers_of(
            store, resolved_qn_or_path, results, edges_out, as_of=as_of
        )
    elif pattern == "children_of":
        _handle_children_of(store, resolved_qn_or_path, results, edges_out, as_of=as_of)
    elif pattern == "tests_for":
        _handle_tests_for(
            store, node, target, resolved_qn_or_path, results, as_of=as_of
        )
    elif pattern == "inheritors_of":
        _handle_inheritors_of(
            store, resolved_qn_or_path, results, edges_out, as_of=as_of
        )
    elif pattern == "file_summary":
        _handle_file_summary(store, resolved_qn_or_path, results, as_of=as_of)

    # D16: filter tests_for results by language if requested.
    if pattern == "tests_for" and languages is not None:
        results = [r for r in results if r.get("language") in languages]

    return results


def query_graph(
    pattern: str,
    target: str,
    repo_root: str | None = None,
    languages: list[str] | None = None,
    repo: str = "",
    *,
    as_of: str = "",
) -> dict[str, Any]:
    """Run a predefined graph query.

    Args:
        pattern: Query pattern. One of: callers_of, callees_of, imports_of,
                 importers_of, children_of, tests_for, inheritors_of, file_summary.
        target: The node name, qualified name, or file path to query about.
        repo_root: Repository root path. Auto-detected if omitted.
        languages: Optional list of language names to filter results to. Only
            applies to ``tests_for`` (filters returned test nodes by language).
            Allowed values: python, typescript, javascript, go, rust, java,
            csharp, ruby, kotlin, swift, php, c, cpp, solidity.
        repo: Phase 2 Task 10 — when non-empty, restrict the result set
            to nodes whose ``repo_id`` matches. Default ``""`` searches
            across every registered repo (legacy behaviour). Used to
            disambiguate same-named symbols across federated repos.
        as_of: Phase 3 Task 9 — when non-empty, return the temporal
            snapshot at the requested 40-char SHA (rows where
            ``valid_from_sha == as_of`` OR ``valid_to_sha == as_of``).
            Default ``""`` returns currently-valid rows
            (``valid_to_sha IS NULL``) — first use of the temporal
            columns by the read layer.

    Returns:
        Matching nodes and edges for the query.
    """
    if len(target) > 1000:
        return {
            "status": "error",
            "error": "Target too long (exceeds 1000 characters).",
        }

    lang_err = _validate_languages(languages)
    if lang_err:
        return lang_err

    store, root = _get_store(repo_root)
    try:
        if pattern not in _QUERY_PATTERNS:
            return {
                "status": "error",
                "error": f"Unknown pattern '{pattern}'. Available: {list(_QUERY_PATTERNS.keys())}",
            }

        results: list[dict] = []
        edges_out: list[dict] = []

        # For callers_of, skip common builtins early (bare names only)
        if (
            pattern == "callers_of"
            and target in _BUILTIN_CALL_NAMES
            and "::" not in target
        ):
            return {
                "status": "ok",
                "pattern": pattern,
                "target": target,
                "description": _QUERY_PATTERNS[pattern],
                "summary": f"'{target}' is a common builtin — callers_of skipped to avoid noise.",
                "results": [],
                "edges": [],
            }

        node, resolved_qn_or_path, error_resp = _resolve_query_target(
            store, root, target, pattern, repo=repo, as_of=as_of
        )
        if error_resp:
            return error_resp

        results = _dispatch_query_pattern(
            store,
            pattern,
            target,
            node,
            resolved_qn_or_path,
            results,
            edges_out,
            languages=languages,
            as_of=as_of,
        )

        results, edges_out = _filter_results_by_repo(store, repo, results, edges_out)

        response: dict[str, Any] = {
            "status": "ok",
            "pattern": pattern,
            "target": target,
            "description": _QUERY_PATTERNS[pattern],
            "summary": f"Found {len(results)} result(s) for {pattern}('{target}')",
            "header": _build_response_header(store, get_db_path(root)),
            "results": results,
            "edges": edges_out,
        }

        _add_query_response_decorations(
            store, root, response, pattern, target, node, results, edges_out
        )

        return response
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 3.5: diff_graph (Phase 3 Task 9)
# ---------------------------------------------------------------------------


def diff_graph(
    repo_root: str | None = None,
    *,
    from_sha: str = "",
    to_sha: str = "",
    repo: str = "",
) -> dict[str, Any]:
    """Return nodes added / removed / modified between two commit SHAs.

    The diff is computed entirely from the temporal columns set by the
    v2 ingest path (:class:`TemporalIndex`). It does NOT require the
    parser to re-run — the close-out + supersede markers already on
    each row encode every transition.

    * **added**: rows whose ``valid_from_sha == to_sha`` AND whose
      ``qualified_name`` does NOT also appear in the closed-out set
      (i.e. genuinely new symbols at ``to_sha``).
    * **removed**: rows whose ``valid_to_sha == to_sha`` AND whose
      ``qualified_name`` does NOT also appear in the introduced set
      (i.e. symbols deleted between ``from_sha`` and ``to_sha`` with
      no replacement).
    * **modified**: ``qualified_name``s that show up in BOTH sets —
      one row closed at ``to_sha``, another row introduced at
      ``to_sha``. This is the supersede signature emitted when a
      function's source text changes across commits.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.
        from_sha: Earlier commit SHA. Required.
        to_sha: Later commit SHA. Required.
        repo: Optional ``repo_id`` filter (Phase 2 Task 10 semantics).
            Empty (default) returns the diff across every registered
            repo.

    Returns:
        ``{"from_sha": ..., "to_sha": ..., "added": [...],
        "removed": [...], "modified": [...]}``. ``added`` /
        ``removed`` entries are dicts with ``id``, ``qualified_name``,
        ``kind``; ``modified`` entries are dicts with just
        ``qualified_name``.
    """
    if not from_sha or not to_sha:
        return {"error": "diff requires both from_sha and to_sha"}

    store, _ = _get_store(repo_root)
    try:
        # Build the optional repo filter once. The base SQL stays
        # static — Bandit B608 is happy because both branches expand
        # to a fixed string literal at f-string interpolation time.
        if repo:
            added_cursor = store._conn.execute(
                "SELECT id, qualified_name, kind FROM nodes "
                "WHERE valid_from_sha = ? AND repo_id = ?",
                (to_sha, repo),
            )
            added_rows = list(added_cursor)
            removed_cursor = store._conn.execute(
                "SELECT id, qualified_name, kind FROM nodes "
                "WHERE valid_to_sha = ? AND repo_id = ?",
                (to_sha, repo),
            )
            removed_rows = list(removed_cursor)
        else:
            added_cursor = store._conn.execute(
                "SELECT id, qualified_name, kind FROM nodes WHERE valid_from_sha = ?",
                (to_sha,),
            )
            added_rows = list(added_cursor)
            removed_cursor = store._conn.execute(
                "SELECT id, qualified_name, kind FROM nodes WHERE valid_to_sha = ?",
                (to_sha,),
            )
            removed_rows = list(removed_cursor)

        closed_qns = {row["qualified_name"] for row in removed_rows}
        new_qns = {row["qualified_name"] for row in added_rows}
        modified_qns = closed_qns & new_qns

        purely_added = [
            r for r in added_rows if r["qualified_name"] not in modified_qns
        ]
        purely_removed = [
            r for r in removed_rows if r["qualified_name"] not in modified_qns
        ]

        return {
            "from_sha": from_sha,
            "to_sha": to_sha,
            "added": [
                {
                    "id": r["id"],
                    "qualified_name": r["qualified_name"],
                    "kind": r["kind"],
                }
                for r in purely_added
            ],
            "removed": [
                {
                    "id": r["id"],
                    "qualified_name": r["qualified_name"],
                    "kind": r["kind"],
                }
                for r in purely_removed
            ],
            "modified": [{"qualified_name": qn} for qn in sorted(modified_qns)],
        }
    finally:
        store.close()


def review_delta(
    repo_root: str | None = None,
    *,
    from_sha: str = "",
    to_sha: str = "",
    show_line_shifts: bool = False,
    repo: str = "",
) -> dict[str, Any]:
    """Review what changed between two commit SHAs (token-efficient).

    Wraps :func:`diff_graph` with an opt-in ``show_line_shifts`` mode.
    When the flag is set, the response gains a ``line_shifts`` list
    pointing at every symbol whose ``line_start`` moved between the
    two commits — useful for refactor auditing ("this function moved
    from line 10 to line 42, did anything break?").

    Args:
        repo_root: Repository root path. Auto-detected if omitted.
        from_sha: Earlier commit SHA. Required.
        to_sha: Later commit SHA. Required.
        show_line_shifts: When True, include nodes whose ``line_start``
            changed between ``from_sha`` and ``to_sha``. Default False
            (response is just the ``diff`` payload to keep it light).
        repo: Optional ``repo_id`` filter (Phase 2 Task 10 semantics).
            Empty (default) returns the delta across every registered
            repo.

    Returns:
        ``{"diff": <diff_graph payload>, "line_shifts": [...] (when
        requested)}``. ``line_shifts`` entries are dicts with
        ``qualified_name``, ``before_line`` (the closed-out row's
        ``line_start``) and ``after_line`` (the freshly introduced
        row's ``line_start``).
    """
    if not from_sha or not to_sha:
        return {"error": "review_delta requires both from_sha and to_sha"}
    diff_result = diff_graph(repo_root, from_sha=from_sha, to_sha=to_sha, repo=repo)
    if "error" in diff_result:
        return diff_result
    payload: dict[str, Any] = {"diff": diff_result}
    if show_line_shifts:
        payload["line_shifts"] = _collect_line_shifts(repo_root, from_sha, to_sha, repo)
    return payload


def _collect_line_shifts(
    repo_root: str | None,
    from_sha: str,
    to_sha: str,
    repo: str,
) -> list[dict[str, Any]]:
    """Return ``line_start`` shifts across the close-out + new-row pair at ``to_sha``.

    Joins the row closed at ``to_sha`` (``valid_to_sha = to_sha``)
    against the row introduced at ``to_sha`` (``valid_from_sha =
    to_sha``) on ``qualified_name`` and surfaces the line-number
    delta. Same-line supersedes (body changed but ``line_start``
    unchanged) are excluded by the SQL ``!=`` predicate.

    The ``from_sha`` argument is reserved for a future ancestor-walk
    scope check; the v1 implementation only needs ``to_sha`` because
    every supersede transition is anchored on the new commit's SHA.
    """
    del from_sha  # reserved for future ancestor-walk scope check
    store, _ = _get_store(repo_root)
    try:
        if repo:
            cursor = store._conn.execute(
                "SELECT old.qualified_name, old.line_start AS before_line, "
                "new.line_start AS after_line "
                "FROM nodes old "
                "JOIN nodes new ON old.qualified_name = new.qualified_name "
                "WHERE old.valid_to_sha = ? "
                "  AND new.valid_from_sha = ? "
                "  AND old.line_start != new.line_start "
                "  AND old.repo_id = ? "
                "  AND new.repo_id = ?",
                (to_sha, to_sha, repo, repo),
            )
        else:
            cursor = store._conn.execute(
                "SELECT old.qualified_name, old.line_start AS before_line, "
                "new.line_start AS after_line "
                "FROM nodes old "
                "JOIN nodes new ON old.qualified_name = new.qualified_name "
                "WHERE old.valid_to_sha = ? "
                "  AND new.valid_from_sha = ? "
                "  AND old.line_start != new.line_start",
                (to_sha, to_sha),
            )
        return [
            {
                "qualified_name": row[0],
                "before_line": row[1],
                "after_line": row[2],
            }
            for row in cursor
        ]
    finally:
        store.close()


def spot_check_last_callers(
    n: int = 3,
    repo_root: str | None = None,
    context_lines: int = 2,
) -> dict[str, Any]:
    """Return source snippets for ``n`` random callsites from the last
    callers_of / callees_of / inheritors_of / importers_of result (#318).

    Lets a reviewer enforce per-query spot-check discipline (read one
    source line per graph result to confirm it wasn't a false positive)
    in 1 MCP call instead of N file Reads.

    Args:
        n: Number of random callsites to sample (default 3).
        repo_root: Repository root path. Auto-detected if omitted.
        context_lines: Lines of context to include before/after each
            callsite line (default 2).

    Returns:
        ``samples`` list of ``{file, line, snippet, source_qualified,
        target_qualified}`` plus the ``pattern`` and ``target`` of the
        cached query.
    """
    import random

    _, root = _get_store(repo_root)
    cached = _LAST_CALLERS_RESULT.get(str(root.resolve()))
    if not cached:
        return {
            "status": "no_cache",
            "summary": (
                "No prior callers_of/callees_of/inheritors_of/importers_of "
                "result cached for this repo. Run that query first."
            ),
            "samples": [],
        }

    edges = cached["edges"]
    if not edges:
        return {
            "status": "ok",
            "summary": "No edges in the last result to sample.",
            "pattern": cached["pattern"],
            "target": cached["target"],
            "samples": [],
        }

    sample_count = min(max(1, int(n)), len(edges))
    sampled = random.sample(edges, sample_count)
    samples: list[dict[str, Any]] = []
    for edge in sampled:
        file_path = edge.get("file_path") or ""
        line_no = int(edge.get("line") or 0)
        snippet = ""
        if file_path and line_no > 0:
            try:
                lines = (
                    Path(file_path)
                    .read_text(encoding="utf-8", errors="replace")
                    .splitlines()
                )
                start = max(0, line_no - 1 - context_lines)
                end = min(len(lines), line_no + context_lines)
                snippet = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
            except OSError:
                snippet = "(could not read file)"
        samples.append(
            {
                "file": file_path,
                "line": line_no,
                # XPIA: snippet is raw text read from a file in the
                # reviewed repo -- untrusted third-party content. The
                # "(could not read file)" fallback is server-synthesized
                # status text, not third-party content, so it stays
                # unwrapped (mirrors wet-mcp's asymmetric error handling).
                "snippet": (
                    snippet
                    if snippet == "(could not read file)"
                    else wrap_external_content(snippet)
                ),
                "source_qualified": edge.get("source_qualified"),
                "target_qualified": edge.get("target_qualified"),
            }
        )

    return build_external_tool_result(
        {
            "status": "ok",
            "summary": (
                f"Sampled {len(samples)} of {len(edges)} callsites from last "
                f"{cached['pattern']}('{cached['target']}')."
            ),
            "pattern": cached["pattern"],
            "target": cached["target"],
            "samples": samples,
        }
    )


def _get_git_content(root: Path, base: str, rel_path: str) -> bytes | None:
    """Fetch file content from a specific git ref."""
    import shutil
    import subprocess

    # SECURITY: Prevent argument injection if base starts with a hyphen
    if base.startswith("-"):
        return None

    try:
        git_bin = shutil.which("git") or "git"
        proc = subprocess.run(
            [git_bin, "show", "--end-of-options", f"{base}:{rel_path}"],
            cwd=str(root),
            capture_output=True,
            timeout=15,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if proc.returncode == 0:
            return proc.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _get_symbol_lines(parser: Any, full_path: Path, source: bytes) -> dict[str, int]:
    """Extract symbol names and their start lines from source code bytes.

    An ordinary per-file parse error yields ``{}`` so one bad file cannot
    fail the whole comparison. A :class:`GrammarUnavailableError` is not a
    per-file problem though -- the host cannot parse *anything*, so every
    file would report "no symbols" and the caller would conclude nothing
    moved. That one is re-raised for the tool boundary to report.
    """
    from .parser import GrammarUnavailableError

    try:
        nodes, _ = parser.parse_bytes(full_path, source)
        return {
            f"{n.parent_name}.{n.name}" if n.parent_name else n.name: n.line_start
            for n in nodes
            if n.kind == "Function" and n.line_start is not None
        }
    except GrammarUnavailableError:
        raise
    except Exception as e:
        logger.debug("Exception in %s: %s", __name__, e)
        return {}


def _detect_line_shifts(
    base_lines: dict[str, int], head_lines: dict[str, int], rel_path: str
) -> list[dict[str, Any]]:
    """Compare symbol line numbers and return detected shifts."""
    shifts = []
    for symbol, base_line in base_lines.items():
        head_line = head_lines.get(symbol)
        if head_line is None:
            continue  # removed -- out of scope for line-drift
        if head_line == base_line:
            continue
        shifts.append(
            {
                "symbol": symbol,
                "file": rel_path,
                "base_line": base_line,
                "head_line": head_line,
                "delta": head_line - base_line,
            }
        )
    return shifts


def renamed_in_diff(
    base: str = "HEAD~1",
    changed_files: list[str] | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Report symbols whose callsite line numbers shifted between ``base``
    and HEAD (#320).

    Reads each file at ``base`` via ``git show <base>:<file>``, parses it
    with the same tree-sitter pipeline as the live graph, and compares
    Function ``line_start`` per qualified name with the current file's
    symbols. Surfaces only symbols where the line shifted -- adds /
    removes are out of scope (the regular ``review`` flow already covers
    them). Useful for Stage 6 audits of large refactors where the question
    is "did this symbol genuinely move, or did the line just slide?".

    Args:
        base: Git ref to compare against (default ``HEAD~1``).
        changed_files: Files to check. Auto-detected from ``git diff base..HEAD``
            when omitted.
        repo_root: Repository root. Auto-detected if omitted.

    Returns:
        ``shifts`` list of ``{symbol, file, base_line, head_line, delta}``,
        or ``status: "error"`` when no grammar could be loaded at all.
    """
    from .parser import CodeParser, GrammarUnavailableError

    store, root = _get_store(repo_root)
    try:
        if changed_files is None:
            changed_files = get_changed_files(root, base)
        if not changed_files:
            return {
                "status": "ok",
                "summary": "No changed files detected.",
                "base": base,
                "shifts": [],
            }

        parser = CodeParser()
        shifts: list[dict[str, Any]] = []
        repo_resolved = root.resolve()

        for rel_path in changed_files:
            full_path_raw = root / rel_path
            try:
                full_path = full_path_raw.resolve()
            except OSError:
                continue
            if not full_path.is_relative_to(repo_resolved):
                continue
            if full_path_raw.is_symlink() or full_path.is_symlink():
                continue
            if not full_path.is_file():
                continue
            if parser.detect_language(full_path) is None:
                continue

            base_source = _get_git_content(root, base, rel_path)
            if not base_source:
                continue

            base_lines = _get_symbol_lines(parser, full_path, base_source)
            try:
                head_source = full_path.read_bytes()
            except OSError:
                continue
            head_lines = _get_symbol_lines(parser, full_path, head_source)

            shifts.extend(_detect_line_shifts(base_lines, head_lines, rel_path))

        return {
            "status": "ok",
            "summary": (
                f"Found {len(shifts)} symbol(s) whose callsite line shifted "
                f"between {base} and HEAD."
            ),
            "base": base,
            "shifts": shifts,
        }
    except GrammarUnavailableError as e:
        # No grammar loads on this host, so "no shifts" would be a lie.
        # MCP tools report failure in the payload rather than raising.
        return {
            "status": "error",
            "error": str(e),
            "base": base,
            "shifts": [],
        }
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 4: get_review_context
# ---------------------------------------------------------------------------


def _filter_valid_paths(root: Path, changed_files: list[str]) -> list[str]:
    """Resolve and filter paths for safety and validity.

    Uses a dual-cache system to minimize OS-level I/O while preserving original
    symlink handling logic.
    """
    abs_files = []
    root_resolved = root.resolve()

    result_cache: dict[str, str | None] = {}
    parent_cache: dict[Path, Path | None] = {}

    for f in changed_files:
        if f in result_cache:
            res = result_cache[f]
            if res is not None:
                abs_files.append(res)
            continue

        full_path_raw = root / f
        try:
            parent_raw = full_path_raw.parent
            if parent_raw not in parent_cache:
                try:
                    parent_cache[parent_raw] = parent_raw.resolve(strict=True)
                except OSError:
                    # Parent directory might not exist yet if it's a deleted file,
                    # fallback to resolving the full path.
                    parent_cache[parent_raw] = None

            parent_resolved = parent_cache[parent_raw]
            if parent_resolved:
                full_path = parent_resolved / full_path_raw.name
            else:
                full_path = full_path_raw.resolve()

            if not full_path.is_relative_to(root_resolved):
                result_cache[f] = None
                continue

            if full_path_raw.is_symlink() or full_path.is_symlink():
                result_cache[f] = None
                continue

            res_str = str(full_path)
            result_cache[f] = res_str
            abs_files.append(res_str)
        except (OSError, ValueError):
            result_cache[f] = None
            continue

    return abs_files


def _get_source_snippets(
    root: Path,
    changed_files: list[str],
    changed_nodes: list[Any],
    max_lines_per_file: int,
) -> dict[str, str]:
    """Generate source snippets for changed files."""
    snippets = {}
    root_resolved = root.resolve()

    # Deduplicate changed_files while preserving order
    unique_files = list(dict.fromkeys(changed_files))
    parent_cache: dict[Path, Path | None] = {}

    for rel_path in unique_files:
        full_path_raw = root / rel_path
        try:
            parent_raw = full_path_raw.parent
            if parent_raw not in parent_cache:
                try:
                    parent_cache[parent_raw] = parent_raw.resolve(strict=True)
                except OSError:
                    parent_cache[parent_raw] = None

            parent_resolved = parent_cache[parent_raw]
            if parent_resolved:
                full_path = parent_resolved / full_path_raw.name
            else:
                full_path = full_path_raw.resolve()

            if not full_path.is_relative_to(root_resolved):
                continue
            if full_path_raw.is_symlink() or full_path.is_symlink():
                continue

            if full_path.is_file():
                try:
                    lines = full_path.read_text(errors="replace").splitlines()
                    if len(lines) > max_lines_per_file:
                        snippets[rel_path] = _extract_relevant_lines(
                            lines, changed_nodes, str(full_path)
                        )
                    else:
                        snippets[rel_path] = "\n".join(
                            f"{i + 1}: {line}" for i, line in enumerate(lines)
                        )
                except (OSError, UnicodeDecodeError):
                    snippets[rel_path] = "(could not read file)"
        except (OSError, ValueError):
            continue
    return snippets


def _build_review_summary_text(
    changed_files_count: int,
    impact: dict[str, Any],
    guidance: str,
) -> str:
    """Construct the summary text for the review context."""
    summary_parts = [
        f"Review context for {changed_files_count} changed file(s):",
        f"  - {len(impact['changed_nodes'])} directly changed nodes",
        f"  - {len(impact['impacted_nodes'])} impacted nodes"
        f" in {len(impact['impacted_files'])} files",
        "",
        "Review guidance:",
        guidance,
    ]
    return "\n".join(summary_parts)


def _compute_untested_functions(
    impact: dict[str, Any],
    languages: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return changed Function nodes lacking TESTED_BY edges.

    D16: Optional ``languages`` filter scopes the list to functions whose
    ``language`` field matches one of the given values. Mitigates the
    cross-language false positive (issue #340) where Python implementations
    are flagged untested simply because tests live in JS/TS or in
    integration test fixtures.
    """
    tested_qns = set()
    for e in impact["edges"]:
        if e.kind == "TESTED_BY":
            tested_qns.add(e.source_qualified)
            tested_qns.add(e.target_qualified)

    out: list[dict[str, Any]] = []
    for n in impact["changed_nodes"]:
        if n.kind != "Function" or n.is_test:
            continue
        if n.qualified_name in tested_qns:
            continue
        if languages is not None and n.language not in languages:
            continue
        out.append(node_to_dict(n))
    return out


def get_review_context(
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    include_source: bool = True,
    max_lines_per_file: int = 200,
    repo_root: str | None = None,
    base: str = "HEAD~1",
    languages: list[str] | None = None,
    repo: str = "",
) -> dict[str, Any]:
    """Generate a focused review context from changed files.

    Builds a token-optimized subgraph + source snippets for code review.

    Args:
        changed_files: Files to review (auto-detected from git diff if omitted).
        max_depth: Impact radius depth (default: 2).
        include_source: Whether to include source code snippets (default: True).
        max_lines_per_file: Max source lines per file in output (default: 200).
        repo_root: Repository root path. Auto-detected if omitted.
        base: Git ref for change detection (default: HEAD~1).
        languages: Optional list of language names to scope the
            ``untested_functions`` field to. Functions whose ``language``
            isn't in the list are excluded. ``review_guidance`` text is
            re-derived from the filtered list. Allowed values: python,
            typescript, javascript, go, rust, java, csharp, ruby, kotlin,
            swift, php, c, cpp, solidity. (D16, fixes #340.)
        repo: Phase 2 Task 10 — when non-empty, scope the impact subgraph
            to nodes whose ``repo_id`` matches. Empty (default) leaves
            the cross-repo behaviour unchanged.

    Returns:
        Structured review context with subgraph, source snippets, and review guidance.
    """
    lang_err = _validate_languages(languages)
    if lang_err:
        return lang_err

    store, root = _get_store(repo_root)
    try:
        if changed_files is None:
            changed_files = get_changed_files(root, base)
            if not changed_files:
                changed_files = get_staged_and_unstaged(root)

        if not changed_files:
            return {
                "status": "ok",
                "summary": "No changes detected. Nothing to review.",
                "context": {},
            }

        abs_files = _filter_valid_paths(root, changed_files)
        impact = store.get_impact_radius(abs_files, max_depth=max_depth, repo=repo)

        untested_functions = _compute_untested_functions(impact, languages=languages)

        context: dict[str, Any] = {
            "changed_files": changed_files,
            "impacted_files": impact["impacted_files"],
            "graph": {
                "changed_nodes": [node_to_dict(n) for n in impact["changed_nodes"]],
                "impacted_nodes": [node_to_dict(n) for n in impact["impacted_nodes"]],
                "edges": [edge_to_dict(e) for e in impact["edges"]],
            },
            "untested_functions": untested_functions,
        }
        if languages is not None:
            context["languages_filter"] = list(languages)

        if include_source:
            # XPIA: source_snippets is raw text read from files in the
            # reviewed repo -- untrusted third-party content -- wrap each
            # snippet in envelope markers before it reaches the caller.
            # The "(could not read file)" fallback is server-synthesized
            # status text, not third-party content, so it stays unwrapped
            # (mirrors wet-mcp's asymmetric error handling).
            context["source_snippets"] = {
                path: (
                    text
                    if text == "(could not read file)"
                    else wrap_external_content(text)
                )
                for path, text in _get_source_snippets(
                    root, changed_files, impact["changed_nodes"], max_lines_per_file
                ).items()
            }

        guidance = _generate_review_guidance(impact, changed_files, languages=languages)
        context["review_guidance"] = guidance

        result = {
            "status": "ok",
            "summary": _build_review_summary_text(len(changed_files), impact, guidance),
            "context": context,
        }
        if include_source:
            result = build_external_tool_result(result)
        return result
    finally:
        store.close()


def _extract_relevant_lines(lines: list[str], nodes: list, file_path: str) -> str:
    """Extract only the lines relevant to changed nodes."""
    ranges = []
    for n in nodes:
        if n.file_path == file_path:
            start = max(0, n.line_start - 3)  # 2 lines context before
            end = min(len(lines), n.line_end + 2)  # 1 line context after
            ranges.append((start, end))

    if not ranges:
        # Show first N lines as fallback
        return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines[:50]))

    # Merge overlapping ranges
    ranges.sort()
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    parts: list[str] = []
    for start, end in merged:
        if parts:
            parts.append("...")
        for i in range(start, end):
            parts.append(f"{i + 1}: {lines[i]}")

    return "\n".join(parts)


def _generate_review_guidance(
    impact: dict,
    changed_files: list[str],
    languages: list[str] | None = None,
) -> str:
    """Generate review guidance based on the impact analysis.

    Args:
        impact: Impact-radius analysis output.
        changed_files: List of changed file paths (relative).
        languages: Optional language filter — when set, restrict the
            untested-function warning to functions whose ``language`` is
            in the list. (D16, fixes #340.)
    """
    guidance_parts = []

    # Check for test coverage
    tested_funcs = set()
    inheritance_edges_count = 0
    for e in impact["edges"]:
        if e.kind == "TESTED_BY":
            tested_funcs.add(e.source_qualified)
        elif e.kind in ("INHERITS", "IMPLEMENTS"):
            inheritance_edges_count += 1

    untested = []
    for n in impact["changed_nodes"]:
        if (
            n.kind == "Function"
            and not n.is_test
            and n.qualified_name not in tested_funcs
        ):
            if languages is None or n.language in languages:
                untested.append(n)

    if untested:
        guidance_parts.append(
            f"- {len(untested)} changed function(s) lack test coverage: "
            + ", ".join(n.name for n in untested[:5])
        )

    # Check for wide blast radius
    if len(impact["impacted_nodes"]) > 20:
        guidance_parts.append(
            f"- Wide blast radius: {len(impact['impacted_nodes'])} nodes impacted. "
            "Review callers and dependents carefully."
        )

    # Check for inheritance changes
    if inheritance_edges_count > 0:
        guidance_parts.append(
            f"- {inheritance_edges_count} inheritance/implementation relationship(s) affected. "
            "Check for Liskov substitution violations."
        )

    # Check for cross-file impact
    impacted_file_count = len(impact["impacted_files"])
    if impacted_file_count > 3:
        guidance_parts.append(
            f"- Changes impact {impacted_file_count} other files."
            " Consider splitting into smaller PRs."
        )

    if not guidance_parts:
        guidance_parts.append(
            "- Changes appear well-contained with minimal blast radius."
        )

    return "\n".join(guidance_parts)


# ---------------------------------------------------------------------------
# Tool 5: semantic_search_nodes
# ---------------------------------------------------------------------------


def _looks_like_literal_identifier(query: str) -> bool:
    """Heuristic for #317: would keyword-substring search on this query
    plausibly hit the user's intent?

    Single-token symbols (``foo``, ``foo_bar``, ``fooBar``,
    ``FooBar``, ``foo.bar``, ``foo::bar``) look like identifiers and are
    fine in keyword mode. Multi-word phrases, sentences, or queries with
    spaces / punctuation suggest semantic intent and warrant a warning
    when no embeddings are available.
    """
    q = query.strip()
    if not q:
        return True
    # Anything containing whitespace or sentence punctuation is treated as
    # a natural-language phrase (semantic intent).
    for ch in (" ", "\t", "\n", "?", "!", ","):
        if ch in q:
            return False
    # Lone allowed identifier characters: alnum, underscore, dot, hyphen,
    # slash, double-colon (qualified-name separator).
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-/:")
    return all(ch in allowed for ch in q)


def semantic_search_nodes(
    query: str,
    kind: str | None = None,
    limit: int = 20,
    repo_root: str | None = None,
    repo: str = "",
    *,
    as_of: str = "",
) -> dict[str, Any]:
    """Search for nodes by name, keyword, or semantic similarity.

    Uses vector embeddings for semantic search if available (install with
    `pip install code-review-graph[embeddings]`). Falls back to keyword
    matching otherwise.

    Args:
        query: Search string to match against node names and qualified names.
        kind: Optional filter by node kind (File, Class, Function, Type, Test).
        limit: Maximum results to return (default: 20).
        repo_root: Repository root path. Auto-detected if omitted.
        repo: Phase 2 Task 10 — when non-empty, scope to nodes whose
            ``repo_id`` matches. Default ``""`` searches across every
            registered repo.
        as_of: Phase 3 Task 9 — temporal snapshot SHA. Empty (default)
            returns currently-valid rows; non-empty returns rows where
            ``valid_from_sha == as_of`` OR ``valid_to_sha == as_of``.
            When set the path forces the keyword fallback (the vector
            store has no temporal column) so the SQL filter applies.

    Returns:
        Ranked list of matching nodes.
    """
    if len(query) > 1000:
        return {
            "status": "error",
            "error": "Query too long (exceeds 1000 characters).",
        }

    store, root = _get_store(repo_root)
    try:
        db_path = get_db_path(root)
        backend = init_backend()
        emb_store = EmbeddingStore(db_path, backend)
        search_mode = "keyword"

        try:
            # Phase 3 Task 9: an explicit ``as_of`` skips the vector path —
            # the embedding store has no temporal column, so we cannot
            # safely return historical snapshots through it. Fall through
            # to the keyword path which threads ``as_of`` into the SQL.
            if as_of == "" and emb_store.available and emb_store.count() > 0:
                # Vector search
                search_mode = "semantic"
                # Host-owned local rerank model (LOCAL_RERANK_MODEL env via the
                # module Settings). The pre-de-host per-sub config lookup is
                # gone — per-sub key buckets no longer exist (BYOK cut).
                rerank_model = settings.local_rerank_model.strip()
                if rerank_model and limit <= 0:
                    return {
                        "status": "error",
                        "error": "Local reranking requires a positive limit",
                    }
                candidate_limit = (
                    min(max(limit * 4, limit), 100) if rerank_model else limit * 2
                )
                raw = semantic_search(query, store, emb_store, limit=candidate_limit)
                if kind:
                    raw = [r for r in raw if r.get("kind") == kind]
                if repo:
                    # The vector store has no repo_id column; cross-check
                    # each hit against the SQL row and drop misses. Batched
                    # via json_each so it stays O(1) queries regardless of
                    # how many hits the vector store returned.
                    repo_qns = [
                        r.get("qualified_name")
                        for r in raw
                        if r.get("qualified_name") is not None
                    ]
                    repo_map: dict[str, str] = {}
                    if repo_qns:
                        cursor = store._conn.execute(
                            "SELECT n.qualified_name, n.repo_id FROM nodes n "
                            "JOIN json_each(?) j ON n.qualified_name = j.value",
                            (json.dumps(repo_qns),),
                        )
                        repo_map = {
                            row["qualified_name"]: row["repo_id"] for row in cursor
                        }
                    filtered = []
                    for r in raw:
                        qn = r.get("qualified_name")
                        if qn is None:
                            continue
                        r_repo = repo_map.get(qn)
                        if r_repo is not None and (r_repo or "") == repo:
                            filtered.append(r)
                    raw = filtered
                # Default-path filter: vector hits should also exclude
                # rows that have been closed-out at a later commit. The
                # vector store does not know about ``valid_to_sha`` so
                # we cross-check via the SQL row — batched via json_each.
                surv_qns = [
                    r.get("qualified_name")
                    for r in raw
                    if r.get("qualified_name") is not None
                ]
                surviving_set: set[str] = set()
                if surv_qns:
                    cursor = store._conn.execute(
                        "SELECT n.qualified_name FROM nodes n "
                        "JOIN json_each(?) j ON n.qualified_name = j.value "
                        "WHERE n.valid_to_sha IS NULL",
                        (json.dumps(surv_qns),),
                    )
                    surviving_set = {row["qualified_name"] for row in cursor}
                surviving: list[dict] = []
                for r in raw:
                    qn = r.get("qualified_name")
                    if qn is None:
                        continue
                    if qn in surviving_set:
                        surviving.append(r)
                raw = surviving
                if rerank_model:
                    from .reranker import LocalRerankError, rerank_candidates

                    try:
                        raw = rerank_candidates(query, raw, model_name=rerank_model)
                    except LocalRerankError as error:
                        return {
                            "status": "error",
                            "error": (
                                f"Local reranking failed for {rerank_model!r}: {error}"
                            ),
                        }
                    search_mode = "semantic_reranked"
                raw = raw[:limit]
                return {
                    "status": "ok",
                    "query": query,
                    "search_mode": search_mode,
                    "summary": f"Found {len(raw)} node(s) matching '{query}' via semantic search"
                    + (f" (kind={kind})" if kind else ""),
                    "header": _build_response_header(
                        store, db_path, keyword_only=False
                    ),
                    "results": raw,
                }
        finally:
            emb_store.close()

        # Keyword fallback
        # Bolt optimization: push node kind filtering to SQLite to avoid unnecessary
        # Python-side materialization and prevent truncating valid results.
        results = store.search_nodes(
            query, kind=kind, limit=limit * 2, repo=repo, as_of=as_of
        )

        def score(node):
            name_lower = node.name.lower()
            q_lower = query.lower()
            if name_lower == q_lower:
                return 0
            if name_lower.startswith(q_lower):
                return 1
            return 2

        results.sort(key=score)
        results = results[:limit]

        response: dict[str, Any] = {
            "status": "ok",
            "query": query,
            "search_mode": search_mode,
            "summary": f"Found {len(results)} node(s) matching '{query}'"
            + (f" (kind={kind})" if kind else ""),
            "header": _build_response_header(store, db_path, keyword_only=True),
            "results": [node_to_dict(r) for r in results],
        }

        # #317: warn when running keyword fallback on a query that looks
        # semantic. Users who pass single identifiers (`foo`, `foo_bar`,
        # `Foo.bar`) are fine; users who pass phrases (`how does X work`,
        # `firebase auth setup`) get garbage from keyword-substring match.
        if not _looks_like_literal_identifier(query):
            response["warning"] = (
                "embeddings_count=0 - results are keyword-substring matches "
                "only, not semantic similarity. Query shape suggests semantic "
                "intent; rebuild with embeddings enabled "
                "(graph action=embed) or reword as a literal identifier."
            )
        return response
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 6: list_graph_stats
# ---------------------------------------------------------------------------


def list_graph_stats(repo_root: str | None = None) -> dict[str, Any]:
    """Get aggregate statistics about the knowledge graph.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Total nodes, edges, breakdown by kind, languages, and last update time.
    """
    store, root = _get_store(repo_root)
    try:
        stats = store.get_stats()

        summary_parts = [
            f"Graph statistics for {root.name}:",
            f"  Files: {stats.files_count}",
            f"  Total nodes: {stats.total_nodes}",
            f"  Total edges: {stats.total_edges}",
            f"  Languages: {', '.join(stats.languages) if stats.languages else 'none'}",
            f"  Last updated: {stats.last_updated or 'never'}",
            "",
            "Nodes by kind:",
        ]
        for kind, count in sorted(stats.nodes_by_kind.items()):
            summary_parts.append(f"  {kind}: {count}")
        summary_parts.append("")
        summary_parts.append("Edges by kind:")
        for kind, count in sorted(stats.edges_by_kind.items()):
            summary_parts.append(f"  {kind}: {count}")

        # Add embedding info if available
        backend = init_backend()
        emb_store = EmbeddingStore(get_db_path(root), backend)
        try:
            emb_count = emb_store.count()
            mode = resolve_backend()
            summary_parts.append("")
            summary_parts.append(
                f"Embeddings: {emb_count} nodes embedded (backend: {mode})"
            )
        finally:
            emb_store.close()

        return {
            "status": "ok",
            "summary": "\n".join(summary_parts),
            "total_nodes": stats.total_nodes,
            "total_edges": stats.total_edges,
            "nodes_by_kind": stats.nodes_by_kind,
            "edges_by_kind": stats.edges_by_kind,
            "languages": stats.languages,
            "files_count": stats.files_count,
            "last_updated": stats.last_updated,
            "embeddings_count": emb_count,
        }
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 7: embed_graph
# ---------------------------------------------------------------------------


def embed_graph(repo_root: str | None = None) -> dict[str, Any]:
    """Compute vector embeddings for all graph nodes to enable semantic search.

    Uses dual-mode embedding: local fastretrieval ONNX by default or cloud via litellm passthrough.
    Cohere embed-v4.0 stores exact 1024-dimensional vectors; other backends use 768.

    Only embeds nodes that don't already have up-to-date embeddings.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Number of nodes embedded and total embedding count.
    """
    store, root = _get_store(repo_root)
    db_path = get_db_path(root)
    backend = init_backend()
    emb_store = EmbeddingStore(db_path, backend)
    try:
        mode = resolve_backend()
        newly_embedded = embed_all_nodes(store, emb_store)
        total = emb_store.count()

        return {
            "status": "ok",
            "summary": (
                f"Embedded {newly_embedded} new node(s) using {mode} backend. "
                f"Total embeddings: {total}. "
                "Semantic search is now active."
            ),
            "newly_embedded": newly_embedded,
            "total_embeddings": total,
            "backend": mode,
        }
    finally:
        emb_store.close()
        store.close()


# ---------------------------------------------------------------------------
# Tool 8: get_docs_section
# ---------------------------------------------------------------------------


def export_graph_dispatch(
    repo_root: str | None = None,
    format: str = "graphml",
    output_path: str | None = None,
) -> dict[str, Any]:
    """Export the code knowledge graph in an interoperable format.

    Phase 1 v1.6.x feature. Supported formats: graphml, json-ld, dot, cypher,
    crg. GraphML imports into Gephi/Cytoscape/networkx; Cypher replays into
    Neo4j; JSON-LD drives JSON-aware tooling; DOT renders via Graphviz; crg
    (Task 6) is the only format that round-trips back into a GraphStore via
    `graph(action='import')`.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.
        format: One of graphml | json-ld | dot | cypher | crg (case-insensitive).
        output_path: When provided, payload is written to this path and only
            metadata is returned. When None, payload is returned inline.

    Returns:
        Dict with status + format + bytes; payload field included only when
        output_path is None.
    """
    from .exporter import export_graph

    store, root = _get_store(repo_root)
    try:
        payload = export_graph(store, format=format, root=root)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    fmt = format.lower()
    byte_count = len(payload.encode("utf-8"))

    if output_path:
        out_p = Path(output_path).resolve()
        if not out_p.is_relative_to(root.resolve()):
            return {
                "status": "error",
                "error": f"Output path {output_path} must be relative to repo root {root}",
            }
        out_p.write_text(payload, encoding="utf-8")
        return {
            "status": "ok",
            "format": fmt,
            "output_path": output_path,
            "bytes": byte_count,
            "summary": f"Exported graph to {output_path} ({byte_count:,} bytes, {fmt}).",
        }

    return {
        "status": "ok",
        "format": fmt,
        "bytes": byte_count,
        "payload": payload,
    }


def import_graph_dispatch(
    repo_root: str | None = None,
    import_path: str | None = None,
) -> dict[str, Any]:
    """Import a `crg`-format export produced by `graph(action='export', format='crg')`.

    Task 6 feature: merges a graph built and exported elsewhere (e.g. a CI
    runner) into the current repo's graph store. Every imported node/edge id
    is namespaced with the exporting repo_id so it never collides with
    locally-parsed nodes; re-importing the same file is idempotent.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.
        import_path: Path to a JSON file previously written via
            `graph(action='export', format='crg', output_path=...)`. Must
            resolve inside repo_root. Required.

    Returns:
        Dict with status='ok' + nodes_added/nodes_updated/edges_added +
        repo_id + summary on success, or status='error' + error message.
    """
    from .federation import RepoRegistry
    from .importer import import_graph

    if not import_path:
        return {
            "status": "error",
            "error": "import_path is required for action='import'.",
        }

    store, root = _get_store(repo_root)
    try:
        in_p = Path(import_path).resolve()
        if not in_p.is_relative_to(root.resolve()):
            return {
                "status": "error",
                "error": f"Import path {import_path} must be relative to repo root {root}",
            }
        try:
            payload = json.loads(in_p.read_text(encoding="utf-8"))
        except OSError as e:
            return {"status": "error", "error": f"Failed to read import payload: {e}"}
        except json.JSONDecodeError as e:
            return {"status": "error", "error": f"Malformed import payload: {e}"}

        registry = RepoRegistry(store)
        try:
            result = import_graph(store, registry, payload)
        except (ValueError, KeyError) as e:
            return {"status": "error", "error": str(e)}

        # repo_id came from an on-disk JSON file that may originate anywhere
        # (a downloaded CI artifact, a colleague's export); sanitize before
        # it flows into a free-text summary, mirroring node_to_dict's
        # control-character stripping for names surfaced in tool responses.
        safe_repo_id = _sanitize_name(result["repo_id"])
        return {
            "status": "ok",
            **result,
            "summary": (
                f"Imported {result['nodes_added']} new node(s) "
                f"({result['nodes_updated']} updated) and "
                f"{result['edges_added']} new edge(s) from repo '{safe_repo_id}'."
            ),
        }
    finally:
        store.close()


def summarize_graph_dispatch(
    repo_root: str | None = None,
    max_nodes: int = 500,
) -> dict[str, Any]:
    """Generate LLM summaries for Function nodes (Phase 1 v1.6.x).

    Uses the first request-scoped SUMMARY_MODELS entry; no implicit provider fallback.
    No-op when no model configured. Call cap via max_nodes (default 500).

    Args:
        repo_root: Repository root path. Auto-detected if omitted.
        max_nodes: Max LLM calls per invocation. Default 500.

    Returns:
        Dict with status, generated, cached, errors, provider, summary.
    """
    from . import summarizer

    store, _ = _get_store(repo_root)
    try:
        try:
            result = summarizer.batch_summarize(store, max_nodes=max_nodes)
        except ValueError as e:
            return {"status": "error", "error": str(e)}
    finally:
        store.close()

    if result.skipped_no_provider:
        return {
            "status": "skipped",
            "reason": "no_provider_configured",
            "summary": (
                "Skipped: no summary model configured. Set SUMMARY_MODELS and its "
                "provider credential to enable LLM summaries."
            ),
        }

    return {
        "status": "ok",
        "provider": result.provider,
        "generated": result.generated,
        "cached": result.cached,
        "errors": result.errors,
        "summary": (
            f"Summarized {result.generated} new + {result.cached} cached Function "
            f"node(s) via {result.provider}"
            + (f"; {result.errors} error(s)." if result.errors else ".")
        ),
    }


def get_docs_section(section_name: str, repo_root: str | None = None) -> dict[str, Any]:
    """Return a specific section from the LLM-optimized reference.

    Used by skills and Claude Code to load only the exact documentation
    section needed, keeping token usage minimal (90%+ savings).

    Args:
        section_name: Exact section name. One of: usage, review-delta,
                      review-pr, commands, legal, watch, embeddings,
                      languages, troubleshooting.
        repo_root: Repository root path. Auto-detected from current directory if omitted.

    Returns:
        The section content, or an error if not found.
    """
    import re as _re

    search_roots: list[Path] = []

    if repo_root:
        search_roots.append(Path(repo_root))

    try:
        _, root = _get_store(repo_root)
        if root not in search_roots:
            search_roots.append(root)
    except (RuntimeError, ValueError):
        pass

    for search_root in search_roots:
        candidate = search_root / "docs" / "LLM-OPTIMIZED-REFERENCE.md"
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8")
            match = _re.search(
                rf'<section name="{_re.escape(section_name)}">'
                r"(.*?)</section>",
                content,
                _re.DOTALL | _re.IGNORECASE,
            )
            if match:
                return {
                    "status": "ok",
                    "section": section_name,
                    "content": match.group(1).strip(),
                }

    available = [
        "usage",
        "review-delta",
        "review-pr",
        "commands",
        "legal",
        "watch",
        "embeddings",
        "languages",
        "troubleshooting",
    ]
    return {
        "status": "not_found",
        "error": (
            f"Section '{section_name}' not found. Available: {', '.join(available)}"
        ),
    }


# ---------------------------------------------------------------------------
# Tool 9: find_large_functions
# ---------------------------------------------------------------------------


def find_large_functions(
    min_lines: int = 50,
    kind: str | None = None,
    file_path_pattern: str | None = None,
    limit: int = 50,
    repo_root: str | None = None,
    repo: str = "",
) -> dict[str, Any]:
    """Find functions, classes, or files exceeding a line-count threshold.

    Useful for identifying decomposition targets, code-quality audits,
    and enforcing size limits during code review.

    Args:
        min_lines: Minimum line count to flag (default: 50).
        kind: Filter by node kind: Function, Class, File, or Test.
        file_path_pattern: Filter by file path substring (e.g. "components/").
        limit: Maximum results (default: 50).
        repo_root: Repository root path. Auto-detected if omitted.
        repo: Phase 2 Task 10 — when non-empty, scope to nodes whose
            ``repo_id`` matches. Default ``""`` returns large nodes
            across every federated repo.

    Returns:
        Oversized nodes with line counts, ordered largest first.
    """
    store, root = _get_store(repo_root)
    try:
        nodes = store.get_nodes_by_size(
            min_lines=min_lines,
            kind=kind,
            file_path_pattern=file_path_pattern,
            limit=limit,
            repo=repo,
        )

        results = []
        for n in nodes:
            d = node_to_dict(n)
            d["line_count"] = (
                (n.line_end - n.line_start + 1) if n.line_start and n.line_end else 0
            )
            # Make file_path relative for readability
            try:
                d["relative_path"] = str(Path(n.file_path).relative_to(root))
            except ValueError:
                d["relative_path"] = n.file_path
            results.append(d)

        summary_parts = [
            f"Found {len(results)} node(s) with >= {min_lines} lines"
            + (f" (kind={kind})" if kind else "")
            + (f" matching '{file_path_pattern}'" if file_path_pattern else "")
            + ":",
        ]
        for r in results[:10]:
            summary_parts.append(
                f"  {r['line_count']:>4} lines | {r['kind']:>8} | "
                f"{r['name']} ({r['relative_path']}:{r['line_start']})"
            )
        if len(results) > 10:
            summary_parts.append(f"  ... and {len(results) - 10} more")

        return {
            "status": "ok",
            "summary": "\n".join(summary_parts),
            "total_found": len(results),
            "min_lines": min_lines,
            "results": results,
        }
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Tool 10: security (Phase 3 Task 5) -- scan / report / suppress / rule_list
# ---------------------------------------------------------------------------

_SUPPRESS_PATH_DEFAULT = ".better-code-review-graph/security-suppressions.json"
_LAST_SCAN_CACHE_FILENAME = "security-last-scan.json"


class _NodeView:
    """Duck-typed adapter exposing the four attributes ``HeuristicScanner``
    expects (``source_text``, ``language``, ``line_start``, ``qualified_name``).

    Used to feed plain ``GraphStore`` rows into the scanner without forcing
    a full ``NodeInfo`` re-construction.
    """

    __slots__ = ("qualified_name", "language", "line_start", "source_text")

    def __init__(
        self,
        qualified_name: str,
        language: str,
        line_start: int | None,
        source_text: str | None,
    ) -> None:
        self.qualified_name = qualified_name
        self.language = language or ""
        self.line_start = line_start
        self.source_text = source_text


def security_scan(
    repo_root: str | None = None,
    *,
    engine: str = "heuristic",
) -> dict[str, Any]:
    """Run a security scan over Function/Class/Method nodes in the graph.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.
        engine: ``"heuristic"`` (default, regex tier-1) or ``"semgrep"``
            (tier-2; requires the ``[security]`` extra).

    Returns:
        ``{"engine": str, "total": int, "by_severity": dict, "by_rule": dict,
        "tags_by_node": dict[node_id -> list[tag dict]],
        "suppressed_count": int}``.

        When ``engine="semgrep"`` is requested but the CLI is unavailable,
        returns ``{"error": <reason>, "engine": "semgrep"}``.
    """
    store, root = _get_store(repo_root)
    try:
        suppressions = _load_suppressions(root)
        tags_by_node: dict[str, list[Tag]] = {}

        if engine == "semgrep":
            try:
                scanner = SemgrepScanner()
            except SemgrepNotAvailable as exc:
                return {"error": str(exc), "engine": "semgrep"}
            result = scanner.scan_path(root)
            for tag in result.tags:
                if tag.rule_id in suppressions:
                    continue
                tags_by_node.setdefault("(repo-wide)", []).append(tag)
        else:
            scanner = HeuristicScanner()
            # Iterate the cursor directly instead of materializing every
            # node's source_text in memory — large monorepos blow up RSS
            # otherwise.
            cursor = store._conn.execute(
                "SELECT qualified_name, language, line_start, source_text "
                "FROM nodes WHERE source_text IS NOT NULL "
                "AND kind IN ('Function','Class','Method')"
            )
            for row in cursor:
                view = _NodeView(
                    qualified_name=row["qualified_name"],
                    language=row["language"] or "",
                    line_start=row["line_start"],
                    source_text=row["source_text"],
                )
                tags = [
                    t for t in scanner.scan_node(view) if t.rule_id not in suppressions
                ]
                if tags:
                    tags_by_node[row["qualified_name"]] = tags

        total = 0
        by_severity: dict[str, int] = {}
        by_rule: dict[str, int] = {}
        for tags in tags_by_node.values():
            total += len(tags)
            for tag in tags:
                by_severity[tag.severity] = by_severity.get(tag.severity, 0) + 1
                by_rule[tag.rule_id] = by_rule.get(tag.rule_id, 0) + 1

        serialized = {
            nid: [
                {
                    "rule_id": t.rule_id,
                    "severity": t.severity,
                    "message": t.message,
                    "line": t.line,
                }
                for t in tags
            ]
            for nid, tags in tags_by_node.items()
        }
        payload = {
            "engine": engine,
            "total": total,
            "by_severity": by_severity,
            "by_rule": by_rule,
            "tags_by_node": serialized,
            "suppressed_count": len(suppressions),
        }
        _cache_last_scan(root, payload)
        _persist_security_tags(store, tags_by_node)
        return payload
    finally:
        store.close()


def security_report(
    repo_root: str | None = None,
    *,
    format: str = "json",
) -> dict[str, Any]:
    """Re-emit the cached last scan as JSON or SARIF v2.1.0.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.
        format: ``"json"`` (default, returns the cached payload directly) or
            ``"sarif"`` (wraps the payload in a SARIF v2.1.0 envelope).

    Returns:
        The cached payload, a SARIF envelope, or
        ``{"error": "No prior scan found..."}`` when no scan has run yet.
    """
    _, root = _get_store(repo_root)
    cached = _load_last_scan(root)
    if cached is None:
        return {"error": "No prior scan found. Run security_scan first."}
    if format == "sarif":
        return _to_sarif(cached)
    return cached


def security_suppress(
    repo_root: str | None = None,
    *,
    rule_id: str | None = None,
    remove: bool = False,
) -> dict[str, Any]:
    """Add or remove ``rule_id`` from the persistent suppression list.

    Args:
        repo_root: Repository root path. Auto-detected if omitted.
        rule_id: The rule identifier (e.g. ``"cwe-89-sql-string-format"``).
        remove: When ``True``, removes the rule instead of adding it.

    Returns:
        ``{"rule_id": str, "suppressed": bool, "total_suppressed": int}`` or
        ``{"error": "rule_id is required"}`` when ``rule_id`` is missing.
    """
    if not rule_id:
        return {"error": "rule_id is required"}
    _, root = _get_store(repo_root)
    suppressions = set(_load_suppressions(root))
    if remove:
        suppressions.discard(rule_id)
    else:
        suppressions.add(rule_id)
    _save_suppressions(root, sorted(suppressions))
    return {
        "rule_id": rule_id,
        "suppressed": not remove,
        "total_suppressed": len(suppressions),
    }


def security_rule_list(
    *,
    engine: str = "heuristic",
) -> dict[str, Any]:
    """Enumerate active rules for the given engine.

    Args:
        engine: ``"heuristic"`` (default) or ``"semgrep"``.

    Returns:
        ``{"engine": str, "rules": [...]}`` -- entries are dicts with
        ``id``/``severity``/``languages``/``message`` for the heuristic engine,
        or filenames (``"name.yaml"``) for the semgrep overlay.
    """
    if engine == "semgrep":
        rules_dir = _resolve_overlay_rules_dir()
        if rules_dir is None:
            return {
                "engine": "semgrep",
                "rules": [],
                "note": "no curated overlay found",
            }
        rule_files = sorted(p.name for p in rules_dir.glob("*.yaml"))
        return {"engine": "semgrep", "rules": rule_files}
    scanner = HeuristicScanner()
    rules = [
        {
            "id": r.id,
            "severity": r.severity,
            "languages": sorted(r.languages),
            "message": r.message,
        }
        for r in scanner._rules
    ]
    return {"engine": "heuristic", "rules": rules}


# ---------------------------------------------------------------------------
# Persistence + serialization helpers
# ---------------------------------------------------------------------------


def _load_suppressions(root: Path) -> set[str]:
    """Load the JSON-array suppression list. Returns ``set()`` if absent or
    unreadable -- callers treat suppressions as best-effort."""
    sup_path = root / _SUPPRESS_PATH_DEFAULT
    if not sup_path.is_file():
        return set()
    try:
        data = json.loads(sup_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {str(item) for item in data}


def _save_suppressions(root: Path, suppressions: list[str]) -> None:
    """Persist the suppression list as a sorted JSON array."""
    sup_path = root / _SUPPRESS_PATH_DEFAULT
    sup_path.parent.mkdir(parents=True, exist_ok=True)
    sup_path.write_text(json.dumps(suppressions, indent=2), encoding="utf-8")


def _cache_last_scan(root: Path, payload: dict[str, Any]) -> None:
    """Cache the most recent scan payload so ``security_report`` can re-emit it."""
    cache_path = root / ".better-code-review-graph" / _LAST_SCAN_CACHE_FILENAME
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_last_scan(root: Path) -> dict[str, Any] | None:
    """Return the cached scan payload, or ``None`` if absent/corrupt."""
    cache_path = root / ".better-code-review-graph" / _LAST_SCAN_CACHE_FILENAME
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _to_sarif(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a cached scan payload to a SARIF v2.1.0 envelope."""
    results: list[dict[str, Any]] = []
    for node_id, tags in payload.get("tags_by_node", {}).items():
        for tag in tags:
            line = tag.get("line") or 1
            results.append(
                {
                    "ruleId": tag["rule_id"],
                    "level": _sarif_level(tag["severity"]),
                    "message": {"text": tag["message"]},
                    "locations": [
                        {
                            "logicalLocations": [{"name": node_id}],
                            "physicalLocation": {"region": {"startLine": line}},
                        }
                    ],
                }
            )
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "better-code-review-graph",
                        "informationUri": (
                            "https://github.com/n24q02m/better-code-review-graph"
                        ),
                    }
                },
                "results": results,
            }
        ],
    }


def _sarif_level(severity: str) -> str:
    """Map CRG severity to SARIF level."""
    return {
        "CRITICAL": "error",
        "HIGH": "error",
        "MEDIUM": "warning",
        "LOW": "note",
    }.get(severity, "warning")


def _persist_security_tags(
    store: GraphStore, tags_by_node: dict[str, list[Tag]]
) -> None:
    """Write JSON-serialized tag summaries into ``nodes.security_tags``.

    Skips the ``(repo-wide)`` semgrep bucket since it has no node anchor.
    Each entry is a compact ``"<rule_id>:<severity>"`` string -- callers
    that need the full tag detail re-run ``security_report``.
    """
    updates: list[tuple[str, str]] = []
    for node_id, tags in tags_by_node.items():
        if node_id == "(repo-wide)":
            continue
        serialized = json.dumps([f"{t.rule_id}:{t.severity}" for t in tags])
        updates.append((serialized, node_id))
    if updates:
        store._conn.executemany(
            "UPDATE nodes SET security_tags = ? WHERE qualified_name = ?",
            updates,
        )
        store._conn.commit()
