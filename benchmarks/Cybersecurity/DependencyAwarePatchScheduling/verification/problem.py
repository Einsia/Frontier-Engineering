_SCALE = 1000000
_MASK64 = (1 << 64) - 1


class _DeterministicRng:
    def __init__(self, seed):
        self.state = (int(seed) ^ 0x9E3779B97F4A7C15) & _MASK64
        if self.state == 0:
            self.state = 0xD1B54A32D192ED03

    def next_u64(self):
        value = self.state
        value ^= value >> 12
        value ^= (value << 25) & _MASK64
        value ^= value >> 27
        self.state = value & _MASK64
        return (self.state * 2685821657736338717) & _MASK64

    def randbelow(self, bound):
        return self.next_u64() % bound

    def randint(self, lower, upper):
        return lower + self.randbelow(upper - lower + 1)


def _shuffle(rng, values):
    for index in range(len(values) - 1, 0, -1):
        other = rng.randbelow(index + 1)
        values[index], values[other] = values[other], values[index]


def _identifier_map(rng, prefix, count, width):
    original = [('%s%0' + str(width) + 'd') % (prefix, index) for index in range(count)]
    replacement = list(original)
    _shuffle(rng, replacement)
    return dict(zip(original, replacement))


def _relabel_and_shuffle(rng, assets, services, resources, vulnerabilities, patches):
    asset_ids = _identifier_map(rng, 'A', len(assets), 2)
    service_ids = _identifier_map(rng, 'S', len(services), 2)
    resource_ids = _identifier_map(rng, 'R', len(resources), 2)
    vulnerability_ids = _identifier_map(rng, 'V', len(vulnerabilities), 3)
    patch_ids = _identifier_map(rng, 'P', len(patches), 3)

    for asset in assets:
        asset['asset_id'] = asset_ids[asset['asset_id']]
    for service in services:
        service['service_id'] = service_ids[service['service_id']]
    for resource in resources:
        resource['resource_id'] = resource_ids[resource['resource_id']]
    for vulnerability in vulnerabilities:
        vulnerability['vulnerability_id'] = vulnerability_ids[
            vulnerability['vulnerability_id']
        ]
        vulnerability['asset_id'] = asset_ids[vulnerability['asset_id']]
    for patch in patches:
        patch['patch_id'] = patch_ids[patch['patch_id']]
        patch['prerequisite_patch_ids'] = sorted(
            patch_ids[pid] for pid in patch['prerequisite_patch_ids']
        )
        patch['affected_asset_ids'] = sorted(
            asset_ids[aid] for aid in patch['affected_asset_ids']
        )
        patch['covered_vulnerability_ids'] = sorted(
            vulnerability_ids[vid] for vid in patch['covered_vulnerability_ids']
        )
        for demand in patch['resource_demands']:
            demand['resource_id'] = resource_ids[demand['resource_id']]
        patch['resource_demands'].sort(key=lambda item: item['resource_id'])
        for demand in patch['service_demands']:
            demand['service_id'] = service_ids[demand['service_id']]
        patch['service_demands'].sort(key=lambda item: item['service_id'])

    for collection in (assets, services, resources, vulnerabilities, patches):
        _shuffle(rng, collection)


def _probability_curve(rng, horizon, base, spread):
    result = []
    for slot in range(horizon):
        cycle = ((slot % 7) - 3) * spread // 10
        value = base + cycle + rng.randint(-spread, spread)
        result.append(max(1000, min(250000, value)))
    return result


def _split_windows(horizon, rng):
    split = horizon // 2 + rng.randint(-1, 1)
    return [
        {'start_slot': 0, 'end_slot': split},
        {'start_slot': split + 2, 'end_slot': horizon},
    ]


