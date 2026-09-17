from collections import deque
import math
import random


RAW_METRIC = 'verified_total_move_distance_plus_one'
INVALID_SCORE = -1e18


def _adjacency(instance):
    adjacency = {node: [] for node in instance['graph']['nodes']}
    for left, right in instance['graph']['edges']:
        adjacency[left].append(right)
        adjacency[right].append(left)
    for node in adjacency:
        adjacency[node] = tuple(sorted(set(adjacency[node])))
    return adjacency


def _all_distances(adjacency):
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
    return distances


def _shortest_path(adjacency, source, target, forbidden):
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


def _sequence_cost(sequence, robot_id, robots, orders, distances, close_route=True):
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
    if close_route:
        if start not in distances[current]:
            return float('inf')
        total += distances[current][start]
    return total


def _greedy_sequences(instance, order_ids, robot_priority):
    robots = {robot['id']: robot for robot in instance['robots']}
    orders = {order['id']: order for order in instance['orders']}
    adjacency = _adjacency(instance)
    distances = _all_distances(adjacency)
    sequences = {robot_id: [] for robot_id in sorted(robots)}

    for order_id in order_ids:
        order = orders[order_id]
        best_key = None
        best_choice = None
        for rank, robot_id in enumerate(robot_priority):
            if order['weight'] > robots[robot_id]['capacity']:
                continue
            old_cost = _sequence_cost(
                sequences[robot_id], robot_id, robots, orders, distances, True
            )
            for position in range(len(sequences[robot_id]) + 1):
                candidate = list(sequences[robot_id])
                candidate.insert(position, order_id)
                new_cost = _sequence_cost(
                    candidate, robot_id, robots, orders, distances, True
                )
                key = (new_cost - old_cost, new_cost, rank, position, robot_id)
                if new_cost != float('inf') and (best_key is None or key < best_key):
                    best_key = key
                    best_choice = (robot_id, position)
        if best_choice is None:
            raise ValueError('No capacity-feasible robot can serve order ' + order_id)
        chosen_robot, chosen_position = best_choice
        sequences[chosen_robot].insert(chosen_position, order_id)
    return sequences


def _build_serial_solution(instance, sequences, schedule_order, open_robot=None):
    robots = {robot['id']: robot for robot in instance['robots']}
    orders = {order['id']: order for order in instance['orders']}
    robot_ids = sorted(robots)
    if sorted(schedule_order) != robot_ids:
        raise ValueError('The schedule must contain every robot exactly once')

    adjacency = _adjacency(instance)
    starts = {robot['start_node'] for robot in robots.values()}
    paths = {robot_id: [robots[robot_id]['start_node']] for robot_id in robot_ids}
    actions = {robot_id: [] for robot_id in robot_ids}
    cursor = 0

    for robot_id in schedule_order:
        path = paths[robot_id]
        while len(path) - 1 < cursor:
            path.append(path[-1])
        forbidden = starts - {robots[robot_id]['start_node']}
        last_action_time = None

        for order_id in sequences[robot_id]:
            order = orders[order_id]
            segment = _shortest_path(
                adjacency, path[-1], order['pickup_node'], forbidden
            )
            path.extend(segment[1:])
            if last_action_time is not None and len(path) - 1 == last_action_time:
                path.append(path[-1])
            pickup_time = len(path) - 1
            actions[robot_id].append(
                {'time': pickup_time, 'type': 'pickup', 'order_id': order_id}
            )
            last_action_time = pickup_time

            segment = _shortest_path(
                adjacency, path[-1], order['dropoff_node'], forbidden
            )
            path.extend(segment[1:])
            if len(path) - 1 == last_action_time:
                path.append(path[-1])
            dropoff_time = len(path) - 1
            actions[robot_id].append(
                {'time': dropoff_time, 'type': 'dropoff', 'order_id': order_id}
            )
            last_action_time = dropoff_time

        if sequences[robot_id] and robot_id != open_robot:
            segment = _shortest_path(
                adjacency, path[-1], robots[robot_id]['start_node'], forbidden
            )
            path.extend(segment[1:])
        cursor = len(path) - 1

    horizon = instance['horizon']
    if cursor > horizon:
        raise ValueError('Constructed route exceeds the instance horizon')

    result = []
    for robot_id in robot_ids:
        path = paths[robot_id]
        path.extend([path[-1]] * (horizon + 1 - len(path)))
        result.append(
            {'robot_id': robot_id, 'path': path, 'actions': actions[robot_id]}
        )
    return {'robots': result}


