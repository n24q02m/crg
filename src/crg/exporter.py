"""Graph export formatters — Phase 1 v1.6.x feature.

Emits the SQLite-backed knowledge graph in interoperable formats for use by
external tools (Gephi, Cytoscape, Neo4j, JSON-LD consumers).

Formats:
    - graphml: XML, supported by Gephi + Cytoscape + NetworkX read_graphml
    - json-ld: JSON, supported by JSON-LD consumers + arbitrary JSON tooling
    - dot: Graphviz DOT, supported by Graphviz + dot2tex + xdot
    - cypher: Neo4j Cypher CREATE statements, replay-able into a Neo4j database
    - crg: JSON, the only format that round-trips back into a GraphStore via
      ``crg.importer.import_graph`` (see Task 6)

Streaming uses iter helpers on the GraphStore. Output is a single string
return value; callers wanting file output write the string to disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import GraphStore

GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"

JSONLD_CONTEXT = {
    "@vocab": "https://crg.n24q02m.dev/schema#",
    "kind": "@type",
    "name": "name",
    "filePath": "filePath",
    "language": "language",
    "lineStart": "lineStart",
    "lineEnd": "lineEnd",
}


def _safe_label(value: object) -> str:
    """Quote-escape a value for a DOT identifier or label string."""
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _cypher_props(props: dict[str, object]) -> str:
    """Format a property dict into Cypher map syntax."""
    parts = []
    for k, v in props.items():
        if v is None:
            continue
        if isinstance(v, (int, float, bool)):
            parts.append(f"{k}: {v}")
        else:
            escaped = str(v).replace("\\", "\\\\").replace("'", "\\'")
            parts.append(f"{k}: '{escaped}'")
    return ", ".join(parts)


_CYPHER_VAR_PATTERN = re.compile(r"\W")
_CYPHER_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CYPHER_BACKTICK_ESCAPE = re.compile(r"\\(?:u0060|U00000060)", re.IGNORECASE)


def _cypher_identifier(value: str) -> str:
    """Quote dynamic labels/types, including Cypher's Unicode backtick escape."""
    if _CYPHER_IDENTIFIER_PATTERN.fullmatch(value):
        return value
    escaped = _CYPHER_BACKTICK_ESCAPE.sub("`", value).replace("`", "``")
    return f"`{escaped}`"


def _cypher_var(node_id: str) -> str:
    """Return a Cypher-safe variable name derived from node id.

    Uses a pre-compiled `\\W` regular expression (non-alphanumeric,
    non-underscore) rather than a generator expression with `"".join(...)`,
    which keeps the string traversal in C for large graph serializations.
    """
    safe = _CYPHER_VAR_PATTERN.sub("_", node_id)
    return f"n_{safe}"


