"""Core of the SustainDC hand-written-control benchmark.

Isolation contract
------------------
This benchmark scores a candidate *relative to a NoOp reference*
(``score_episode`` -> ``100 * sqrt(improvement_fraction)``). That makes the
reference itself a scoring input: an attacker does not have to make the
datacenter better, only to make the yardstick worse. When the candidate was
``exec_module``-d into this process (the old ``load_policy_module`` path in
``verification/evaluate.py``), its module-level code ran *before*
``run_benchmark`` and could rebind any of the globals that ``run_benchmark``
resolves at call time -- ``NoOpPolicy``, ``run_episode``, ``score_episode``,
``SCENARIOS``, ``NOISE_TOLERANCE`` -- and drive the score to ~100 with a policy
byte-identical to NoOp.

The fix is structural: candidate code never enters this process. It runs in a
throw-away subprocess (``verification/policy_runner.py``) behind
``IsolatedPolicy``, which answers one ``decide_actions`` call per environment
step over a pipe. This process owns the environments, the NoOp reference, the
action validation and the scoring, so the reference cannot be reached at all.
``_assert_scoring_integrity`` is belt-and-braces on top of that boundary.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import random
import selectors
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

import numpy as np

BENCHMARK_ROOT = Path(__file__).resolve().parent
DEFAULT_SUSTAINDC_ROOT = BENCHMARK_ROOT / "sustaindc"
SUSTAINDC_ROOT_ENV = "SUSTAINDC_ROOT"
POLICY_RUNNER = BENCHMARK_ROOT / "verification" / "policy_runner.py"
NOOP_REFERENCE_PATH = BENCHMARK_ROOT / "verification" / "noop_reference.json"

# Wall-clock budget for one candidate subprocess over one full episode.
EPISODE_WALL_CLOCK_S = 600.0

# Scoring tolerance: improvements at or below this are treated as noise.
# Defined next to the other scoring constants (it used to sit at the very bottom
# of the file, far from everything that reads it).
NOISE_TOLERANCE = 0.002


TIMESTEPS_PER_DAY = 96
AGENT_NAMES = ("agent_ls", "agent_dc", "agent_bat")

ACTION_DESCRIPTIONS = {
    "agent_ls": {
        0: "Defer flexible jobs into the queue.",
        1: "Keep the queue unchanged.",
        2: "Execute jobs from the queue.",
    },
    "agent_dc": {
        0: "Decrease the cooling setpoint (more cooling).",
        1: "Keep the cooling setpoint unchanged.",
        2: "Increase the cooling setpoint (less cooling).",
    },
    "agent_bat": {
        0: "Charge the battery.",
        1: "Discharge the battery.",
        2: "Keep the battery idle.",
    },
}

LS_FEATURES = [
    "time_cos_hour",
    "time_sin_hour",
    "ci_current_norm",
    "ci_future_slope",
    "ci_past_slope",
    "ci_future_mean",
    "ci_future_std",
    "ci_percentile",
    "ci_time_to_next_peak_norm",
    "ci_time_to_next_valley_norm",
    "queue_oldest_task_age_norm",
    "queue_average_task_age_norm",
    "queue_fill_ratio",
    "workload_current",
    "outdoor_temp_current_norm",
    "temp_future_slope",
    "temp_future_mean",
    "temp_future_std",
    "temp_percentile",
    "temp_time_to_next_peak_norm",
    "temp_time_to_next_valley_norm",
    "queue_hist_0_6h",
    "queue_hist_6_12h",
    "queue_hist_12_18h",
    "queue_hist_18_24h",
    "queue_hist_over_24h",
]

DC_FEATURES = [
    "time_cos_hour",
    "time_sin_hour",
    "ci_current_norm",
    "ci_future_slope",
    "ci_past_slope",
    "ci_future_mean",
    "ci_future_std",
    "ci_percentile",
    "ci_time_to_next_peak_norm",
    "ci_time_to_next_valley_norm",
    "workload_current",
    "workload_next",
    "outdoor_temp_current_norm",
    "outdoor_temp_next_norm",
]

BAT_FEATURES = [
    "time_cos_hour",
    "time_sin_hour",
    "ci_current_norm",
    "ci_future_slope",
    "ci_past_slope",
    "ci_future_mean",
    "ci_future_std",
    "ci_percentile",
    "ci_time_to_next_peak_norm",
    "ci_time_to_next_valley_norm",
    "workload_current",
    "outdoor_temp_current_norm",
    "battery_soc",
]


@dataclass(frozen=True)
class Scenario:
    name: str
    location: str
    month: int
    days_per_episode: int
    seed: int
    description: str


@dataclass
class EpisodeMetrics:
    scenario: str
    steps: int = 0
    carbon_kg: float = 0.0
    water_l: float = 0.0
    dropped_tasks: float = 0.0
    overdue_tasks: float = 0.0
    grid_energy_kwh: float = 0.0
    avg_soc: float = 0.0
    total_reward: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["avg_soc"] = float(self.avg_soc)
        return data


SCENARIOS = (
    Scenario(
        name="az_july",
        location="az",
        month=6,
        days_per_episode=2,
        seed=11,
        description="Arizona summer: hot weather with expensive cooling decisions.",
    ),
    Scenario(
        name="ca_april",
        location="ca",
        month=3,
        days_per_episode=2,
        seed=17,
        description="California spring: milder weather, still non-trivial carbon scheduling.",
    ),
    Scenario(
        name="ny_january",
        location="ny",
        month=0,
        days_per_episode=2,
        seed=23,
        description="New York winter: lower outdoor temperatures and different demand profile.",
    ),
    Scenario(
        name="tx_august",
        location="tx",
        month=7,
        days_per_episode=2,
        seed=29,
        description="Texas late summer: high thermal pressure and volatile carbon intensity.",
    ),
)


BENCHMARK_ENV_CONFIG = {
    "agents": list(AGENT_NAMES),
    "workload_file": "Alibaba_CPU_Data_Hourly_1.csv",
    "max_bat_cap_Mw": 1.0,
    "individual_reward_weight": 0.8,
    "flexible_load": 0.6,
    "dc_config_file": "dc_config.json",
    "evaluation": False,
}


class NoOpPolicy:
    @staticmethod
    def reset_policy() -> None:
        return None

    @staticmethod
    def decide_actions(observations: Mapping[str, np.ndarray]) -> Dict[str, int]:
        return {
            "agent_ls": 1,
            "agent_dc": 1,
            "agent_bat": 2,
        }


def resolve_sustaindc_root(explicit_root: str | Path | None = None) -> Path:
    candidate = explicit_root or os.environ.get(SUSTAINDC_ROOT_ENV, DEFAULT_SUSTAINDC_ROOT)
    root = Path(candidate).expanduser().resolve()
    if not (root / "sustaindc_env.py").exists():
        raise FileNotFoundError(
            "Could not find a SustainDC checkout. Expected "
            f"{root / 'sustaindc_env.py'}. Clone dc-rl into the sibling "
            f"directory or pass --sustaindc-root /path/to/dc-rl."
        )
    return root


def _clear_cached_utils_if_needed(sustaindc_root: Path) -> None:
    cached_utils = sys.modules.get("utils")
    expected_utils = sustaindc_root / "utils" / "__init__.py"
    cached_utils_file = Path(getattr(cached_utils, "__file__", "")).resolve() if cached_utils else None
    if cached_utils is not None and cached_utils_file != expected_utils:
        for module_name in list(sys.modules):
            if module_name == "utils" or module_name.startswith("utils."):
                sys.modules.pop(module_name, None)


def _load_sustaindc_modules(sustaindc_root: str | Path | None = None):
    root = resolve_sustaindc_root(sustaindc_root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    _clear_cached_utils_if_needed(root)
    cached_env_module = sys.modules.get("sustaindc_env")
    expected_env_file = root / "sustaindc_env.py"
    cached_env_file = (
        Path(getattr(cached_env_module, "__file__", "")).resolve()
        if cached_env_module is not None
        else None
    )
    if cached_env_module is not None and cached_env_file != expected_env_file:
        sys.modules.pop("sustaindc_env", None)

    env_module = importlib.import_module("sustaindc_env")
    utils_module = importlib.import_module("utils.utils_cf")
    return root, env_module, env_module.SustainDC, utils_module.get_init_day


def load_policy_module(solution_path: Path):
    """Import a policy module into *this* process.

    DANGER: never call this on a candidate solution. This benchmark scores
    relative to a NoOp reference computed in this process, so candidate code
    that lands here can rebind ``NoOpPolicy``/``run_episode``/``score_episode``
    and fabricate its own improvement. Candidates go through
    :class:`IsolatedPolicy`. This helper survives only for trusted, in-repo
    policies (and for tooling that regenerates the frozen NoOp reference).
    """
    spec = importlib.util.spec_from_file_location("benchmark_solution", solution_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load solution module from {solution_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "decide_actions"):
        raise AttributeError(
            f"{solution_path} must define a decide_actions(observations) function."
        )
    return module


class CandidateRejected(Exception):
    """The candidate ran but produced something the scorer will not score."""


class IsolatedPolicy:
    """A ``decide_actions``-compatible stand-in backed by a subprocess.

    Quacks like a policy module (``reset_policy`` / ``decide_actions``) so
    :func:`run_episode` needs no special-casing, but every call is answered by
    ``verification/policy_runner.py`` in a separate process. Candidate code
    therefore never shares a namespace with the environments, the NoOp
    reference, or the scoring functions.
    """

    def __init__(self, solution_path: Path, timeout_s: float = EPISODE_WALL_CLOCK_S):
        self._path = Path(solution_path).resolve()
        self._timeout_s = timeout_s
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> "IsolatedPolicy":
        request_r, self._request_w = os.pipe()
        self._response_r, response_w = os.pipe()
        env = dict(os.environ)
        env["SUSTAINDC_REQUEST_FD"] = str(request_r)
        env["SUSTAINDC_RESPONSE_FD"] = str(response_w)
        # Child stdio goes to a temp file, never to pipes: nothing in the step
        # loop drains them, so a chatty candidate would fill a 64K pipe buffer
        # and deadlock until the wall-clock budget expired.
        self._log = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
        self._proc = subprocess.Popen(
            [sys.executable, str(POLICY_RUNNER), str(self._path)],
            stdin=subprocess.DEVNULL,
            stdout=self._log,
            stderr=self._log,
            close_fds=True,
            pass_fds=(request_r, response_w),
            env=env,
        )
        os.close(request_r)
        os.close(response_w)
        self._request_stream = os.fdopen(self._request_w, "w", encoding="utf-8")
        self._response_stream = os.fdopen(self._response_r, "r", encoding="utf-8")
        self._deadline = time.time() + self._timeout_s
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _exchange(self, request: Dict[str, Any]) -> Any:
        if self._proc is None:
            raise CandidateRejected("policy subprocess is not running")
        if time.time() > self._deadline:
            raise CandidateRejected(
                f"candidate exceeded the {self._timeout_s:.0f}s per-episode budget"
            )
        self._request_stream.write(json.dumps(request, ensure_ascii=False) + "\n")
        self._request_stream.flush()

        selector = selectors.DefaultSelector()
        selector.register(self._response_stream, selectors.EVENT_READ)
        events = selector.select(timeout=max(1e-3, self._deadline - time.time()))
        selector.close()
        if not events:
            if self._proc.poll() is not None:
                raise CandidateRejected(
                    f"policy subprocess died with code {self._proc.returncode}. "
                    f"{self.log_tail()}"
                )
            raise CandidateRejected(
                f"candidate exceeded the {self._timeout_s:.0f}s per-episode budget"
            )

        line = self._response_stream.readline()
        if not line:
            raise CandidateRejected(
                "policy subprocess closed its response stream unexpectedly. "
                f"{self.log_tail()}"
            )
        payload = json.loads(line)
        if "error" in payload:
            raise CandidateRejected(f"candidate policy failed: {payload['error']}")
        return payload.get("actions")

    def log_tail(self, limit: int = 2000) -> str:
        """Child stdout/stderr, for diagnostics only -- never parsed as data."""
        try:
            self._log.seek(0)
            return self._log.read()[-limit:]
        except (OSError, ValueError):
            return ""

    def reset_policy(self) -> None:
        self._exchange({"op": "reset"})

    def decide_actions(self, observations: Mapping[str, np.ndarray]) -> Dict[str, Any]:
        payload = {
            "op": "act",
            "observations": {
                str(agent): np.asarray(values, dtype=float).reshape(-1).tolist()
                for agent, values in observations.items()
            },
        }
        actions = self._exchange(payload)
        if not isinstance(actions, dict):
            raise CandidateRejected("decide_actions must return a mapping of agent -> action")
        return actions

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            self._request_stream.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        try:
            self._log.close()
        except OSError:
            pass
        self._proc = None


# --- Scoring-input integrity ------------------------------------------------
#
# The process boundary above is the real defence. These frozen literals are the
# second line: they pin every module global that feeds the *relative* score, so
# any future in-process regression (or an accidental edit) fails loudly instead
# of silently changing what a candidate is compared against.

_EXPECTED_SCENARIOS = (
    ("az_july", "az", 6, 2, 11),
    ("ca_april", "ca", 3, 2, 17),
    ("ny_january", "ny", 0, 2, 23),
    ("tx_august", "tx", 7, 2, 29),
)
_EXPECTED_NOISE_TOLERANCE = 0.002
_EXPECTED_NOOP_ACTIONS = {"agent_ls": 1, "agent_dc": 1, "agent_bat": 2}
_EXPECTED_ENV_CONFIG = {
    "agents": ["agent_ls", "agent_dc", "agent_bat"],
    "workload_file": "Alibaba_CPU_Data_Hourly_1.csv",
    "max_bat_cap_Mw": 1.0,
    "individual_reward_weight": 0.8,
    "flexible_load": 0.6,
    "dc_config_file": "dc_config.json",
    "evaluation": False,
}


def _assert_scoring_integrity() -> None:
    """Fail loudly if any scoring input has drifted from its frozen value."""
    observed = tuple(
        (s.name, s.location, s.month, s.days_per_episode, s.seed) for s in SCENARIOS
    )
    if observed != _EXPECTED_SCENARIOS:
        raise RuntimeError(f"SCENARIOS have been modified: {observed!r}")
    if NOISE_TOLERANCE != _EXPECTED_NOISE_TOLERANCE:
        raise RuntimeError(f"NOISE_TOLERANCE has been modified: {NOISE_TOLERANCE!r}")
    if BENCHMARK_ENV_CONFIG != _EXPECTED_ENV_CONFIG:
        raise RuntimeError(f"BENCHMARK_ENV_CONFIG has been modified: {BENCHMARK_ENV_CONFIG!r}")
    noop_actions = NoOpPolicy.decide_actions({})
    if dict(noop_actions) != _EXPECTED_NOOP_ACTIONS:
        raise RuntimeError(f"NoOpPolicy no longer produces the no-op action: {noop_actions!r}")
    if getattr(NoOpPolicy, "__module__", None) != __name__:
        raise RuntimeError("NoOpPolicy has been replaced by a foreign class")


def _build_env(scenario: Scenario, sustaindc_root: str | Path | None = None):
    _, env_module, SustainDC, get_init_day = _load_sustaindc_modules(sustaindc_root)
    env_config = dict(BENCHMARK_ENV_CONFIG)
    env_config.update(
        {
            "location": scenario.location,
            "month": scenario.month,
            "days_per_episode": scenario.days_per_episode,
        }
    )
    env_defaults = getattr(getattr(env_module, "EnvConfig", None), "DEFAULT_CONFIG", {})
    if "fixed_init_day" in env_defaults and "fixed_init_hour" in env_defaults:
        env_config.update(
            {
                "fixed_init_day": get_init_day(scenario.month) + 3,
                "fixed_init_hour": 12,
            }
        )
    return SustainDC(env_config)


def _reset_policy_if_available(policy_module: Any) -> None:
    if hasattr(policy_module, "reset_policy"):
        policy_module.reset_policy()


def _coerce_actions(actions: Mapping[str, Any]) -> Dict[str, int]:
    missing = [agent for agent in AGENT_NAMES if agent not in actions]
    if missing:
        raise KeyError(f"Policy output is missing actions for: {missing}")

    coerced: Dict[str, int] = {}
    for agent in AGENT_NAMES:
        action = int(actions[agent])
        if action not in ACTION_DESCRIPTIONS[agent]:
            raise ValueError(
                f"{agent} produced invalid action {action}. "
                f"Valid actions are {sorted(ACTION_DESCRIPTIONS[agent])}."
            )
        coerced[agent] = action
    return coerced


def _close_env(env: Any) -> None:
    try:
        env.close()
    except Exception:
        pass

    for sub_env_name in ("ls_env", "dc_env", "bat_env"):
        sub_env = getattr(env, sub_env_name, None)
        if sub_env is not None and hasattr(sub_env, "close"):
            try:
                sub_env.close()
            except Exception:
                pass


def run_episode(
    policy_module: Any,
    scenario: Scenario,
    sustaindc_root: str | Path | None = None,
) -> EpisodeMetrics:
    random.seed(scenario.seed)
    np.random.seed(scenario.seed)
    env = _build_env(scenario, sustaindc_root=sustaindc_root)
    try:
        env.seed(scenario.seed)
        _reset_policy_if_available(policy_module)
        observations = env.reset()

        metrics = EpisodeMetrics(scenario=scenario.name)
        soc_trace = []

        while True:
            actions = _coerce_actions(policy_module.decide_actions(observations))
            observations, rewards, terminateds, truncateds, infos = env.step(actions)
            common = infos["__common__"]

            metrics.steps += 1
            metrics.carbon_kg += float(common["bat_CO2_footprint"]) / 1000.0
            metrics.water_l += float(common["dc_water_usage"])
            metrics.dropped_tasks += float(common["ls_tasks_dropped"])
            metrics.overdue_tasks += float(common["ls_overdue_penalty"])
            metrics.grid_energy_kwh += float(common["bat_total_energy_with_battery_KWh"])
            metrics.total_reward += sum(float(v) for v in rewards.values())
            soc_trace.append(float(common["bat_SOC"]))

            if terminateds.get("__all__") or truncateds.get("__all__"):
                break

        if soc_trace:
            metrics.avg_soc = float(np.mean(soc_trace))
        return metrics
    finally:
        _close_env(env)


def _metric_improvement(candidate: float, reference: float, floor: float) -> float:
    denom = max(reference, floor)
    raw_gain = 1.0 - candidate / denom
    if raw_gain <= NOISE_TOLERANCE:
        return 0.0
    return float(np.clip(raw_gain, 0.0, 1.0))


def score_episode(candidate: EpisodeMetrics, reference: EpisodeMetrics) -> Dict[str, float]:
    carbon_gain = _metric_improvement(candidate.carbon_kg, reference.carbon_kg, 1e-9)
    water_gain = _metric_improvement(candidate.water_l, reference.water_l, 1e-9)
    improvement_fraction = 0.85 * carbon_gain + 0.15 * water_gain
    base_score = 100.0 * np.sqrt(improvement_fraction)
    safety_penalty = 5.0 * candidate.dropped_tasks + 0.5 * candidate.overdue_tasks
    final_score = float(np.clip(base_score - safety_penalty, 0.0, 100.0))

    return {
        "carbon_gain": round(carbon_gain, 6),
        "water_gain": round(water_gain, 6),
        "improvement_fraction": round(float(improvement_fraction), 6),
        "base_score": round(float(base_score), 4),
        "safety_penalty": round(float(safety_penalty), 4),
        "score": round(final_score, 4),
        "theoretical_ceiling": 100.0,
    }


def aggregate_metrics(metrics: list[EpisodeMetrics]) -> Dict[str, float]:
    return {
        "steps": int(sum(item.steps for item in metrics)),
        "carbon_kg": float(sum(item.carbon_kg for item in metrics)),
        "water_l": float(sum(item.water_l for item in metrics)),
        "dropped_tasks": float(sum(item.dropped_tasks for item in metrics)),
        "overdue_tasks": float(sum(item.overdue_tasks for item in metrics)),
        "grid_energy_kwh": float(sum(item.grid_energy_kwh for item in metrics)),
        "avg_soc": float(np.mean([item.avg_soc for item in metrics])),
        "total_reward": float(sum(item.total_reward for item in metrics)),
    }


def run_benchmark(
    policy_module: Any,
    sustaindc_root: str | Path | None = None,
    noop_reference: Dict[str, EpisodeMetrics] | None = None,
) -> Dict[str, Any]:
    """Score a policy object against the NoOp reference.

    ``policy_module`` must be something this process can safely call --
    :class:`IsolatedPolicy` for a candidate, or a trusted in-repo module. Use
    :func:`run_benchmark_isolated` for anything candidate-authored.
    """
    _assert_scoring_integrity()
    candidate_results: list[EpisodeMetrics] = []
    noop_results: list[EpisodeMetrics] = []
    scenario_reports: list[Dict[str, Any]] = []
    resolved_root = resolve_sustaindc_root(sustaindc_root)
    reference_source = "frozen_table" if noop_reference else "recomputed_in_process"

    for scenario in SCENARIOS:
        candidate_metrics = run_episode(
            policy_module,
            scenario,
            sustaindc_root=resolved_root,
        )
        if noop_reference is not None:
            noop_metrics = noop_reference[scenario.name]
        else:
            # NoOpPolicy is this module's own class and this process has never
            # imported candidate code, so the reference cannot be tampered with.
            noop_metrics = run_episode(
                NoOpPolicy,
                scenario,
                sustaindc_root=resolved_root,
            )
        # Re-check right before the reference is consumed.
        _assert_scoring_integrity()
        score_breakdown = score_episode(candidate_metrics, noop_metrics)

        candidate_results.append(candidate_metrics)
        noop_results.append(noop_metrics)
        scenario_reports.append(
            {
                "scenario": asdict(scenario),
                "candidate": candidate_metrics.as_dict(),
                "noop_reference": noop_metrics.as_dict(),
                "score_breakdown": score_breakdown,
            }
        )

    average_score = float(
        np.mean([report["score_breakdown"]["score"] for report in scenario_reports])
    )

    return {
        "average_score": round(average_score, 4),
        "score_ceiling": 100.0,
        "sustaindc_root": str(resolved_root),
        "noop_reference_source": reference_source,
        "scenario_reports": scenario_reports,
        "candidate_aggregate": aggregate_metrics(candidate_results),
        "noop_aggregate": aggregate_metrics(noop_results),
        "feature_reference": {
            "agent_ls": LS_FEATURES,
            "agent_dc": DC_FEATURES,
            "agent_bat": BAT_FEATURES,
        },
    }


def scenario_fingerprint(sustaindc_root: Path) -> str:
    """Identify what a frozen NoOp reference was measured against.

    Covers the scenario definitions, the env config, the NoOp actions, and the
    contents of the vendored SustainDC sources that drive the simulation, so a
    stale table is detected rather than silently trusted.
    """
    import hashlib

    digest = hashlib.sha256()
    digest.update(json.dumps(_EXPECTED_SCENARIOS, sort_keys=True).encode("utf-8"))
    digest.update(json.dumps(_EXPECTED_ENV_CONFIG, sort_keys=True).encode("utf-8"))
    digest.update(json.dumps(_EXPECTED_NOOP_ACTIONS, sort_keys=True).encode("utf-8"))
    root = Path(sustaindc_root)
    for relative in sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if p.is_file() and "__pycache__" not in p.parts
    ):
        digest.update(relative.encode("utf-8"))
        digest.update(hashlib.sha256((root / relative).read_bytes()).digest())
    return digest.hexdigest()


def load_noop_reference(sustaindc_root: Path) -> Dict[str, EpisodeMetrics] | None:
    """Return the frozen NoOp reference, or None if absent or stale.

    The NoOp baseline is deterministic for the fixed SCENARIOS, so it can be
    precomputed once and reused -- which both removes the reference simulation
    from the scored run entirely and halves the runtime. Falling back to None
    (recompute in this process) is always safe, so a missing or mismatched
    table degrades to "slower", never to "wrong".
    """
    if not NOOP_REFERENCE_PATH.is_file():
        return None
    try:
        payload = json.loads(NOOP_REFERENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if payload.get("fingerprint") != scenario_fingerprint(sustaindc_root):
        return None
    try:
        episodes = payload["episodes"]
        reference = {
            name: EpisodeMetrics(**values) for name, values in episodes.items()
        }
    except (KeyError, TypeError):
        return None
    if {s.name for s in SCENARIOS} - set(reference):
        return None
    return reference


def write_noop_reference(sustaindc_root: Path) -> Path:
    """Recompute and persist the frozen NoOp reference table."""
    _assert_scoring_integrity()
    resolved_root = resolve_sustaindc_root(sustaindc_root)
    episodes = {
        scenario.name: run_episode(
            NoOpPolicy, scenario, sustaindc_root=resolved_root
        ).as_dict()
        for scenario in SCENARIOS
    }
    payload = {
        "_comment": (
            "Precomputed NoOp reference metrics. The relative score is measured "
            "against these, so they are deliberately NOT recomputed alongside a "
            "candidate. Regenerate with: python verification/evaluate.py "
            "--refresh-noop-reference"
        ),
        "fingerprint": scenario_fingerprint(resolved_root),
        "episodes": episodes,
    }
    NOOP_REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOOP_REFERENCE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return NOOP_REFERENCE_PATH


def run_benchmark_isolated(
    solution_path: str | Path,
    sustaindc_root: str | Path | None = None,
) -> Dict[str, Any]:
    """Score a *candidate* solution without ever importing it here.

    This is the only entrypoint an evaluator should use on candidate code.
    """
    _assert_scoring_integrity()
    resolved_root = resolve_sustaindc_root(sustaindc_root)
    solution_path = Path(solution_path).resolve()
    noop_reference = load_noop_reference(resolved_root)

    candidate_results: list[EpisodeMetrics] = []
    noop_results: list[EpisodeMetrics] = []
    scenario_reports: list[Dict[str, Any]] = []

    for scenario in SCENARIOS:
        # A fresh subprocess per scenario: no state leaks between episodes and a
        # crash in one scenario cannot corrupt another.
        try:
            with IsolatedPolicy(solution_path) as policy:
                candidate_metrics = run_episode(policy, scenario, sustaindc_root=resolved_root)
        except CandidateRejected:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            # Raised by _coerce_actions for a malformed/illegal action, or by
            # the env when fed one. Anything thrown while driving the candidate
            # is the candidate's fault, not an evaluator crash.
            raise CandidateRejected(
                f"scenario {scenario.name}: {type(exc).__name__}: {exc}"
            ) from exc

        if noop_reference is not None:
            noop_metrics = noop_reference[scenario.name]
        else:
            noop_metrics = run_episode(NoOpPolicy, scenario, sustaindc_root=resolved_root)

        _assert_scoring_integrity()
        score_breakdown = score_episode(candidate_metrics, noop_metrics)

        candidate_results.append(candidate_metrics)
        noop_results.append(noop_metrics)
        scenario_reports.append(
            {
                "scenario": asdict(scenario),
                "candidate": candidate_metrics.as_dict(),
                "noop_reference": noop_metrics.as_dict(),
                "score_breakdown": score_breakdown,
            }
        )

    average_score = float(
        np.mean([report["score_breakdown"]["score"] for report in scenario_reports])
    )

    return {
        "average_score": round(average_score, 4),
        "score_ceiling": 100.0,
        "sustaindc_root": str(resolved_root),
        "noop_reference_source": "frozen_table" if noop_reference else "recomputed_in_process",
        "scenario_reports": scenario_reports,
        "candidate_aggregate": aggregate_metrics(candidate_results),
        "noop_aggregate": aggregate_metrics(noop_results),
        "feature_reference": {
            "agent_ls": LS_FEATURES,
            "agent_dc": DC_FEATURES,
            "agent_bat": BAT_FEATURES,
        },
    }


def format_report(report: Dict[str, Any]) -> str:
    lines = [
        "Function Benchmark Evaluation",
        f"Average score: {report['average_score']:.2f} / {report['score_ceiling']:.2f}",
        "",
    ]

    for scenario_report in report["scenario_reports"]:
        scenario = scenario_report["scenario"]
        score = scenario_report["score_breakdown"]["score"]
        candidate = scenario_report["candidate"]
        noop = scenario_report["noop_reference"]
        lines.extend(
            [
                f"[{scenario['name']}] {scenario['description']}",
                f"  score: {score:.2f} / 100.00",
                (
                    "  candidate metrics: "
                    f"carbon={candidate['carbon_kg']:.2f}kg, "
                    f"water={candidate['water_l']:.2f}L, "
                    f"dropped={candidate['dropped_tasks']:.0f}, "
                    f"overdue={candidate['overdue_tasks']:.0f}"
                ),
                (
                    "  noop metrics:      "
                    f"carbon={noop['carbon_kg']:.2f}kg, "
                    f"water={noop['water_l']:.2f}L, "
                    f"dropped={noop['dropped_tasks']:.0f}, "
                    f"overdue={noop['overdue_tasks']:.0f}"
                ),
                "",
            ]
        )

    candidate_aggregate = report["candidate_aggregate"]
    lines.extend(
        [
            "Aggregate candidate metrics",
            json.dumps(candidate_aggregate, indent=2),
            "",
            "Aggregate noop reference metrics",
            json.dumps(report["noop_aggregate"], indent=2),
        ]
    )
    return "\n".join(lines)
