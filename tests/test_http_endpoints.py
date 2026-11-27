"""HTTP route declarations become Endpoint nodes; client calls become evidence."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from tree_sitter_language_pack import get_parser

from crg import http_endpoints
from crg.http_endpoints import (
    RouteIndex,
    _is_absolute,
    _join_base,
    _text,
    call_path_from_parts,
    extract_http_surface,
    is_internal_host,
    normalize_route_path,
    path_key,
    split_go_pattern,
)
from crg.parser import CodeParser, NodeInfo


def _no_module(module: str, file_path: str, language: str) -> None:
    return None


def _parse(tmp_path: Path, name: str, code: str):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    nodes, edges = CodeParser().parse_bytes(path, code.encode("utf-8"))
    return nodes, edges, str(path)


def _endpoints(nodes) -> dict[str, object]:
    return {n.name: n for n in nodes if n.kind == "Endpoint"}


def _routes(edges) -> set[tuple[str, str]]:
    return {
        (e.source.rsplit("::", 1)[-1], e.target.rsplit("::", 1)[-1])
        for e in edges
        if e.kind == "ROUTES_TO"
    }


def _calls(nodes) -> list[tuple[str, dict]]:
    out = []
    for n in nodes:
        for call in n.extra.get("http_calls", []):
            out.append((n.name, call))
    return out


def _static_calls(nodes) -> dict[tuple[str, str], dict]:
    return {
        (c["method"], c["path"]): {**c, "owner": owner}
        for owner, c in _calls(nodes)
        if not c.get("dynamic")
    }


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/users/{user_id}", "/users/{user_id}"),
        ("/users/{user_id:int}", "/users/{user_id}"),
        ("/users/<int:user_id>", "/users/{user_id}"),
        ("/users/<user_id>", "/users/{user_id}"),
        ("/users/:id", "/users/{id}"),
        ("/users/:id?", "/users/{id}"),
        ("/files/{path...}", "/files/{path}"),
        ("/exact/{$}", "/exact"),
        ("users//list/", "/users/list"),
        ("", "/"),
        ("/", "/"),
    ],
)
def test_normalize_route_path_unifies_param_syntax(raw: str, expected: str) -> None:
    assert normalize_route_path(raw) == expected


def test_path_key_erases_param_names() -> None:
    assert path_key("/users/{user_id}/posts/{id}") == "/users/{}/posts/{}"
    assert path_key("/") == "/"


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ([(True, "/users/7")], ("/users/7", 1.0)),
        ([(True, "http://users-svc:8000/users/7?x=1#f")], ("/users/7", 1.0)),
        ([(True, "http://localhost:8000")], ("/", 1.0)),
        ([(True, "/users/"), (False, "uid")], ("/users/{}", 0.9)),
        ([(False, "BASE"), (True, "/users/"), (False, "uid")], ("/users/{}", 0.72)),
        ([(True, "http://"), (False, "host"), (True, "/users/1")], ("/users/1", 1.0)),
        (
            [(True, "/users/"), (False, "uid"), (True, "/posts")],
            ("/users/{}/posts", 0.9),
        ),
        ([(True, "/search?q="), (False, "q")], ("/search", 1.0)),
        ([(True, "/users/{id}")], ("/users/{}", 1.0)),
    ],
)
def test_call_path_from_parts_strips_bases_and_marks_params(parts, expected) -> None:
    path, confidence, _host = call_path_from_parts(parts)
    assert (path, round(confidence, 2)) == expected


@pytest.mark.parametrize(
    "parts",
    [
        [(False, "url")],
        [(False, "BASE"), (False, "path")],
        [(True, "/users"), (False, "suffix")],
        [(True, "/users/u-"), (False, "uid")],
        [(True, "users/1")],
        [(False, "BASE"), (True, "users")],
        [(True, "http://"), (False, "host")],
        [(True, "ftp://files.internal/x")],
    ],
)
def test_call_path_from_parts_rejects_dynamic_urls(parts) -> None:
    path, confidence, _host = call_path_from_parts(parts)
    assert path is None
    assert confidence == 0.0


def test_call_path_from_parts_reports_literal_host() -> None:
    _path, _conf, host = call_path_from_parts(
        [(True, "https://api.github.com/users/x")]
    )
    assert host == "api.github.com"


def test_route_index_prefers_literal_segments() -> None:
    index: RouteIndex[str] = RouteIndex()
    for key in ("/users/{}", "/users/me", "/", "/orders/{}/items"):
        index.add(key, key)
    assert index.match("/users/7") == [(1, "/users/{}")]
    assert sorted(index.match("/users/me")) == [(1, "/users/{}"), (2, "/users/me")]
    # A parameter in the call is an unknown value: it never matches a literal.
    assert index.match("/users/{}") == [(1, "/users/{}")]
    assert index.match("/users/7/x") == []
    assert index.match("/orders/7") == []
    assert index.match("/orders/7/items") == [(2, "/orders/{}/items")]
    assert index.match("/") == [(0, "/")]
    assert index.match("//users//7/") == [(1, "/users/{}")]


def _reference_score(call_path: str, route_key: str) -> int | None:
    """Score one route key the slow way: compare segment by segment."""
    call = [s for s in call_path.split("/") if s]
    route = [s for s in route_key.split("/") if s]
    if len(call) != len(route):
        return None
    score = 0
    for call_segment, route_segment in zip(call, route, strict=True):
        if route_segment == "{}":
            continue
        if call_segment != route_segment:
            return None
        score += 1
    return score


def test_route_index_matches_segment_by_segment_scoring() -> None:
    keys = ["/", "/a", "/{}", "/a/b", "/a/{}", "/{}/b", "/{}/{}", "/a/b/c"]
    keys += ["/a/{}/c", "/{}/b/{}", "/x/y"]
    index: RouteIndex[str] = RouteIndex()
    for key in keys:
        index.add(key, key)
    index.add("/a/b", "second value for /a/b")
    paths = ["/", "/a", "/b", "/{}", "/a/b", "/a/c", "/a/{}", "/{}/b", "/z/b"]
    paths += ["/a/b/c", "/a/z/c", "/a/{}/c", "/q/b/s", "/x/y", "/x/y/z"]
    for path in paths:
        expected = [
            (score, key)
            for key in keys
            if (score := _reference_score(path, key)) is not None
        ]
        if _reference_score(path, "/a/b") is not None:
            expected.append((2, "second value for /a/b"))
        assert sorted(index.match(path)) == sorted(expected), path


# ---------------------------------------------------------------------------
# Python: FastAPI + Flask
# ---------------------------------------------------------------------------


FASTAPI_APP = """\
from fastapi import APIRouter, FastAPI

