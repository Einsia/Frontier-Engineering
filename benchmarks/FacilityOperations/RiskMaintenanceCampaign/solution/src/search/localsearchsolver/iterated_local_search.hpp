#pragma once

#include "localsearchsolver/common.hpp"

#include <unordered_set>
#include <thread>

namespace localsearchsolver
{

template <typename LocalScheme>
using IteratedLocalSearchCallback = std::function<void(const typename LocalScheme::Solution&)>;

template <typename LocalScheme>
struct IteratedLocalSearchOptionalParameters
{
    typedef typename LocalScheme::Solution Solution;
    typedef typename LocalScheme::GlobalCost GlobalCost;

    /** Maximum number of iterations. */
    Counter maximum_number_of_iterations = -1;
    /** Maximum number of restarts. */
    Counter maximum_number_of_restarts = -1;
    /**
     * Minimum number of perturbation.
     *
     * In the literature, such a strategy is known as "Evolutionary Local
     * Search"
     *
     * See "Evolutionary Local Search for the Super-Peer Selection Problem and
     * the p-Hub Median Problem" (WolfPeter et Merz, 2007)
     * https://doi.org/10.1007/978-3-540-75514-2_1
     */
    Counter minimum_number_of_perturbations = 1;
    /** Ids of generated initial solutions. */
    std::vector<Counter> initial_solution_ids = {0};
    /** User-provided initial solutions. */
    std::vector<Solution> initial_solutions;
    /** Maximum size of the solution pool. */
    Counter maximum_size_of_the_solution_pool = 1;
    /** Seed. */
    Seed seed = 0;
    /** Cutoff. */
    GlobalCost cutoff = best<GlobalCost>();
    /** Callback function called when a new best solution is found. */
    IteratedLocalSearchCallback<LocalScheme> new_solution_callback
        = [](const Solution& solution) { (void)solution; };
    /** Info structure. */
    optimizationtools::Info info;
};

template <typename LocalScheme>
struct IteratedLocalSearchOutput
{
    /** Constructor. */
    IteratedLocalSearchOutput(
            const LocalScheme& local_scheme,
            Counter maximum_size_of_the_solution_pool):
        solution_pool(local_scheme, maximum_size_of_the_solution_pool) { }

