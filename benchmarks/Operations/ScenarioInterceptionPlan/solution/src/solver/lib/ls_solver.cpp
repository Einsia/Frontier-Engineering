#include "ls_solver.h"

namespace PACE2025_HS {
	constexpr uint32_t MAX_RANDOM_PICK_NUMBER = 10000000 + 10;
	static uint32_t pick_threshold[MAX_RANDOM_PICK_NUMBER];
	void init_threshold_lut() {
		for (int i = 1; i < MAX_RANDOM_PICK_NUMBER; ++i) {
			pick_threshold[i] = (UINT32_MAX / i) >> 2;
		}
	}

	WVNS4SCP::WVNS4SCP(const SimplifiedSCInstance& ins, const Vec<SetId>& init_sol, int seed) :
		ins_(ins), logger_(ins_.logger_), element_num_(ins.element_num_),
		set_num_(ins.set_num_), elements_(ins.elements_), sets_(ins.sets_),
		current_sets_(set_num_), uncovered_elements_(element_num_), rand_seed_(seed), rander(seed),
		is_hop2_neighbor_initialized_(ins.is_hop2_neighbor_initialized_),
		elements_hop2_(ins.elements_hop2_), sets_hop2_(ins.sets_hop2_),
		set_component_number_(ins.set_component_number_),
		set_component_id_map_(ins.set_component_id_map_),
		element_component_id_map_(ins.element_component_id_map_),
		set_component_size_map_(ins.set_component_size_map_),
		component_sets_(ins.component_sets_), 
		component_elements_(ins.component_elements_) {

		init_threshold_lut();

		elements_cross_cs_.resize(element_num_);
		Vec<ElementId> tmp_ue(element_num_, 1);		//各个元素是否被覆盖
		for (SetId s : init_sol) {
			current_sets_.insert(s);				//加入已选中集合
			for (ElementId e : sets_[s]) {
				tmp_ue[e] = 0;
				elements_cross_cs_[e].insert(s);	//加入元素与选中集合的交集
			}
		}

		max_weight_value_ = ELEMENT_INITIAL_WEIGHT;
		weight_values_ = goal::Array<Weight>(element_num_, ELEMENT_INITIAL_WEIGHT);
		current_uncovered_weight_ = 0;
		sets_cross_ue_.resize(set_num_);
		for (ElementId e = 0; e < element_num_; ++e) {
			if (tmp_ue[e] == 1) {
				//fatalif(true, "There are covering nodes in the initial solution.");
				uncovered_elements_.insert(e);
				for (SetId s : elements_[e]) {
					sets_cross_ue_[s].insert(e);	//加入集合与未覆盖元素的交集
				}
				current_uncovered_weight_ += weight_values_[e];
			}
		}

		init_delta_values();
		update_optimal_solution();
	}

	void WVNS4SCP::init_delta_values() {
		delta_values_ = goal::Array<Weight>(set_num_, Weight(0));
		remove_delta_values_.clear();
		for (SetId s = 0; s < set_num_; ++s) {
			if (current_sets_.isItemExist(s)) {
				//若s是选中结合，对应值为->所有被覆盖的点中，仅被i覆盖的点的权值和
				//delta_values_[s] 等于删除s会导致多少未覆盖权重
				for (ElementId e : sets_[s]) {
					//对于所有s可覆盖的节点p，若其只被覆盖一次，则说明 e 只被 s 覆盖
					if (elements_cross_cs_[e].size() == 1) {
						delta_values_[s] += weight_values_[e];
					}
				}
				remove_delta_values_.insert({ delta_values_[s], s });
			}
			else {
				//非选中集合 s 对应的值即为 -> s能覆盖但是仍未被覆盖元素的权值和
				for (ElementId e : sets_cross_ue_[s]) {
					delta_values_[s] += weight_values_[e];
				}
			}
		}
	}

