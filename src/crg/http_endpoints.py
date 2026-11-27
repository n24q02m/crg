"""HTTP surface extraction: route declarations and HTTP client calls.

Route declarations become ``Endpoint`` nodes. Each one is contained by its
File node and, when the handler is defined in the same file, linked to it
with a ``ROUTES_TO`` edge. Client calls whose URL can be reduced to a path
are recorded on the calling Function (or the File node for module-level
calls) as ``extra["http_calls"]``. Router prefixes and router mounts are
recorded on the File node as ``extra["http_routers"]`` and
``extra["http_mounts"]``. The link pass in
:func:`crg.federation.link_http_endpoints` resolves mounts across files and
turns call records into ``CALLS_ENDPOINT`` edges once every file (and every
federated repo) has been parsed.

Supported route declarations:

* FastAPI: ``@app.get``/``@router.post``/``@app.api_route(methods=...)`` with
  ``APIRouter(prefix=...)`` and ``include_router(..., prefix=...)``.
* Flask: ``@app.route(..., methods=...)``, ``@bp.get`` with
  ``Blueprint(url_prefix=...)`` and ``register_blueprint(..., url_prefix=...)``.
* Express: ``app.get``/``router.post``/``app.all``/``app.route(p).get(h)`` with
  ``app.use(prefix, router)``.
* Go ``net/http``: ``http.HandleFunc``/``mux.Handle`` including Go 1.22
  ``"GET /path/{id}"`` patterns and gorilla-style ``.Methods(...)``.

Supported clients: ``httpx``/``requests`` (Python), ``fetch``/``axios``
(JavaScript and TypeScript) and ``net/http`` (Go).

The extractor never guesses. A route whose path is not a static string is
skipped. A client call whose method or URL cannot be resolved is kept as a
``dynamic`` record without a path, so the link pass can count it without
creating an edge.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .parser import EdgeInfo, NodeInfo

# A URL expression is flattened into parts: ``(True, text)`` for literal
# text and ``(False, source)`` for anything only known at runtime.
Part = tuple[bool, str]

HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}
)
ANY_METHOD = "*"
SUPPORTED_LANGUAGES = frozenset({"python", "javascript", "typescript", "tsx", "go"})

_ROUTE_VERBS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)
_CLIENT_VERBS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
_DYNAMIC_BASE_FACTOR = 0.8
_DYNAMIC_SEGMENT_FACTOR = 0.9
_MAX_RESOLVE_DEPTH = 6
_MAX_PARTS = 64
_MAX_ENDPOINTS_PER_FILE = 500
_MAX_CALLS_PER_NODE = 200

_TRIGGERS: dict[str, tuple[bytes, ...]] = {
    "python": (
        b"fastapi",
        b"flask",
        b"httpx",
        b"requests",
        b"apirouter",
        b"blueprint",
        b"testclient",
        b"include_router",
        b"register_blueprint",
    ),
    "javascript": (b"express", b"fetch", b"axios", b"router", b".use("),
    "go": (b"net/http", b"handlefunc", b".handle("),
}
_TRIGGERS["typescript"] = _TRIGGERS["javascript"]
_TRIGGERS["tsx"] = _TRIGGERS["javascript"]

_BRACE_PARAM_RE = re.compile(r"^\{\s*([A-Za-z_][\w-]*)?\s*(?:\.\.\.)?\s*(?::[^}]*)?\}$")
_ANGLE_PARAM_RE = re.compile(r"^<(?:[^:<>]+:)?([A-Za-z_]\w*)>$")
_COLON_PARAM_RE = re.compile(r"^:([A-Za-z_]\w*)(?:\([^)]*\))?\??$")
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):(//)?")
_GO_VERB_RE = re.compile(r"%(?:%|[-+# 0]*(?:\d+|\*)?(?:\.(?:\d+|\*)?)?[a-zA-Z])")
_INTERNAL_SUFFIXES = (
    ".local",
    ".internal",
    ".localhost",
    ".svc",
    ".lan",
    ".home.arpa",
    ".test",
    ".example",
    ".invalid",
)


# ---------------------------------------------------------------------------
# Path normalisation and matching
# ---------------------------------------------------------------------------


def _normalize_segment(segment: str) -> str | None:
    if segment == "{$}":
        return None
    match = _BRACE_PARAM_RE.match(segment)
    if match:
        return "{" + (match.group(1) or "") + "}"
    match = _ANGLE_PARAM_RE.match(segment) or _COLON_PARAM_RE.match(segment)
    if match:
        return "{" + match.group(1) + "}"
    return segment


def normalize_route_path(raw: str) -> str:
    """Return ``raw`` with one leading slash and ``{name}`` parameters.

    FastAPI/Starlette ``{id:int}``, Go ``{path...}``, Flask ``<int:id>`` and
    Express ``:id``/``:id?`` all become ``{id}``. Empty segments and the Go
    ``{$}`` end-of-path marker are dropped.
    """
    segments = []
    for segment in raw.strip().split("/"):
        if not segment:
            continue
        normalized = _normalize_segment(segment)
        if normalized is not None:
            segments.append(normalized)
    return "/" + "/".join(segments)


def path_key(path: str) -> str:
    """Erase parameter names: ``/users/{id}`` becomes ``/users/{}``."""
    segments = [
        "{}" if segment.startswith("{") and segment.endswith("}") else segment
        for segment in path.split("/")
        if segment
    ]
    return "/" + "/".join(segments)


def match_score(call_path: str, route_key: str) -> int | None:
    """Score how well a call path matches a route key.

    Both arguments use ``{}`` for parameters. The score is the number of
    literal route segments matched; ``None`` means no match. A parameter in
    the call never matches a literal route segment, because the value is not
    known.
    """
    call_segments = [s for s in call_path.split("/") if s]
    route_segments = [s for s in route_key.split("/") if s]
    if len(call_segments) != len(route_segments):
        return None
    score = 0
    for call_segment, route_segment in zip(call_segments, route_segments, strict=True):
        if route_segment == "{}":
            continue
        if call_segment != route_segment:
            return None
        score += 1
    return score


def is_internal_host(host: str) -> bool:
    """Return True for hosts that can belong to a service in the workspace.

    Single-label names (``users-svc``, ``localhost``), private and loopback
    addresses, and reserved internal suffixes count as internal. Any other
    dotted name (``api.github.com``) is treated as an external service and
    never linked.
    """
    name = host.strip().strip("[]").lower()
    if not name:
        return True
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return "." not in name or name.endswith(_INTERNAL_SUFFIXES)
    return address.is_private or address.is_loopback or address.is_link_local


def _merge_parts(parts: list[Part]) -> list[Part]:
    merged: list[Part] = []
    for is_literal, text in parts:
        if is_literal:
            if not text:
                continue
            if merged and merged[-1][0]:
                merged[-1] = (True, merged[-1][1] + text)
                continue
        merged.append((is_literal, text))
    return merged


def _hostname(authority: str) -> str:
    host = authority.rsplit("@", 1)[-1]
    if host.startswith("["):
        return host[1:].split("]", 1)[0].lower()
    return host.split(":", 1)[0].lower()


def _is_absolute(parts: list[Part]) -> bool:
    if not parts or not parts[0][0]:
        return False
    text = parts[0][1]
    return text.startswith("//") or bool(_SCHEME_RE.match(text))


def call_path_from_parts(parts: list[Part]) -> tuple[str | None, float, str | None]:
    """Reduce a flattened URL expression to ``(path_key, confidence, host)``.

    A runtime base in front of the path (``f"{BASE}/users"``) is stripped
    and lowers the confidence to 0.8. Each runtime value that fills a whole
    path segment becomes ``{}`` and multiplies the confidence by 0.9. The
    query string and fragment are dropped. Anything else that is only known
    at runtime makes the call unresolvable: the result is
    ``(None, 0.0, host)``.
    """
    merged = _merge_parts(parts)
    host: str | None = None
    rejected = (None, 0.0, None)
    if not merged:
        return rejected
    confidence = 1.0
    first_literal, first_text = merged[0]
    if first_literal and (first_text.startswith("//") or _SCHEME_RE.match(first_text)):
        scheme = _SCHEME_RE.match(first_text)
        if scheme is not None:
            if scheme.group(1).lower() not in ("http", "https") or not scheme.group(2):
                return rejected
            after = first_text[scheme.end() :]
        else:
            after = first_text[2:]
        cut = len(after)
        for marker in "/?#":
            index = after.find(marker)
            if index != -1:
                cut = min(cut, index)
        authority, remainder = after[:cut], after[cut:]
        if authority:
            host = _hostname(authority)
            if remainder[:1] in ("?", "#"):
                remainder = "/" + remainder
            rest = ([(True, remainder)] if remainder else []) + merged[1:]
            if not rest:
                return "/", 1.0, host
        else:
            if remainder or len(merged) < 3 or merged[1][0]:
                return rejected
            rest = merged[2:]
    elif first_literal:
        rest = merged
    else:
        confidence *= _DYNAMIC_BASE_FACTOR
        rest = merged[1:]
    if not rest or not rest[0][0] or not rest[0][1].startswith("/"):
        return None, 0.0, host
    text = ""
    for index, (is_literal, value) in enumerate(rest):
        if is_literal:
            stops = [i for i in (value.find("?"), value.find("#")) if i != -1]
            if stops:
                text += value[: min(stops)]
                break
            text += value
            continue
        following = rest[index + 1] if index + 1 < len(rest) else None
        if not text.endswith("/"):
            return None, 0.0, host
        if following is not None and following[1][:1] not in ("/", "?", "#"):
            return None, 0.0, host
        text += "{}"
        confidence *= _DYNAMIC_SEGMENT_FACTOR
    return path_key(normalize_route_path(text)), round(confidence, 4), host


def _join_base(base: list[Part], parts: list[Part]) -> list[Part] | None:
    """Join a client base URL and a relative call URL like httpx and axios do."""
    merged = _merge_parts(parts)
    if not merged or not merged[0][0]:
        return None
    first = merged[0][1].lstrip("/")
    return [*base, (True, "/"), (True, first), *merged[1:]]


# ---------------------------------------------------------------------------
# Shared extractor machinery
# ---------------------------------------------------------------------------


def _text(node: Any) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _line(node: Any) -> int:
    return node.start_point[0] + 1


def _walk(root: Any) -> Iterator[Any]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def _key(node: Any) -> tuple[int, int]:
    return node.start_byte, node.end_byte


@dataclass
class _Router:
    name: str
    kind: str  # "app" or "router"
    framework: str
    prefix: str | None


class _Extractor:
    scope_types: frozenset[str] = frozenset()

    def __init__(
        self,
        root: Any,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        import_map: dict[str, str],
        resolve_module: Callable[[str, str, str], str | None],
    ) -> None:
        self.root = root
        self.language = language
        self.file_path = file_path
        self.nodes = nodes
        self.edges = edges
        self.import_map = import_map
        self.resolve_module = resolve_module
        self.file_node = nodes[0]
        self.routers: dict[str, _Router] = {}
        self.mounts: list[dict[str, Any]] = []
        self.bindings: dict[tuple[int, int, str], list[Any]] = {}
        self._endpoint_names: set[str] = set()
        self._top_level: dict[str, list[str]] = {}
        self._members: dict[str, list[str]] = {}
        self._owners: list[tuple[int, int, int, NodeInfo]] = []
        for node in nodes:
            if node.kind not in ("Function", "Test"):
                continue
            if node.parent_name:
                qualified = f"{file_path}::{node.parent_name}.{node.name}"
                self._members.setdefault(node.name, []).append(qualified)
            else:
                qualified = f"{file_path}::{node.name}"
                self._top_level.setdefault(node.name, []).append(qualified)
            if node.line_start is not None and node.line_end is not None:
                span = node.line_end - node.line_start
                self._owners.append((span, node.line_start, node.line_end, node))
        self._owners.sort(key=lambda item: item[0])

    # -- scopes and bindings ------------------------------------------------

    def _scope_of(self, node: Any) -> Any:
        current = node.parent
        while current is not None:
            if current.type in self.scope_types:
                return current
            current = current.parent
        return self.root

    def _bind(self, scope: Any, name: str, value: Any) -> None:
        self.bindings.setdefault((*_key(scope), name), []).append(value)

    def _bind_here(self, node: Any, name: str, value: Any) -> None:
        self._bind(self._scope_of(node), name, value)

    def _bind_params(self, function: Any, field: str = "parameters") -> None:
        params = function.child_by_field_name(field)
        if params is None:
            return
        if params.type == "identifier":
            self._bind(function, _text(params), None)
            return
        for node in _walk(params):
            if node.type == "identifier":
                self._bind(function, _text(node), None)

    def _lookup(self, name: str, node: Any) -> Any:
        scope = self._scope_of(node)
        while True:
            values = self.bindings.get((*_key(scope), name))
            if values is not None:
                return values[0] if len(values) == 1 else None
            if scope.parent is None:
                return None
            scope = self._scope_of(scope)

    # -- URL parts ----------------------------------------------------------

    def _parts(self, node: Any, depth: int) -> list[Part]:
        raise NotImplementedError  # pragma: no cover - every extractor overrides it

    def _resolve_name(self, node: Any, depth: int) -> list[Part]:
        name = _text(node)
        if depth >= _MAX_RESOLVE_DEPTH:
            return [(False, name)]
        value = self._lookup(name, node)
        if value is None:
            return [(False, name)]
        return self._parts(value, depth + 1)

    def parts(self, node: Any) -> list[Part] | None:
        if node is None:
            return None
        parts = _merge_parts(self._parts(node, 0))
        if len(parts) > _MAX_PARTS:
            return [(False, _text(node))]
        return parts

    def static(self, node: Any) -> str | None:
        parts = self.parts(node)
        if parts is None:
            return None
        if not parts:
            return ""
        if len(parts) == 1 and parts[0][0]:
            return parts[0][1]
        return None

    def static_method(self, node: Any) -> str | None:
        value = self.static(node)
        if value is None:
            return None
        method = value.strip().upper()
        return method if method in HTTP_METHODS else None

    # -- handlers and owners ------------------------------------------------

    def _function_qn(self, name: str) -> str | None:
        top = self._top_level.get(name, [])
        if len(top) == 1:
            return top[0]
        return None

    def _member_qn(self, name: str) -> str | None:
        members = self._members.get(name, [])
        if len(members) == 1:
            return members[0]
        return None

    def _owner(self, line: int) -> NodeInfo:
        for _span, start, end, node in self._owners:
            if start <= line <= end:
                return node
        return self.file_node

    # -- emitters -----------------------------------------------------------

    def add_router(self, router: _Router) -> None:
        self.routers.setdefault(router.name, router)

    def add_endpoint(
        self,
        *,
        router: _Router,
        method: str,
        raw_path: str,
        line: int,
        handler: str | None,
        handler_qn: str | None,
        handler_ref: dict[str, Any] | None = None,
        path: str | None = None,
    ) -> None:
        if path is None:
            if router.prefix is None:
                return
            path = normalize_route_path(f"{router.prefix}/{raw_path}")
        name = f"{method} {path}"
        if (
            name in self._endpoint_names
            or len(self._endpoint_names) >= _MAX_ENDPOINTS_PER_FILE
        ):
            return
        self._endpoint_names.add(name)
        extra: dict[str, Any] = {
            "http_method": method,
            "path": path,
            "raw_path": raw_path,
            "framework": router.framework,
            "router": router.name,
            "router_kind": router.kind,
            "handler": handler,
        }
        if handler_qn is None and handler_ref is not None:
            extra["handler_ref"] = handler_ref
        qualified = f"{self.file_path}::{name}"
        self.nodes.append(
            NodeInfo(
                kind="Endpoint",
                name=name,
                file_path=self.file_path,
                line_start=line,
                line_end=line,
                language=self.language,
                extra=extra,
            )
        )
        self.edges.append(
            EdgeInfo(
                kind="CONTAINS",
                source=self.file_path,
                target=qualified,
                file_path=self.file_path,
                line=line,
            )
        )
        if handler_qn is not None:
            self.edges.append(
                EdgeInfo(
                    kind="ROUTES_TO",
                    source=qualified,
                    target=handler_qn,
                    file_path=self.file_path,
                    line=line,
                )
            )

    def add_mount(
        self,
        *,
        parent: str,
        prefix: str | None,
        child: str | None,
        child_file: str | None,
        line: int,
        replaces_prefix: bool = False,
    ) -> None:
        mount: dict[str, Any] = {
            "parent": parent,
            "prefix": prefix,
            "child": child,
            "child_file": child_file,
            "line": line,
        }
        if replaces_prefix:
            mount["replaces_prefix"] = True
        self.mounts.append(mount)

    def add_call(
        self,
        node: Any,
        method: str | None,
        url: Any,
        client: str,
        base: list[Part] | None = None,
    ) -> None:
        line = _line(node)
        owner = self._owner(line)
        calls = owner.extra.setdefault("http_calls", [])
        if len(calls) >= _MAX_CALLS_PER_NODE:
            return
        record: dict[str, Any] = {"method": method, "line": line, "client": client}
        parts = self.parts(url)
        path = None
        confidence = 0.0
        host = None
        if method is not None and parts is not None:
            if base is not None and not _is_absolute(parts):
                parts = _join_base(base, parts)
            if parts is not None:
                path, confidence, host = call_path_from_parts(parts)
        if path is None:
            record["dynamic"] = True
            record["confidence"] = 0.0
        else:
            record.update(path=path, confidence=confidence, host=host)
        calls.append(record)

    def finish(self) -> None:
        if self.mounts:
            self.file_node.extra["http_mounts"] = self.mounts
        if self.routers:
            self.file_node.extra["http_routers"] = {
                name: {
                    "kind": router.kind,
                    "framework": router.framework,
                    "prefix": router.prefix,
                }
                for name, router in self.routers.items()
            }


# ---------------------------------------------------------------------------
# Python: FastAPI, Flask, httpx, requests
# ---------------------------------------------------------------------------


def _py_args(call: Any) -> tuple[list[Any], dict[str, Any]]:
    arguments = call.child_by_field_name("arguments")
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    if arguments is None or arguments.type != "argument_list":
        return positional, keywords
    for child in arguments.named_children:
        if child.type == "keyword_argument":
            name = _text(child.child_by_field_name("name"))
            keywords[name] = child.child_by_field_name("value")
        elif child.type != "comment":
            positional.append(child)
    return positional, keywords


class _PythonExtractor(_Extractor):
    scope_types = frozenset({"function_definition", "lambda"})

    def run(self) -> None:
        self.module_imports: dict[str, str] = {}
        self.from_imports: dict[str, tuple[str, str]] = {}
        self.client_vars: dict[str, tuple[str, list[Part] | None]] = {}
        self.client_modules: dict[str, str] = {}
        assignments: list[tuple[str, Any]] = []
        decorated: list[Any] = []
        calls: list[Any] = []
        for node in _walk(self.root):
            kind = node.type
            if kind == "assignment":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left is not None and left.type == "identifier":
                    self._bind_here(node, _text(left), right)
                    if right is not None:
                        assignments.append((_text(left), right))
                elif left is not None:
                    self._bind_targets(node, left)
            elif kind in ("augmented_assignment", "for_statement"):
                target = node.child_by_field_name("left")
                if target is not None:
                    self._bind_targets(node, target)
            elif kind in self.scope_types:
                self._bind_params(node)
            elif kind == "import_statement":
                self._import(node)
            elif kind == "import_from_statement":
                self._import_from(node)
            elif kind == "decorated_definition":
                decorated.append(node)
            elif kind == "call":
                calls.append(node)
            elif kind == "with_item":
                self._with_item(node)
        self.client_modules = {
            local: module
            for local, module in self.module_imports.items()
            if module in ("httpx", "requests")
        }
        for name, value in assignments:
            if value.type == "call":
                self._classify_constructor(name, value)
        for node in decorated:
            self._route(node)
        for node in calls:
            if not self._mount(node):
                self._client_call(node)
        self.finish()

    def _bind_targets(self, node: Any, target: Any) -> None:
        for child in _walk(target):
            if child.type == "identifier":
                self._bind_here(node, _text(child), None)

    def _import(self, node: Any) -> None:
        for name in node.children_by_field_name("name"):
            if name.type == "aliased_import":
                module = _text(name.child_by_field_name("name"))
                self.module_imports[_text(name.child_by_field_name("alias"))] = module
            else:
                module = _text(name)
                self.module_imports[module.split(".", 1)[0]] = module

    def _import_from(self, node: Any) -> None:
        module = _text(node.child_by_field_name("module_name"))
        for name in node.children_by_field_name("name"):
            if name.type == "aliased_import":
                original = _text(name.child_by_field_name("name"))
                local = _text(name.child_by_field_name("alias"))
            else:
                original = local = _text(name)
            self.from_imports[local] = (module, original)

    def _module_file(self, module: str) -> str | None:
        if not module.startswith("."):
            return self.resolve_module(module, self.file_path, "python")
        level = len(module) - len(module.lstrip("."))
        rest = module[level:]
        base = Path(self.file_path).parent
        for _ in range(level - 1):
            base = base.parent
        if rest:
            target = base.joinpath(*rest.split("."))
            candidates = [target.with_name(target.name + ".py"), target / "__init__.py"]
        else:
            candidates = [base / "__init__.py"]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate.resolve())
        return None

    def _callee(self, call: Any) -> tuple[str, str | None]:
        """Return ``(name, module)`` for ``Name(...)`` or ``module.Name(...)``."""
        function = call.child_by_field_name("function")
        kind = function.type if function is not None else ""
        if kind == "identifier":
            name = _text(function)
            imported = self.from_imports.get(name)
            return name, imported[0] if imported else None
        if kind == "attribute":
            obj = function.child_by_field_name("object")
            name = _text(function.child_by_field_name("attribute"))
            if obj is not None and obj.type == "identifier":
                local = _text(obj)
                return name, self.module_imports.get(local, local)
            return name, None
        return "", None

    def _client_constructor(self, call: Any) -> tuple[str, list[Part] | None] | None:
        name, module = self._callee(call)
        root = (module or "").split(".", 1)[0]
        if name in ("Client", "AsyncClient") and root == "httpx":
            client = "httpx"
        elif name in ("Session", "session") and root == "requests":
            client = "requests"
        elif name == "TestClient":
            client = "testclient"
        else:
            return None
        _positional, keywords = _py_args(call)
        base_node = keywords.get("base_url")
        return client, (self.parts(base_node) if base_node is not None else None)

    def _classify_constructor(self, name: str, call: Any) -> None:
        callee, _module = self._callee(call)
        _positional, keywords = _py_args(call)
        if callee in ("FastAPI", "Flask"):
            framework = "fastapi" if callee == "FastAPI" else "flask"
            self.add_router(_Router(name, "app", framework, ""))
            return
        if callee in ("APIRouter", "Blueprint"):
            framework = "fastapi" if callee == "APIRouter" else "flask"
            prefix_node = keywords.get(
                "prefix" if framework == "fastapi" else "url_prefix"
            )
            prefix = "" if prefix_node is None else self.static(prefix_node)
            self.add_router(_Router(name, "router", framework, prefix))
            return
        client = self._client_constructor(call)
        if client is not None:
            self.client_vars[name] = client

    def _with_item(self, node: Any) -> None:
        value = node.child_by_field_name("value")
        if value is None or value.type != "as_pattern":
            return
        call = value.named_children[0] if value.named_children else None
        alias = value.child_by_field_name("alias")
        if call is None or alias is None or call.type != "call":
            return
        name = _text(alias).strip()
        self._bind_here(node, name, None)
        client = self._client_constructor(call)
        if client is not None:
            self.client_vars[name] = client

    def _qualify_def(self, definition: Any, name: str) -> str | None:
        current = definition.parent
        while current is not None:
            if current.type == "class_definition":
                owner = _text(current.child_by_field_name("name"))
                qualified = f"{self.file_path}::{owner}.{name}"
                return qualified if qualified in self._members.get(name, []) else None
            if current.type == "function_definition":
                return None
            current = current.parent
        return self._function_qn(name)

    def _route_methods(
        self, router: _Router, verb: str, keywords: dict[str, Any]
    ) -> list[str]:
        if verb in _ROUTE_VERBS:
            return [verb.upper()]
        generic = "api_route" if router.framework == "fastapi" else "route"
        if verb != generic:
            return []
        methods_node = keywords.get("methods")
        if methods_node is None:
            return ["GET"]
        if methods_node.type not in ("list", "tuple", "set"):
            return []
        methods = []
        for item in methods_node.named_children:
            method = self.static_method(item)
            if method is None:
                return []
            methods.append(method)
        return methods

    def _route(self, decorated: Any) -> None:
        definition = decorated.child_by_field_name("definition")
        if definition is None or definition.type != "function_definition":
            return
        handler = _text(definition.child_by_field_name("name"))
        handler_qn = self._qualify_def(definition, handler)
        for decorator in decorated.children:
            if decorator.type != "decorator" or not decorator.named_children:
                continue
            call = decorator.named_children[0]
            function = (
                call.child_by_field_name("function") if call.type == "call" else None
            )
            if function is None or function.type != "attribute":
                continue
            obj = function.child_by_field_name("object")
            router = self.routers.get(_text(obj)) if obj.type == "identifier" else None
            if router is None:
                continue
            positional, keywords = _py_args(call)
            verb = _text(function.child_by_field_name("attribute"))
            methods = self._route_methods(router, verb, keywords)
            path_node = (
                positional[0]
                if positional
                else keywords.get("path", keywords.get("rule"))
            )
            raw = self.static(path_node)
            if not methods or raw is None or (raw and not raw.startswith("/")):
                continue
            for method in methods:
                self.add_endpoint(
                    router=router,
                    method=method,
                    raw_path=raw,
                    line=_line(decorator),
                    handler=handler,
                    handler_qn=handler_qn,
                )

    def _child(self, node: Any) -> tuple[str, str | None] | None:
        """Resolve a mounted router expression to ``(name, file or None)``."""
        if node.type == "identifier":
            name = _text(node)
            if name in self.routers:
                return name, None
            imported = self.from_imports.get(name)
            if imported is None:
                return None
            module_file = self._module_file(imported[0])
            return (imported[1], module_file) if module_file else None
        if node.type != "attribute":
            return None
        obj = node.child_by_field_name("object")
        attr = _text(node.child_by_field_name("attribute"))
        if obj is None or obj.type != "identifier":
            return None
        local = _text(obj)
        if local in self.from_imports:
            module, original = self.from_imports[local]
            joiner = "" if module.endswith(".") else "."
            module_file = self._module_file(f"{module}{joiner}{original}")
        elif local in self.module_imports:
            module_file = self._module_file(self.module_imports[local])
        else:
            return None
        return (attr, module_file) if module_file else None

    def _mount(self, call: Any) -> bool:
        function = call.child_by_field_name("function")
        if function is None or function.type != "attribute":
            return False
        verb = _text(function.child_by_field_name("attribute"))
        if verb not in ("include_router", "register_blueprint"):
            return False
        obj = function.child_by_field_name("object")
        positional, keywords = _py_args(call)
        child_node = (
            positional[0]
            if positional
            else keywords.get("router", keywords.get("blueprint"))
        )
        child = self._child(child_node) if child_node is not None else None
        if obj is None or obj.type != "identifier" or child is None:
            return True
        prefix_key = "prefix" if verb == "include_router" else "url_prefix"
        prefix_node = keywords.get(prefix_key)
        self.add_mount(
            parent=_text(obj),
            prefix="" if prefix_node is None else self.static(prefix_node),
            child=child[0],
            child_file=child[1],
            line=_line(call),
            replaces_prefix=verb == "register_blueprint" and prefix_node is not None,
        )
        return True

    def _client_call(self, call: Any) -> None:
        function = call.child_by_field_name("function")
        if function is None or function.type != "attribute":
            return
        obj = function.child_by_field_name("object")
        if obj is None or obj.type != "identifier":
            return
        name = _text(obj)
        base: list[Part] | None = None
        if name in self.client_modules:
            client = self.client_modules[name]
        elif name in self.client_vars:
            client, base = self.client_vars[name]
        else:
            return
        verb = _text(function.child_by_field_name("attribute"))
        positional, keywords = _py_args(call)
        if verb in _CLIENT_VERBS:
            method: str | None = verb.upper()
            url = positional[0] if positional else keywords.get("url")
        elif verb in ("request", "stream"):
            method_node = positional[0] if positional else keywords.get("method")
            method = self.static_method(method_node)
            url = positional[1] if len(positional) > 1 else keywords.get("url")
        else:
            return
        self.add_call(call, method, url, client, base)

    def _parts(self, node: Any, depth: int) -> list[Part]:
        kind = node.type
        if kind == "string":
            out: list[Part] = []
            for child in node.children:
                if child.type in ("string_start", "string_end"):
                    continue
                if child.type == "interpolation":
                    # An interpolation without an expression stays unknown.
                    expression = child.child_by_field_name("expression")
                    inner = expression if expression is not None else child
                    out.extend(self._parts(inner, depth + 1))
                else:
                    out.append((True, _text(child)))
            return out
        if kind == "concatenated_string":
            out = []
            for child in node.named_children:
                out.extend(self._parts(child, depth + 1))
            return out
        if kind == "binary_operator":
            operator = _text(node.child_by_field_name("operator"))
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if operator == "+" and left is not None and right is not None:
                return self._parts(left, depth + 1) + self._parts(right, depth + 1)
        if kind == "parenthesized_expression" and node.named_children:
            return self._parts(node.named_children[0], depth + 1)
        if kind == "identifier":
            return self._resolve_name(node, depth)
        return [(False, _text(node))]


# ---------------------------------------------------------------------------
# JavaScript / TypeScript: Express, fetch, axios
# ---------------------------------------------------------------------------

_JS_STRINGS = frozenset({"string", "template_string"})
_JS_WRAPPERS = frozenset(
    {"as_expression", "satisfies_expression", "non_null_expression"}
)


def _js_args(call: Any) -> list[Any]:
    arguments = call.child_by_field_name("arguments")
    children = arguments.named_children if arguments is not None else []
    return [child for child in children if child.type != "comment"]


def _js_object(node: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for child in node.named_children:
        if child.type == "pair":
            key = child.child_by_field_name("key")
            name = _text(key)
            if key is not None and key.type == "string":
                name = name[1:-1]
            props[name] = child.child_by_field_name("value")
        elif child.type == "shorthand_property_identifier":
            props[_text(child)] = child
    return props


class _JsExtractor(_Extractor):
    scope_types = frozenset(
        {
            "function_declaration",
            "function_expression",
            "function",
            "arrow_function",
            "method_definition",
            "generator_function_declaration",
            "generator_function",
        }
    )

    def run(self) -> None:
        # local name -> (module specifier, exported name or None for default)
        self.modules: dict[str, tuple[str, str | None]] = {}
        self.express: set[str] = set()
        self.router_factories: set[str] = set()
        self.axios: set[str] = {"axios"}
        self.axios_instances: dict[str, list[Part] | None] = {}
        declarators: list[tuple[str, Any]] = []
        calls: list[Any] = []
        for node in _walk(self.root):
            kind = node.type
            if kind == "variable_declarator":
                self._declarator(node, declarators)
            elif kind == "assignment_expression":
                left = node.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    self._bind_here(
                        node, _text(left), node.child_by_field_name("right")
                    )
            elif kind == "augmented_assignment_expression":
                left = node.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    self._bind_here(node, _text(left), None)
            elif kind in self.scope_types:
                self._bind_params(node)
                self._bind_params(node, "parameter")
            elif kind == "import_statement":
                self._import(node)
            elif kind == "call_expression":
                calls.append(node)
        for name, value in declarators:
            self._classify(name, value)
        for call in calls:
            if not (self._route(call) or self._mount(call)):
                self._client_call(call)
        self.finish()

    def _import(self, node: Any) -> None:
        source = node.child_by_field_name("source")
        module = _text(source)[1:-1]
        for clause in node.named_children:
            if clause.type != "import_clause":
                continue
            for child in clause.named_children:
                if child.type == "identifier":
                    self._module_binding(_text(child), module, None)
                elif child.type == "namespace_import":
                    for ident in child.named_children:
                        self._module_binding(_text(ident), module, None)
                elif child.type == "named_imports":
                    for spec in child.named_children:
                        if spec.type != "import_specifier":
                            continue
                        original = _text(spec.child_by_field_name("name"))
                        alias = spec.child_by_field_name("alias")
                        local = _text(alias) if alias is not None else original
                        self._module_binding(local, module, original)

    def _module_binding(self, local: str, module: str, original: str | None) -> None:
        self.modules[local] = (module, original)
        if module == "express":
            if original is None:
                self.express.add(local)
            elif original == "Router":
                self.router_factories.add(local)
        elif module == "axios" and original is None:
            self.axios.add(local)

    def _require(self, value: Any) -> str | None:
        if value is None or value.type != "call_expression":
            return None
        function = value.child_by_field_name("function")
        args = _js_args(value)
        if _text(function) != "require" or len(args) != 1:
            return None
        if args[0].type != "string":
            return None
        return _text(args[0])[1:-1]

    def _declarator(self, node: Any, declarators: list[tuple[str, Any]]) -> None:
        name = node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        module = self._require(value)
        if name.type == "identifier":
            local = _text(name)
            self._bind_here(node, local, value)
            if module is not None:
                self._module_binding(local, module, None)
            elif value is not None:
                declarators.append((local, value))
            return
        for child in name.named_children:
            if child.type == "shorthand_property_identifier_pattern":
                original = local = _text(child)
            elif child.type == "pair_pattern":
                original = _text(child.child_by_field_name("key"))
                local = _text(child.child_by_field_name("value"))
            else:
                continue
            self._bind_here(node, local, None)
            if module is not None:
                self._module_binding(local, module, original)

    def _classify(self, name: str, value: Any) -> None:
        if value.type != "call_expression":
            return
        function = value.child_by_field_name("function")
        kind = function.type if function is not None else ""
        if kind == "identifier":
            callee = _text(function)
            if callee in self.express:
                self.add_router(_Router(name, "app", "express", ""))
            elif callee in self.router_factories:
                self.add_router(_Router(name, "router", "express", ""))
            return
        if kind != "member_expression":
            return
        obj = function.child_by_field_name("object")
        prop = _text(function.child_by_field_name("property"))
        owner = _text(obj)
        if prop == "Router" and owner in self.express:
            self.add_router(_Router(name, "router", "express", ""))
        elif prop == "create" and owner in self.axios:
            args = _js_args(value)
            base = None
            if args and args[0].type == "object":
                base_node = _js_object(args[0]).get("baseURL")
                base = self.parts(base_node) if base_node is not None else None
            self.axios_instances[name] = base

    def _handler(self, node: Any) -> tuple[str | None, str | None, dict | None]:
        """Return ``(handler name, same-file qualified name, cross-file ref)``."""
        if node.type == "identifier":
            name = _text(node)
            qualified = self._function_qn(name)
            if qualified is None and name in self.modules:
                module, original = self.modules[name]
                return (
                    name,
                    None,
                    {"name": original or name, "file": self._file(module)},
                )
            return name, qualified, None
        if node.type == "member_expression":
            obj = node.child_by_field_name("object")
            name = _text(node.child_by_field_name("property"))
            owner = _text(obj)
            if owner in self.modules:
                module = self.modules[owner][0]
                return name, None, {"name": name, "file": self._file(module)}
            qualified = self._member_qn(name)
            return name, qualified, None if qualified else {"name": name, "file": None}
        return None, None, None

    def _file(self, module: str) -> str | None:
        if not module.startswith("."):
            return None
        return self.resolve_module(module, self.file_path, self.language)

    def _route_base(self, node: Any) -> tuple[_Router, Any] | None:
        """Follow ``app.route(path).get(h).post(h)`` back to ``app.route(path)``."""
        for _ in range(16):
            if node.type != "call_expression":
                return None
            function = node.child_by_field_name("function")
            if function is None or function.type != "member_expression":
                return None
            prop = _text(function.child_by_field_name("property"))
            obj = function.child_by_field_name("object")
            if prop == "route":
                router = (
                    self.routers.get(_text(obj)) if obj.type == "identifier" else None
                )
                args = _js_args(node)
                return (router, args[0]) if router is not None and args else None
            if prop not in _ROUTE_VERBS and prop != "all":
                return None
            node = obj
        return None

    def _route(self, call: Any) -> bool:
        function = call.child_by_field_name("function")
        if function is None or function.type != "member_expression":
            return False
        prop_node = function.child_by_field_name("property")
        prop = _text(prop_node)
        if prop not in _ROUTE_VERBS and prop != "all":
            return False
        obj = function.child_by_field_name("object")
        args = _js_args(call)
        if obj.type == "identifier":
            router = self.routers.get(_text(obj))
            if router is None or len(args) < 2:
                return router is not None
            path_node, handlers = args[0], args[1:]
        else:
            base = self._route_base(obj)
            if base is None:
                return False
            router, path_node = base
            handlers = args
        raw = self.static(path_node)
        if raw is None or not raw.startswith("/") or not handlers:
            return True
        handler, handler_qn, handler_ref = self._handler(handlers[-1])
        self.add_endpoint(
            router=router,
            method=ANY_METHOD if prop == "all" else prop.upper(),
            raw_path=raw,
            line=_line(prop_node),
            handler=handler,
            handler_qn=handler_qn,
            handler_ref=handler_ref,
        )
        return True

    def _child(self, node: Any) -> tuple[str | None, str | None] | None:
        if node.type == "identifier":
            name = _text(node)
            if name in self.routers:
                return name, None
            if name in self.modules:
                module, original = self.modules[name]
                module_file = self._file(module)
                return (original, module_file) if module_file else None
            return None
        module = self._require(node)
        module_file = self._file(module) if module is not None else None
        return (None, module_file) if module_file else None

    def _mount(self, call: Any) -> bool:
        function = call.child_by_field_name("function")
        if function is None or function.type != "member_expression":
            return False
        if _text(function.child_by_field_name("property")) != "use":
            return False
        obj = function.child_by_field_name("object")
        if obj.type != "identifier" or _text(obj) not in self.routers:
            return False
        args = _js_args(call)
        prefix: str | None = ""
        if args and args[0].type in _JS_STRINGS:
            prefix = self.static(args[0])
            args = args[1:]
        for child_node in reversed(args):
            child = self._child(child_node)
            if child is not None:
                self.add_mount(
                    parent=_text(obj),
                    prefix=prefix,
                    child=child[0],
                    child_file=child[1],
                    line=_line(call),
                )
                break
        return True

    def _object_arg(self, node: Any) -> dict[str, Any] | None:
        """Return the properties of an object literal (or a name bound to one)."""
        if node.type == "identifier":
            node = self._lookup(_text(node), node)
            if node is None:
                return None
        if node.type != "object":
            return None
        return _js_object(node)

    def _config_method(self, props: dict[str, Any] | None) -> str | None:
        if props is None:
            return None
        method_node = props.get("method")
        if method_node is None:
            return "GET"
        if method_node.type == "shorthand_property_identifier":
            return None
        return self.static_method(method_node)

    def _client_call(self, call: Any) -> None:
        function = call.child_by_field_name("function")
        if function.type == "await_expression" and function.named_children:
            # The TypeScript grammar parses ``await axios.get<T>(url)`` as a
            # call whose function is ``await axios.get``.
            function = function.named_children[-1]
        args = _js_args(call)
        if function.type == "identifier":
            name = _text(function)
            if name == "fetch":
                self._fetch(call, args)
            elif name in self.axios or name in self.axios_instances:
                self._axios_config(call, args, self.axios_instances.get(name))
            return
        if function.type != "member_expression":
            return
        obj = function.child_by_field_name("object")
        prop = _text(function.child_by_field_name("property"))
        owner = _text(obj)
        if prop == "fetch" and owner in ("window", "globalThis", "self"):
            self._fetch(call, args)
            return
        if owner not in self.axios and owner not in self.axios_instances:
            return
        base = self.axios_instances.get(owner)
        if prop in _CLIENT_VERBS:
            self.add_call(call, prop.upper(), args[0] if args else None, "axios", base)
        elif prop == "request":
            self._axios_config(call, args, base)

    def _fetch(self, call: Any, args: list[Any]) -> None:
        method: str | None = "GET"
        if len(args) > 1:
            method = self._config_method(self._object_arg(args[1]))
        self.add_call(call, method, args[0] if args else None, "fetch")

    def _axios_config(
        self, call: Any, args: list[Any], base: list[Part] | None
    ) -> None:
        if not args:
            return
        props = self._object_arg(args[0]) if args[0].type == "object" else None
        if props is not None:
            url = props.get("url")
            base_node = props.get("baseURL")
        else:
            url = args[0]
            props = self._object_arg(args[1]) if len(args) > 1 else {}
            base_node = props.get("baseURL") if props else None
        if base_node is not None:
            base = self.parts(base_node)
        self.add_call(call, self._config_method(props), url, "axios", base)

    def _parts(self, node: Any, depth: int) -> list[Part]:
        kind = node.type
        if kind == "string":
            return [(True, _text(node)[1:-1])]
        if kind == "template_string":
            out: list[Part] = []
            for child in node.named_children:
                if child.type == "template_substitution":
                    # An empty substitution stays unknown.
                    inner = child.named_children
                    out.extend(self._parts(inner[0] if inner else child, depth + 1))
                else:
                    out.append((True, _text(child)))
            return out
        if kind == "binary_expression":
            operator = _text(node.child_by_field_name("operator"))
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if operator == "+" and left is not None and right is not None:
                return self._parts(left, depth + 1) + self._parts(right, depth + 1)
        if (kind == "parenthesized_expression" or kind in _JS_WRAPPERS) and (
            node.named_children
        ):
            return self._parts(node.named_children[0], depth + 1)
        if kind == "identifier":
            return self._resolve_name(node, depth)
        return [(False, _text(node))]


# ---------------------------------------------------------------------------
# Go: net/http routes and clients
# ---------------------------------------------------------------------------

_GO_CLIENT_FUNCS = {"Get": "GET", "Head": "HEAD", "Post": "POST", "PostForm": "POST"}


def _go_args(call: Any) -> list[Any]:
    arguments = call.child_by_field_name("arguments")
    children = arguments.named_children if arguments is not None else []
    return [child for child in children if child.type != "comment"]


def split_go_pattern(pattern: str) -> tuple[str | None, str | None]:
    """Split a ``net/http`` pattern into ``(method or None, normalised path)``.

    ``"GET /users/{id}"`` gives ``("GET", "/users/{id}")``. A host prefix is
    dropped (``"example.com/x"`` gives ``"/x"``). A pattern without a path
    gives ``(method, None)``.
    """
    text = pattern.strip()
    method = None
    head, sep, rest = text.partition(" ")
    if sep and head in HTTP_METHODS:
        method = head
        text = rest.strip()
    if not text.startswith("/"):
        slash = text.find("/")
        if slash <= 0:
            return method, None
        text = text[slash:]
    return method, normalize_route_path(text)


class _GoExtractor(_Extractor):
    scope_types = frozenset(
        {"function_declaration", "method_declaration", "func_literal"}
    )

    def run(self) -> None:
        self.http_names: set[str] = set()
        calls: list[Any] = []
        for node in _walk(self.root):
            kind = node.type
            if kind in ("const_spec", "var_spec"):
                self._pair(
                    node,
                    node.children_by_field_name("name"),
                    node.child_by_field_name("value"),
                )
            elif kind == "short_var_declaration":
                left = node.child_by_field_name("left")
                names = left.named_children if left is not None else []
                self._pair(node, names, node.child_by_field_name("right"))
            elif kind == "assignment_statement":
                left = node.child_by_field_name("left")
                names = left.named_children if left is not None else []
                operator = _text(node.child_by_field_name("operator"))
                right = node.child_by_field_name("right") if operator == "=" else None
                self._pair(node, names, right, force_unknown=right is None)
            elif kind in self.scope_types:
                self._bind_params(node)
                self._bind_params(node, "receiver")
            elif kind == "import_spec":
                self._import(node)
            elif kind == "call_expression":
                calls.append(node)
        for call in calls:
            if not self._route(call):
                self._client_call(call)
        self.finish()

    def _pair(
        self,
        node: Any,
        names: list[Any],
        values: Any,
        *,
        force_unknown: bool = False,
    ) -> None:
        value_nodes = values.named_children if values is not None else []
        aligned = not force_unknown and len(value_nodes) == len(names)
        for index, name in enumerate(names):
            if name.type == "identifier":
                value = value_nodes[index] if aligned else None
                self._bind_here(node, _text(name), value)

    def _import(self, node: Any) -> None:
        path = _text(node.child_by_field_name("path")).strip('"`')
        if path != "net/http":
            return
        alias = node.child_by_field_name("name")
        local = _text(alias) if alias is not None else "http"
        if local not in ("_", "."):
            self.http_names.add(local)

    def _handler(self, node: Any) -> tuple[str | None, str | None]:
        if node.type == "identifier":
            name = _text(node)
            return name, self._function_qn(name)
        if node.type == "selector_expression":
            name = _text(node.child_by_field_name("field"))
            return name, self._member_qn(name)
        return None, None

    def _gorilla_methods(self, call: Any) -> list[str] | None:
        selector = call.parent
        if (
            selector is None
            or selector.type != "selector_expression"
            or _text(selector.child_by_field_name("field")) != "Methods"
            or selector.parent is None
            or selector.parent.type != "call_expression"
        ):
            return None
        methods = []
        for arg in _go_args(selector.parent):
            method = self.static_method(arg)
            if method is None:
                return []
            methods.append(method)
        return methods

    def _route(self, call: Any) -> bool:
        function = call.child_by_field_name("function")
        if function is None or function.type != "selector_expression":
            return False
        if _text(function.child_by_field_name("field")) not in ("HandleFunc", "Handle"):
            return False
        args = _go_args(call)
        pattern = self.static(args[0]) if len(args) >= 2 else None
        if pattern is None:
            return True
        method, path = split_go_pattern(pattern)
        if path is None:
            return True
        gorilla = self._gorilla_methods(call)
        methods = (
            [method] if method else gorilla if gorilla is not None else [ANY_METHOD]
        )
        operand = _text(function.child_by_field_name("operand"))
        router = self.routers.get(operand)
        if router is None:
            router = _Router(operand, "app", "net/http", "")
            self.add_router(router)
        handler, handler_qn = self._handler(args[1])
        for item in methods:
            self.add_endpoint(
                router=router,
                method=item,
                raw_path=pattern,
                line=_line(call),
                handler=handler,
                handler_qn=handler_qn,
                path=path,
            )
        return True

    def _method(self, node: Any) -> str | None:
        if node.type == "selector_expression":
            operand = _text(node.child_by_field_name("operand"))
            field = _text(node.child_by_field_name("field"))
            if operand in self.http_names and field.startswith("Method"):
                method = field[len("Method") :].upper()
                return method if method in HTTP_METHODS else None
            return None
        return self.static_method(node)

    def _client_call(self, call: Any) -> None:
        function = call.child_by_field_name("function")
        if function is None or function.type != "selector_expression":
            return
        if _text(function.child_by_field_name("operand")) not in self.http_names:
            return
        field = _text(function.child_by_field_name("field"))
        args = _go_args(call)
        if field in _GO_CLIENT_FUNCS:
            self.add_call(
                call, _GO_CLIENT_FUNCS[field], args[0] if args else None, "net/http"
            )
        elif field in ("NewRequest", "NewRequestWithContext"):
            offset = 1 if field == "NewRequestWithContext" else 0
            method = self._method(args[offset]) if len(args) > offset else None
            url = args[offset + 1] if len(args) > offset + 1 else None
            self.add_call(call, method, url, "net/http")

    def _sprintf(self, call: Any, depth: int) -> list[Part]:
        args = _go_args(call)
        template = self.static(args[0]) if args else None
        if template is None or "%[" in template:
            return [(False, _text(call))]
        out: list[Part] = []
        position = 0
        next_arg = 1
        for match in _GO_VERB_RE.finditer(template):
            out.append((True, template[position : match.start()]))
            verb = match.group(0)
            if verb == "%%":
                out.append((True, "%"))
            elif "*" in verb or next_arg >= len(args):
                return [(False, _text(call))]
            else:
                out.extend(self._parts(args[next_arg], depth + 1))
                next_arg += 1
            position = match.end()
        out.append((True, template[position:]))
        return out

    def _parts(self, node: Any, depth: int) -> list[Part]:
        kind = node.type
        if kind in ("interpreted_string_literal", "raw_string_literal"):
            return [(True, _text(node)[1:-1])]
        if kind == "binary_expression":
            operator = _text(node.child_by_field_name("operator"))
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if operator == "+" and left is not None and right is not None:
                return self._parts(left, depth + 1) + self._parts(right, depth + 1)
        if kind == "parenthesized_expression" and node.named_children:
            return self._parts(node.named_children[0], depth + 1)
        if kind == "identifier":
            return self._resolve_name(node, depth)
        if kind == "call_expression":
            function = node.child_by_field_name("function")
            if (
                function is not None
                and function.type == "selector_expression"
                and _text(function.child_by_field_name("operand")) == "fmt"
                and _text(function.child_by_field_name("field")) == "Sprintf"
            ):
                return self._sprintf(node, depth)
        return [(False, _text(node))]


_EXTRACTORS: dict[str, type[_Extractor]] = {
    "python": _PythonExtractor,
    "javascript": _JsExtractor,
    "typescript": _JsExtractor,
    "tsx": _JsExtractor,
    "go": _GoExtractor,
}


def extract_http_surface(
    root: Any,
    source: bytes,
    language: str,
    file_path: str,
    nodes: list[NodeInfo],
    edges: list[EdgeInfo],
    import_map: dict[str, str],
    resolve_module: Callable[[str, str, str], str | None],
) -> None:
    """Add Endpoint nodes, ROUTES_TO edges and call evidence for one file.

    Mutates ``nodes`` and ``edges`` in place. ``nodes[0]`` must be the File
    node. Files that mention none of the supported frameworks or clients
    are left untouched without walking the tree.
    """
    extractor_type = _EXTRACTORS.get(language)
    if extractor_type is None or not nodes:
        return
    lowered = source.lower()
    if not any(token in lowered for token in _TRIGGERS[language]):
        return
    extractor = extractor_type(
        root, language, file_path, nodes, edges, import_map, resolve_module
    )
    extractor.run()  # type: ignore[attr-defined]
