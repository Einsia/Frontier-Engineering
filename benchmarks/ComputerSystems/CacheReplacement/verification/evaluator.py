"""
CacheReplacement evaluator — 4-layer pipeline for ChampSim cache policy optimization.
"""

import argparse, json, math, os, re, shutil, subprocess, sys, time, traceback
from pathlib import Path

BENCHMARK_VERSION = "1.0.0"
CHAMPSIM_COMMIT = "51588e1d6f97875fe8de1a3621d28668bff83fcf"
STORAGE_BUDGET_BYTES = 65536
TIMEOUT_COMPILE = 300; TIMEOUT_QUICK_VERIFY = 120
TIMEOUT_PER_TRACE_QUICK = 600; TIMEOUT_PER_TRACE_FULL = 1800
WARMUP_QUICK = 10_000_000; SIM_QUICK = 20_000_000
WARMUP_FULL = 50_000_000; SIM_FULL = 100_000_000

FORBIDDEN_HEADERS = ["iostream","fstream","sstream","thread","mutex","future","shared_mutex","filesystem","unistd.h","fcntl.h","sys/stat.h","sys/mman.h","dlfcn.h","execinfo.h","signal.h","setjmp.h"]
FORBIDDEN_APIS = ["fopen","fread","fwrite","fclose","open(","read(","write(","close(","mmap(","munmap(","dlopen","dlsym","system(","popen","fork","pthread_","std::thread","std::async"]
FORBIDDEN_RANDOM = ["rand()","srand(","random_device","mt19937","default_random_engine","steady_clock","system_clock","time(","clock("]

# Layer 1: Source Validation

def _static_validation(cc_path: Path, h_path: Path | None) -> list[str]:
    errors = []
    cc_text = cc_path.read_text()
    if "// EVOLVE-BLOCK-START" not in cc_text: errors.append("Missing '// EVOLVE-BLOCK-START' in .cc file")
    if "// EVOLVE-BLOCK-END" not in cc_text: errors.append("Missing '// EVOLVE-BLOCK-END' in .cc file")
    s = cc_text.find("// EVOLVE-BLOCK-START"); e = cc_text.find("// EVOLVE-BLOCK-END")
    if s >= 0 and e >= 0 and s >= e: errors.append("EVOLVE-BLOCK-START must precede EVOLVE-BLOCK-END")
    for h in FORBIDDEN_HEADERS:
        if f"#include <{h}>" in cc_text: errors.append(f"Forbidden header: <{h}>")
    for api in FORBIDDEN_APIS:
        if api in cc_text: errors.append(f"Forbidden API: {api}")
    for rf in FORBIDDEN_RANDOM:
        if rf in cc_text: errors.append(f"Non-deterministic function: {rf}")
    dm_patterns = [r'\bnew\s+\w+', r'\bdelete\s+\[\]', r'\bdelete\s+\w+', r'\bmalloc\s*\(', r'\bfree\s*\(', r'\bcalloc\s*\(', r'\brealloc\s*\(']
    for pat in dm_patterns:
        if re.search(pat, cc_text): errors.append(f"Dynamic memory: {pat}")
    for dc in ["std::vector","std::map","std::unordered_map","std::set","std::list","std::deque"]:
        if dc in cc_text: errors.append(f"Dynamic container: {dc}")
    if h_path and h_path.is_file():
        h_text = h_path.read_text()
        hs = h_text.find("// EVOLVE-BLOCK-START"); he = h_text.find("// EVOLVE-BLOCK-END")
        if hs >= 0 and he >= 0:
            total = 0; type_sizes = {"uint8_t":1,"int8_t":1,"uint16_t":2,"int16_t":2,"uint32_t":4,"int32_t":4,"uint64_t":8,"int64_t":8,"bool":1,"char":1,"float":4,"double":8}
            block = h_text[hs+len("// EVOLVE-BLOCK-START"):he]
            for m in re.finditer(r'(uint\d+_t|int\d+_t|bool|char|float|double)\s+\w+\[(\d+)\]', block):
                total += type_sizes.get(m.group(1),4) * int(m.group(2))
            for m in re.finditer(r'std::array\s*<\s*(\w+)\s*,\s*(\d+)\s*>', block):
                total += type_sizes.get(m.group(1),4) * int(m.group(2))
            if total > STORAGE_BUDGET_BYTES:
                errors.append(f"Storage budget exceeded: ~{total} B > {STORAGE_BUDGET_BYTES} B (approximate check)")
    return errors

