"""Reference solver for CVRP: GRASP multi-start + intra 2-opt +
relocate/swap/2-opt* + LNS refinement with greedy repair and tabu
diversification.

Pure standard library. Used to produce data/reference.json (the score
baseline per instance).

Deterministic: every source of randomness is seeded and the LNS search
budget is measured in *iterations*, not wall-clock time, so regenerating
reference.json on any machine yields byte-identical output. main() runs a
fixed list of seeds and keeps the best distance per instance.

Usage:
    python verification/ref_solver.py [--starts N] [--iterations N]

    --starts N       number of GRASP multi-start constructions (default 40)
    --iterations N   fixed LNS iterations per instance (default: max(100, 4*n))
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import deque
from pathlib import Path

INST_DIR = Path(__file__).resolve().parents[1] / "data" / "instances"
HELDOUT_DIR = Path(__file__).resolve().parents[1] / "data" / "instances_heldout"
OUT_JSON = Path(__file__).resolve().parents[1] / "data" / "reference.json"


def parse_instance(path: Path) -> dict:
    """Parse a TSPLIB-style CVRP .vrp file."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    coords: dict[int, tuple[float, float]] = {}
    demands: dict[int, int] = {}
    capacity = 0
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("CAPACITY"):
            capacity = int(line.split(":")[-1].strip())
            continue
        if upper == "NODE_COORD_SECTION":
            section = "coords"
            continue
        if upper == "DEMAND_SECTION":
            section = "demand"
            continue
        if upper == "DEPOT_SECTION":
            section = "depot"
            continue
        if upper == "EOF" or upper.startswith("EDGE_WEIGHT") or upper.startswith("DISPLAY_DATA"):
            section = None
            continue
        if upper.startswith(("NAME", "COMMENT", "TYPE", "DIMENSION")):
            continue
        if section == "coords":
            parts = line.split()
            if len(parts) >= 3:
                coords[int(parts[0])] = (float(parts[1]), float(parts[2]))
        elif section == "demand":
            parts = line.split()
            if len(parts) >= 2:
                demands[int(parts[0])] = int(parts[1])
    n_customers = max(coords) - 1  # depot is id 1, customers are ids 2..n+1
    pts = [coords[1]] + [coords[i] for i in range(2, n_customers + 2)]
    dist = [[0] * (n_customers + 1) for _ in range(n_customers + 1)]
    for i in range(n_customers + 1):
        for j in range(n_customers + 1):
            dx = pts[i][0] - pts[j][0]
            dy = pts[i][1] - pts[j][1]
            dist[i][j] = int(round(math.hypot(dx, dy)))
    demand = [0] + [demands.get(i, 0) for i in range(2, n_customers + 2)]
    return {
        "n": n_customers,
        "capacity": capacity,
        "demand": demand,
        "distance": dist,
        "name": path.stem,
    }


def route_dist(seq: list[int], dist: list[list[int]]) -> int:
    if not seq:
        return 0
    total = dist[0][seq[0]]
    for a, b in zip(seq, seq[1:]):
        total += dist[a][b]
    total += dist[seq[-1]][0]
    return total


def two_opt(seq: list[int], dist: list[list[int]]) -> list[int]:
    best = seq[:]
    improved = True
    while improved:
        improved = False
        for a in range(len(best) - 1):
            for b in range(a + 1, len(best)):
                cand = best[:a] + best[a : b + 1][::-1] + best[b + 1 :]
                if route_dist(cand, dist) < route_dist(best, dist):
                    best = cand
                    improved = True
    return best