	void WVNS4SCP::increase_uncovered_element_weight(ElementId e, Weight inc_w) {
		//fatalif(!uncovered_elements_.isItemExist(e), "element not found.");
		current_uncovered_weight_ += inc_w;
		weight_values_[e] += inc_w;
		if (max_weight_value_ < weight_values_[e]) {
			max_weight_value_ = weight_values_[e];
		}
		for (SetId s : elements_[e]) {
			delta_values_[s] += inc_w;
			//fatalif(current_sets_.isItemExist(s), "[ERROR] set %d should not be centered.", s);
		}
	}

	void WVNS4SCP::increase_arbitrary_element_weight(ElementId e, Weight inc_w) {
		weight_values_[e] += inc_w;
		if (max_weight_value_ < weight_values_[e]) {
			max_weight_value_ = weight_values_[e];
		}

		if (uncovered_elements_.isItemExist(e)) {
			current_uncovered_weight_ += inc_w;
			for (SetId s : elements_[e]) {
				delta_values_[s] += inc_w;
				//fatalif(current_sets_.isItemExist(s), "[ERROR] set %d should not be centered.", s);
			}
		}
		else {
			if (elements_cross_cs_[e].size() == 1) {
				SetId single_domi_s = *elements_cross_cs_[e].begin();
				Weight& delta = delta_values_[single_domi_s];
				remove_delta_values_.erase({ delta, single_domi_s });
				delta += inc_w;
				remove_delta_values_.insert({ delta, single_domi_s });
			}
		}

	}

	void WVNS4SCP::reset_element_weights() {
		max_weight_value_ = ELEMENT_INITIAL_WEIGHT;
		weight_values_ = goal::Array<Weight>(element_num_, ELEMENT_INITIAL_WEIGHT);
		current_uncovered_weight_ = 0;
		for (auto i = 0; i < uncovered_elements_.size(); ++i) {
			ElementId e = uncovered_elements_.itemAt(i);
			current_uncovered_weight_ += weight_values_[e];
		}
		init_delta_values();
	}

	void WVNS4SCP::smooth_element_weights() {
		for (ElementId e = 0; e < element_num_; ++e) {
			Weight w = weight_values_[e];
			//if (w > 1) { increase_arbitrary_element_weight(e, w / 2 - w); }
			if (w > 1) { increase_arbitrary_element_weight(e, Weight(std::sqrt(w)) - w); }
		}
		max_weight_value_ /= 2;
	}

