#pragma once

#include "localsearchsolver/common.hpp"

#include <thread>

namespace localsearchsolver
{

enum class ParentSelection
{
    Random,
    BinaryTournament,
};

template <typename LocalScheme>
using GeneticLocalSearchCallback = std::function<void(const typename LocalScheme::Solution&)>;

template <typename LocalScheme>
struct GeneticLocalSearchOptionalParameters
{
    typedef typename LocalScheme::Solution Solution;
    typedef typename LocalScheme::GlobalCost GlobalCost;

    /** Number of threads. */
    Counter number_of_threads = 1;
    /** Maximum number of genetic iterations. */
    Counter maximum_number_of_iterations = -1;
    /** Maximum size of the population. */
    Counter maximum_size_of_the_population = 10;
    /** Parent selection. */
    ParentSelection parent_selection = ParentSelection::Random;
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
    GeneticLocalSearchCallback<LocalScheme> new_solution_callback
        = [](const Solution&) { };

    optimizationtools::Info info;
};

template <typename LocalScheme>
struct GeneticLocalSearchOutput
{
    /** Constructor. */
    GeneticLocalSearchOutput(
            const LocalScheme& local_scheme,
            Counter maximum_size_of_the_solution_pool):
        solution_pool(local_scheme, maximum_size_of_the_solution_pool) { }

    /** Solution pool. */
    SolutionPool<LocalScheme> solution_pool;
    /** Number of genetic iterations. */
    Counter number_of_iterations = 0;
};

template <typename LocalScheme>
inline GeneticLocalSearchOutput<LocalScheme> genetic_local_search(
        LocalScheme& local_scheme,
        GeneticLocalSearchOptionalParameters<LocalScheme> parameters = {});

///////////////////////////////////////////////////////////////////////////////
/////////////////////////// Template implementations //////////////////////////
///////////////////////////////////////////////////////////////////////////////

template <typename LocalScheme>
class Population
{
    typedef typename LocalScheme::Solution Solution;
    typedef typename LocalScheme::GlobalCost GlobalCost;

    struct PopulationSolution
    {
        Solution solution;
        double diversity = std::numeric_limits<double>::infinity();
        Counter diversity_rank = -1;
        Counter global_cost_rank = -1;
        Counter rank = -1;
    };

public:

    /** Constructor. */
    Population(const LocalScheme& local_scheme, Counter maximum_size_of_the_population):
        local_scheme_(local_scheme),
        maximum_size_of_the_population_(maximum_size_of_the_population)
    { }

    /** Destructor. */
    virtual ~Population() { }

    /** Return the current number of solutions in the solution pool. */
    Counter size() const { return solutions_.size(); }

    std::pair<Solution, Solution> get_parents_random(
            std::mt19937_64& generator)
    {
        // Draw 2 random solutions.
        auto solution_ids = optimizationtools::bob_floyd(
                (Counter)2, size(), generator);
        return {
            solutions_[solution_ids[0]].solution,
            solutions_[solution_ids[1]].solution};
    }

    std::pair<Solution, Solution> get_parents_binary_tournament(
            std::mt19937_64& generator)
    {
        // Draw 4 random solutions.
        auto solution_ids = optimizationtools::bob_floyd(
                (Counter)4, size(), generator);
        std::shuffle(solution_ids.begin(), solution_ids.end(), generator);

        // Compute solution_id_1.
        Counter solution_id_1 = -1;
        if (solutions_[solution_ids[0]].rank
                < solutions_[solution_ids[1]].rank) {
            solution_id_1 = solution_ids[0];
        } else {
            solution_id_1 = solution_ids[1];
        }

        // Compute solution_id_2.
        Counter solution_id_2 = -1;
        if (solutions_[solution_ids[2]].rank
                < solutions_[solution_ids[3]].rank) {
            solution_id_2 = solution_ids[2];
        } else {
            solution_id_2 = solution_ids[3];
        }

        return {
            solutions_[solution_id_1].solution,
            solutions_[solution_id_2].solution};
    }