app = FastAPI()
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}")
def get_user(user_id: int):
    return {"id": user_id}


@router.post("")
async def create_user():
    return {}


@app.api_route("/items/{item_id:int}", methods=["GET", "PUT"])
def item(item_id):
    return {}


@app.delete(path="/items/{item_id}")
def drop_item(item_id):
    return {}


app.include_router(router, prefix="/api")
"""


def test_fastapi_routes_become_endpoints(tmp_path: Path) -> None:
    nodes, edges, fp = _parse(tmp_path, "svc/main.py", FASTAPI_APP)
    eps = _endpoints(nodes)
    assert set(eps) == {
        "GET /users/{user_id}",
        "POST /users",
        "GET /items/{item_id}",
        "PUT /items/{item_id}",
        "DELETE /items/{item_id}",
    }
    get_user = eps["GET /users/{user_id}"]
    assert get_user.extra["framework"] == "fastapi"
    assert get_user.extra["http_method"] == "GET"
    assert get_user.extra["path"] == "/users/{user_id}"
    assert get_user.extra["router"] == "router"
    assert get_user.extra["router_kind"] == "router"
    assert get_user.line_start == 7
    assert ("GET /users/{user_id}", "get_user") in _routes(edges)
    assert ("POST /users", "create_user") in _routes(edges)
    assert ("PUT /items/{item_id}", "item") in _routes(edges)
    contains = {
        e.target.rsplit("::", 1)[-1]
        for e in edges
        if e.kind == "CONTAINS" and e.source == fp
    }
    assert "GET /users/{user_id}" in contains

    file_node = nodes[0]
    assert file_node.extra["http_mounts"] == [
        {
            "parent": "app",
            "prefix": "/api",
            "child": "router",
            "child_file": None,
            "line": 27,
        }
    ]


FLASK_APP = """\
from flask import Blueprint, Flask

app = Flask(__name__)
bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/<int:user_id>", methods=["GET", "POST"])
def user(user_id):
    return ""


@app.route("/health")
def health():
    return "ok"


@app.get("/ping")
def ping():
    return "pong"