	WVNS4SCP::SwapMoveAction WVNS4SCP::find_pair(
		Count curr_iter, const SwapMoveAction& last_operation, 
		const SwapMoveAction& last_operation2,
		TabuStrategyStrategy tabu_strategy) {
		if (uncovered_elements_.empty()) {
			logger_ << "No vertex uncorvered." << std::endl;
			return { -1, -1, -MAX_WEIGHT_VALUE };
		}

		if (_modified_values_.empty()) {
			_modified_values_.resize(set_num_, { -1, -1 });
			__operated_sets_.reserve(set_num_);
		}
		BtreeSet<DeltaSetPair> modified_items;

		Weight* __restrict delta_ptr = delta_values_.begin();
		Weight* __restrict weight_ptr = weight_values_.begin();
		auto try_to_open_center = [&](SetId add_s) {
			Weight modified_min_delta = MAX_WEIGHT_VALUE;
			++_curr_modified_version_;
			for (ElementId e : sets_[add_s]) {
				if (elements_cross_cs_[e].size() == 1) {
					//single_domi_s一定是当前的选中集合
					SetId single_domi_s = *elements_cross_cs_[e].begin();
					Weight& delta = delta_ptr[single_domi_s];

					if (_modified_values_[single_domi_s].first != _curr_modified_version_) {
						_modified_values_[single_domi_s].first = _curr_modified_version_;
						_modified_values_[single_domi_s].second = delta;
						__operated_sets_.emplace_back(single_domi_s);
					}

					delta -= weight_ptr[e];
					if (modified_min_delta > delta) {
						modified_min_delta = delta;
					}
				}
			}
			
			const auto& first_eval = remove_delta_values_.begin();
			if (_modified_values_[first_eval->s()].first != _curr_modified_version_ &&
				modified_min_delta > first_eval->delta()) { return; }

			for (SetId ms : __operated_sets_) {
				Weight delta = delta_ptr[ms];
				if (delta == modified_min_delta) {
					modified_items.insert({ delta ,ms });
				}
			}
		};
		auto recover_modified_sets = [&]() {
			for (SetId ms : __operated_sets_) {
				delta_ptr[ms] = _modified_values_[ms].second;
			}
			__operated_sets_.clear();
			modified_items.clear();
		};

		Weight best_cost = MAX_WEIGHT_VALUE; int pick_t = 0; Count min_set_age = MAX_COUNT_VALUE;
		SwapMoveAction best_action = { -1, -1, -MAX_WEIGHT_VALUE };

		auto search_add_set = [&](SetId add_s) {
			//fatalif(current_sets_.isItemExist(add_s), "[FindPair-ERROR] %d should not be centered.", add_s);

			if (tabu_strategy == PACE2025_HS::WVNS4SCP::PairTabu && add_s == last_operation.rev_s_) { return; }
			if (tabu_strategy == PACE2025_HS::WVNS4SCP::AddTabu) {
				if (add_s == last_operation.rev_s_ || add_s == last_operation2.rev_s_) { return; }
			}

			Weight cost_reduced = current_uncovered_weight_ - delta_ptr[add_s];
			try_to_open_center(add_s);
			
			auto search_remove_set = [&](const BtreeSet<DeltaSetPair>& d_values) {
				Weight min_delta_val = MAX_WEIGHT_VALUE; Count tried_num = 0;
				Count age_s = set_add_operation_age_[add_s];
				for (const DeltaSetPair& dsp : d_values) {
					Weight rev_delta = dsp.delta(); SetId rev_s = dsp.s();

					if (_modified_values_[rev_s].first == _curr_modified_version_ &&
						_modified_values_[rev_s].second == rev_delta) { continue; }

					if (min_delta_val < rev_delta) { break; }

					//age_s = set_add_operation_age_[rev_s];
					Weight cost = cost_reduced + (min_delta_val = rev_delta);

					bool is_tabu_move = false;

					switch (tabu_strategy) {
					case PACE2025_HS::WVNS4SCP::RemoveTabu:
						//1. 基于加点的两轮禁忌策略：不考虑移除 [前两轮] 加的集合
						is_tabu_move = (cost != 0 && (rev_s == last_operation.add_s_ || rev_s == last_operation2.add_s_));
						break;
					case PACE2025_HS::WVNS4SCP::PairTabu:
						//2. 基于删加的单轮禁忌策略：不考虑 [上一轮] 操作的集合
						is_tabu_move = (cost != 0 && (add_s == last_operation.rev_s_ || rev_s == last_operation.add_s_));
						break;
					case PACE2025_HS::WVNS4SCP::AddTabu:
						is_tabu_move = false;
						break;
					default:
						break;
					}
					
					if (is_tabu_move == false) {
						if (best_cost > cost) {
							min_set_age = age_s;
							best_cost = cost; pick_t = 0;
							best_action = { add_s, rev_s, cost };
						}
						else if (best_cost == cost) {
							if (min_set_age > age_s) {
								min_set_age = age_s; pick_t = 0;
								best_action = { add_s, rev_s, cost };
							}
							else if (min_set_age == age_s) {
								if ((mini_rander() >> 2) <= pick_threshold[++pick_t]) {
									best_action = { add_s, rev_s, cost };
								}
							}
						}

						if (++tried_num > MAX_BEST_REMOVE_TRY_NUM) { break; }
					}
				}
				return min_delta_val;
			};

			Weight min_delta_val = search_remove_set(remove_delta_values_);
			if (modified_items.begin()->delta() <= min_delta_val) {
				search_remove_set(modified_items);
			}

			recover_modified_sets();
		};

		int slt = uncovered_elements_.randomPick(rander);
		if (rander.pick(0, 100) < 5) {
			ElementId idx = rander.pick(0, (int)elements_[slt].size());
			search_add_set(elements_[slt][idx]);
		}
		else {
			for (SetId add_s : elements_[slt]) {
				search_add_set(add_s);
			}
		}

		return best_action;
	}

