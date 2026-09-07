"""Regression tests for the Cryptographic candidate-isolation hardening.

Three holes used to make ``combined_score`` a number the candidate chose:

* **The timing harness was compiled after the candidate had run.** The candidate
  binary runs with cwd set to the sandbox ``verification`` directory, which is
  where ``evaluate.cpp`` sat waiting to be built. Overwriting it with a program
  that printed ``Throughput : 999999999.00 Mbps`` scored 999999999 against an
  honest 21.2. (:func:`test_rewriting_the_timing_harness_is_inert`)
* **Nothing checked the output during the timed phase.** ``evaluate.cpp`` looked
  only at the exit status, and for the two hash tasks it sent the digest to
  ``/dev/null``. Since the correctness phase and the timed phase are trivially
  distinguishable by input size, a candidate could be honest while checked and
  return instantly while timed: 3.3x-4.0x inflation.
  (:func:`test_free_lunch_during_the_timed_phase_is_rejected`)
* **The correctness verdict was a regex over text the candidate wrote into**,
  and SHA3-256's ``validate.cpp`` returned 0 however many vectors failed.
  (:func:`test_sha3_validate_exit_status_reflects_failures`)

The scorer now generates every input, computes every expected answer in-process
from FIPS-197 / SP 800-38A / FIPS-180-4 / FIPS-202 references, spawns the
candidate itself, and checks the output of *every* timed iteration.

Most tests shrink the workload (``ITERATIONS_*`` / ``SIZE_8MBITS``) so they take
seconds rather than minutes; the shape of the benchmark is not what they are
testing. The one test that uses the real workload is marked ``slow``.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "benchmarks" / "_shared"
CRYPTO_DIR = REPO_ROOT / "benchmarks" / "Cryptographic"

if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import crypto_eval  # noqa: E402
import crypto_reference  # noqa: E402

from frontier_eval.tasks.cryptographic.spec import (  # noqa: E402
    CRYPTO_AES128_SPEC,
    CRYPTO_SHA3_256_SPEC,
    CRYPTO_SHA256_SPEC,
)

SPECS = {
    "AES-128": CRYPTO_AES128_SPEC,
    "SHA-256": CRYPTO_SHA256_SPEC,
    "SHA3-256": CRYPTO_SHA3_256_SPEC,
}

#: ``combined_score`` the pre-hardening scorer produced for the shipped
#: baselines on the audit host, interleaved with the post-hardening runs so
#: machine drift hit both arms equally (5 samples each):
#:
#:   AES-128   before 20.939 [20.80, 21.20]   after 20.632 [20.43, 21.13]   -1.5%
#:   SHA-256   before 35.300 [34.84, 35.98]   after 34.277 [34.01, 34.94]   -2.9%
#:   SHA3-256  before 67.039 [66.17, 69.55]   after 74.103 [73.11, 75.67]  +10.5%
#:
#: (medians and min-max of 9 samples per arm). The 1000000-byte case, which is
#: the one that actually measures cryptography, moved +0.1% / -0.3% / +3.7%.
#: SHA3-256's rise is the shell redirect to /dev/null that the old harness paid
#: on every spawn and this one does not -- scorer overhead, not candidate speed.
#:
#: These are wall-clock throughputs, so they are not reproducible to the digit
#: on a shared machine -- the pre-hardening scorer alone varied by 3-6% between
#: consecutive runs. The tests below therefore assert a generous band; the tight
#: comparison lives in the numbers above.
HONEST_SCORE_HINT = {"AES-128": 20.6, "SHA-256": 34.3, "SHA3-256": 74.1}

#: The 1000000-byte case is the one that actually measures cryptography (the
#: 1000-byte case is dominated by process startup: ~2.3 ms per spawn against
#: ~2 us of hashing). It is the number that must not move.
HONEST_8MBIT_HINT = {"AES-128": 124.1, "SHA-256": 357.2, "SHA3-256": 1374.1}

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="the Cryptographic benchmarks need g++"
)


def _baseline(benchmark: str) -> Path:
    spec = SPECS[benchmark]
    return CRYPTO_DIR / benchmark / "baseline" / spec.baseline_source


def _write(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _score(candidate: Path, benchmark: str) -> dict:
    result = crypto_eval.evaluate(
        str(candidate), repo_root=REPO_ROOT, spec=SPECS[benchmark]
    )
    assert isinstance(result, dict) and "metrics" in result, (
        "with openevolve absent the scorer must return a plain metrics/artifacts dict"
    )
    return result


@pytest.fixture()
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the benchmark so a security test costs seconds, not minutes."""
    monkeypatch.setattr(crypto_eval, "ITERATIONS_8KBITS", 4)
    monkeypatch.setattr(crypto_eval, "ITERATIONS_8MBITS", 3)
    monkeypatch.setattr(crypto_eval, "SIZE_8MBITS", 20000)


