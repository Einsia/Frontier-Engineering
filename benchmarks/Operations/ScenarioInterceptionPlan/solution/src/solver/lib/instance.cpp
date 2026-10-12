#include "instance.h"
#include <filesystem>

namespace PACE2025_HS {
    bool global_exit_signal_reached = false;
    char global_input_line[1024 * 1024];

	void OriginalSCInstance::read_hs_instance(const Str& filename) {
        std::filesystem::path p(filename);
        instname_ = p.stem().string();

        FILE* file = fopen(filename.c_str(), "r");
        if (!file) {
            fatalif(true, "Open file %s failed!", filename.c_str());
        }
        read_hs_instance(file);
        fclose(file); 
	}

	void OriginalSCInstance::read_hs_instance(FILE* input) {
        bool header_processed = false; 
        ElementId element_id = 0;
        SetId set_id = 0;
        enum class ProblemType { HS, DS };
        ProblemType prob_type = ProblemType::DS;
        while (fgets(global_input_line, sizeof(global_input_line), input)) {
            // Skip empty lines
            if (global_input_line[0] == '\n') continue;
            // Skip comment lines
            if (global_input_line[0] == 'c') continue;
            // Process the line
            if (!header_processed) {
                // Read header line (p hs n m)
                char type[3]; SetId n; ElementId m;

                if (sscanf(global_input_line, "p %2s %d %d", type, &n, &m) == 3) {
                    type[2] = 0; 
                    if (strcmp(type, "hs") == 0) {
                        prob_type = ProblemType::HS;
                        set_num_ = n; sets_.resize(set_num_);
                        element_num_ = m; elements_.resize(element_num_);
                    }
                    else if (strcmp(type, "ds") == 0) {
                        prob_type = ProblemType::DS;
                        set_num_ = n; sets_.resize(set_num_);
                        element_num_ = n; elements_.resize(element_num_);
                        for (SetId s = 0; s < set_num_; ++s) {
                            sets_[s].emplace_back(s);
                            elements_[s].emplace_back(s);
                        }
                    }
                    else {
                        fatalif(true, "Problem type (%s) != hs!", type);
                    }
                    header_processed = true;
                }
            }
            else {
                // Process a set line
                char* ptr = global_input_line;
                // Read all integers in the line
                if (prob_type == ProblemType::HS) {
                    while (*ptr != '\0') {
                        if (isdigit(*ptr)) {
                            int input_n = sscanf(ptr, "%d", &set_id);
                            if (input_n == 1) {
                                --set_id;
                                sets_[set_id].emplace_back(element_id);
                                elements_[element_id].emplace_back(set_id);

                                // Move pointer past the number we just read
                                while (isdigit(*ptr)) { ptr++; }
                            }
                        }
                        else { ptr++; }
                    }
                    ++element_id;
                } else {
                    Vec<ElementId> ids;
                    while (*ptr != '\0') {
                        if (isdigit(*ptr)) {
                            int input_n = sscanf(ptr, "%d", &set_id);
                            if (input_n == 1) {
                                ids.emplace_back(--set_id);
                                // Move pointer past the number we just read
                                while (isdigit(*ptr)) { ptr++; }
                            }
                        }
                        else { ptr++; }
                    }
                    sets_[ids[0]].emplace_back(ids[1]);
                    sets_[ids[1]].emplace_back(ids[0]);
                    elements_[ids[0]].emplace_back(ids[1]);
                    elements_[ids[1]].emplace_back(ids[0]);
                }
            }
        }
	}

    bool OriginalSCInstance::is_valid_solution(const Vec<SetId>& res) const {
        Vec<ElementId> is_element_covered(element_num_, 0);
        for (SetId s : res) {
            for (ElementId e : sets_[s]) {
                is_element_covered[e] = true;
            }
        }

        for (ElementId e = 0; e < element_num_; ++e) {
            if (!is_element_covered[e]) {
                return false;
            }
        }

        return true;
    }

