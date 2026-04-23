"""In-memory node registry. Populated at app startup by scanning
`app/workflow/nodes/`. Read by scheduler + `/workflow/nodes/registry` API.
"""
from __future__ import annotations

import importlib
import pkgutil
import threading
from typing import Type

from app.workflow.nodes.base import AbstractNode, BaseNode, NodeManifest


CATEGORY_ORDER = [
    "trigger", "knowledge", "llm", "agent", "logic",
    "extension", "output", "memory",
]


class NodeRegistry:
    def __init__(self) -> None:
        # Key: f"{type}@{version}"
        self._entries: dict[str, Type[BaseNode]] = {}
        self._lock = threading.Lock()

    def register(self, cls: Type[BaseNode]) -> None:
        if not hasattr(cls, "manifest") or not isinstance(cls.manifest, NodeManifest):
            raise TypeError(f"{cls!r} missing NodeManifest")
        key = self._key(cls.manifest.type, cls.manifest.type_version)
        with self._lock:
            if key in self._entries:
                raise ValueError(f"Node already registered: {key}")
            self._entries[key] = cls

    def unregister(self, node_type: str, version: str = "1.0") -> None:
        with self._lock:
            self._entries.pop(self._key(node_type, version), None)

    def get(self, node_type: str, version: str = "1.0") -> Type[BaseNode]:
        try:
            return self._entries[self._key(node_type, version)]
        except KeyError as e:
            raise KeyError(f"Unknown node type: {e}") from e

    def instance(self, node_type: str, version: str = "1.0") -> BaseNode:
        return self.get(node_type, version)()

    def list(self) -> list[Type[BaseNode]]:
        return list(self._entries.values())

    def catalog(self) -> list[dict]:
        out: list[dict] = []
        for cls in self.list():
            out.append({
                "manifest": cls.manifest.model_dump(),
                "io": cls.io.model_dump(),
                "config_form": cls.config_form.model_dump(by_alias=True),
            })
        return out

    def grouped_catalog(self) -> list[dict]:
        """Catalog grouped by category, ordered by CATEGORY_ORDER, then by name."""
        buckets: dict[str, list[dict]] = {}
        for entry in self.catalog():
            cat = entry["manifest"]["category"]
            buckets.setdefault(cat, []).append(entry)
        out: list[dict] = []
        for cat in CATEGORY_ORDER:
            items = buckets.pop(cat, [])
            if items:
                items.sort(key=lambda e: e["manifest"]["name"])
                out.append({"category": cat, "nodes": items})
        # Any unknown categories go last, alphabetically.
        for cat in sorted(buckets):
            items = buckets[cat]
            items.sort(key=lambda e: e["manifest"]["name"])
            out.append({"category": cat, "nodes": items})
        return out

    @staticmethod
    def _key(t: str, v: str) -> str:
        return f"{t}@{v}"


registry = NodeRegistry()


def load_builtin_nodes(package: str = "app.workflow.nodes") -> int:
    """Scan the given package and auto-register every AbstractNode subclass
    with a manifest. Idempotent — skips already-registered entries.
    Returns count of newly-registered nodes.
    """
    pkg = importlib.import_module(package)
    before = len(registry.list())
    for _, modname, is_pkg in pkgutil.walk_packages(pkg.__path__, prefix=f"{package}."):
        if is_pkg:
            continue
        # Skip the framework modules themselves.
        if modname.endswith(".base") or modname.endswith(".registry"):
            continue
        mod = importlib.import_module(modname)
        for obj in vars(mod).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, AbstractNode)
                and obj is not AbstractNode
                and hasattr(obj, "manifest")
                and isinstance(getattr(obj, "manifest", None), NodeManifest)
            ):
                key = NodeRegistry._key(obj.manifest.type, obj.manifest.type_version)
                if key not in registry._entries:
                    registry.register(obj)
    return len(registry.list()) - before
