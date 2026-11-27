"""CALLS_ENDPOINT edges link HTTP client calls to Endpoint nodes across repos."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from crg.federation import link_http_endpoints
from crg.graph import GraphStore
from crg.incremental import GraphUpdateHandler, full_build, incremental_update
from crg.parser import CodeParser, NodeInfo
from crg.tools import build_or_update_graph

SERVICE_A_USERS = """\
from fastapi import APIRouter

router = APIRouter(prefix="/users")


@router.get("/{user_id}")
def get_user(user_id: int):
    return {"id": user_id}


@router.get("/me")
def get_me():
    return {}
"""

SERVICE_A_MAIN = """\
from fastapi import FastAPI

from .routers import users

app = FastAPI()
app.include_router(users.router)
"""

REPO_B_CLIENT = """\
import os

import httpx

USERS_URL = os.environ["USERS_URL"]


def load_profile(uid):
    return httpx.get(f"{USERS_URL}/users/{uid}").json()


def load_anything(url):
    return httpx.get(url).json()
"""


def _make_repo(root: Path) -> None:
    root.mkdir(parents=True)
    (root / ".git").mkdir()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _workspace(tmp_path: Path, client_code: str) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    _make_repo(workspace)
    (workspace / ".crg").mkdir()
    service_a = workspace / "service_a"
    repo_b = workspace / "repo_b"
    _make_repo(service_a)
    _make_repo(repo_b)
    _write(service_a / "app" / "__init__.py", "")
    _write(service_a / "app" / "routers" / "__init__.py", "")
    _write(service_a / "app" / "routers" / "users.py", SERVICE_A_USERS)
    _write(service_a / "app" / "main.py", SERVICE_A_MAIN)
    _write(repo_b / "client" / "profile.py", client_code)
    return workspace, service_a, repo_b


def _calls_endpoint_edges(store: GraphStore) -> list:
    rows = store._conn.execute(
        "SELECT source_qualified, target_qualified, repo_id, confidence, "
        "resolution, extra FROM edges WHERE kind = 'CALLS_ENDPOINT'"
    ).fetchall()
    return list(rows)


def test_two_repo_federation_links_exactly_one_cross_repo_call(
    tmp_path: Path,
) -> None:
    workspace, service_a, repo_b = _workspace(tmp_path, REPO_B_CLIENT)
    result = build_or_update_graph(
        full_rebuild=True,
        repo_root=str(workspace),
        roots=[str(service_a), str(repo_b)],
    )
    assert result["status"] == "ok", result
    assert result["http_endpoints"]["cross_repo"] == 1

    store = GraphStore(workspace / ".crg" / "graph.db")
    try:
        repo_ids = {
            Path(r["path"]).resolve(): r["repo_id"]
            for r in store._conn.execute("SELECT repo_id, path FROM repos")
        }
        edges = _calls_endpoint_edges(store)
        assert len(edges) == 1
        edge = edges[0]
        users_file = (service_a / "app" / "routers" / "users.py").resolve()
        client_file = (repo_b / "client" / "profile.py").resolve()
        assert edge["source_qualified"] == f"{client_file}::load_profile"
        assert edge["target_qualified"] == f"{users_file}::GET /users/{{user_id}}"
        assert edge["repo_id"] == repo_ids[repo_b.resolve()]
        assert edge["resolution"] == "http_route"
        # Dynamic base URL stripped (x0.8) and one dynamic segment (x0.9).
        assert edge["confidence"] == 0.72
        import json

        extra = json.loads(edge["extra"])
        assert extra["cross_repo"] is True
        assert extra["endpoint_repo_id"] == repo_ids[service_a.resolve()]
        assert extra["http_method"] == "GET"
        assert extra["path"] == "/users/{}"

        # The endpoint links back to its handler, so the impact of a change
        # to the handler reaches the client in the other repo.
        impact = store.get_impact_radius([str(users_file)], max_depth=3)
        assert str(client_file) in impact["impacted_files"]
    finally:
        store.close()


def test_dynamic_url_produces_no_edge(tmp_path: Path) -> None:
    client = (
        "import httpx\n"
        "\n"
        "def load_anything(url):\n"
        "    return httpx.get(url).json()\n"
        "\n"
        "def load_built(base, path):\n"
        "    return httpx.get(base + path).json()\n"
    )
    workspace, service_a, repo_b = _workspace(tmp_path, client)
    result = build_or_update_graph(
        full_rebuild=True,
        repo_root=str(workspace),
        roots=[str(service_a), str(repo_b)],
    )
    assert result["status"] == "ok", result
    stats = result["http_endpoints"]
    assert stats["linked"] == 0
    assert stats["dynamic"] == 2
    store = GraphStore(workspace / ".crg" / "graph.db")
    try:
        assert _calls_endpoint_edges(store) == []
    finally:
        store.close()


def test_ambiguous_and_external_calls_are_not_linked(tmp_path: Path) -> None:
    client = (
        "import httpx\n"
        "\n"
        "def ambiguous():\n"
        "    return httpx.get('/health')\n"
        "\n"
        "def external():\n"
        "    return httpx.get('https://api.github.com/users/octocat')\n"
        "\n"
        "def unmatched():\n"
        "    return httpx.get('/nothing/here')\n"
        "\n"
        "def literal_me():\n"
        "    return httpx.get('http://users/users/me')\n"
    )
    workspace, service_a, repo_b = _workspace(tmp_path, client)
    health = "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health():\n    return 1\n"
    _write(service_a / "app" / "health.py", health)
    other = workspace / "service_c"
    _make_repo(other)
    _write(other / "health.py", health)
    result = build_or_update_graph(
        full_rebuild=True,
        repo_root=str(workspace),
        roots=[str(service_a), str(repo_b), str(other)],
    )
    stats = result["http_endpoints"]
    assert stats["ambiguous"] == 1
    assert stats["external"] == 1
    assert stats["unmatched"] == 1
    store = GraphStore(workspace / ".crg" / "graph.db")
    try:
        edges = _calls_endpoint_edges(store)
        # Only the literal /users/me call links, and it prefers the
        # literal route over the parameterised one.
        assert len(edges) == 1
        assert edges[0]["source_qualified"].endswith("::literal_me")
        assert edges[0]["target_qualified"].endswith("::GET /users/me")
    finally:
        store.close()


def test_single_repo_build_links_and_relinks_idempotently(tmp_path: Path) -> None:
    repo = tmp_path / "mono"
    _make_repo(repo)
    (repo / ".crg").mkdir()
    _write(
        repo / "web" / "routes" / "users.js",
        'const express = require("express");\n'
        "const router = express.Router();\n"
        "function show(req, res) {}\n"
        'router.get("/:id", show);\n'
        "module.exports = router;\n",
    )
    _write(
        repo / "web" / "app.js",
        'const express = require("express");\n'
        'const users = require("./routes/users");\n'
        "const app = express();\n"
        'app.use("/api/users", users);\n',
    )
    _write(
        repo / "ui" / "load.js",
        "export function load(id) {\n"
        "  return fetch(`/api/users/${id}`);\n"
        "}\n"
        "export function stale(id) {\n"
        "  return fetch(`/users/${id}`);\n"
        "}\n",
    )
    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        result = full_build(repo, store)
        assert result["http_endpoints"]["linked"] == 1
        assert result["http_endpoints"]["cross_repo"] == 0
        edges = _calls_endpoint_edges(store)
        assert len(edges) == 1
        assert edges[0]["source_qualified"].endswith("load.js::load")
        assert edges[0]["target_qualified"].endswith("users.js::GET /{id}")

        endpoint = store._conn.execute(
            "SELECT extra FROM nodes WHERE kind = 'Endpoint'"
        ).fetchone()
        assert json.loads(endpoint["extra"])["effective_paths"] == ["/api/users/{id}"]

        again = link_http_endpoints(store)
        assert again["linked"] == 1
        assert len(_calls_endpoint_edges(store)) == 1
    finally:
        store.close()


def test_link_pass_on_empty_graph(tmp_path: Path) -> None:
    store = GraphStore(tmp_path / "g.db")
    try:
        stats = link_http_endpoints(store)
    finally:
        store.close()
    assert stats == {
        "endpoints": 0,
        "calls": 0,
        "linked": 0,
        "cross_repo": 0,
        "ambiguous": 0,
        "unmatched": 0,
        "dynamic": 0,
        "external": 0,
        "handlers_bound": 0,
    }


# ---------------------------------------------------------------------------
# Link pass edge cases on hand-built graph rows
# ---------------------------------------------------------------------------


def _endpoint_node(
    file_path: str, method: str, path: str, line: int = 1, **extra
) -> NodeInfo:
    return NodeInfo(
        "Endpoint",
        f"{method} {path}",
        file_path,
        line,
        line,
        "python",
        extra={"http_method": method, "path": path, "raw_path": path, **extra},
    )


def _caller(file_path: str, name: str, calls: list) -> NodeInfo:
    return NodeInfo(
        "Function", name, file_path, 1, 5, "python", extra={"http_calls": calls}
    )


def _call(method: str, path: str, line: int = 2) -> dict:
    return {"method": method, "path": path, "confidence": 1.0, "line": line}


def test_link_pass_skips_malformed_rows_and_unknown_mounts(tmp_path: Path) -> None:
    routes = str(tmp_path / "routes.py")
    deep = str(tmp_path / "deep.py")
    client = str(tmp_path / "client.py")
    chain = {f"r{i}": {"kind": "router", "prefix": ""} for i in range(8)}
    store = GraphStore(tmp_path / "g.db")
    try:
        for node in (
            NodeInfo(
                "File",
                routes,
                routes,
                1,
                1,
                "python",
                extra={
                    "http_routers": {
                        "app": {"kind": "app", "prefix": ""},
                        "dyn": {"kind": "router", "prefix": None},
                        "loose": {"kind": "router", "prefix": "/loose"},
                        "cyc_a": {"kind": "router", "prefix": "/a"},
                        "cyc_b": {"kind": "router", "prefix": "/b"},
                        "solo": {"kind": "router", "prefix": "/solo"},
                    },
                    "http_mounts": [
                        "not-a-mount",
                        {"parent": "app", "prefix": None, "child": "loose"},
                        {"parent": "ghost", "prefix": "/g", "child": "loose"},
                        {"parent": 7, "prefix": "/n", "child": "loose"},
                        {"parent": "cyc_b", "prefix": "", "child": "cyc_a"},
                        {"parent": "cyc_a", "prefix": "", "child": "cyc_b"},
                        {"parent": "app", "prefix": "/x", "child": None},
                    ],
                },
            ),
            NodeInfo(
                "File",
                deep,
                deep,
                1,
                1,
                "python",
                extra={
                    "http_routers": chain,
                    "http_mounts": [
                        {"parent": f"r{i + 1}", "prefix": f"/p{i}", "child": f"r{i}"}
                        for i in range(7)
                    ],
                },
            ),
            NodeInfo(
                "File",
                str(tmp_path / "odd.py"),
                str(tmp_path / "odd.py"),
                1,
                1,
                "python",
                extra={"http_routers": ["app"], "http_mounts": {"parent": "app"}},
            ),
            # No router at all: the stored path is used as is.
            _endpoint_node(routes, "GET", "/plain"),
            # A router missing from http_routers behaves like an unmounted app.
            _endpoint_node(routes, "GET", "/ghost", router="ghost", router_kind="app"),
            # A dynamic router prefix can never be matched.
            _endpoint_node(
                routes, "GET", "/hidden", router="dyn", router_kind="router"
            ),
            # Only invalid mounts point at "loose": its prefix is unknown.
            _endpoint_node(
                routes, "GET", "/loose/l", router="loose", router_kind="router"
            ),
            # A router that is never mounted is matched with lower confidence.
            _endpoint_node(
                routes, "GET", "/solo/s", router="solo", router_kind="router"
            ),
            # A mount cycle gives no prefix.
            _endpoint_node(routes, "GET", "/a/c", router="cyc_a", router_kind="router"),
            # More than five nested mounts are not followed.
            _endpoint_node(deep, "GET", "/deep", router="r0", router_kind="router"),
            # All-parameter routes would match anything and are never linked.
            _endpoint_node(routes, "GET", "/{anything}"),
            _endpoint_node(routes, "POST", "/only-post"),
            NodeInfo(
                "Endpoint",
                "GET /no-method",
                routes,
                1,
                1,
                "python",
                extra={"path": "/no-method"},
            ),
            _caller(
                client,
                "load",
                [
                    "not-a-call",
                    _call("GET", "/plain"),
                    _call("GET", "/ghost"),
                    _call("GET", "/hidden"),
                    _call("GET", "/loose/l"),
                    _call("GET", "/solo/s"),
                    _call("GET", "/a/c"),
                    _call("GET", "/deep"),
                    _call("GET", "/whatever"),
                    _call("GET", "/only-post"),
                    _call("GET", "/no-method"),
                ],
            ),
            NodeInfo("Function", "broken", client, 6, 8, "python"),
            NodeInfo("Function", "listy", client, 9, 9, "python"),
        ):
            store.upsert_node(node)
        store._conn.execute(
            "UPDATE nodes SET extra = ? WHERE name = 'broken'",
            ('{"http_calls": [',),
        )
        store._conn.execute(
            "UPDATE nodes SET extra = ? WHERE name = 'listy'",
            ('["http_calls"]',),
        )
        store.commit()

        stats = link_http_endpoints(store)
        linked = {
            row["target_qualified"].rsplit("::", 1)[-1]: row["confidence"]
            for row in _calls_endpoint_edges(store)
        }
        effective = {
            row["name"]: json.loads(row["extra"])["effective_paths"]
            for row in store._conn.execute(
                "SELECT name, extra FROM nodes WHERE kind = 'Endpoint' "
                "AND name != 'GET /no-method'"
            )
        }
    finally:
        store.close()

    assert linked == {"GET /plain": 1.0, "GET /ghost": 1.0, "GET /solo/s": 0.7}
    assert effective["GET /solo/s"] == ["/solo/s"]
    for name in ("GET /hidden", "GET /loose/l", "GET /a/c", "GET /deep"):
        assert effective[name] == [], name
    assert stats["endpoints"] == 9
    assert stats["calls"] == 10
    assert stats["linked"] == 3
    assert stats["unmatched"] == 7


def test_endpoint_matched_through_two_mounts_keeps_its_best_score(
    tmp_path: Path,
) -> None:
    routes = str(tmp_path / "routes.py")
    client = str(tmp_path / "client.py")
    store = GraphStore(tmp_path / "g.db")
    try:
        for node in (
            NodeInfo(
                "File",
                routes,
                routes,
                1,
                1,
                "python",
                extra={
                    "http_routers": {
                        "app": {"kind": "app", "prefix": ""},
                        "shared": {"kind": "router", "prefix": ""},
                    },
                    "http_mounts": [
                        {"parent": "app", "prefix": "/{x}/b/c", "child": "shared"},
                        {"parent": "app", "prefix": "/a/{y}/{z}", "child": "shared"},
                    ],
                },
            ),
            # Served as /{x}/b/c and /a/{y}/{z}: a call to /a/b/c matches the
            # first with two literal segments and the second with one.
            _endpoint_node(routes, "GET", "/", router="shared", router_kind="router"),
            # Matches /a/b/c with one literal segment only.
            _endpoint_node(routes, "GET", "/{p}/{q}/c"),
            _caller(client, "load", [_call("GET", "/a/b/c")]),
        ):
            store.upsert_node(node)
        store.commit()

        stats = link_http_endpoints(store)
        linked = [
            row["target_qualified"].rsplit("::", 1)[-1]
            for row in _calls_endpoint_edges(store)
        ]
        effective = json.loads(
            store._conn.execute(
                "SELECT extra FROM nodes WHERE kind = 'Endpoint' AND name = 'GET /'"
            ).fetchone()["extra"]
        )["effective_paths"]
    finally:
        store.close()

    assert effective == ["/a/{y}/{z}", "/{x}/b/c"]
    # The weaker second match of the mounted endpoint must not replace its
    # stronger first one, or it would tie with /{p}/{q}/c and link nothing.
    assert linked == ["GET /"]
    assert stats["linked"] == 1
    assert stats["ambiguous"] == 0


def test_imported_route_handlers_are_bound_after_the_build(tmp_path: Path) -> None:
    repo = tmp_path / "mono"
    _make_repo(repo)
    (repo / ".crg").mkdir()
    _write(
        repo / "web" / "controllers" / "users.js",
        "export function listUsers(req, res) {}\n",
    )
    _write(repo / "web" / "other.js", "export function listUsers() {}\n")
    _write(
        repo / "web" / "app.js",
        'import express from "express";\n'
        'import { listUsers } from "./controllers/users";\n'
        'import { helper } from "some-package";\n'
        "const app = express();\n"
        'app.get("/users", listUsers);\n'
        'app.get("/helper", helper);\n',
    )
    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        result = full_build(repo, store)
        bound = store._conn.execute(
            "SELECT source_qualified, target_qualified FROM edges "
            "WHERE kind = 'ROUTES_TO' AND resolution = 'http_handler'"
        ).fetchall()
    finally:
        store.close()
    assert result["http_endpoints"]["handlers_bound"] == 1
    assert len(bound) == 1
    assert bound[0]["source_qualified"].endswith("app.js::GET /users")
    assert bound[0]["target_qualified"].endswith("users.js::listUsers")


def test_handler_defined_twice_in_target_file_is_not_bound(tmp_path: Path) -> None:
    controllers = str(tmp_path / "controllers.js")
    app = str(tmp_path / "app.js")
    store = GraphStore(tmp_path / "g.db")
    try:
        for node in (
            NodeInfo("Function", "show", controllers, 1, 1, "javascript"),
            NodeInfo(
                "Function", "show", controllers, 2, 2, "javascript", parent_name="A"
            ),
            _endpoint_node(
                app,
                "GET",
                "/show",
                router="app",
                router_kind="app",
                handler_ref={"name": "show", "file": controllers},
            ),
            _endpoint_node(
                app,
                "GET",
                "/odd",
                router="app",
                router_kind="app",
                handler_ref="show",
            ),
        ):
            store.upsert_node(node)
        store.commit()
        stats = link_http_endpoints(store)
    finally:
        store.close()
    assert stats["handlers_bound"] == 0


APP_JS = """\
import express from "express";
import { listUsers } from "./controllers";
const app = express();
app.get("{path}", listUsers);
"""


def _http_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "mono"
    _make_repo(repo)
    (repo / ".crg").mkdir()
    _write(repo / "web" / "controllers.js", "export function listUsers(req, res) {}\n")
    _write(repo / "web" / "app.js", APP_JS.replace("{path}", "/users"))
    _write(
        repo / "ui" / "load.js",
        'export function load() {\n  return fetch("/users");\n}\n',
    )
    return repo.resolve()


def _http_graph(store: GraphStore) -> dict[str, list[str]]:
    """Endpoint names and the targets of every HTTP edge in ``store``."""
    endpoints = store._conn.execute(
        "SELECT name FROM nodes WHERE kind = 'Endpoint'"
    ).fetchall()
    edges = store._conn.execute(
        "SELECT kind, resolution, target_qualified FROM edges "
        "WHERE kind IN ('CALLS_ENDPOINT', 'ROUTES_TO')"
    ).fetchall()
    graph: dict[str, list[str]] = {"endpoints": sorted(r["name"] for r in endpoints)}
    for row in edges:
        key = f"{row['kind']}:{row['resolution']}"
        graph.setdefault(key, []).append(row["target_qualified"].rsplit("::", 1)[-1])
    return graph


def test_incremental_update_drops_links_of_changed_and_deleted_endpoints(
    tmp_path: Path,
) -> None:
    repo = _http_repo(tmp_path)
    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        full_build(repo, store)
        assert _http_graph(store) == {
            "endpoints": ["GET /users"],
            "CALLS_ENDPOINT:http_route": ["GET /users"],
            "ROUTES_TO:http_handler": ["listUsers"],
        }

        # The route moves: the old Endpoint and the call linked to it go away.
        _write(repo / "web" / "app.js", APP_JS.replace("{path}", "/people"))
        incremental_update(repo, store, changed_files=["web/app.js"])
        assert _http_graph(store) == {
            "endpoints": ["GET /people"],
            "ROUTES_TO:http_handler": ["listUsers"],
        }

        # The handler's file is deleted: its cross-file binding goes with it.
        (repo / "web" / "controllers.js").unlink()
        incremental_update(repo, store, changed_files=["web/controllers.js"])
        assert _http_graph(store) == {"endpoints": ["GET /people"]}

        # The route file is deleted: no Endpoint and no edge to one remain.
        (repo / "web" / "app.js").unlink()
        incremental_update(repo, store, changed_files=["web/app.js"])
        assert _http_graph(store) == {"endpoints": []}
    finally:
        store.close()


def test_watcher_events_drop_links_of_changed_and_deleted_endpoints(
    tmp_path: Path,
) -> None:
    repo = _http_repo(tmp_path)
    store = GraphStore(repo / ".crg" / "graph.db")
    try:
        full_build(repo, store)
        handler = GraphUpdateHandler(repo, store, CodeParser(), [])
        app = repo / "web" / "app.js"

        _write(app, APP_JS.replace("{path}", "/people"))
        handler._update_file(str(app))
        assert _http_graph(store) == {
            "endpoints": ["GET /people"],
            "ROUTES_TO:http_handler": ["listUsers"],
        }

        app.unlink()
        handler.on_deleted(SimpleNamespace(is_directory=False, src_path=str(app)))
        assert _http_graph(store) == {"endpoints": []}
    finally:
        store.close()
