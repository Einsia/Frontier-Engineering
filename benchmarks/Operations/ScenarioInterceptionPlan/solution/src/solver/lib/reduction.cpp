#include "instance.h"
#include "solver/tools/binary_search.hpp"

namespace PACE2025_HS {
    void SimplifiedSCInstance::reduction(long long max_time_limit) {
        constexpr ElementId max_element_dominate_check_limit = 32;
        constexpr SetId max_set_dominate_check_limit = 32;

        //必选的集合
        UnorderedSet<SetId> cur_fixed_sets;
        //同时包含必选以及必不选的集合
        UnorderedSet<SetId> cur_removed_sets;
        //可忽略覆盖的元素
        UnorderedSet<ElementId> cur_removed_elements;

        auto remove_dominated_elements = [&](
            const Vec<ElementId>& dominated_flags,
            const Vec<ElementId>& dominated_elements) {
            if (dominated_elements.empty()) { return; }
            for (SetId s1 = 0; s1 < set_num_; ++s1) {
                if (cur_removed_sets.contains(s1)) { continue; }
                Vec<ElementId>& S1 = sets_[s1];
                ElementId j = 0, cover_n = ElementId(S1.size());
                for (ElementId i = 0; i < cover_n; ++i) {
                    if (!dominated_flags[S1[i]]) {
                        S1[j++] = S1[i];
                    }
                }
                S1.erase(S1.begin() + j, S1.end());
                if (S1.empty()) { cur_removed_sets.insert(s1); }
            }
            for (ElementId de : dominated_elements) {
                cur_removed_elements.insert(de);
            }
        };

        auto remove_dominated_sets = [&](
            const Vec<ElementId>& dominated_flags,
            const Vec<SetId>& dominated_sets) {
            if (dominated_sets.empty()) { return; }
            for (ElementId e1 = 0; e1 < element_num_; ++e1) {
                if (cur_removed_elements.contains(e1)) { continue; }
                Vec<SetId>& E1 = elements_[e1];
                SetId j = 0, cover_n = SetId(E1.size());
                for (SetId i = 0; i < cover_n; ++i) {
                    if (!dominated_flags[E1[i]]) {
                        E1[j++] = E1[i];
                    }
                }
                E1.erase(E1.begin() + j, E1.end());
            }
            for (SetId ds : dominated_sets) {
                cur_removed_sets.insert(ds);
            }
        };

        auto fix_single_dominated_sets = [&](const Vec<SetId>& fixed_sets) {
            if (fixed_sets.empty()) { return; }
            Vec<ElementId> dominated_flags(element_num_, 0);
            Vec<ElementId> dominated_elements;
            for (SetId fs : fixed_sets) {
                cur_removed_sets.insert(fs);
                cur_fixed_sets.insert(fs);
                for (ElementId e : sets_[fs]) {
                    if (!dominated_flags[e]) {
                        dominated_flags[e] = true;
                        dominated_elements.emplace_back(e);
                    }
                    
                }
            }
            remove_dominated_elements(dominated_flags, dominated_elements);
        };

        auto identity_element_reduction = [&]() {
            auto element_identity = [&](const Vec<SetId>& E1, const Vec<SetId>& E2) {
                if (E1.size() != E2.size()) { return false; }
                for (auto i = 0; i < E1.size(); ++i) {
                    if (E1[i] != E2[i]) { return false; }
                }
                return true;
            };

            Vec<ElementId> dominated_flags(element_num_, 0);
            Vec<ElementId> dominated_elements;
            using HashValue = unsigned long long;
            HashValue hash_base = HashValue(1000000 + 3);
            UnorderedMap<HashValue, ElementId> hash_mp;
            for (ElementId e1 = 0; e1 < element_num_; ++e1) {
                if (cur_removed_elements.contains(e1)) { continue; }
                const Vec<SetId>& E1 = elements_[e1];
                HashValue val = 0;
                for (SetId s : E1) {
                    val = val * hash_base + (HashValue)s;
                }
                if (!hash_mp.contains(val)) {
                    hash_mp[val] = e1;
                }
                else {
                    ElementId e2 = hash_mp[val];
                    const Vec<SetId>& E2 = elements_[e2];
                    if (element_identity(E1, E2)) {
                        dominated_flags[e1] = true;
                        dominated_elements.emplace_back(e1);
                    }
                }
            }

            remove_dominated_elements(dominated_flags, dominated_elements);

            return !dominated_elements.empty();
        };

        auto identity_set_reduction = [&]() {
            auto set_identity = [&](const Vec<ElementId>& S1, const Vec<ElementId>& S2) {
                if (S1.size() != S2.size()) { return false; }
                for (auto i = 0; i < S1.size(); ++i) {
                    if (S1[i] != S2[i]) { return false; }
                }
                return true;
            };

            Vec<SetId> dominated_flags(set_num_, 0);
            Vec<SetId> dominated_sets;
            using HashValue = unsigned long long;
            HashValue hash_base = HashValue(1000000 + 3);
            UnorderedMap<HashValue, SetId> hash_mp;
            for (SetId s1 = 0; s1 < set_num_; ++s1) {
                if (cur_removed_sets.contains(s1)) { continue; }
                const Vec<ElementId>& S1 = sets_[s1];
                HashValue val = 0;
                for (ElementId e : S1) {
                    val = val * hash_base + (HashValue)e;
                }
                if (!hash_mp.contains(val)) {
                    hash_mp[val] = s1;
                }
                else {
                    SetId s2 = hash_mp[val];
                    const Vec<ElementId>& S2 = sets_[s2];
                    if (set_identity(S1, S2)) {
                        dominated_flags[s1] = true;
                        dominated_sets.emplace_back(s1);
                    }
                }
            }

            remove_dominated_sets(dominated_flags, dominated_sets);

            return !dominated_sets.empty();
        };

        //检查覆盖元素e1的集合是否支配覆盖元素e2的集合
        auto is_element_dominated = [&](const Vec<SetId>& E1, const Vec<SetId>& E2) {
            if (E1.size() > E2.size()) return false;

            /*ElementId p1 = 0, p2 = 0;
            bool dominated = true;
            while (p1 != E1.size() && p2 != E2.size()) {
                ElementId val1 = E1[p1], val2 = E2[p2];
                if (val1 == val2) { ++p1; ++p2; }
                else if (val1 > val2) {
                    ++p2;
                    if (E2.size() - p2 < E1.size() - p1) {
                        dominated = false; break;
                    }
                }
                else { dominated = false; break; }
            }*/
            if (E1.back() > E2.back()) { return false; }
            Vec<SetId>::const_iterator iter_1 = E1.begin();
            Vec<SetId>::const_iterator iter_2 = E2.begin();
            bool dominated = true;
            while (iter_1 != E1.end() && iter_2 != E2.end()) {
                ElementId val1 = *iter_1;
                //iter_2 = branchless_lower_bound(iter_2, E2.end(), *iter_1);
                iter_2 = std::lower_bound(iter_2, E2.end(), val1);

                if (iter_2 == E2.end() || *iter_2 != val1) {
                    dominated = false; break;
                }
                else {
                    ++iter_1; ++iter_2;
                    if (iter_1 == E1.end()) {
                        dominated = true; break;
                    }
                    if (E2.end() - iter_2 < E1.end() - iter_1) {
                        dominated = false; break;
                    }
                }
            }

            return dominated;
        };

        auto element_dominate_reduction = [&](goal::Timer& timer) {
            Vec<ElementId> dominated_flags(element_num_, 0);
            Vec<ElementId> dominated_elements;
            for (ElementId e1 = 0; e1 < element_num_; ++e1) {
                if (global_exit_signal_reached) { break; }
                if (timer.isTimeOut()) { break; }

                //如果e1已经被其它元素支配，则不再需要考虑e1是否支配其它元素
                //其它元素肯定可以被支配e1的元素支配
                //同时避免相同集合互相支配
                if (dominated_flags[e1]) { continue; }
                if (cur_removed_elements.contains(e1)) { continue; }
                const Vec<SetId>& E1 = elements_[e1];
                if (E1.size() > max_element_dominate_check_limit) { continue; }

                /*Vec<SetId> covered_sets = E1;
                std::sort(covered_sets.begin(), covered_sets.end(), [&](SetId l, SetId r) {
                    return sets_[l].size() < sets_[r].size();
                });
                Vec<ElementId> result = sets_[covered_sets[0]];
                for (int i = 1; i < covered_sets.size(); ++i) {
                    if (result.empty()) break; 
                    Vec<ElementId> temp;
                    std::set_intersection(
                        result.begin(), result.end(),
                        sets_[covered_sets[i]].begin(), sets_[covered_sets[i]].end(),
                        std::back_inserter(temp)
                    );
                    result = std::move(temp); 
                }
                for (ElementId e2 : result) {
                    if (e2 == e1) { continue; }
                    if (!dominated_flags[e2]) {
                        dominated_flags[e2] = true;
                        dominated_elements.emplace_back(e2);
                    }
                }*/

                SetId minimum_elems_set = -1; SetId min_set_count = element_num_ + 1;
                for (SetId s : E1) {
                    SetId set_count = (ElementId)sets_[s].size();
                    if (min_set_count > set_count) {
                        min_set_count = set_count;
                        minimum_elems_set = s;
                    }
                }
                const Vec<ElementId>& S1 = sets_[minimum_elems_set];
                for (ElementId e2 : S1) {
                    if (e2 == e1) { continue; }
                    const Vec<SetId>& E2 = elements_[e2];
                    //判断E1是否是E2的子集: 如果是，则可以删除e2
                    if (dominated_flags[e2] || E1.size() > E2.size()) { continue; }
                    if (is_element_dominated(E1, E2)) {
                        dominated_flags[e2] = true;
                        dominated_elements.emplace_back(e2);
                    }
                }
            }

            remove_dominated_elements(dominated_flags, dominated_elements);

            return !dominated_elements.empty();
        };
        
        //检查集合s1覆盖的元素是否被集合s2覆盖的元素支配
        auto is_set_dominated = [&](const Vec<ElementId>& S1, const Vec<ElementId>& S2) {
            if (S1.size() > S2.size()) return false;

            /*SetId p1 = 0, p2 = 0; bool dominated = false;
            while (p1 != S1.size() && p2 != S2.size()) {
                ElementId val1 = S1[p1], val2 = S2[p2];
                if (val1 == val2) {
                    ++p1; ++p2;
                    if (p1 == S1.size()) {
                        dominated = true; break;
                    }
                }
                else if (val1 > val2) {
                    ++p2;
                    if (S2.size() - p2 < S1.size() - p1) {
                        dominated = false; break;
                    }
                }
                else { dominated = false; break; }
            }*/
            if (S1.back() > S2.back()) { return false; }
            if (S1.front() < S2.front()) { return false; }
            bool dominated = false;
            Vec<ElementId>::const_iterator iter_1 = S1.begin();
            Vec<ElementId>::const_iterator iter_2 = S2.begin();
            while (iter_1 != S1.end() && iter_2 != S2.end()) {
                ElementId val1 = *iter_1;
                iter_2 = std::lower_bound(iter_2, S2.end(), val1);
                if (iter_2 == S2.end() || *iter_2 != val1) {
                    dominated = false; break;
                }
                else {
                    ++iter_1; ++iter_2;
                    if (iter_1 == S1.end()) {
                        dominated = true; break;
                    }
                    if (S2.end() - iter_2 < S1.end() - iter_1) {
                        dominated = false; break;
                    }
                }
            }
            return dominated;
        };

        auto special_dominate_reduction = [&](goal::Timer& timer) {
            Vec<ElementId> dominated_element_flags(element_num_, 0);
            Vec<ElementId> dominated_elements;
            auto special_element_dominate_reduction = [&]() {
                for (ElementId e1 = 0; e1 < element_num_; ++e1) {
                    if (global_exit_signal_reached) { break; }
                    if (timer.isTimeOut()) { break; }

                    //如果e1已经被其它元素支配，则不再需要考虑e1是否支配其它元素
                    //其它元素肯定可以被支配e1的元素支配
                    //同时避免相同集合互相支配
                    if (dominated_element_flags[e1]) { continue; }
                    if (cur_removed_elements.contains(e1)) { continue; }
                    const Vec<SetId>& E1 = elements_[e1];
                    if (E1.size() > max_element_dominate_check_limit) { continue; }

                    //特殊检查
                    if (E1.size() <= 3) {
                        for (SetId si : E1) {
                            if (elements_.size() > si && si != e1 && !dominated_element_flags[si] && is_element_dominated(E1, elements_[si])) {
                                dominated_element_flags[si] = true; dominated_elements.emplace_back(si);
                            }
                        }
                    }
                }
            };

            Vec<SetId> dominated_set_flags(set_num_, 0);
            Vec<SetId> dominated_sets;
            auto special_set_dominate_reduction = [&]() {
                ConsecutiveIdSet<SetId> adj_sets(set_num_);
                for (SetId s1 = 0; s1 < set_num_; ++s1) {
                    if (global_exit_signal_reached) { break; }
                    if (timer.isTimeOut()) { break; }

                    //已经被支配：不需要考虑集合s1是否被其它集合支配
                    if (dominated_set_flags[s1]) { continue; }
                    if (cur_removed_sets.contains(s1)) { continue; }

                    const Vec<ElementId>& S1 = sets_[s1];
                    if (S1.empty()) {
                        dominated_set_flags[s1] = true;
                        dominated_sets.emplace_back(s1);
                        continue;
                    }
                    if (S1.size() > max_set_dominate_check_limit) { continue; }

                    //特殊检查
                    if (S1.size() <= 3) {
                        for (ElementId ei : S1) {
                            //如果s2=ei已经被支配了，则不需要考虑s2支配s1 -> 存在更大的集合支配s1, 同时避免相同集合互相支配
                            if (sets_.size() > ei && ei != s1 && !dominated_set_flags[ei] && is_set_dominated(S1, sets_[ei])) {
                                dominated_set_flags[s1] = true; dominated_sets.emplace_back(s1); break;
                            }
                        }
                    }
                }
            };

            special_element_dominate_reduction();
            special_set_dominate_reduction();

            remove_dominated_elements(dominated_element_flags, dominated_elements);

            remove_dominated_sets(dominated_set_flags, dominated_sets);

            return !dominated_elements.size() && !dominated_sets.empty();
        };

        auto set_dominate_reduction = [&](goal::Timer& timer) {
            Vec<SetId> dominated_flags(set_num_, 0);
            Vec<SetId> dominated_sets;
            for (SetId s1 = 0; s1 < set_num_; ++s1) {
                if (global_exit_signal_reached) { break; }
                if (timer.isTimeOut()) { break; }

                //已经被支配：不需要考虑集合s1是否被其它集合支配
                if (dominated_flags[s1]) { continue; }
                if (cur_removed_sets.contains(s1)) { continue; }

                const Vec<ElementId>& S1 = sets_[s1];
                if (S1.empty()) { 
                    dominated_flags[s1] = true; 
                    dominated_sets.emplace_back(s1);
                    continue; 
                }
                if (S1.size() > max_set_dominate_check_limit) { continue; }

                //Vec<ElementId> covered_elems = S1;
                //std::sort(covered_elems.begin(), covered_elems.end(), [&](ElementId l, ElementId r) {
                //    return elements_[l].size() < elements_[r].size();
                //});
                //for (SetId s2 : elements_[covered_elems[0]]) {
                //    if (s2 == s1) { continue; }
                //    const Vec<ElementId>& S2 = sets_[s2];
                //    //判断S1是否是S2的子集: 如果是，则可以删除s1
                //    //如果s2已经被支配了，则不需要考虑s2支配s1
                //    // - 存在更大的集合支配s1
                //    // - 同时避免相同集合互相支配
                //    if (dominated_flags[s2] || S1.size() > S2.size()) { continue; }
                //    bool dominated = true;
                //    // 检查候选集合是否包含S的所有元素
                //    for (int i = 1; i < covered_elems.size(); ++i) {
                //        if (!std::binary_search(
                //            elements_[covered_elems[i]].begin(),
                //            elements_[covered_elems[i]].end(),
                //            s2
                //        )) { dominated = false; break; }
                //    }
                //    if (dominated) {
                //        dominated_flags[s1] = true;
                //        dominated_sets.emplace_back(s1);
                //        break;
                //    }
                //}

                ElementId minimum_sets_elem = -1; ElementId min_elem_count = set_num_ + 1;
                for (ElementId e : S1) {
                    ElementId elem_count = (ElementId)elements_[e].size();
                    if (min_elem_count > elem_count) {
                        min_elem_count = elem_count;
                        minimum_sets_elem = e;
                    }
                }
                const Vec<SetId>& E1 = elements_[minimum_sets_elem];
                for (SetId s2 : E1) {
                    if (s2 == s1) { continue; }
                    const Vec<ElementId>& S2 = sets_[s2];
                    //判断S1是否是S2的子集: 如果是，则可以删除s1
                    //如果s2已经被支配了，则不需要考虑s2支配s1
                    // - 存在更大的集合支配s1
                    // - 同时避免相同集合互相支配
                    if (dominated_flags[s2] || S1.size() > S2.size()) { continue; }
                    if (is_set_dominated(S1, S2)) {
                        dominated_flags[s1] = true;
                        dominated_sets.emplace_back(s1);
                        break;
                    }
                }
            }

            remove_dominated_sets(dominated_flags, dominated_sets);

            return !dominated_sets.empty();
        };

        auto single_dominate_reduction = [&]() {
            Vec<SetId> fixed_sets;
            for (ElementId e1 = 0; e1 < element_num_; ++e1) {
                if (cur_removed_elements.contains(e1)) { continue; }
                if (elements_[e1].size() == 1) {
                    fixed_sets.emplace_back(elements_[e1][0]);
                }
            }

            fix_single_dominated_sets(fixed_sets);

            return !fixed_sets.empty();
        };

        auto rebuild_instance = [&]() {
            if (cur_removed_sets.empty() && cur_removed_elements.empty()) { return; }

            //将删除点的原始对应点加入相应集合
            for (SetId r_s : cur_fixed_sets) {
                ori_fixed_sets_.insert(cur_set_id_to_ori_[r_s]);
            }
            for (SetId r_s : cur_removed_sets) {
                ori_removed_sets_.insert(cur_set_id_to_ori_[r_s]);
            }
            for (SetId r_e : cur_removed_elements) {
                ori_removed_elements_.insert(cur_ele_id_to_ori_[r_e]);
            }

            Vec<SetId> tmp_set_id_mapper(set_num_), new_set_id_ori_mapper(set_num_);
            Vec<ElementId> tmp_ele_id_mapper1(element_num_), new_ele_id_ori_mapper(element_num_);

            //删除集合并记录新id的对应关系
            SetId new_set_num = 0;
            for (SetId s = 0; s < set_num_; ++s) {
                if (!cur_removed_sets.contains(s)) {
                    sets_[new_set_num] = sets_[s];
                    tmp_set_id_mapper[s] = new_set_num;
                    new_set_id_ori_mapper[new_set_num] = cur_set_id_to_ori_[s];
                    new_set_num += 1;
                }
            }
            sets_.erase(sets_.begin() + new_set_num, sets_.end());
            set_num_ = new_set_num;

            //删除元素并记录新id的对应关系
            ElementId new_element_num = 0;
            for (ElementId e = 0; e < element_num_; ++e) {
                if (!cur_removed_elements.contains(e)) {
                    elements_[new_element_num] = elements_[e];
                    tmp_ele_id_mapper1[e] = new_element_num;
                    new_ele_id_ori_mapper[new_element_num] = cur_ele_id_to_ori_[e];
                    new_element_num += 1;
                }
            }
            elements_.erase(elements_.begin() + new_element_num, elements_.end());
            element_num_ = new_element_num;

            //重新对所有集合进行编号
            for (SetId s = 0; s < set_num_; ++s) {
                for (ElementId& e : sets_[s]) {
                    e = tmp_ele_id_mapper1[e];
                }
            }
            //重新对所有元素进行编号
            for (ElementId e = 0; e < element_num_; ++e) {
                for (SetId& s : elements_[e]) {
                    s = tmp_set_id_mapper[s];
                }
            }

            //更新当前id到原始id的映射
            cur_set_id_to_ori_ = new_set_id_ori_mapper;
            cur_ele_id_to_ori_ = new_ele_id_ori_mapper;

            //清空当前的化简状态
            cur_fixed_sets.clear();
            cur_removed_sets.clear();
            cur_removed_elements.clear();
        };

        auto reduction_ = [&](Count max_count, bool apply_element_d, goal::Timer& timer) {
            for (Count i = 0, success = 1; success > 0 && i < max_count; ++i) {
                if (global_exit_signal_reached) { break; }

                if (i == 0) { 
                    //for DS insatnces
                    special_dominate_reduction(timer); 
                }

                success = 0;
                success += single_dominate_reduction();
                success += identity_element_reduction();
                success += identity_set_reduction();
                success += set_dominate_reduction(timer);
                success += single_dominate_reduction();
                if (apply_element_d) {
                    bool sub_succ = element_dominate_reduction(timer);
                    if (!sub_succ) { apply_element_d = false; }
                    success += sub_succ;
                }
                rebuild_instance();

                Str reduction_str = StringUtil::format("Reduction #%lld -> removed elements: %zd | removed (fixed) sets : %zd (%zd)",
                    i, ori_removed_elements_.size(), ori_removed_sets_.size(), ori_fixed_sets_.size()
                );
                logger_ << reduction_str << " | Time: " << timer.elapsedSeconds() << std::endl;
            }
            
        };

        goal::Timer timer_fast(max_time_limit * 0.45 * 1000.0);
        reduction_(20, false, timer_fast);

        goal::Timer timer_slow(max_time_limit * 0.55 * 1000.0);
        reduction_(20, true, timer_slow);

        initialize_connected_component();

        /*std::map<int, int> size_num;
        dbg(set_component_number_);
        for (int i = 0; i < set_component_number_; ++i) {
            size_num[component_sets_[i].size()] += 1;
            if (component_sets_[i].size() == 2) {
                for (SetId s : component_sets_[i]) {
                    std::cout << s << ": ";
                    for (ElementId e : sets_[s]) {
                        std::cout << e << ", ";
                    }
                    std::cout << std::endl;
                }
                std::cout << "================================" << std::endl;
            }
        }

        for (auto& iter : size_num) {
            dbg(iter.first, iter.second);
        }*/

        Vec<SetId> exact_fixed_sets = solve_small_component_and_rebuild(30);

        fix_single_dominated_sets(exact_fixed_sets);
        rebuild_instance();

        initialize_connected_component();

        /*std::map<int, int> size_num2;
        dbg(set_component_number_);
        for (int i = 0; i < set_component_number_; ++i) {
            size_num2[component_sets_[i].size()] += 1;
            if (component_sets_[i].size() == 2) {
                for (SetId s : component_sets_[i]) {
                    std::cout << s << ": ";
                    for (ElementId e : sets_[s]) {
                        std::cout << e << ", ";
                    }
                    std::cout << std::endl;
                }
                std::cout << "================================" << std::endl;
            }
        }

        for (auto& iter : size_num2) {
            dbg(iter.first, iter.second);
        }*/

        graph_density_ = 0.0;
        for (SetId s = 0; s < set_num_; ++s) {
            graph_density_ += sets_[s].size();
        }
        if (set_num_ > 0 && element_num_ > 0) {
            graph_density_ /= set_num_; 
            graph_density_ /= element_num_;
        }
    }

