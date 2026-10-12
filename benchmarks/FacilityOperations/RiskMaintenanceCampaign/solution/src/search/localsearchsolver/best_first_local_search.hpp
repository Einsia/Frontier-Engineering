#pragma once

#include "localsearchsolver/common.hpp"

#include <unordered_set>
#include <thread>

namespace localsearchsolver
{

template <typename LocalScheme>
using BestFirstLocalSearchCallback = std::function<void(const typename LocalScheme::Solution&)>;

template <typename LocalScheme>
struct BestFirstLocalSearchOptionalParameters
{
    typedef typename LocalScheme::Solution Solution;
    typedef typename LocalScheme::GlobalCost GlobalCost;

    /** Maximum number of nodes. */
    Counter maximum_number_of_nodes = -1;
    /** Number of threads running the algorithm independently in parallel. */
    Counter number_of_threads_1 = 1;
    /** Number of threads running on the same node pool in parallel. */
    Counter number_of_threads_2 = 1;
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
    BestFirstLocalSearchCallback<LocalScheme> new_solution_callback
        = [](const Solution& solution) { (void)solution; };
    /** Info structure. */
    optimizationtools::Info info;
};

template <typename LocalScheme>
struct BestFirstLocalSearchOutput
{
    /** Constructor. */
    BestFirstLocalSearchOutput(
            const LocalScheme& local_scheme,
            Counter maximum_size_of_the_solution_pool):
        solution_pool(local_scheme, maximum_size_of_the_solution_pool) { }

    /** Solution pool. */
    SolutionPool<LocalScheme> solution_pool;
};

template <typename LocalScheme>
inline BestFirstLocalSearchOutput<LocalScheme> best_first_local_search(
        LocalScheme& local_scheme,
        BestFirstLocalSearchOptionalParameters<LocalScheme> parameters = {});

///////////////////////////////////////////////////////////////////////////////
/////////////////////////// Template implementations //////////////////////////
///////////////////////////////////////////////////////////////////////////////

template <typename LocalScheme>
struct BestFirstLocalSearchNode
{
    typedef typename LocalScheme::CompactSolution CompactSolution;
    typedef typename LocalScheme::Move Move;

    std::shared_ptr<CompactSolution> compact_solution;
    std::vector<Move> perturbations;
    Counter id = -1;
    Counter depth;
    Counter next_child_pos = 0;
    Counter child_id;
};

template <typename LocalScheme>
struct BestFirstLocalSearchNodeComparator
{
    BestFirstLocalSearchNodeComparator(const LocalScheme& branching_scheme):
        branching_scheme(branching_scheme) {  }

    const LocalScheme& branching_scheme;

    bool operator()(
            const std::shared_ptr<BestFirstLocalSearchNode<LocalScheme>>& node_1,
            const std::shared_ptr<BestFirstLocalSearchNode<LocalScheme>>& node_2) const {
        if (node_1->perturbations.back().global_cost
            != node_2->perturbations.back().global_cost)
            return node_1->perturbations.back().global_cost
                < node_2->perturbations.back().global_cost;
        return node_1->id < node_2->id;
    }
};

template <typename LocalScheme>
using CompactSolutionSet = std::unordered_set<
        std::shared_ptr<typename LocalScheme::CompactSolution>,
        typename LocalScheme::CompactSolutionHasher&,
        typename LocalScheme::CompactSolutionHasher&>;

template <typename LocalScheme>
using NodeSet = std::multiset<
        std::shared_ptr<BestFirstLocalSearchNode<LocalScheme>>,
        const BestFirstLocalSearchNodeComparator<LocalScheme>&>;

template <typename LocalScheme>
using MoveMap = std::unordered_map<
        typename LocalScheme::Move,
        Counter,
        typename LocalScheme::MoveHasher&,
        typename LocalScheme::MoveHasher&>;

template <typename LocalScheme>
struct BestFirstLocalSearchData
{
    typedef typename LocalScheme::CompactSolutionHasher CompactSolutionHasher;
    typedef typename LocalScheme::MoveHasher MoveHasher;
    typedef typename LocalScheme::Move Move;

    BestFirstLocalSearchData(
            LocalScheme& local_scheme,
            BestFirstLocalSearchOptionalParameters<LocalScheme>& parameters,
            BestFirstLocalSearchOutput<LocalScheme>& output):
        local_scheme(local_scheme),
        parameters(parameters),
        output(output),
        compact_solution_hasher(local_scheme.compact_solution_hasher()),
        history{0, compact_solution_hasher, compact_solution_hasher},
        q(local_scheme),
        move_hasher(local_scheme.move_hasher()),
        move_nodes{0, move_hasher, move_hasher}
        {  }

