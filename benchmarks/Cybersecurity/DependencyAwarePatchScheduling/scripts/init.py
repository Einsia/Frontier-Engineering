from __future__ import annotations

import json
import sys
from typing import Any


# EVOLVE-BLOCK-START
def solve(instance):
    scale = 1000000
    horizon = instance['horizon']
    patches = {p['patch_id']: p for p in instance['patches']}
    vulnerabilities = {v['vulnerability_id']: v for v in instance['vulnerabilities']}
    assets = {a['asset_id']: a for a in instance['assets']}
    services = {s['service_id']: s for s in instance['services']}
    resources = {r['resource_id']: r for r in instance['resources']}

    def rounded_div(numerator, denominator):
        return (numerator + denominator // 2) // denominator

    def security_loss(vulnerability, remediation_slot):
        remaining_ppm = scale
        limit = min(horizon, remediation_slot)
        probabilities = vulnerability['exploit_probability_ppm_by_slot']
        for slot in range(limit):
            remaining_ppm = rounded_div(remaining_ppm * (scale - probabilities[slot]), scale)
        breach_ppm = scale - remaining_ppm
        adjusted_impact = rounded_div(vulnerability['impact_microunits'] * vulnerability['criticality_ppm'], scale)
        return rounded_div(adjusted_impact * breach_ppm, scale)

    def objective(schedule):
        remediation = {vid: horizon for vid in vulnerabilities}
        for entry in schedule:
            patch = patches[entry['patch_id']]
            completion = entry['start_slot'] + patch['duration']
            for vid in patch['covered_vulnerability_ids']:
                if completion < remediation[vid]:
                    remediation[vid] = completion
        security_total = sum((security_loss(vulnerability, remediation[vid]) for vid, vulnerability in vulnerabilities.items()))
        downtime_total = 0
        rollback_total = 0
        for entry in schedule:
            patch = patches[entry['patch_id']]
            start = entry['start_slot']
            end = start + patch['duration']
            for demand in patch['service_demands']:
                service = services[demand['service_id']]
                units = demand['downtime_units']
                for slot in range(start, end):
                    downtime_total += units * service['loss_microunits_by_slot'][slot]
            rollback_total += rounded_div(patch['rollback_probability_ppm'] * patch['rollback_impact_microunits'], scale)
        return max(1, security_total + downtime_total + rollback_total)

    def contained(windows, start, end):
        return any((window['start_slot'] <= start and end <= window['end_slot'] for window in windows))

    def feasible(schedule):
        selected = {entry['patch_id']: entry['start_slot'] for entry in schedule}
        if len(selected) != len(schedule):
            return False
        records = []
        for entry in schedule:
            pid = entry['patch_id']
            start = entry['start_slot']
            patch = patches[pid]
            end = start + patch['duration']
            if start < 0 or end > horizon:
                return False
            for prerequisite in patch['prerequisite_patch_ids']:
                if prerequisite not in selected:
                    return False
                prerequisite_end = selected[prerequisite] + patches[prerequisite]['duration']
                if prerequisite_end > start:
                    return False
            for aid in patch['affected_asset_ids']:
                if not contained(assets[aid]['maintenance_windows'], start, end):
                    return False
            for demand in patch['service_demands']:
                service = services[demand['service_id']]
                if not contained(service['maintenance_windows'], start, end):
                    return False
            records.append((pid, start, end, patch))
        occupied_assets = set()
        for pid, start, end, patch in records:
            for aid in patch['affected_asset_ids']:
                if not assets[aid]['exclusive_change']:
                    continue
                for slot in range(start, end):
                    key = (aid, slot)
                    if key in occupied_assets:
                        return False
                    occupied_assets.add(key)
        resource_usage = {rid: [0] * horizon for rid in resources}
        service_usage = {sid: [0] * horizon for sid in services}
        for pid, start, end, patch in records:
            for demand in patch['resource_demands']:
                usage = resource_usage[demand['resource_id']]
                for slot in range(start, end):
                    usage[slot] += demand['units']
            for demand in patch['service_demands']:
                usage = service_usage[demand['service_id']]
                for slot in range(start, end):
                    usage[slot] += demand['downtime_units']
        for rid, usage in resource_usage.items():
            capacity = resources[rid]['capacity_by_slot']
            if any((usage[slot] > capacity[slot] for slot in range(horizon))):
                return False
        for sid, usage in service_usage.items():
            service = services[sid]
            capacity = service['downtime_capacity_by_slot']
            if any((usage[slot] > capacity[slot] for slot in range(horizon))):
                return False
            if sum(usage) > service['downtime_budget']:
                return False
        return True

    def closure(root):
        ordered = []
        seen = set()

        def visit(pid):
            if pid in seen:
                return
            seen.add(pid)
            for prerequisite in sorted(patches[pid]['prerequisite_patch_ids']):
                visit(prerequisite)
            ordered.append(pid)
        visit(root)
        return ordered

    def priority_order():
        full_losses = {vid: security_loss(vulnerability, horizon) for vid, vulnerability in vulnerabilities.items()}
        scored = []
        for root in sorted(patches):
            bundle = closure(root)
            covered = set()
            penalty = 0
            work = 0
            for pid in bundle:
                patch = patches[pid]
                covered.update(patch['covered_vulnerability_ids'])
                work += patch['duration'] * (1 + sum((d['units'] for d in patch['resource_demands'])) + sum((d['downtime_units'] for d in patch['service_demands'])))
                penalty += rounded_div(patch['rollback_probability_ppm'] * patch['rollback_impact_microunits'], scale)
                for demand in patch['service_demands']:
                    service = services[demand['service_id']]
                    average_rate = sum(service['loss_microunits_by_slot']) // horizon
                    penalty += patch['duration'] * demand['downtime_units'] * average_rate
            benefit = sum((full_losses[vid] for vid in covered))
            net = max(0, benefit - penalty)
            density = net * scale // max(1, work)
            scored.append((-density, root))
        scored.sort()
        return [root for _, root in scored]

    def earliest_start(pid, schedule):
        patch = patches[pid]
        selected = {entry['patch_id']: entry['start_slot'] for entry in schedule}
        lower_bound = 0
        for prerequisite in patch['prerequisite_patch_ids']:
            if prerequisite not in selected:
                return None
            lower_bound = max(lower_bound, selected[prerequisite] + patches[prerequisite]['duration'])
        last_start = horizon - patch['duration']
        for start in range(lower_bound, last_start + 1):
            trial = schedule + [{'patch_id': pid, 'start_slot': start}]
            if feasible(trial):
                return start
        return None
    schedule = []
    current_value = objective(schedule)
    selected = set()
    for root in priority_order():
        if root in selected:
            continue
        needed = [pid for pid in closure(root) if pid not in selected]
        trial = [dict(entry) for entry in schedule]
        failed = False
        for pid in needed:
            start = earliest_start(pid, trial)
            if start is None:
                failed = True
                break
            trial.append({'patch_id': pid, 'start_slot': start})
        if failed:
            continue
        trial_value = objective(trial)
        if trial_value < current_value:
            schedule = trial
            current_value = trial_value
            selected = {entry['patch_id'] for entry in schedule}
    schedule.sort(key=lambda entry: (entry['start_slot'], entry['patch_id']))
    return {'schedule': schedule}
# EVOLVE-BLOCK-END


def main() -> int:
    try:
        instance = json.load(sys.stdin)
        if not isinstance(instance, dict):
            raise TypeError("input must be a JSON object")
        solution = solve(instance)
        if not isinstance(solution, dict):
            raise TypeError("solve() must return a JSON object")
        json.dump(solution, sys.stdout, allow_nan=False, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        print(f"candidate error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