    SimplifiedSCInstance::SimplifiedSCInstance(const OriginalSCInstance& inst, Log logger): osci_(inst), logger_(logger) {
        element_num_ = osci_.element_num_;
        set_num_ = osci_.set_num_;
        elements_ = osci_.elements_;
        sets_ = osci_.sets_;
        
        cur_set_id_to_ori_.resize(set_num_);
        for (SetId s = 0; s < set_num_; ++s) {
            cur_set_id_to_ori_[s] = s;
            std::sort(sets_[s].begin(), sets_[s].end());
        }
        cur_ele_id_to_ori_.resize(element_num_);
        for (ElementId e = 0; e < element_num_; ++e) {
            cur_ele_id_to_ori_[e] = e;
            std::sort(elements_[e].begin(), elements_[e].end());
        }

        //db4(element_num_, elements_.size(), set_num_, sets_.size());
    }

    Vec<SetId> SimplifiedSCInstance::generate_complete_sol(const Vec<SetId>& res) const {
        Vec<SetId> complete_res; complete_res.reserve(osci_.set_num_);
        for (SetId s : res) {
            complete_res.emplace_back(cur_set_id_to_ori_[s]);
        }
        for (SetId s : ori_fixed_sets_) {
            complete_res.emplace_back(s);
        }
        return complete_res;
    }

    bool SimplifiedSCInstance::is_valid_solution(const Vec<SetId>& res) const {
        Vec<SetId> complete_res; complete_res.reserve(osci_.set_num_);
        for (SetId s : res) {
            complete_res.emplace_back(cur_set_id_to_ori_[s]);
        }
        for (SetId s : ori_fixed_sets_) {
            complete_res.emplace_back(s);
        }

        return osci_.is_valid_solution(complete_res);
    }

    ElementId SimplifiedSCInstance::initialize_connected_component() {
        Vec<ElementId> element_vis(element_num_, 0);
        Vec<SetId> set_vis(set_num_, 0);
        Vec<SetId> component_size_map(set_num_, 0);

        element_component_id_map_.resize(element_num_);
        set_component_id_map_.resize(set_num_);
        set_component_size_map_.resize(set_num_);
        set_component_number_ = 0;
        component_sets_.resize(set_num_);
        component_elements_.resize(set_num_);
        for (SetId c = 0; c < set_num_; ++c) {
            component_sets_[c].clear();
            component_elements_[c].clear();
        }

        for (ElementId e = 0; e < element_num_; ++e) {
            if (element_vis[e] == 1) { continue; }
            std::queue<ElementId> que; que.push(e);
            element_vis[e] = true; 
            while (!que.empty()) {
                ElementId out = que.front(); que.pop();
                element_component_id_map_[out] = set_component_number_;
                component_elements_[set_component_number_].emplace_back(out);
                for (SetId s : elements_[out]) {
                    if (set_vis[s]) { continue; }
                    set_vis[s] = true;
                    for (ElementId e2 : sets_[s]) {
                        if (element_vis[e2] == false) {
                            que.push(e2);
                            element_vis[e2] = true;
                        }
                    }
                    component_sets_[set_component_number_].emplace_back(s);
                    ++component_size_map[set_component_number_];
                    set_component_id_map_[s] = set_component_number_;
                }
            }
            ++set_component_number_;
        }

        for (SetId s = 0; s < set_num_; ++s) {
            SetId component_id = set_component_id_map_[s];
            set_component_size_map_[s] = component_size_map[component_id];
        }

        return set_component_number_;
    }

