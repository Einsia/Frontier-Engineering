import math
import random


def generate_instances(seed):
    rng = random.Random(seed)
    n = 14 + seed % 5
    groups = ["consumer", "merchant", "enterprise"]
    queries = []
    eps_min_sum = 0.0
    for i in range(n):
        group = groups[i % len(groups)]
        tier = i % 4
        sensitivity = round(0.35 + 0.18 * tier + rng.random() * 0.22, 6)
        if i % 6 == 0:
            sensitivity = round(sensitivity + 0.75, 6)
        business_value = round(5.0 + rng.random() * 15.0 + (4.0 if i % 6 == 0 else 0.0), 6)
        population_coverage = round(0.18 + rng.random() * 0.72, 6)
        epsilon_min = round(0.055 + 0.018 * (i % 3), 6)
        epsilon_max = round(epsilon_min + 0.62 + rng.random() * 0.72, 6)
        max_error = round(sensitivity / epsilon_min * 1.0001, 6)
        eps_min_sum += epsilon_min
        queries.append({
            "id": "q_%02d" % i,
            "sensitivity": sensitivity,
            "business_value": business_value,
            "population_coverage": population_coverage,
            "epsilon_min": epsilon_min,
            "epsilon_max": epsilon_max,
            "max_error": max_error,
            "group": group,
        })
    extra = 0.47 * n + rng.random() * 0.35
    max_extra = sum(q["epsilon_max"] - q["epsilon_min"] for q in queries)
    epsilon_total = round(eps_min_sum + min(extra, max_extra * 0.72), 6)
    return [{
        "queries": queries,
        "epsilon_total": epsilon_total,
        "fairness": {"max_group_error_ratio": 2.35},
    }]


def _error(q, eps):
    return float(q["sensitivity"]) / float(eps)


def _objective(instance, allocations):
    total = 1.0
    for q in instance["queries"]:
        eps = float(allocations[q["id"]])
        value_weight = float(q["business_value"]) * float(q["population_coverage"])
        sensitivity = float(q["sensitivity"])
        error = sensitivity / eps
        total += value_weight * math.log1p(2.4 * eps) - 0.18 * value_weight * error / (1.0 + sensitivity)
    if total <= 0.0:
        total = 1e-12
    return float(total)


def _group_average_errors(instance, allocations):
    group_errors = {}
    group_counts = {}
    for q in instance["queries"]:
        group = q["group"]
        group_errors[group] = group_errors.get(group, 0.0) + _error(q, allocations[q["id"]])
        group_counts[group] = group_counts.get(group, 0) + 1
    return {group: group_errors[group] / group_counts[group] for group in group_errors}


def _fairness_ratio(instance, allocations):
    avgs = list(_group_average_errors(instance, allocations).values())
    if not avgs:
        return 1.0
    smallest = min(avgs)
    if smallest <= 0.0:
        return float("inf")
    return max(avgs) / smallest


def _repair_fairness(instance, allocations, remaining, step=0.01):
    queries = list(instance["queries"])
    q_by_id = {q["id"]: q for q in queries}
    limit = float(instance["fairness"]["max_group_error_ratio"])
    iterations = 0
    while remaining > 1e-12 and _fairness_ratio(instance, allocations) > limit + 1e-9:
        averages = _group_average_errors(instance, allocations)
        if not averages:
            break
        worst_group = max(averages, key=averages.get)
        candidates = []
        for q in queries:
            qid = q["id"]
            if q["group"] != worst_group:
                continue
            cap = float(q["epsilon_max"]) - allocations[qid]
            if cap <= 1e-12:
                continue
            # d(sensitivity / epsilon) / d epsilon = -sensitivity / epsilon^2.
            reduction = float(q["sensitivity"]) / (allocations[qid] * allocations[qid])
            candidates.append((reduction, qid, cap))
        if not candidates:
            break
        _reduction, qid, cap = max(candidates)
        add = min(step, remaining, cap)
        allocations[qid] += add
        remaining -= add
        iterations += 1
        if iterations > 10000:
            break
    return remaining


def _allocate_feasible_greedy(instance, allocations, remaining, score_delta, step=0.01):
    queries = list(instance["queries"])
    while remaining > 1e-12:
        best_q = None
        best_gain = -1e100
        for q in queries:
            qid = q["id"]
            cap = float(q["epsilon_max"]) - allocations[qid]
            if cap <= 1e-12:
                continue
            delta = min(step, remaining, cap)
            before = allocations[qid]
            allocations[qid] = before + delta
            ok, _ = validate_solution(instance, {"allocations": dict(allocations)})
            allocations[qid] = before
            if not ok:
                continue
            gain = score_delta(q, allocations, delta)
            if gain > best_gain:
                best_gain = gain
                best_q = q
        if best_q is None:
            break
        qid = best_q["id"]
        add = min(step, remaining, float(best_q["epsilon_max"]) - allocations[qid])
        if add <= 1e-12:
            break
        allocations[qid] += add
        remaining -= add
    return remaining