def savings_solve(inst: dict, rng: random.Random | None = None) -> list[list[int]]:
    n, cap = inst["n"], inst["capacity"]
    demand, dist = inst["demand"], inst["distance"]
    routes = {c: [c] for c in range(1, n + 1)}
    load = {c: demand[c] for c in range(1, n + 1)}
    first = {c: c for c in range(1, n + 1)}
    last = {c: c for c in range(1, n + 1)}
    owner = {c: c for c in range(1, n + 1)}

    savings = []
    for i in range(1, n + 1):
        for j in range(i + 1, n + 1):
            savings.append((dist[0][i] + dist[0][j] - dist[i][j], i, j))
    if rng is None:
        savings.sort(reverse=True)
    else:
        # Randomized savings (GRASP-style perturbation) for multi-start search.
        savings.sort(
            key=lambda t: t[0] + rng.uniform(-abs(t[0]) * 0.5, abs(t[0]) * 0.5),
            reverse=True,
        )

    for _s, i, j in savings:
        ri, rj = owner[i], owner[j]
        if ri == rj:
            continue
        if load[ri] + load[rj] > cap:
            continue
        # Merge rj into ri when ri's tail == i and rj's head == j (or symmetric).
        if last[ri] == i and first[rj] == j:
            for c in routes[rj]:
                owner[c] = ri
            routes[ri] = routes[ri] + routes[rj]
            load[ri] += load[rj]
            last[ri] = last[rj]
            del routes[rj], load[rj], first[rj], last[rj]
        elif last[rj] == i and first[ri] == j:
            for c in routes[ri]:
                owner[c] = rj
            routes[rj] = routes[rj] + routes[ri]
            load[rj] += load[ri]
            last[rj] = last[ri]
            del routes[ri], load[ri], first[ri], last[ri]
        elif last[ri] == j and first[rj] == i:
            for c in routes[rj]:
                owner[c] = ri
            routes[ri] = routes[ri] + routes[rj]
            load[ri] += load[rj]
            last[ri] = last[rj]
            del routes[rj], load[rj], first[rj], last[rj]
        elif last[rj] == j and first[ri] == i:
            for c in routes[ri]:
                owner[c] = rj
            routes[rj] = routes[rj] + routes[ri]
            load[rj] += load[ri]
            last[rj] = last[ri]
            del routes[ri], load[ri], first[ri], last[ri]

    final = []
    for seq in routes.values():
        final.append(two_opt(seq, dist))
    return final


def relocate_improve(routes: list[list[int]], inst: dict) -> list[list[int]]:
    """Best-improve cross-route relocate local search.

    Repeatedly moves the single customer that most reduces total distance
    (removal from its route + best insertion into another route), respecting
    capacity, until no improving move remains.
    """
    n, cap, demand, dist = inst["n"], inst["capacity"], inst["demand"], inst["distance"]
    routes = [list(r) for r in routes if r]
    improved = True
    while improved:
        improved = False
        best_gain = 0.0
        best = None  # (ri, pos, rj, c)
        for ri in range(len(routes)):
            route = routes[ri]
            if not route:
                continue
            d_ri = route_dist(route, dist)
            for pos in range(len(route)):
                c = route[pos]
                ra = route[:pos] + route[pos + 1 :]
                d_ra = route_dist(ra, dist) if ra else 0
                gain_remove = d_ri - d_ra
                for rj in range(len(routes)):
                    if rj == ri:
                        continue
                    rj_route = routes[rj]
                    if not rj_route:
                        if demand[c] > cap:
                            continue
                        gain_insert = -(dist[0][c] + dist[c][0])
                    else:
                        if sum(demand[x] for x in rj_route) + demand[c] > cap:
                            continue
                        d_rj = route_dist(rj_route, dist)
                        gain_insert = max(
                            d_rj
                            - route_dist(
                                rj_route[:ipos] + [c] + rj_route[ipos:], dist
                            )
                            for ipos in range(len(rj_route) + 1)
                        )
                    total = gain_remove + gain_insert
                    if total > best_gain + 1e-9:
                        best_gain = total
                        best = (ri, pos, rj, c)
        if best is not None:
            ri, pos, rj, c = best
            routes[ri].pop(pos)
            if not routes[ri]:
                routes.pop(ri)
                if rj > ri:
                    rj -= 1
            rj_route = routes[rj]
            best_ipos = min(
                range(len(rj_route) + 1),
                key=lambda ipos: route_dist(rj_route[:ipos] + [c] + rj_route[ipos:], dist),
            )
            routes[rj].insert(best_ipos, c)
            improved = True
    return routes