    void SimplifiedSCInstance::print_statistics() const {
        // 元素数目、元素最大/最小/平均大小
        // 集合数目、集合最大/最小/平均大小
        auto statistic_on_element = [&]() {
            std::map<ElementId, SetId> element_degree_count;
            printf("Element Infomation: \n");
            printf("\tElement Number: %d\n", element_num_);
            SetId max_cover_n = 0, min_cover_n = set_num_;
            Count avg_cover_n = 0;
            for (ElementId e = 0; e < element_num_; ++e) {
                SetId cover_n = SetId(elements_[e].size());
                if (max_cover_n < cover_n) { max_cover_n = cover_n; }
                if (min_cover_n > cover_n) { min_cover_n = cover_n; }
                avg_cover_n += cover_n;
                element_degree_count[cover_n] += 1;
            }
            printf("\tElement Max Covered Number: %d\n", max_cover_n);
            printf("\tElement Min Covered Number: %d\n", min_cover_n);
            printf("\tElement Avg Covered Number: %.2f\n", 1.0 * avg_cover_n / element_num_);

            if (avg_cover_n / element_num_ > 0) { return; }

            // 元素的二跳邻居大小/集合的二跳邻居大小
            SetId max_2_hop_cover_n = 0, min_2_hop_cover_n = set_num_;
            Count avg_2_hop_cover_n = 0;
            for (ElementId e = 0; e < element_num_; ++e) {
                const Vec<SetId>& E1 = elements_[e];
                UnorderedSet<ElementId> tow_hops;
                for (SetId s : E1) {
                    const Vec<SetId>& S1 = sets_[s];
                    for (ElementId e2 : S1) {
                        if (!tow_hops.contains(e2)) {
                            tow_hops.insert(e2);
                        }
                    }
                }
                SetId cover_n_2_hop = SetId(tow_hops.size());
                if (max_2_hop_cover_n < cover_n_2_hop) { max_2_hop_cover_n = cover_n_2_hop; }
                if (min_2_hop_cover_n > cover_n_2_hop) { min_2_hop_cover_n = cover_n_2_hop; }
                avg_2_hop_cover_n += cover_n_2_hop;
            }

            printf("\tElement Max 2-Hop Neighbor Number: %d\n", max_2_hop_cover_n);
            printf("\tElement Min 2-Hop Neighbor Number: %d\n", min_2_hop_cover_n);
            printf("\tElement Avg 2-Hop Neighbor Number: %.2f\n", 1.0 * avg_2_hop_cover_n / element_num_);
        };

        auto statistic_on_set = [&]() {
            std::map<SetId, ElementId> set_degree_count;
            printf("Set Infomation: \n");
            printf("\tSet Number: %d\n", set_num_);
            SetId max_cover_n = 0, min_cover_n = element_num_;
            Count avg_cover_n = 0;
            for (SetId s = 0; s < set_num_; ++s) {
                ElementId cover_n = ElementId(sets_[s].size());
                if (max_cover_n < cover_n) { max_cover_n = cover_n; }
                if (min_cover_n > cover_n) { min_cover_n = cover_n; }
                avg_cover_n += cover_n;
                set_degree_count[cover_n] += 1;
            }
            printf("\tSet Max Covered Number: %d\n", max_cover_n);
            printf("\tSet Min Covered Number: %d\n", min_cover_n);
            printf("\tSet Avg Covered Number: %.2f\n", 1.0 * avg_cover_n / set_num_);

            /*for (auto iter = set_degree_count.begin(); iter != set_degree_count.end(); ++iter) {
                printf("%d %d\n", iter->first, iter->second);
            }*/
            if (avg_cover_n / set_num_ > 0) { return; }

            // 元素的二跳邻居大小/集合的二跳邻居大小
            SetId max_2_hop_cover_n = 0, min_2_hop_cover_n = set_num_;
            Count avg_2_hop_cover_n = 0;
            for (SetId s = 0; s < set_num_; ++s) {
                const Vec <ElementId>& S1 = sets_[s];
                UnorderedSet<SetId> tow_hops;
                for (ElementId e : S1) {
                    const Vec<ElementId>& E1 = elements_[e];
                    for (SetId s2 : E1) {
                        if (!tow_hops.contains(s2)) {
                            tow_hops.insert(s2);
                        }
                    }
                }
                ElementId cover_n_2_hop = ElementId(tow_hops.size());
                if (max_2_hop_cover_n < cover_n_2_hop) { max_2_hop_cover_n = cover_n_2_hop; }
                if (min_2_hop_cover_n > cover_n_2_hop) { min_2_hop_cover_n = cover_n_2_hop; }
                avg_2_hop_cover_n += cover_n_2_hop;
            }

            printf("\tSet Max 2-Hop Neighbor Number: %d\n", max_2_hop_cover_n);
            printf("\tSet Min 2-Hop Neighbor Number: %d\n", min_2_hop_cover_n);
            printf("\tSet Avg 2-Hop Neighbor Number: %.2f\n", 1.0 * avg_2_hop_cover_n / set_num_);
        };


        statistic_on_element();
        statistic_on_set();

        printf("Other Information:\n\tSet Component Mumber: %d\n", set_component_number_);
    }
}

