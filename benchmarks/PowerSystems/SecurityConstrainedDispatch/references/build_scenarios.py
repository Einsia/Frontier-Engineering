from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from pypower.idx_bus import BUS_TYPE, REF
from pypower.idx_gen import GEN_BUS, GEN_STATUS, PG, PMAX, PMIN, VG


TASK_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(TASK_ROOT))

from verification.grid_utils import (  # noqa: E402
    apply_scenario,
    assess_result,
    generation_cost,
    load_case,
    run_candidate_pf,
    run_reference_opf,
)


CASE_SPECS = {
    "case24_ieee_rts": {
        "file": "pglib_opf_case24_ieee_rts.m",
        "outages": [6, 14],
    },
    "case57_ieee": {
        "file": "pglib_opf_case57_ieee.m",
        "outages": [5, 6],
    },
    "case73_ieee_rts": {
        "file": "pglib_opf_case73_ieee_rts.m",
        "outages": [6, 85],
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def marginal_cost(cost_row: np.ndarray, pg_mw: float) -> float:
    model = int(cost_row[0])
    count = int(cost_row[3])
    if model != 2 or count < 1:
        return 0.0
    coefficients = cost_row[4 : 4 + count]
    derivative = np.polyder(coefficients)
    return float(np.polyval(derivative, pg_mw)) if len(derivative) else 0.0


def make_baseline(
    scenario_case: dict,
    reference: dict,
    *,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    reference_pg = np.asarray(reference["gen"][:, PG], dtype=float)
    reference_vg = np.asarray(reference["gen"][:, VG], dtype=float)
    reference_cost = generation_cost(reference)
    gen = scenario_case["gen"]
    bus_type = {int(row[0]): int(row[BUS_TYPE]) for row in scenario_case["bus"]}
    controllable = [
        index
        for index, row in enumerate(gen)
        if row[GEN_STATUS] > 0
        and row[PMAX] - row[PMIN] > 1e-6
        and bus_type[int(row[GEN_BUS])] != REF
    ]
    rng = np.random.default_rng(seed)
    best_pg = reference_pg.copy()
    best_vg = reference_vg.copy()
    best_cost = reference_cost

    # Solve an auxiliary linear-cost OPF that deliberately favors generators
    # with high original marginal cost. Its solution is physically feasible but
    # economically poor under the original objective. Interpolating toward it
    # creates a reproducible baseline with meaningful optimization headroom.
    adversarial_case = copy.deepcopy(scenario_case)
    for index in range(len(adversarial_case["gen"])):
        slope = marginal_cost(scenario_case["gencost"][index], reference_pg[index])
        adversarial_case["gencost"][index, :] = 0.0
        adversarial_case["gencost"][index, 0] = 2.0
        adversarial_case["gencost"][index, 3] = 2.0
        adversarial_case["gencost"][index, 4] = -slope
    adversarial = run_reference_opf(adversarial_case)
    if bool(adversarial.get("success", False)):
        adversarial_pg = np.asarray(adversarial["gen"][:, PG], dtype=float)
        adversarial_vg = np.asarray(adversarial["gen"][:, VG], dtype=float)
        for alpha in np.linspace(0.95, 0.05, 19):
            proposal = reference_pg + alpha * (adversarial_pg - reference_pg)
            proposal_vg = reference_vg + alpha * (adversarial_vg - reference_vg)
            result = run_candidate_pf(scenario_case, proposal, proposal_vg)
            valid, _ = assess_result(result)
            if not valid:
                continue
            cost = generation_cost(result)
            ratio = cost / max(reference_cost, 1e-9)
            if cost > best_cost and ratio <= 1.20:
                best_pg = proposal
                best_vg = proposal_vg
                best_cost = cost

    # First search the line segment between the AC-OPF point and the original
    # PGLib dispatch. This usually provides a realistic, costlier operating
    # point while retaining much of the reference solution's feasibility.
    original_pg = np.clip(gen[:, PG], gen[:, PMIN], gen[:, PMAX])
    original_vg = gen[:, VG].copy()
    for alpha in np.linspace(0.95, 0.05, 19):
        proposal = np.clip(
            reference_pg + alpha * (original_pg - reference_pg),
            gen[:, PMIN],
            gen[:, PMAX],
        )
        proposal_vg = reference_vg + alpha * (original_vg - reference_vg)
        result = run_candidate_pf(scenario_case, proposal, proposal_vg)
        valid, _ = assess_result(result)
        if not valid:
            continue
        cost = generation_cost(result)
        ratio = cost / max(reference_cost, 1e-9)
        if cost > best_cost and ratio <= 1.20:
            best_pg = proposal
            best_vg = proposal_vg
            best_cost = cost

    for _ in range(500):
        if len(controllable) < 2:
            break
        sampled = rng.choice(controllable, size=min(len(controllable), 8), replace=False)
        derivatives = {
            int(index): marginal_cost(scenario_case["gencost"][index], reference_pg[index])
            for index in sampled
        }
        cheap = min(sampled, key=lambda index: derivatives[int(index)])
        expensive = max(sampled, key=lambda index: derivatives[int(index)])
        if cheap == expensive:
            continue
        maximum_shift = min(
            reference_pg[cheap] - gen[cheap, PMIN],
            gen[expensive, PMAX] - reference_pg[expensive],
        )
        if maximum_shift <= 1e-6:
            continue
        shift = maximum_shift * float(rng.uniform(0.15, 0.8))
        proposal = reference_pg.copy()
        proposal[cheap] -= shift
        proposal[expensive] += shift
        result = run_candidate_pf(scenario_case, proposal, reference_vg)
        valid, _ = assess_result(result)
        if not valid:
            continue
        cost = generation_cost(result)
        ratio = cost / max(reference_cost, 1e-9)
        if cost > best_cost and ratio <= 1.20:
            best_pg = proposal
            best_vg = reference_vg
            best_cost = cost

    return best_pg, best_vg, best_cost


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=TASK_ROOT / "references" / "scenarios.json")
    args = parser.parse_args()

    pglib_dir = TASK_ROOT / "references" / "pglib"
    scenario_templates = (
        ("low_load", 0.98, None),
        ("nominal", 1.00, None),
        ("contingency_a", 1.00, "a"),
        ("contingency_b_high", 1.02, "b"),
    )
    records = []

    for case_number, (case_id, spec) in enumerate(CASE_SPECS.items()):
        source_path = pglib_dir / spec["file"]
        source = load_case(source_path)
        for scenario_number, (name, scale, outage_key) in enumerate(scenario_templates):
            outage = None
            if outage_key == "a":
                outage = spec["outages"][0]
            elif outage_key == "b":
                outage = spec["outages"][1]
            scenario_case = apply_scenario(source, load_scale=scale, outage_branch=outage)
            reference = run_reference_opf(scenario_case)
            valid_reference, reference_checks = assess_result(reference)
            if not valid_reference:
                raise RuntimeError(f"reference OPF is invalid for {case_id}/{name}: {reference_checks}")
            baseline_pg, baseline_vg, baseline_cost = make_baseline(
                scenario_case,
                reference,
                seed=20260713 + case_number * 100 + scenario_number,
            )
            baseline_result = run_candidate_pf(scenario_case, baseline_pg, baseline_vg)
            valid_baseline, baseline_checks = assess_result(baseline_result)
            if not valid_baseline:
                raise RuntimeError(f"baseline is invalid for {case_id}/{name}: {baseline_checks}")
            reference_cost = generation_cost(reference)
            records.append(
                {
                    "case_id": case_id,
                    "source_file": spec["file"],
                    "scenario_id": name,
                    "load_scale": scale,
                    "outage_branch": outage,
                    "reference_cost": reference_cost,
                    "baseline_cost": baseline_cost,
                    "baseline_pg_mw": [float(value) for value in baseline_pg],
                    "baseline_vg_pu": [float(value) for value in baseline_vg],
                }
            )

    payload = {
        "schema_version": 1,
        "pglib_release": "v23.07",
        "pglib_commit": "dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3",
        "case_sha256": {
            spec["file"]: sha256(pglib_dir / spec["file"])
            for spec in CASE_SPECS.values()
        },
        "scenarios": records,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} scenarios to {args.output}")
    for record in records:
        ratio = 100.0 * record["reference_cost"] / record["baseline_cost"]
        print(f"{record['case_id']}/{record['scenario_id']}: baseline score {ratio:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
