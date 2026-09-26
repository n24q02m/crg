"""Console-script entry: local argparse dispatch (de-hosted, no shared core).

Bare invocation and any leading-dash argv (e.g. --http) start the server;
a leading positional argv[0] routes to a subcommand (``graph``, ``query``,
``review``, ``security``) instead of the server.
"""

from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import Any


def _version() -> str:
    """Resolve the installed package version, falling back to 'dev'."""
    try:
        return pkg_version("better-code-review-graph")
    except PackageNotFoundError:
        return "dev"


def _serve(argv: list[str]) -> int | None:
    from .server import serve_main

    serve_main()
    return 0


def _print_result(result: dict[str, Any]) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "error" in result else 0


# ---------------------------------------------------------------------------
# 1. graph subcommand
# ---------------------------------------------------------------------------


def _configure_graph(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "graph_action",
        choices=["build", "embed", "stats", "export", "import", "summarize"],
        help="Graph action to run",
    )
    p.add_argument(
        "--full-rebuild",
        action="store_true",
        default=False,
        help="Re-parse every file (build only)",
    )
    p.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path (auto-detected if omitted)",
    )
    p.add_argument(
        "--base",
        default="HEAD~1",
        help="Git ref for incremental diff (build only)",
    )
    p.add_argument(
        "--roots",
        nargs="*",
        default=None,
        help="Additional repository root paths for federated build",
    )
    p.add_argument(
        "--format",
        choices=["graphml", "json-ld", "dot", "cypher", "crg"],
        default="graphml",
        help="Export format (export only)",
    )
    p.add_argument(
        "--output-path",
        default=None,
        help="Output file path for export",
    )
    p.add_argument(
        "--input-path",
        default="",
        help="Input file path for import",
    )
    p.add_argument(
        "--max-nodes",
        type=int,
        default=500,
        help="Maximum functions to summarize (summarize only)",
    )


def _handle_graph(args: argparse.Namespace) -> int:
    from .tools import (
        build_or_update_graph,
        embed_graph,
        export_graph_dispatch,
        import_graph_dispatch,
        list_graph_stats,
        summarize_graph_dispatch,
    )

    action = args.graph_action
    if action == "build":
        kwargs: dict[str, Any] = {
            "full_rebuild": args.full_rebuild,
            "repo_root": args.repo_root,
            "base": args.base,
        }
        if args.roots is not None:
            kwargs["roots"] = args.roots
        result = build_or_update_graph(**kwargs)
    elif action == "embed":
        result = embed_graph(repo_root=args.repo_root)
    elif action == "stats":
        result = list_graph_stats(repo_root=args.repo_root)
    elif action == "export":
        result = export_graph_dispatch(
            format=args.format,
            output_path=args.output_path,
            repo_root=args.repo_root,
        )
    elif action == "import":
        result = import_graph_dispatch(
            import_path=args.input_path,
            repo_root=args.repo_root,
        )
    elif action == "summarize":
        result = summarize_graph_dispatch(
            repo_root=args.repo_root,
            max_nodes=args.max_nodes,
        )
    else:  # pragma: no cover
        result = {"error": f"Unknown graph action: {action}"}

    return _print_result(result)


# ---------------------------------------------------------------------------
# 2. query subcommand
# ---------------------------------------------------------------------------