	void WVNS4SCP::add_to_open_set(SetId add_s) {
		current_sets_.insert(add_s);
		current_uncovered_weight_ -= delta_values_[add_s];
		remove_delta_values_.insert({ delta_values_[add_s], add_s });

		Weight* __restrict delta_ptr = delta_values_.begin();
		Weight* __restrict weight_ptr = weight_values_.begin();
		if (_modified_values_.empty()) {
			_modified_values_.resize(set_num_, { -1, -1 });
			__operated_sets_.reserve(set_num_);
		}
		++_curr_modified_version_;

		for (ElementId e : sets_[add_s]) {
			if (elements_cross_cs_[e].size() == 1) {
				//如果原来元素 e 只被集合一个集合覆盖，则新增 add_s 后被多个集合覆盖
				//需要更新原来覆盖元素 e 的集合的 delta_values值
				SetId pre_domi_s = *elements_cross_cs_[e].begin();
				Weight& delta = delta_values_[pre_domi_s];

				if (_modified_values_[pre_domi_s].first != _curr_modified_version_) {
					_modified_values_[pre_domi_s].first = _curr_modified_version_;
					_modified_values_[pre_domi_s].second = delta;
					__operated_sets_.emplace_back(pre_domi_s);
				}

				//remove_delta_values_.erase({ delta, pre_domi_s });
				delta -= weight_values_[e];
				//remove_delta_values_.insert({ delta, pre_domi_s });
			}
			else if (elements_cross_cs_[e].size() == 0) {
				//如果原来元素 e 未被任何集合覆盖，则新增 add_s 后导致 e 被覆盖
				//需要更新所有可覆盖元素 e 的集合的 delta_values值
				//  -> 覆盖元素 e 的集合 s 原来一定都未被选中
				//  -> 选中集合 s 后不再导致元素 e 被新覆盖
				for (SetId s : elements_[e]) {
					//集合 add_s 的delta_values值保持不变（性质相反）
					if (s != add_s) {
						delta_values_[s] -= weight_values_[e];
					}
				}
			}
		}

		//添加集合 add_s 对辅助数据结构的影响
		for (ElementId e : sets_[add_s]) {
			//元素 e 与选中集合的交集新增 add_s
			elements_cross_cs_[e].insert(add_s);
			//如果元素 e 之前未被覆盖，则从未覆盖集合中删去
			//并更新 [能覆盖e的集合] 与 [未覆盖元素集合] 的交集 (删去 e)
			if (uncovered_elements_.isItemExist(e)) {
				uncovered_elements_.eraseItem(e);
				for (SetId s : elements_[e]) {
					sets_cross_ue_[s].erase(e);
				}
			}
		}

		for (SetId ms : __operated_sets_) {
			remove_delta_values_.erase({ _modified_values_[ms].second, ms });
			remove_delta_values_.insert({ delta_ptr[ms], ms });
		}
		__operated_sets_.clear();
	}

