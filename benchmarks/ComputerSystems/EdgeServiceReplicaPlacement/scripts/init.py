"""Reasonable CPU-only baseline for EdgeServiceReplicaPlacement."""

from __future__ import annotations

import math
from typing import Any


# EVOLVE-BLOCK-START
def reset_policy() -> None:
    """The baseline is stateless; the hook keeps scenario isolation explicit."""


def decide(observation: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Choose desired replicas and current-period routes from observable state only."""

    nodes = {node["id"]: node for node in observation["nodes"]}
    services = {service["id"]: service for service in observation["services"]}
    alive = [node_id for node_id, node in nodes.items() if node["alive"]]
    cpu_used = {node_id: 0.0 for node_id in alive}
    placement: dict[tuple[str, str], int] = {}

    # Critical services are allocated first. Each regional demand gets modest headroom;
    # capacity spillover is placed on the nearest surviving region.
    service_order = sorted(
        services,
        key=lambda service_id: services[service_id]["reliability_class"] != "critical",
    )
    for service_id in service_order:
        service = services[service_id]
        cpu = float(service["cpu_per_replica"])
        rate = float(service["service_rate_rps"])
        for source_region, demand_by_service in observation["workload_rps"].items():
            needed = max(1, math.ceil(1.20 * float(demand_by_service[service_id]) / rate))
            candidates = sorted(
                alive,
                key=lambda node_id: (
                    nodes[node_id]["region"] != source_region,
                    observation["network_rtt_ms"][source_region][nodes[node_id]["region"]],
                    cpu_used[node_id],
                    node_id,
                ),
            )
            for replica_index in range(needed):
                feasible = [
                    node_id
                    for node_id in candidates
                    if cpu_used[node_id] + cpu <= float(nodes[node_id]["cpu_capacity"])
                ]
                if not feasible:
                    break
                # Alternate failure domains when equivalent capacity is available.
                node_id = min(
                    feasible,
                    key=lambda candidate: (
                        nodes[candidate]["region"] != source_region,
                        observation["network_rtt_ms"][source_region][nodes[candidate]["region"]],
                        placement.get((service_id, candidate), 0),
                        cpu_used[candidate],
                        candidate,
                    ),
                )
                placement[(service_id, node_id)] = placement.get((service_id, node_id), 0) + 1
                cpu_used[node_id] += cpu

    replicas = [
        {"service_id": service_id, "node_id": node_id, "count": count}
        for (service_id, node_id), count in sorted(placement.items())
        if count > 0
    ]
    active = {
        (item["service_id"], item["node_id"]): int(item["count"])
        for item in observation["active_replicas"]
    }
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
    for source_region, demand_by_service in observation["workload_rps"].items():
        for service_id, demand_value in demand_by_service.items():
            demand = max(float(demand_value), 1e-9)
            remaining_demand = demand
            targets = sorted(
                node_id
                for node_id in alive
                if nodes[node_id]["region"] == source_region
                and remaining_capacity.get((service_id, node_id), 0.0) > 0.0
            )
            for node_id in targets:
                amount = min(remaining_demand, remaining_capacity[(service_id, node_id)])
                if amount > 1e-12:
                    routes.append(
                        {
                            "service_id": service_id,
                            "source_region": source_region,
                            "node_id": node_id,
                            "fraction": amount / demand,
                        }
                    )
                    remaining_capacity[(service_id, node_id)] -= amount
                    remaining_demand -= amount
                if remaining_demand <= 1e-12:
                    break
            if remaining_demand > 1e-12:
                unmet.append((source_region, service_id, demand, remaining_demand))

    link_remaining = dict(observation["cross_region_bandwidth_mb_per_period"])
    period_seconds = float(observation["period_minutes"]) * 60.0
    for source_region, service_id, demand, remaining_demand in unmet:
        response_mb = float(services[service_id]["response_mb"])
        targets = sorted(
            (
                node_id
                for node_id in alive
                if nodes[node_id]["region"] != source_region
                and remaining_capacity.get((service_id, node_id), 0.0) > 0.0
            ),
            key=lambda node_id: (
                observation["network_rtt_ms"][source_region][nodes[node_id]["region"]],
                node_id,
            ),
        )
        for node_id in targets:
            target_region = nodes[node_id]["region"]
            link = f"{source_region}->{target_region}"
            by_link = link_remaining.get(link, 0.0) / max(response_mb * period_seconds, 1e-12)
            amount = min(remaining_demand, remaining_capacity[(service_id, node_id)], by_link)
            if amount > 1e-12:
                routes.append(
                    {
                        "service_id": service_id,
                        "source_region": source_region,
                        "node_id": node_id,
                        "fraction": amount / demand,
                    }
                )
                remaining_capacity[(service_id, node_id)] -= amount
                link_remaining[link] -= amount * response_mb * period_seconds
                remaining_demand -= amount
            if remaining_demand <= 1e-12:
                break
    return {"replicas": replicas, "routes": routes}
# EVOLVE-BLOCK-END
