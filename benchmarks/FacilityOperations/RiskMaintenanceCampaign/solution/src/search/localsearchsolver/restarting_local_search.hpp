#pragma once

#include "localsearchsolver/common.hpp"

#include <unordered_set>
#include <thread>

namespace localsearchsolver
{

template <typename LocalScheme>
using RestartingLocalSearchCallback = std::function<void(const typename LocalScheme::Solution&)>;

template <typename LocalScheme>
struct RestartingLocalSearchOptionalParameters
{
    typedef typename LocalScheme::Solution Solution;
    typedef typename LocalScheme::GlobalCost GlobalCost;

    /** Maximum number of restarts. */
    Counter maximum_number_of_restarts = -1;
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
    RestartingLocalSearchCallback<LocalScheme> new_solution_callback
        = [](const Solution& solution) { (void)solution; };
    /** Info structure. */
    optimizationtools::Info info;
};

template <typename LocalScheme>
struct RestartingLocalSearchOutput
{
    /** Constructor. */
    RestartingLocalSearchOutput(
            const LocalScheme& local_scheme,
            Counter maximum_size_of_the_solution_pool):
        solution_pool(local_scheme, maximum_size_of_the_solution_pool) { }

    /** Solution pool. */
    SolutionPool<LocalScheme> solution_pool;
    /** Number of restarts. */
    Counter number_of_restarts = 0;
};

template <typename LocalScheme>
inline RestartingLocalSearchOutput<LocalScheme> iterated_local_search(
        LocalScheme& local_scheme,
        RestartingLocalSearchOptionalParameters<LocalScheme> parameters = {});

///////////////////////////////////////////////////////////////////////////////
/////////////////////////// Template implementations //////////////////////////
///////////////////////////////////////////////////////////////////////////////

template <typename LocalScheme>
inline RestartingLocalSearchOutput<LocalScheme> restarting_local_search(
        LocalScheme& local_scheme,
        RestartingLocalSearchOptionalParameters<LocalScheme> parameters)
{
    // Initial display.
    VER(parameters.info,
               "=======================================" << std::endl
            << "          Local Search Solver          " << std::endl
            << "=======================================" << std::endl
            << std::endl
            << "Algorithm" << std::endl
            << "---------" << std::endl
            << "Restarting Local Search" << std::endl
            << std::endl
            << "Parameters" << std::endl
            << "----------" << std::endl
            << "Maximum number of restarts:      " << parameters.maximum_number_of_restarts << std::endl
            << "Seed:                            " << parameters.seed << std::endl
            << "Maximum size of the pool:        " << parameters.maximum_size_of_the_solution_pool << std::endl
            << "Time limit:                      " << parameters.info.time_limit << std::endl
            << std::endl
       );

    //std::cout << "iterated_local_search start" << std::endl;
    RestartingLocalSearchOutput<LocalScheme> output(
            local_scheme,
            parameters.maximum_size_of_the_solution_pool);
    output.solution_pool.display_init(parameters.info);

    std::mt19937_64 generator(parameters.seed);

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

        // Generate initial solution.
        Counter initial_solution_pos = (output.number_of_restarts - 1) % number_of_initial_solutions;
        auto solution = (initial_solution_pos < (Counter)parameters.initial_solution_ids.size())?
            local_scheme.initial_solution(parameters.initial_solution_ids[initial_solution_pos], generator):
            parameters.initial_solutions[initial_solution_pos - (Counter)parameters.initial_solution_ids.size()];
        // Local Search.
        local_scheme.local_search(solution, generator);

        // Check for a new best solution.
        if (output.solution_pool.size() == 0
                || local_scheme.global_cost(output.solution_pool.worst())
                > local_scheme.global_cost(solution)) {
            std::stringstream ss;
            ss << "iteration " << output.number_of_restarts;
            output.solution_pool.add(solution, ss, parameters.info);
            output.solution_pool.display(ss, parameters.info);
            parameters.new_solution_callback(solution);
        }
    }

    output.solution_pool.display_end(parameters.info);
    VER(parameters.info, "Number of restarts:         " << output.number_of_restarts << std::endl);
    PUT(parameters.info, "Algorithm", "NumberOfRestarts", output.number_of_restarts);
    return output;
}

}