def export_graphml(store: GraphStore) -> str:
    """Emit GraphML XML for the entire graph.

    Compatible with Gephi import, Cytoscape import, and ``networkx.read_graphml``.
    """

    # Fast XML escape helper without importing xml.sax.saxutils
    def _escape(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def _generate():
        yield "<?xml version='1.0' encoding='utf-8'?>\n"
        yield f'<graphml xmlns="{GRAPHML_NS}">'

        keys = [
            ("kind", "node", "string"),
            ("name", "node", "string"),
            ("qualified_name", "node", "string"),
            ("file_path", "node", "string"),
            ("language", "node", "string"),
            ("line_start", "node", "int"),
            ("line_end", "node", "int"),
            ("edge_kind", "edge", "string"),
            ("edge_file", "edge", "string"),
            ("edge_line", "edge", "int"),
        ]
        for key_id, scope, attr_type in keys:
            yield f'<key id="{key_id}" for="{scope}" attr.name="{key_id}" attr.type="{attr_type}" />'

        yield '<graph id="G" edgedefault="directed">'

        for node in store.iter_raw_nodes():
            yield f'<node id="{_escape(node["qualified_name"])}">'
            for k, v in (
                ("kind", node["kind"]),
                ("name", node["name"]),
                ("qualified_name", node["qualified_name"]),
                ("file_path", node["file_path"]),
                ("language", node["language"]),
            ):
                if v is None or v == "":
                    continue
                yield f'<data key="{k}">{_escape(str(v))}</data>'
            for k, v in (
                ("line_start", node["line_start"]),
                ("line_end", node["line_end"]),
            ):
                if v is None:
                    continue
                yield f'<data key="{k}">{v}</data>'
            yield "</node>"

        for edge in store.iter_raw_edges():
            yield f'<edge source="{_escape(edge["source_qualified"])}" target="{_escape(edge["target_qualified"])}">'
            for k, v in (("edge_kind", edge["kind"]), ("edge_file", edge["file_path"])):
                if v is None or v == "":
                    continue
                yield f'<data key="{k}">{_escape(str(v))}</data>'
            if edge["line"] is not None:
                yield f'<data key="edge_line">{edge["line"]}</data>'
            yield "</edge>"

        yield "</graph></graphml>"

    return "".join(_generate())


def export_jsonld(store: GraphStore) -> str:
    """Emit JSON-LD with @context + nodes + edges arrays."""

    # Bolt optimization: stream the output by iterating over the database cursor in a Python generator
    # and yielding incrementally-dumped string pieces instead of materializing full lists.
    def _generate():
        yield "{\n"
        yield (
            '  "@context": '
            + json.dumps(JSONLD_CONTEXT, indent=2).replace("\n", "\n  ")
            + ",\n"
        )
        yield '  "nodes": [\n'

        first = True
        for node in store.iter_raw_nodes():
            if not first:
                yield ",\n"
            first = False
            n: dict[str, object] = {
                "@id": node["qualified_name"],
                "@type": node["kind"],
                "name": node["name"],
                "filePath": node["file_path"],
                "language": node["language"] or "",
            }
            if node["line_start"] is not None:
                n["lineStart"] = node["line_start"]
            if node["line_end"] is not None:
                n["lineEnd"] = node["line_end"]
            yield "    " + json.dumps(n, indent=2).replace("\n", "\n    ")

        yield "\n  ],\n"
        yield '  "edges": [\n'

        first = True
        for edge in store.iter_raw_edges():
            if not first:
                yield ",\n"
            first = False
            e: dict[str, object] = {
                "source": edge["source_qualified"],
                "target": edge["target_qualified"],
                "kind": edge["kind"],
            }
            if edge["file_path"]:
                e["filePath"] = edge["file_path"]
            if edge["line"] is not None:
                e["line"] = edge["line"]
            yield "    " + json.dumps(e, indent=2).replace("\n", "\n    ")

        yield "\n  ]\n"
        yield "}"

    return "".join(_generate())


def export_dot(store: GraphStore) -> str:
    """Emit Graphviz DOT format (digraph)."""

    # Bolt optimization: stream the output by iterating over the database cursor in a Python generator
    def _generate():
        yield "digraph G {"
        for node in store.iter_raw_nodes():
            label = _safe_label(node["name"] or node["qualified_name"])
            yield f'  "{_safe_label(node["qualified_name"])}" [label="{label}"];'
        for edge in store.iter_raw_edges():
            kind = _safe_label(edge["kind"])
            yield (
                f'  "{_safe_label(edge["source_qualified"])}" -> '
                f'"{_safe_label(edge["target_qualified"])}" [label="{kind}"];'
            )
        yield "}"

    return "\n".join(_generate())


def export_cypher(store: GraphStore) -> str:
    """Emit Neo4j Cypher CREATE statements that recreate the graph."""

    # Bolt optimization: stream the output by iterating over the database cursor in a Python generator
    def _generate():
        for node in store.iter_raw_nodes():
            kind_label = _cypher_identifier(node["kind"] or "Node")
            var = _cypher_var(node["qualified_name"])
            props: dict[str, object] = {
                "id": node["qualified_name"],
                "name": node["name"],
                "file_path": node["file_path"],
                "language": node["language"] or "",
                "line_start": node["line_start"],
                "line_end": node["line_end"],
            }
            yield f"CREATE ({var}:{kind_label} {{{_cypher_props(props)}}});"
        for edge in store.iter_raw_edges():
            kind = _cypher_identifier(
                (edge["kind"] or "RELATED").upper().replace("-", "_")
            )
            source_props = _cypher_props({"id": edge["source_qualified"]})
            target_props = _cypher_props({"id": edge["target_qualified"]})
            yield (
                f"MATCH (a {{{source_props}}}), (b {{{target_props}}}) "
                f"CREATE (a)-[:{kind}]->(b);"
            )

    return "\n".join(_generate())


def export_crg(store: GraphStore, root: Path | None = None) -> str:
    """Emit the full graph as round-trippable JSON (Task 6).

    Unlike the other formats (one-way interop with external tools), ``crg``
    dumps every column of the ``nodes`` / ``edges`` tables verbatim --
    including ``source_text``, the summarizer columns, and the temporal
    ``valid_from_sha``/``valid_to_sha`` columns -- so
    :func:`crg.importer.import_graph` can reconstruct
    an equivalent subgraph in a different store (e.g. built on a CI runner,
    imported on a laptop; the crg format is not used by the CF-hosted
    deployment).

    ``repo_id`` identifies the exporting graph and becomes the namespace
    prefix an importer uses to keep re-imported ids from colliding with
    locally-parsed nodes. It is derived via
    :func:`crg.federation.derive_repo_id` from ``root``
    when the caller supplies it (``export_graph_dispatch`` always does,
    since it already resolves the repo root) -- this is the same id a
    federated ``graph(action='build', roots=[...])`` would register for
    that same root, so repo-scoped queries agree after either path. When
    ``root`` is omitted (e.g. calling this function directly against a
    store that isn't backed by a real repo checkout), falls back to the
    store's own db directory so the id stays deterministic per store; note
    that fallback is *not* guaranteed to match a federated id for a real
    root, since ``store.db_path`` normally lives at
    ``<root>/.crg/graph.db`` -- one directory below ``root``.
    """
    from .federation import derive_repo_id

    repo_id = derive_repo_id(root if root is not None else store.db_path.parent)

    # To prevent massive memory overhead when exporting large JSON structures,
    # stream the output by iterating over the database cursor in a Python generator
    # and yielding incrementally-dumped string pieces instead of materializing full lists.
    def _generate():
        yield "{\n"
        yield '  "schema_version": 1,\n'
        yield f'  "repo_id": {json.dumps(repo_id)},\n'
        yield '  "nodes": [\n'

        first = True
        for row in store.iter_raw_nodes():
            if not first:
                yield ",\n"
            first = False
            yield "    " + json.dumps(dict(row), indent=2).replace("\n", "\n    ")

        yield "\n  ],\n"
        yield '  "edges": [\n'

        first = True
        for row in store.iter_raw_edges():
            if not first:
                yield ",\n"
            first = False
            yield "    " + json.dumps(dict(row), indent=2).replace("\n", "\n    ")

        yield "\n  ]\n"
        yield "}"

    return "".join(_generate())


_FORMATTERS = {
    "graphml": export_graphml,
    "json-ld": export_jsonld,
    "jsonld": export_jsonld,
    "dot": export_dot,
    "cypher": export_cypher,
}


def export_graph(
    store: GraphStore, format: str = "graphml", root: Path | None = None
) -> str:
    """Dispatch to the per-format formatter. Raises ValueError on unknown format.

    ``root`` is only consumed by the ``crg`` format (see :func:`export_crg`);
    the other formatters ignore it.
    """
    fmt = format.lower()
    if fmt == "crg":
        return export_crg(store, root=root)
    if fmt not in _FORMATTERS:
        valid = sorted({"graphml", "json-ld", "dot", "cypher", "crg"})
        raise ValueError(f"Unknown export format '{format}'. Valid: {valid}")
    return _FORMATTERS[fmt](store)
