#include "examples/roadef2020.hpp"

#include <numeric>
#include <unordered_set>

using namespace localsearchsolver::roadef2020;

void LocalScheme::add(
        Solution& solution,
        InterventionId j,
        Time t_start) const
{
    assert(t_start >= 0);
    assert(t_start < instance_.horizon());
    assert(t_start <= instance_.start_max(j));
    assert(solution.intervention_starts[j] == -1);

    Time t_end = t_start + instance_.duration(j, t_start);
    ScenarioId lcm = instance_.least_common_multiple();

    // Update intervention_times_.
    solution.number_of_interventions++;
    solution.intervention_starts[j] = t_start;

    for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
        // Update solution.time_steps.
        for (ResourcePos r_pos = 0; r_pos < instance_.number_of_resources(j); ++r_pos) {
            ResourceId r = instance_.resource(j, r_pos);
            Workload w = instance_.workload(j, r_pos, t_cur, t_start);
            Workload w_min = instance_.workload_min(r, t_cur);
            Workload w_max = instance_.workload_max(r, t_cur);
            // Update overwork
            if (solution.time_steps[t_cur].workloads[r] >= w_max) {
                solution.overwork += w;
            } else if (solution.time_steps[t_cur].workloads[r] + w <= w_max) {
            } else {
                solution.overwork += (solution.time_steps[t_cur].workloads[r] + w - w_max);
            }
            // Update underwork
            if (solution.time_steps[t_cur].workloads[r] >= w_min) {
            } else if (solution.time_steps[t_cur].workloads[r] + w_min <= w_min) {
                solution.underwork -= w;
            } else {
                solution.underwork -= (w_min - solution.time_steps[t_cur].workloads[r]);
            }
            // Update workload
            solution.time_steps[t_cur].workloads[r] += w;
            assert(solution.time_steps[t_cur].workloads[r] >= 0);
        }

        // Update conflicts_
        SeasonId season = instance_.season(t_cur);
        if (season != -1) {
            for (ExclusionId e: instance_.exclusions(j, season)) {
                InterventionId j2 = instance_.exclusion(e).j(j);
                if (solution.intervention_starts[j2] == -1)
                    continue;
                Time t2_start = solution.intervention_starts[j2];
                if (t2_start <= t_cur && t_cur < t2_start + instance_.duration(j2, t2_start)) {
                    SolutionConflict conflict;
                    conflict.j1 = j;
                    conflict.j2 = j2;
                    conflict.t_cur = t_cur;
                    solution.conflicts.push_back(conflict);
                }
            }
        }

        // Remove previous cost
        ScenarioId s_pos = std::ceil(instance_.quantile() * instance_.number_of_scenarios(t_cur)) - 1;
        solution.mean_cost -= lcm / instance_.number_of_scenarios(t_cur) * solution.time_steps[t_cur].risk_sum;
        Risk ee = lcm * solution.time_steps[t_cur].risks[solution.time_steps[t_cur].sorted_scenarios[s_pos]]
            - lcm / instance_.number_of_scenarios(t_cur) * solution.time_steps[t_cur].risk_sum;
        if (ee > 0)
            solution.expected_excess -= ee;
        assert(solution.mean_cost >= 0);
        assert(solution.expected_excess >= 0);

        // Update risks
        solution.time_steps[t_cur].risk_sum = 0;
        for (ScenarioId s = 0; s < instance_.number_of_scenarios(t_cur); ++s) {
            solution.time_steps[t_cur].risks[s] += instance_.risk(j, t_cur, t_start, s);
            solution.time_steps[t_cur].risk_sum += solution.time_steps[t_cur].risks[s];
        }
        // Update sorted scenarios
        std::nth_element(
                solution.time_steps[t_cur].sorted_scenarios.begin(),
                solution.time_steps[t_cur].sorted_scenarios.begin() + s_pos,
                solution.time_steps[t_cur].sorted_scenarios.end(),
                [&solution, t_cur](ScenarioId s1, ScenarioId s2)
                {
                    return solution.time_steps[t_cur].risks[s1]
                        < solution.time_steps[t_cur].risks[s2];
                });
        // Update cost
        solution.mean_cost += lcm / instance_.number_of_scenarios(t_cur) * solution.time_steps[t_cur].risk_sum;
        ee = lcm * solution.time_steps[t_cur].risks[solution.time_steps[t_cur].sorted_scenarios[s_pos]]
            - lcm / instance_.number_of_scenarios(t_cur) * solution.time_steps[t_cur].risk_sum;
        if (ee > 0)
            solution.expected_excess += ee;
        assert(solution.mean_cost >= 0);
        assert(solution.expected_excess >= 0);
    }
}

