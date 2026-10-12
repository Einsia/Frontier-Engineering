#pragma once

/**
 * ROADEF/EURO Challenge 2020: Maintenance Planning Problem.
 *
 * Problem description:
 * See https://github.com/fontanf/orproblems/blob/main/orproblems/roadef2020.hpp
 *
 * TODO
 *
 */

#include "localsearchsolver/common.hpp"

#include "orproblems/roadef2020.hpp"

namespace localsearchsolver
{

namespace roadef2020
{

using namespace orproblems::roadef2020;

class LocalScheme
{

public:

    /** Global cost: <Number of interventions, Number of conflicts, Overwork, Underwork, Cost>; */
    using GlobalCost = std::tuple<InterventionId, ExclusionId, Workload, Workload, Cost>;

    inline InterventionId&       number_of_interventions(GlobalCost& global_cost) { return std::get<0>(global_cost); }
    inline ExclusionId&              number_of_conflicts(GlobalCost& global_cost) { return std::get<1>(global_cost); }
    inline Workload&                            overwork(GlobalCost& global_cost) { return std::get<2>(global_cost); }
    inline Workload&                           underwork(GlobalCost& global_cost) { return std::get<3>(global_cost); }
    inline Cost&                                    cost(GlobalCost& global_cost) { return std::get<4>(global_cost); }
    inline InterventionId  number_of_interventions(const GlobalCost& global_cost) { return std::get<0>(global_cost); }
    inline ExclusionId         number_of_conflicts(const GlobalCost& global_cost) { return std::get<1>(global_cost); }
    inline Workload                       overwork(const GlobalCost& global_cost) { return std::get<2>(global_cost); }
    inline Workload                      underwork(const GlobalCost& global_cost) { return std::get<3>(global_cost); }
    inline Cost                               cost(const GlobalCost& global_cost) { return std::get<4>(global_cost); }

    /*
     * Solutions.
     */

    using CompactSolution = std::vector<Time>;

    struct CompactSolutionHasher
    {
        std::hash<Time> hasher;

        inline bool operator()(
                const std::shared_ptr<CompactSolution>& compact_solution_1,
                const std::shared_ptr<CompactSolution>& compact_solution_2) const
        {
            return *compact_solution_1 == *compact_solution_2;
        }

        inline std::size_t operator()(
                const std::shared_ptr<CompactSolution>& compact_solution) const
        {
            size_t hash = 0;
            for (Time t: *compact_solution)
                optimizationtools::hash_combine(hash, hasher(t));
            return hash;
        }
    };

    inline CompactSolutionHasher compact_solution_hasher() const { return CompactSolutionHasher(); }

    struct SolutionTimeStep
    {
        /** Workload for each resource, workloads[r]. */
        std::vector<Workload> workloads;
        /** Risk for each scenario, risks[scenario]. */
        std::vector<Risk> risks;
        /** Scenarios sorted by risk. */
        std::vector<ScenarioId> sorted_scenarios;
        /** Sum of risks of all scenarios. */
        Risk risk_sum = 0;
    };

    struct SolutionConflict
    {
        InterventionId j1 = -1;
        InterventionId j2 = -1;
        Time t_cur = -1;
    };

    struct Solution
    {
        /** Number of interventions. */
        InterventionId number_of_interventions = 0;
        /** Start date for each intervention, -1 if not in solution. */
        std::vector<Time> intervention_starts;
        /** Informations for each time step. */
        std::vector<SolutionTimeStep> time_steps;
        /** List of pair of interventions in conflict. */
        std::vector<SolutionConflict> conflicts;
        /** Mean cost. */
        Cost mean_cost = 0;
        /** Expected excess. */
        Cost expected_excess = 0;
        /** Underwork. */
        Workload underwork = 0;
        /** Overwork. */
        Workload overwork = 0;
    };

    CompactSolution solution2compact(const Solution& solution)
    {
        return solution.intervention_starts;
    }

    Solution compact2solution(const CompactSolution& compact_solution)
    {
        auto solution = empty_solution();
        for (InterventionId j = 0; j < instance_.number_of_interventions(); ++j)
            if (compact_solution[j] != -1)
                add(solution, j, compact_solution[j]);
        return solution;
    }

    /*
     * Constructors and destructor.
     */

    struct Parameters
    {
    };

    LocalScheme(
            const Instance& instance,
            Parameters parameters):
        instance_(instance),
        parameters_(parameters),
        interventions_(instance.number_of_interventions()),
        times_(instance.horizon())
    {
        // Initialize interventions_.
        std::iota(interventions_.begin(), interventions_.end(), 0);
        // Initialize times_.
        std::iota(times_.begin(), times_.end(), 0);
        // Initialize risks_ and sorted_scenarios_.
        ScenarioId s_max = 0;
        for (Time t_cur = 0; t_cur < instance.horizon(); ++t_cur)
            if (s_max < instance_.number_of_scenarios(t_cur))
                s_max = instance_.number_of_scenarios(t_cur);
        risks_.resize(s_max, 0);
        sorted_scenarios_.resize(s_max, 0);
    }