# Layer 2: Compile (cross-platform)

def _build_champsim(cd: Path, config_name: str = "my_policy_config") -> bool:
    """Configure and build ChampSim. Handles vcpkg on macOS and Linux."""
    cfg = cd / "config" / f"{config_name}.json"
    # Step 1: Run config.sh (generates Makefile + .csconfig)
    p1 = subprocess.run([sys.executable, str(cd/"config.sh"), str(cfg)], cwd=cd, capture_output=True, text=True, timeout=60)
    if p1.returncode != 0: return False
    # Step 2: Ensure vcpkg include path is in absolute.options
    # On Linux config.sh handles this; on macOS it may not.
    abs_opts = cd / "absolute.options"
    if abs_opts.is_file():
        vcpkg_incs = [str(p) for p in sorted((cd / "vcpkg_installed").glob("*/include"))]
        for inc in vcpkg_incs:
            if inc not in abs_opts.read_text():
                with open(abs_opts, "a") as f:
                    f.write(f" -isystem {inc}")
    # Step 3: Build
    p2 = subprocess.run(["make", "-j4"], cwd=cd, capture_output=True, text=True, timeout=TIMEOUT_COMPILE)
    return p2.returncode == 0

def _ensure_config(cd: Path, name: str, replacement: str):
    cfg = {"executable_name":"champsim","block_size":64,"page_size":4096,"heartbeat_frequency":10000000,"num_cores":1,
           "ooo_cpu":[{"frequency":4000,"ifetch_buffer_size":64,"decode_buffer_size":32,"dispatch_buffer_size":32,"register_file_size":128,"rob_size":352,"lq_size":128,"sq_size":72,"fetch_width":6,"decode_width":6,"dispatch_width":6,"execute_width":4,"lq_width":2,"sq_width":2,"retire_width":5,"mispredict_penalty":1,"scheduler_size":128,"decode_latency":1,"dispatch_latency":1,"schedule_latency":0,"execute_latency":0,"branch_predictor":"bimodal","btb":"basic_btb"}],
           "L1I":{"sets":64,"ways":8,"rq_size":64,"wq_size":64,"pq_size":8,"mshr_size":8,"latency":4,"max_tag_check":2,"max_fill":2},
           "L1D":{"sets":64,"ways":12,"rq_size":64,"wq_size":64,"pq_size":8,"mshr_size":16,"latency":5,"max_tag_check":2,"max_fill":2,"prefetch_as_load":False,"virtual_prefetch":False,"replacement":replacement},
           "L2C":{"sets":1024,"ways":8,"rq_size":32,"wq_size":32,"pq_size":16,"mshr_size":32,"latency":10,"max_tag_check":1,"max_fill":1,"prefetch_as_load":False,"virtual_prefetch":False,"replacement":replacement},
           "LLC":{"sets":2048,"ways":16,"rq_size":32,"wq_size":32,"pq_size":32,"mshr_size":64,"latency":20,"max_tag_check":1,"max_fill":1,"prefetch_as_load":False,"virtual_prefetch":False,"replacement":replacement}}
    (cd/"config").mkdir(exist_ok=True); (cd/"config"/f"{name}.json").write_text(json.dumps(cfg,indent=2))

# Layer 3: Quick Verify (uses verify_trace.xz, ~2M instructions, ~25s)

def _quick_verify(binary: Path, verify_trace: Path) -> tuple[bool, str]:
    """Quick sanity check. NOT used for scoring."""
    cmd = [str(binary), "--warmup-instructions", "1000000", "--simulation-instructions", "2000000", str(verify_trace)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_QUICK_VERIFY)
    if p.returncode != 0: return False, p.stderr[:500]
    ipc = _parse_ipc(p.stdout)
    return (True, p.stdout) if ipc and ipc > 0 else (False, f"Invalid IPC: {ipc}")

# Layer 4: Full Evaluation