    bool SimplifiedSCInstance::try_to_initialize_hop2_neighbor(long long max_time_limit) {
        goal::Timer timer(max_time_limit * 1000.0);
        constexpr Count max_hop2_number_limit = 4096;

        is_hop2_neighbor_initialized_ = false;
        max_set_num_cover_element_ = 0;
        avg_set_num_cover_element_ = 0;
        Count total_set_num_cover_element = 0;
        for (ElementId e = 0; e < element_num_; ++e) {
            SetId cover_n = SetId(elements_[e].size());
            if (max_set_num_cover_element_ < cover_n) { 
                max_set_num_cover_element_ = cover_n; 
            }
            total_set_num_cover_element += cover_n;
        }
        if (element_num_ > 0) {
            avg_set_num_cover_element_ = total_set_num_cover_element / element_num_ + 1;
        }

        max_element_num_cover_by_set_ = 0;
        avg_element_num_cover_by_set_ = 0;
        Count total_element_num_cover_by_set = 0;
        for (SetId s = 0; s < set_num_; ++s) {
            ElementId cover_n = ElementId(sets_[s].size());
            if (max_element_num_cover_by_set_ < cover_n) { 
                max_element_num_cover_by_set_ = cover_n; 
            }
            total_element_num_cover_by_set += cover_n;
        }
        if (set_num_ > 0) {
            avg_element_num_cover_by_set_ = total_element_num_cover_by_set / set_num_ + 1;
        }
        
        Count avg_hop2_neighbor_size = avg_set_num_cover_element_;
        avg_hop2_neighbor_size *= avg_element_num_cover_by_set_;
        if (avg_hop2_neighbor_size > max_hop2_number_limit) {
            is_hop2_neighbor_initialized_ = false; return false;
        }

        elements_hop2_.clear(); elements_hop2_.resize(element_num_);
        ConsecutiveIdSet<ElementId> adj2_elements(element_num_);
        for (ElementId e = 0; e < element_num_; ++e) {
            if (global_exit_signal_reached ||  timer.isTimeOut()) { return false; }

            const Vec<SetId>& E1 = elements_[e];
            adj2_elements.clear(true);
            for (SetId s : E1) {
                const Vec<SetId>& S1 = sets_[s];
                for (ElementId e2 : S1) {
                    if (e2 != e && !adj2_elements.isItemExist(e2)) {
                        adj2_elements.insert(e2);
                    }
                }
            }
            elements_hop2_[e] = adj2_elements.getItems();
        }

        sets_hop2_.clear(); sets_hop2_.resize(set_num_);
        ConsecutiveIdSet<SetId> adj2_sets(set_num_);
        for (SetId s = 0; s < set_num_; ++s) {
            if (global_exit_signal_reached || timer.isTimeOut()) { return false; }

            const Vec <ElementId>& S1 = sets_[s];
            adj2_sets.clear(true);
            for (ElementId e : S1) {
                const Vec<ElementId>& E1 = elements_[e];
                for (SetId s2 : E1) {
                    if (s2 != s && !adj2_sets.isItemExist(s2)) {
                        adj2_sets.insert(s2);
                    }
                }
            }
            sets_hop2_[s] = adj2_sets.getItems();
        }

        return is_hop2_neighbor_initialized_ = true;
    }


