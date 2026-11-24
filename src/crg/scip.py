"""SCIP index importer (CRG-14).

Supports both SCIP JSON dumps and binary protobuf ``.scip`` files without
requiring external protobuf compilation. Symbols and occurrence roles are
converted into exact ``nodes`` and ``edges`` with ``confidence=1.0`` and
``resolution="scip"``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .parser import EdgeInfo, NodeInfo

if TYPE_CHECKING:
    from .graph import GraphStore

# SCIP SymbolRole bitflags (from scip.proto)
_ROLE_DEFINITION = 0x1
_ROLE_IMPORT = 0x2
_ROLE_READ = 0x8


@dataclass
class _ScipSymbolInfo:
    symbol: str
    documentation: list[str] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _ScipOccurrence:
    line: int
    col: int
    end_line: int
    end_col: int
    symbol: str
    roles: int = 0


@dataclass
class _ScipDocument:
    relative_path: str
    language: str = ""
    occurrences: list[_ScipOccurrence] = field(default_factory=list)
    symbols: list[_ScipSymbolInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Lightweight protobuf wire decoder for scip.proto Index/Document messages
# ---------------------------------------------------------------------------


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
    raise ValueError("Truncated varint in SCIP protobuf")


def _skip_field(buf: bytes, pos: int, wire_type: int) -> int:
    if wire_type == 0:
        _, pos = _read_varint(buf, pos)
        return pos
    if wire_type == 1:
        return pos + 8
    if wire_type == 2:
        length, pos = _read_varint(buf, pos)
        return pos + length
    if wire_type == 5:
        return pos + 4
    raise ValueError(f"Unsupported protobuf wire type: {wire_type}")


def _iter_fields(buf: bytes) -> list[tuple[int, int, Any]]:
    fields: list[tuple[int, int, Any]] = []
    pos = 0
    while pos < len(buf):
        tag, pos = _read_varint(buf, pos)
        field_num = tag >> 3
        wire_type = tag & 0x7
        if wire_type == 0:
            val, pos = _read_varint(buf, pos)
            fields.append((field_num, wire_type, val))
        elif wire_type == 2:
            length, pos = _read_varint(buf, pos)
            fields.append((field_num, wire_type, buf[pos : pos + length]))
            pos += length
        else:
            pos = _skip_field(buf, pos, wire_type)
    return fields


def _decode_packed_int32(data: bytes) -> list[int]:
    out: list[int] = []
    pos = 0
    while pos < len(data):
        val, pos = _read_varint(data, pos)
        if val >= (1 << 31):
            val -= 1 << 32
        out.append(val)
    return out


def _decode_occurrence(buf: bytes) -> _ScipOccurrence:
    coords: list[int] = []
    symbol = ""
    roles = 0
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1:
            if wtype == 2:
                coords.extend(_decode_packed_int32(val))
            elif wtype == 0:
                coords.append(int(val))
        elif fnum == 2 and wtype == 2:
            symbol = bytes(val).decode("utf-8", errors="replace")
        elif fnum == 3 and wtype == 0:
            roles = int(val)
    line = (coords[0] + 1) if len(coords) >= 1 else 1
    col = coords[1] if len(coords) >= 2 else 0
    if len(coords) >= 4:
        end_line = coords[2] + 1
        end_col = coords[3]
    elif len(coords) == 3:
        end_line = line
        end_col = coords[2]
    else:
        end_line = line
        end_col = col
    return _ScipOccurrence(
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
        symbol=symbol,
        roles=roles,
    )


def _decode_relationship(buf: bytes) -> dict[str, Any]:
    rel: dict[str, Any] = {
        "symbol": "",
        "is_reference": False,
        "is_implementation": False,
        "is_type_definition": False,
        "is_definition": False,
    }
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1 and wtype == 2:
            rel["symbol"] = bytes(val).decode("utf-8", errors="replace")
        elif fnum == 2 and wtype == 0:
            rel["is_reference"] = bool(val)
        elif fnum == 3 and wtype == 0:
            rel["is_implementation"] = bool(val)
        elif fnum == 4 and wtype == 0:
            rel["is_type_definition"] = bool(val)
        elif fnum == 5 and wtype == 0:
            rel["is_definition"] = bool(val)
    return rel


def _decode_symbol_info(buf: bytes) -> _ScipSymbolInfo:
    symbol = ""
    docs: list[str] = []
    rels: list[dict[str, Any]] = []
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1 and wtype == 2:
            symbol = bytes(val).decode("utf-8", errors="replace")
        elif fnum == 3 and wtype == 2:
            docs.append(bytes(val).decode("utf-8", errors="replace"))
        elif fnum == 4 and wtype == 2:
            rels.append(_decode_relationship(val))
    return _ScipSymbolInfo(symbol=symbol, documentation=docs, relationships=rels)


def _decode_document(buf: bytes) -> _ScipDocument:
    rel_path = ""
    language = ""
    occs: list[_ScipOccurrence] = []
    syms: list[_ScipSymbolInfo] = []
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1 and wtype == 2:
            rel_path = bytes(val).decode("utf-8", errors="replace")
        elif fnum == 2 and wtype == 2:
            occs.append(_decode_occurrence(val))
        elif fnum == 3 and wtype == 2:
            syms.append(_decode_symbol_info(val))
        elif fnum == 4 and wtype == 2:
            language = bytes(val).decode("utf-8", errors="replace")
    return _ScipDocument(
        relative_path=rel_path,
        language=language,
        occurrences=occs,
        symbols=syms,
    )


def _parse_scip_protobuf(raw: bytes) -> list[_ScipDocument]:
    docs: list[_ScipDocument] = []
    for fnum, wtype, val in _iter_fields(raw):
        if fnum == 2 and wtype == 2:
            docs.append(_decode_document(val))
    return docs


def _parse_scip_json(payload: dict[str, Any]) -> list[_ScipDocument]:
    docs: list[_ScipDocument] = []
    for raw_doc in payload.get("documents", []):
        if not isinstance(raw_doc, dict):
            continue
        occs: list[_ScipOccurrence] = []
        for o in raw_doc.get("occurrences", []):
            if not isinstance(o, dict):
                continue
            r = o.get("range") or [1, 0]
            line = int(r[0]) + 1 if len(r) >= 1 else int(o.get("line", 1))
            col = int(r[1]) if len(r) >= 2 else 0
            end_line = int(r[2]) + 1 if len(r) >= 4 else line
            end_col = int(r[3]) if len(r) >= 4 else (int(r[2]) if len(r) == 3 else col)
            occs.append(
                _ScipOccurrence(
                    line=line,
                    col=col,
                    end_line=end_line,
                    end_col=end_col,
                    symbol=str(o.get("symbol", "")),
                    roles=int(o.get("symbol_roles", o.get("roles", 0))),
                )
            )
        syms: list[_ScipSymbolInfo] = []
        for s in raw_doc.get("symbols", []):
            if not isinstance(s, dict):
                continue
            syms.append(
                _ScipSymbolInfo(
                    symbol=str(s.get("symbol", "")),
                    documentation=[str(d) for d in s.get("documentation", [])],
                    relationships=[
                        r for r in s.get("relationships", []) if isinstance(r, dict)
                    ],
                )
            )
        docs.append(
            _ScipDocument(
                relative_path=str(raw_doc.get("relative_path", "")),
                language=str(raw_doc.get("language", "")),
                occurrences=occs,
                symbols=syms,
            )
        )
    return docs


def _scip_symbol_parts(symbol: str) -> tuple[str, str]:
    """Return ``(node_kind, clean_name)`` parsed from a SCIP symbol string."""
    trimmed = symbol.strip()
    if trimmed.endswith("()."):
        kind = "Function"
        core = trimmed[:-3].rstrip("/.#")
    elif trimmed.endswith("#"):
        kind = "Class"
        core = trimmed[:-1]
    elif trimmed.endswith("."):
        kind = "Type"
        core = trimmed[:-1]
    else:
        kind = "Function"
        core = trimmed
    parts = [p for p in re.split(r"[/#.\s]+", core) if p]
    if not parts:
        return kind, trimmed
    if len(parts) >= 2 and "#" in core:
        return kind, f"{parts[-2]}.{parts[-1]}"
    return kind, parts[-1]


def import_scip_index(
    store: GraphStore,
    scip_path: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Import a JSON or binary protobuf SCIP index into *store*."""
    if not scip_path.is_file():
        raise FileNotFoundError(f"SCIP index not found: {scip_path}")

    raw = scip_path.read_bytes()
    stripped = raw.lstrip()
    if scip_path.suffix.lower() == ".json" or stripped.startswith(b"{"):
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid SCIP JSON payload: root must be an object")
        docs = _parse_scip_json(payload)
    else:
        docs = _parse_scip_protobuf(raw)

    base_root = repo_root.resolve() if repo_root else scip_path.parent.resolve()
    symbol_to_qn: dict[str, str] = {}
    symbol_docs_map: dict[str, list[str]] = {}
    doc_rel_to_file: dict[str, str] = {}
    nodes_upserted = 0
    edges_upserted = 0

    # Pass 1: register File & definition nodes
    for doc in docs:
        if not doc.relative_path:
            continue
        abs_fp = str((base_root / Path(*doc.relative_path.split("/"))).resolve())
        doc_rel_to_file[doc.relative_path] = abs_fp
        lang = doc.language.lower() if doc.language else ""
        file_node = NodeInfo(
            kind="File",
            name=abs_fp,
            file_path=abs_fp,
            line_start=1,
            line_end=max((o.end_line for o in doc.occurrences), default=1),
            language=lang,
        )
        store.upsert_node(file_node)
        nodes_upserted += 1

        for sym_info in doc.symbols:
            if sym_info.symbol:
                symbol_docs_map[sym_info.symbol] = sym_info.documentation

        for occ in doc.occurrences:
            if not occ.symbol or not (occ.roles & _ROLE_DEFINITION):
                continue
            kind, name = _scip_symbol_parts(occ.symbol)
            qn = f"{abs_fp}::{name}"
            symbol_to_qn[occ.symbol] = qn
            extra: dict[str, Any] = {"scip_symbol": occ.symbol}
            if occ.symbol in symbol_docs_map and symbol_docs_map[occ.symbol]:
                extra["docstring"] = "\n".join(symbol_docs_map[occ.symbol])
            store.upsert_node(
                NodeInfo(
                    kind=kind,
                    name=name,
                    file_path=abs_fp,
                    line_start=occ.line,
                    line_end=max(occ.line, occ.end_line),
                    language=lang,
                    extra=extra,
                )
            )
            store.upsert_edge(
                EdgeInfo(
                    kind="CONTAINS",
                    source=abs_fp,
                    target=qn,
                    file_path=abs_fp,
                    line=occ.line,
                    confidence=1.0,
                    resolution="scip",
                )
            )
            nodes_upserted += 1
            edges_upserted += 1

    # Pass 2: occurrences (references / imports / calls) & relationships
    for doc in docs:
        abs_fp = doc_rel_to_file.get(doc.relative_path)
        if not abs_fp:
            continue
        defs = sorted(
            (o for o in doc.occurrences if o.roles & _ROLE_DEFINITION and o.symbol),
            key=lambda o: o.line,
        )

        for occ in doc.occurrences:
            if not occ.symbol or (occ.roles & _ROLE_DEFINITION):
                continue
            target_qn = symbol_to_qn.get(occ.symbol)
            if not target_qn:
                continue
            source_qn = abs_fp
            for d in defs:
                if d.line <= occ.line:
                    source_qn = symbol_to_qn.get(d.symbol, abs_fp)
                else:
                    break
            if occ.roles & _ROLE_IMPORT:
                kind = "IMPORTS_FROM"
                source_qn = abs_fp
            elif occ.symbol.endswith("()."):
                kind = "CALLS"
            elif occ.roles & _ROLE_READ:
                kind = "REFERENCES"
            else:
                kind = "CALLS"
            store.upsert_edge(
                EdgeInfo(
                    kind=kind,
                    source=source_qn,
                    target=target_qn,
                    file_path=abs_fp,
                    line=occ.line,
                    confidence=1.0,
                    resolution="scip",
                )
            )
            edges_upserted += 1

        for sym_info in doc.symbols:
            src_qn = symbol_to_qn.get(sym_info.symbol)
            if not src_qn:
                continue
            for rel in sym_info.relationships:
                tgt_qn = symbol_to_qn.get(str(rel.get("symbol", "")))
                if not tgt_qn:
                    continue
                edge_kind = (
                    "IMPLEMENTS" if rel.get("is_implementation") else "REFERENCES"
                )
                store.upsert_edge(
                    EdgeInfo(
                        kind=edge_kind,
                        source=src_qn,
                        target=tgt_qn,
                        file_path=abs_fp,
                        line=1,
                        confidence=1.0,
                        resolution="scip",
                    )
                )
                edges_upserted += 1

    store.commit()
    return {
        "documents": len(docs),
        "nodes_upserted": nodes_upserted,
        "edges_upserted": edges_upserted,
        "scip_path": os.fspath(scip_path),
    }