def _stable_seed(seed, text):
    value = int(seed) & ((1 << 64) - 1)
    for byte in text.encode('utf-8'):
        value ^= byte
        value = (value * 1099511628211) & ((1 << 64) - 1)
    return value


def _route_table(instance, robot_id, close_route):
    robots = {robot['id']: robot for robot in instance['robots']}
    order_list = sorted(instance['orders'], key=lambda order: order['id'])
    adjacency = _adjacency(instance)
    distances = _all_distances(adjacency)
    robot = robots[robot_id]
    count = len(order_list)
    full = 1 << count
    dynamic = [dict() for _ in range(full)]

    for index, order in enumerate(order_list):
        if order['weight'] > robot['capacity']:
            continue
        start = robot['start_node']
        pickup = order['pickup_node']
        dropoff = order['dropoff_node']
        if pickup not in distances[start] or dropoff not in distances[pickup]:
            continue
        cost = distances[start][pickup] + distances[pickup][dropoff]
        dynamic[1 << index][index] = (cost, (order['id'],))

    for mask in range(1, full):
        for last, state in list(dynamic[mask].items()):
            cost, sequence = state
            last_dropoff = order_list[last]['dropoff_node']
            for next_index, order in enumerate(order_list):
                bit = 1 << next_index
                if mask & bit or order['weight'] > robot['capacity']:
                    continue
                pickup = order['pickup_node']
                dropoff = order['dropoff_node']
                if pickup not in distances[last_dropoff] or dropoff not in distances[pickup]:
                    continue
                new_mask = mask | bit
                new_cost = (
                    cost
                    + distances[last_dropoff][pickup]
                    + distances[pickup][dropoff]
                )
                candidate = (new_cost, sequence + (order['id'],))
                previous = dynamic[new_mask].get(next_index)
                if previous is None or candidate < previous:
                    dynamic[new_mask][next_index] = candidate

    options = {0: (0, ())}
    for mask in range(1, full):
        best = None
        for last, state in dynamic[mask].items():
            cost, sequence = state
            if close_route:
                dropoff = order_list[last]['dropoff_node']
                start = robot['start_node']
                if start not in distances[dropoff]:
                    continue
                cost += distances[dropoff][start]
            candidate = (cost, sequence)
            if best is None or candidate < best:
                best = candidate
        if best is not None:
            options[mask] = best
    return options


def _exact_reference_sequences(instance):
    robot_ids = sorted(robot['id'] for robot in instance['robots'])
    order_ids = sorted(order['id'] for order in instance['orders'])
    count = len(order_ids)
    full_mask = (1 << count) - 1
    closed_tables = {
        robot_id: _route_table(instance, robot_id, True) for robot_id in robot_ids
    }
    open_tables = {
        robot_id: _route_table(instance, robot_id, False) for robot_id in robot_ids
    }

    best_key = None
    best_payload = None
    for last_robot in robot_ids:
        states = {0: (0, ())}
        for robot_id in robot_ids:
            table = open_tables[robot_id] if robot_id == last_robot else closed_tables[robot_id]
            next_states = {}
            for covered, state in states.items():
                accumulated_cost, subsets = state
                remaining = full_mask ^ covered
                subset = remaining
                while True:
                    if not (robot_id == last_robot and subset == 0) and subset in table:
                        route_cost = table[subset][0]
                        new_covered = covered | subset
                        candidate = (
                            accumulated_cost + route_cost,
                            subsets + (subset,),
                        )
                        previous = next_states.get(new_covered)
                        if previous is None or candidate < previous:
                            next_states[new_covered] = candidate
                    if subset == 0:
                        break
                    subset = (subset - 1) & remaining
            states = next_states

        if full_mask in states:
            cost, subsets = states[full_mask]
            key = (cost, last_robot, subsets)
            if best_key is None or key < best_key:
                best_key = key
                best_payload = (last_robot, subsets)

    if best_payload is None:
        raise ValueError('No capacity-feasible reference partition exists')

    last_robot, subsets = best_payload
    sequences = {}
    for index, robot_id in enumerate(robot_ids):
        table = open_tables[robot_id] if robot_id == last_robot else closed_tables[robot_id]
        sequences[robot_id] = list(table[subsets[index]][1])
    return sequences, last_robot