def _configure_query(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "query_action",
        choices=[
            "query",
            "search",
            "impact",
            "large_functions",
            "spot_check",
            "renamed_in_diff",
            "diff",
        ],
        help="Query action to run",
    )
    p.add_argument(
        "--pattern",
        default="callers_of",
        choices=[
            "callers_of",
            "callees_of",
            "imports_of",
            "importers_of",
            "children_of",
            "tests_for",
            "inheritors_of",
            "file_summary",
        ],
        help="Query pattern (for query action)",
    )
    p.add_argument(
        "--target",
        default="",
        help="Target symbol or file path for query action",
    )
    p.add_argument(
        "--search-query",
        default="",
        help="Search text or symbol name for search action",
    )
    p.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Changed file paths for impact analysis",
    )
    p.add_argument(
        "--max-results",
        type=int,
        default=500,
        help="Maximum impact results",
    )
    p.add_argument(
        "--max-payload-bytes",
        type=int,
        default=500_000,
        help="Soft impact response-size cap",
    )
    p.add_argument(
        "--base",
        default="HEAD~1",
        help="Git base ref for impact/renamed_in_diff",
    )
    p.add_argument(
        "--from-sha",
        default="",
        help="Base commit SHA for graph diff",
    )
    p.add_argument(
        "--to-sha",
        default="",
        help="Target commit SHA for graph diff",
    )
    p.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path",
    )
    p.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Maximum traversal depth",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Result count ceiling",
    )
    p.add_argument(
        "--kind",
        default=None,
        help="Filter by node kind (function, class, file, etc.)",
    )
    p.add_argument(
        "--min-lines",
        type=int,
        default=50,
        help="Line count threshold for large_functions",
    )
    p.add_argument(
        "--file-path-pattern",
        default=None,
        help="Filter large functions by file path substring",
    )
    p.add_argument(
        "--n",
        type=int,
        default=5,
        help="Number of random callsites for spot_check",
    )
    p.add_argument(
        "--context-lines",
        type=int,
        default=2,
        help="Source lines around spot-check callsites",
    )
    p.add_argument(
        "--repo",
        default="",
        help="Scope query to a specific federated repo_id",
    )
    p.add_argument(
        "--languages",
        nargs="*",
        default=None,
        help="Filter by programming language(s)",
    )
    p.add_argument(
        "--as-of",
        default="",
        help="Temporal commit SHA",
    )


def _handle_query(args: argparse.Namespace) -> int:
    from .tools import (
        diff_graph,
        find_large_functions,
        get_impact_radius,
        query_graph,
        renamed_in_diff,
        semantic_search_nodes,
        spot_check_last_callers,
    )

    action = args.query_action
    if action == "query":
        result = query_graph(
            pattern=args.pattern,
            target=args.target,
            repo_root=args.repo_root,
            repo=args.repo,
            languages=args.languages,
            as_of=args.as_of,
        )
    elif action == "search":
        limit = args.limit if args.limit is not None else 20
        result = semantic_search_nodes(
            query=args.search_query,
            repo_root=args.repo_root,
            limit=limit,
            kind=args.kind,
            repo=args.repo,
            as_of=args.as_of,
        )
    elif action == "impact":
        result = get_impact_radius(
            changed_files=args.changed_files,
            base=args.base,
            repo_root=args.repo_root,
            max_depth=args.max_depth,
            max_results=args.max_results,
            max_payload_bytes=args.max_payload_bytes,
            repo=args.repo,
            as_of=args.as_of,
        )
    elif action == "large_functions":
        limit = args.limit if args.limit is not None else 50
        kind = args.kind if args.kind is not None else "function"
        result = find_large_functions(
            min_lines=args.min_lines,
            kind=kind,
            file_path_pattern=args.file_path_pattern,
            repo_root=args.repo_root,
            limit=limit,
            repo=args.repo,
        )
    elif action == "spot_check":
        result = spot_check_last_callers(
            n=args.n,
            repo_root=args.repo_root,
            context_lines=args.context_lines,
        )
    elif action == "renamed_in_diff":
        base = args.base if args.base is not None else "HEAD~1"
        result = renamed_in_diff(
            base=base,
            repo_root=args.repo_root,
        )
    elif action == "diff":
        result = diff_graph(
            from_sha=args.from_sha,
            to_sha=args.to_sha,
            repo_root=args.repo_root,
            repo=args.repo,
        )
    else:  # pragma: no cover
        result = {"error": f"Unknown query action: {action}"}

    return _print_result(result)


# ---------------------------------------------------------------------------
# 3. review subcommand
# ---------------------------------------------------------------------------


def _configure_review(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "review_action",
        choices=["context", "delta"],
        help="Review action to run",
    )
    p.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Changed file paths for review context",
    )
    p.add_argument(
        "--base",
        default="HEAD~1",
        help="Git base ref for review context",
    )
    p.add_argument(
        "--from-sha",
        default="",
        help="Base commit SHA for review delta",
    )
    p.add_argument(
        "--to-sha",
        default="",
        help="Target commit SHA for review delta",
    )
    p.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path",
    )
    p.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Maximum traversal depth",
    )
    p.add_argument(
        "--repo",
        default="",
        help="Scope to a specific federated repo_id",
    )
    p.add_argument(
        "--languages",
        nargs="*",
        default=None,
        help="Filter by programming language(s)",
    )