def swap_improve(routes: list[list[int]], inst: dict) -> list[list[int]]:
    """Best-improve cross-route swap local search (exchange one customer each)."""
    cap, demand, dist = inst["capacity"], inst["demand"], inst["distance"]
    routes = [list(r) for r in routes if r]
    improved = True
    while improved:
        improved = False
        best_gain = 0.0
        best = None  # (ri, pi, rj, pj)
        for ri in range(len(routes)):
            for rj in range(ri + 1, len(routes)):
                a, b = routes[ri], routes[rj]
                load_a = sum(demand[x] for x in a)
                load_b = sum(demand[x] for x in b)
                d_a = route_dist(a, dist)
                d_b = route_dist(b, dist)
                for pi in range(len(a)):
                    ci = a[pi]
                    for pj in range(len(b)):
                        cj = b[pj]
                        if load_a - demand[ci] + demand[cj] > cap:
                            continue
                        if load_b - demand[cj] + demand[ci] > cap:
                            continue
                        new_a = a[:pi] + [cj] + a[pi + 1 :]
                        new_b = b[:pj] + [ci] + b[pj + 1 :]
                        gain = (d_a + d_b) - (
                            route_dist(new_a, dist) + route_dist(new_b, dist)
                        )
                        if gain > best_gain + 1e-9:
                            best_gain = gain
                            best = (ri, pi, rj, pj)
        if best is not None:
            ri, pi, rj, pj = best
            routes[ri][pi], routes[rj][pj] = routes[rj][pj], routes[ri][pi]
            improved = True
    return routes


def two_opt_star_improve(routes: list[list[int]], inst: dict) -> list[list[int]]:
    """Best-improve cross-route 2-opt* local search (swap route tails)."""
    cap, demand, dist = inst["capacity"], inst["demand"], inst["distance"]
    routes = [list(r) for r in routes if r]
    improved = True
    while improved:
        improved = False
        best_gain = 0.0
        best = None  # (ri, rj, new_a, new_b)
        for ri in range(len(routes)):
            for rj in range(ri + 1, len(routes)):
                a, b = routes[ri], routes[rj]
                d_a = route_dist(a, dist)
                d_b = route_dist(b, dist)
                for pi in range(len(a)):
                    for pj in range(len(b)):
                        new_a = a[: pi + 1] + b[pj + 1 :]
                        new_b = b[: pj + 1] + a[pi + 1 :]
                        if sum(demand[x] for x in new_a) > cap:
                            continue
                        if sum(demand[x] for x in new_b) > cap:
                            continue
                        gain = (d_a + d_b) - (
                            route_dist(new_a, dist) + route_dist(new_b, dist)
                        )
                        if gain > best_gain + 1e-9:
                            best_gain = gain
                            best = (ri, rj, new_a, new_b)
        if best is not None:
            ri, rj, new_a, new_b = best
            routes[ri] = new_a
            routes[rj] = new_b
            improved = True
    return routes


def local_search(routes: list[list[int]], inst: dict) -> list[list[int]]:
    """Intensify a solution: intra 2-opt + Or-opt + relocate + swap + 2-opt*
    to a fixed point."""
    dist = inst["distance"]
    routes = [list(r) for r in routes if r]
    improved = True
    while improved:
        before = sum(route_dist(r, dist) for r in routes)
        routes = [two_opt(r, dist) for r in routes]
        routes = relocate_improve(routes, inst)
        routes = swap_improve(routes, inst)
        routes = two_opt_star_improve(routes, inst)
        after = sum(route_dist(r, dist) for r in routes)
        improved = after < before - 1e-9
    return routes


def greedy_repair(
    routes: list[list[int]], unrouted: list[int], inst: dict, rng: random.Random
) -> list[list[int]]:
    """Reinsert every customer in `unrouted` at its cheapest feasible position.

    Insertion order is a random permutation driven by `rng`, and a new route
    (depot-customer-depot) is used whenever it is cheaper than any feasible
    insertion or none exists. Deterministic for a fixed `rng`.
    """
    cap, demand, dist = inst["capacity"], inst["demand"], inst["distance"]
    routes = [list(r) for r in routes if r]
    for c in rng.sample(unrouted, len(unrouted)):
        best_inc = None  # cheapest insertion cost increase
        best_pos = None  # (route index, position)
        for ri, r in enumerate(routes):
            if sum(demand[x] for x in r) + demand[c] > cap:
                continue
            for pos in range(len(r) + 1):
                pred = r[pos - 1] if pos > 0 else 0
                succ = r[pos] if pos < len(r) else 0
                inc = dist[pred][c] + dist[c][succ] - dist[pred][succ]
                if best_inc is None or inc < best_inc - 1e-9:
                    best_inc = inc
                    best_pos = (ri, pos)
        new_route_inc = 2 * dist[0][c]
        if best_inc is None or new_route_inc < best_inc - 1e-9:
            routes.append([c])
        else:
            ri, pos = best_pos
            routes[ri].insert(pos, c)
    return routes


