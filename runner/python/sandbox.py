"""Sandboxed Python code executor.

Defense-in-depth:
- Outer: Docker container with read-only FS (except /tmp), non-root, network-
  isolated to the backend service via compose network.
- Inner (this file): each execute spawns a fresh `python -c` child with
  RLIMIT_AS / RLIMIT_CPU via preexec_fn, wall-clock timeout via
  subprocess.communicate(timeout=...), own session so we can SIGKILL the
  whole process tree on timeout.
"""
from __future__ import annotations

import json
import os
import resource
import signal
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from typing import Any

RUNNER_SENTINEL = "__RUNNER_OUTPUT__"


class RunnerTimeout(TimeoutError):
    pass


class ResourceExhausted(RuntimeError):
    pass


@dataclass
class RunResult:
    outputs: dict[str, Any]
    stdout: str
    stderr: str


_WRAPPER_TEMPLATE = textwrap.dedent("""
    import json, os, sys, traceback
    _inputs = json.loads(os.environ.get("RUNNER_INPUTS", "{{}}"))
    _outputs = {{}}
    try:
        _globals = {{"inputs": _inputs, "outputs": _outputs, "__name__": "__user_code__"}}
        exec(compile({code!r}, "<user_code>", "exec"), _globals)
        if callable(_globals.get("main")) and not _outputs:
            res = _globals["main"](_inputs)
            if isinstance(res, dict):
                _outputs = res
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)
    sys.stdout.write("\\n{sentinel}" + json.dumps(_outputs) + "\\n")
""").strip()


def _preexec(memory_limit: int, cpu_seconds: int) -> None:
    # RLIMIT_AS + RLIMIT_CPU are the primary guard. On Linux (production /
    # Docker) both are honored. On macOS dev RLIMIT_AS is unreliable — we
    # tolerate ValueError rather than fail the sandbox entirely; the outer
    # Docker container in production provides the real enforcement.
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    except (ValueError, OSError):
        pass
    # Do NOT call os.setsid() here — subprocess `start_new_session=True`
    # already does it. Calling twice raises PermissionError in preexec.


def run_python_code(
    *, code: str, inputs: dict[str, Any], timeout: float, memory_limit: int
) -> RunResult:
    cpu_seconds = max(1, int(timeout) + 1)
    env = dict(os.environ, RUNNER_INPUTS=json.dumps(inputs))
    wrapper = _WRAPPER_TEMPLATE.format(code=code, sentinel=RUNNER_SENTINEL)

    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", wrapper],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
            preexec_fn=lambda: _preexec(memory_limit, cpu_seconds),
            start_new_session=True,
        )
    except OSError as e:
        raise ResourceExhausted(str(e)) from e

    try:
        out_b, err_b = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise RunnerTimeout(f"wall-clock {timeout}s exceeded")

    stdout = out_b.decode("utf-8", errors="replace")
    stderr = err_b.decode("utf-8", errors="replace")

    if proc.returncode == -signal.SIGKILL or "MemoryError" in stderr:
        raise ResourceExhausted("memory or CPU limit exceeded")
    if proc.returncode != 0:
        raise RuntimeError(f"user code exited with {proc.returncode}: {stderr[:500]}")

    outputs: dict = {}
    pre_lines: list[str] = []
    for line in stdout.splitlines():
        if line.startswith(RUNNER_SENTINEL):
            try:
                outputs = json.loads(line[len(RUNNER_SENTINEL):] or "{}")
            except json.JSONDecodeError:
                outputs = {}
        else:
            pre_lines.append(line)
    return RunResult(outputs=outputs, stdout="\n".join(pre_lines), stderr=stderr)