def _handle_review(args: argparse.Namespace) -> int:
    from .tools import get_review_context, review_delta

    action = args.review_action
    if action == "context":
        result = get_review_context(
            changed_files=args.changed_files,
            base=args.base,
            repo_root=args.repo_root,
            max_depth=args.max_depth,
            repo=args.repo,
            languages=args.languages,
        )
    elif action == "delta":
        result = review_delta(
            from_sha=args.from_sha,
            to_sha=args.to_sha,
            repo_root=args.repo_root,
            repo=args.repo,
        )
    else:  # pragma: no cover
        result = {"error": f"Unknown review action: {action}"}

    return _print_result(result)


# ---------------------------------------------------------------------------
# 4. security subcommand
# ---------------------------------------------------------------------------


def _configure_security(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "security_action",
        choices=["scan", "report", "suppress", "rule_list"],
        help="Security action to run",
    )
    p.add_argument(
        "--engine",
        choices=["heuristic", "semgrep"],
        default="heuristic",
        help="Security scanning engine",
    )
    p.add_argument(
        "--format",
        choices=["json", "sarif"],
        default="json",
        help="Security report format",
    )
    p.add_argument(
        "--rule-id",
        default="",
        help="Rule ID to suppress or un-suppress",
    )
    p.add_argument(
        "--remove",
        action="store_true",
        default=False,
        help="Remove rule from suppression list instead of adding",
    )
    p.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path",
    )


def _handle_security(args: argparse.Namespace) -> int:
    from .tools import (
        security_report,
        security_rule_list,
        security_scan,
        security_suppress,
    )

    action = args.security_action
    if action == "scan":
        result = security_scan(
            engine=args.engine,
            repo_root=args.repo_root,
        )
    elif action == "report":
        result = security_report(
            format=args.format,
            repo_root=args.repo_root,
        )
    elif action == "suppress":
        result = security_suppress(
            rule_id=args.rule_id,
            remove=args.remove,
            repo_root=args.repo_root,
        )
    elif action == "rule_list":
        result = security_rule_list(
            engine=args.engine,
        )
    else:  # pragma: no cover
        result = {"error": f"Unknown security action: {action}"}

    return _print_result(result)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    """Route argv: server start vs. local subcommands.

    Same dispatch contract the shared core builder used to provide, now
    local: bare or leading-dash argv goes to the server (``_serve``), a
    known leading subcommand is parsed by its own argparse subparser and
    handed to its handler, anything else is a clean rc-2 usage error.
    """
    import sys

    handlers: dict[str, tuple[Any, Any]] = {
        "graph": (_configure_graph, _handle_graph),
        "query": (_configure_query, _handle_query),
        "review": (_configure_review, _handle_review),
        "security": (_configure_security, _handle_security),
    }

    argv = sys.argv[1:]
    if not argv:
        rc = _serve([])
        return 0 if rc is None else rc

    # Intercept bare flags before argparse: -h/--help/--version must print
    # and exit instead of starting (and blocking on) the stdio server, and
    # any other leading dash is passed through to the server untouched.
    if argv[0] in ("-h", "--help"):
        names = ", ".join(sorted(handlers))
        print("usage: better-code-review-graph [-h] [--version] [<subcommand> ...]")
        print("Any other flags/args are passed through to the MCP server (e.g. --http).")
        print(f"subcommands: {names}")
        return 0
    if argv[0] in ("--version", "-V"):
        print(f"better-code-review-graph {_version()}")
        return 0
    if argv[0].startswith("-"):
        rc = _serve(argv)
        return 0 if rc is None else rc

    spec = handlers.get(argv[0])
    if spec is None:
        names = ", ".join(sorted(handlers))
        print(
            f"better-code-review-graph: unknown subcommand {argv[0]!r} "
            f"(expected one of: {names})",
            file=sys.stderr,
        )
        return 2

    configure_fn, handler_fn = spec
    parser = argparse.ArgumentParser(prog="better-code-review-graph")
    subparsers = parser.add_subparsers(dest="subcommand")
    sub = subparsers.add_parser(argv[0])
    if configure_fn is not None:
        configure_fn(sub)
    ns = parser.parse_args(argv)
    return handler_fn(ns)


if __name__ == "__main__":
    main()