    Vec<SetId> SimplifiedSCInstance::solve_small_component_and_rebuild(long long max_time_limit) {
        constexpr SetId max_exact_solver_number = 22;

        auto solve_one_component = [&](SetId component_id) {
            const Vec<SetId>& set_ids = component_sets_[component_id];
            const SetId set_num = set_ids.size();
            if (set_num > max_exact_solver_number) { return Vec<SetId>(); }

            // 压缩元素编号
            UnorderedMap<ElementId, ElementId> element_to_index;
            ElementId index_mapped = 0;
            for (const SetId& s : set_ids) {
                const Vec<ElementId>& si = sets_[s];
                for (ElementId e : si) {
                    if (!element_to_index.contains(e)) {
                        element_to_index[e] = index_mapped++;
                    }
                }
            }

            const ElementId element_num = index_mapped;
            if (element_num > 32) { return Vec<SetId>(); }

            using Mask = uint64_t; Vec<Mask> set_masks(set_num);
            const Mask FULL_MASK = (Mask(1) << element_num) - 1;
            for (SetId i = 0; i < set_num; ++i) {
                SetId s = set_ids[i]; Mask mask = 0;
                for (ElementId e : sets_[s]) {
                    mask |= Mask(1) << element_to_index[e];
                }
                set_masks[i] = mask;

                if (mask == FULL_MASK) { return Vec<SetId>({ s }); }
            }

            SetId best_count = std::numeric_limits<SetId>::max(); Vec<SetId> best_res;
            goal::Func<void(SetId, Mask, Vec<SetId>&)> dfs =
                [&](SetId idx, Mask cover_mask, Vec<SetId>& picked) {
                if (cover_mask == FULL_MASK) {
                    if ((SetId)picked.size() < best_count) {
                        best_count = picked.size(); best_res = picked;
                    }
                    return;
                }

                //搜到底了，或者不可能再改进了
                if (idx == set_num || (SetId)picked.size() >= best_count) return;
                //单个集合覆盖的情况已经排除，至少为两个
                if (best_count == 2) { return; }
                // 不选 sets[idx]
                dfs(idx + 1, cover_mask, picked);

                // 选 sets[idx]
                picked.push_back(set_ids[idx]);
                dfs(idx + 1, cover_mask | set_masks[idx], picked);
                picked.pop_back();
            };

            Vec<SetId> path; path.reserve(set_num);
            dfs(0, Mask(0), path);

            return best_res;
        };

        Vec<std::pair<SetId, SetId>> comp_set_size(set_component_number_);
        for (SetId c = 0; c < set_component_number_; ++c) {
            SetId set_num = (SetId)component_sets_[c].size();
            comp_set_size[c] = std::make_pair(set_num, c);
        }
        std::sort(comp_set_size.begin(), comp_set_size.end());

        goal::Timer timer(max_time_limit * 1000.0);
        Vec<SetId> fixed_sets; fixed_sets.reserve(set_num_);
        for (SetId c = 0; c < set_component_number_; ++c) {
            if (global_exit_signal_reached || timer.isTimeOut()) { break; }
            if (comp_set_size[c].first > max_exact_solver_number) { break; }
            Vec<SetId> res = solve_one_component(comp_set_size[c].second);
            if (!res.empty()) { for (SetId s : res) fixed_sets.emplace_back(s); }
        }

        return fixed_sets;
    }

}