app.register_blueprint(bp, url_prefix="/v1")
"""


def test_flask_routes_methods_and_blueprints(tmp_path: Path) -> None:
    nodes, edges, _fp = _parse(tmp_path, "flask_app.py", FLASK_APP)
    eps = _endpoints(nodes)
    assert set(eps) == {
        "GET /users/{user_id}",
        "POST /users/{user_id}",
        "GET /health",
        "GET /ping",
    }
    assert eps["GET /health"].extra["framework"] == "flask"
    assert eps["GET /health"].extra["router_kind"] == "app"
    assert ("POST /users/{user_id}", "user") in _routes(edges)
    mounts = nodes[0].extra["http_mounts"]
    assert mounts[0]["parent"] == "app"
    assert mounts[0]["prefix"] == "/v1"
    assert mounts[0]["child"] == "bp"


def test_python_cross_file_mount_records_child_file(tmp_path: Path) -> None:
    pkg = tmp_path / "svc"
    (pkg / "routers").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "routers" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "routers" / "users.py").write_text("router = None\n", encoding="utf-8")
    code = (
        "from fastapi import FastAPI\n"
        "from .routers import users\n"
        "from .routers.users import router as users_router\n"
        "app = FastAPI()\n"
        "app.include_router(users.router, prefix='/api')\n"
        "app.include_router(users_router)\n"
    )
    nodes, _edges, _fp = _parse(tmp_path, "svc/main.py", code)
    mounts = nodes[0].extra["http_mounts"]
    users_file = str((pkg / "routers" / "users.py").resolve())
    assert mounts[0]["child"] == "router"
    assert mounts[0]["prefix"] == "/api"
    assert mounts[0]["child_file"] == users_file
    assert mounts[1]["child"] == "router"
    assert mounts[1]["prefix"] == ""
    assert mounts[1]["child_file"] == users_file


def test_route_with_dynamic_path_is_skipped(tmp_path: Path) -> None:
    code = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "PATH = compute()\n"
        "@router.get(PATH)\n"
        "def dyn():\n"
        "    return 1\n"
        "@cache.get('not-a-path')\n"
        "def cached():\n"
        "    return 1\n"
    )
    nodes, _edges, _fp = _parse(tmp_path, "dyn.py", code)
    assert _endpoints(nodes) == {}


PY_CLIENT = """\
import httpx
import requests
from fastapi.testclient import TestClient

BASE = "http://users-svc:8000"
API = BASE + "/api"


def fetch_user(uid):
    return httpx.get(f"{BASE}/users/{uid}", timeout=3)


def create(payload):
    url = API + "/users"
    return requests.post(url, json=payload)


def generic(method, uid):
    return requests.request("PATCH", "/users/" + str(uid))


def with_client():
    with httpx.Client(base_url="http://svc/api/") as client:
        client.get("/orders/1")
        client.request("DELETE", "/orders/2")


def session_call():
    s = requests.Session()
    return s.put("http://svc/things/9")


def dynamic(url):
    requests.get(url)
    requests.request(verb, "/x")
    return httpx.get(url=f"{settings.host}{path}")


def external():
    return requests.get("https://api.github.com/users/octocat")


requests.head("/status")
"""


def test_python_http_client_calls_are_recorded(tmp_path: Path) -> None:
    nodes, _edges, _fp = _parse(tmp_path, "client.py", PY_CLIENT)
    calls = _static_calls(nodes)
    assert calls[("GET", "/users/{}")]["owner"] == "fetch_user"
    assert calls[("GET", "/users/{}")]["confidence"] == pytest.approx(0.9)
    assert calls[("POST", "/api/users")]["owner"] == "create"
    assert calls[("POST", "/api/users")]["confidence"] == pytest.approx(1.0)
    assert calls[("PATCH", "/users/{}")]["owner"] == "generic"
    assert calls[("GET", "/api/orders/1")]["owner"] == "with_client"
    assert calls[("DELETE", "/api/orders/2")]["owner"] == "with_client"
    assert calls[("PUT", "/things/9")]["owner"] == "session_call"
    assert calls[("GET", "/users/octocat")]["host"] == "api.github.com"
    # Module-level calls are attributed to the File node.
    assert calls[("HEAD", "/status")]["owner"].endswith("client.py")
    dynamic = [c for owner, c in _calls(nodes) if c.get("dynamic")]
    assert len(dynamic) == 3
    assert all("path" not in c for c in dynamic)


# ---------------------------------------------------------------------------
# JavaScript / TypeScript: Express + fetch/axios
# ---------------------------------------------------------------------------


EXPRESS_APP = """\
const express = require("express");
const users = require("./routes/users");
const app = express();
const router = express.Router();

function getUser(req, res) {}
function listBooks(req, res) {}

