#pragma once

/**
 * ROADEF/EURO Challenge 2020: Maintenance Planning Problem.
 *
 * Input:
 * - TODO
 * Problem:
 * - TODO
 * Objective:
 * - TODO
 *
 */

#include "optimizationtools/indexed_set.hpp"

#include <fstream>
#include <iostream>
#include <map>
#include <memory>

namespace orproblems
{

namespace roadef2020
{

using Cost = int64_t;
using SeasonId = int64_t;
using ScenarioId = int64_t;
using ResourceId = int64_t;
using ResourcePos = int64_t;
using InterventionId = int16_t;
using InterventionPos = int16_t;
using ExclusionId = int64_t;
using Time = int16_t;
using Workload = int64_t;
using Risk = int64_t;
using Counter = int64_t;

struct Exclusion
{
    InterventionId j1;
    InterventionId j2;
    SeasonId season;

    InterventionId j(InterventionId j_cur) const { return (j_cur == j1)? j2: j1; }
};

struct InterventionRisk
{
    Time t_first; // default: t_cur + 1
    std::vector<std::vector<Risk>> risks;
    std::vector<std::vector<double>> risks_double;

    inline Risk risk(Time t_start, ScenarioId s) const
    {
        if (t_start < t_first
                || t_start - t_first >= (Time)risks.size())
            return 0;
        return risks[t_start - t_first][s];
    }
};

struct InterventionResourceWorkload
{
    Time t_first = 0; // default: t_cur + 1
    std::vector<Workload> workloads;
    std::vector<double> workloads_double;

    inline Workload workload(Time t_start) const
    {
        if (t_start < t_first
                || t_start - t_first >= (Time)workloads.size())
            return 0;
        return workloads[t_start - t_first];
    }
};

struct InterventionResource
{
    ResourceId r;
    std::vector<InterventionResourceWorkload> workloads;

    inline Workload workload(Time t_cur, Time t_start) const
    {
        return workloads[t_cur].workload(t_start);
    }
};

struct Intervention
{
    std::string name;
    std::vector<Time> deltas;
    /** risk[t_cur]. */
    std::vector<InterventionRisk> risks;
    Time t_start_max;
    /** workloads[r_pos]. */
    std::vector<InterventionResource> resources;
    /** exclusions[season] = {j1, j2, ..., j3}. */
    std::vector<std::vector<ExclusionId>> exclusions;
    InterventionPos number_of_exclusions = 0;
    std::vector<int8_t> fixed_assignments;
    double duration_mean = 0;
    std::vector<double> workload_mean;
};

struct Resource
{
    std::string name;
    /* Minimum usage of the resource at time t. */
    std::vector<Workload> min;
    /* Maximum usage of the resource at time t. */
    std::vector<Workload> max;
    std::vector<double> min_double;
    std::vector<double> max_double;
    Workload multiplier = 1;
    std::vector<bool> unconstrained;
};

class Instance
{

public:

    Instance() { }

    /** Create instance from file. */
    Instance(std::string filepath, std::string format);

    /*
     * getters
     */

    inline double                            alpha() const { return alpha_; }
    inline double                         quantile() const { return quantile_; }
    inline Time                            horizon() const { return horizon_; }
    inline InterventionId  number_of_interventions() const { return interventions_.size(); }
    inline ResourceId          number_of_resources() const { return resources_.size(); }
    inline SeasonId              number_of_seasons() const { return season_strings_.size(); }
    inline ExclusionId        number_of_exclusions() const { return exclusions_.size(); }

    inline ScenarioId    least_common_multiple() const { return least_common_multiple_; }
    inline Risk                        alpha_1() const { return alpha_1_; }
    inline Risk                        alpha_2() const { return alpha_2_; }
    inline Risk               alpha_multiplier() const { return alpha_multiplier_; }
    inline Risk                risk_multiplier() const { return risk_multiplier_; }

    inline ScenarioId  number_of_scenarios(Time t) const { return number_of_scenarioss_[t]; }
    inline SeasonId             season(Time t) const { return (t < (Time)seasons_.size())? seasons_[t]: -1; }

    inline Time                start_max(InterventionId j) const { return interventions_[j].t_start_max; }
    inline Time                 duration(InterventionId j, Time t) const { return interventions_[j].deltas[t]; }
    inline double          duration_mean(InterventionId j) const { return interventions_[j].duration_mean; }
    inline double          workload_mean(InterventionId j, ResourceId r) const { return interventions_[j].workload_mean[r]; }
    inline ExclusionId  number_of_exclusions(InterventionId j) const { return interventions_[j].number_of_exclusions; }
    inline Risk                     risk(InterventionId j, Time t_cur, Time t_start, ScenarioId s) const { return interventions_[j].risks[t_cur].risk(t_start, s); }
    inline ResourcePos   number_of_resources(InterventionId j) const { return interventions_[j].resources.size(); }
    inline ResourceId           resource(InterventionId j, ResourcePos r_pos) const { return interventions_[j].resources[r_pos].r; }
    inline Workload             workload(InterventionId j, ResourcePos r_pos, Time t_cur, Time t_start) const { return interventions_[j].resources[r_pos].workload(t_cur, t_start); }
    inline const std::vector<ExclusionId>& exclusions(InterventionId j, SeasonId season) const { return interventions_[j].exclusions[season]; }

    inline Workload         workload_min(ResourceId r, Time t) const { return resources_[r].min[t]; }
    inline Workload         workload_max(ResourceId r, Time t) const { return resources_[r].max[t]; }
    inline Workload  resource_multiplier(ResourceId r) const { return resources_[r].multiplier; }

    inline const Exclusion& exclusion(ExclusionId e) const { return exclusions_[e]; }

    std::string intervention_name(InterventionId j) const { return interventions_[j].name; }
    std::string     resource_name(ResourceId r)     const { return resources_[r].name; }
    std::string       season_name(SeasonId season)  const { return season_strings_[season]; }

    InterventionId intervention(std::string intervention_name) const { return string_to_interv_.at(intervention_name); }

    int fixed(InterventionId j, Time t_start) const { return interventions_[j].fixed_assignments[t_start]; }
    bool unconstrained(ResourceId r, Time t_cur) const { return resources_[r].unconstrained[t_cur]; }

private:

    /*
     * Attributes
     */

    double alpha_;
    double quantile_;
    Time horizon_;
    std::vector<Intervention> interventions_;
    std::vector<Resource> resources_;
    /** number_of_scenarioss_[t]. */
    std::vector<ScenarioId> number_of_scenarioss_;
    /** seasons_[t]. */
    std::vector<SeasonId> seasons_;
    std::vector<Exclusion> exclusions_;

    std::map<std::string, InterventionId> string_to_interv_;
    std::map<std::string, ResourceId>     string_to_resource_;
    std::map<std::string, SeasonId>       string_to_season_;
    std::vector<std::string> season_strings_;

    ScenarioId least_common_multiple_ = 1;
    Risk alpha_1_;
    Risk alpha_2_;
    Risk alpha_multiplier_ = 1;
    Risk risk_multiplier_ = 1;

    void fix_assignments();

};

std::ostream& operator<<(std::ostream& os, const Instance& instance);

}

}
