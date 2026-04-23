import pytest

from app.workflow.nodes.base import AbstractNode, NodeManifest
from app.workflow.nodes.registry import (
    NodeRegistry,
    load_builtin_nodes,
    registry,
)


class _A(AbstractNode):
    manifest = NodeManifest(type="test.a", category="extension", name="A")


class _B(AbstractNode):
    manifest = NodeManifest(
        type="test.a", category="extension", name="A-v2", type_version="2.0",
    )


def test_register_and_get():
    r = NodeRegistry()
    r.register(_A)
    r.register(_B)
    assert r.get("test.a").manifest.name == "A"
    assert r.get("test.a", "2.0").manifest.name == "A-v2"


def test_duplicate_rejected():
    r = NodeRegistry()
    r.register(_A)
    with pytest.raises(ValueError, match="already registered"):
        r.register(_A)


def test_missing_manifest_rejected():
    class Bad:
        pass
    r = NodeRegistry()
    with pytest.raises(TypeError, match="missing NodeManifest"):
        r.register(Bad)  # type: ignore[arg-type]


def test_load_builtin_discovers_example():
    load_builtin_nodes()  # idempotent
    assert any(
        cls.manifest.type == "builtin.echo" for cls in registry.list()
    )


def test_load_builtin_idempotent():
    before = len(registry.list())
    load_builtin_nodes()
    load_builtin_nodes()
    assert len(registry.list()) == before  # no duplicate registrations


def test_catalog_shape():
    load_builtin_nodes()
    cat = registry.catalog()
    assert all({"manifest", "io", "config_form"} <= set(e.keys()) for e in cat)


def test_grouped_catalog_ordering():
    load_builtin_nodes()
    groups = registry.grouped_catalog()
    # All groups carry category + nodes keys, category values are valid strings
    for g in groups:
        assert "category" in g and "nodes" in g
        assert isinstance(g["category"], str) and len(g["nodes"]) > 0