router.get("/users/:id", getUser);
router.post("/users", (req, res) => {});
app.route("/books").get(listBooks).post(listBooks);
app.all("/any", listBooks);
app.use("/api", router);
app.use("/v2", users);
app.get(dynamicPath, getUser);
app.listen(3000);
"""


def test_express_routes_and_mounts(tmp_path: Path) -> None:
    (tmp_path / "web" / "routes").mkdir(parents=True)
    (tmp_path / "web" / "routes" / "users.js").write_text(
        "module.exports = {};\n", encoding="utf-8"
    )
    nodes, edges, _fp = _parse(tmp_path, "web/app.js", EXPRESS_APP)
    eps = _endpoints(nodes)
    assert set(eps) == {
        "GET /users/{id}",
        "POST /users",
        "GET /books",
        "POST /books",
        "* /any",
    }
    assert eps["GET /users/{id}"].extra["framework"] == "express"
    assert eps["GET /users/{id}"].extra["router_kind"] == "router"
    assert eps["GET /books"].extra["router_kind"] == "app"
    routes = _routes(edges)
    assert ("GET /users/{id}", "getUser") in routes
    assert ("POST /books", "listBooks") in routes
    assert all(src != "POST /users" for src, _ in routes)
    mounts = nodes[0].extra["http_mounts"]
    assert mounts[0] == {
        "parent": "app",
        "prefix": "/api",
        "child": "router",
        "child_file": None,
        "line": 13,
    }
    assert mounts[1]["child_file"] == str(
        (tmp_path / "web" / "routes" / "users.js").resolve()
    )
    assert mounts[1]["child"] is None


JS_CLIENT = """\
import axios from "axios";
const BASE = "http://users-svc";
const api = axios.create({ baseURL: "http://gateway/api" });

export async function loadUser(id) {
  const res = await fetch(`${BASE}/users/${id}`);
  return res.json();
}

export function saveUser(id, body) {
  return fetch("/users/" + id, { method: "PUT", body });
}

export function viaAxios() {
  axios.post("/users", {});
  api.get("/orders/5");
  axios({ url: "/things/1", method: "delete" });
}

export function dynamicCalls(url, verb) {
  fetch(url);
  fetch("/users/1", { method: verb });
  axios.get(`${window.location.origin}${path}`);
}
"""


def test_js_fetch_and_axios_calls(tmp_path: Path) -> None:
    nodes, _edges, _fp = _parse(tmp_path, "web/client.js", JS_CLIENT)
    calls = _static_calls(nodes)
    assert calls[("GET", "/users/{}")]["owner"] == "loadUser"
    assert calls[("GET", "/users/{}")]["confidence"] == pytest.approx(0.9)
    assert calls[("PUT", "/users/{}")]["owner"] == "saveUser"
    assert calls[("POST", "/users")]["owner"] == "viaAxios"
    assert calls[("GET", "/api/orders/5")]["owner"] == "viaAxios"
    assert calls[("DELETE", "/things/1")]["owner"] == "viaAxios"
    dynamic = [c for owner, c in _calls(nodes) if c.get("dynamic")]
    assert len(dynamic) == 3


def test_typescript_client_and_router(tmp_path: Path) -> None:
    code = (
        'import { Router } from "express";\n'
        "export const router = Router();\n"
        "function show(req: any, res: any): void {}\n"
        'router.get("/reports/:rid", show);\n'
        "export async function pull(rid: string): Promise<void> {\n"
        "  await axios.get<Report>(`/reports/${rid}`);\n"
        "}\n"
    )
    nodes, edges, _fp = _parse(tmp_path, "web/reports.ts", code)
    assert "GET /reports/{rid}" in _endpoints(nodes)
    assert ("GET /reports/{rid}", "show") in _routes(edges)
    assert ("GET", "/reports/{}") in _static_calls(nodes)


# ---------------------------------------------------------------------------
# Go: net/http routes and clients
# ---------------------------------------------------------------------------


GO_SERVICE = """\
package main

import (
\t"fmt"
\t"net/http"
)

const base = "http://users-svc"

type H struct{}

func (h *H) getUser(w http.ResponseWriter, r *http.Request) {}

func health(w http.ResponseWriter, r *http.Request) {}

func main() {
\th := &H{}
\tmux := http.NewServeMux()
\tmux.HandleFunc("GET /users/{id}", h.getUser)
\tmux.HandleFunc("POST example.com/users", health)
\thttp.HandleFunc("/health", health)
\tr.HandleFunc("/legacy/{id}", health).Methods("GET", "DELETE")
\tmux.Handle("/static/", nil)
\tmux.HandleFunc(pattern, health)
}