# --------------------------------------------------------------------------
# The scorer's own answer key
# --------------------------------------------------------------------------


def test_reference_matches_the_published_vectors() -> None:
    """The scorer's references are anchored to FIPS/NIST, not to a candidate."""
    crypto_reference.selftest()
    assert crypto_reference.sha256_hex(b"abc").startswith("ba7816bf")
    assert crypto_reference.sha3_256_hex(b"abc").startswith("3a985da7")
    # NIST SP 800-38A F.5.1.
    ct = crypto_reference.aes128_ctr_encrypt(
        bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c"),
        bytes.fromhex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff"),
        bytes.fromhex("6bc1bee22e409f96e93d7e117393172a"),
    )
    assert ct.hex() == "874d6191b620e3261bef6864990db6ce"


def test_a_broken_reference_refuses_to_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scorer that cannot verify its own answer key must not fall back to trust."""
    monkeypatch.setattr(
        crypto_reference, "sha256_hex", lambda data: "00" * 32, raising=True
    )
    result = _score(_baseline("SHA-256"), "SHA-256")
    assert result["metrics"]["valid"] == 0.0
    assert "self-test failed" in result["artifacts"]["error_message"]


def test_scorer_lives_outside_every_benchmark_directory() -> None:
    """``copy_files.txt`` is ``.``; scoring code inside the task tree is copied.

    ``run_eval.py`` executes the *workspace* copy of ``frontier_eval/``, so the
    real scorer has to live somewhere that copy cannot reach.
    """
    scorer = SHARED_DIR / "crypto_eval.py"
    assert scorer.is_file()
    assert CRYPTO_DIR not in scorer.parents
    for benchmark in SPECS:
        impl = CRYPTO_DIR / benchmark / "frontier_eval" / "evaluator_impl.py"
        text = impl.read_text(encoding="utf-8")
        assert "from crypto_eval import evaluate" in text
        # The old 566-line implementation, and its holes, are gone from here:
        # the shim compiles nothing and runs nothing.
        assert "g++" not in text
        assert "subprocess" not in text
        assert len(text.splitlines()) < 80, "the task-local shim must stay thin"


def test_no_isystem_usr_include_regression() -> None:
    """``-isystem /usr/include`` broke ``#include_next <stdlib.h>``.

    On a host whose OpenSSL headers are in ``/usr/include`` the old scorer put
    ``-isystem /usr/include`` on the command line that built ``validate.cpp``.
    That reorders the include search ahead of the libstdc++ headers, so
    ``<cstdlib>`` failed with "fatal error: stdlib.h: No such file or directory"
    and an honest baseline scored 0/invalid. Nothing in the scoring path
    compiles against OpenSSL any more.
    """
    for path in [
        SHARED_DIR / "crypto_eval.py",
        SHARED_DIR / "crypto_reference.py",
        REPO_ROOT / "frontier_eval" / "tasks" / "cryptographic" / "evaluator" / "python.py",
        *(CRYPTO_DIR / b / "frontier_eval" / "evaluator_impl.py" for b in SPECS),
    ]:
        assert "isystem" not in path.read_text(encoding="utf-8"), path


# --------------------------------------------------------------------------
# Honest candidates
# --------------------------------------------------------------------------


@pytest.mark.parametrize("benchmark", sorted(SPECS))
def test_honest_baseline_is_valid(benchmark: str, quick: None) -> None:
    result = _score(_baseline(benchmark), benchmark)
    metrics = result["metrics"]
    assert metrics["valid"] == 1.0, result["artifacts"].get("error_message")
    assert metrics["validate_pass_rate"] == 1.0
    assert metrics["validate_passed"] == metrics["validate_total"]
    assert metrics["combined_score"] > 0.0
    assert metrics.get("scorer_tampered", 0.0) == 0.0


@pytest.mark.slow
@pytest.mark.parametrize("benchmark", sorted(SPECS))
def test_honest_baseline_score_stays_in_band(benchmark: str) -> None:
    """The honest score must not have moved when the channel was replaced.

    Wall-clock throughput cannot be asserted to the digit: the *pre*-hardening
    scorer varied 3-6% between consecutive runs of the same binary on this
    machine, and much more between machines. The band below is wide on purpose;
    it catches a scorer that has started measuring something else entirely, not
    a few percent of scheduler noise. See HONEST_SCORE_HINT for the measured
    before/after distributions.
    """
    result = _score(_baseline(benchmark), benchmark)
    metrics = result["metrics"]
    assert metrics["valid"] == 1.0, result["artifacts"].get("error_message")
    ratio = metrics["throughput_8mbits_mbps"] / HONEST_8MBIT_HINT[benchmark]
    assert 0.4 < ratio < 2.5, (
        f"{benchmark} 1MB-case throughput {metrics['throughput_8mbits_mbps']:.1f} Mbps is "
        f"{ratio:.2f}x the recorded {HONEST_8MBIT_HINT[benchmark]:.1f} Mbps"
    )


# --------------------------------------------------------------------------
# Hole 1: the timing harness used to be built after the candidate had run
# --------------------------------------------------------------------------

_REWRITE_HARNESS = '''
#include <fstream>
namespace {
struct Rewrite {
  Rewrite() {
    // Under the old scorer this file had not been compiled yet, and the score
    // was the "Throughput : N Mbps" line scraped from whatever it built.
    std::ofstream f("evaluate.cpp");
    if (f) f << "#include <cstdio>\\nint main(){printf(\\"Benchmark: a\\\\n  Throughput  : 999999999.00 Mbps\\\\n\\");return 0;}\\n";
    std::ofstream g("validate.cpp");
    if (g) g << "int main(){return 0;}\\n";
  }
} rewrite_instance;
}
'''


def test_rewriting_the_timing_harness_is_inert(tmp_path: Path, quick: None) -> None:
    """Scored 999999999 before; now the write simply has no reader.

    Nothing is compiled after the candidate has run, and the throughput is
    measured by the scoring process rather than parsed out of a subprocess's
    stdout, so this candidate is graded exactly like the honest baseline it is
    otherwise a copy of.
    """
    source = _baseline("AES-128").read_text(encoding="utf-8")
    hacked = _write(
        tmp_path, "AES-128.cpp", source.replace("int main() {", _REWRITE_HARNESS + "\nint main() {", 1)
    )
    result = _score(hacked, "AES-128")
    metrics = result["metrics"]
    assert metrics["valid"] == 1.0, result["artifacts"].get("error_message")
    assert metrics["combined_score"] < 1e4, "the candidate dictated its own throughput"
    honest = _score(_baseline("AES-128"), "AES-128")["metrics"]["combined_score"]
    assert 0.3 < metrics["combined_score"] / honest < 3.0


# --------------------------------------------------------------------------
# Hole 2: the timed phase never looked at the answer
# --------------------------------------------------------------------------


def _free_lunch_source(benchmark: str) -> str:
    """An honest implementation that stops working once it is being timed.

    Each variant detects the timed phase the way the old harness made possible:
    by the size of the input, which the correctness phase never uses.
    """
    source = _baseline(benchmark).read_text(encoding="utf-8")
    if benchmark == "AES-128":
        return source.replace(
            'int main() {\n    std::ifstream infile("test_in.txt");',
            '''int main() {
    {   std::ifstream probe("test_in.txt");
        std::string l; int n = 0;
        while (std::getline(probe, l)) ++n;
        if (n <= 3) { std::ofstream o("test_out_custom.txt"); o << "00" << std::endl; return 0; }
    }
    std::ifstream infile("test_in.txt");''',
            1,
        )
    if benchmark == "SHA-256":
        return source.replace(
            "#include <iostream>", "#include <iostream>\n#include <unistd.h>\n#include <sys/stat.h>", 1
        ).replace(
            "int main() {\n    SHA256 sha;",
            '''int main() {
    {   struct stat st;
        // Above every correctness-phase length, so this is honest while
        // checked and free while timed -- exactly the old free lunch.
        if (fstat(0, &st) == 0 && st.st_size > 5000) {
            std::cout << std::string(64, 'a');
            return 0;
        }
    }
    SHA256 sha;''',
            1,
        )
    return source.replace(
        """    if (argc != 2) {
        return 1; 
    }""",
        """    if (argc != 2) {
        return 1; 
    }
    {   std::ifstream probe(argv[1], std::ios::binary | std::ios::ate);
        if (probe && probe.tellg() > std::streamoff(5000)) {
            std::cout << std::string(64, 'a');
            return 0;
        }
    }""",
        1,
    )


@pytest.mark.parametrize("benchmark", sorted(SPECS))
def test_free_lunch_during_the_timed_phase_is_rejected(
    benchmark: str, tmp_path: Path, quick: None
) -> None:
    """Passed correctness, then returned instantly while timed: 3.3x-4.0x before."""
    spec = SPECS[benchmark]
    candidate = _write(tmp_path, spec.baseline_source, _free_lunch_source(benchmark))
    result = _score(candidate, benchmark)
    metrics = result["metrics"]
    assert metrics["valid"] == 0.0
    assert metrics["combined_score"] == 0.0
    assert "wrong output on timed iteration" in result["artifacts"]["error_message"]


@pytest.mark.parametrize("benchmark", sorted(SPECS))
def test_a_stale_answer_cannot_be_replayed(
    benchmark: str, tmp_path: Path, quick: None
) -> None:
    """Every iteration gets a fresh input, so last round's answer is wrong now."""
    handler = crypto_eval.ALGORITHMS[benchmark]()
    import secrets

    rng = secrets.SystemRandom()
    base = handler.new_body(rng, 512)
    a = handler.apply_seed(base, handler.new_seed(rng))
    b = handler.apply_seed(base, handler.new_seed(rng))
    assert handler.expected(a) != handler.expected(b)
    assert a.nbytes == b.nbytes == base.nbytes