    /**
     * Return a pair of distinct solutions to use as parents for a crossover
     * operator.
     */
    std::pair<Solution, Solution> get_parents(
            ParentSelection parent_selection,
            std::mt19937_64& generator)
    {
        switch (parent_selection) {
        case ParentSelection::Random:
            return get_parents_random(generator);
        case ParentSelection::BinaryTournament:
            return get_parents_binary_tournament(generator);
        }
        return get_parents_random(generator);
    }

    /**
     * Add a solution to the population.
     *
     * If the solution is already in the population, it is not added again.
     *
     * If the size of the population exceeds the maximum size of the
     * population, then the worst solution is removed from the population.
     */
    void add(const Solution& solution, std::mt19937_64& generator)
    {
        // Check if the solution is already in the population.
        for (Counter solution_id = 0; solution_id < size(); ++solution_id) {
            const Solution& solution_2 = solutions_[solution_id].solution;
            if (local_scheme_.distance(solution, solution_2) == 0) {
                //std::cout << "New solution is identical to solution " << solution_id << "." << std::endl;
                return;
            }
        }

        // Add the new solution to the population.
        PopulationSolution population_solution;
        population_solution.solution = solution;
        //std::cout << "Add new solution." << std::endl;
        solutions_.push_back(population_solution);
        update_scores(generator);

        // If the maximum population size is exceeded, remove the worst
        // solution.
        if (size() > maximum_size_of_the_population_) {
            Counter solution_id_worse = -1;
            for (Counter solution_id = 0; solution_id < size(); ++solution_id)
                if (solutions_[solution_id].rank == size() - 1)
                    solution_id_worse = solution_id;
            //std::cout << "Remove solution " << solution_id_worse << "." << std::endl;
            solutions_[solution_id_worse] = solutions_.back();
            solutions_.pop_back();
            update_scores(generator);
        }
    }

    void print()
    {
        for (Counter solution_id = 0; solution_id < size(); ++solution_id) {
            const PopulationSolution& solution = solutions_[solution_id];
            std::cout << "Solution " << solution_id << ":"
                << " cost " << to_string(local_scheme_.global_cost(solution.solution))
                << "; cost rank " << solution.global_cost_rank
                << "; diversity: " << solution.diversity
                << "; diversity rank: " << solution.diversity_rank
                << "; rank: " << solution.rank
                << std::endl;
        }
    }

private:

    /*
     * Private methods.
     */

    /**
     * Update the scores of the solutions of the population.
     *
     * This method should be called each time the population is modified (when
     * a solution is added or removed) since it affects these values.
     */
    void update_scores(std::mt19937_64& generator)
    {
        // Compute diversities.
        for (Counter solution_id = 0; solution_id < size(); ++solution_id) {
            const Solution& solution = solutions_[solution_id].solution;
            solutions_[solution_id].diversity = std::numeric_limits<double>::infinity();
            for (Counter solution_id_2 = 0; solution_id_2 < size(); ++solution_id_2) {
                if (solution_id_2 == solution_id)
                    continue;
                const Solution& solution_2 = solutions_[solution_id_2].solution;
                double d = local_scheme_.distance(solution, solution_2);
                if (solutions_[solution_id].diversity > d)
                    solutions_[solution_id].diversity = d;
            }
        }

        // Compute diversity_ranks.
        std::vector<Counter> diversity_ranks(size());
        std::iota(diversity_ranks.begin(), diversity_ranks.end(), 0);
        std::shuffle(diversity_ranks.begin(), diversity_ranks.end(), generator);
        sort(
                diversity_ranks.begin(), diversity_ranks.end(),
                [this](Counter solution_id_1, Counter solution_id_2) -> bool
                {
                    return solutions_[solution_id_1].diversity
                            > solutions_[solution_id_2].diversity;
                });
        for (Counter pos = 0; pos < size(); ++pos)
            solutions_[diversity_ranks[pos]].diversity_rank = pos;

        // Compute global_cost_ranks.
        std::vector<Counter> global_cost_ranks(size());
        std::iota(global_cost_ranks.begin(), global_cost_ranks.end(), 0);
        std::shuffle(global_cost_ranks.begin(), global_cost_ranks.end(), generator);
        sort(
                global_cost_ranks.begin(), global_cost_ranks.end(),
                [this](Counter solution_id_1, Counter solution_id_2) -> bool
                {
                    return local_scheme_.global_cost(solutions_[solution_id_1].solution)
                            < local_scheme_.global_cost(solutions_[solution_id_2].solution);
                });
        for (Counter pos = 0; pos < size(); ++pos)
            solutions_[global_cost_ranks[pos]].global_cost_rank = pos;

        // Compute ranks.
        std::vector<Counter> ranks(size());
        std::iota(ranks.begin(), ranks.end(), 0);
        std::shuffle(ranks.begin(), ranks.end(), generator);
        sort(
                ranks.begin(), ranks.end(),
                [this](Counter solution_id_1, Counter solution_id_2) -> bool
                {
                    return solutions_[solution_id_1].diversity_rank
                            + solutions_[solution_id_1].global_cost_rank
                            < solutions_[solution_id_2].diversity_rank
                            + solutions_[solution_id_2].global_cost_rank;
                });
        for (Counter pos = 0; pos < size(); ++pos)
            solutions_[ranks[pos]].rank = pos;
        //print();
    }