    LocalScheme& local_scheme;
    BestFirstLocalSearchOptionalParameters<LocalScheme>& parameters;
    BestFirstLocalSearchOutput<LocalScheme>& output;
    CompactSolutionHasher compact_solution_hasher;
    CompactSolutionSet<LocalScheme> history;
    NodeSet<LocalScheme> q;
    Counter number_of_working_threads = 0;
    Counter initial_solution_pos = 0;
    Counter number_of_perturbations = -1;

    MoveHasher move_hasher;

    /**
     * move_nodes[move] is last node at which move "move" has been used as a
     * perturbation.
     */
    MoveMap<LocalScheme> move_nodes;

    /**
     * tabu_nodes[number_of_nodes] is a vector a nodes which are currently tabu
     * and should be released at node "number_of_nodes".
     */
    std::unordered_map<Counter, std::vector<std::shared_ptr<BestFirstLocalSearchNode<LocalScheme>>>> tabu_nodes;

    /** Number of nodes explored. */
    Counter number_of_nodes = 0;

    std::mutex mutex;
};

template <typename LocalScheme>
std::vector<typename LocalScheme::Move> update_children(
        LocalScheme& local_scheme,
        typename LocalScheme::Solution& solution,
        std::mt19937_64& generator,
        Counter next_child_pos = 0)
{
    typedef typename LocalScheme::Move Move;

    auto move_compare = [](const Move& move_1, const Move& move_2) -> bool
    {
        return move_1.global_cost < move_2.global_cost;
    };

    // Get perturbation moves.
    auto moves_0 = local_scheme.perturbations(solution, generator);
    if (next_child_pos >= (Counter)moves_0.size())
        return {};
    // Sort moves.
    std::sort(moves_0.begin(), moves_0.end(), move_compare);
    std::vector<Move> moves;
    for (auto it = moves_0.begin() + next_child_pos;
            it != moves_0.end() && it != moves_0.begin() + next_child_pos + 1024;
            ++it)
        moves.push_back(*it);
    std::reverse(moves.begin(), moves.end());
    return moves;
}

template <typename LocalScheme>
inline void best_first_local_search_worker(
        BestFirstLocalSearchData<LocalScheme>& data,
        Counter thread_id)
{
    typedef typename LocalScheme::CompactSolution CompactSolution;
    //std::cout << "best_first_local_search_worker start" << std::endl;

    LocalScheme local_scheme(data.local_scheme);
    Seed seed = data.parameters.seed + thread_id;
    std::mt19937_64 generator(seed);

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
        // Store initial_solution_pos to use it after releasing the mutex.
        Counter initial_solution_pos = data.initial_solution_pos;
        // No more initial solutions to generate.
        if (initial_solution_pos
                >= (Counter)data.parameters.initial_solution_ids.size()
                + (Counter)data.parameters.initial_solutions.size()) {
            data.mutex.unlock();
            break;
        }
        data.initial_solution_pos++;
        data.number_of_working_threads++;
        data.mutex.unlock();

        auto solution = (initial_solution_pos < (Counter)data.parameters.initial_solution_ids.size())?
            local_scheme.initial_solution(data.parameters.initial_solution_ids[initial_solution_pos], generator):
            data.parameters.initial_solutions[initial_solution_pos - (Counter)data.parameters.initial_solution_ids.size()];
        local_scheme.local_search(solution, generator);

        // Check for a new best solution.
        if (data.output.solution_pool.size() == 0
                || local_scheme.global_cost(data.output.solution_pool.worst())
                > local_scheme.global_cost(solution)) {
            std::stringstream ss;
            ss << "s" << initial_solution_pos
                << " (t" << thread_id << ")";
            int res = data.output.solution_pool.add(solution, ss, data.parameters.info);
            if (res == 2) {
                data.output.solution_pool.display(ss, data.parameters.info);
                data.parameters.new_solution_callback(solution);
            }
        }

        // Get perturbation moves.
        auto moves = update_children(local_scheme, solution, generator);
        auto compact_solution = std::shared_ptr<CompactSolution>(
                new CompactSolution(local_scheme.solution2compact(solution)));

        data.mutex.lock();
        if (data.number_of_perturbations == -1)
            data.number_of_perturbations = local_scheme.perturbations(solution, generator).size();
        if (data.history.find(compact_solution) == data.history.end()
                && moves.size() > 0) {
            BestFirstLocalSearchNode<LocalScheme> root;
            root.id = -1;
            root.compact_solution = compact_solution;
            root.perturbations = moves;
            root.child_id = 0;
            root.depth = 1;
            data.history.insert(compact_solution);
            data.q.insert(std::shared_ptr<BestFirstLocalSearchNode<LocalScheme>>(
                        new BestFirstLocalSearchNode<LocalScheme>(root)));
        }
        data.number_of_working_threads--;
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

        // Check node limit.
        if (data.parameters.maximum_number_of_nodes != -1
                && data.number_of_nodes >= data.parameters.maximum_number_of_nodes) {
            data.mutex.unlock();
            return;
        }

        Counter node_id = data.number_of_nodes;
        data.number_of_nodes++;

        // Compute tabu tenure.
        Counter tabu_tenure = -1;
        if (node_id < data.number_of_perturbations) {
            tabu_tenure = data.number_of_perturbations / 10;
        } else if (node_id < 10 * data.number_of_perturbations) {
            tabu_tenure = data.number_of_perturbations / 2;
        } else {
            tabu_tenure = data.number_of_perturbations;
        }

        // Add back nodes which are not tabu anymore.
        if (data.tabu_nodes.find(node_id) != data.tabu_nodes.end()) {
            for (auto node: data.tabu_nodes[node_id])
                data.q.insert(node);
            data.tabu_nodes.erase(node_id);
        }

        // Check for algorithm end.
        if (data.q.empty() && data.number_of_working_threads == 0) {
            data.mutex.unlock();
            break;
        }

        // Check cutoff.
        if (local_scheme.global_cost(data.output.solution_pool.best())
                    <= data.parameters.cutoff)
            break;

        if (data.q.empty()) {
            data.mutex.unlock();
            continue;
        }

        // Draw next node from the queue.
        auto node_cur = *data.q.begin();
        data.q.erase(data.q.begin());
        auto move = node_cur->perturbations.back();
        // Check if the perturbation is tabu.
        while (data.move_hasher.hashable(move)
                && data.move_nodes.find(move) != data.move_nodes.end()
                && data.move_nodes[move] > node_id - tabu_tenure) {
            // Add a new node for this perturbation to the tabu node set.
            BestFirstLocalSearchNode<LocalScheme> node_tmp;
            node_tmp.compact_solution = node_cur->compact_solution;
            node_tmp.perturbations = {move};
            node_tmp.id = node_cur->id;
            node_tmp.depth = node_cur->depth;
            node_tmp.child_id = node_cur->child_id;
            node_tmp.next_child_pos = -1;
            if (data.tabu_nodes.find(data.move_nodes[move] + tabu_tenure) == data.tabu_nodes.end())
                data.tabu_nodes[data.move_nodes[move] + tabu_tenure] = {};
            data.tabu_nodes[data.move_nodes[move] + tabu_tenure].push_back(
                    std::shared_ptr<BestFirstLocalSearchNode<LocalScheme>>(
                        new BestFirstLocalSearchNode<LocalScheme>(node_tmp)));

            // Remove the perturbation from the father's children.
            node_cur->perturbations.pop_back();
            if (node_cur->next_child_pos != -1) {
                node_cur->next_child_pos++;
                if (node_cur->perturbations.empty()) {
                    auto solution_tmp = local_scheme.compact2solution(*node_cur->compact_solution);
                    node_cur->perturbations = update_children(
                            local_scheme,
                            solution_tmp,
                            generator,
                            node_cur->next_child_pos);
                }
            }
            if (!node_cur->perturbations.empty())
                data.q.insert(node_cur);

            node_cur = nullptr;
            if (data.q.empty())
                break;

            node_cur = *data.q.begin();
            data.q.erase(data.q.begin());
            move = node_cur->perturbations.back();
        }
        if (node_cur == nullptr) {
            data.mutex.unlock();
            continue;
        }
        if (data.move_hasher.hashable(move))
            data.move_nodes[move] = node_id;
        data.number_of_working_threads++;
        //std::cout << "node " << node_id
        //    << " depth " << node_cur->depth
        //    << " cost " << to_string(move.global_cost)
        //    << " thread " << thread_id
        //    << std::endl;
        data.mutex.unlock();

        auto solution = local_scheme.compact2solution(*node_cur->compact_solution);
        // Remove the perturbation from the father's children.
        node_cur->perturbations.pop_back();
        if (node_cur->next_child_pos != -1) {
            node_cur->next_child_pos++;
            if (node_cur->perturbations.empty())
                node_cur->perturbations = update_children(
                        local_scheme,
                        solution,
                        generator,
                        node_cur->next_child_pos);
        }
        // Apply perturbation and local search.
        local_scheme.apply_move(solution, move);
        local_scheme.local_search(solution, generator, move);

        // Check for a new best solution.
        if (data.output.solution_pool.size() == 0
                || local_scheme.global_cost(data.output.solution_pool.worst())
                > local_scheme.global_cost(solution)) {
            std::stringstream ss;
            ss << "n" << node_id
                << " d" << node_cur->depth
                << " c" << node_cur->next_child_pos - 1
                << " (t" << thread_id << ")";
            int res = data.output.solution_pool.add(solution, ss, data.parameters.info);
            if (res == 2) {
                data.output.solution_pool.display(ss, data.parameters.info);
                data.parameters.new_solution_callback(solution);
            }
        }

        // Get perturbation moves.
        auto moves = update_children(local_scheme, solution, generator);
        auto compact_solution = std::shared_ptr<CompactSolution>(
                    new CompactSolution(local_scheme.solution2compact(solution)));

        data.mutex.lock();

        if (data.history.find(compact_solution) == data.history.end()
                && !moves.empty()) {
            BestFirstLocalSearchNode<LocalScheme> child;
            child.compact_solution = compact_solution;
            child.perturbations = moves;
            child.id = node_id;
            child.depth = node_cur->depth + 1;
            child.child_id = node_cur->next_child_pos - 1;
            data.history.insert(compact_solution);
            data.q.insert(std::shared_ptr<BestFirstLocalSearchNode<LocalScheme>>(
                        new BestFirstLocalSearchNode<LocalScheme>(child)));
        }

        if (!node_cur->perturbations.empty())
            data.q.insert(node_cur);

        data.number_of_working_threads--;
        data.mutex.unlock();
    }
}