void LocalScheme::remove(
        Solution& solution,
        InterventionId j) const
{
    assert(solution.intervention_starts[j] != -1);
    Time t_start = solution.intervention_starts[j];
    Time t_end = t_start + instance_.duration(j, t_start);
    ScenarioId lcm = instance_.least_common_multiple();

    // Update intervention_times_.
    solution.number_of_interventions--;
    solution.intervention_starts[j] = -1;

    // Update solution.conflicts
    for (auto it = solution.conflicts.begin(); it != solution.conflicts.end();) {
        if (it->j1 != j && it->j2 != j) {
            ++it;
        } else {
            *it = solution.conflicts.back();
            solution.conflicts.pop_back();
        }
    }

    // Update solution.time_steps.
    for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
        // Update solution.time_steps.
        for (ResourcePos r_pos = 0; r_pos < instance_.number_of_resources(j); ++r_pos) {
            ResourceId r = instance_.resource(j, r_pos);
            Workload w = instance_.workload(j, r_pos, t_cur, t_start);
            Workload w_min = instance_.workload_min(r, t_cur);
            Workload w_max = instance_.workload_max(r, t_cur);
            // Update overwork
            if (solution.time_steps[t_cur].workloads[r] - w >= w_max) {
                solution.overwork -= w;
            } else if (solution.time_steps[t_cur].workloads[r] <= w_max) {
            } else {
                solution.overwork -= (solution.time_steps[t_cur].workloads[r] - w_max);
            }
            // Update underwork
            if (solution.time_steps[t_cur].workloads[r] - w >= w_min) {
            } else if (solution.time_steps[t_cur].workloads[r] <= w_min) {
                solution.underwork += w;
            } else {
                solution.underwork += (solution.time_steps[t_cur].workloads[r] - w_min);
            }
            // Update workload
            solution.time_steps[t_cur].workloads[r] -= w;
        }

        // Remove previous cost
        ScenarioId s_pos = std::ceil(instance_.quantile() * instance_.number_of_scenarios(t_cur)) - 1;
        solution.mean_cost -= lcm / instance_.number_of_scenarios(t_cur) * solution.time_steps[t_cur].risk_sum;
        Risk ee = lcm * solution.time_steps[t_cur].risks[solution.time_steps[t_cur].sorted_scenarios[s_pos]]
            - lcm / instance_.number_of_scenarios(t_cur) * solution.time_steps[t_cur].risk_sum;
        if (ee > 0)
            solution.expected_excess -= ee;
        assert(solution.mean_cost >= 0);
        assert(solution.expected_excess >= 0);

        // Update risks
        solution.time_steps[t_cur].risk_sum = 0;
        for (ScenarioId s = 0; s < instance_.number_of_scenarios(t_cur); ++s) {
            solution.time_steps[t_cur].risks[s] -= instance_.risk(j, t_cur, t_start, s);
            solution.time_steps[t_cur].risk_sum += solution.time_steps[t_cur].risks[s];
        }
        // Update sorted scenarios
        std::nth_element(
                solution.time_steps[t_cur].sorted_scenarios.begin(),
                solution.time_steps[t_cur].sorted_scenarios.begin() + s_pos,
                solution.time_steps[t_cur].sorted_scenarios.end(),
                [&solution, t_cur](ScenarioId s1, ScenarioId s2)
                {
                    return solution.time_steps[t_cur].risks[s1]
                        < solution.time_steps[t_cur].risks[s2];
                });
        // Update cost
        solution.mean_cost += lcm / instance_.number_of_scenarios(t_cur) * solution.time_steps[t_cur].risk_sum;
        ee = lcm * solution.time_steps[t_cur].risks[solution.time_steps[t_cur].sorted_scenarios[s_pos]]
            - lcm / instance_.number_of_scenarios(t_cur) * solution.time_steps[t_cur].risk_sum;
        if (ee > 0)
            solution.expected_excess += ee;
        assert(solution.mean_cost >= 0);
        assert(solution.expected_excess >= 0);
    }
}

