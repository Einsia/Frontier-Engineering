"""Deterministic reduced-order simulator for an edge service control policy."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "references" / "config.json"
ROUTE_TOLERANCE = 1e-8
MAX_ACTION_ITEMS = 256


class ActionValidationError(ValueError):
    """Candidate action violates a structural or physical hard constraint."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class ScenarioTrace:
    name: str
    family: str
    seed: int
    feedback: bool
    workloads: tuple[dict[str, dict[str, float]], ...]
    failed_nodes: tuple[frozenset[str], ...]
    link_factors: tuple[dict[str, float], ...]
    recovery_start: int | None


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pair(source: str, target: str) -> str:
    return f"{source}->{target}"


def _base_demand(service_id: str, region_index: int, step: int, variant: float) -> float:
    base = {"api": 54.0, "search": 34.0, "media": 25.0}[service_id]
    region_factor = (1.08, 0.94, 0.82)[region_index]
    phase = (step + 2 * region_index) % 24
    day_wave = 0.82 + 0.30 * (1.0 + math.sin(2.0 * math.pi * phase / 24.0)) / 2.0
    return base * region_factor * day_wave * variant


def make_scenario(family: str, seed: int, *, feedback: bool) -> ScenarioTrace:
    """Generate every exogenous event before candidate execution."""

    rng = random.Random(seed)
    regions = ("edge-a", "edge-b", "edge-c")
    services = ("api", "search", "media")
    variant = 0.96 + 0.08 * rng.random()
    burst_region = regions[seed % len(regions)]
    failed_node = f"{burst_region[-1]}-{1 + seed % 2}"
    workloads: list[dict[str, dict[str, float]]] = []
    failed_nodes: list[frozenset[str]] = []
    link_factors: list[dict[str, float]] = []
    recovery_start: int | None = None

    for step in range(24):
        demand: dict[str, dict[str, float]] = {}
        for region_index, region in enumerate(regions):
            demand[region] = {}
            for service in services:
                value = _base_demand(service, region_index, step, variant)
                if family in {"regional_burst", "node_failure_burst"} and region == burst_region and 8 <= step <= 12:
                    value *= 1.85 if service != "media" else 1.55
                if family == "recovery_migration" and region == burst_region and 7 <= step <= 14:
                    value *= 1.45
                demand[region][service] = round(value, 6)
        workloads.append(demand)

        failed: set[str] = set()
        if family == "node_failure_burst" and 8 <= step <= 13:
            failed.add(failed_node)
            recovery_start = 14
        elif family == "recovery_migration" and 6 <= step <= 10:
            failed.add(failed_node)
            recovery_start = 11
        failed_nodes.append(frozenset(failed))

        factors: dict[str, float] = {}
        if family == "link_degradation" and 9 <= step <= 15:
            degraded_target = regions[(seed + 1) % len(regions)]
            factors[_pair(burst_region, degraded_target)] = 0.22
            factors[_pair(degraded_target, burst_region)] = 0.22
        link_factors.append(factors)

    return ScenarioTrace(
        name=f"{family}-v{seed % 100}",
        family=family,
        seed=seed,
        feedback=feedback,
        workloads=tuple(workloads),
        failed_nodes=tuple(failed_nodes),
        link_factors=tuple(link_factors),
        recovery_start=recovery_start,
    )