def validate_solution(instance, solution):
    if not isinstance(solution, dict) or set(solution.keys()) != {"allocations"}:
        return False, "solution must be a dict with only an allocations field"
    allocations = solution.get("allocations")
    if not isinstance(allocations, dict):
        return False, "allocations must be a dict"
    queries = list(instance["queries"])
    expected = {q["id"] for q in queries}
    if set(allocations.keys()) != expected:
        return False, "allocations must cover exactly the query ids"
    total = 0.0
    group_errors = {}
    group_counts = {}
    for q in queries:
        qid = q["id"]
        eps = allocations[qid]
        if not isinstance(eps, (int, float)) or isinstance(eps, bool) or not math.isfinite(eps):
            return False, "allocation for %s is not a finite number" % qid
        eps = float(eps)
        if eps < float(q["epsilon_min"]) - 1e-9:
            return False, "allocation for %s is below epsilon_min" % qid
        if eps > float(q["epsilon_max"]) + 1e-9:
            return False, "allocation for %s is above epsilon_max" % qid
        total += eps
        err = _error(q, eps)
        if err > float(q["max_error"]) + 1e-8:
            return False, "allocation for %s exceeds max_error" % qid
        group = q["group"]
        group_errors[group] = group_errors.get(group, 0.0) + err
        group_counts[group] = group_counts.get(group, 0) + 1
    if total > float(instance["epsilon_total"]) + 1e-8:
        return False, "total epsilon exceeds epsilon_total"
    avgs = [group_errors[g] / group_counts[g] for g in group_errors]
    if avgs:
        smallest = min(avgs)
        largest = max(avgs)
        if smallest <= 0.0:
            return False, "group average error must be positive"
        ratio = largest / smallest
        if ratio > float(instance["fairness"]["max_group_error_ratio"]) + 1e-9:
            return False, "group error fairness ratio exceeded"
    return True, "ok"


def evaluate_solution(instance, solution):
    ok, _ = validate_solution(instance, solution)
    if not ok:
        return -1e18
    value = _objective(instance, solution["allocations"])
    if not math.isfinite(value) or value <= 0.0:
        return 1e-12
    return float(value)


def _baseline_allocations(instance):
    queries = list(instance["queries"])
    allocations = {q["id"]: float(q["epsilon_min"]) for q in queries}
    remaining = float(instance["epsilon_total"]) - sum(allocations.values())
    if remaining <= 0.0:
        return allocations
    remaining = _repair_fairness(instance, allocations, remaining)
    remaining = min(remaining, 0.25 * float(instance["epsilon_total"]))
    rounds = 0
    while remaining > 1e-12 and rounds < 10000:
        used = 0.0
        for q in sorted(queries, key=lambda x: x["id"]):
            qid = q["id"]
            cap = float(q["epsilon_max"]) - allocations[qid]
            if cap <= 1e-12:
                continue
            add = min(0.02, cap, remaining)
            allocations[qid] += add
            ok, _ = validate_solution(instance, {"allocations": dict(allocations)})
            if ok:
                remaining -= add
                used += add
            else:
                allocations[qid] -= add
            if remaining <= 1e-12:
                break
        if used <= 1e-12:
            break
        rounds += 1
    return allocations


def solve_baseline(instance):
    return {"allocations": _baseline_allocations(instance)}


def solve_random(instance):
    queries = list(instance["queries"])
    allocations = {q["id"]: float(q["epsilon_min"]) for q in queries}
    remaining = float(instance["epsilon_total"]) - sum(allocations.values())
    remaining = _repair_fairness(instance, allocations, remaining)
    return {"allocations": allocations}


def solve_reference(instance):
    queries = list(instance["queries"])
    allocations = {q["id"]: float(q["epsilon_min"]) for q in queries}
    remaining = float(instance["epsilon_total"]) - sum(allocations.values())
    if remaining <= 0.0:
        return {"allocations": allocations}
    remaining = _repair_fairness(instance, allocations, remaining)

    def gain(q, current_allocations, delta):
        qid = q["id"]
        before = current_allocations[qid]
        old = _objective(instance, current_allocations)
        current_allocations[qid] = before + delta
        try:
            return (_objective(instance, current_allocations) - old) / delta
        finally:
            current_allocations[qid] = before

    _allocate_feasible_greedy(instance, allocations, remaining, gain)
    return {"allocations": allocations}