func client(id int) {
\thttp.Get(base + "/users/1")
\thttp.Post("http://svc/items", "application/json", nil)
\treq, _ := http.NewRequest(http.MethodPut, fmt.Sprintf("%s/users/%d", base, id), nil)
\t_ = req
\tu := fmt.Sprintf("/orders/%d/lines", id)
\thttp.NewRequestWithContext(ctx, "PATCH", u, nil)
\thttp.Get(target)
\thttp.NewRequest(method, "/x", nil)
}
"""


def test_go_net_http_routes_and_clients(tmp_path: Path) -> None:
    nodes, edges, _fp = _parse(tmp_path, "svc/main.go", GO_SERVICE)
    eps = _endpoints(nodes)
    assert set(eps) == {
        "GET /users/{id}",
        "POST /users",
        "* /health",
        "GET /legacy/{id}",
        "DELETE /legacy/{id}",
        "* /static",
    }
    assert eps["GET /users/{id}"].extra["framework"] == "net/http"
    routes = _routes(edges)
    assert ("* /health", "health") in routes
    assert ("GET /users/{id}", "H.getUser") in routes
    calls = _static_calls(nodes)
    assert calls[("GET", "/users/1")]["owner"] == "client"
    assert ("POST", "/items") in calls
    assert ("PUT", "/users/{}") in calls
    assert ("PATCH", "/orders/{}/lines") in calls
    dynamic = [c for owner, c in _calls(nodes) if c.get("dynamic")]
    assert len(dynamic) == 2


def test_unsupported_language_is_untouched(tmp_path: Path) -> None:
    nodes, edges, _fp = _parse(
        tmp_path, "Main.java", 'class Main { void f() { get("/users"); } }\n'
    )
    assert _endpoints(nodes) == {}
    assert _calls(nodes) == []


# ---------------------------------------------------------------------------
# Edge cases: the extractor never guesses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "internal"),
    [
        ("", True),
        ("10.0.0.1", True),
        ("[::1]", True),
        ("fe80::1", True),
        ("8.8.8.8", False),
        ("users-svc", True),
        ("billing.internal", True),
        ("api.github.com", False),
    ],
)
def test_is_internal_host(host: str, internal: bool) -> None:
    assert is_internal_host(host) is internal


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ([], (None, 0.0, None)),
        ([(True, "//users-svc/users")], ("/users", 1.0, "users-svc")),
        ([(True, "http://users-svc?x=1")], ("/", 1.0, "users-svc")),
        ([(True, "http://[::1]:8080/users")], ("/users", 1.0, "::1")),
        ([(True, "/users/"), (False, "uid"), (True, ".json")], (None, 0.0, None)),
    ],
)
def test_call_path_from_parts_edge_cases(parts, expected) -> None:
    assert call_path_from_parts(parts) == expected


def test_private_url_helpers_reject_unknown_parts() -> None:
    base = [(True, "http://svc")]
    assert _join_base(base, []) is None
    assert _join_base(base, [(False, "url")]) is None
    assert _join_base(base, [(True, "/users")]) == [
        (True, "http://svc"),
        (True, "/"),
        (True, "users"),
    ]
    assert _is_absolute([]) is False
    assert _is_absolute([(False, "url")]) is False
    assert _is_absolute([(True, "//svc/x")]) is True
    assert _text(None) == ""


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("GET", (None, None)),
        ("POST example.com", ("POST", None)),
        ("example.com/items/{id}", (None, "/items/{id}")),
    ],
)
def test_split_go_pattern_without_path(pattern: str, expected) -> None:
    assert split_go_pattern(pattern) == expected


def test_extract_http_surface_without_nodes_is_a_no_op() -> None:
    edges: list = []
    extract_http_surface(
        None, b"import requests", "python", "x.py", [], edges, {}, _no_module
    )
    assert edges == []


def test_function_without_lines_does_not_own_calls() -> None:
    source = b'import requests\n\ndef f():\n    requests.get("/users")\n'
    root = get_parser("python").parse(source).root_node
    file_node = NodeInfo("File", "x.py", "x.py", 1, 4, "python")
    nodes = [file_node, NodeInfo("Function", "f", "x.py", None, None, "python")]
    extract_http_surface(root, source, "python", "x.py", nodes, [], {}, _no_module)
    assert file_node.extra["http_calls"][0]["path"] == "/users"
    assert "http_calls" not in nodes[1].extra


PY_EDGE_ROUTES = """\
from fastapi import APIRouter, FastAPI

app = FastAPI()
dyn = APIRouter(prefix=compute_prefix())


def handler():
    return 1


def handler():
    return 2


@app.get("/dup")
@app.get("/dup")
def dup():
    return 0


@app.get("/ambiguous")
def handler():
    return 3