def _run_trace(binary: Path, trace_path: Path, warmup: int, sim: int, timeout: int) -> dict:
    cmd = [str(binary), "--warmup-instructions", str(warmup), "--simulation-instructions", str(sim), str(trace_path)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0: return {"status":"failed","error":p.stderr[:200]}
        ipc = _parse_ipc(p.stdout)
        return ({"status":"ok","ipc":ipc} if ipc and ipc > 0 else {"status":"failed","error":f"invalid IPC: {ipc}"})
    except subprocess.TimeoutExpired: return {"status":"timeout"}

def _parse_ipc(output: str) -> float | None:
    for line in output.splitlines():
        m = re.search(r'cumulative IPC:\s+([\d.]+)', line)
        if m:
            try: return float(m.group(1))
            except ValueError: return None
    return None

def _get_baseline_ipcs(base_dir: Path, traces: list[str], warmup: int, sim: int) -> dict:
    ref_dir = base_dir / "references"; cache_file = ref_dir / "generated_baseline.json"
    if cache_file.is_file():
        data = json.loads(cache_file.read_text())
        if data.get("champsim_commit") == CHAMPSIM_COMMIT: return data.get("ipc_results", {})
    cd = base_dir / "data" / "ChampSim"
    _ensure_config(cd, "lru_baseline", "lru")
    if not _build_champsim(cd, "lru_baseline"): raise RuntimeError("Failed to build LRU baseline")
    binary = cd / "bin" / "champsim"; td = base_dir / "data" / "traces"
    to = TIMEOUT_PER_TRACE_FULL if sim == SIM_FULL else TIMEOUT_PER_TRACE_QUICK
    results = {}
    for t in traces:
        tf = td / f"{t}.champsimtrace.xz"
        if not tf.is_file(): continue
        r = _run_trace(binary, tf, warmup, sim, to)
        if r["status"] == "ok": results[t] = r["ipc"]
    ref_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"benchmark_version":BENCHMARK_VERSION,"champsim_commit":CHAMPSIM_COMMIT,"warmup":warmup,"simulation":sim,"ipc_results":results},indent=2))
    return results

# Main evaluate