LocalScheme::GlobalCost LocalScheme::cost_add(
        const Solution& solution,
        InterventionId j,
        Time t_start,
        const GlobalCost& cutoff)
{
    assert(t_start >= 0);
    assert(t_start < instance_.horizon());
    assert(t_start <= instance_.start_max(j));
    assert(solution.intervention_starts[j] == -1);

    Time t_end = t_start + instance_.duration(j, t_start);
    GlobalCost c = global_cost(solution);
    number_of_interventions(c)--; // because -number_of_interventions

    // Check disjonctive constraints.
    for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
        SeasonId season = instance_.season(t_cur);
        if (season != -1) {
            for (ExclusionId e: instance_.exclusions(j, season)) {
                InterventionId j2 = instance_.exclusion(e).j(j);
                if (solution.intervention_starts[j2] == -1)
                    continue;
                Time t2_start = solution.intervention_starts[j2];
                if (t2_start <= t_cur && t_cur < t2_start + instance_.duration(j2, t2_start)) {
                    number_of_conflicts(c)++;
                    if (c >= cutoff)
                        return cutoff;
                }
            }
        }
    }

    // Check resource constraint.
    for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
        for (ResourcePos r_pos = 0; r_pos < instance_.number_of_resources(j); ++r_pos) {
            Workload w = instance_.workload(j, r_pos, t_cur, t_start);
            if (w == 0)
                continue;
            ResourceId r = instance_.resource(j, r_pos);
            Workload w_cur = solution.time_steps[t_cur].workloads[r];
            Workload w_max = instance_.workload_max(r, t_cur);
            if (w_cur >= w_max) {
                overwork(c) += w;
                if (c >= cutoff)
                    return cutoff;
            } else if (w_cur + w <= w_max) {
            } else {
                overwork(c) += (w_cur + w - w_max);
                if (c >= cutoff)
                    return cutoff;
            }
        }
    }

    Cost mean_cost = solution.mean_cost;
    Cost expected_excess = solution.expected_excess;
    ScenarioId lcm = instance_.least_common_multiple();
    for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
        ScenarioId st = instance_.number_of_scenarios(t_cur);
        ScenarioId s_pos = std::ceil(instance_.quantile() * st) - 1;

        // Remove previous cost
        mean_cost -= lcm / st * solution.time_steps[t_cur].risk_sum;
        Risk ee = lcm * solution.time_steps[t_cur].risks[solution.time_steps[t_cur].sorted_scenarios[s_pos]]
            - lcm / st * solution.time_steps[t_cur].risk_sum;
        if (ee > 0)
            expected_excess -= ee;

        // Update risks
        Risk risk_sum = 0;
        for (ScenarioId s = 0; s < st; ++s) {
            sorted_scenarios_[s] = solution.time_steps[t_cur].sorted_scenarios[s];
            risks_[s] = solution.time_steps[t_cur].risks[s] + instance_.risk(j, t_cur, t_start, s);
            risk_sum += risks_[s];
        }
        // Update sorted scenarios
        std::nth_element(
                sorted_scenarios_.begin(),
                sorted_scenarios_.begin() + s_pos,
                sorted_scenarios_.begin() + st,
                [this](ScenarioId s1, ScenarioId s2)
                {
                    return risks_[s1] < risks_[s2];
                });
        // Update cost
        mean_cost += lcm / st * risk_sum;
        ee = lcm * risks_[sorted_scenarios_[s_pos]]
            - lcm / st * risk_sum;
        if (ee > 0)
            expected_excess += ee;

        cost(c) = instance_.alpha_1() * mean_cost
            + instance_.alpha_2() * expected_excess;
        if (c >= cutoff)
            return cutoff;
    }

    cost(c) = instance_.alpha_1() * mean_cost
        + instance_.alpha_2() * expected_excess;
    assert(cost(c) >= 0);
    return c;
}

/***************************** Initial solutions *****************************/

LocalScheme::Solution LocalScheme::empty_solution() const
{
    Solution solution;
    solution.intervention_starts.resize(instance_.number_of_interventions(), -1);
    solution.time_steps.resize(instance_.horizon());
    for (Time t = 0; t < instance_.horizon(); ++t) {
        solution.time_steps[t].workloads.resize(instance_.number_of_resources(), 0);
        solution.time_steps[t].risks.resize(instance_.number_of_scenarios(t), 0);
        solution.time_steps[t].sorted_scenarios.resize(instance_.number_of_scenarios(t));
        for (ScenarioId s = 0; s < instance_.number_of_scenarios(t); ++s)
            solution.time_steps[t].sorted_scenarios[s] = s;
        // Initialize underwork
        for (ResourceId r = 0; r < instance_.number_of_resources(); ++r)
            solution.underwork += instance_.workload_min(r, t);
    }
    return solution;
}