@dyn.get("/hidden")
def hidden():
    return 0


@app.websocket("/ws")
def ws():
    return 0


@app.api_route("/not-a-list", methods=METHODS)
def not_a_list():
    return 0


@app.api_route("/dynamic-method", methods=["GET", verb])
def dynamic_method():
    return 0


@app.get()
def no_path():
    return 0


@app.get("/class")
class NotAFunction:
    pass


@staticmethod
@app_factory
def plain():
    return 0


class Views:
    @app.get("/views")
    def index(self):
        return 0


def outer():
    @app.get("/nested")
    def inner():
        return 0

    return inner


if True:

    @app.get("/inside-if")
    def inside_if():
        return 0
"""


def test_python_routes_that_cannot_be_resolved_are_skipped(tmp_path: Path) -> None:
    nodes, edges, _fp = _parse(tmp_path, "svc/edge.py", PY_EDGE_ROUTES)
    endpoint_names = [n.name for n in nodes if n.kind == "Endpoint"]
    assert sorted(endpoint_names) == [
        "GET /ambiguous",
        "GET /dup",
        "GET /inside-if",
        "GET /nested",
        "GET /views",
    ]
    routes = _routes(edges)
    assert ("GET /views", "Views.index") in routes
    assert ("GET /inside-if", "inside_if") in routes
    # A handler name defined more than once, or a nested handler, is not linked.
    assert {src for src, _ in routes} == {"GET /dup", "GET /views", "GET /inside-if"}


PY_EDGE_CALLS = """\
import httpx
import requests as rq
from fastapi.testclient import TestClient

a0 = "/chain"
a1 = a0
a2 = a1
a3 = a2
a4 = a3
a5 = a4
a6 = a5
a7 = a6
annotated: str
x, y = "/tuple", "/pair"
total = "/total"
total += "/more"
weird = make()()
deep = pkg.sub.Client()
client = TestClient(app)
api = httpx.Client(base_url="http://users-svc")


def calls(url, lock):
    rq.get("/aliased")
    rq.get(a7)
    rq.get()
    rq.get(u for u in url)
    rq.get(  # the URL follows
        "/commented"
    )
    rq.get("/users" "/list")
    rq.get(("/paren"))
    rq.get("/fmt/%s" % url)
    for item in url:
        rq.get(item)
    rq.get(total)
    rq.get(x)
    rq.get(annotated)
    weird.get("/weird")
    deep.get("/deep")
    api.get(url)
    with httpx.Client():
        pass
    with lock as held:
        held.get("/held")
    with open("f") as fh:
        fh.get("/file")


def test_with_client():
    client.get("/views")
"""


def test_python_client_calls_that_cannot_be_resolved_stay_dynamic(
    tmp_path: Path,
) -> None:
    nodes, _edges, _fp = _parse(tmp_path, "svc/calls.py", PY_EDGE_CALLS)
    static = _static_calls(nodes)
    assert set(static) == {
        ("GET", "/aliased"),
        ("GET", "/commented"),
        ("GET", "/users/list"),
        ("GET", "/paren"),
        ("GET", "/views"),
    }
    assert static[("GET", "/aliased")]["client"] == "requests"
    assert static[("GET", "/views")]["client"] == "testclient"
    assert static[("GET", "/views")]["owner"] == "test_with_client"
    dynamic = [c for owner, c in _calls(nodes) if c.get("dynamic")]
    # a7 (resolve depth cap), no URL, a generator, "%", a loop variable,
    # a re-bound name, a tuple target, an annotation, and a dynamic URL on a
    # client with a base URL.
    assert len(dynamic) == 9


def test_python_calls_with_too_many_parts_or_calls_are_capped(tmp_path: Path) -> None:
    many_parts = "/{seg}" * 40
    lines = ["import requests", "", "", "def wide(seg):"]
    lines.append(f'    requests.get(f"{many_parts}")')
    lines += ["", "", "def busy():"]
    lines += [f'    requests.get("/n{i}")' for i in range(205)]
    nodes, _edges, _fp = _parse(tmp_path, "svc/many.py", "\n".join(lines) + "\n")
    owners: dict[str, list[dict]] = {}
    for owner, call in _calls(nodes):
        owners.setdefault(owner, []).append(call)
    assert owners["wide"] == [
        {
            "method": "GET",
            "line": 5,
            "client": "requests",
            "dynamic": True,
            "confidence": 0.0,
        }
    ]
    assert len(owners["busy"]) == 200


def test_python_mounts_resolve_relative_and_absolute_modules(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    (pkg / "routes").mkdir(parents=True)
    (pkg / "api").mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "routes" / "__init__.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8"
    )
    (pkg / "api" / "__init__.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8"
    )
    code = (
        "from fastapi import FastAPI\n"
        "from .. import routes\n"
        "from . import missing\n"
        "from . import router as local_router\n"
        "import ext_routes\n"
        "app = FastAPI()\n"
        'app.include_router(routes.router, prefix="/r")\n'
        "app.include_router(local_router)\n"
        "app.include_router(missing.router)\n"
        "app.include_router(ext_routes.router)\n"
        "app.include_router(unknown_name)\n"
        "app.include_router(make_router())\n"
        "app.include_router(a.b.router)\n"
        "app.include_router(other.router)\n"
        "app.include_router()\n"
        "self.app.include_router(local_router)\n"
    )
    nodes, _edges, _fp = _parse(tmp_path, "pkg/api/main.py", code)
    mounts = nodes[0].extra["http_mounts"]
    assert [(m["child"], m["prefix"], m["child_file"]) for m in mounts] == [
        ("router", "/r", str((pkg / "routes" / "__init__.py").resolve())),
        ("router", "", str((pkg / "api" / "__init__.py").resolve())),
    ]


JS_EDGE = """\
import * as ax from "axios";
import { /* factory */ Router as makeRouter, json } from "express";
import express from "express";
import { listUsers } from "./controllers";
import * as controllers from "./controllers";
import { helper } from "some-package";
const { Router, static: serveStatic } = require("express");
const [first] = require("express");
const dynamicModule = require(moduleName);
const app = express();
const api = makeRouter();
const r2 = Router();
const plain = foo();
const weird = foo()();
const inst = axios.create();
let url;
url = "/assigned";
const cfg = {};
cfg.url = "/member";
let counter = "/counter";
counter += "/more";
cfg.n += 1;
const opts = { method: "POST" };
const notObj = 5;