def solve_random(instance):
    seed = 0
    robot_ids = sorted(robot['id'] for robot in instance['robots'])
    order_ids = sorted(order['id'] for order in instance['orders'])
    rng = random.Random(_stable_seed(seed, instance['instance_id']))
    rng.shuffle(robot_ids)
    rng.shuffle(order_ids)
    sequences = _greedy_sequences(instance, order_ids, robot_ids)
    return _build_serial_solution(instance, sequences, robot_ids, None)


def solve_baseline(instance):
    robot_ids = sorted(robot['id'] for robot in instance['robots'])
    order_ids = sorted(order['id'] for order in instance['orders'])
    sequences = _greedy_sequences(instance, order_ids, robot_ids)
    return _build_serial_solution(instance, sequences, robot_ids, None)


def solve_reference(instance):
    robot_ids = sorted(robot['id'] for robot in instance['robots'])
    order_ids = sorted(order['id'] for order in instance['orders'])
    baseline_sequences = _greedy_sequences(instance, order_ids, robot_ids)
    candidates = []

    baseline = _build_serial_solution(instance, baseline_sequences, robot_ids, None)
    if validate_solution(instance, baseline)[0]:
        candidates.append(baseline)

    used_robots = [robot_id for robot_id in robot_ids if baseline_sequences[robot_id]]
    for last_robot in used_robots:
        schedule = [robot_id for robot_id in robot_ids if robot_id != last_robot]
        schedule.append(last_robot)
        candidate = _build_serial_solution(
            instance, baseline_sequences, schedule, last_robot
        )
        if validate_solution(instance, candidate)[0]:
            candidates.append(candidate)

    if len(order_ids) <= 10:
        try:
            exact_sequences, last_robot = _exact_reference_sequences(instance)
            schedule = [robot_id for robot_id in robot_ids if robot_id != last_robot]
            schedule.append(last_robot)
            candidate = _build_serial_solution(
                instance, exact_sequences, schedule, last_robot
            )
            if validate_solution(instance, candidate)[0]:
                candidates.append(candidate)
        except ValueError:
            pass

    if not candidates:
        return baseline
    return min(candidates, key=lambda solution: (_move_distance(solution), repr(solution)))


