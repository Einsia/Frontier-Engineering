#include "greedy_solver.h"

namespace PACE2025_HS {
    Vec<SetId> GreedyGenerator::greedy_by_cover_count(long long max_time_limit) {
        struct CompareNode {
            SetId s_; ElementId dominate_count_ = 0;
            const bool operator < (const CompareNode& node) const {
                return dominate_count_ < node.dominate_count_;
            }
        };

        goal::Timer timer(max_time_limit * 1000.0);

        PriorityQueue<CompareNode>que;
        Vec<ElementId> cur_set_status(ins_.set_num_);
        for (SetId s = 0; s < ins_.set_num_; ++s) {
            cur_set_status[s] = ElementId(ins_.sets_[s].size());
            que.push({ s, cur_set_status[s] });
        }
        Vec<ElementId> is_element_coverd(ins_.element_num_, 0);
        Vec<SetId> is_set_picked(ins_.set_num_, 0);
        Vec<SetId> res; res.reserve(ins_.set_num_);
        ElementId coverd_element_count = 0;
        while (!que.empty()) {
            CompareNode tp = que.top(); que.pop();
            if (is_set_picked[tp.s_] || 
                tp.dominate_count_ != cur_set_status[tp.s_]) { continue; }

            //db2(tp.s_, tp.dominate_count_);

            res.emplace_back(tp.s_);
            is_set_picked[tp.s_] = true;

            //全局终止信号到达后，直接依次选取其余未被选中的集合
            if (global_exit_signal_reached || timer.isTimeOut()) { continue; }

            for (ElementId e : ins_.sets_[tp.s_]) {
                if (is_element_coverd[e]) { continue; }
                is_element_coverd[e] = true;
                ++coverd_element_count;
                for (SetId ns : ins_.elements_[e]) {
                    if (is_set_picked[ns]) { continue; }
                    if (--cur_set_status[ns] != 0) {
                        que.push({ ns, cur_set_status[ns] });
                    }
                }
            }

            if (coverd_element_count == ins_.element_num_) { break; }
        }

        return res;
    }

    Vec<SetId> GreedyGenerator::greedy_by_surprisal(long long max_time_limit) {
        goal::Timer timer(max_time_limit * 1000.0);

        struct CompareNode {
            SetId s_; double score_; Count version_;
            const bool operator < (const CompareNode& other) const {
                return score_ > other.score_ || score_ == other.score_ && s_ < other.s_;
            }
        };

        Vec<Count> set_versions(ins_.set_num_, 0);
        //每个集合当前的(未覆盖元素)元素惊喜度得分
        Vec<double> set_surprisal(ins_.set_num_, 1.0); 
        //每个集合当前的未覆盖元素数目
        Vec<ElementId> set_cover_count(ins_.set_num_, 0);
        PriorityQueue<CompareNode> que;

        // 初始得分计算
        for (SetId s = 0; s < ins_.set_num_; ++s) {
            set_cover_count[s] = ElementId(ins_.sets_[s].size());
            set_surprisal[s] = 1.0;
            for (ElementId e : ins_.sets_[s]) {
                SetId count = ins_.elements_[e].size();
                fatalif(count == 0, "error element");
                set_surprisal[s] *= 1.0 * (count - 1) / count;
            }
            //db3(s, set_surprisal[s], set_cover_count[s]);
            que.push({ s, set_surprisal[s] / set_cover_count[s], 0 });
        }

        Vec<ElementId> is_element_coverd(ins_.element_num_, 0);
        Vec<SetId> is_set_picked(ins_.set_num_, 0);
        Vec<SetId> res; res.reserve(ins_.set_num_);
        ElementId coverd_element_count = 0;
        while (!que.empty()) {
            CompareNode tp = que.top(); que.pop();
            if (tp.version_ != set_versions[tp.s_]) { continue; }

            res.push_back(tp.s_);
            is_set_picked[tp.s_] = true;

            //db2(tp.s_, tp.score_);

            //全局终止信号到达后，直接依次选取其余未被选中的集合
            if (global_exit_signal_reached || timer.isTimeOut()) { continue; }

            for (ElementId e : ins_.sets_[tp.s_]) {
                if (!is_element_coverd[e]) {
                    is_element_coverd[e] = true;
                    ++coverd_element_count;
                    SetId count = ins_.elements_[e].size();
                    fatalif(count == 0, "error element");
                    if (count > 1) {
                        double element_factor = 1.0 * count / (count - 1);
                        for (SetId ns : ins_.elements_[e]) {
                            if (!is_set_picked[ns] && --set_cover_count[ns] != 0) {
                                set_surprisal[ns] *= element_factor;
                                que.push({ ns, set_surprisal[ns] / set_cover_count[ns], ++set_versions[ns] });
                            }
                        }
                    }
                }
            }
            if (coverd_element_count == ins_.element_num_) { break; }
        }

        return res;
    }

