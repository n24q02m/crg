"""Tree-sitter based multi-language code parser.

Extracts structural nodes (classes, functions, imports, types) and edges
(calls, inheritance, contains) from source files.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

import tree_sitter_language_pack as tslp

if TYPE_CHECKING:
    from .federation import RepoRegistry
    from .resolver import TargetRepo

logger = logging.getLogger(__name__)


class GrammarUnavailableError(RuntimeError):
    """A language this parser claims to support has no loadable grammar.

    Signals a broken *host*, not a broken file: the grammar cache could not
    be resolved, downloaded, or loaded. Distinct from an unsupported
    language, which is an ordinary empty result.
    """


# ---------------------------------------------------------------------------
# Data models for extracted entities
# ---------------------------------------------------------------------------


@dataclass
class NodeInfo:
    kind: str  # File, Class, Function, Type, Test
    name: str
    file_path: str
    # Line numbers may be None for nodes discovered without positional info
    # (e.g. placeholders inserted from qualified-name references). The SQLite
    # schema stores these columns as nullable INTEGERs.
    line_start: int | None
    line_end: int | None
    language: str = ""
    parent_name: str | None = None  # enclosing class/module
    params: str | None = None
    return_type: str | None = None
    modifiers: str | None = None
    is_test: bool = False
    extra: dict = field(default_factory=dict)
    # Raw source slice for Function-kind nodes (line_start..line_end inclusive).
    # Populated by the parser only for kind == "Function" so batch_summarize has
    # candidates without re-reading files. Class/Type/Test/File leave this None
    # to avoid bloating the DB with content that is irrelevant for LLM summaries.
    source_text: str | None = None
    # Phase 2 Task 9: federation scoping. Empty string is the single-repo
    # default and matches the SQLite ``DEFAULT ''`` on the ``nodes.repo_id``
    # column added in alembic revision ``003_federation``. The federation
    # driver populates this via ``RepoRegistry.assign(path)``.
    repo_id: str = ""


@dataclass
class EdgeInfo:
    kind: str  # CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON
    source: str  # qualified name or path
    target: str  # qualified name or path
    file_path: str
    line: int = 0
    extra: dict = field(default_factory=dict)
    # Phase 2 Task 9: federation scoping. Same shape and rationale as
    # ``NodeInfo.repo_id``; for cross-repo edges this is the *source*
    # repo's id (the edge originates in that repo).
    repo_id: str = ""
    confidence: float = 1.0
    resolution: str = "syntactic"


# ---------------------------------------------------------------------------
# Language extension mapping
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".php": "php",
    ".sol": "solidity",
    ".dart": "dart",
}

#: The languages this parser claims to handle. Membership is what separates
#: "crg does not parse this" (an ordinary empty result) from "this host
#: cannot load a grammar it is supposed to have" (a fault worth raising).
SUPPORTED_LANGUAGES: frozenset[str] = frozenset(EXTENSION_TO_LANGUAGE.values())

# Tree-sitter node type mappings per language
# Maps (language) -> dict of semantic role -> list of TS node types
_CLASS_TYPES: dict[str, list[str]] = {
    "python": ["class_definition"],
    "javascript": ["class_declaration", "class"],
    "typescript": ["class_declaration", "class"],
    "tsx": ["class_declaration", "class"],
    "go": ["type_declaration"],
    "rust": ["struct_item", "enum_item", "trait_item", "impl_item"],
    "java": ["class_declaration", "interface_declaration", "enum_declaration"],
    "c": ["struct_specifier", "type_definition"],
    "cpp": ["class_specifier", "struct_specifier"],
    "csharp": [
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "struct_declaration",
    ],
    "ruby": ["class", "module"],
    "kotlin": ["class_declaration", "object_declaration"],
    "swift": ["class_declaration", "struct_declaration", "protocol_declaration"],
    "php": ["class_declaration", "interface_declaration"],
    "solidity": [
        "contract_declaration",
        "interface_declaration",
        "library_declaration",
        "struct_declaration",
        "enum_declaration",
        "error_declaration",
        "user_defined_type_definition",
    ],
    "dart": ["class_definition"],
}

_FUNCTION_TYPES: dict[str, list[str]] = {
    "python": ["function_definition"],
    "javascript": ["function_declaration", "method_definition", "arrow_function"],
    "typescript": ["function_declaration", "method_definition", "arrow_function"],
    "tsx": ["function_declaration", "method_definition", "arrow_function"],
    "go": ["function_declaration", "method_declaration"],
    "rust": ["function_item"],
    "java": ["method_declaration", "constructor_declaration"],
    "c": ["function_definition"],
    "cpp": ["function_definition"],
    "csharp": ["method_declaration", "constructor_declaration"],
    "ruby": ["method", "singleton_method"],
    "kotlin": ["function_declaration"],
    "swift": ["function_declaration"],
    "php": ["function_definition", "method_declaration"],
    # Solidity: events and modifiers use kind="Function" because the graph
    # schema has no dedicated kind for them.  State variables are also modeled
    # as Function nodes (public ones auto-generate getters) and distinguished
    # via extra["solidity_kind"].
    "solidity": [
        "function_definition",
        "constructor_definition",
        "modifier_definition",
        "event_definition",
        "fallback_receive_definition",
    ],
    "dart": ["method_signature", "function_signature"],
}

_IMPORT_TYPES: dict[str, list[str]] = {
    "python": ["import_statement", "import_from_statement"],
    "javascript": ["import_statement"],
    "typescript": ["import_statement"],
    "tsx": ["import_statement"],
    "go": ["import_declaration"],
    "rust": ["use_declaration"],
    "java": ["import_declaration"],
    "c": ["preproc_include"],
    "cpp": ["preproc_include"],
    "csharp": ["using_directive"],
    "ruby": ["call"],  # require/require_relative
    "kotlin": ["import_header"],
    "swift": ["import_declaration"],
    "php": ["namespace_use_declaration"],
    "solidity": ["import_directive"],
}

_CALL_TYPES: dict[str, list[str]] = {
    "python": ["call"],
    "javascript": ["call_expression", "new_expression"],
    "typescript": ["call_expression", "new_expression"],
    "tsx": ["call_expression", "new_expression"],
    "go": ["call_expression"],
    "rust": ["call_expression", "macro_invocation"],
    "java": ["method_invocation", "object_creation_expression"],
    "c": ["call_expression"],
    "cpp": ["call_expression"],
    "csharp": ["invocation_expression", "object_creation_expression"],
    "ruby": ["call", "method_call"],
    "kotlin": ["call_expression"],
    "swift": ["call_expression"],
    "php": [
        "function_call_expression",
        "member_call_expression",
        "nullsafe_member_call_expression",
        "scoped_call_expression",
    ],
    "solidity": ["call_expression"],
}

# Patterns that indicate a test function
_TEST_PATTERNS = [
    re.compile(r"^test_"),
    re.compile(r"^Test"),
    re.compile(r"_test$"),
    re.compile(r"\.test\."),
    re.compile(r"\.spec\."),
    re.compile(r"_spec$"),
]


def _is_test_function(name: str, file_path: str) -> bool:
    """A function is a test only if its name matches test patterns.
    Being in a test file alone is not sufficient (test files contain helpers too).
    """
    return any(p.search(name) for p in _TEST_PATTERNS)


def _is_test_file(qualified_or_path: str) -> bool:
    """Whether a qualified name (``<path>::<name>``) or path sits in a test file.

    Used to keep a test's own helpers out of TESTED_BY: a function defined in
    a test file is test scaffolding, never the subject under test. Helpers
    living in a non-test module (``support.py``, a fixtures package) are not
    detectable this way and do produce an edge -- see the TESTED_BY note in
    ``docs/graph.md``.

    Both the stem and the full filename are checked because the patterns split
    across the two: ``_test$`` / ``_spec$`` anchor on a stem (``foo_test.go``),
    while ``\\.test\\.`` / ``\\.spec\\.`` need the extension still attached
    (``foo.spec.ts`` has stem ``foo.spec``, which no pattern matches).
    """
    path = qualified_or_path.split("::", 1)[0]
    if not path:
        return False
    candidate = Path(path)
    return any(
        p.search(candidate.stem) or p.search(candidate.name) for p in _TEST_PATTERNS
    )


# Languages whose module-level state is understood well enough to emit
# SHARES_STATE edges. Every other language returns no state and is untouched.
_MODULE_STATE_LANGUAGES = {"python"}


def _assignment_nodes(root) -> list:
    """Assignment nodes bound at module scope in ``root``.

    Only direct children of the module node count. A name bound inside a
    function or class body belongs to that scope, not to module state, and
    treating it as shared would link every function that reuses a common
    local name.

    Both spellings the grammar has used are accepted: tree-sitter 0.26 puts
    the ``assignment`` directly under ``module``, while earlier versions wrap
    it in an ``expression_statement``. Reading only one of them yields an
    empty set and no error, so the feature would go quiet rather than fail.
    """
    found = []
    for child in root.children:
        if child.type == "assignment":
            found.append(child)
        elif child.type == "expression_statement":
            found.extend(c for c in child.children if c.type == "assignment")
    return found


def _collect_module_state(root, source: bytes, language: str) -> set[str]:
    """Names bound at module import time in ``root``."""
    if language not in _MODULE_STATE_LANGUAGES:
        return set()

    names: set[str] = set()
    for assignment in _assignment_nodes(root):
        left = assignment.child_by_field_name("left")
        if left is None:
            continue
        if left.type == "identifier":
            names.add(source[left.start_byte : left.end_byte].decode())
        elif left.type in ("pattern_list", "tuple_pattern"):
            for target in left.children:
                if target.type == "identifier":
                    names.add(source[target.start_byte : target.end_byte].decode())
    return names


def _identifiers_in(target, source: bytes) -> list[str]:
    """Names bound by an assignment target, flat or destructured."""
    if target is None:
        return []
    if target.type == "identifier":
        return [source[target.start_byte : target.end_byte].decode()]
    return [
        source[c.start_byte : c.end_byte].decode()
        for c in target.children
        if c.type == "identifier"
    ]


def _parameter_names(func_node, source: bytes) -> set[str]:
    """Every name the function's signature binds locally.

    Covers the plain, annotated, defaulted and splat spellings, each of which
    the grammar gives a different node type.
    """
    names: set[str] = set()
    params = func_node.child_by_field_name("parameters")
    if params is None:
        return names
    for p in params.children:
        if p.type == "identifier":
            names.add(source[p.start_byte : p.end_byte].decode())
            continue
        named = p.child_by_field_name("name")
        if named is not None:
            names.add(source[named.start_byte : named.end_byte].decode())
            continue
        names.update(
            source[c.start_byte : c.end_byte].decode()
            for c in p.children
            if c.type == "identifier"
        )
    return names


def _bindings_and_globals(func_node, source: bytes) -> tuple[set[str], set[str]]:
    """Names the body binds, and names it declares ``global``.

    The two together decide whether a binding reaches module state: Python
    only rebinds the module name when the function declared it ``global``.
    Without that declaration the same statement creates a local.
    """
    bound: set[str] = set()
    declared_global: set[str] = set()

    def walk(node) -> None:
        if node.type == "global_statement":
            for c in node.children:
                if c.type == "identifier":
                    declared_global.add(source[c.start_byte : c.end_byte].decode())
            return
        if node.type in ("assignment", "augmented_assignment", "for_statement"):
            bound.update(_identifiers_in(node.child_by_field_name("left"), source))
        for c in node.children:
            walk(c)

    body = func_node.child_by_field_name("body")
    if body is not None:
        walk(body)
    return bound, declared_global


def _collect_reads(node, source: bytes, candidates: set[str], reads: set[str]) -> None:
    """Record uses of ``candidates`` reachable from ``node``.

    Two positions hold an identifier that is not a use of the name: the
    member half of ``obj.NAME`` and the keyword half of ``f(NAME=1)``. Both
    descend only into the part that can genuinely reference module state.

    A missing field yields ``None``; tree-sitter returns a partial tree for
    unparseable source, and the parser has to keep going on it.
    """
    if node is None:
        return
    if node.type == "attribute":
        _collect_reads(node.child_by_field_name("object"), source, candidates, reads)
        return
    if node.type == "keyword_argument":
        _collect_reads(node.child_by_field_name("value"), source, candidates, reads)
        return
    if node.type == "global_statement":
        return
    if node.type == "identifier":
        name = source[node.start_byte : node.end_byte].decode()
        if name in candidates:
            reads.add(name)
        return
    for child in node.children:
        _collect_reads(child, source, candidates, reads)


def _scan_state_access(
    func_node, source: bytes, state_names: set[str]
) -> tuple[set[str], set[str]]:
    """Which of ``state_names`` this function reads and which it rebinds.

    A name is a write only where the function declared it ``global`` and then
    bound it. A name bound without that declaration is a local that shadows
    the module name for the whole body, so it is dropped from both sets, as
    is any name the signature already binds.

    Known to be missed: ``with`` and ``except`` aliases, comprehension
    targets, and in-place mutation such as ``CONFIG["k"] = v``, which rebinds
    nothing and is out of scope for this phase.
    """
    if not state_names:
        return set(), set()

    bound, declared_global = _bindings_and_globals(func_node, source)
    writes = state_names & bound & declared_global
    shadowed = _parameter_names(func_node, source) | (bound - declared_global)

    candidates = state_names - shadowed
    if not candidates:
        return set(), writes

    reads: set[str] = set()
    body = func_node.child_by_field_name("body")
    if body is not None:
        _collect_reads(body, source, candidates, reads)
    return reads - writes, writes


def _module_functions(root) -> list:
    """Function definitions at module scope, decorated ones included.

    A decorator wraps the definition in ``decorated_definition``, so looking
    only for ``function_definition`` among the module's children silently
    drops every decorated function.
    """
    found = []
    for child in root.children:
        if child.type == "function_definition":
            found.append(child)
        elif child.type == "decorated_definition":
            found.extend(c for c in child.children if c.type == "function_definition")
    return found


def _module_state_edges(
    root, source: bytes, file_path: str, state_names: set[str]
) -> list[EdgeInfo]:
    """Link each writer of a module-level name to each of its readers.

    A SHARES_STATE edge from A to B means A assigns a module-level name that
    B reads. It does not assert that the two are functionally related, and it
    says nothing about ordering at runtime. Direction is writer to reader,
    matching the direction of influence get_impact_radius reasons about.

    Readers alone produce nothing: two functions reading the same constant
    are not coupled, and linking them would swamp the impact radius.
    """
    writers: dict[str, list[str]] = {}
    readers: dict[str, list[str]] = {}

    for func in _module_functions(root):
        name_node = func.child_by_field_name("name")
        if name_node is None:
            continue
        func_name = source[name_node.start_byte : name_node.end_byte].decode()
        qualified = f"{file_path}::{func_name}"
        reads, writes = _scan_state_access(func, source, state_names)
        for n in sorted(writes):
            writers.setdefault(n, []).append(qualified)
        for n in sorted(reads):
            readers.setdefault(n, []).append(qualified)

    edges: list[EdgeInfo] = []
    for state_name in sorted(writers):
        for writer_qn in writers[state_name]:
            for reader_qn in readers.get(state_name, []):
                if reader_qn == writer_qn:
                    continue
                edges.append(
                    EdgeInfo(
                        kind="SHARES_STATE",
                        source=writer_qn,
                        target=reader_qn,
                        file_path=file_path,
                        line=0,
                        extra={"name": state_name},
                    )
                )
    return edges


def file_hash(path: Path) -> str:
    """SHA-256 hash of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_source_span(source_lines: list[str], start: int, end: int) -> str:
    """Return the joined slice of ``source_lines`` between 1-indexed
    ``start`` and ``end`` (both inclusive).

    ``source_lines`` is the file split on ``"\n"``. ``start`` / ``end``
    follow the same 1-indexed convention used by NodeInfo (Tree-sitter
    ``start_point[0] + 1``). Out-of-range bounds clamp to the available
    range so a malformed ``end`` (e.g. past EOF) returns whatever lines
    do exist instead of crashing. An empty ``source_lines`` returns an
    empty string.
    """
    if not source_lines:
        return ""
    # Clamp to valid 1-indexed range; tolerate inverted/None-like bounds.
    lo = max(1, start) if start else 1
    hi = min(len(source_lines), end) if end else len(source_lines)
    if hi < lo:
        return ""
    return "\n".join(source_lines[lo - 1 : hi])


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class CodeParser:
    """Parses source files using Tree-sitter and extracts structural information."""

    def __init__(self) -> None:
        self._parsers: dict[str, object] = {}
        self._module_file_cache: dict[str, str | None] = {}
        # Per-parse scratchpad: the file currently being parsed split on "\n".
        # Set in parse_bytes(), read by _handle_function_node() to populate
        # NodeInfo.source_text. Reset to None between parses so a stale
        # buffer can never leak across files.
        self._current_source_lines: list[str] | None = None
        self._php_scopes: list[tuple[int, int, str, dict[tuple[str, str], str]]] = []

    def _get_parser(self, language: str):
        """The Tree-sitter parser for ``language``.

        Returns ``None`` only when ``language`` is outside
        :data:`SUPPORTED_LANGUAGES` -- i.e. crg does not parse it, which is
        an ordinary "nothing to extract" answer.

        Raises :class:`GrammarUnavailableError` when a *supported* language
        has no loadable grammar. That is a broken host, and it must not be
        reported as an empty parse: every caller would record zero nodes for
        a file full of code and the build would look like it succeeded.
        """
        if language not in self._parsers:
            if language not in SUPPORTED_LANGUAGES:
                return None
            try:
                # tslp.get_parser expects SupportedLanguage (a large Literal
                # union). Membership in SUPPORTED_LANGUAGES is checked above,
                # so narrowing through cast is safe here.
                self._parsers[language] = tslp.get_parser(
                    cast("tslp.SupportedLanguage", language)
                )
            except Exception as exc:
                raise GrammarUnavailableError(
                    f"Tree-sitter grammar for {language!r} could not be loaded: "
                    f"{exc}. This is a host problem, not a problem with the "
                    f"file being parsed -- continuing would index every "
                    f"{language} file as zero nodes and report the build as "
                    f"successful. Check that the grammar cache directory is "
                    f"resolvable and writable "
                    f"(tree_sitter_language_pack.cache_dir()); on a host with "
                    f"no network or no usable cache location, pre-download the "
                    f"grammars or pin the cache explicitly via "
                    f"tslp.configure(tslp.PackConfig(cache_dir=...))."
                ) from exc
        return self._parsers[language]

    def detect_language(self, path: Path) -> str | None:
        suffix = path.suffix.lower()
        if suffix == ".ipynb":
            return "python"
        return EXTENSION_TO_LANGUAGE.get(suffix)

    @staticmethod
    def _extract_ipynb_source(
        raw: bytes,
    ) -> tuple[bytes, list[tuple[int, int, int]]] | None:
        """Extract code cells from a Jupyter notebook into Python source + cell line spans."""
        try:
            notebook = json.loads(raw.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(notebook, dict):
            return None
        cells = notebook.get("cells")
        if not isinstance(cells, list):
            return None

        lines_out: list[str] = []
        cell_spans: list[tuple[int, int, int]] = []
        cur_line = 1
        for idx, cell in enumerate(cells):
            if not isinstance(cell, dict) or cell.get("cell_type") != "code":
                continue
            src_field = cell.get("source", "")
            if isinstance(src_field, list):
                cell_text = "".join(str(part) for part in src_field)
            else:
                cell_text = str(src_field)
            cell_lines = cell_text.splitlines()
            start_line = cur_line
            if cell_lines:
                lines_out.extend(cell_lines)
                end_line = cur_line + len(cell_lines) - 1
            else:
                lines_out.append("")
                end_line = cur_line
            cell_spans.append((start_line, end_line, idx))
            lines_out.append("")
            cur_line = end_line + 2

        return "\n".join(lines_out).encode("utf-8"), cell_spans

    def parse_file(
        self,
        path: Path,
        *,
        repo_registry: RepoRegistry | None = None,
        target_repos: list[TargetRepo] | None = None,
    ) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse a single file and return extracted nodes and edges.

        Parameters
        ----------
        path:
            Filesystem path to the file to parse.
        repo_registry:
            Phase 2 Task 9 — when provided, every emitted ``NodeInfo``
            and ``EdgeInfo`` has its ``repo_id`` populated from
            ``repo_registry.assign(path)``. Single-repo callers (the
            default) get the legacy behaviour with empty ``repo_id``.
        target_repos:
            Phase 2 Task 9 — when both this and ``repo_registry`` are
            provided, ``IMPORTS_FROM`` edges whose target can be
            resolved across the federated targets are rewritten to
            ``<other_repo_id>:<file>::<symbol>`` via
            :func:`crg.resolver.resolve_cross_repo_imports`.
            Unresolved imports keep their original within-repo target.
        """
        try:
            source = path.read_bytes()
        except (OSError, PermissionError):
            return [], []
        return self.parse_bytes(
            path,
            source,
            repo_registry=repo_registry,
            target_repos=target_repos,
        )

    def parse_bytes(
        self,
        path: Path,
        source: bytes,
        *,
        repo_registry: RepoRegistry | None = None,
        target_repos: list[TargetRepo] | None = None,
    ) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse pre-read bytes and return extracted nodes and edges.

        This avoids re-reading the file from disk, eliminating TOCTOU gaps
        when the caller has already read the bytes (e.g. for hashing).

        See :meth:`parse_file` for the ``repo_registry`` / ``target_repos``
        federation kwargs.
        """
        language = self.detect_language(path)
        if not language:
            return [], []

        cell_spans: list[tuple[int, int, int]] | None = None
        is_notebook = path.suffix.lower() == ".ipynb"
        if is_notebook:
            extracted = self._extract_ipynb_source(source)
            if extracted is None:
                return [], []
            source, cell_spans = extracted

        # ``language`` came from EXTENSION_TO_LANGUAGE (or .ipynb), so it is
        # always in SUPPORTED_LANGUAGES and _get_parser either returns a parser
        # or raises GrammarUnavailableError.
        parser = self._get_parser(language)
        if not parser:
            return [], []

        tree = parser.parse(source)
        nodes: list[NodeInfo] = []
        edges: list[EdgeInfo] = []
        file_path_str = str(path)

        # Decode + split the file once so _handle_function_node can populate
        # NodeInfo.source_text without re-reading bytes per Function. The
        # scratchpad is cleared at the end so stale lines never leak into the
        # next parse_bytes call.
        source_text_full = source.decode("utf-8", errors="replace")
        self._current_source_lines = source_text_full.split("\n")
        if language == "php":
            self._php_scopes = self._collect_php_scopes(tree.root_node)

        try:
            # File node
            nodes.append(
                NodeInfo(
                    kind="File",
                    name=file_path_str,
                    file_path=file_path_str,
                    line_start=1,
                    line_end=source.count(b"\n") + 1,
                    language=language,
                )
            )

            # Pre-scan for import mappings and defined names
            import_map, defined_names = self._collect_file_scope(
                tree.root_node,
                language,
                source,
            )
            python_abstract_contracts = (
                self._collect_python_abstract_contracts(tree.root_node, source)
                if language == "python"
                else set()
            )
            declared_interfaces = (
                self._collect_declared_interfaces(tree.root_node, language)
                if language in {"csharp", "kotlin"}
                else set()
            )

            # Walk the tree
            self._extract_from_tree(
                tree.root_node,
                source,
                language,
                file_path_str,
                nodes,
                edges,
                import_map=import_map,
                defined_names=defined_names,
                python_abstract_contracts=python_abstract_contracts,
                declared_interfaces=declared_interfaces,
            )

            # Module-level shared state. Runs after the walk because it pairs
            # functions with each other rather than emitting per-node, and it
            # needs the whole file's set of module-level names first.
            state_names = _collect_module_state(tree.root_node, source, language)
            if state_names:
                edges.extend(
                    _module_state_edges(
                        tree.root_node, source, file_path_str, state_names
                    )
                )
            if is_notebook and cell_spans is not None:
                nodes[0].extra["notebook"] = True
                nodes[0].extra["code_cells"] = len(cell_spans)
                for node in nodes[1:]:
                    if node.line_start is None:
                        continue
                    for start_line, end_line, cell_idx in cell_spans:
                        if start_line <= node.line_start <= end_line:
                            node.extra["cell_index"] = cell_idx
                            break
        finally:
            self._current_source_lines = None
            self._php_scopes = []

        # Phase 2 Task 9: federation post-processing. Single-repo callers
        # (no registry) skip this entirely so behaviour is unchanged.
        if repo_registry is not None:
            self._apply_federation(
                path=path,
                language=language,
                nodes=nodes,
                edges=edges,
                repo_registry=repo_registry,
                target_repos=target_repos,
            )

        return nodes, edges

    def _apply_federation(
        self,
        *,
        path: Path,
        language: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        repo_registry: RepoRegistry,
        target_repos: list[TargetRepo] | None,
    ) -> None:
        """Stamp ``repo_id`` on nodes/edges and resolve cross-repo imports.

        Tagging is unconditional once a registry is wired in (every node
        belongs to *some* repo, even in single-repo federation mode);
        cross-repo IMPORTS_FROM rewrites are best-effort and only run
        when ``target_repos`` is non-empty.
        """
        # Resolve once, reuse for every node/edge in this file.
        try:
            source_repo_id = repo_registry.assign(path)
        except ValueError:
            # File lives outside every registered root — leave repo_id
            # empty so the row is still writeable; the caller decides
            # whether to register the path before retrying.
            return

        for node in nodes:
            node.repo_id = source_repo_id
        for edge in edges:
            edge.repo_id = source_repo_id

        if not target_repos:
            return

        # Cross-repo IMPORTS_FROM rewrite. Lazy import keeps the
        # resolver's tomllib/regex cost off the hot path for callers
        # that don't pass target_repos.
        from .resolver import resolve_cross_repo_imports  # noqa: PLC0415

        # Look up the source repo's filesystem root (registry knows it)
        # so the resolver can read its ``pyproject.toml`` /
        # ``Cargo.toml`` / ``go.mod`` etc. ``RepoRegistry.entries()``
        # gives us the canonical mapping.
        source_root: Path | None = None
        for entry in repo_registry.entries():
            if entry.repo_id == source_repo_id:
                source_root = entry.path
                break
        if source_root is None:
            return

        for edge in edges:
            if edge.kind != "IMPORTS_FROM":
                continue
            # Prefer the original import line (captured into
            # ``extra["import_stmt"]`` by ``_handle_import_node``) so
            # the resolvers see the imported symbol name. Fall back to
            # a synthesised statement built from the bare target —
            # this keeps the path working for legacy callers that
            # construct EdgeInfo by hand without ``extra``.
            stmt = (edge.extra or {}).get("import_stmt") or self._build_resolver_stmt(
                language, edge.target
            )
            try:
                resolved = resolve_cross_repo_imports(
                    stmt,
                    language,
                    source_root,
                    source_repo_id,
                    target_repos,
                )
            except Exception as exc:
                # The resolver may touch the filesystem; treat any
                # error as "no cross-repo match" rather than aborting
                # the whole parse. Single-repo mode is preserved.
                #
                # The fallback is deliberate, the silence was not: the
                # resolver returns None for a genuine "no match", so an
                # exception here is a different event entirely, and it
                # previously produced no record at any log level. A whole
                # federated build could resolve zero cross-repo imports and
                # look exactly like a correctly configured single-repo one.
                logger.warning(
                    "Cross-repo import resolution failed for %r in %s "
                    "(%s: %s); leaving the edge target unresolved, so this "
                    "import will not be linked across repos.",
                    stmt,
                    path,
                    type(exc).__name__,
                    exc,
                )
                resolved = None
            if resolved is not None:
                edge.target = resolved

    @staticmethod
    def _build_resolver_stmt(language: str, target: str) -> str:
        """Synthesise an import statement from the parser's bare target.

        The parser stores per-language extracted forms (Python: dotted
        module, JS/TS: module path string, Go: quoted path, Rust: full
        ``use`` line, Java/Kotlin/C#: dotted name, Solidity/Ruby:
        quoted path). The cross-repo resolvers re-parse these strings
        with their own regexes so the round-trip is lossy in edge
        cases (e.g. Python's imported symbol name is dropped because
        we only keep the module). For Phase 2 Task 9 this is the
        documented trade-off: cross-repo qualified names use the
        module's basename when the imported symbol name is not
        threaded through the parser-extracted target.
        """
        lang = language.lower()
        if lang == "python":
            return f"import {target}"
        if lang in ("javascript", "typescript", "tsx"):
            # TypeScript resolver matches the module string anywhere on the line.
            return f'import "{target}"'
        if lang == "go":
            return f'import "{target}"'
        if lang == "rust":
            # Rust resolver expects ``use ...;`` shape; the target is
            # already the full path-with-`::`.
            stripped = target.strip().rstrip(";")
            if stripped.startswith("use "):
                return target
            return f"use {stripped};"
        if lang in ("java", "kotlin"):
            return f"import {target};"
        # Fallback / tier-2 languages: pass through verbatim.
        return target

    def _extract_from_tree(
        self,
        root,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None = None,
        enclosing_func: str | None = None,
        import_map: dict[str, str] | None = None,
        defined_names: set[str] | None = None,
        local_defined_names: set[str] | None = None,
        python_abstract_contracts: set[str] | None = None,
        declared_interfaces: set[str] | None = None,
    ) -> None:
        """Recursively walk the AST and extract nodes/edges."""
        class_types = set(_CLASS_TYPES.get(language, []))
        func_types = set(_FUNCTION_TYPES.get(language, []))
        import_types = set(_IMPORT_TYPES.get(language, []))
        call_types = set(_CALL_TYPES.get(language, []))

        for child in root.children:
            node_type = child.type
            processed = False

            if node_type in class_types:
                processed = self._handle_class_node(
                    child,
                    source,
                    language,
                    file_path,
                    nodes,
                    edges,
                    enclosing_class,
                    import_map,
                    defined_names,
                    local_defined_names,
                    python_abstract_contracts,
                    declared_interfaces,
                )
            elif node_type in func_types and not (
                language == "dart"
                and node_type == "function_signature"
                and root.type == "method_signature"
            ):
                processed = self._handle_function_node(
                    child,
                    source,
                    language,
                    file_path,
                    nodes,
                    edges,
                    enclosing_class,
                    import_map,
                    defined_names,
                    local_defined_names,
                    python_abstract_contracts,
                    declared_interfaces,
                )
            elif node_type in import_types:
                processed = self._handle_import_node(
                    child, source, language, file_path, edges
                )
            elif node_type in call_types:
                processed = self._handle_call_node(
                    child,
                    source,
                    language,
                    file_path,
                    edges,
                    enclosing_class,
                    enclosing_func,
                    import_map,
                    defined_names,
                    local_defined_names,
                )

            if not processed and language == "solidity":
                processed = self._handle_solidity_node(
                    child,
                    source,
                    language,
                    file_path,
                    nodes,
                    edges,
                    enclosing_class,
                    enclosing_func,
                )

            if processed:
                continue

            # Recurse for other node types
            self._extract_from_tree(
                child,
                source,
                language,
                file_path,
                nodes,
                edges,
                enclosing_class=enclosing_class,
                enclosing_func=enclosing_func,
                import_map=import_map,
                defined_names=defined_names,
                local_defined_names=local_defined_names,
                python_abstract_contracts=python_abstract_contracts,
                declared_interfaces=declared_interfaces,
            )

    def _handle_class_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        import_map: dict[str, str] | None,
        defined_names: set[str] | None,
        local_defined_names: set[str] | None,
        python_abstract_contracts: set[str] | None,
        declared_interfaces: set[str] | None,
    ) -> bool:
        name = self._get_name(node, language, "class")
        if not name:
            return False

        is_rust_impl = language == "rust" and node.type == "impl_item"
        if not is_rust_impl:
            node_info = NodeInfo(
                kind="Class",
                name=name,
                file_path=file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                language=language,
                parent_name=enclosing_class,
            )
            if language == "php":
                node_info.extra["php_symbol"] = self._php_declared_symbol(
                    node, name, enclosing_class
                )
            nodes.append(node_info)

            # CONTAINS edge
            edges.append(
                EdgeInfo(
                    kind="CONTAINS",
                    source=file_path,
                    target=self._qualify(name, file_path, enclosing_class),
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )

        # Inheritance/implementation edges
        relationships = self._get_bases(
            node,
            language,
            source,
            python_abstract_contracts=python_abstract_contracts,
            declared_interfaces=declared_interfaces,
        )
        for kind, base in relationships:
            target = base
            if (
                kind == "IMPLEMENTS"
                and not any(separator in base for separator in (".", "::", "\\"))
                and base in (defined_names or set())
            ):
                target = self._qualify(base, file_path, None)
            edges.append(
                EdgeInfo(
                    kind=kind,
                    source=self._qualify(name, file_path, enclosing_class),
                    target=target,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )

        # Recurse into class body
        self._extract_from_tree(
            node,
            source,
            language,
            file_path,
            nodes,
            edges,
            enclosing_class=name,
            enclosing_func=None,
            import_map=import_map,
            defined_names=defined_names,
            local_defined_names=local_defined_names,
            python_abstract_contracts=python_abstract_contracts,
            declared_interfaces=declared_interfaces,
        )
        return True

    def _handle_function_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        import_map: dict[str, str] | None,
        defined_names: set[str] | None,
        local_defined_names: set[str] | None,
        python_abstract_contracts: set[str] | None = None,
        declared_interfaces: set[str] | None = None,
    ) -> bool:
        name = self._get_name(node, language, "function")
        if not name:
            return False
        if (
            language == "go"
            and node.type == "method_declaration"
            and enclosing_class is None
        ):
            enclosing_class = self._get_go_receiver_type(node)

        nested_names = self._collect_nested_function_names(node, language)
        visible_local_names = set(local_defined_names or ())
        visible_local_names.update(nested_names)

        is_test = _is_test_function(name, file_path)
        kind = "Test" if is_test else "Function"
        qualified = self._qualify(name, file_path, enclosing_class)
        params = self._get_params(node, language, source)
        ret_type = self._get_return_type(node, language, source)

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1
        # Only Function-kind nodes carry source_text — Test/Class skip to keep
        # batch_summarize's candidate set focused and the DB compact.
        source_text: str | None = None
        if kind == "Function" and self._current_source_lines is not None:
            source_text = _extract_source_span(
                self._current_source_lines, line_start, line_end
            )

        node_info = NodeInfo(
            kind=kind,
            name=name,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            language=language,
            parent_name=enclosing_class,
            params=params,
            return_type=ret_type,
            is_test=is_test,
            source_text=source_text,
        )
        if language == "php":
            node_info.extra["php_symbol"] = self._php_declared_symbol(
                node, name, enclosing_class
            )
        nodes.append(node_info)

        # CONTAINS edge
        container = (
            self._qualify(enclosing_class, file_path, None)
            if enclosing_class
            else file_path
        )
        edges.append(
            EdgeInfo(
                kind="CONTAINS",
                source=container,
                target=qualified,
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )

        # Solidity: modifier invocations on functions → CALLS edges
        if language == "solidity":
            for sub in node.children:
                if sub.type == "modifier_invocation":
                    for ident in sub.children:
                        if ident.type == "identifier":
                            edges.append(
                                EdgeInfo(
                                    kind="CALLS",
                                    source=qualified,
                                    target=ident.text.decode(
                                        "utf-8",
                                        errors="replace",
                                    ),
                                    file_path=file_path,
                                    line=sub.start_point[0] + 1,
                                )
                            )
                            break

        # Recurse to find calls inside the function
        self._extract_from_tree(
            node,
            source,
            language,
            file_path,
            nodes,
            edges,
            enclosing_class=enclosing_class,
            enclosing_func=name,
            import_map=import_map,
            defined_names=defined_names,
            local_defined_names=visible_local_names or None,
            python_abstract_contracts=python_abstract_contracts,
            declared_interfaces=declared_interfaces,
        )
        return True

    def _handle_import_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        edges: list[EdgeInfo],
    ) -> bool:
        imports = self._extract_import(node, language, source)
        # Phase 2 Task 9: stash the raw import line on the edge so the
        # federation post-processing can hand the full statement (with
        # the imported symbol name intact) to the cross-repo resolvers.
        # Single-repo callers ignore this field entirely.
        raw_stmt = node.text.decode("utf-8", errors="replace").strip()
        for imp_target in imports:
            edges.append(
                EdgeInfo(
                    kind="IMPORTS_FROM",
                    source=file_path,
                    target=imp_target,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                    extra={"import_stmt": raw_stmt},
                )
            )
        return True

    def _handle_call_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        enclosing_func: str | None,
        import_map: dict[str, str] | None,
        defined_names: set[str] | None,
        local_defined_names: set[str] | None,
    ) -> bool:
        call_name = self._get_call_name(node, language, source)
        if call_name:
            # Attribute calls on the module/IIFE toplevel have no enclosing
            # function. File-level init code — e.g. JavaScript IIFE bodies,
            # ``document.addEventListener('click', handler)`` wiring, or a
            # Python module calling helpers at import time — still *uses*
            # the referenced symbols, so the edges are attributed to the
            # File node (qualified name = file path) instead of being
            # dropped. This keeps callers_of/dead-code from reporting
            # handlers registered by toplevel init code as unreferenced.
            caller = (
                self._qualify(enclosing_func, file_path, enclosing_class)
                if enclosing_func
                else file_path
            )
            call_extra = {}
            if language == "php":
                target = call_name
                call_extra = {
                    "php_targets": self._php_call_targets(
                        node, call_name, enclosing_class
                    ),
                    "php_unresolved_target": call_name,
                }
            else:
                target = self._resolve_call_target(
                    call_name,
                    file_path,
                    language,
                    import_map or {},
                    defined_names or set(),
                    enclosing_class=enclosing_class,
                    local_defined_names=local_defined_names,
                )
            line = node.start_point[0] + 1
            edges.append(
                EdgeInfo(
                    kind="CALLS",
                    source=caller,
                    target=target,
                    file_path=file_path,
                    line=line,
                    extra=call_extra,
                )
            )
            # Function references passed as arguments — e.g. JS
            # ``el.addEventListener('click', handler)`` or Python
            # ``deferred.addCallback(handler)`` — are a real use of the
            # referenced symbol, but the argument identifier itself is not
            # a call expression, so they previously produced no CALLS edge
            # and dead-code analysis reported the handler as unreferenced.
            # Emit CALLS edges for argument identifiers that resolve to a
            # file-scope definition or an import, so callers_of(handler)
            # finds the registering function.
            self._emit_argument_reference_edges(
                node,
                source,
                language,
                file_path,
                edges,
                caller,
                enclosing_class,
                call_name,
                import_map,
                defined_names,
                local_defined_names,
            )
            # TESTED_BY means "called directly by a test", NOT "properly
            # tested". A test calls its subject, but it also calls helpers,
            # builders and assertion utilities, and no static rule separates
            # intent from incidental use. Consumers must read the edge with
            # that meaning -- see _is_test_file for the one exclusion applied.
            # Toplevel/file-level calls have no test function to attribute.
            if (
                enclosing_func
                and _is_test_function(enclosing_func, file_path)
                and not _is_test_file(target)
            ):
                edges.append(
                    EdgeInfo(
                        kind="TESTED_BY",
                        source=caller,
                        target=target,
                        file_path=file_path,
                        line=line,
                    )
                )
        return False

    def _emit_argument_reference_edges(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        edges: list[EdgeInfo],
        caller: str,
        enclosing_class: str | None,
        call_name: str | None,
        import_map: dict[str, str] | None,
        defined_names: set[str] | None,
        local_defined_names: set[str] | None,
    ) -> None:
        """Emit CALLS edges for function references passed as call arguments.

        Tree-sitter grammars expose call arguments under a field named
        ``arguments`` (JavaScript/TypeScript ``arguments``, Python
        ``arguments``, Go ``arguments``, Java ``argument_list``). This
        helper walks that subtree, collects bare identifiers, and for
        each one that resolves to a visible file/local definition or an
        imported symbol, records a CALLS edge from the enclosing function to
        the resolved target. This keeps dead-code analysis from flagging
        callback-style references (``el.addEventListener('click',
        handler)``) as unreferenced.
        """
        args_node = node.child_by_field_name("arguments")
        if args_node is None:
            return

        seen: set[str] = set()
        call_types = _CALL_TYPES.get(language, ())
        import_names = import_map or {}
        definition_names = defined_names or set()
        local_names = local_defined_names or set()
        for ident in self._iter_argument_identifiers(args_node, call_types):
            name = ident.text.decode("utf-8", errors="replace")
            if not name or name in seen or name == call_name:
                continue
            seen.add(name)
            # Match direct-call resolution: an imported name remains a valid
            # reference even when its module is external or not indexed, so
            # _resolve_call_target may intentionally return the bare name.
            if (
                name not in definition_names
                and name not in local_names
                and name not in import_names
            ):
                continue
            resolved = self._resolve_call_target(
                name,
                file_path,
                language,
                import_names,
                definition_names,
                enclosing_class=enclosing_class,
                local_defined_names=local_names,
            )
            # Only emit identifiers that resolve to a same-file definition or
            # an import. Unknown bare names stay untouched.
            if resolved == name and name not in import_names:
                continue
            edges.append(
                EdgeInfo(
                    kind="CALLS",
                    source=caller,
                    target=resolved,
                    file_path=file_path,
                    line=ident.start_point[0] + 1,
                )
            )

    @staticmethod
    def _iter_argument_identifiers(args_node, call_types=()):
        """Yield identifiers in an arguments subtree.

        Nested calls are skipped because their own call nodes are visited by
        the main tree walk and emit their own edges. ``call_types`` is
        language-specific: grammars use different node names for calls.
        """
        nested_callable_types = (
            "function_expression",
            "arrow_function",
            "lambda",
        )
        stack = [args_node]
        while stack:
            current = stack.pop()
            for child in current.children:
                if child.type == "identifier":
                    yield child
                elif child.type in call_types or child.type in nested_callable_types:
                    continue
                else:
                    stack.append(child)

    def _handle_solidity_emit_statement(
        self,
        node,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        enclosing_func: str | None,
    ) -> bool:
        if not enclosing_func:
            return False
        for sub in node.children:
            if sub.type == "expression":
                for ident in sub.children:
                    if ident.type == "identifier":
                        caller = self._qualify(
                            enclosing_func,
                            file_path,
                            enclosing_class,
                        )
                        edges.append(
                            EdgeInfo(
                                kind="CALLS",
                                source=caller,
                                target=ident.text.decode("utf-8", errors="replace"),
                                file_path=file_path,
                                line=node.start_point[0] + 1,
                            )
                        )
        return False

    def _handle_solidity_state_variable(
        self,
        node,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
    ) -> bool:
        if not enclosing_class:
            return False
        var_name = None
        var_visibility = None
        var_mutability = None
        var_type = None
        for sub in node.children:
            if sub.type == "identifier":
                var_name = sub.text.decode("utf-8", errors="replace")
            elif sub.type == "visibility":
                var_visibility = sub.text.decode("utf-8", errors="replace")
            elif sub.type == "type_name":
                var_type = sub.text.decode("utf-8", errors="replace")
            elif sub.type in ("constant", "immutable"):
                var_mutability = sub.type
        if var_name:
            qualified = self._qualify(var_name, file_path, enclosing_class)
            nodes.append(
                NodeInfo(
                    kind="Function",
                    name=var_name,
                    file_path=file_path,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    language=language,
                    parent_name=enclosing_class,
                    return_type=var_type,
                    modifiers=var_visibility,
                    extra={
                        "solidity_kind": "state_variable",
                        "mutability": var_mutability,
                    },
                )
            )
            edges.append(
                EdgeInfo(
                    kind="CONTAINS",
                    source=self._qualify(
                        enclosing_class,
                        file_path,
                        None,
                    ),
                    target=qualified,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )
            return True
        return False

    def _handle_solidity_constant_variable(
        self,
        node,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
    ) -> bool:
        var_name = None
        var_type = None
        for sub in node.children:
            if sub.type == "identifier":
                var_name = sub.text.decode("utf-8", errors="replace")
            elif sub.type == "type_name":
                var_type = sub.text.decode("utf-8", errors="replace")
        if var_name:
            qualified = self._qualify(
                var_name,
                file_path,
                enclosing_class,
            )
            nodes.append(
                NodeInfo(
                    kind="Function",
                    name=var_name,
                    file_path=file_path,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    language=language,
                    parent_name=enclosing_class,
                    return_type=var_type,
                    extra={"solidity_kind": "constant"},
                )
            )
            container = (
                self._qualify(enclosing_class, file_path, None)
                if enclosing_class
                else file_path
            )
            edges.append(
                EdgeInfo(
                    kind="CONTAINS",
                    source=container,
                    target=qualified,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )
            return True
        return False

    def _handle_solidity_using_directive(
        self,
        node,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: str | None,
    ) -> bool:
        lib_name = None
        for sub in node.children:
            if sub.type == "type_alias":
                for ident in sub.children:
                    if ident.type == "identifier":
                        lib_name = ident.text.decode(
                            "utf-8",
                            errors="replace",
                        )
        if lib_name:
            source_name = (
                self._qualify(enclosing_class, file_path, None)
                if enclosing_class
                else file_path
            )
            edges.append(
                EdgeInfo(
                    kind="DEPENDS_ON",
                    source=source_name,
                    target=lib_name,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )
            return True
        return False

    def _handle_solidity_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        enclosing_func: str | None,
    ) -> bool:
        if language != "solidity":
            return False

        node_type = node.type
        if node_type == "emit_statement":
            return self._handle_solidity_emit_statement(
                node, file_path, edges, enclosing_class, enclosing_func
            )
        if node_type == "state_variable_declaration":
            return self._handle_solidity_state_variable(
                node, language, file_path, nodes, edges, enclosing_class
            )
        if node_type == "constant_variable_declaration":
            return self._handle_solidity_constant_variable(
                node, language, file_path, nodes, edges, enclosing_class
            )
        if node_type == "using_directive":
            return self._handle_solidity_using_directive(
                node, file_path, edges, enclosing_class
            )
        return False

    def _collect_file_scope(
        self,
        root,
        language: str,
        source: bytes,
    ) -> tuple[dict[str, str], set[str]]:
        """Pre-scan top-level AST to collect import mappings and defined names.

        Returns:
            (import_map, defined_names) where import_map maps imported names
            to their source module/path, and defined_names is the set of
            function/class names defined at file scope.
        """
        import_map: dict[str, str] = {}
        defined_names: set[str] = set()

        class_types = set(_CLASS_TYPES.get(language, []))
        func_types = set(_FUNCTION_TYPES.get(language, []))
        import_types = set(_IMPORT_TYPES.get(language, []))

        # Node types that wrap a class/function with decorators/annotations
        decorator_wrappers = {"decorated_definition", "decorator"}

        for child in root.children:
            node_type = child.type

            # Unwrap decorator wrappers to reach the inner definition
            target = child
            if node_type in decorator_wrappers:
                for inner in child.children:
                    if inner.type in func_types or inner.type in class_types:
                        target = inner
                        break

            target_type = target.type

            # Collect defined function/class names
            if target_type in func_types or target_type in class_types:
                name = self._get_name(
                    target,
                    language,
                    "class" if target_type in class_types else "function",
                )
                if name:
                    defined_names.add(name)

            # Collect import mappings: imported_name → module_path
            if node_type in import_types:
                self._collect_import_names(child, language, source, import_map)

        # Anonymous JS wrappers (IIFEs/load callbacks) are flattened by the
        # parser: calls inside them are attributed to the File node, and named
        # declarations in that wrapper use file-qualified names. Do not fold
        # declarations under a named function or class into file scope.
        if language in ("javascript", "typescript", "tsx"):
            defined_names.update(self._collect_iife_function_names(root, language))

        return import_map, defined_names

    def _collect_iife_function_names(self, root, language: str) -> set[str]:
        """Collect declarations flattened into JS anonymous-wrapper scope."""
        if language not in ("javascript", "typescript", "tsx"):
            return set()

        names: set[str] = set()

        def visit(current, scope_kind: str) -> None:
            for child in current.children:
                if child.type == "function_declaration":
                    if scope_kind in {"module", "anonymous"}:
                        name = self._get_name(child, language, "function")
                        if name:
                            names.add(name)
                    # A named function introduces a lexical scope of its own.
                    continue
                if child.type in (
                    "class_declaration",
                    "class",
                    "method_definition",
                ):
                    continue
                if child.type in ("function_expression", "arrow_function"):
                    visit(child, "anonymous")
                else:
                    visit(child, scope_kind)

        visit(root, "module")
        return names

    def _collect_nested_function_names(self, node, language: str) -> set[str]:
        """Collect named declarations visible inside one function body."""
        if language not in ("javascript", "typescript", "tsx"):
            return set()

        names: set[str] = set()

        def visit(current) -> None:
            for child in current.children:
                if child.type == "function_declaration":
                    name = self._get_name(child, language, "function")
                    if name:
                        names.add(name)
                    # Declarations below this child belong to its scope.
                    continue
                if child.type in (
                    "class_declaration",
                    "class",
                    "method_definition",
                ):
                    continue
                visit(child)

        visit(node)
        return names

    @staticmethod
    def _iter_tree_nodes(root):
        yield root
        for child in root.children:
            yield from CodeParser._iter_tree_nodes(child)

    @staticmethod
    def _short_type_name(value: str) -> str:
        value = re.sub(r"(?:<.*>|\[.*\])$", "", value.strip())
        return value.rsplit(".", 1)[-1].rsplit("::", 1)[-1].rsplit("\\", 1)[-1].strip()

    def _collect_python_abstract_contracts(self, root, source: bytes) -> set[str]:
        """Collect abstract contracts known within one Python module.

        Python's protocol conformance is structural and intentionally remains
        out of scope. An ``IMPLEMENTS`` edge is emitted only for an explicit
        ABC/Protocol inheritance chain or a class that declares an
        ``@abstractmethod``.
        """
        contracts = {"ABC", "Protocol"}
        abstract_decorators = {"abstractmethod"}
        for import_node in self._iter_tree_nodes(root):
            if import_node.type != "import_from_statement":
                continue
            statement = import_node.text.decode("utf-8", errors="replace")
            match = re.match(
                r"from\s+(abc|typing)\s+import\s+(.+)", statement, re.DOTALL
            )
            if not match:
                continue
            for item in match.group(2).split(","):
                parts = item.strip().split()
                if not parts:
                    continue
                original = parts[0]
                local = parts[2] if len(parts) >= 3 and parts[1] == "as" else original
                if original in {"ABC", "Protocol"}:
                    contracts.add(local)
                if original == "abstractmethod":
                    abstract_decorators.add(local)
        classes: list[tuple[str, list[str], bool]] = []

        for candidate in self._iter_tree_nodes(root):
            if candidate.type != "class_definition":
                continue
            name = self._get_name(candidate, "python", "class")
            if not name:
                continue
            bases = self._get_bases_python(candidate)
            has_abstract_method = any(
                descendant.type == "decorator"
                and any(
                    re.search(
                        rf"(?:@|\.){re.escape(marker)}\b",
                        descendant.text.decode("utf-8", errors="replace"),
                    )
                    for marker in abstract_decorators
                )
                for descendant in self._iter_tree_nodes(candidate)
            )
            classes.append((name, bases, has_abstract_method))

        changed = True
        while changed:
            changed = False
            for name, bases, has_abstract_method in classes:
                if name in contracts:
                    continue
                if has_abstract_method or any(
                    self._short_type_name(base) in contracts for base in bases
                ):
                    contracts.add(name)
                    changed = True
        return contracts

    def _collect_declared_interfaces(self, root, language: str) -> set[str]:
        if language not in {"csharp", "kotlin"}:
            return set()
        return {
            name
            for node in self._iter_tree_nodes(root)
            if (
                node.type == "interface_declaration"
                or (
                    language == "kotlin"
                    and node.type == "class_declaration"
                    and any(child.type == "interface" for child in node.children)
                )
            )
            for name in [self._get_name(node, language, "class")]
            if name
        }

    def _collect_import_names(
        self,
        node,
        language: str,
        source: bytes,
        import_map: dict[str, str],
    ) -> None:
        """Extract imported names and their source modules into import_map."""
        if language == "python":
            self._collect_python_import_names(node, import_map)
        elif language in ("javascript", "typescript", "tsx"):
            self._collect_js_ts_import_names(node, import_map)

    def _collect_python_import_names(
        self,
        node,
        import_map: dict[str, str],
    ) -> None:
        """Extract Python imported names from an import_from_statement."""
        if node.type != "import_from_statement":
            return

        # from X.Y import A, B → {A: X.Y, B: X.Y}
        module = None
        seen_import_keyword = False
        for child in node.children:
            if child.type == "dotted_name" and not seen_import_keyword:
                module = child.text.decode("utf-8", errors="replace")
            elif child.type == "import":
                seen_import_keyword = True
            elif seen_import_keyword and module:
                if child.type in ("identifier", "dotted_name"):
                    name = child.text.decode("utf-8", errors="replace")
                    import_map[name] = module
                elif child.type == "aliased_import":
                    # from X import A as B → {B: X}
                    names = [
                        sub.text.decode("utf-8", errors="replace")
                        for sub in child.children
                        if sub.type in ("identifier", "dotted_name")
                    ]
                    # Last name is the alias (local name)
                    if names:
                        import_map[names[-1]] = module

    def _collect_js_ts_import_names(
        self,
        node,
        import_map: dict[str, str],
    ) -> None:
        """Extract JS/TS imported names from an import_statement."""
        # import { A, B } from './path' → {A: ./path, B: ./path}
        module = None
        for child in node.children:
            if child.type == "string":
                module = child.text.decode("utf-8", errors="replace").strip("'\"")
        if module:
            for child in node.children:
                if child.type == "import_clause":
                    self._collect_js_import_names(child, module, import_map)

    def _collect_js_import_names(
        self,
        clause_node,
        module: str,
        import_map: dict[str, str],
    ) -> None:
        """Walk JS/TS import_clause to extract named and default imports."""
        for child in clause_node.children:
            if child.type == "identifier":
                # Default import
                import_map[child.text.decode("utf-8", errors="replace")] = module
            elif child.type == "named_imports":
                for spec in child.children:
                    if spec.type == "import_specifier":
                        # Could be: name or name as alias
                        names = [
                            s.text.decode("utf-8", errors="replace")
                            for s in spec.children
                            if s.type in ("identifier", "property_identifier")
                        ]
                        # Last identifier is the local name
                        if names:
                            import_map[names[-1]] = module

    def _resolve_module_to_file(
        self,
        module: str,
        file_path: str,
        language: str,
    ) -> str | None:
        """Resolve a module/import path to an absolute file path.

        Uses self._module_file_cache to avoid repeated filesystem lookups.
        """
        caller_dir = str(Path(file_path).parent)
        cache_key = f"{language}:{caller_dir}:{module}"
        if cache_key in self._module_file_cache:
            return self._module_file_cache[cache_key]

        resolved = self._do_resolve_module(module, file_path, language)
        self._module_file_cache[cache_key] = resolved
        return resolved

    def _do_resolve_module(
        self,
        module: str,
        file_path: str,
        language: str,
    ) -> str | None:
        """Language-aware module-to-file resolution."""
        caller_dir = Path(file_path).parent

        if language == "python":
            rel_path = module.replace(".", "/")
            candidates = [rel_path + ".py", rel_path + "/__init__.py"]
            # Walk up from caller's directory to find the module file
            current = caller_dir
            while True:
                for candidate in candidates:
                    target = current / candidate
                    if target.is_file():
                        return str(target.resolve())
                if current == current.parent:
                    break
                current = current.parent

        elif language in ("javascript", "typescript", "tsx"):
            if module.startswith("."):
                # Relative import — resolve from caller's directory
                base = caller_dir / module
                extensions = [".ts", ".tsx", ".js", ".jsx"]
                # Try exact path first (might already have extension)
                if base.is_file():
                    return str(base.resolve())
                # Try with extensions
                for ext in extensions:
                    target = base.with_suffix(ext)
                    if target.is_file():
                        return str(target.resolve())
                # Try index file in directory
                if base.is_dir():
                    for ext in extensions:
                        target = base / f"index{ext}"
                        if target.is_file():
                            return str(target.resolve())

        return None

    def _resolve_call_target(
        self,
        call_name: str,
        file_path: str,
        language: str,
        import_map: dict[str, str],
        defined_names: set[str],
        *,
        enclosing_class: str | None = None,
        local_defined_names: set[str] | None = None,
    ) -> str:
        """Resolve a bare call name to a scoped qualified target."""
        local_names = local_defined_names or set()
        if call_name in local_names:
            return self._qualify(call_name, file_path, enclosing_class)
        if call_name in defined_names:
            return self._qualify(call_name, file_path, None)
        if call_name in import_map:
            resolved = self._resolve_module_to_file(
                import_map[call_name],
                file_path,
                language,
            )
            if resolved:
                return self._qualify(call_name, resolved, None)
        return call_name

    def _qualify(self, name: str, file_path: str, enclosing_class: str | None) -> str:
        """Create a qualified name: file_path::ClassName.name or file_path::name."""
        if enclosing_class:
            return f"{file_path}::{enclosing_class}.{name}"
        return f"{file_path}::{name}"

    def _get_name(self, node, language: str, kind: str) -> str | None:
        """Extract the name from a class/function definition node."""
        if language == "solidity":
            name = self._get_name_solidity(node)
            if name:
                return name

        if language == "rust" and node.type == "impl_item":
            name = self._get_name_rust_impl(node)
            if name:
                return name

        if language == "dart":
            name_node = node.child_by_field_name("name")
            if name_node is None and node.type == "method_signature":
                name_node = next(
                    (
                        child.child_by_field_name("name")
                        for child in node.children
                        if child.type == "function_signature"
                    ),
                    None,
                )
            if name_node is not None:
                return name_node.text.decode("utf-8", errors="replace")

        if language in ("c", "cpp") and kind == "function":
            name = self._get_name_cpp(node, language, kind)
            if name:
                return name

        if language == "go" and node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return name_node.text.decode("utf-8", errors="replace")

        # Most languages use a "name" child
        for child in node.children:
            if child.type in (
                "identifier",
                "name",
                "type_identifier",
                "property_identifier",
                "simple_identifier",
                "constant",
            ):
                return child.text.decode("utf-8", errors="replace")

        if language == "go" and node.type == "type_declaration":
            return self._get_name_go(node, language, kind)

        return None

    def _get_name_solidity(self, node) -> str | None:
        """Extract name for Solidity nodes."""
        if node.type == "constructor_definition":
            return "constructor"
        if node.type == "fallback_receive_definition":
            for child in node.children:
                if child.type in ("receive", "fallback"):
                    return child.text.decode("utf-8", errors="replace")
        return None

    def _get_name_cpp(self, node, language: str, kind: str) -> str | None:
        """Extract name for C/C++ nodes."""
        for child in node.children:
            if child.type in ("function_declarator", "pointer_declarator"):
                result = self._get_name(child, language, kind)
                if result:
                    return result
        return None

    def _get_name_go(self, node, language: str, kind: str) -> str | None:
        """Extract name for Go nodes."""
        for child in node.children:
            if child.type == "type_spec":
                return self._get_name(child, language, kind)
        return None

    def _get_go_receiver_type(self, node) -> str | None:
        """Extract receiver type name from a Go method_declaration node."""
        recv = node.child_by_field_name("receiver")
        if recv is None:
            return None
        for param in recv.children:
            if param.type == "parameter_declaration":
                for child in param.children:
                    if child.type == "type_identifier":
                        return child.text.decode("utf-8", errors="replace")
                    if child.type == "pointer_type":
                        for sub in child.children:
                            if sub.type == "type_identifier":
                                return sub.text.decode("utf-8", errors="replace")
        return None

    def _get_params(self, node, language: str, source: bytes) -> str | None:
        """Extract parameter list as a string."""
        if language == "solidity":
            return self._get_params_solidity(node)

        if language == "dart" and node.type == "method_signature":
            node = next(
                (
                    child
                    for child in node.children
                    if child.type == "function_signature"
                ),
                node,
            )

        if language == "dart":
            for child in node.children:
                if child.type == "formal_parameter_list":
                    return child.text.decode("utf-8", errors="replace")

        for child in node.children:
            if child.type in ("parameters", "formal_parameters", "parameter_list"):
                return child.text.decode("utf-8", errors="replace")
        return None

    def _get_params_solidity(self, node) -> str | None:
        """Extract parameters for Solidity nodes."""
        params = [
            c.text.decode("utf-8", errors="replace")
            for c in node.children
            if c.type == "parameter"
        ]
        if params:
            return f"({', '.join(params)})"
        return None

    def _get_return_type(self, node, language: str, source: bytes) -> str | None:
        """Extract return type annotation if present."""
        if language == "python":
            return self._get_return_type_python(node)

        if language == "dart":
            if node.type == "method_signature":
                node = next(
                    (
                        child
                        for child in node.children
                        if child.type == "function_signature"
                    ),
                    node,
                )
            for child in node.children:
                if child.type in ("type_identifier", "built_in_type"):
                    return child.text.decode("utf-8", errors="replace")

        for child in node.children:
            if child.type in (
                "type",
                "return_type",
                "type_annotation",
                "return_type_definition",
            ):
                return child.text.decode("utf-8", errors="replace")
        return None

    def _get_return_type_python(self, node) -> str | None:
        """Extract return type for Python nodes."""
        for i, child in enumerate(node.children):
            if child.type == "->" and i + 1 < len(node.children):
                return node.children[i + 1].text.decode("utf-8", errors="replace")
        return None

    def _get_bases_python(self, node) -> list[str]:
        bases = []
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type in ("identifier", "attribute"):
                        bases.append(arg.text.decode("utf-8", errors="replace"))
                    elif arg.type == "subscript":
                        value = arg.child_by_field_name("value")
                        if value is not None:
                            bases.append(value.text.decode("utf-8", errors="replace"))
        return bases

    @staticmethod
    def _get_direct_type_names(node) -> list[str]:
        """Extract type names from a grammar wrapper without splitting paths."""
        atom_types = {
            "identifier",
            "member_expression",
            "nested_identifier",
            "nested_type_identifier",
            "qualified_identifier",
            "qualified_name",
            "scoped_type_identifier",
            "scoped_identifier",
            "simple_identifier",
            "type_identifier",
            "name",
        }

        def collect(current) -> list[str]:
            if current.type in atom_types:
                text = current.text.decode("utf-8", errors="replace").strip()
                text = re.sub(r"(?:<.*>|\[.*\])$", "", text).lstrip("\\")
                return [text] if text else []

            # Generic wrappers contain the base type followed by type
            # arguments. Only the base type is an edge target.
            if current.type in {"generic_name", "generic_type"}:
                for child in current.children:
                    names = collect(child)
                    if names:
                        return names[:1]
                return []

            if current.type in {
                "type_argument_list",
                "type_arguments",
                "type_parameter_list",
                "type_parameters",
                "trait_bounds",
            }:
                return []

            names: list[str] = []
            for child in current.children:
                names.extend(collect(child))
            return names

        return collect(node)

    def _get_bases_jvm_like(self, node) -> list[tuple[str, str]]:
        relationships: list[tuple[str, str]] = []
        for child in node.children:
            if child.type == "superclass":
                kind = "INHERITS"
            elif child.type == "super_interfaces":
                kind = "IMPLEMENTS"
            elif child.type == "extends_interfaces":
                kind = "INHERITS"
            elif child.type in ("extends_type", "implements_type"):
                kind = "IMPLEMENTS" if child.type == "implements_type" else "INHERITS"
            elif child.type == "type_identifier":
                kind = "INHERITS"
            elif child.type in ("supertype", "delegation_specifier"):
                kind = "INHERITS"
            else:
                continue

            names = self._get_direct_type_names(child)
            relationships.extend((kind, name) for name in names)
        return relationships

    def _get_bases_kotlin(
        self, node, declared_interfaces: set[str]
    ) -> list[tuple[str, str]]:
        relationships: list[tuple[str, str]] = []
        for child in node.children:
            if child.type == "delegation_specifier":
                for specifier in child.children:
                    names = self._get_direct_type_names(specifier)
                    if not names:
                        continue
                    if any(
                        grandchild.type == "interface" for grandchild in node.children
                    ):
                        kind = "INHERITS"
                    elif specifier.type == "constructor_invocation":
                        kind = "INHERITS"
                    elif specifier.type == "user_type":
                        kind = "IMPLEMENTS"
                    else:
                        kind = (
                            "IMPLEMENTS"
                            if names[0] in declared_interfaces
                            else "INHERITS"
                        )
                    relationships.extend((kind, name) for name in names)
        return relationships

    def _get_bases_cpp(self, node) -> list[str]:
        bases = []
        for child in node.children:
            if child.type == "base_class_clause":
                for sub in child.children:
                    if sub.type == "type_identifier":
                        bases.append(sub.text.decode("utf-8", errors="replace"))
        return bases

    def _get_bases_web(self, node) -> list[tuple[str, str]]:
        relationships: list[tuple[str, str]] = []

        def collect_heritage_clauses(current) -> None:
            if current.type in ("extends_clause", "implements_clause"):
                kind = (
                    "IMPLEMENTS" if current.type == "implements_clause" else "INHERITS"
                )
                for name in self._get_direct_type_names(current):
                    relationships.append((kind, name))
                return
            for child in current.children:
                collect_heritage_clauses(child)

        collect_heritage_clauses(node)
        return relationships

    def _get_bases_csharp(
        self, node, declared_interfaces: set[str]
    ) -> list[tuple[str, str]]:
        relationships: list[tuple[str, str]] = []
        for child in node.children:
            if child.type != "base_list":
                continue
            names = self._get_direct_type_names(child)
            for index, name in enumerate(names):
                if node.type == "interface_declaration":
                    kind = "INHERITS"
                elif node.type == "struct_declaration":
                    kind = "IMPLEMENTS"
                elif name in declared_interfaces or index > 0:
                    kind = "IMPLEMENTS"
                else:
                    kind = "INHERITS"
                relationships.append((kind, name))
        return relationships

    def _get_bases_php(self, node) -> list[tuple[str, str]]:
        relationships: list[tuple[str, str]] = []
        for child in node.children:
            if child.type == "base_clause":
                kind = "INHERITS"
            elif child.type == "class_interface_clause":
                kind = "IMPLEMENTS"
            else:
                continue
            relationships.extend(
                (kind, name) for name in self._get_direct_type_names(child)
            )
        return relationships

    def _get_name_rust_impl(self, node) -> str | None:
        target = node.child_by_field_name("type")
        if target is None:
            return None
        names = self._get_direct_type_names(target)
        if names:
            return self._short_type_name(names[0])
        return self._short_type_name(target.text.decode("utf-8", errors="replace"))

    def _get_bases_rust(self, node) -> list[tuple[str, str]]:
        trait = node.child_by_field_name("trait")
        if trait is None:
            return []
        names = self._get_direct_type_names(trait)
        if not names:
            text = trait.text.decode("utf-8", errors="replace")
            names = [text] if text else []
        return [("IMPLEMENTS", name) for name in names]

    def _get_bases_solidity(self, node) -> list[str]:
        bases = []
        for child in node.children:
            if child.type == "inheritance_specifier":
                for sub in child.children:
                    if sub.type == "user_defined_type":
                        for ident in sub.children:
                            if ident.type == "identifier":
                                bases.append(
                                    ident.text.decode("utf-8", errors="replace")
                                )
        return bases

    def _get_bases_go(self, node) -> list[str]:
        bases = []
        for child in node.children:
            if child.type == "type_spec":
                for sub in child.children:
                    if sub.type in ("struct_type", "interface_type"):
                        for field_node in sub.children:
                            if field_node.type == "field_declaration_list":
                                for f in field_node.children:
                                    if f.type == "type_identifier":
                                        bases.append(
                                            f.text.decode("utf-8", errors="replace")
                                        )
                                    elif f.type == "field_declaration" and not any(
                                        c.type == "field_identifier" for c in f.children
                                    ):
                                        for c in f.children:
                                            if c.type == "type_identifier":
                                                bases.append(
                                                    c.text.decode(
                                                        "utf-8", errors="replace"
                                                    )
                                                )
        return bases

    def _get_bases(
        self,
        node,
        language: str,
        source: bytes,
        *,
        python_abstract_contracts: set[str] | None = None,
        declared_interfaces: set[str] | None = None,
    ) -> list[tuple[str, str]]:
        """Extract base classes / implemented interfaces."""
        if language == "python":
            contracts = python_abstract_contracts or set()
            return [
                (
                    "IMPLEMENTS"
                    if self._short_type_name(base) in contracts
                    else "INHERITS",
                    base,
                )
                for base in self._get_bases_python(node)
            ]
        if language == "java":
            return self._get_bases_jvm_like(node)
        if language == "kotlin":
            return self._get_bases_kotlin(node, declared_interfaces or set())
        if language == "csharp":
            return self._get_bases_csharp(node, declared_interfaces or set())
        if language == "php":
            return self._get_bases_php(node)
        if language == "cpp":
            return [("INHERITS", base) for base in self._get_bases_cpp(node)]
        if language in ("typescript", "javascript", "tsx"):
            return self._get_bases_web(node)
        if language == "rust":
            return self._get_bases_rust(node)
        if language == "solidity":
            return [("INHERITS", base) for base in self._get_bases_solidity(node)]
        if language == "go":
            return [("INHERITS", base) for base in self._get_bases_go(node)]
        if language == "dart":
            return [
                ("INHERITS", sub.text.decode("utf-8", errors="replace"))
                for child in node.children
                if child.type in ("superclass", "interfaces")
                for sub in child.children
                if sub.type == "type_identifier"
            ]
        return []

    def _extract_import(self, node, language: str, source: bytes) -> list[str]:
        """Extract import targets as module/path strings."""
        text = node.text.decode("utf-8", errors="replace").strip()

        if language == "python":
            return self._extract_import_python(node)
        elif language in ("javascript", "typescript", "tsx"):
            return self._extract_import_javascript(node)
        elif language == "go":
            return self._extract_import_go(node)
        elif language == "rust":
            return self._extract_import_rust(text)
        elif language in ("c", "cpp"):
            return self._extract_import_c(node)
        elif language in ("java", "csharp"):
            return self._extract_import_java(text)
        elif language == "solidity":
            return self._extract_import_solidity(node)
        elif language == "ruby":
            return self._extract_import_ruby(text)
        else:
            return [text]

    def _extract_import_python(self, node) -> list[str]:
        imports = []
        # import x.y.z  or  from x.y import z
        if node.type == "import_from_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(child.text.decode("utf-8", errors="replace"))
                    break
        else:
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(child.text.decode("utf-8", errors="replace"))
        return imports

    def _extract_import_javascript(self, node) -> list[str]:
        imports = []
        # import ... from 'module'
        for child in node.children:
            if child.type == "string":
                val = child.text.decode("utf-8", errors="replace").strip("'\"")
                imports.append(val)
        return imports

    def _extract_import_go(self, node) -> list[str]:
        imports = []
        for child in node.children:
            if child.type == "import_spec_list":
                for spec in child.children:
                    if spec.type == "import_spec":
                        for s in spec.children:
                            if s.type == "interpreted_string_literal":
                                val = s.text.decode("utf-8", errors="replace")
                                imports.append(val.strip('"'))
            elif child.type == "import_spec":
                for s in child.children:
                    if s.type == "interpreted_string_literal":
                        val = s.text.decode("utf-8", errors="replace")
                        imports.append(val.strip('"'))
        return imports

    def _extract_import_rust(self, text: str) -> list[str]:
        # use crate::module::item
        return [text.replace("use ", "").rstrip(";").strip()]

    def _extract_import_c(self, node) -> list[str]:
        imports = []
        # #include <header> or #include "header"
        for child in node.children:
            if child.type in ("system_lib_string", "string_literal"):
                val = child.text.decode("utf-8", errors="replace").strip('<>"')
                imports.append(val)
        return imports

    def _extract_import_java(self, text: str) -> list[str]:
        imports = []
        # import/using package.Class
        parts = text.split()
        if len(parts) >= 2:
            imports.append(parts[-1].rstrip(";"))
        return imports

    def _extract_import_solidity(self, node) -> list[str]:
        imports = []
        # import "path/to/file.sol" or import {Symbol} from "path"
        for child in node.children:
            if child.type == "string":
                val = child.text.decode("utf-8", errors="replace").strip('"')
                if val:
                    imports.append(val)
        return imports

    def _extract_import_ruby(self, text: str) -> list[str]:
        imports = []
        # require 'module' or require_relative 'path'
        if "require" in text:
            match = re.search(r"""['"](.*?)['"]""", text)
            if match:
                imports.append(match.group(1))
        return imports

    @staticmethod
    def _collect_php_scopes(
        root,
    ) -> list[tuple[int, int, str, dict[tuple[str, str], str]]]:
        """Collect lexical namespaces and class/function use aliases once per file."""
        scopes = []
        namespace = ""
        start = 0
        statements = []

        def append_scope(end: int) -> None:
            aliases: dict[tuple[str, str], str] = {}
            for statement in statements:
                if statement.type != "namespace_use_declaration":
                    continue
                type_node = statement.child_by_field_name("type")
                default_kind = type_node.text.decode() if type_node else "class"
                group = statement.child_by_field_name("body")
                prefix = ""
                if group is not None:
                    prefix_node = next(
                        (
                            c
                            for c in statement.named_children
                            if c.type == "namespace_name"
                        ),
                        None,
                    )
                    if prefix_node is not None:
                        prefix = prefix_node.text.decode(
                            "utf-8", errors="replace"
                        ).strip("\\")
                clauses = (group or statement).named_children
                for clause in clauses:
                    if clause.type != "namespace_use_clause":
                        continue
                    alias = clause.child_by_field_name("alias")
                    clause_type = clause.child_by_field_name("type")
                    kind = clause_type.text.decode() if clause_type else default_kind
                    target = next(
                        (
                            c
                            for c in clause.named_children
                            if c != alias and c.type in {"name", "qualified_name"}
                        ),
                        None,
                    )
                    if target is None or kind not in {"class", "function"}:
                        continue
                    qualified = target.text.decode("utf-8", errors="replace").strip(
                        "\\"
                    )
                    if prefix:
                        qualified = f"{prefix}\\{qualified}"
                    local = (
                        alias.text.decode("utf-8", errors="replace")
                        if alias is not None
                        else qualified.rsplit("\\", 1)[-1]
                    )
                    aliases[(kind, local.lower())] = qualified.lower()
            scopes.append((start, end, namespace, aliases))

        for child in root.named_children:
            if child.type != "namespace_definition":
                statements.append(child)
                continue
            append_scope(child.start_byte)
            name = child.child_by_field_name("name")
            namespace = (
                name.text.decode("utf-8", errors="replace").lower() if name else ""
            )
            start = child.start_byte
            body = child.child_by_field_name("body")
            statements = list(body.named_children) if body is not None else []
            if body is not None:
                append_scope(child.end_byte)
                namespace = ""
                start = child.end_byte
                statements = []
        append_scope(root.end_byte)
        return scopes

    def _php_scope(self, offset: int) -> tuple[str, dict[tuple[str, str], str]]:
        for start, end, namespace, aliases in self._php_scopes:
            if start <= offset < end:
                return namespace, aliases
        return "", {}

    def _php_declared_symbol(self, node, name: str, parent: str | None) -> str:
        namespace, _aliases = self._php_scope(node.start_byte)
        symbol = f"{parent}::{name}" if parent else name
        return (f"{namespace}\\{symbol}" if namespace else symbol).lower()

    def _php_call_targets(
        self, node, name: str, enclosing_class: str | None
    ) -> list[str]:
        """Keep lexical PHP evidence; unknown dynamic receivers stay unresolved."""
        namespace, aliases = self._php_scope(node.start_byte)

        def qualify(value: str, kind: str) -> str:
            value = value.lower()
            if value.startswith("\\"):
                return value.lstrip("\\")
            if value.startswith("namespace\\"):
                value = value[len("namespace\\") :]
            else:
                first, separator, rest = value.partition("\\")
                imported = aliases.get((kind, first))
                if imported is not None:
                    return imported + (separator + rest if separator else "")
            return f"{namespace}\\{value}" if namespace else value

        if node.type == "function_call_expression":
            target = qualify(name, "function")
            candidates = [target]
            # PHP falls back to global functions only for unqualified calls
            # without a function-import alias, never for qualified names.
            if (
                namespace
                and "\\" not in name
                and ("function", name.lower()) not in aliases
            ):
                candidates.append(name.lower())
            return candidates
        receiver = node.child_by_field_name(
            "scope" if node.type == "scoped_call_expression" else "object"
        )
        if receiver is None:
            return []
        value = receiver.text.decode("utf-8", errors="replace")
        if value in {"$this", "self", "static"} and enclosing_class:
            owner = f"{namespace}\\{enclosing_class}" if namespace else enclosing_class
        elif node.type == "scoped_call_expression" and receiver.type in {
            "name",
            "qualified_name",
            "relative_name",
        }:
            owner = qualify(value, "class")
        else:
            return []
        return [f"{owner}::{name}".lower()]

    def _get_call_name(self, node, language: str, source: bytes) -> str | None:
        """Extract the function/method name being called."""
        if not node.children:
            return None
        if language == "php":
            name_node = node.child_by_field_name(
                "function" if node.type == "function_call_expression" else "name"
            )
            if name_node is not None and name_node.type in {
                "name",
                "qualified_name",
                "relative_name",
            }:
                return name_node.text.decode("utf-8", errors="replace")
            return None

        first = node.children[0]

        # Solidity wraps call targets in an 'expression' node – unwrap it
        if language == "solidity" and first.type == "expression" and first.children:
            first = first.children[0]

        # Simple call: func_name(args)
        if first.type == "identifier":
            return first.text.decode("utf-8", errors="replace")

        # Method call: obj.method(args)
        member_types = (
            "attribute",
            "member_expression",
            "field_expression",
            "selector_expression",
        )
        if first.type in member_types:
            # Get the rightmost identifier (the method name)
            for child in reversed(first.children):
                if child.type in (
                    "identifier",
                    "property_identifier",
                    "field_identifier",
                    "field_name",
                ):
                    return child.text.decode("utf-8", errors="replace")
            return first.text.decode("utf-8", errors="replace")

        # Scoped call (e.g., Rust path::func())
        if first.type in ("scoped_identifier", "qualified_name"):
            return first.text.decode("utf-8", errors="replace")

        return None
