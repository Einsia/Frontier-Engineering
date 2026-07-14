from __future__ import annotations

import json
import sys
from typing import Any


# EVOLVE-BLOCK-START
def solve(instance):
    from collections import deque
    robots = {robot['id']: robot for robot in instance['robots']}
    orders = {order['id']: order for order in instance['orders']}
    robot_ids = sorted(robots)
    adjacency = {node: [] for node in instance['graph']['nodes']}
    for left, right in instance['graph']['edges']:
        adjacency[left].append(right)
        adjacency[right].append(left)
    for node in adjacency:
        adjacency[node] = sorted(set(adjacency[node]))
    distances = {}
    for source in sorted(adjacency):
        seen = {source: 0}
        queue = deque([source])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen[neighbor] = seen[current] + 1
                    queue.append(neighbor)
        distances[source] = seen

    def sequence_cost(robot_id, sequence):
        if not sequence:
            return 0
        start = robots[robot_id]['start_node']
        current = start
        total = 0
        for order_id in sequence:
            order = orders[order_id]
            pickup = order['pickup_node']
            dropoff = order['dropoff_node']
            if pickup not in distances[current] or dropoff not in distances[pickup]:
                return float('inf')
            total += distances[current][pickup]
            total += distances[pickup][dropoff]
            current = dropoff
        if start not in distances[current]:
            return float('inf')
        return total + distances[current][start]
    sequences = {robot_id: [] for robot_id in robot_ids}
    for order_id in sorted(orders):
        order = orders[order_id]
        best_key = None
        best_choice = None
        for rank, robot_id in enumerate(robot_ids):
            if order['weight'] > robots[robot_id]['capacity']:
                continue
            old_cost = sequence_cost(robot_id, sequences[robot_id])
            for position in range(len(sequences[robot_id]) + 1):
                candidate = list(sequences[robot_id])
                candidate.insert(position, order_id)
                new_cost = sequence_cost(robot_id, candidate)
                key = (new_cost - old_cost, new_cost, rank, position, robot_id)
                if new_cost != float('inf') and (best_key is None or key < best_key):
                    best_key = key
                    best_choice = (robot_id, position)
        if best_choice is None:
            raise ValueError('No capacity-feasible robot can serve every order')
        chosen_robot, chosen_position = best_choice
        sequences[chosen_robot].insert(chosen_position, order_id)

    def shortest_path(source, target, forbidden):
        if source == target:
            return [source]
        parent = {source: None}
        queue = deque([source])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor in parent:
                    continue
                if neighbor in forbidden and neighbor != target:
                    continue
                parent[neighbor] = current
                if neighbor == target:
                    path = [target]
                    while path[-1] != source:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                queue.append(neighbor)
        raise ValueError('A required service node is unreachable')
    starts = {robot['start_node'] for robot in robots.values()}
    paths = {robot_id: [robots[robot_id]['start_node']] for robot_id in robot_ids}
    actions = {robot_id: [] for robot_id in robot_ids}
    cursor = 0
    for robot_id in robot_ids:
        path = paths[robot_id]
        while len(path) - 1 < cursor:
            path.append(path[-1])
        forbidden = starts - {robots[robot_id]['start_node']}
        last_action_time = None
        for order_id in sequences[robot_id]:
            order = orders[order_id]
            segment = shortest_path(path[-1], order['pickup_node'], forbidden)
            path.extend(segment[1:])
            if last_action_time is not None and len(path) - 1 == last_action_time:
                path.append(path[-1])
            pickup_time = len(path) - 1
            actions[robot_id].append({'time': pickup_time, 'type': 'pickup', 'order_id': order_id})
            last_action_time = pickup_time
            segment = shortest_path(path[-1], order['dropoff_node'], forbidden)
            path.extend(segment[1:])
            if len(path) - 1 == last_action_time:
                path.append(path[-1])
            dropoff_time = len(path) - 1
            actions[robot_id].append({'time': dropoff_time, 'type': 'dropoff', 'order_id': order_id})
            last_action_time = dropoff_time
        if sequences[robot_id]:
            segment = shortest_path(path[-1], robots[robot_id]['start_node'], forbidden)
            path.extend(segment[1:])
        cursor = len(path) - 1
    horizon = instance['horizon']
    if cursor > horizon:
        raise ValueError('The baseline route exceeds the instance horizon')
    output = []
    for robot_id in robot_ids:
        path = paths[robot_id]
        path.extend([path[-1]] * (horizon + 1 - len(path)))
        output.append({'robot_id': robot_id, 'path': path, 'actions': actions[robot_id]})
    return {'robots': output}
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