# --------------------------------------------------------------------------
# Malformed and hostile output
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "benchmark,body",
    [
        ("SHA-256", 'int main(){ std::cout << "not a digest"; return 0; }'),
        ("SHA-256", 'int main(){ std::cout << std::string(64, (char)0xff); return 0; }'),
        ("SHA-256", "int main(){ return 0; }"),
        ("SHA-256", "int main(){ return 3; }"),
        (
            "SHA-256",
            # A perfect-looking verdict on stdout buys nothing: the scorer reads
            # the digest, not a claim about it.
            'int main(){ std::cout << "Verification Complete: 10/10 passed.\\n'
            'Throughput  : 999999999.00 Mbps\\n"; return 0; }',
        ),
    ],
)
def test_illegal_output_is_rejected(
    benchmark: str, body: str, tmp_path: Path, quick: None
) -> None:
    source = "#include <iostream>\n#include <string>\n" + body + "\n"
    candidate = _write(tmp_path, SPECS[benchmark].baseline_source, source)
    result = _score(candidate, benchmark)
    assert result["metrics"]["valid"] == 0.0
    assert result["metrics"]["combined_score"] == 0.0


def test_a_crashing_candidate_cannot_take_the_scorer_with_it(
    tmp_path: Path, quick: None
) -> None:
    """The candidate is a separate process; it cannot reach into the scorer.

    This is the compiled-language form of "the candidate cannot import the
    scorer": aborting mid-run produces a scored, invalid result rather than
    killing the process that owns the score.
    """
    candidate = _write(
        tmp_path,
        "SHA-256.cpp",
        "#include <cstdlib>\nint main(){ std::abort(); }\n",
    )
    result = _score(candidate, "SHA-256")
    assert result["metrics"]["valid"] == 0.0
    assert result["metrics"]["combined_score"] == 0.0