def validate_solution(instance, solution):
    if type(solution) is not dict or set(solution) != {'robots'}:
        return False, 'Solution must be an object containing only robots'
    submitted_robots = solution['robots']
    if type(submitted_robots) is not list:
        return False, 'robots must be an array'

    robot_map = {robot['id']: robot for robot in instance['robots']}
    order_map = {order['id']: order for order in instance['orders']}
    node_set = set(instance['graph']['nodes'])
    horizon = instance['horizon']
    expected_robot_ids = set(robot_map)
    entries = {}

    for index, entry in enumerate(submitted_robots):
        if type(entry) is not dict or set(entry) != {'robot_id', 'path', 'actions'}:
            return False, 'Each robot entry must contain only robot_id, path, and actions'
        robot_id = entry['robot_id']
        if type(robot_id) is not str or robot_id not in robot_map:
            return False, 'Unknown robot at output index ' + str(index)
        if robot_id in entries:
            return False, 'Duplicate robot ' + robot_id

        path = entry['path']
        if type(path) is not list or len(path) != horizon + 1:
            return False, 'Robot ' + robot_id + ' path must have horizon + 1 nodes'
        for time, node in enumerate(path):
            if type(node) is not str or node not in node_set:
                return False, 'Robot ' + robot_id + ' uses an unknown node at time ' + str(time)

        actions = entry['actions']
        if type(actions) is not list:
            return False, 'Robot ' + robot_id + ' actions must be an array'
        actions_by_time = {}
        for action_index, action in enumerate(actions):
            if type(action) is not dict or set(action) != {'time', 'type', 'order_id'}:
                return False, 'Malformed action for robot ' + robot_id
            time = action['time']
            action_type = action['type']
            order_id = action['order_id']
            if type(time) is not int or time < 0 or time > horizon:
                return False, 'Action time is outside the horizon for robot ' + robot_id
            if action_type not in ('pickup', 'dropoff'):
                return False, 'Unknown action type for robot ' + robot_id
            if type(order_id) is not str or order_id not in order_map:
                return False, 'Unknown order in action ' + str(action_index)
            if time in actions_by_time:
                return False, 'Robot ' + robot_id + ' performs multiple actions at one time'
            actions_by_time[time] = action
        entries[robot_id] = (path, actions_by_time)

    if set(entries) != expected_robot_ids:
        missing = sorted(expected_robot_ids - set(entries))
        return False, 'Missing robots: ' + ','.join(missing)

    directed_edges = set()
    for left, right in instance['graph']['edges']:
        directed_edges.add((left, right))
        directed_edges.add((right, left))

    robot_ids = sorted(robot_map)
    for robot_id in robot_ids:
        path = entries[robot_id][0]
        if path[0] != robot_map[robot_id]['start_node']:
            return False, 'Robot ' + robot_id + ' starts at the wrong node'
        for time in range(1, horizon + 1):
            if path[time] != path[time - 1] and (path[time - 1], path[time]) not in directed_edges:
                return False, 'Robot ' + robot_id + ' makes an illegal move at time ' + str(time)

    for time in range(horizon + 1):
        occupied = {}
        for robot_id in robot_ids:
            node = entries[robot_id][0][time]
            if node in occupied:
                return False, 'Vertex collision at time ' + str(time)
            occupied[node] = robot_id

    for time in range(1, horizon + 1):
        for left_index in range(len(robot_ids)):
            left_id = robot_ids[left_index]
            left_path = entries[left_id][0]
            for right_index in range(left_index + 1, len(robot_ids)):
                right_id = robot_ids[right_index]
                right_path = entries[right_id][0]
                if (
                    left_path[time - 1] == right_path[time]
                    and right_path[time - 1] == left_path[time]
                    and left_path[time - 1] != left_path[time]
                ):
                    return False, 'Opposite-direction edge collision at time ' + str(time)

    picked = {}
    dropped = {}
    for robot_id in robot_ids:
        path, actions_by_time = entries[robot_id]
        capacity = robot_map[robot_id]['capacity']
        carried = set()
        load = 0
        for time in range(horizon + 1):
            action = actions_by_time.get(time)
            if action is None:
                continue
            order_id = action['order_id']
            order = order_map[order_id]
            if action['type'] == 'pickup':
                if order_id in picked:
                    return False, 'Order ' + order_id + ' is picked up more than once'
                if path[time] != order['pickup_node']:
                    return False, 'Order ' + order_id + ' is picked up at the wrong node'
                load += order['weight']
                if load > capacity:
                    return False, 'Robot ' + robot_id + ' exceeds its capacity'
                carried.add(order_id)
                picked[order_id] = (robot_id, time)
            else:
                if order_id not in carried:
                    return False, 'Robot ' + robot_id + ' drops an order it is not carrying'
                if order_id in dropped:
                    return False, 'Order ' + order_id + ' is dropped more than once'
                if path[time] != order['dropoff_node']:
                    return False, 'Order ' + order_id + ' is dropped at the wrong node'
                pickup_robot, pickup_time = picked[order_id]
                if pickup_robot != robot_id or time <= pickup_time:
                    return False, 'Order ' + order_id + ' has an invalid pickup/dropoff order'
                carried.remove(order_id)
                load -= order['weight']
                if load < 0:
                    return False, 'Robot ' + robot_id + ' has a negative load'
                dropped[order_id] = (robot_id, time)
        if load != 0 or carried:
            return False, 'Robot ' + robot_id + ' finishes with undelivered cargo'

    expected_orders = set(order_map)
    if set(picked) != expected_orders:
        return False, 'Not every order is picked up exactly once'
    if set(dropped) != expected_orders:
        return False, 'Not every order is dropped off exactly once'
    return True, 'ok'


