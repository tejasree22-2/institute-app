"""Sandboxed Python execution shared by verify / run / submit.

Each execution gets its own temp dir, an empty environment (so the API's secrets never reach
student code), a wall-clock timeout, a stdout cap and rlimits on memory, processes and file size,
and runs inside the unprivileged sandbox in services/sandbox.py (Landlock + seccomp: no access to
the DB or app files, no network, can't signal the API). That needs no root, so it works on a Render
native Python service.

settings.sandbox_mode decides what happens when the kernel can't provide the sandbox:
"required" (production default) refuses to run code, "best-effort" (local default) runs it with
only the limits above. check_sandbox() tests it once at startup; /health reports the result.
"""
import logging
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass

from fastapi import HTTPException

from ..config import settings
from . import sandbox

log = logging.getLogger(__name__)

# executions run in FastAPI's thread pool; cap how many run at once so a burst can't exhaust the box
_slots = threading.BoundedSemaphore(settings.exec_max_concurrent)

_CHILD_ENV = {"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"}

# filled in by check_sandbox(): the Landlock ABI to use, or 0 when running without the sandbox
_sandbox_abi = 0
sandbox_status = "not checked"


@dataclass
class TestCaseInput:
    id: int
    stdin: str
    expected_stdout: str
    is_hidden: bool


@dataclass
class TestResult:
    test_case_id: int
    passed: bool
    hidden: bool
    actual_output: str
    error: str | None
    runtime_ms: int


def _set_limit(kind: int, value: int):
    try:
        resource.setrlimit(kind, (value, value))
    except (ValueError, OSError):
        pass  # not all platforms allow every limit; the timeout still applies


def _child_setup(run_dir: str, abi: int):
    def setup():
        mem_bytes = settings.exec_memory_limit_mb * 1024 * 1024
        _set_limit(resource.RLIMIT_AS, mem_bytes)
        _set_limit(resource.RLIMIT_FSIZE, settings.exec_max_file_bytes)
        _set_limit(resource.RLIMIT_CORE, 0)
        _set_limit(resource.RLIMIT_CPU, settings.exec_timeout_seconds + 1)
        _set_limit(resource.RLIMIT_NPROC, settings.exec_max_processes)
        if abi:
            sandbox.apply(run_dir, abi)
    return setup


def _run_one(code_path: str, stdin_text: str, abi: int) -> tuple[str, str | None, int]:
    run_dir = os.path.dirname(code_path)
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            [sandbox.interpreter(), "-I", "-S", code_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=run_dir,
            env={**_CHILD_ENV, "TMPDIR": run_dir, "HOME": run_dir},
            start_new_session=True,
            preexec_fn=_child_setup(run_dir, abi),
        )
    except subprocess.SubprocessError:
        log.exception("sandbox setup failed")
        raise HTTPException(status_code=503, detail="The code runner is unavailable — please tell your instructor")
    try:
        stdout, stderr = proc.communicate(stdin_text, timeout=settings.exec_timeout_seconds)
    except subprocess.TimeoutExpired:
        # kill the whole process group so forked children don't outlive the run
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return "", "Timed out", int((time.monotonic() - start) * 1000)
    runtime_ms = int((time.monotonic() - start) * 1000)
    stdout = stdout[: settings.exec_stdout_cap_bytes]
    error = stderr.strip()[-2000:] if proc.returncode != 0 else None
    if proc.returncode == -signal.SIGSYS:
        error = "Blocked: the program used an operation that isn't allowed here"
    return stdout, error, runtime_ms


def check_sandbox():
    """Run a tiny program inside the sandbox once at startup and remember whether it works."""
    global _sandbox_abi, sandbox_status
    abi = sandbox.landlock_abi()
    if not abi:
        _sandbox_abi, sandbox_status = 0, "unavailable: kernel has no Landlock"
    else:
        try:
            out, err, _ = _run_in_dir("print(6 * 7)", "", abi)
            ok = out.strip() == "42" and err is None
            _sandbox_abi = abi if ok else 0
            sandbox_status = f"ok (Landlock ABI {abi} + seccomp)" if ok else f"unavailable: self-test failed: {err or out!r}"
        except Exception as exc:  # noqa: BLE001 — any failure means no sandbox
            _sandbox_abi, sandbox_status = 0, f"unavailable: {exc}"
    level = logging.INFO if _sandbox_abi else logging.WARNING
    log.log(level, "code sandbox %s (mode: %s)", sandbox_status, settings.sandbox_mode)


def _run_in_dir(code: str, stdin_text: str, abi: int) -> tuple[str, str | None, int]:
    os.makedirs(settings.runner_workdir, exist_ok=True)
    run_dir = tempfile.mkdtemp(prefix=f"run-{uuid.uuid4().hex}-", dir=settings.runner_workdir)
    try:
        code_path = os.path.join(run_dir, "solution.py")
        with open(code_path, "w") as f:
            f.write(code)
        return _run_one(code_path, stdin_text, abi)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def run_test_cases(code: str, test_cases: list[TestCaseInput]) -> list[TestResult]:
    if not _sandbox_abi and settings.sandbox_mode == "required":
        raise HTTPException(status_code=503, detail="The code runner is unavailable — please tell your instructor")
    with _slots:
        return _run_test_cases(code, test_cases)


def _run_test_cases(code: str, test_cases: list[TestCaseInput]) -> list[TestResult]:
    os.makedirs(settings.runner_workdir, exist_ok=True)
    run_dir = tempfile.mkdtemp(prefix=f"run-{uuid.uuid4().hex}-", dir=settings.runner_workdir)
    results: list[TestResult] = []
    try:
        code_path = os.path.join(run_dir, "solution.py")
        with open(code_path, "w") as f:
            f.write(code)

        for tc in test_cases:
            actual, error, runtime_ms = _run_one(code_path, tc.stdin, _sandbox_abi)
            passed = error is None and actual.rstrip() == tc.expected_stdout.rstrip()
            results.append(TestResult(
                test_case_id=tc.id,
                passed=passed,
                hidden=tc.is_hidden,
                actual_output=actual,
                error=error,
                runtime_ms=runtime_ms,
            ))
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)

    return results


def strip_hidden_details(results: list[TestResult]) -> list[TestResult]:
    """For results returned to a student: hidden cases keep only passed/runtime_ms."""
    stripped = []
    for r in results:
        if r.hidden:
            stripped.append(TestResult(
                test_case_id=r.test_case_id,
                passed=r.passed,
                hidden=True,
                actual_output=None,
                error=None,
                runtime_ms=r.runtime_ms,
            ))
        else:
            stripped.append(r)
    return stripped