	void WVNS4SCP::remove_to_close_set(SetId rev_s) {
		//fatalif(!current_sets_.isItemExist(rev_s), "can not remove a un-picked set!");

		//fatalif(!component_remove_delta_values_.contains({ delta_values_[rev_s] ,rev_s }), "errorB");
		remove_delta_values_.erase({ delta_values_[rev_s] ,rev_s });
		current_uncovered_weight_ += delta_values_[rev_s];
		current_sets_.eraseItem(rev_s);

		//删除集合 rev_s 对辅助数据结构的影响
		for (ElementId e : sets_[rev_s]) {
			//如果删除集合 rev_ s 后导致元素 e 不能被覆盖，则将元素 e 插入未被覆盖集合
			//并更新 [能覆盖e的集合] 与 [未覆盖元素集合] 的交集 (添加 e)
			elements_cross_cs_[e].erase(rev_s);
			if (elements_cross_cs_[e].empty()) {
				uncovered_elements_.insert(e);
				for (SetId s : elements_[e]) {
					sets_cross_ue_[s].insert(e);
				}
			}
		}

		Weight* __restrict delta_ptr = delta_values_.begin();
		Weight* __restrict weight_ptr = weight_values_.begin();
		if (_modified_values_.empty()) {
			_modified_values_.resize(set_num_, { -1, -1 });
			__operated_sets_.reserve(set_num_);
		}
		++_curr_modified_version_;

		for (ElementId e : sets_[rev_s]) {
			//如果元素 e [当前（删除 rev_s 后）]只被一个元素覆盖
			//则更新唯一覆盖它的集合的delta_values值
			if (elements_cross_cs_[e].size() == 1) {
				SetId single_domi_s = *elements_cross_cs_[e].begin();
				Weight& delta = delta_ptr[single_domi_s];

				if (_modified_values_[single_domi_s].first != _curr_modified_version_) {
					_modified_values_[single_domi_s].first = _curr_modified_version_;
					_modified_values_[single_domi_s].second = delta;
					__operated_sets_.emplace_back(single_domi_s);
				}

				//remove_delta_values_.erase({ delta, single_domi_s });
				delta += weight_ptr[e];
				//remove_delta_values_.insert({ delta, single_domi_s });
			}
			//如果元素 e [当前（删除 rev_s 后）]不再被覆盖
			//则更新可覆盖它的集合的delta_values值
			else if (elements_cross_cs_[e].size() == 0) {
				for (SetId s : elements_[e]) {
					//集合 rev_s 的delta_values值保持不变（性质相反）
					if (s != rev_s) {
						delta_ptr[s] += weight_ptr[e];
					}
				}
			}
		}

		for (SetId ms : __operated_sets_) {
			remove_delta_values_.erase({ _modified_values_[ms].second, ms });
			remove_delta_values_.insert({ delta_ptr[ms], ms });
		}
		__operated_sets_.clear();
	}

	void WVNS4SCP::make_swap_move(SetId add_s, SetId rev_s) {
		add_to_open_set(add_s);
		remove_to_close_set(rev_s);
	}