def _move_distance(solution):
    total = 0
    for entry in solution['robots']:
        path = entry['path']
        total += sum(path[index] != path[index - 1] for index in range(1, len(path)))
    return total


def _completion_time(solution):
    times = [
        action['time']
        for entry in solution['robots']
        for action in entry['actions']
        if action['type'] == 'dropoff'
    ]
    return max(times) if times else 0


def evaluate_solution(instance, solution):
    valid, message = validate_solution(instance, solution)
    if not valid:
        raise ValueError(message)
    return _move_distance(solution) + 1


def _make_instance(seed, index):
    mixed_seed = _stable_seed(seed, 'warehouse-routing-' + str(index))
    rng = random.Random(mixed_seed)
    width = 5 + rng.randrange(3)
    height = 5 + rng.randrange(3)
    robot_count = 2 + ((index + rng.randrange(3)) % 3)
    order_count = 5 + index

    def grid_node(x, y):
        return 'n' + str(x) + '_' + str(y)

    grid_nodes = [grid_node(x, y) for x in range(width) for y in range(height)]
    edge_set = set()

    def add_edge(left, right):
        if left != right:
            edge_set.add(tuple(sorted((left, right))))

    for x in range(width):
        for y in range(height - 1):
            add_edge(grid_node(x, y), grid_node(x, y + 1))

    cross_rows = {0, height // 2, height - 1}
    for y in sorted(cross_rows):
        for x in range(width - 1):
            add_edge(grid_node(x, y), grid_node(x + 1, y))

    anchor_candidates = [
        grid_node(0, 0),
        grid_node(width - 1, 0),
        grid_node(0, height - 1),
        grid_node(width - 1, height - 1),
        grid_node(width // 2, 0),
    ]
    anchors = anchor_candidates[:robot_count]
    parking_nodes = ['park_' + str(index) + '_' + str(i) for i in range(robot_count)]
    for parking, anchor in zip(parking_nodes, anchors):
        add_edge(parking, anchor)

    capacities = [4 + rng.randrange(4) for _ in range(robot_count)]
    robots = [
        {
            'id': 'r' + str(i).zfill(2),
            'start_node': parking_nodes[i],
            'capacity': capacities[i],
        }
        for i in range(robot_count)
    ]

    service_nodes = [node for node in grid_nodes if node not in set(anchors)]
    orders = []
    maximum_weight = min(capacities)
    for order_index in range(order_count):
        pickup = service_nodes[rng.randrange(len(service_nodes))]
        dropoff = service_nodes[rng.randrange(len(service_nodes))]
        while dropoff == pickup:
            dropoff = service_nodes[rng.randrange(len(service_nodes))]
        orders.append(
            {
                'id': 'o' + str(order_index).zfill(2),
                'pickup_node': pickup,
                'dropoff_node': dropoff,
                'weight': 1 + rng.randrange(maximum_weight),
            }
        )

    nodes = sorted(grid_nodes + parking_nodes)
    edges = [list(edge) for edge in sorted(edge_set)]
    node_count = len(nodes)
    horizon = (
        (2 * order_count + robot_count + 1) * (node_count - 1)
        + 2 * order_count
        + 10
    )
    return {
        'instance_id': 'warehouse-routing-' + str(seed) + '-' + str(index),
        'graph': {'nodes': nodes, 'edges': edges},
        'robots': robots,
        'orders': orders,
        'horizon': horizon,
    }


def generate_instances(seed):
    if type(seed) is not int:
        raise TypeError('seed must be an integer')
    instances = []
    for index in range(2):
        instance = _make_instance(seed, index)
        instances.append(instance)
    return instances
