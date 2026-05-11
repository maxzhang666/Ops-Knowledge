# Stub magika before any module imports markitdown (magika/onnxruntime
# unavailable on some platforms — e.g. Amazon Linux 2 has no onnxruntime
# wheel for the system glibc).
#
# markitdown's MarkItDown.__init__ unconditionally calls `magika.Magika()`,
# and `convert_stream` calls `_magika.identify_stream(...)` even when a
# `file_extension=` is supplied (it tries to enrich the guess). So the
# stub must (a) be instantiable, (b) accept arbitrary identify_* calls,
# and (c) return an object whose `status != "ok"` so markitdown falls
# back to the extension-based path.
#
# Using MagicMock for the result object: any attribute access (including
# the new magika 2.x shape `result.prediction.output.label`) yields a
# MagicMock instead of crashing — and `result.status == "ok"` short-circuits
# the only branch markitdown actually walks because we explicitly set
# status to "error".
import sys
import types
from unittest.mock import MagicMock

if "magika" not in sys.modules:
    class _NoopMagika:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, _name):
            def _identify(*_a, **_kw):
                result = MagicMock()
                result.status = "error"  # not "ok" → markitdown skips this guess
                result.ok = False         # magika 1.x back-compat
                result.score = 0.0
                return result
            return _identify

    _mod = types.ModuleType("magika")
    _mod.Magika = _NoopMagika  # type: ignore[attr-defined]
    sys.modules["magika"] = _mod
    sys.modules["magika.content_types"] = types.ModuleType("magika.content_types")
    sys.modules["magika.types"] = types.ModuleType("magika.types")