def _make_instance(seed, tier_index):
    configurations = [
        ('small', 16, 4, 2, 2, 5),
        ('medium', 22, 5, 3, 2, 9),
        ('large', 28, 7, 4, 3, 13),
    ]
    tier, base_horizon, base_assets, base_services, base_resources, base_patches = (
        configurations[tier_index]
    )
    mixed_seed = (
        (int(seed) & _MASK64)
        ^ ((tier_index + 1) * 0xA24BAED4963EE407)
    ) & _MASK64
    rng = _DeterministicRng(mixed_seed)
    horizon = base_horizon + rng.randbelow((3, 6, 9)[tier_index])
    asset_count = base_assets + rng.randbelow((2, 3, 4)[tier_index])
    service_count = base_services + rng.randbelow((2, 2, 3)[tier_index])
    resource_count = base_resources + rng.randbelow((1, 2, 2)[tier_index])
    patch_count = base_patches + rng.randbelow((1, 4, 5)[tier_index])

    assets = []
    for index in range(asset_count):
        windows = (
            [{'start_slot': 0, 'end_slot': horizon}]
            if index < 2
            else _split_windows(horizon, rng)
        )
        assets.append(
            {
                'asset_id': 'A%02d' % index,
                'exclusive_change': index % 2 == 0,
                'maintenance_windows': windows,
            }
        )

    services = []
    for index in range(service_count):
        windows = (
            [{'start_slot': 0, 'end_slot': horizon}]
            if index < 2
            else _split_windows(horizon, rng)
        )
        if index == 0:
            capacities = [1] * horizon
            budget = 3
        else:
            capacities = [
                1 + (1 if (slot + index) % 5 == 0 else 0)
                for slot in range(horizon)
            ]
            budget = max(6, horizon // 2 + index * 2)
        base_loss = 16000 + index * 5000 + rng.randint(0, 3000)
        losses = [
            base_loss + ((slot * 977 + rng.randbelow(4001)) % 7000)
            for slot in range(horizon)
        ]
        services.append(
            {
                'service_id': 'S%02d' % index,
                'maintenance_windows': windows,
                'downtime_capacity_by_slot': capacities,
                'downtime_budget': budget,
                'loss_microunits_by_slot': losses,
            }
        )

    resources = []
    for index in range(resource_count):
        capacities = []
        for slot in range(horizon):
            if index == 0:
                capacity = 1 if slot % 6 == 4 else 2
            elif index == 1:
                capacity = 2 if slot % 7 == 3 else 1
            else:
                capacity = 1 if slot % 5 in (1, 2) else 2
            capacities.append(capacity)
        resources.append(
            {
                'resource_id': 'R%02d' % index,
                'capacity_by_slot': capacities,
            }
        )

    vulnerabilities = [
        {
            'vulnerability_id': 'V000',
            'asset_id': 'A00',
            'impact_microunits': 5200000 + rng.randint(0, 250000),
            'criticality_ppm': 950000,
            'exploit_probability_ppm_by_slot': _probability_curve(
                rng, horizon, 62000, 9000
            ),
        },
        {
            'vulnerability_id': 'V001',
            'asset_id': 'A00',
            'impact_microunits': 14000000 + rng.randint(0, 500000),
            'criticality_ppm': 1000000,
            'exploit_probability_ppm_by_slot': _probability_curve(
                rng, horizon, 68000, 10000
            ),
        },
        {
            'vulnerability_id': 'V002',
            'asset_id': 'A01',
            'impact_microunits': 1100000 + rng.randint(0, 150000),
            'criticality_ppm': 800000,
            'exploit_probability_ppm_by_slot': _probability_curve(
                rng, horizon, 32000, 6000
            ),
        },
    ]

    for index in range(3, patch_count):
        asset_index = 2 + ((index - 3) % (asset_count - 2))
        vulnerabilities.append(
            {
                'vulnerability_id': 'V%03d' % index,
                'asset_id': 'A%02d' % asset_index,
                'impact_microunits': 500000 + rng.randint(0, 1000000),
                'criticality_ppm': 550000 + rng.randint(0, 350000),
                'exploit_probability_ppm_by_slot': _probability_curve(
                    rng,
                    horizon,
                    18000 + rng.randint(0, 22000),
                    5000,
                ),
            }
        )

    patches = [
        {
            'patch_id': 'P000',
            'duration': 1,
            'prerequisite_patch_ids': [],
            'affected_asset_ids': ['A00'],
            'covered_vulnerability_ids': ['V000'],
            'resource_demands': [{'resource_id': 'R00', 'units': 1}],
            'service_demands': [
                {'service_id': 'S00', 'downtime_units': 1}
            ],
            'rollback_probability_ppm': 20000,
            'rollback_impact_microunits': 400000,
        },
        {
            'patch_id': 'P001',
            'duration': 1,
            'prerequisite_patch_ids': [],
            'affected_asset_ids': ['A01'],
            'covered_vulnerability_ids': ['V002'],
            'resource_demands': [{'resource_id': 'R01', 'units': 1}],
            'service_demands': [
                {'service_id': 'S01', 'downtime_units': 1}
            ],
            'rollback_probability_ppm': 15000,
            'rollback_impact_microunits': 300000,
        },
        {
            'patch_id': 'P002',
            'duration': 3,
            'prerequisite_patch_ids': ['P001'],
            'affected_asset_ids': ['A00'],
            'covered_vulnerability_ids': ['V001'],
            'resource_demands': [{'resource_id': 'R00', 'units': 1}],
            'service_demands': [
                {'service_id': 'S00', 'downtime_units': 1}
            ],
            'rollback_probability_ppm': 35000,
            'rollback_impact_microunits': 800000,
        },
    ]

    for index in range(3, patch_count):
        pool = ['P001'] + ['P%03d' % prior for prior in range(3, index)]
        max_dependencies = (1, 2, 3)[tier_index]
        dependency_count = 0
        if pool and (tier_index > 0 or index % 2 == 0):
            dependency_count = 1 + rng.randbelow(
                min(max_dependencies, len(pool))
            )
        available = list(pool)
        dependencies = []
        for _ in range(dependency_count):
            chosen_index = rng.randbelow(len(available))
            dependencies.append(available.pop(chosen_index))
        dependencies.sort()

        asset_index = 2 + ((index - 3) % (asset_count - 2))
        service_index = 1 + ((index - 3) % (service_count - 1))
        resource_index = (index - 3) % resource_count
        resource_demands = [
            {'resource_id': 'R%02d' % resource_index, 'units': 1}
        ]
        if tier_index == 2 and resource_count > 2 and index % 5 == 0:
            second_resource = (resource_index + 1) % resource_count
            resource_demands.append(
                {'resource_id': 'R%02d' % second_resource, 'units': 1}
            )
        patches.append(
            {
                'patch_id': 'P%03d' % index,
                'duration': 1 + rng.randbelow(3),
                'prerequisite_patch_ids': dependencies,
                'affected_asset_ids': ['A%02d' % asset_index],
                'covered_vulnerability_ids': ['V%03d' % index],
                'resource_demands': resource_demands,
                'service_demands': [
                    {
                        'service_id': 'S%02d' % service_index,
                        'downtime_units': 1,
                    }
                ],
                'rollback_probability_ppm': 10000 + rng.randint(0, 50000),
                'rollback_impact_microunits': 150000 + rng.randint(0, 650000),
            }
        )

    _relabel_and_shuffle(
        rng,
        assets,
        services,
        resources,
        vulnerabilities,
        patches,
    )
    token = rng.next_u64() & 0xFFFFFFFF
    return {
        'instance_id': 'daps-%s-%08x' % (tier, token),
        'tier': tier,
        'horizon': horizon,
        'probability_scale': _SCALE,
        'assets': assets,
        'services': services,
        'resources': resources,
        'vulnerabilities': vulnerabilities,
        'patches': patches,
    }


def generate_instances(seed):
    return [_make_instance(seed, tier_index) for tier_index in range(3)]


def _rounded_div(numerator, denominator):
    return (numerator + denominator // 2) // denominator


def _security_loss(vulnerability, remediation_slot, horizon):
    remaining_ppm = _SCALE
    probabilities = vulnerability['exploit_probability_ppm_by_slot']
    for slot in range(min(horizon, remediation_slot)):
        remaining_ppm = _rounded_div(
            remaining_ppm * (_SCALE - probabilities[slot]), _SCALE
        )
    breach_ppm = _SCALE - remaining_ppm
    adjusted_impact = _rounded_div(
        vulnerability['impact_microunits'] * vulnerability['criticality_ppm'],
        _SCALE,
    )
    return _rounded_div(adjusted_impact * breach_ppm, _SCALE)


def _objective_from_schedule(instance, schedule):
    horizon = instance['horizon']
    patches = {p['patch_id']: p for p in instance['patches']}
    vulnerabilities = {
        v['vulnerability_id']: v for v in instance['vulnerabilities']
    }
    services = {s['service_id']: s for s in instance['services']}

    remediation = {vid: horizon for vid in vulnerabilities}
    for entry in schedule:
        patch = patches[entry['patch_id']]
        completion = entry['start_slot'] + patch['duration']
        for vid in patch['covered_vulnerability_ids']:
            remediation[vid] = min(remediation[vid], completion)

    security_total = sum(
        _security_loss(vulnerability, remediation[vid], horizon)
        for vid, vulnerability in vulnerabilities.items()
    )
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
        rollback_total += _rounded_div(
            patch['rollback_probability_ppm']
            * patch['rollback_impact_microunits'],
            _SCALE,
        )
    return max(1, security_total + downtime_total + rollback_total)


def validate_solution(instance, solution):
    if type(solution) is not dict or set(solution) != {'schedule'}:
        return False, 'solution must be an object containing only schedule'
    schedule = solution['schedule']
    if type(schedule) is not list:
        return False, 'schedule must be an array'

    horizon = instance['horizon']
    patches = {p['patch_id']: p for p in instance['patches']}
    assets = {a['asset_id']: a for a in instance['assets']}
    services = {s['service_id']: s for s in instance['services']}
    resources = {r['resource_id']: r for r in instance['resources']}
    selected = {}

    for index, entry in enumerate(schedule):
        if type(entry) is not dict or set(entry) != {'patch_id', 'start_slot'}:
            return False, 'schedule entry %d has invalid fields' % index
        pid = entry['patch_id']
        start = entry['start_slot']
        if type(pid) is not str or not pid:
            return False, 'schedule entry %d has an invalid patch_id' % index
        if pid not in patches:
            return False, 'unknown patch_id: %s' % pid
        if pid in selected:
            return False, 'duplicate patch_id: %s' % pid
        if type(start) is not int or type(start) is bool:
            return False, 'start_slot for %s must be an integer' % pid
        if start < 0:
            return False, 'start_slot for %s must be non-negative' % pid
        selected[pid] = start

    def contained(windows, start, end):
        return any(
            window['start_slot'] <= start and end <= window['end_slot']
            for window in windows
        )

    records = []
    for pid, start in selected.items():
        patch = patches[pid]
        end = start + patch['duration']
        if end > horizon:
            return False, 'patch %s completes after the horizon' % pid
        for prerequisite in patch['prerequisite_patch_ids']:
            if prerequisite not in selected:
                return False, 'patch %s is missing prerequisite %s' % (
                    pid,
                    prerequisite,
                )
            prerequisite_end = (
                selected[prerequisite] + patches[prerequisite]['duration']
            )
            if prerequisite_end > start:
                return False, 'prerequisite %s does not precede %s' % (
                    prerequisite,
                    pid,
                )
        for aid in patch['affected_asset_ids']:
            if aid not in assets:
                return False, 'patch %s references unknown asset %s' % (pid, aid)
            if not contained(assets[aid]['maintenance_windows'], start, end):
                return False, 'patch %s is outside asset %s maintenance windows' % (
                    pid,
                    aid,
                )
        for demand in patch['service_demands']:
            sid = demand['service_id']
            if sid not in services:
                return False, 'patch %s references unknown service %s' % (pid, sid)
            if not contained(services[sid]['maintenance_windows'], start, end):
                return False, 'patch %s is outside service %s maintenance windows' % (
                    pid,
                    sid,
                )
        records.append((pid, start, end, patch))

    occupied_assets = {}
    for pid, start, end, patch in records:
        for aid in patch['affected_asset_ids']:
            if not assets[aid]['exclusive_change']:
                continue
            for slot in range(start, end):
                key = (aid, slot)
                if key in occupied_assets:
                    return False, 'patches %s and %s overlap on asset %s' % (
                        occupied_assets[key],
                        pid,
                        aid,
                    )
                occupied_assets[key] = pid

    resource_usage = {rid: [0] * horizon for rid in resources}
    service_usage = {sid: [0] * horizon for sid in services}
    for pid, start, end, patch in records:
        for demand in patch['resource_demands']:
            rid = demand['resource_id']
            if rid not in resources:
                return False, 'patch %s references unknown resource %s' % (pid, rid)
            for slot in range(start, end):
                resource_usage[rid][slot] += demand['units']
        for demand in patch['service_demands']:
            sid = demand['service_id']
            for slot in range(start, end):
                service_usage[sid][slot] += demand['downtime_units']

    for rid, usage in resource_usage.items():
        capacity = resources[rid]['capacity_by_slot']
        for slot in range(horizon):
            if usage[slot] > capacity[slot]:
                return False, 'resource %s exceeds capacity at slot %d' % (
                    rid,
                    slot,
                )
    for sid, usage in service_usage.items():
        service = services[sid]
        capacity = service['downtime_capacity_by_slot']
        for slot in range(horizon):
            if usage[slot] > capacity[slot]:
                return False, 'service %s exceeds downtime capacity at slot %d' % (
                    sid,
                    slot,
                )
        if sum(usage) > service['downtime_budget']:
            return False, 'service %s exceeds its cumulative downtime budget' % sid

    return True, 'ok'


def evaluate_solution(instance, solution):
    return _objective_from_schedule(instance, solution['schedule'])


def _closure_ids(root, patches):
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


def _patch_order(instance, by_density):
    horizon = instance['horizon']
    patches = {p['patch_id']: p for p in instance['patches']}
    vulnerabilities = {
        v['vulnerability_id']: v for v in instance['vulnerabilities']
    }
    services = {s['service_id']: s for s in instance['services']}
    full_losses = {
        vid: _security_loss(vulnerability, horizon, horizon)
        for vid, vulnerability in vulnerabilities.items()
    }
    scored = []
    for root in sorted(patches):
        bundle = _closure_ids(root, patches)
        covered = set()
        penalty = 0
        work = 0
        for pid in bundle:
            patch = patches[pid]
            covered.update(patch['covered_vulnerability_ids'])
            work += patch['duration'] * (
                1
                + sum(d['units'] for d in patch['resource_demands'])
                + sum(d['downtime_units'] for d in patch['service_demands'])
            )
            penalty += _rounded_div(
                patch['rollback_probability_ppm']
                * patch['rollback_impact_microunits'],
                _SCALE,
            )
            for demand in patch['service_demands']:
                service = services[demand['service_id']]
                average_rate = sum(service['loss_microunits_by_slot']) // horizon
                penalty += (
                    patch['duration']
                    * demand['downtime_units']
                    * average_rate
                )
        benefit = sum(full_losses[vid] for vid in covered)
        net = max(0, benefit - penalty)
        score = (net * _SCALE) // max(1, work) if by_density else net
        scored.append((-score, root))
    scored.sort()
    return [root for _, root in scored]


def _earliest_start(instance, pid, schedule, patches):
    horizon = instance['horizon']
    patch = patches[pid]
    selected = {entry['patch_id']: entry['start_slot'] for entry in schedule}
    lower_bound = 0
    for prerequisite in patch['prerequisite_patch_ids']:
        if prerequisite not in selected:
            return None
        lower_bound = max(
            lower_bound,
            selected[prerequisite] + patches[prerequisite]['duration'],
        )
    last_start = horizon - patch['duration']
    for start in range(lower_bound, last_start + 1):
        trial = {'schedule': schedule + [{'patch_id': pid, 'start_slot': start}]}
        valid, _ = validate_solution(instance, trial)
        if valid:
            return start
    return None


def _construct(instance, order):
    patches = {p['patch_id']: p for p in instance['patches']}
    schedule = []
    selected = set()
    current_value = _objective_from_schedule(instance, schedule)
    for root in order:
        if root in selected:
            continue
        needed = [
            pid for pid in _closure_ids(root, patches) if pid not in selected
        ]
        trial = [dict(entry) for entry in schedule]
        failed = False
        for pid in needed:
            start = _earliest_start(instance, pid, trial, patches)
            if start is None:
                failed = True
                break
            trial.append({'patch_id': pid, 'start_slot': start})
        if failed:
            continue
        trial_value = _objective_from_schedule(instance, trial)
        if trial_value < current_value:
            schedule = trial
            current_value = trial_value
            selected = {entry['patch_id'] for entry in schedule}
    schedule.sort(key=lambda entry: (entry['start_slot'], entry['patch_id']))
    return {'schedule': schedule}


def _exact_small(instance, incumbent):
    patches = {p['patch_id']: p for p in instance['patches']}
    patch_ids = sorted(patches)
    if len(patch_ids) > 6:
        raise ValueError('exact reference is limited to at most six patches')

    best_schedule = [dict(entry) for entry in incumbent['schedule']]
    best_key = (
        _objective_from_schedule(instance, best_schedule),
        tuple((entry['start_slot'], entry['patch_id']) for entry in best_schedule),
    )

    for mask in range(1 << len(patch_ids)):
        selected = {
            patch_ids[index]
            for index in range(len(patch_ids))
            if mask & (1 << index)
        }
        if any(
            prerequisite not in selected
            for pid in selected
            for prerequisite in patches[pid]['prerequisite_patch_ids']
        ):
            continue

        remaining = set(selected)
        order = []
        while remaining:
            ready = sorted(
                pid
                for pid in remaining
                if set(patches[pid]['prerequisite_patch_ids']).issubset(order)
            )
            if not ready:
                raise ValueError('patch dependency graph contains a cycle')
            chosen = ready[0]
            order.append(chosen)
            remaining.remove(chosen)

        def search(index, schedule):
            nonlocal best_key, best_schedule
            if index == len(order):
                canonical = sorted(
                    schedule,
                    key=lambda entry: (entry['start_slot'], entry['patch_id']),
                )
                key = (
                    _objective_from_schedule(instance, canonical),
                    tuple(
                        (entry['start_slot'], entry['patch_id'])
                        for entry in canonical
                    ),
                )
                if key < best_key:
                    best_key = key
                    best_schedule = [dict(entry) for entry in canonical]
                return

            pid = order[index]
            patch = patches[pid]
            lower_bound = 0
            placed = {entry['patch_id']: entry for entry in schedule}
            for prerequisite in patch['prerequisite_patch_ids']:
                entry = placed[prerequisite]
                lower_bound = max(
                    lower_bound,
                    entry['start_slot'] + patches[prerequisite]['duration'],
                )
            for start in range(
                lower_bound,
                instance['horizon'] - patch['duration'] + 1,
            ):
                trial = schedule + [{'patch_id': pid, 'start_slot': start}]
                valid, _ = validate_solution(instance, {'schedule': trial})
                if valid:
                    search(index + 1, trial)

        search(0, [])

    return {'schedule': best_schedule}


def solve_random(instance):
    return {'schedule': []}


def solve_baseline(instance):
    return _construct(instance, _patch_order(instance, True))


def solve_reference(instance):
    density_order = _patch_order(instance, True)
    value_order = _patch_order(instance, False)
    orders = [density_order, value_order]
    for first in value_order:
        orders.append([first] + [pid for pid in density_order if pid != first])

    best_solution = None
    best_key = None
    for order in orders:
        solution = _construct(instance, order)
        metric = _objective_from_schedule(instance, solution['schedule'])
        signature = tuple(
            (entry['start_slot'], entry['patch_id'])
            for entry in solution['schedule']
        )
        key = (metric, signature)
        if best_key is None or key < best_key:
            best_key = key
            best_solution = solution
    if instance['tier'] == 'small':
        return _exact_small(instance, best_solution)
    return best_solution