template <typename LocalScheme>
inline BestFirstLocalSearchOutput<LocalScheme> best_first_local_search(
        LocalScheme& local_scheme,
        BestFirstLocalSearchOptionalParameters<LocalScheme> parameters)
{
    // Initial display.
    VER(parameters.info, ""
            << "=======================================" << std::endl
            << "          Local Search Solver          " << std::endl
            << "=======================================" << std::endl
            << std::endl
            << "Algorithm" << std::endl
            << "---------" << std::endl
            << "Best First Local Search" << std::endl
            << std::endl
            << "Parameters" << std::endl
            << "----------" << std::endl
            << "Maximum number of nodes:     " << parameters.maximum_number_of_nodes << std::endl
            << "Seed:                        " << parameters.seed << std::endl
            << "Maximum size of the pool:    " << parameters.maximum_size_of_the_solution_pool << std::endl
            << "Time limit:                  " << parameters.info.time_limit << std::endl);
    print_local_scheme_parameters(local_scheme, parameters.info);
    VER(parameters.info, std::endl);


    //std::cout << "best_first_local_search start" << std::endl;
    BestFirstLocalSearchOutput<LocalScheme> output(
            local_scheme,
            parameters.maximum_size_of_the_solution_pool);
    output.solution_pool.display_init(parameters.info);
    std::vector<std::thread> threads;
    std::vector<std::shared_ptr<BestFirstLocalSearchData<LocalScheme>>> datas;
    Counter thread_id = 0;
    for (Counter thread_id_1 = 0; thread_id_1 < parameters.number_of_threads_1; ++thread_id_1) {
        datas.push_back(std::shared_ptr<BestFirstLocalSearchData<LocalScheme>>(
                    new BestFirstLocalSearchData<LocalScheme>(local_scheme, parameters, output)));
        for (Counter thread_id_2 = 0; thread_id_2 < parameters.number_of_threads_2; ++thread_id_2) {
            threads.push_back(std::thread(
                        best_first_local_search_worker<LocalScheme>,
                        std::ref(*datas[thread_id_1]),
                        thread_id));
            thread_id++;
        }
    }
    for (Counter thread_id = 0; thread_id < (Counter)threads.size(); ++thread_id)
        threads[thread_id].join();

    output.solution_pool.display_end(parameters.info);
    //VER(parameters.info, "Number of nodes:            " << output.number_of_nodes << std::endl);
    //PUT(parameters.info, "Algorithm", "NumberOfNodes", output.number_of_nodes);
    print_local_scheme_statistics(local_scheme, parameters.info);
    return output;
}

}