	void WVNS4SCP::make_swap_move_faster(SetId add_s, SetId rev_s) {
		current_sets_.insert(add_s);
		current_uncovered_weight_ -= delta_values_[add_s];

		Weight* __restrict delta_ptr = delta_values_.begin();
		Weight* __restrict weight_ptr = weight_values_.begin();
		if (_modified_values_.empty()) {
			_modified_values_.resize(set_num_, { -1, -1 });
			__operated_sets_.reserve(set_num_);
		}
		++_curr_modified_version_;

		for (ElementId e : sets_[add_s]) {
			if (elements_cross_cs_[e].size() == 1) {
				//如果原来元素 e 只被集合一个集合覆盖，则新增 add_s 后被多个集合覆盖
				//需要更新原来覆盖元素 e 的集合的 delta_values值
				SetId pre_domi_s = *elements_cross_cs_[e].begin();
				Weight& delta = delta_values_[pre_domi_s];

				if (_modified_values_[pre_domi_s].first != _curr_modified_version_) {
					_modified_values_[pre_domi_s].first = _curr_modified_version_;
					_modified_values_[pre_domi_s].second = delta;
					__operated_sets_.emplace_back(pre_domi_s);
				}

				delta -= weight_values_[e];
			}
			else if (elements_cross_cs_[e].size() == 0) {
				//如果原来元素 e 未被任何集合覆盖，则新增 add_s 后导致 e 被覆盖
				//需要更新所有可覆盖元素 e 的集合的 delta_values值
				//  -> 覆盖元素 e 的集合 s 原来一定都未被选中
				//  -> 选中集合 s 后不再导致元素 e 被新覆盖
				for (SetId s : elements_[e]) {
					//集合 add_s 的delta_values值保持不变（性质相反）
					if (s != add_s) { delta_values_[s] -= weight_values_[e]; }
				}
			}
		}

		//添加集合 add_s 对辅助数据结构的影响
		for (ElementId e : sets_[add_s]) {
			//元素 e 与选中集合的交集新增 add_s
			elements_cross_cs_[e].insert(add_s);
			//如果元素 e 之前未被覆盖，则从未覆盖集合中删去
			//并更新 [能覆盖e的集合] 与 [未覆盖元素集合] 的交集 (删去 e)
			if (uncovered_elements_.isItemExist(e)) {
				uncovered_elements_.eraseItem(e);
				for (SetId s : elements_[e]) {
					sets_cross_ue_[s].erase(e);
				}
			}
		}

		current_uncovered_weight_ += delta_values_[rev_s];
		current_sets_.eraseItem(rev_s);

		//删除集合 rev_s 对辅助数据结构的影响
		for (ElementId e : sets_[rev_s]) {
			//如果删除集合 rev_ s 后导致元素 e 不能被覆盖，则将元素 e 插入未被覆盖集合
			//并更新 [能覆盖e的集合] 与 [未覆盖元素集合] 的交集 (添加 e)
			elements_cross_cs_[e].erase(rev_s);
			if (elements_cross_cs_[e].empty()) {
				uncovered_elements_.insert(e);
				for (SetId s : elements_[e]) {
					sets_cross_ue_[s].insert(e);
				}
			}
		}

		for (ElementId e : sets_[rev_s]) {
			//如果元素 e [当前（删除 rev_s 后）]只被一个元素覆盖
			//则更新唯一覆盖它的集合的delta_values值
			if (elements_cross_cs_[e].size() == 1) {
				SetId single_domi_s = *elements_cross_cs_[e].begin();
				Weight& delta = delta_ptr[single_domi_s];

				if (_modified_values_[single_domi_s].first != _curr_modified_version_) {
					_modified_values_[single_domi_s].first = _curr_modified_version_;
					_modified_values_[single_domi_s].second = delta;
					__operated_sets_.emplace_back(single_domi_s);
				}

				delta += weight_ptr[e];
			}
			//如果元素 e [当前（删除 rev_s 后）]不再被覆盖
			//则更新可覆盖它的集合的delta_values值
			else if (elements_cross_cs_[e].size() == 0) {
				for (SetId s : elements_[e]) {
					//集合 rev_s 的delta_values值保持不变（性质相反）
					if (s != rev_s) { delta_ptr[s] += weight_ptr[e]; }
				}
			}
		}

		bool add_s_added = false, rev_s_removed = false;
		for (SetId ms : __operated_sets_) {
			if (ms != add_s) { remove_delta_values_.erase({ _modified_values_[ms].second, ms }); }
			else { add_s_added = true; }
			if (ms != rev_s) { remove_delta_values_.insert({ delta_ptr[ms], ms }); }
			else { rev_s_removed = true; }
		}
		__operated_sets_.clear();

		if (add_s_added == false) { remove_delta_values_.insert({ delta_ptr[add_s], add_s }); }
		if (rev_s_removed == false) { remove_delta_values_.erase({ delta_ptr[rev_s], rev_s }); }
	}

	Count WVNS4SCP::remove_redundant_sets() {
		UnorderedSet<SetId> redundant_sets;
		for (auto i = 0; i < current_sets_.size(); ++i) {
			SetId s = current_sets_.itemAt(i);
			if (delta_values_[s] == 0) {
				redundant_sets.insert(s);
			}
		}

		if (redundant_sets.empty()) { return Count(0); }

		Count remove_set_count = 0;
		Vec<SetId> outdated_sets;
		outdated_sets.reserve(redundant_sets.size());
		while (!redundant_sets.empty()) {
			SetId rev_s = *redundant_sets.begin();
			if (delta_values_[rev_s] == 0) {
				++remove_set_count;
				remove_to_close_set(rev_s);
			}
			redundant_sets.erase(rev_s);
		}
		return remove_set_count;
	}

