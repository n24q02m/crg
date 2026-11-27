"""Tests for Go method_declaration, pointer receiver, and embedded struct bases."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from crg.parser import CodeParser


def test_go_method_and_embedded_struct_extraction() -> None:
    parser = CodeParser()
    code = b"""package svc

type Base struct{}
func (b Base) Ping() int { return helper() }

type Child struct {
    Base
    count int
}
func (c *Child) Pong() int { return helper() }
func helper() int { return 1 }
"""
    nodes, edges = parser.parse_bytes(Path("svc/app.go"), code)
    qnames = {(n.kind, n.name, n.parent_name) for n in nodes}
    assert ("Function", "Ping", "Base") in qnames
    assert ("Function", "Pong", "Child") in qnames
    assert ("Function", "helper", None) in qnames
    assert (
        "INHERITS",
        "svc\\app.go::Child" if "\\" in str(nodes[0].name) else "svc/app.go::Child",
        "Base",
    ) in {(e.kind, e.source, e.target) for e in edges}


def test_go_receiver_fallback_when_receiver_absent() -> None:
    parser = CodeParser()
    fake = SimpleNamespace(child_by_field_name=lambda _name: None)
    assert parser._get_go_receiver_type(fake) is None

    empty_recv = SimpleNamespace(
        child_by_field_name=lambda _name: SimpleNamespace(
            children=[SimpleNamespace(type="identifier", children=[])]
        )
    )
    assert parser._get_go_receiver_type(empty_recv) is None