class A { list() {} }
class B { list() {} }

app.get("/imported", listUsers);
app.get("/namespaced", controllers.show);
app.get("/pkg", helper);
app.get("/ambiguous-member", obj.list);
app.something("/x").get(h);
factory().get("/y", h);
chain.get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h).get(h);
app.use("/legacy", require("./legacy"));
app.use(cors());
app.use(api);
app.use("/api", unknownRouter);
other.use("/z", api);
this.app.use("/w", api);

const single = u => fetch(u);

export function clients(extra, method) {
  fetch("/with-opts", opts);
  fetch("/unbound-opts", missingOpts);
  fetch("/call-opts", makeOpts());
  fetch("/number-opts", notObj);
  fetch("/headers-only", { headers: {} });
  fetch("/shorthand", { method });
  fetch("/string-key", { "method": "PUT", ...extra });
  window.fetch("/window");
  axios.request({ url: "/req", method: "post" });
  axios.isCancel(extra);
  axios();
  axios("/fn", { method: "patch", baseURL: "http://svc" });
  axios("/fn-default");
  ax.get("/ns");
  inst.get("/inst");
  fetch(base || "/or");
  (getClient())("/zz");
  fetch(url);
  fetch(counter);
}
"""


def test_js_edge_cases_never_guess(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "controllers.js").write_text(
        "export function listUsers() {}\nexport function show() {}\n",
        encoding="utf-8",
    )
    (web / "legacy.js").write_text("module.exports = {};\n", encoding="utf-8")
    nodes, edges, _fp = _parse(tmp_path, "web/app.js", JS_EDGE)
    eps = _endpoints(nodes)
    assert set(eps) == {
        "GET /imported",
        "GET /namespaced",
        "GET /pkg",
        "GET /ambiguous-member",
    }
    controllers = str((web / "controllers.js").resolve())
    assert eps["GET /imported"].extra["handler_ref"] == {
        "name": "listUsers",
        "file": controllers,
    }
    assert eps["GET /namespaced"].extra["handler_ref"] == {
        "name": "show",
        "file": controllers,
    }
    assert eps["GET /pkg"].extra["handler_ref"] == {"name": "helper", "file": None}
    assert eps["GET /ambiguous-member"].extra["handler_ref"] == {
        "name": "list",
        "file": None,
    }
    assert _routes(edges) == set()

    file_extra = nodes[0].extra
    assert set(file_extra["http_routers"]) == {"app", "api", "r2"}
    mounts = [(m["parent"], m["prefix"], m["child"]) for m in file_extra["http_mounts"]]
    assert mounts == [("app", "/legacy", None), ("app", "", "api")]
    assert file_extra["http_mounts"][0]["child_file"] == str(
        (web / "legacy.js").resolve()
    )

    static = _static_calls(nodes)
    assert set(static) == {
        ("POST", "/with-opts"),
        ("GET", "/headers-only"),
        ("PUT", "/string-key"),
        ("GET", "/window"),
        ("POST", "/req"),
        ("PATCH", "/fn"),
        ("GET", "/fn-default"),
        ("GET", "/ns"),
        ("GET", "/inst"),
    }
    assert static[("PATCH", "/fn")]["host"] == "svc"
    dynamic = [c for owner, c in _calls(nodes) if c.get("dynamic")]
    # u, unbound options, call options, number options, shorthand method,
    # "||", a re-bound url and a re-bound counter.
    assert len(dynamic) == 8


def test_typescript_wrapped_url_is_unwrapped(tmp_path: Path) -> None:
    code = 'export function f() {\n  return fetch("/typed" as string);\n}\n'
    nodes, _edges, _fp = _parse(tmp_path, "web/typed.ts", code)
    assert ("GET", "/typed") in _static_calls(nodes)


GO_EDGE = """\
package main

