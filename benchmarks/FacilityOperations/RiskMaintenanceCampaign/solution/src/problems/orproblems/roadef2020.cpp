#include "orproblems/roadef2020.hpp"

#include "simdjson.h"

#include <numeric>
#include <unordered_set>

using namespace orproblems::roadef2020;
using namespace simdjson;

Risk gcd(Risk a, Risk b)
{
    for (;;)
    {
        if (a == 0)
            return b;
        b %= a;
        if (b == 0)
            return a;
        a %= b;
    }
}

Risk lcm(Risk a, Risk b)
{
    Risk temp = gcd(a, b);
    return temp? (a / temp * b): 0;
}

Instance::Instance(
        std::string instance_path,
        std::string)
{
    std::ifstream f(instance_path);
    if (!f.good())
        throw std::runtime_error(
                "Unable to open file \"" + instance_path + "\".");

    // Read json file.
    ondemand::parser parser;
    auto json = padded_string::load(instance_path);
    ondemand::document doc = parser.iterate(json); // position a pointer at the beginning of the JSON data

    std::cout << "Read instance..." << std::endl;
    for (auto field: doc.get_object()) {
        auto key = std::string_view(field.unescaped_key());
        if (key == "Resources") {
            std::cout << "* Read resources..." << std::endl;
            ResourceId resource_id = 0;
            for (auto resource_field: field.value().get_object()) {
                auto resource_name = std::string_view(resource_field.unescaped_key());
                string_to_resource_[std::string(resource_name)] = resource_id;
                resources_.push_back({});
                resources_.back().name = std::string(resource_name);
                Resource& resource = resources_.back();
                for (auto m: resource_field.value().get_object()) {
                    auto m_str = std::string_view(m.unescaped_key());
                    if (m_str == "min") {
                        for (double val: m.value().get_array()) {
                            resource.min_double.push_back(val);
                            while (fabs(val * resource.multiplier
                                        - std::round(val * resource.multiplier)) > 0.000001)
                                resource.multiplier *= 10;
                        }
                    } else if (m_str == "max") {
                        for (double val: m.value().get_array()) {
                            resource.max_double.push_back(val);
                            while (fabs(val * resource.multiplier
                                        - std::round(val * resource.multiplier)) > 0.000001)
                                resource.multiplier *= 10;
                        }
                    }
                }
                resource_id++;
            }
        } else if (key == "Seasons") {
            std::cout << "* Read seasons..." << std::endl;
            SeasonId season_id = 0;
            for (auto season: field.value().get_object()) {
                auto season_name = std::string_view(season.unescaped_key());
                season_strings_.push_back(std::string(season_name));
                string_to_season_[std::string(season_name)] = season_id;
                for (auto val: season.value().get_array()) {
                    Time t = std::stol(std::string(std::string_view(val))) - 1;
                    if ((Time)seasons_.size() <= t)
                        seasons_.resize(t + 1, -1);
                    seasons_[t] = season_id;
                }
                season_id++;
            }
        } else if (key == "Interventions") {
            std::cout << "* Read interventions..." << std::endl;
            InterventionId intervention_id = 0;
            for (auto intervention_field: field.value().get_object()) {
                auto intervention_name = std::string_view(intervention_field.unescaped_key());
                string_to_interv_[std::string(intervention_name)] = intervention_id;
                interventions_.push_back({});
                Intervention& intervention = interventions_.back();
                intervention.name = std::string(intervention_name);
                intervention.exclusions = std::vector<std::vector<ExclusionId>>(number_of_seasons());
                for (auto m: intervention_field.value().get_object()) {
                    auto m_str = std::string_view(m.unescaped_key());
                    if (m_str == "tmax") {
                        intervention.t_start_max
                            = std::stol(std::string(std::string_view(m.value()))) - 1;
                    } else if (m_str == "Delta") {
                        for (double val: m.value().get_array())
                            intervention.deltas.push_back(val);
                    } else if (m_str == "workload") {
                        ResourcePos resource_pos = 0;
                        for (auto resource_field: m.value().get_object()) {
                            intervention.resources.push_back({});
                            InterventionResource& resource = intervention.resources.back();
                            auto resource_name = std::string_view(resource_field.unescaped_key());
                            ResourceId resource_id = string_to_resource_[std::string(resource_name)];
                            resource.r = resource_id;
                            Time t_pos = 0;
                            for (auto t_cur_field: resource_field.value().get_object()) {
                                Time t_cur = std::stol(std::string(std::string_view(t_cur_field.unescaped_key()))) - 1;
                                while ((Time)resource.workloads.size() <= t_cur) {
                                    resource.workloads.push_back({});
                                    resource.workloads.back().t_first = resource.workloads.size();
                                }
                                InterventionResourceWorkload& iworkload = resource.workloads[t_cur];
                                for (auto t_start_field: t_cur_field.value().get_object()) {
                                    Time t_start = std::stol(std::string(std::string_view(t_start_field.unescaped_key()))) - 1;
                                    if (iworkload.t_first > t_start)
                                        iworkload.t_first = t_start;
                                    Time t_pos = t_start - iworkload.t_first;
                                    if ((Time)iworkload.workloads_double.size() <= t_pos)
                                        iworkload.workloads_double.resize(t_pos + 1, 0);
                                    iworkload.workloads_double[t_pos] = t_start_field.value();
                                    while (fabs((double)t_start_field.value() * resources_[resource_id].multiplier
                                                - std::round((double)t_start_field.value() * resources_[resource_id].multiplier)) > 0.000001)
                                        resources_[resource_id].multiplier *= 10;
                                }
                                t_pos++;
                            }
                            resource_pos++;
                        }
                        std::sort(intervention.resources.begin(), intervention.resources.end(),
                                [](const InterventionResource& r1, const InterventionResource& r2) {
                                    return r1.r < r2.r;
                                });
                    } else if (m_str == "risk") {
                        for (auto t_cur_field: m.value().get_object()) {
                            Time t_cur = std::stol(std::string(std::string_view(t_cur_field.unescaped_key()))) - 1;
                            while ((Time)intervention.risks.size() <= t_cur) {
                                intervention.risks.push_back({});
                                intervention.risks.back().t_first = intervention.risks.size();
                            }
                            InterventionRisk& irisk = intervention.risks[t_cur];
                            for (auto t_start_field: t_cur_field.value().get_object()) {
                                Time t_start = std::stol(std::string(std::string_view(t_start_field.unescaped_key()))) - 1;
                                if (irisk.t_first > t_start)
                                    irisk.t_first = t_start;
                                Time t_pos = t_start - irisk.t_first;
                                if ((Time)irisk.risks_double.size() <= t_pos)
                                    irisk.risks_double.resize(t_pos + 1);
                                for (double risk: t_start_field.value().get_array()) {
                                    irisk.risks_double[t_pos].push_back(risk);
                                    while (fabs((double)risk * risk_multiplier_
                                                - std::round((double)risk * risk_multiplier_)) > 0.000001)
                                        risk_multiplier_ *= 10;
                                }
                            }
                        }
                    }
                }
                intervention_id++;
            }
        } else if (key == "Exclusions") {
            std::cout << "* Read exclusions..." << std::endl;
            ExclusionId exclusion_id = 0;
            for (auto exclusion_field: field.value().get_object()) {
                exclusions_.push_back({});
                Exclusion& exclusion = exclusions_.back();
                InterventionId id = 0;
                for (auto val: exclusion_field.value().get_array()) {
                    if (id == 0) {
                        std::string intervention_name = std::string(std::string_view(val));
                        exclusion.j1 = string_to_interv_[intervention_name];
                    } else if (id == 1) {
                        std::string intervention_name = std::string(std::string_view(val));
                        exclusion.j2 = string_to_interv_[intervention_name];
                    } else if (id == 2) {
                        std::string season_name = std::string(std::string_view(val));
                        exclusion.season = string_to_season_[season_name];
                    } else {

                    }
                    id++;
                }
                interventions_[exclusion.j1].exclusions[exclusion.season].push_back(exclusion_id);
                interventions_[exclusion.j1].number_of_exclusions++;
                interventions_[exclusion.j2].exclusions[exclusion.season].push_back(exclusion_id);
                interventions_[exclusion.j2].number_of_exclusions++;
                exclusion_id++;
            }
        } else if (key == "T") {
            std::cout << "* Read horizon..." << std::endl;
            horizon_ = (int64_t)field.value();
        } else if (key == "Scenarios_number") {
            std::cout << "* Read scenarios..." << std::endl;
            for (ScenarioId number_of_scenarios: field.value().get_array()) {
                number_of_scenarioss_.push_back(number_of_scenarios);
                least_common_multiple_ = lcm(least_common_multiple_, number_of_scenarios);
                if (least_common_multiple_ >= 10000000)
                    least_common_multiple_ =  10000000;
                assert(least_common_multiple_ >= 0);
            }
        } else if (key == "Alpha") {
            std::cout << "* Read alpha..." << std::endl;
            alpha_ = field.value();
            while (alpha_ * alpha_multiplier_
                    - std::floor(alpha_ * alpha_multiplier_) != 0) {
                alpha_multiplier_ *= 10;
            }
        } else if (key == "Quantile") {
            std::cout << "* Read quantile..." << std::endl;
            quantile_ = field.value();
        } else if (key == "ComputationTime") {
        }
    }

    // Compute integer values.
    std::cout << "Convert instance..." << std::endl;

    std::cout << "* Convert alpha..." << std::endl;
    alpha_1_ = alpha_ * alpha_multiplier_;
    alpha_2_ = alpha_multiplier_ - alpha_1_;

    // Convert resources.
    std::cout << "* Convert resources..." << std::endl;
    for (ResourceId r = 0; r < number_of_resources(); ++r) {
        Resource& resource = resources_[r];
        resource.multiplier = std::min((ResourceId)1000000, resources_[r].multiplier);
        for (double val: resource.min_double)
            resource.min.push_back(std::round(val * resources_[r].multiplier));
        std::vector<double> min_tmp;
        resource.min_double.swap(min_tmp);
        for (double val: resource.max_double)
            resource.max.push_back(std::round(val * resources_[r].multiplier));
        std::vector<double> max_tmp;
        resource.min_double.swap(max_tmp);
    }

    // Convert risks.
    std::cout << "* Convert risks..." << std::endl;
    risk_multiplier_ = std::min((ResourceId)10000, risk_multiplier_);
    for (InterventionId j = 0; j < number_of_interventions(); ++j) {
        for (Time t_cur = 0; t_cur < (Time)interventions_[j].risks.size(); ++t_cur) {
            InterventionRisk& irisk = interventions_[j].risks[t_cur];
            for (const auto& vec: irisk.risks_double) {
                irisk.risks.push_back({});
                for (double val: vec)
                    irisk.risks.back().push_back(std::round(val * risk_multiplier_));
            }
            std::vector<std::vector<double>> tmp;
            irisk.risks_double.swap(tmp);
        }
    }
    //for (InterventionId j = 0; j < number_of_interventions(); ++j) {
    //    for (Time t_start = 0; t_start <= start_max(j); ++t_start) {
    //        Time t_end = t_start + duration(j, t_start);
    //        for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
    //            for (ScenarioId s = 0; s < number_of_scenarios(t_cur); ++s) {
    //                std::cout << "j " << j
    //                    << " t_cur " << t_cur
    //                    << " t_start " << t_start
    //                    << " s " << s
    //                    << " d " << risk_double(j, t_cur, t_start, s)
    //                    << " m " << risk_multiplier_
    //                    << " i " << risk_int(j, t_cur, t_start, s)
    //                    << std::endl;
    //            }
    //        }
    //    }
    //}

    // Convert workloads.
    std::cout << "* Convert workloads..." << std::endl;
    for (InterventionId j = 0; j < number_of_interventions(); ++j) {
        for (ResourcePos r_pos = 0; r_pos < number_of_resources(j); ++r_pos) {
            ResourceId r = resource(j, r_pos);
            for (Time t_cur = 0; t_cur < (Time)interventions_[j].resources[r_pos].workloads.size(); ++t_cur) {
                InterventionResourceWorkload& iworkload
                    = interventions_[j].resources[r_pos].workloads[t_cur];
                for (double w: iworkload.workloads_double)
                    iworkload.workloads.push_back(
                            std::round(w * resources_[r].multiplier));
                std::vector<double> w_tmp;
                iworkload.workloads_double.swap(w_tmp);
            }
        }
    }
    //for (InterventionId j = 0; j < number_of_interventions(); ++j) {
    //    std::cout << "j " << j << " name " << intervention_name(j) << std::endl;
    //    for (ResourcePos r_pos = 0; r_pos < number_of_resources(j); ++r_pos) {
    //        ResourceId r = resource(j, r_pos);
    //        std::cout << "r_pos " << r_pos << " r " << r
    //            << " name " << resource_name(r)
    //            << std::endl;
    //        for (Time t_start = 0; t_start < start_max(j); ++t_start) {
    //            Time t_end = t_start + duration(j, t_start);
    //            std::cout << "t_start " << t_start << " t_end " << t_end << std::endl;
    //            for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
    //                Workload w = workload(j, r_pos, t_cur, t_start);
    //                std::cout << "t_cur " << t_cur
    //                    << " w " << w << std::endl;
    //            }
    //        }
    //    }
    //}

    fix_assignments();
}