    /** Solution pool. */
    SolutionPool<LocalScheme> solution_pool;
    /** Number of iterations. */
    Counter number_of_iterations = 0;
    /** Number of restarts. */
    Counter number_of_restarts = 0;
};

template <typename LocalScheme>
inline IteratedLocalSearchOutput<LocalScheme> iterated_local_search(
        LocalScheme& local_scheme,
        IteratedLocalSearchOptionalParameters<LocalScheme> parameters = {});

///////////////////////////////////////////////////////////////////////////////
/////////////////////////// Template implementations //////////////////////////
///////////////////////////////////////////////////////////////////////////////

template <typename LocalScheme>
inline IteratedLocalSearchOutput<LocalScheme> iterated_local_search(
        LocalScheme& local_scheme,
        IteratedLocalSearchOptionalParameters<LocalScheme> parameters)
{
    typedef typename LocalScheme::Solution Solution;
    typedef typename LocalScheme::Move Move;

    // Initial display.
    VER(parameters.info, ""
            << "=======================================" << std::endl
            << "          Local Search Solver          " << std::endl
            << "=======================================" << std::endl
            << std::endl
            << "Algorithm" << std::endl
            << "---------" << std::endl
            << "Iterated Local Search" << std::endl
            << std::endl
            << "Parameters" << std::endl
            << "----------" << std::endl
            << "Maximum number of iterations:     " << parameters.maximum_number_of_iterations << std::endl
            << "Maximum number of restarts:       " << parameters.maximum_number_of_restarts << std::endl
            << "Minimum number of perturbations:  " << parameters.minimum_number_of_perturbations << std::endl
            << "Seed:                             " << parameters.seed << std::endl
            << "Maximum size of the pool:         " << parameters.maximum_size_of_the_solution_pool << std::endl
            << "Time limit:                       " << parameters.info.time_limit << std::endl);
    print_local_scheme_parameters(local_scheme, parameters.info);
    VER(parameters.info, std::endl);

    auto move_compare = [](const Move& move_1, const Move& move_2) -> bool
    {
        return move_1.global_cost < move_2.global_cost;
    };

    //std::cout << "iterated_local_search start" << std::endl;
    IteratedLocalSearchOutput<LocalScheme> output(
            local_scheme,
            parameters.maximum_size_of_the_solution_pool);
    output.solution_pool.display_init(parameters.info);

    std::mt19937_64 generator(parameters.seed);

    std::vector<Solution> initial_solutions;
    Counter number_of_initial_solutions
        = (Counter)parameters.initial_solution_ids.size()
        + (Counter)parameters.initial_solutions.size();
    for (output.number_of_restarts = 1;; output.number_of_restarts++) {
        // Check maximum number of restarts.
        if (parameters.maximum_number_of_restarts >= 0
                && output.number_of_restarts > parameters.maximum_number_of_restarts)
            break;

        // Check time.
        if (parameters.info.needs_to_end())
            break;

        // Check cutoff.
        if (local_scheme.global_cost(output.solution_pool.best())
                <= parameters.cutoff)
            break;

        // Generate initial solutions.
        if (initial_solutions.empty()) {
            for (Counter initial_solution_pos = 0;
                    initial_solution_pos < number_of_initial_solutions;
                    initial_solution_pos++) {

                auto solution_tmp = (initial_solution_pos < (Counter)parameters.initial_solution_ids.size())?
                    local_scheme.initial_solution(parameters.initial_solution_ids[initial_solution_pos], generator):
                    parameters.initial_solutions[initial_solution_pos - (Counter)parameters.initial_solution_ids.size()];
                local_scheme.local_search(solution_tmp, generator);

                // Check for a new best solution.
                if (output.solution_pool.size() == 0
                        || local_scheme.global_cost(output.solution_pool.worst())
                        > local_scheme.global_cost(solution_tmp)) {
                    std::stringstream ss;
                    ss << "s" << output.number_of_restarts;
                    output.solution_pool.add(solution_tmp, ss, parameters.info);
                    output.solution_pool.display(ss, parameters.info);
                    parameters.new_solution_callback(solution_tmp);
                }

                initial_solutions.push_back(solution_tmp);
            }

            std::sort(
                    initial_solutions.begin(),
                    initial_solutions.end(),
                    [&local_scheme](const Solution& solution_1, const Solution& solution_2) -> bool
                    {
                        return local_scheme.global_cost(solution_1)
                            > local_scheme.global_cost(solution_2);
                    });
        }

        Solution solution_cur = initial_solutions.back();
        initial_solutions.pop_back();
        Counter perturbation_id = 0;
        std::vector<Move> perturbations = local_scheme.perturbations(solution_cur, generator);
        // Sort moves.
        std::sort(perturbations.begin(), perturbations.end(), move_compare);
        Counter depth = 1;
        Solution solution_next = solution_cur;
        bool better_found = false;
        for (;; ++output.number_of_iterations) {

            // Check end.
            if (parameters.info.needs_to_end())
                break;

            // Check cutoff.
            if (local_scheme.global_cost(output.solution_pool.best())
                    <= parameters.cutoff)
                break;

            if (perturbation_id >= parameters.minimum_number_of_perturbations
                    && better_found) {
                solution_cur = solution_next;
                better_found = false;
                perturbation_id = 0;
                depth++;
                perturbations = local_scheme.perturbations(solution_cur, generator);
                // Sort moves.
                std::sort(perturbations.begin(), perturbations.end(), move_compare);
            }

            if (perturbation_id >= (Counter)perturbations.size())
                break;

            // Apply perturbation and local search.
            Solution solution_tmp = solution_cur;
            auto move = perturbations[perturbation_id];
            local_scheme.apply_move(solution_tmp, move);
            local_scheme.local_search(solution_tmp, generator, move);

            // Check for a new best solution.
            if (output.solution_pool.size() == 0
                    || local_scheme.global_cost(output.solution_pool.worst())
                    > local_scheme.global_cost(solution_tmp)) {
                std::stringstream ss;
                ss << "s" << output.number_of_restarts
                    << " d" << depth
                    << " c" << perturbation_id << "/" << perturbations.size()
                    << " i" << output.number_of_iterations;
                output.solution_pool.add(solution_tmp, ss, parameters.info);
                output.solution_pool.display(ss, parameters.info);
                parameters.new_solution_callback(solution_tmp);
            }

            if (local_scheme.global_cost(solution_next)
                    > local_scheme.global_cost(solution_tmp)) {
                solution_next = solution_tmp;
                better_found = true;
            }

            perturbation_id++;
        }
    }

    output.solution_pool.display_end(parameters.info);
    VER(parameters.info, "Number of restarts:         " << output.number_of_restarts << std::endl);
    VER(parameters.info, "Number of iterations:       " << output.number_of_iterations << std::endl);
    PUT(parameters.info, "Algorithm", "NumberOfRestarts", output.number_of_restarts);
    PUT(parameters.info, "Algorithm", "NumberOfIterations", output.number_of_iterations);
    print_local_scheme_statistics(local_scheme, parameters.info);
    return output;
}

}