def evaluate(candidate_path: str, *, mode: str = "quick", repo_root: Path | None = None) -> dict:
    start = time.time()
    metrics = {"benchmark_version":BENCHMARK_VERSION,"simulator_commit":CHAMPSIM_COMMIT,"valid":0.0,"score":0.0,"runtime_s":0.0,"compile_time_s":0.0,"simulation_time_s":0.0,"l1_static_pass":0.0,"l2_compile_pass":0.0,"l3_quick_verify_pass":0.0,"l4_eval_pass":0.0,"num_traces_completed":0,"num_traces_total":0,"mode":mode,"error":None}
    artifacts = {"per_trace_results":{}}
    try:
        repo = repo_root or _find_repo_root()
        base = repo / "benchmarks" / "ComputerSystems" / "CacheReplacement"
        cand = Path(candidate_path).expanduser().resolve()
        artifacts["candidate_path"] = str(cand)
        if mode == "quick":
            traces = ["605.mcf_s-665B","625.x264_s-18B","607.cactuBSSN_s-2421B"]
            warmup, sim, tto = WARMUP_QUICK, SIM_QUICK, TIMEOUT_PER_TRACE_QUICK
        else:
            traces = ["603.bwaves_s-3699B","605.mcf_s-665B","625.x264_s-18B","654.roms_s-842B","657.xz_s-3167B","600.perlbench_s-210B","602.gcc_s-734B","607.cactuBSSN_s-2421B","621.wrf_s-575B","631.deepsjeng_s-928B"]
            warmup, sim, tto = WARMUP_FULL, SIM_FULL, TIMEOUT_PER_TRACE_FULL
        if not cand.is_file(): metrics["error"] = "Candidate not found"; return _wrap(metrics, artifacts)
        h_path = (cand.parent / f"{cand.stem}.h") if (cand.parent / f"{cand.stem}.h").is_file() else cand.with_suffix(".h")
        se = _static_validation(cand, h_path if h_path.is_file() else None)
        artifacts["static_errors"] = se
        if se: metrics["error"] = f"Static validation: {'; '.join(se)}"; return _wrap(metrics, artifacts)
        metrics["l1_static_pass"] = 1.0
        cd = base / "data" / "ChampSim"; md = cd / "replacement" / "my_policy"
        md.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(cand), str(md / "my_policy.cc"))
        if h_path.is_file(): shutil.copy2(str(h_path), str(md / "my_policy.h"))
        else: (md / "my_policy.h").write_text('#ifndef REPLACEMENT_MY_POLICY_H\n#define REPLACEMENT_MY_POLICY_H\n#include <vector>\n#include "cache.h"\n#include "modules.h"\nstruct my_policy;\n#endif\n')
        t0 = time.perf_counter()
        _ensure_config(cd, "my_policy_config", "my_policy")
        if not _build_champsim(cd, "my_policy_config"): metrics["error"] = "Compilation failed"; return _wrap(metrics, artifacts)
        metrics["compile_time_s"] = time.perf_counter() - t0; metrics["l2_compile_pass"] = 1.0
        binary = cd / "bin" / "champsim"
        vt = base / "verification" / "verify_trace.xz"
        if vt.is_file():
            qok, qlog = _quick_verify(binary, vt); artifacts["quick_verify_log"] = qlog
            if not qok: metrics["error"] = "Quick verification failed"; return _wrap(metrics, artifacts)
        metrics["l3_quick_verify_pass"] = 1.0
        baseline_ipcs = _get_baseline_ipcs(base, traces, warmup, sim)
        if not baseline_ipcs: metrics["error"] = "Baseline generation failed"; return _wrap(metrics, artifacts)
        td = base / "data" / "traces"; metrics["num_traces_total"] = float(len(traces))
        t1 = time.perf_counter(); results = {}
        for trace_name in traces:
            tf = td / f"{trace_name}.champsimtrace.xz"
            results[trace_name] = _run_trace(binary, tf, warmup, sim, tto) if tf.is_file() else {"status":"failed","error":"trace not found"}
        metrics["simulation_time_s"] = time.perf_counter() - t1; artifacts["per_trace_results"] = results
        completed = {t:r for t,r in results.items() if r.get("status")=="ok"}
        metrics["num_traces_completed"] = float(len(completed))
        if completed:
            ratios = []
            for t,r in completed.items():
                bl = baseline_ipcs.get(t)
                if bl and bl > 0 and r.get("ipc",0) > 0: ratios.append(r["ipc"]/bl)
            if ratios:
                metrics["score"] = math.exp(sum(math.log(max(x,0.001)) for x in ratios)/len(ratios))
                metrics["valid"] = 1.0; metrics["l4_eval_pass"] = 1.0
            else: metrics["error"] = "No valid trace results"
        else: metrics["error"] = "No traces completed"
    except subprocess.TimeoutExpired as exc: metrics["error"] = f"Timeout: {exc}"
    except Exception as exc: metrics["error"] = str(exc); artifacts["traceback"] = traceback.format_exc()
    finally: metrics["runtime_s"] = time.time() - start
    return _wrap(metrics, artifacts)

def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here.parent, *here.parents]:
        if (p / "benchmarks").is_dir() and (p / "frontier_eval").is_dir(): return p
    return Path.cwd()

def _wrap(m: dict, a: dict) -> dict:
    try:
        from openevolve.evaluation_result import EvaluationResult as ER
        return ER(metrics=m, artifacts=a)
    except ImportError: return {"metrics": m, "artifacts": a}

def main() -> int:
    p = argparse.ArgumentParser(description="CacheReplacement: evaluate a cache replacement policy via ChampSim simulation.")
    p.add_argument("candidate", help="Path to the candidate my_policy.cc file (e.g., replacement/my_policy.cc)")
    p.add_argument("--mode", choices=["quick", "full"], default="quick",
                   help="'quick' (3 traces, ~15 min) or 'full' (10 traces, ~30-60 min)")
    p.add_argument("--metrics-out", default="", help="Optional path to write metrics JSON")
    p.add_argument("--artifacts-out", default="", help="Optional path to write artifacts JSON")
    args = p.parse_args()
    result = evaluate(args.candidate, mode=args.mode)
    r = result if isinstance(result,dict) else {"metrics":dict(result.metrics or {}),"artifacts":dict(result.artifacts or {})}
    if args.metrics_out: Path(args.metrics_out).write_text(json.dumps(r["metrics"],indent=2))
    if args.artifacts_out: Path(args.artifacts_out).write_text(json.dumps(r["artifacts"],indent=2,default=str))
    print(json.dumps(r["metrics"],indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