SCENARIO_FAMILIES = (
    "normal_diurnal",
    "regional_burst",
    "node_failure_burst",
    "link_degradation",
    "recovery_migration",
)
SCENARIOS = tuple(
    make_scenario(family, 4100 + family_index * 17 + variant, feedback=variant == 0)
    for family_index, family in enumerate(SCENARIO_FAMILIES)
    for variant in range(2)
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_float(value: Any, field: str) -> float:
    if not _is_number(value):
        raise ActionValidationError("type", f"{field} must be a number, not {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ActionValidationError("non_finite", f"{field} must be finite")
    return result


class EdgeServiceSimulator:
    """Stateful placement and routing simulator with one-period replica cold starts."""

    def __init__(self, scenario: ScenarioTrace, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict(load_config() if config is None else config)
        self.scenario = scenario
        self.nodes = {item["id"]: dict(item) for item in self.config["nodes"]}
        self.services = {item["id"]: dict(item) for item in self.config["services"]}
        self.regions = tuple(self.config["regions"])
        self.step_index = 0
        self.active: dict[tuple[str, str], int] = {}
        self.pending: dict[tuple[str, str], int] = {}
        self.history: list[dict[str, dict[str, float]]] = []
        self.last_action: dict[str, Any] | None = None
        self.last_feedback: list[str] = []
        self.period_rows: list[dict[str, float]] = []
        self._recovered = scenario.recovery_start is None
        self._recovery_steps = 0
        self._bootstrap_replicas()

    def _bootstrap_replicas(self) -> None:
        for region in self.regions:
            region_nodes = [node_id for node_id, node in self.nodes.items() if node["region"] == region]
            for index, service_id in enumerate(self.services):
                self.active[(service_id, region_nodes[index % len(region_nodes)])] = 1

    @property
    def done(self) -> bool:
        return self.step_index >= len(self.scenario.workloads)

    def _alive_nodes(self) -> set[str]:
        failed = self.scenario.failed_nodes[self.step_index]
        return set(self.nodes) - set(failed)

    def _activate_pending_and_apply_failures(self) -> None:
        alive = self._alive_nodes()
        for key, count in list(self.pending.items()):
            if key[1] in alive and count > 0:
                self.active[key] = self.active.get(key, 0) + count
        self.pending.clear()
        self.active = {key: count for key, count in self.active.items() if key[1] in alive and count > 0}

    def observation(self) -> dict[str, Any]:
        if self.done:
            raise RuntimeError("scenario has finished")
        alive = self._alive_nodes()
        bandwidth = {}
        default_limit = float(self.config["cross_region_bandwidth_mb_per_period"])
        factors = self.scenario.link_factors[self.step_index]
        for source in self.regions:
            for target in self.regions:
                if source != target:
                    bandwidth[_pair(source, target)] = default_limit * factors.get(_pair(source, target), 1.0)
        return {
            "timestep": self.step_index,
            "period_minutes": self.config["period_minutes"],
            "nodes": [
                {
                    **node,
                    "alive": node_id in alive,
                }
                for node_id, node in self.nodes.items()
            ],
            "services": list(self.services.values()),
            "workload_rps": self.scenario.workloads[self.step_index],
            "workload_history": self.history[-4:],
            "active_replicas": [
                {"service_id": service, "node_id": node, "count": count}
                for (service, node), count in sorted(self.active.items())
            ],
            "pending_replicas": [
                {"service_id": service, "node_id": node, "count": count, "ready_in_steps": 1}
                for (service, node), count in sorted(self.pending.items())
            ],
            "network_rtt_ms": self.config["network_rtt_ms"],
            "cross_region_bandwidth_mb_per_period": bandwidth,
            "last_action": self.last_action,
            "last_feedback": self.last_feedback,
        }

    def _validate_action(self, action: Any) -> tuple[dict[tuple[str, str], int], list[dict[str, Any]]]:
        if not isinstance(action, dict):
            raise ActionValidationError("schema", "action must be a JSON object")
        if set(action) != {"replicas", "routes"}:
            raise ActionValidationError("schema", "action must contain exactly replicas and routes")
        replicas = action["replicas"]
        routes = action["routes"]
        if not isinstance(replicas, list) or not isinstance(routes, list):
            raise ActionValidationError("type", "replicas and routes must be lists")
        if len(replicas) + len(routes) > MAX_ACTION_ITEMS:
            raise ActionValidationError("size", f"action exceeds {MAX_ACTION_ITEMS} items")

        alive = self._alive_nodes()
        desired: dict[tuple[str, str], int] = {}
        cpu_by_node = {node_id: 0.0 for node_id in self.nodes}
        for index, item in enumerate(replicas):
            if not isinstance(item, dict) or set(item) != {"service_id", "node_id", "count"}:
                raise ActionValidationError("schema", f"replicas[{index}] has invalid fields")
            service_id = item["service_id"]
            node_id = item["node_id"]
            count = item["count"]
            if service_id not in self.services or node_id not in self.nodes:
                raise ActionValidationError("unknown_id", f"unknown placement {service_id!r}/{node_id!r}")
            if node_id not in alive:
                raise ActionValidationError("failed_node", f"cannot place replicas on failed node {node_id}")
            if isinstance(count, bool) or not isinstance(count, int):
                raise ActionValidationError("type", f"replica count for {service_id}/{node_id} must be an integer")
            if count < 0:
                raise ActionValidationError("range", "replica count must be non-negative")
            key = (service_id, node_id)
            if key in desired:
                raise ActionValidationError("duplicate", f"duplicate placement {service_id}/{node_id}")
            desired[key] = count
            cpu_by_node[node_id] += count * float(self.services[service_id]["cpu_per_replica"])
        for node_id, used in cpu_by_node.items():
            if used > float(self.nodes[node_id]["cpu_capacity"]) + 1e-9:
                raise ActionValidationError("capacity", f"placement uses {used:g} CPU on {node_id}")

        cleaned_routes: list[dict[str, Any]] = []
        seen_routes: set[tuple[str, str, str]] = set()
        route_sums: dict[tuple[str, str], float] = {}
        for index, item in enumerate(routes):
            required = {"service_id", "source_region", "node_id", "fraction"}
            if not isinstance(item, dict) or set(item) != required:
                raise ActionValidationError("schema", f"routes[{index}] has invalid fields")
            service_id = item["service_id"]
            source = item["source_region"]
            node_id = item["node_id"]
            if service_id not in self.services or source not in self.regions or node_id not in self.nodes:
                raise ActionValidationError("unknown_id", f"unknown route {service_id!r}/{source!r}/{node_id!r}")
            fraction = _finite_float(item["fraction"], f"routes[{index}].fraction")
            if fraction < 0.0 or fraction > 1.0:
                raise ActionValidationError("range", "route fraction must be in [0, 1]")
            key = (service_id, source, node_id)
            if key in seen_routes:
                raise ActionValidationError("duplicate", f"duplicate route {key}")
            seen_routes.add(key)
            placement_key = (service_id, node_id)
            if node_id not in alive:
                raise ActionValidationError("failed_node", f"cannot route to failed node {node_id}")
            if self.active.get(placement_key, 0) <= 0:
                raise ActionValidationError("inactive_route", f"route targets no active replica at {service_id}/{node_id}")
            if desired.get(placement_key, 0) <= 0:
                raise ActionValidationError("inactive_route", f"route targets placement removed by this action: {service_id}/{node_id}")
            route_key = (service_id, source)
            route_sums[route_key] = route_sums.get(route_key, 0.0) + fraction
            if route_sums[route_key] > 1.0 + ROUTE_TOLERANCE:
                raise ActionValidationError("route_sum", f"route fractions exceed 1 for {service_id}/{source}")
            cleaned_routes.append({**item, "fraction": fraction})
        return desired, cleaned_routes

    def _apply_desired(self, desired: Mapping[tuple[str, str], int]) -> None:
        keys = set(self.active) | set(self.pending) | set(desired)
        for key in keys:
            target = int(desired.get(key, 0))
            active = self.active.get(key, 0)
            pending = self.pending.get(key, 0)
            total = active + pending
            if target > total:
                self.pending[key] = pending + target - total
            elif target < total:
                remove = total - target
                pending_removed = min(pending, remove)
                pending -= pending_removed
                remove -= pending_removed
                active = max(0, active - remove)
                if pending:
                    self.pending[key] = pending
                else:
                    self.pending.pop(key, None)
                if active:
                    self.active[key] = active
                else:
                    self.active.pop(key, None)

    def _simulate_period(self, routes: list[dict[str, Any]]) -> dict[str, float]:
        workload = self.scenario.workloads[self.step_index]
        period_seconds = float(self.config["period_minutes"]) * 60.0
        total_demand = sum(sum(values.values()) for values in workload.values())
        route_rows: list[dict[str, Any]] = []
        routed = 0.0
        for route in routes:
            service_id = route["service_id"]
            source = route["source_region"]
            node_id = route["node_id"]
            demand = float(workload[source][service_id])
            requested = demand * route["fraction"]
            routed += requested
            route_rows.append({**route, "requested": requested, "after_link": requested})

        default_limit = float(self.config["cross_region_bandwidth_mb_per_period"])
        factors = self.scenario.link_factors[self.step_index]
        by_link: dict[str, list[dict[str, Any]]] = {}
        for row in route_rows:
            target = self.nodes[row["node_id"]]["region"]
            if row["source_region"] != target:
                by_link.setdefault(_pair(row["source_region"], target), []).append(row)
        for link, rows in by_link.items():
            requested_mb = sum(
                row["requested"]
                * float(self.services[row["service_id"]]["response_mb"])
                * period_seconds
                for row in rows
            )
            limit = default_limit * factors.get(link, 1.0)
            scale = min(1.0, limit / requested_mb) if requested_mb > 0 else 1.0
            for row in rows:
                row["after_link"] *= scale

        by_target: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in route_rows:
            by_target.setdefault((row["service_id"], row["node_id"]), []).append(row)
        for (service_id, node_id), rows in by_target.items():
            capacity = self.active.get((service_id, node_id), 0) * float(self.services[service_id]["service_rate_rps"])
            incoming = sum(row["after_link"] for row in rows)
            scale = min(1.0, capacity / incoming) if incoming > 0 else 1.0
            utilization = min(1.25, incoming / capacity) if capacity > 0 else 1.25
            for row in rows:
                row["served"] = row["after_link"] * scale
                row["utilization"] = utilization

        served = sum(float(row.get("served", 0.0)) for row in route_rows)
        weighted_p95 = 0.0
        weighted_p99 = 0.0
        slo_violations = max(0.0, total_demand - served)
        cross_region_mb = 0.0
        for row in route_rows:
            amount = float(row.get("served", 0.0))
            service = self.services[row["service_id"]]
            target_region = self.nodes[row["node_id"]]["region"]
            rtt = float(self.config["network_rtt_ms"][row["source_region"]][target_region])
            utilization = min(0.995, float(row.get("utilization", 1.25)))
            queue_pressure = utilization * utilization / max(0.08, 1.0 - utilization)
            p95 = rtt + float(service["base_latency_ms"]) * (1.0 + 0.85 * queue_pressure)
            p99 = rtt + float(service["base_latency_ms"]) * (1.0 + 1.35 * queue_pressure)
            weighted_p95 += amount * p95
            weighted_p99 += amount * p99
            if p99 > float(service["p99_slo_ms"]):
                slo_violations += amount
            if row["source_region"] != target_region:
                cross_region_mb += amount * float(service["response_mb"]) * period_seconds

        compute_cost = float(self.config["compute_cost_per_replica_period"]) * sum(self.active.values())
        compute_cost += (
            float(self.config["compute_cost_per_replica_period"])
            * float(self.config["pending_replica_cost_factor"])
            * sum(self.pending.values())
        )
        availability = served / total_demand if total_demand else 1.0
        if self.scenario.recovery_start is not None and self.step_index >= self.scenario.recovery_start and not self._recovered:
            if availability >= 0.99:
                self._recovered = True
            else:
                self._recovery_steps += 1
        return {
            "demand": total_demand,
            "served": served,
            "slo_violations": min(total_demand, slo_violations),
            "p95_weighted": weighted_p95,
            "p99_weighted": weighted_p99,
            "compute_cost": compute_cost,
            "cross_region_mb": cross_region_mb,
            "cross_region_cost": cross_region_mb / 1024.0 * float(self.config["cross_region_cost_per_gb"]),
        }

    def step(self, action: Any) -> dict[str, float]:
        if self.done:
            raise RuntimeError("scenario has finished")
        desired, routes = self._validate_action(action)
        self._apply_desired(desired)
        row = self._simulate_period(routes)
        self.period_rows.append(row)
        self.last_action = action
        feedback = []
        if row["served"] < 0.99 * row["demand"]:
            feedback.append("availability_below_0.99")
        if row["slo_violations"] > 0.05 * row["demand"]:
            feedback.append("slo_violation_rate_above_0.05")
        self.last_feedback = feedback
        self.history.append(self.scenario.workloads[self.step_index])
        self.step_index += 1
        if not self.done:
            self._activate_pending_and_apply_failures()
        return row

    def metrics(self) -> dict[str, float | str]:
        if not self.done:
            raise RuntimeError("scenario is not complete")
        total_demand = sum(row["demand"] for row in self.period_rows)
        served = sum(row["served"] for row in self.period_rows)
        violations = sum(row["slo_violations"] for row in self.period_rows)
        return {
            "scenario_family": self.scenario.family,
            "request_availability": served / total_demand if total_demand else 1.0,
            "unserved_rate": 1.0 - served / total_demand if total_demand else 0.0,
            "request_weighted_p95_ms": sum(row["p95_weighted"] for row in self.period_rows) / max(served, 1e-12),
            "request_weighted_p99_ms": sum(row["p99_weighted"] for row in self.period_rows) / max(served, 1e-12),
            "p99_slo_violation_rate": violations / total_demand if total_demand else 0.0,
            "compute_cost": sum(row["compute_cost"] for row in self.period_rows),
            "cross_region_gb": sum(row["cross_region_mb"] for row in self.period_rows) / 1024.0,
            "cross_region_cost": sum(row["cross_region_cost"] for row in self.period_rows),
            "failure_recovery_steps": float(self._recovery_steps),
        }


def run_policy(policy: Any, scenario: ScenarioTrace) -> dict[str, float | str]:
    reset = getattr(policy, "reset_policy", None)
    if reset is not None:
        reset()
    simulator = EdgeServiceSimulator(scenario)
    simulator._activate_pending_and_apply_failures()
    while not simulator.done:
        action = policy.decide(simulator.observation())
        simulator.step(action)
    return simulator.metrics()