	bool WVNS4SCP::update_optimal_solution() {
		if (uncovered_elements_.empty() && (history_optimal_.empty() ||
			current_sets_.size() < history_optimal_.size())) {
			history_optimal_ = current_sets_.getItems();
			return true;
		}
		return false;
	}

	void WVNS4SCP::load_optimal_solution(const Vec<SetId>& sol) {
		UnorderedSet<SetId> sol_sets(sol.begin(), sol.end());
		Vec<SetId> cur_sets = current_sets_.getItems();
		for (SetId s : cur_sets) {
			if (!sol_sets.contains(s)) {
				remove_to_close_set(s);
			}
		}
		for (SetId s : sol) {
			if (!current_sets_.isItemExist(s)) {
				add_to_open_set(s);
			}
		}
	}

	Vec<SetId> WVNS4SCP::solve(Count max_iteration, long long time_out_sec) {
		logger_
			<< "WVNS Solving -> " << " Set Num: " << set_num_
			<< " | " << "Element Num: " << element_num_
			<< " | Seed: " << rand_seed_ << std::endl;

		if (current_sets_.empty()) { return history_optimal_; }

		auto reach_local_optimal = [&](ElementId last_uncoverd_count, Weight last_uncoverd_weight) {
			//总是加权
			//return uncovered_elements_.size() > 0;
			//以未覆盖点数判断局部最优
			return uncovered_elements_.size() >= last_uncoverd_count;
			//以未覆盖权重判断局部最优
			return current_uncovered_weight_ >= last_uncoverd_weight;
			//以未覆盖点数和未覆盖权重判断局部最优
			return uncovered_elements_.size() >= last_uncoverd_count ||
				uncovered_elements_.size() == last_uncoverd_count && current_uncovered_weight_ >= last_uncoverd_weight;
			};

		set_add_operation_age_ = Vec<Count>(set_num_, 1);
		Count total_iterations = 0; goal::Timer timer(time_out_sec * 1000.0);
		do {
			SetId last_removed_set = -1, last_goal_component = -1;
			while (uncovered_elements_.size() == 0) {
				remove_to_close_set(last_removed_set = current_sets_.randomPick(rander));
				last_goal_component = set_component_id_map_[last_removed_set];
				set_add_operation_age_ = Vec<Count>(set_num_, 1);
				logger_
					<< "Local Search -> Current Best: " << history_optimal_.size() + ins_.fixed_set_number()
					<< " | Next Optimizing: " << current_sets_.size() + ins_.fixed_set_number()
					<< " | Uncover: " << uncovered_elements_.size()
					<< " | Time: " << timer.elapsedSeconds() << std::endl;
			}

			UnorderedSet<SetId> changed_status_sets; changed_status_sets.insert(last_removed_set);
			auto check_and_recover_component = [&](SetId add_s, SetId rev_s) {
				if (changed_status_sets.contains(add_s)) {
					changed_status_sets.erase(add_s);
				}
				else { changed_status_sets.insert(add_s); }

				//手动关闭之前的连通分量: 恢复到之前的解
				SetId rev_component_id = set_component_id_map_[rev_s];
				if (rev_component_id != last_goal_component) {
					bool is_last_component_solved = true;
					for (ElementId i = 0; i < uncovered_elements_.size(); ++i) {
						ElementId e = uncovered_elements_.itemAt(i);
						if (element_component_id_map_[e] == last_goal_component) {
							is_last_component_solved = false; break;
						}
					}
					if (!is_last_component_solved) {
						for (SetId cs : changed_status_sets) {
							if (current_sets_.isItemExist(cs)) {
								remove_to_close_set(cs);
							}
							else { add_to_open_set(cs); }
						}
					}
					last_goal_component = rev_component_id;
					changed_status_sets.clear();
				}

				if (changed_status_sets.contains(rev_s)) {
					changed_status_sets.erase(rev_s);
				}
				else { changed_status_sets.insert(rev_s); }
			};

			SwapMoveAction last_action = { -1, -1, -MAX_WEIGHT_VALUE };
			SwapMoveAction last_action2 = { -1, -1, -MAX_WEIGHT_VALUE };
			for (int iter = 1; iter <= max_iteration && !uncovered_elements_.empty(); ++iter, ++total_iterations) {
				if (global_exit_signal_reached || timer.isTimeOut()) {
					logger_
						<< "Local Search Final Status -> Iteration: " << iter
						<< " | Uncover: " << uncovered_elements_.size()
						<< " | Cost: " << current_uncovered_weight_
						<< " | Max Weight: " << max_weight_value_
						<< std::endl;
					break;
				}

				ElementId last_uncoverd_count = (ElementId)uncovered_elements_.size();
				Weight last_uncoverd_weight = current_uncovered_weight_;

				TabuStrategyStrategy tabu_strategy = TabuStrategyStrategy::PairTabu;
				SwapMoveAction best_swap = find_pair(iter, last_action, last_action2, tabu_strategy);
				SetId add_s = best_swap.add_s_, rev_s = best_swap.rev_s_;

				if (add_s < 0) {
					last_action2 = last_action;
					last_action = { -1, -1, -MAX_WEIGHT_VALUE };
					continue;
				}

				/*logger_
					 << "Iteration #" << iter << " -> "
					 << "Add: " << add_s << " | Remove: " << rev_s
					 << " | Uncover: " << uncovered_elements_.size()
					 << " | Cost: " << best_swap.cost_
					<< " | Local: " << reach_local_optimal(last_uncoverd_count, last_uncoverd_weight)
					<< " | Max Weight: " << max_weight_value_
					<< std::endl;*/

				make_swap_move_faster(add_s, rev_s);

				//fatalif(best_swap.cost_ != current_uncovered_weight_, "Obj calc ERROR!");

				if (set_component_number_ > 1) {
					check_and_recover_component(add_s, rev_s);
				}

				set_add_operation_age_[add_s] = iter;
				set_add_operation_age_[rev_s] = iter;
				last_action2 = last_action;
				last_action = best_swap;

				update_optimal_solution();

				if (reach_local_optimal(last_uncoverd_count, last_uncoverd_weight)) {
					ElementId uncoverd_count = (ElementId)uncovered_elements_.size();
					/*for (ElementId i = 0; i < uncoverd_count; ++i) {
						ElementId e = uncovered_elements_.itemAt(i);
						increase_uncovered_element_weight(e, 1);
					}*/
					//随机加权
					/*ElementId e = uncovered_elements_.itemAt(rander.pick(0, uncoverd_count));
					increase_uncovered_element_weight(e, 1);*/

					if (ins_.graph_density_ > FULL_WEIGHT_DENSITY_THRESHOLD) {
						for (ElementId i = 0; i < uncoverd_count; ++i) {
							ElementId e = uncovered_elements_.itemAt(i);
							increase_uncovered_element_weight(e, 1);
						}
					}
					else {
						//随机加权
						ElementId e = uncovered_elements_.itemAt(rander.pick(0, uncoverd_count));
						increase_uncovered_element_weight(e, 1);
					}
				}
			}
		} while (!global_exit_signal_reached && !timer.isTimeOut());

		//load_optimal_solution(history_optimal_);

		Count redundant_set_num = remove_redundant_sets();
		if (redundant_set_num > 0) {
			update_optimal_solution();
			logger_ << "Local Search -> Remove Redundant Set Number: " << redundant_set_num << std::endl;
		}

		logger_
			<< "Local Search End -> Iterations: " << total_iterations
			<< " | Time: " << timer.elapsedSeconds()
			<< " | Iter/Sec: " << total_iterations / timer.elapsedSeconds() << std::endl;

		return history_optimal_;
	};

}
