# Stub magika before any module imports markitdown (magika/onnxruntime unavailable on some platforms)
import sys
import types

if "magika" not in sys.modules:
    _mod = types.ModuleType("magika")
    _mod.Magika = None  # type: ignore[attr-defined]
    sys.modules["magika"] = _mod
    sys.modules["magika.content_types"] = types.ModuleType("magika.content_types")
    sys.modules["magika.types"] = types.ModuleType("magika.types")