import (
\t_ "net/http"
\t"fmt"
\t"net/http"
)

type A struct{}

func (A) List(w http.ResponseWriter, r *http.Request) {}

type B struct{}

func (B) List(w http.ResponseWriter, r *http.Request) {}

func index(w http.ResponseWriter, r *http.Request) {}

func handle(p string, h interface{}) {}

func main() {
\tvar m string
\tvar s struct{ url string }
\ts.url = "/sel"
\thttp.HandleFunc("GET", index)
\tr.HandleFunc("/gorilla", index).Methods(m)
\thandle("/x", index)
\tmux.HandleFunc("/members", a.List)
}

func client(id string, parts []string) {
\thttp.Get(("/paren"))
\thttp.Get(buildURL())
\thttp.Get(strings.Join(parts, "/"))
\thttp.Get(cfg.URL)
\thttp.Get(base | "/x")
\thttp.Get(fmt.Sprintf("/idx/%[1]s", id))
\thttp.Get(fmt.Sprintf("/pct%%/%s", id))
\thttp.Get(fmt.Sprintf("/star/%*d", 3, id))
\thttp.Get(fmt.Sprintf("/few/%s/%s", id))
\thttp.Get(fmt.Sprintf(tmpl, id))
\thttp.NewRequest(cfg.Method, "/cfg", nil)
\thttp.NewRequest(http.MethodFoo, "/foo", nil)
\thttp.NewRequest()
}
"""


def test_go_edge_cases_never_guess(tmp_path: Path) -> None:
    nodes, edges, _fp = _parse(tmp_path, "svc/edge.go", GO_EDGE)
    assert set(_endpoints(nodes)) == {"* /members"}
    assert _routes(edges) == set()
    static = _static_calls(nodes)
    assert set(static) == {("GET", "/paren"), ("GET", "/pct%/{}")}
    dynamic = [c for owner, c in _calls(nodes) if c.get("dynamic")]
    # buildURL(), strings.Join, cfg.URL, "|", %[1]s, %*d, too few arguments,
    # a dynamic template, cfg.Method, http.MethodFoo and no arguments.
    assert len(dynamic) == 11


HTTP_SERVICE = """\
import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/items/{item_id}")
def get_item(item_id: int):
    return httpx.get("http://inventory/stock/7").json()
"""


def test_extractor_failure_keeps_the_rest_of_the_file(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    nodes, edges, _ = _parse(tmp_path, "ok/svc.py", HTTP_SERVICE)
    assert set(_endpoints(nodes)) == {"GET /api/items/{item_id}"}
    assert _calls(nodes)
    assert "http_routers" in nodes[0].extra

    real_run = http_endpoints._PythonExtractor.run

    def failing_run(self) -> None:
        real_run(self)  # mutate nodes, edges and extras first
        raise RuntimeError("extractor bug")

    monkeypatch.setattr(http_endpoints._PythonExtractor, "run", failing_run)
    with caplog.at_level(logging.WARNING, logger="crg.http_endpoints"):
        nodes, edges, _ = _parse(tmp_path, "broken/svc.py", HTTP_SERVICE)

    assert [n.kind for n in nodes] == ["File", "Function"]
    assert nodes[1].name == "get_item"
    assert not any(key.startswith("http_") for n in nodes for key in n.extra)
    assert not any(e.kind == "ROUTES_TO" for e in edges)
    assert any(e.kind == "CONTAINS" for e in edges)
    assert "svc.py" in caplog.text
    assert "extractor bug" in caplog.text
