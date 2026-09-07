"""Weak static calibration policy; never exposed as an agent-editable file."""

from __future__ import annotations

from typing import Any


def reset_policy() -> None:
    return None


def decide(observation: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    nodes = {node["id"]: node for node in observation["nodes"]}
    alive = {node_id for node_id, node in nodes.items() if node["alive"]}
    services = {service["id"]: service for service in observation["services"]}
    regions = list(observation["workload_rps"])
    placement: dict[tuple[str, str], int] = {}
    for region in regions:
        local = sorted(node_id for node_id in alive if nodes[node_id]["region"] == region)
        for index, service_id in enumerate(services):
            if local:
                placement[(service_id, local[index % len(local)])] = 1
    replicas = [
        {"service_id": service_id, "node_id": node_id, "count": count}
        for (service_id, node_id), count in sorted(placement.items())
    ]
    active = {
        (item["service_id"], item["node_id"]): int(item["count"])
        for item in observation["active_replicas"]
    }
    routes: list[dict[str, Any]] = []
    for source in regions:
        for service_id in services:
            targets = [
                node_id
                for node_id in alive
                if nodes[node_id]["region"] == source
                and active.get((service_id, node_id), 0) > 0
                and placement.get((service_id, node_id), 0) > 0
            ]
            if targets:
                routes.append(
                    {
                        "service_id": service_id,
                        "source_region": source,
                        "node_id": targets[0],
                        "fraction": 1.0,
                    }
                )
    return {"replicas": replicas, "routes": routes}
