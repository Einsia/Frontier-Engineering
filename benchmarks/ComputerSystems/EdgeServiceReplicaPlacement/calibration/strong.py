"""Stronger hidden calibration policy using history-aware demand estimates."""

from __future__ import annotations

import math
from typing import Any


def reset_policy() -> None:
    return None


def decide(observation: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    nodes = {node["id"]: node for node in observation["nodes"]}
    services = {service["id"]: service for service in observation["services"]}
    alive = [node_id for node_id, node in nodes.items() if node["alive"]]
    active_now = {
        (item["service_id"], item["node_id"]): int(item["count"])
        for item in observation["active_replicas"]
    }
    cpu_used = {node_id: 0.0 for node_id in alive}
    placement: dict[tuple[str, str], int] = {}
    history = observation["workload_history"]

    for service_id in sorted(services, key=lambda sid: services[sid]["reliability_class"] != "critical"):
        service = services[service_id]
        cpu = float(service["cpu_per_replica"])
        rate = float(service["service_rate_rps"])
        for source, current_by_service in observation["workload_rps"].items():
            current = float(current_by_service[service_id])
            recent = [float(period[source][service_id]) for period in history[-3:]]
            trend = max(0.0, current - recent[-1]) if recent else 0.0
            forecast = max([current, *recent], default=current) + 1.5 * trend
            headroom = 1.35 if service["reliability_class"] == "critical" else 1.22
            needed = max(1, math.ceil(headroom * forecast / rate))
            local_domains: set[str] = set()
            candidates = sorted(
                alive,
                key=lambda node_id: (
                    nodes[node_id]["region"] != source,
                    observation["network_rtt_ms"][source][nodes[node_id]["region"]],
                    cpu_used[node_id],
                    node_id,
                ),
            )
            for _ in range(needed):
                feasible = [node_id for node_id in candidates if cpu_used[node_id] + cpu <= float(nodes[node_id]["cpu_capacity"])]
                if not feasible:
                    break
                node_id = min(
                    feasible,
                    key=lambda candidate: (
                        nodes[candidate]["region"] != source,
                        observation["network_rtt_ms"][source][nodes[candidate]["region"]],
                        active_now.get((service_id, candidate), 0) <= 0,
                        nodes[candidate]["failure_domain"] in local_domains,
                        placement.get((service_id, candidate), 0),
                        cpu_used[candidate],
                        candidate,
                    ),
                )
                placement[(service_id, node_id)] = placement.get((service_id, node_id), 0) + 1
                cpu_used[node_id] += cpu
                local_domains.add(nodes[node_id]["failure_domain"])

    replicas = [
        {"service_id": service_id, "node_id": node_id, "count": count}
        for (service_id, node_id), count in sorted(placement.items())
    ]
    active = active_now
    routes: list[dict[str, Any]] = []
    remaining_capacity = {
        (service_id, node_id): active.get((service_id, node_id), 0)
        * float(services[service_id]["service_rate_rps"])
        for service_id in services
        for node_id in alive
        if active.get((service_id, node_id), 0) > 0
        and placement.get((service_id, node_id), 0) > 0
    }
    unmet: list[tuple[str, str, float, float]] = []

    # First reserve each target's capacity for demand originating in its own region.
    for source, demand_by_service in observation["workload_rps"].items():
        for service_id, demand_value in demand_by_service.items():
            demand = max(float(demand_value), 1e-9)
            remaining_demand = demand
            local_targets = sorted(
                node_id
                for node_id in alive
                if nodes[node_id]["region"] == source
                and remaining_capacity.get((service_id, node_id), 0.0) > 0.0
            )
            for node_id in local_targets:
                amount = min(remaining_demand, remaining_capacity[(service_id, node_id)])
                if amount > 1e-12:
                    routes.append({"service_id": service_id, "source_region": source, "node_id": node_id, "fraction": amount / demand})
                    remaining_capacity[(service_id, node_id)] -= amount
                    remaining_demand -= amount
            if remaining_demand > 1e-12:
                unmet.append((source, service_id, demand, remaining_demand))

    # Then use only spare remote capacity, bounded by the observed link budget.
    link_remaining = dict(observation["cross_region_bandwidth_mb_per_period"])
    period_seconds = float(observation["period_minutes"]) * 60.0
    for source, service_id, demand, remaining_demand in unmet:
        response_mb = float(services[service_id]["response_mb"])
        remote_targets = sorted(
            (
                node_id
                for node_id in alive
                if nodes[node_id]["region"] != source
                and remaining_capacity.get((service_id, node_id), 0.0) > 0.0
            ),
            key=lambda node_id: (
                observation["network_rtt_ms"][source][nodes[node_id]["region"]],
                node_id,
            ),
        )
        for node_id in remote_targets:
            target_region = nodes[node_id]["region"]
            link = f"{source}->{target_region}"
            by_link = link_remaining.get(link, 0.0) / max(response_mb * period_seconds, 1e-12)
            amount = min(remaining_demand, remaining_capacity[(service_id, node_id)], by_link)
            if amount > 1e-12:
                routes.append({"service_id": service_id, "source_region": source, "node_id": node_id, "fraction": amount / demand})
                remaining_capacity[(service_id, node_id)] -= amount
                link_remaining[link] -= amount * response_mb * period_seconds
                remaining_demand -= amount
            if remaining_demand <= 1e-12:
                break
    return {"replicas": replicas, "routes": routes}