    Vec<SetId> GreedyGenerator::greedy_by_pagerank(long long max_time_limit) {
        Vec<double> importance_score(ins_.set_num_);
        for (SetId s = 1; s < ins_.set_num_; ++s) {
            importance_score[s] = 1.0 / s;
        }

        struct CompareNode {
            SetId s_; double score_ = 0;
            const bool operator < (const CompareNode& node) const {
                return score_ < node.score_ || score_ == node.score_ && s_ < node.s_;
            }
        };

        goal::Timer timer(max_time_limit * 1000.0);

        PriorityQueue<CompareNode>que;
        Vec<double> cur_set_status(ins_.set_num_);
        for (SetId s = 0; s < ins_.set_num_; ++s) {
            cur_set_status[s] = 0.0;
            for (ElementId e : ins_.sets_[s]) {
                cur_set_status[s] += importance_score[ins_.elements_[e].size()];
            }

            que.push({ s, cur_set_status[s] });
        }

        Vec<ElementId> is_element_coverd(ins_.element_num_, 0);
        Vec<SetId> is_set_picked(ins_.set_num_, 0);
        Vec<SetId> res; res.reserve(ins_.set_num_);
        ElementId coverd_element_count = 0;
        while (!que.empty()) {
            CompareNode tp = que.top(); que.pop();
            if (is_set_picked[tp.s_] ||
                tp.score_ != cur_set_status[tp.s_]) {
                continue;
            }

            //db2(tp.s_, tp.score_);

            res.emplace_back(tp.s_);
            is_set_picked[tp.s_] = true;

            //全局终止信号到达后，直接依次选取其余未被选中的集合
            if (global_exit_signal_reached || timer.isTimeOut()) { continue; }

            for (ElementId e : ins_.sets_[tp.s_]) {
                if (is_element_coverd[e]) { continue; }
                is_element_coverd[e] = true;
                ++coverd_element_count;
                double score = importance_score[ins_.elements_[e].size()];
                for (SetId ns : ins_.elements_[e]) {
                    if (is_set_picked[ns]) { continue; }
                    cur_set_status[ns] -= score;
                    if (cur_set_status[ns] != 0.0) {
                        que.push({ ns, cur_set_status[ns] });
                    }
                }
            }

            if (coverd_element_count == ins_.element_num_) { break; }
        }

        return res;
    }
    
