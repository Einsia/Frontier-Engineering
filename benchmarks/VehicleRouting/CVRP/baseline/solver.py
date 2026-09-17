"""CVRP candidate solver (baseline: random-order cheapest insertion).

Contract:
  * Run standalone:  python baseline/solver.py <instance.vrp> <output.json>
  * `solve(instance)` returns a list of routes; each route is a list of
    customer ids (1..n) visited in order. The depot (id 0) is implicit at
    both ends and must NOT appear in the route.
  * instance dict fields:
      - n        : number of customers (ids 1..n)
      - capacity : vehicle capacity
      - demand   : demand[0..n], demand[0] == 0
      - distance : (n+1)x(n+1) rounded Euclidean distance matrix
"""
import json
import math
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixed section: instance parsing and I/O. Do not modify.
# ---------------------------------------------------------------------------
def parse_instance(path):
    """Parse a TSPLIB-style CVRP .vrp file into an instance dict."""
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    coords = {}
    demands = {}
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
            section = None
            continue
        if upper == "EOF" or upper.startswith(("EDGE_WEIGHT", "DISPLAY_DATA")):
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
    return {
        "n": n_customers,
        "capacity": capacity,
        "demand": [0] + [demands.get(i, 0) for i in range(2, n_customers + 2)],
        "distance": dist,
    }


def main():
    inst_path, out_path = sys.argv[1], sys.argv[2]
    inst = parse_instance(inst_path)
    routes = solve(inst)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(routes, fh)


# ---------------------------------------------------------------------------
# EVOLVE-BLOCK-START
# ---------------------------------------------------------------------------
def solve(instance):
    """Random-order cheapest insertion: process customers in a random order
    (seeded) and insert each at its cheapest feasible position across all
    routes. A standard randomized-construction baseline."""
    import random

    rng = random.Random(42)
    n = instance["n"]
    capacity = instance["capacity"]
    demand = instance["demand"]
    dist = instance["distance"]

    order = list(range(1, n + 1))
    rng.shuffle(order)
    routes = []

    def best_place(cust):
        best = None
        for ri, route in enumerate(routes):
            load = sum(demand[c] for c in route)
            if load + demand[cust] > capacity:
                continue
            for pos in range(len(route) + 1):
                prev = 0 if pos == 0 else route[pos - 1]
                nxt = 0 if pos == len(route) else route[pos]
                cost = dist[prev][cust] + dist[cust][nxt] - dist[prev][nxt]
                if best is None or cost < best[0]:
                    best = (cost, ri, pos)
        return best

    for cust in order:
        b = best_place(cust)
        if b is None:
            routes.append([cust])
        else:
            routes[b[1]].insert(b[2], cust)
    return routes


# ---------------------------------------------------------------------------
# EVOLVE-BLOCK-END
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