    /*
     * Private attributes.
     */

    /** LocalScheme. */
    const LocalScheme& local_scheme_;

    /** Maximum size of the population. */
    Counter maximum_size_of_the_population_ = -1;

    /** Set of solutions. */
    std::vector<PopulationSolution> solutions_;

};

template <typename LocalScheme>
struct GeneticLocalSearchData
{
    GeneticLocalSearchData(
            LocalScheme& local_scheme,
            GeneticLocalSearchOptionalParameters<LocalScheme>& parameters,
            GeneticLocalSearchOutput<LocalScheme>& output):
        local_scheme(local_scheme),
        parameters(parameters),
        population(local_scheme, parameters.maximum_size_of_the_population),
        output(output)
        {  }

    /** Local scheme. */
    LocalScheme& local_scheme;
    /** Genetic Local Search optional parameters. */
    GeneticLocalSearchOptionalParameters<LocalScheme>& parameters;
    /** Population. */
    Population<LocalScheme> population;
    /** Genetic Local Search output structure. */
    GeneticLocalSearchOutput<LocalScheme>& output;

    /** Position storing which is the next initial solution to generate/add. */
    Counter initial_solution_pos = 0;
    /** Mutex to use when manipulating the structure. */
    std::mutex mutex;
};

template <typename LocalScheme>
inline void genetic_local_search_worker(
        GeneticLocalSearchData<LocalScheme>& data,
        Counter thread_id)
{
    LocalScheme local_scheme(data.local_scheme);
    std::mt19937_64 generator(data.parameters.seed + thread_id);
    Counter number_of_initial_solutions
        = (Counter)data.parameters.initial_solution_ids.size()
        + (Counter)data.parameters.initial_solutions.size();

    // Generate initial solutions.
    for (;;) {

        // Check end.
        if (data.parameters.info.needs_to_end())
            break;

        // Check cutoff.
        if (local_scheme.global_cost(data.output.solution_pool.best())
                <= data.parameters.cutoff)
            break;

        data.mutex.lock();
        // No more initial solutions to generate.
        if (data.initial_solution_pos >= (Counter)data.parameters.maximum_size_of_the_population) {
            data.mutex.unlock();
            break;
        }
        Counter initial_solution_pos = data.initial_solution_pos % number_of_initial_solutions;
        data.initial_solution_pos++;
        data.mutex.unlock();

        // Generate initial solution.
        auto solution = (initial_solution_pos < (Counter)data.parameters.initial_solution_ids.size())?
            local_scheme.initial_solution(data.parameters.initial_solution_ids[initial_solution_pos], generator):
            data.parameters.initial_solutions[initial_solution_pos - (Counter)data.parameters.initial_solution_ids.size()];
        // Run A* Local Search.
        local_scheme.local_search(solution, generator);
        //std::cout << to_string(local_scheme.global_cost(solution)) << std::endl;

        // Lock mutex since we will modify the shared structure.
        data.mutex.lock();
        // Add the new solution to the population.
        data.population.add(solution, generator);
        // Check for a new best solution.
        if (local_scheme.global_cost(data.output.solution_pool.worst())
                > local_scheme.global_cost(solution)) {
            std::stringstream ss;
            ss << "initial solution " << initial_solution_pos
                << " (thread " << thread_id << ")";
            auto res = data.output.solution_pool.add(solution, ss, data.parameters.info);
            if (res == 2) {
                data.output.solution_pool.display(ss, data.parameters.info);
                data.parameters.new_solution_callback(solution);
            }
        }
        // Unlock mutex.
        data.mutex.unlock();
    }

    for (;;) {

        // Check end.
        if (data.parameters.info.needs_to_end())
            break;

        // Check cutoff.
        if (local_scheme.global_cost(data.output.solution_pool.best())
                <= data.parameters.cutoff)
            break;

        data.mutex.lock();

        // Check genetic iteration limit.
        if (data.parameters.maximum_number_of_iterations != -1
                && data.output.number_of_iterations
                >= data.parameters.maximum_number_of_iterations) {
            data.mutex.unlock();
            return;
        }

        // We need at least two solutions.
        if (data.population.size() < 4) {
            data.mutex.unlock();
            continue;
        }

        Counter number_of_iterations = data.output.number_of_iterations;
        data.output.number_of_iterations++;

        // Draw parent solutions.
        auto p = data.population.get_parents(
                data.parameters.parent_selection,
                generator);
        const auto& solution_parent_1 = p.first;
        const auto& solution_parent_2 = p.second;

        data.mutex.unlock();

        // Crossover.
        auto solution = local_scheme.crossover(
                solution_parent_1, solution_parent_2, generator);
        // Run Local Search.
        local_scheme.local_search(solution, generator);

        // Lock mutex since we will modify the shared structure.
        data.mutex.lock();
        // Add the new solution to the population.
        data.population.add(solution, generator);
        // Check for a new best solution.
        if (local_scheme.global_cost(data.output.solution_pool.worst())
                > local_scheme.global_cost(solution)) {
            std::stringstream ss;
            ss << "iteration " << number_of_iterations
                << " (thread " << thread_id << ")";
            int res = data.output.solution_pool.add(solution, ss, data.parameters.info);
            if (res == 2) {
                data.output.solution_pool.display(ss, data.parameters.info);
                data.parameters.new_solution_callback(solution);
            }
        }
        // Unlock mutex.
        data.mutex.unlock();
    }

}

template <typename LocalScheme>
inline GeneticLocalSearchOutput<LocalScheme> genetic_local_search(
        LocalScheme& local_scheme,
        GeneticLocalSearchOptionalParameters<LocalScheme> parameters)
{
    // Initial display.
    VER(parameters.info,
               "=======================================" << std::endl
            << "          Local Search Solver          " << std::endl
            << "=======================================" << std::endl
            << std::endl
            << "Algorithm" << std::endl
            << "---------" << std::endl
            << "Genetic Local Search" << std::endl
            << std::endl
            << "Parameters" << std::endl
            << "----------" << std::endl
            << "Maximum size of the population:  " << parameters.maximum_size_of_the_population << std::endl
            << "Maximum number of iterations:    " << parameters.maximum_number_of_iterations << std::endl
            << "Seed:                            " << parameters.seed << std::endl
            << "Maximum size of the pool:        " << parameters.maximum_size_of_the_solution_pool << std::endl
            << "Time limit:                      " << parameters.info.time_limit << std::endl
            << std::endl
       );

    GeneticLocalSearchOutput<LocalScheme> output(
            local_scheme,
            parameters.maximum_size_of_the_solution_pool);
    output.solution_pool.display_init(parameters.info);
    std::vector<std::thread> threads;
    GeneticLocalSearchData<LocalScheme> data(local_scheme, parameters, output);
    for (Counter thread_id = 0; thread_id < parameters.number_of_threads; ++thread_id) {
        threads.push_back(std::thread(
                    genetic_local_search_worker<LocalScheme>,
                    std::ref(data),
                    thread_id));
    }
    for (Counter thread_id = 0; thread_id < (Counter)threads.size(); ++thread_id)
        threads[thread_id].join();

    output.solution_pool.display_end(parameters.info);
    VER(parameters.info, "Number of iterations:       " << output.number_of_iterations << std::endl);
    PUT(parameters.info, "Algorithm", "NumberOfIterations", output.number_of_iterations);
    return output;
}

}