def lns_improve(
    routes: list[list[int]],
    inst: dict,
    rng: random.Random,
    max_iters: int,
    tabu_size: int = 12,
) -> list[list[int]]:
    """Large neighbourhood search with tabu diversification.

    Repeat (deterministically, seeded by `rng`) `max_iters` times: destroy
    25%-50% of customers, reinsert them with `greedy_repair`, then intensify
    with `local_search`. Destroy sets recently used are skipped (tabu list),
    so the search keeps exploring. Returns the best solution found.
    """
    n, cap, demand, dist = inst["n"], inst["capacity"], inst["demand"], inst["distance"]
    best = [list(r) for r in routes if r]
    best_cost = sum(route_dist(r, dist) for r in best)
    tabu: deque[tuple[int, ...]] = deque()
    tabu_set: set[tuple[int, ...]] = set()

    for _ in range(max_iters):
        remove = None
        for _attempt in range(8):
            q = rng.randint(max(1, n // 4), max(1, n // 2))
            cand = tuple(sorted(rng.sample(range(1, n + 1), q)))
            if cand not in tabu_set:
                remove = cand
                break
        if remove is None:
            remove = tuple(sorted(rng.sample(range(1, n + 1), rng.randint(max(1, n // 4), max(1, n // 2)))))
        tabu_set.add(remove)
        tabu.append(remove)
        if len(tabu) > tabu_size:
            tabu_set.discard(tabu.popleft())

        remove_set = set(remove)
        temp = []
        for r in best:
            nr = [c for c in r if c not in remove_set]
            if nr:
                temp.append(nr)
        temp = greedy_repair(temp, sorted(remove), inst, rng)
        temp = local_search(temp, inst)
        cost = sum(route_dist(r, dist) for r in temp)
        if cost < best_cost - 1e-9:
            best = [list(r) for r in temp]
            best_cost = cost
    return best


def grasp_solve(
    inst: dict, starts: int = 40, seed: int = 123, lns_iters: int | None = None
) -> list[list[int]]:
    """GRASP-style multi-start: randomized savings + local search, keep best.

    When `lns_iters` is given, refine the best solution with deterministic
    iteration-budgeted LNS.
    """
    rng = random.Random(seed)
    best: list[list[int]] | None = None
    best_d = float("inf")
    dist = inst["distance"]
    for k in range(starts):
        # First start uses the deterministic savings order (guaranteed baseline);
        # remaining starts use randomized savings for diversification.
        routes = savings_solve(inst, rng=None if k == 0 else rng)
        routes = [two_opt(r, dist) for r in routes]
        routes = relocate_improve(routes, inst)
        routes = swap_improve(routes, inst)
        routes = [two_opt(r, dist) for r in routes]
        d = sum(route_dist(r, dist) for r in routes)
        if d < best_d:
            best_d = d
            best = routes
    if best is not None and lns_iters is not None and lns_iters > 0:
        best = lns_improve(best, inst, random.Random(seed + 1), lns_iters)
    return best or []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate CVRP reference distances")
    parser.add_argument("--starts", type=int, default=40, help="GRASP multi-start count")
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="LNS iterations per instance (default: max(100, 4*n))",
    )
    args = parser.parse_args(argv)

    # A few fixed seeds diversify the search; the best distance per instance is
    # kept. The seed list is a constant so regeneration is byte-identical.
    seeds = (123, 2024, 7)
    results = {}

    def _solve_dir(inst_dir: Path) -> None:
        for path in sorted(inst_dir.glob("*.vrp")):
            inst = parse_instance(path)
            iters = args.iterations if args.iterations else max(100, 4 * inst["n"])
            best_total = min(
                sum(
                    route_dist(r, inst["distance"])
                    for r in grasp_solve(inst, starts=args.starts, seed=seed, lns_iters=iters)
                )
                for seed in seeds
            )
            results[inst["name"]] = best_total
            print(f"{inst['name']}: ref_dist={best_total} (iters={iters}, seeds={seeds})")

    _solve_dir(INST_DIR)
    if HELDOUT_DIR.is_dir():
        _solve_dir(HELDOUT_DIR)
    OUT_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",  # force LF so regeneration is byte-identical on any OS
    )
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