LocalScheme::Solution LocalScheme::initial_solution(
        Counter,
        std::mt19937_64& generator)
{
    Solution solution = empty_solution();

    for (InterventionId j = 0; j < instance_.number_of_interventions(); ++j) {
        std::vector<Time> starts;
        for (Time t_start = 0; t_start <= instance_.start_max(j); ++t_start) {
            if (instance_.fixed(j, t_start) == 0)
                continue;
            starts.push_back(t_start);
        }
        std::shuffle(starts.begin(), starts.end(), generator);
        add(solution, j, starts.front());
    }
    return solution;
}

/******************************** Local search *******************************/

std::vector<LocalScheme::Move> LocalScheme::perturbations(
        Solution& solution,
        std::mt19937_64&)
{
    std::vector<Move> moves;
    for (InterventionId j = 0; j < instance_.number_of_interventions(); ++j) {
        Time t_start_old = solution.intervention_starts[j];
        if (instance_.fixed(j, t_start_old) == 1)
            continue;
        remove(solution, j);
        for (Time t_start = 0; t_start <= instance_.start_max(j); ++t_start) {
            if (instance_.fixed(j, t_start) == 0)
                continue;
            auto c = cost_add(solution, j, t_start, worst<GlobalCost>());
            Move move;
            move.j = j;
            move.t_start = t_start;
            move.global_cost = c;
            number_of_conflicts(move.global_cost) = number_of_conflicts(global_cost(solution));
            overwork(move.global_cost) = overwork(global_cost(solution));
            underwork(move.global_cost) = underwork(global_cost(solution));
            moves.push_back(move);
        }
        add(solution, j, t_start_old);
    }
    return moves;
}

void LocalScheme::local_search(
        Solution& solution,
        std::mt19937_64& generator,
        const Move& tabu)
{
    //if (tabu.j != -1)
    //    std::cout << "j " << tabu.j
    //        << " name " << instance_.intervention_name(tabu.j)
    //        << " t_start " << tabu.t_start
    //        << " d " << instance_.duration(tabu.j, tabu.t_start)
    //        << std::endl;
    //std::cout << to_string(global_cost(solution)) << std::endl;
    //std::cout << real_cost(solution) << std::endl;
    std::vector<Counter> neighborhoods = {0};
    Counter it;
    for (it = 0; ; ++it) {
        GlobalCost c_best = global_cost(solution);

        bool improved = false;
        // Loop through neighborhoods.
        for (Counter neighborhood: neighborhoods) {
            switch (neighborhood) {
            case 0: { // Shift neighborhood.
                std::shuffle(interventions_.begin(), interventions_.end(), generator);
                std::shuffle(times_.begin(), times_.end(), generator);
                InterventionId j_best = -1;
                Time t_start_best = -1;
                for (InterventionId j: interventions_) {
                    if (j == tabu.j)
                        continue;
                    Time t_start_old = solution.intervention_starts[j];
                    assert(t_start_old != -1);
                    if (instance_.fixed(j, t_start_old) == 1)
                        continue;
                    remove(solution, j);
                    for (Time t_start: times_) {
                        if (t_start > instance_.start_max(j))
                            continue;
                        if (t_start == t_start_old)
                            continue;
                        if (instance_.fixed(j, t_start) == 0)
                            continue;
                        GlobalCost c = cost_add(solution, j, t_start, c_best);
                        if (c >= c_best)
                            continue;
                        if (j_best != -1 && !dominates(c, c_best))
                            continue;
                        j_best = j;
                        t_start_best = t_start;
                        c_best = c;
                    }
                    add(solution, j, t_start_old);
                }
                if (j_best != -1) {
                    improved = true;
                    // Apply best move.
                    remove(solution, j_best);
                    add(solution, j_best, t_start_best);
                }
                break;
            } default: {
            }
            }
            if (improved)
                break;
        }
        if (!improved) {
            break;
        }
    }
    //std::cout << "it " << it << std::endl;
    //std::cout << to_string(global_cost(solution)) << std::endl;
    //std::cout << real_cost(solution) << std::endl;
}