    LocalScheme(const LocalScheme& local_scheme):
        LocalScheme(local_scheme.instance_, local_scheme.parameters_) { }

    virtual ~LocalScheme() { }

    /*
     * Initial solutions.
     */

    Solution empty_solution() const;

    Solution initial_solution(
            Counter initial_solution_id,
            std::mt19937_64& generator);

    /*
     * Solution properties.
     */

    inline double real_cost(const Solution& solution) const
    {
        return (double)cost(solution)
            / instance_.horizon()
            / instance_.least_common_multiple()
            / instance_.alpha_multiplier()
            / instance_.risk_multiplier();
    }

    inline bool feasible(const Solution& solution) const
    {
        return (solution.number_of_interventions == instance_.number_of_interventions()
                && solution.conflicts.size() == 0
                && solution.overwork == 0
                && solution.underwork == 0);
    }

    inline GlobalCost global_cost(const Solution& solution) const
    {
        return {
            -solution.number_of_interventions,
            solution.conflicts.size(),
            solution.overwork,
            solution.underwork,
            cost(solution),
        };
    }

    /*
     * Local search.
     */

    struct Move
    {
        Move(): j(-1), t_start(-1), global_cost(worst<GlobalCost>()) { }

        InterventionId j;
        Time t_start;
        GlobalCost global_cost;
    };

    struct MoveHasher
    {
        std::hash<InterventionId> hasher_1;
        std::hash<Time> hasher_2;

        inline bool hashable(const Move&) const { return true; }

        inline bool operator()(
                const Move& move_1,
                const Move& move_2) const
        {
            return move_1.j == move_2.j && move_1.t_start == move_2.t_start;
        }

        inline std::size_t operator()(
                const Move& move) const
        {
            size_t hash = hasher_1(move.j);
            optimizationtools::hash_combine(hash, hasher_2(move.t_start));
            return hash;
        }
    };

    inline MoveHasher move_hasher() const { return MoveHasher(); }

    std::vector<Move> perturbations(
            Solution& solution,
            std::mt19937_64&);

    inline void apply_move(Solution& solution, const Move& move) const
    {
        remove(solution, move.j);
        add(solution, move.j, move.t_start);
    }

    void local_search(
            Solution& solution,
            std::mt19937_64& generator,
            const Move& tabu = Move());

    /*
     * Outputs.
     */

    std::ostream& print(
            std::ostream &os,
            const Solution& solution)
    {
        for (InterventionId j = 0; j < instance_.number_of_interventions(); ++j) {
            os << "j " << j << " t_start " << solution.intervention_starts[j] << std::endl;
        }
        for (Time t_cur = 0; t_cur < instance_.horizon(); ++t_cur) {
            os << "t " << t_cur;
            for (ResourceId r = 0; r < instance_.number_of_resources(); ++r)
                os << " " << solution.time_steps[t_cur].workloads[r] << "/" << instance_.workload_max(r, t_cur);
            os << std::endl;
        }
        return os;
    }

    inline void write(
            const Solution& solution,
            std::string filepath) const
    {
        if (filepath.empty())
            return;
        std::ofstream cert(filepath);
        if (!cert.good()) {
            std::cerr << "\033[31m" << "ERROR, unable to open file \"" << filepath << "\"" << "\033[0m" << std::endl;
            return;
        }

        for (InterventionId j = 0; j < instance_.number_of_interventions(); ++j)
            cert << instance_.intervention_name(j)
                << " " << solution.intervention_starts[j] + 1 << std::endl;
    }

private:

    /*
     * Manipulate solutions.
     */

    inline double cost(const Solution& solution) const
    {
        return (instance_.alpha_1() * solution.mean_cost
                + instance_.alpha_2() * solution.expected_excess);
    }

    void add(Solution& solution, InterventionId j, Time t_start) const;

    void remove(Solution& solution, InterventionId j) const;

    /*
     * Evaluate moves.
     */

    GlobalCost cost_add(
            const Solution& solution,
            InterventionId j,
            Time t_start,
            const GlobalCost& cutoff);

    /*
     * Private attributes.
     */

    const Instance& instance_;
    Parameters parameters_;

    /*
     * Temporary structures.
     */

    std::vector<InterventionId> interventions_;
    std::vector<Time> times_;
    std::vector<Risk> risks_;
    std::vector<ScenarioId> sorted_scenarios_;

};

}

}