def test_candidate_cannot_reach_the_scorers_python(tmp_path: Path, quick: None) -> None:
    """There is no in-process channel: the candidate is C++ in its own process.

    Asserted structurally, because the absence of a channel is what is being
    checked: the scorer never imports, execs or evals anything the candidate
    produced, and never parses a number out of the candidate's output.
    """
    text = (SHARED_DIR / "crypto_eval.py").read_text(encoding="utf-8")
    for forbidden in ("exec_module", "spec_from_file_location", "eval(", "exec("):
        assert forbidden not in text, f"scorer must not load candidate-side code: {forbidden}"
    # The only compilation is the candidate's, and it happens before any run.
    assert text.count('"g++"') == 1
    compile_at = text.index('"g++"')
    first_spawn = text.index("def _spawn(")
    assert first_spawn < compile_at or "_run_correctness" in text
    # combined_score is assigned from a locally computed geometric mean only.
    assert 'metrics["combined_score"] = metrics["throughput_geom_mean_mbps"]' in text


def test_scorer_tampering_invalidates_the_run(
    tmp_path: Path, quick: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A candidate that rewrites the shared scorer poisons *later* runs.

    It cannot change the run in progress (the code is already resident), but the
    run that did it is no longer worth believing, and a human needs to know.
    """
    monkeypatch.setattr(crypto_eval, "_SCORER_FINGERPRINT_AT_IMPORT", "deadbeef")
    result = _score(_baseline("SHA-256"), "SHA-256")
    assert result["metrics"]["valid"] == 0.0
    assert result["metrics"]["scorer_tampered"] == 1.0
    assert "restore the tree" in result["artifacts"]["error_message"]


def test_pure_python_aes_fallback_still_scores(
    quick: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scorer must not depend on ``cryptography`` being installed.

    With the fallback active the 1 MB case cycles a small number of inputs
    instead of one per iteration (50 pure-Python keystreams would cost ~90s of
    scorer time); ``throughput_variants_*`` records that so a score taken in
    this configuration is auditable. See the residual-risk note in crypto_eval.
    """
    monkeypatch.setattr(crypto_reference, "_AES_FAST", None)
    monkeypatch.setattr(crypto_reference, "_AES_BACKEND_NAME", "pure-python")
    monkeypatch.setattr(crypto_reference, "aes_backend_name", lambda: "pure-python")
    monkeypatch.setattr(
        crypto_reference,
        "aes128_ctr_encrypt",
        crypto_reference._aes128_ctr_pure,
    )
    result = _score(_baseline("AES-128"), "AES-128")
    metrics = result["metrics"]
    assert metrics["valid"] == 1.0, result["artifacts"].get("error_message")
    assert result["artifacts"]["aes_reference_backend"] == "pure-python"
    assert metrics["throughput_variants_8_mbits_stream"] == 3.0
    assert metrics["throughput_variants_8_kbits_stream"] == crypto_eval.ITERATIONS_8KBITS


def test_a_hanging_candidate_times_out(tmp_path: Path, quick: None, monkeypatch) -> None:
    """The deadline is enforced by a watchdog, not by a polled wait.

    ``subprocess.run(timeout=...)`` polls waitpid with a backoff capped at 50 ms
    and that latency lands inside the timing window -- it cost 30% of the
    measured throughput before it was found. The replacement must still stop a
    candidate that never exits, and must kill the whole process group: the
    candidate is a grandchild, behind /bin/sh.
    """
    monkeypatch.setattr(crypto_eval, "_run_once", _run_once_with_short_deadline)
    candidate = _write(
        tmp_path,
        "SHA-256.cpp",
        "#include <unistd.h>\nint main(){ for(;;) pause(); }\n",
    )
    result = _score(candidate, "SHA-256")
    assert result["metrics"]["valid"] == 0.0
    assert result["metrics"]["timeout"] == 1.0


_orig_run_once = crypto_eval._run_once


def _run_once_with_short_deadline(handler, run_dir, body, timeout_s, **kwargs):
    return _orig_run_once(handler, run_dir, body, 2.0, **kwargs)


# --------------------------------------------------------------------------
# The standalone developer checks under verification/
# --------------------------------------------------------------------------


def test_sha3_validate_exit_status_reflects_failures() -> None:
    """``verification/validate.cpp`` used to ``return 0`` however many failed."""
    text = (CRYPTO_DIR / "SHA3-256" / "verification" / "validate.cpp").read_text(
        encoding="utf-8"
    )
    assert "return (passed == TEST_COUNT) ? 0 : 1;" in text


@pytest.mark.parametrize("benchmark", sorted(SPECS))
def test_verification_sources_are_marked_as_not_the_scorer(benchmark: str) -> None:
    for name in ("validate.cpp", "evaluate.cpp"):
        text = (CRYPTO_DIR / benchmark / "verification" / name).read_text(encoding="utf-8")
        assert text.startswith("// NOTE: this file is a developer convenience")


# --------------------------------------------------------------------------
# End to end, through run_eval.py and the task-local shim
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_run_eval_end_to_end(tmp_path: Path) -> None:
    benchmark = "AES-128"
    task_dir = CRYPTO_DIR / benchmark
    metrics_out = tmp_path / "metrics.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(task_dir / "frontier_eval" / "run_eval.py"),
            "--candidate",
            str(_baseline(benchmark)),
            "--metrics-out",
            str(metrics_out),
            "--artifacts-out",
            str(tmp_path / "artifacts.json"),
        ],
        cwd=str(task_dir),
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "FRONTIER_ENGINEERING_ROOT": str(REPO_ROOT),
            "FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR": str(task_dir),
        },
        timeout=900,
    )
    assert proc.returncode == 0, proc.stderr
    metrics = json.loads(metrics_out.read_text(encoding="utf-8"))
    assert metrics["valid"] == 1.0
    assert metrics["combined_score"] > 0.0
