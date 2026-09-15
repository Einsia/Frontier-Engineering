"""Compile the allocator to Wasm64 and score it with a separate trusted driver."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from candidate_sandbox import CANDIDATE_RUNTIME_ENV, namespace_command

SUPPORT = Path(__file__).resolve().with_name("malloc_wasm")
TRACES = (
    "amptjp-bal.rep", "cccp-bal.rep", "cp-decl-bal.rep", "expr-bal.rep",
    "coalescing-bal.rep", "random-bal.rep", "random2-bal.rep", "binary-bal.rep",
    "binary2-bal.rep", "realloc-bal.rep", "realloc2-bal.rep",
)


def _setup_module():
    spec = importlib.util.spec_from_file_location("frontier_malloc_setup", SUPPORT / "setup.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(command, work: Path, readable, timeout: float):
    env = {key: os.environ[key] for key in CANDIDATE_RUNTIME_ENV if key in os.environ}
    env["OMP_NUM_THREADS"] = "1"

    def limits():
        os.setsid()
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 << 20, 32 << 20))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        resource.setrlimit(resource.RLIMIT_CPU, (int(timeout) + 5, int(timeout) + 5))

    with tempfile.TemporaryDirectory(prefix="malloc_logs_") as log_dir:
        out = Path(log_dir) / "stdout"
        err = Path(log_dir) / "stderr"
        with out.open("wb") as stdout, err.open("wb") as stderr:
            proc = subprocess.Popen(
                namespace_command(command, work, readonly_paths=readable),
                cwd=work, env=env, stdout=stdout, stderr=stderr,
                stdin=subprocess.DEVNULL, preexec_fn=limits,
            )
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                raise TimeoutError(f"Malloc evaluation exceeded {timeout:g} seconds") from None
        stdout_text = out.read_text(errors="replace")
        stderr_text = err.read_text(errors="replace")
        if proc.returncode:
            if "wasm trap: interrupt" in stderr_text:
                raise TimeoutError("allocator call exceeded the one-second execution deadline")
            raise ValueError(f"process exited {proc.returncode}: {stderr_text[-12000:]}")
        return stdout_text, stderr_text


def _metrics(report: dict) -> dict:
    if report.get("schema") != "malloc_wasm64.v1":
        raise ValueError("unexpected trusted driver result schema")
    traces = report.get("traces")
    if not isinstance(traces, list) or [t.get("name") for t in traces] != list(TRACES):
        raise ValueError("incomplete trusted driver result")
    passed, util, seconds, operations = 0, 0.0, 0.0, 0
    for trace in traces:
        if trace.get("valid") not in (0, 1):
            raise ValueError("invalid trace verdict")
        if not trace["valid"]:
            continue
        u, t, n = trace["utilization"], trace["runtime_s"], trace["operations"]
        if not (math.isfinite(u) and 0 <= u <= 1 and math.isfinite(t) and t > 0):
            raise ValueError("invalid measured utilization or runtime")
        if type(n) is not int or n <= 0:
            raise ValueError("invalid measured operation count")
        passed += 1
        util += u
        seconds += t
        operations += n
    throughput = operations / seconds if seconds else 0.0
    util_points = 60.0 * util / len(TRACES)
    thru_points = 40.0 * min(1.0, throughput / 10_000_000.0)
    score = (util_points + thru_points) * passed / len(TRACES)
    return {
        "combined_score": score, "score_100": score, "score_ratio": score / 100,
        "valid": float(passed > 0), "timeout": 0.0,
        "testcases_passed": passed, "testcases_total": len(TRACES),
        "testcase_pass_rate": passed / len(TRACES), "errors": len(TRACES) - passed,
        "util_points": util_points, "thru_points": thru_points,
        "throughput_ops_s": throughput, "allocator_runtime_s": seconds,
        "isolated_candidate": 1.0,
    }


def evaluate(program: Path, benchmark: Path) -> tuple[dict, dict]:
    started = time.monotonic()
    artifacts = {}
    metrics = {"combined_score": 0.0, "valid": 0.0, "timeout": 0.0}
    try:
        program, benchmark = Path(program).resolve(), Path(benchmark).resolve()
        if program.stat().st_size > 2 << 20:
            raise ValueError("candidate C source exceeds 2 MiB")
        source = program.read_bytes()
        if not source or len(source) > 2 << 20:
            raise ValueError("candidate C source must be between 1 byte and 2 MiB")
        artifacts["candidate_sha256"] = hashlib.sha256(source).hexdigest()
        setup = _setup_module()
        toolchain = setup.resolve()
        artifacts["toolchain"] = {
            "compiler": setup.WASI_DIRECTORY, "runtime": setup.WASMTIME_DIRECTORY,
        }
        artifacts["driver_source_sha256"] = hashlib.sha256(
            (SUPPORT / "host.c").read_bytes()
        ).hexdigest()
        artifacts["guest_runtime_sha256"] = hashlib.sha256(
            (SUPPORT / "guest.c").read_bytes()
        ).hexdigest()
        handout = benchmark / "malloclab-handout"
        with tempfile.TemporaryDirectory(prefix="malloc_wasm_") as directory:
            work = Path(directory).resolve()
            staged = work / "candidate.c"
            staged.write_bytes(source)
            headers = work / "headers"
            headers.mkdir()
            for name in ("mm.h", "memlib.h"):
                shutil.copyfile(handout / name, headers / name)
            wasm = work / "candidate.wasm"
            _run(
                setup.compile_command(staged, wasm, headers, toolchain=toolchain),
                work, [toolchain.clang.parent.parent, SUPPORT], 60,
            )
            artifacts["module_sha256"] = hashlib.sha256(wasm.read_bytes()).hexdigest()
            cc = shutil.which("cc") or shutil.which("gcc")
            if not cc:
                raise ValueError("a native C compiler is required for the trusted driver")
            host = work / "malloc_host"
            _, warnings = _run(
                [cc, "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I", str(toolchain.wasmtime / "include"), str(SUPPORT / "host.c"),
                 "-L", str(toolchain.wasmtime / "lib"),
                 "-Wl,-rpath," + str(toolchain.wasmtime / "lib"),
                 "-lwasmtime", "-lpthread", "-lm", "-o", str(host)],
                work, [toolchain.wasmtime, SUPPORT], 60,
            )
            if warnings:
                artifacts["driver_build_log"] = warnings
            output, diagnostics = _run(
                [str(host), str(wasm), str(handout / "traces")],
                work, [toolchain.wasmtime, handout / "traces"], 180,
            )
            report = json.loads(output)
            metrics = _metrics(report)
            artifacts["trace_results"] = report
            if diagnostics:
                artifacts["driver_log"] = diagnostics
    except TimeoutError as exc:
        metrics.update(timeout=1.0, error_message=str(exc))
    except Exception as exc:
        metrics["error_message"] = str(exc)
    metrics["runtime_s"] = time.monotonic() - started
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--metrics-out", required=True, type=Path)
    parser.add_argument("--details-out", type=Path)
    args = parser.parse_args()
    metrics, artifacts = evaluate(args.candidate, args.benchmark)
    args.metrics_out.write_text(json.dumps(metrics, indent=2) + "\n")
    if args.details_out:
        args.details_out.write_text(json.dumps(artifacts, indent=2) + "\n")
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
