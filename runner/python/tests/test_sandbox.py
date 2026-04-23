import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from sandbox import ResourceExhausted, RunnerTimeout, run_python_code  # noqa: E402


def test_basic_roundtrip():
    r = run_python_code(
        code="outputs['y'] = inputs['x'] * 2",
        inputs={"x": 3}, timeout=5, memory_limit=128 * 1024 * 1024,
    )
    assert r.outputs == {"y": 6}


def test_main_return_value_fallback():
    r = run_python_code(
        code="def main(i):\n    return {'z': i['a'] + i['b']}\n",
        inputs={"a": 1, "b": 2}, timeout=5, memory_limit=128 * 1024 * 1024,
    )
    assert r.outputs == {"z": 3}


def test_stdout_captured():
    r = run_python_code(
        code="print('hello'); outputs['x'] = 1",
        inputs={}, timeout=5, memory_limit=128 * 1024 * 1024,
    )
    assert "hello" in r.stdout
    assert r.outputs == {"x": 1}


def test_timeout_raises():
    with pytest.raises(RunnerTimeout):
        run_python_code(
            code="import time; time.sleep(5)",
            inputs={}, timeout=0.3, memory_limit=128 * 1024 * 1024,
        )


def test_user_exception_surfaces():
    with pytest.raises(RuntimeError, match="exited"):
        run_python_code(
            code="raise ValueError('oops')",
            inputs={}, timeout=5, memory_limit=128 * 1024 * 1024,
        )