void Instance::fix_assignments()
{
    std::cout << "Fix assignments..." << std::endl;
    Counter number_of_fixed_assignments = 0;
    Counter number_of_assignments = 0;
    for (InterventionId j = 0; j < number_of_interventions(); ++j) {
        interventions_[j].fixed_assignments = std::vector<int8_t>(start_max(j) + 1, -1);
        number_of_assignments += start_max(j) + 1;
    }
    Counter total_number_of_resources = 0;
    Counter number_of_unconstrained_resources = 0;
    for (ResourceId r = 0; r < number_of_resources(); ++r) {
        resources_[r].unconstrained = std::vector<bool>(horizon(), false);
        total_number_of_resources += horizon();
    }

    // Dominated starts.
    for (InterventionId j = 0; j < number_of_interventions(); ++j) {
        for (Time t_start = 0; t_start < start_max(j); ++t_start) {
            if (fixed(j, t_start) != -1)
                continue;
            Time t_end = t_start + duration(j, t_start);
            Time t_end_2 = t_start + 1 + duration(j, t_start + 1);
            if (t_end_2 > t_end)
                continue;
            bool dominated = true;
            for (Time t_cur = t_start + 1; t_cur < t_end; ++t_cur) {
                for (ResourcePos r_pos = 0; r_pos < number_of_resources(j); ++r_pos) {
                    Workload w = workload(j, r_pos, t_cur, t_start);
                    Workload w2 = workload(j, r_pos, t_cur, t_start + 1);
                    if (w < w2) {
                        dominated = false;
                        break;
                    }
                }
                if (!dominated)
                    break;
                for (ScenarioId s = 0; s < number_of_scenarios(t_cur); ++s) {
                    Risk r = risk(j, t_cur, t_start, s);
                    Risk r2 = risk(j, t_cur, t_start + 1, s);
                    if (r < r2) {
                        dominated = false;
                        break;
                    }
                }
                if (!dominated)
                    break;
            }
            if (dominated) {
                interventions_[j].fixed_assignments[t_start] = 0;
                number_of_fixed_assignments++;
            }
        }
    }
    std::cout << "* Dominated starts:                "
        << number_of_fixed_assignments << " / " << number_of_assignments << std::endl;

    for (;;) {
        bool new_fixed = false;

        // Conflicts.
        for (InterventionId j = 0; j < number_of_interventions(); ++j) {
            std::vector<bool> mandatory(horizon(), true);
            for (Time t_start = 0; t_start <= start_max(j); ++t_start) {
                if (fixed(j, t_start) == 0)
                    continue;
                for (Time t = 0; t < t_start; ++t)
                    mandatory[t] = false;
                for (Time t = t_start + duration(j, t_start); t < horizon(); ++t)
                    mandatory[t] = false;
            }
            for (Time t_cur = 0; t_cur < horizon(); ++t_cur) {
                if (!mandatory[t_cur])
                    continue;
                SeasonId s = seasons_[t_cur];
                for (ExclusionId e: exclusions(j, s)) {
                    InterventionId j2 = exclusion(e).j(j);
                    for (Time t_start_2 = 0; t_start_2 <= start_max(j2); ++t_start_2) {
                        if (interventions_[j2].fixed_assignments[t_start_2] != -1)
                            continue;
                        if (t_start_2 <= t_cur
                                && t_cur < t_start_2 + duration(j2, t_start_2)) {
                            interventions_[j2].fixed_assignments[t_start_2] = 0;
                            number_of_fixed_assignments++;
                            new_fixed = true;
                        }
                    }
                }
            }
        }
        std::cout << "* Conflicts:                       "
            << number_of_fixed_assignments << " / " << number_of_assignments << std::endl;

        if (!new_fixed)
            break;
    }

    // Single starts.
    for (InterventionId j = 0; j < number_of_interventions(); ++j) {
        std::vector<Time> starts;
        for (Time t_start = 0; t_start <= start_max(j); ++t_start)
            if (fixed(j, t_start) != 0)
                starts.push_back(t_start);
        if (starts.size() == 1) {
            interventions_[j].fixed_assignments[starts.front()] = 1;
            number_of_fixed_assignments++;
        }
    }
    std::cout << "* Single starts:                   "
        << number_of_fixed_assignments << " / " << number_of_assignments << std::endl;

    // Unconstrained resources.
    std::vector<std::vector<Workload>> workloads_max(
            horizon(),
            std::vector<Workload>(number_of_resources(), 0));
    for (InterventionId j = 0; j < number_of_interventions(); ++j) {
        std::vector<std::vector<Workload>> workloads_max_j(
                horizon(),
                std::vector<Workload>(number_of_resources(), 0));
        for (Time t_start = 0; t_start <= start_max(j); ++t_start) {
            if (fixed(j, t_start) == 0)
                continue;
            Time t_end = t_start + duration(j, t_start);
            for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
                for (ResourcePos r_pos = 0; r_pos < number_of_resources(j); ++r_pos) {
                    ResourceId r = resource(j, r_pos);
                    Workload w = workload(j, r_pos, t_cur, t_start);
                    if (workloads_max_j[t_cur][r] < w)
                        workloads_max_j[t_cur][r] = w;
                }
            }
        }
        for (Time t_cur = 0; t_cur < horizon(); ++t_cur) {
            for (ResourcePos r_pos = 0; r_pos < number_of_resources(j); ++r_pos) {
                ResourceId r = resource(j, r_pos);
                workloads_max[t_cur][r] += workloads_max_j[t_cur][r];
            }
        }
    }
    for (Time t_cur = 0; t_cur < horizon(); ++t_cur) {
        for (ResourceId r = 0; r < number_of_resources(); ++r) {
            if (resources_[r].unconstrained[t_cur])
                continue;
            if (workloads_max[t_cur][r] <= workload_max(r, t_cur)) {
                resources_[r].unconstrained[t_cur] = true;
                number_of_unconstrained_resources++;
                //std::cout << "t " << t_cur << " r " << r
                //    << " w " << workloads_max[t_cur][r] << " / " << workload_max(r, t_cur)
                //    << std::endl;
            }
        }
    }
    std::cout << "* Unconstrained resources:         "
        << number_of_unconstrained_resources << " / " << total_number_of_resources << std::endl;

    for (InterventionId j = 0; j < number_of_interventions(); ++j) {

        interventions_[j].workload_mean.resize(number_of_resources(), 0);
        for (ResourcePos r_pos = 0; r_pos < number_of_resources(j); ++r_pos) {
            ResourceId r = resource(j, r_pos);
            Time number_of_starts = 0;
            for (Time t_start = 0; t_start <= start_max(j); ++t_start) {
                double r_max = 0;
                Time t_end = t_start + duration(j, t_start);
                for (Time t_cur = t_start; t_cur < t_end; ++t_cur) {
                    Workload w = workload(j, r_pos, t_cur, t_start);
                    Workload w_max = workload_max(r, t_cur);
                    double r = (double)w / w_max;
                    if (r_max < r)
                        r_max = r;
                }
                interventions_[j].workload_mean[r] += r_max;
                number_of_starts++;
            }
            interventions_[j].workload_mean[r] /= number_of_starts;
        }

        Time d_sum = 0;
        Time number_of_starts = 0;
        for (Time t_start = 0; t_start <= start_max(j); ++t_start) {
            if (fixed(j, t_start) == 0)
                continue;
            d_sum += duration(j, t_start);
            number_of_starts++;
        }
        interventions_[j].duration_mean = (double)d_sum / number_of_starts;
    }

    // Reduced instance.
    std::vector<InterventionId> interventions(number_of_interventions());
    std::iota(interventions.begin(), interventions.end(), 0);
    std::sort(interventions.begin(), interventions.end(),
            [this](InterventionId j1, InterventionId j2) {
                    return duration_mean(j1) < duration_mean(j2);
            });
    std::vector<bool> selected_interventions(number_of_interventions(), true);
    InterventionId n = number_of_interventions();
    Time d_max = 0;
    for (InterventionId j: interventions) {
        Time d = duration_mean(j);
        if (n < (double)number_of_interventions() / 2
                && d > d_max)
            break;
        if (d_max < ceil(d - 0.5) + 0.5) {
            //std::cout << "d " << d_max << " n " << n << std::endl;
            d_max = ceil(d - 0.5) + 0.5;
        }
        selected_interventions[j] = false;
        n--;
    }
    //std::cout << "n " << n << std::endl;
    for (InterventionId j: interventions) {
        if (selected_interventions[j])
            continue;
        if (number_of_exclusions(j) > 0) {
            selected_interventions[j] = true;
            n++;
        }
    }
}

std::ostream& orproblems::roadef2020::operator<<(
        std::ostream& os,
        const Instance& instance)
{
    os << "Instance:" << std::endl;
    os << "* Horizon:                         " << instance.horizon() << std::endl;
    os << "* Number of interventions:         " << instance.number_of_interventions() << std::endl;
    os << "* Number of resources:             " << instance.number_of_resources() << std::endl;
    os << "* Number of seasons:               " << instance.number_of_seasons() << std::endl;
    os << "* Number of exclusions:            " << instance.number_of_exclusions() << std::endl;
    os << "* Alpha:                           " << instance.alpha() << std::endl;
    os << "* Quantile:                        " << instance.quantile() << std::endl;
    return os;
}