    Vec<SetId> GreedyGenerator::greedy_by_iterated_pagerank(Count max_iteration, long long max_time_limit) {
        goal::Timer timer(max_time_limit * 1000.0);
        //贪心一轮的时间如果太长，不如交给局部搜索去优化
        constexpr int max_one_iteration_time_limit = 5;//5s

        auto pagerank_iteration = [&](const Vec<double>& init_elements_score) {
            Vec<double> importance_score(ins_.set_num_);
            for (SetId s = 1; s < ins_.set_num_; ++s) {
                importance_score[s] = 1.0 / s;
            }

            struct CompareNode {
                SetId s_; double score_ = 0;
                const bool operator < (const CompareNode& node) const {
                    return score_ < node.score_ || score_ == node.score_ && s_ < node.s_;
                }
            };

            PriorityQueue<CompareNode>que;
            Vec<double> cur_set_status(ins_.set_num_);
            for (SetId s = 0; s < ins_.set_num_; ++s) {
                cur_set_status[s] = 0.0;
                for (ElementId e : ins_.sets_[s]) {
                    double score = importance_score[ins_.elements_[e].size()];
                    score *= init_elements_score[e];
                    cur_set_status[s] += score;
                }

                que.push({ s, cur_set_status[s] });
            }

            Vec<ElementId> is_element_coverd(ins_.element_num_, 0);
            Vec<SetId> is_set_picked(ins_.set_num_, 0);
            Vec<SetId> res; res.reserve(ins_.set_num_);
            ElementId coverd_element_count = 0;
            while (!que.empty()) {
                CompareNode tp = que.top(); que.pop();
                if (is_set_picked[tp.s_] ||
                    tp.score_ != cur_set_status[tp.s_]) {
                    continue;
                }

                //db2(tp.s_, tp.score_);

                res.emplace_back(tp.s_);
                is_set_picked[tp.s_] = true;

                //全局终止信号到达后，直接依次选取其余未被选中的集合
                if (global_exit_signal_reached || timer.isTimeOut()) { continue; }

                for (ElementId e : ins_.sets_[tp.s_]) {
                    if (is_element_coverd[e]) { continue; }
                    is_element_coverd[e] = true;
                    ++coverd_element_count;
                    double score = importance_score[ins_.elements_[e].size()];
                    score *= init_elements_score[e];
                    for (SetId ns : ins_.elements_[e]) {
                        if (is_set_picked[ns]) { continue; }
                        cur_set_status[ns] -= score;
                        if (cur_set_status[ns] != 0.0) {
                            que.push({ ns, cur_set_status[ns] });
                        }
                    }
                }

                if (coverd_element_count == ins_.element_num_) { break; }
            }

            return res;
        };

        Vec<double> init_elements_score(ins_.element_num_, 1.0);
        Vec<SetId> best_res, curr_res; int no_improve_times = 0;

        for (Count i = 0; i < max_iteration; ++i) {
            goal::Timer one_iter_timer;

            curr_res = pagerank_iteration(init_elements_score);

            if (best_res.empty() || curr_res.size() < best_res.size()) { 
                best_res = curr_res; no_improve_times = 0;
            }
            else if (++no_improve_times >= 2) { break; }

            logger_ << "Greedy Iteration #" << i << " -> " << "Current Size: " << curr_res.size() << std::endl;

            Vec<SetId> covered_times(ins_.element_num_, 0);
            SetId max_cover_times = 0;
            for (SetId s : curr_res) {
                for (ElementId e : ins_.sets_[s]) {
                    if (max_cover_times < ++covered_times[e]) {
                        max_cover_times = covered_times[e];
                    }
                }
            }
            Count tot_cover_times = 0;
            for (ElementId e = 0; e < ins_.element_num_; ++e) {
                tot_cover_times += covered_times[e];
            }
            for (ElementId e = 0; e < ins_.element_num_; ++e) {
                //init_elements_score[e] *= (1 + 1.0 / covered_times[e]);
                init_elements_score[e] *= 1.0 * max_cover_times / covered_times[e];
                //init_elements_score[e] = 0.5 * init_elements_score[e] + 0.5 * (std::sqrt(1.0 / covered_times[e]));
            }

            if (global_exit_signal_reached || timer.isTimeOut()) { break; }
            // Fixed max_iteration (16) and no-improvement limit replace wall-clock early exit.
        }

        return best_res;
    }
}
