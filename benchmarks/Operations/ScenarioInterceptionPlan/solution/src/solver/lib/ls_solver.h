#pragma once

#include "instance.h"
#include "solver/tools/Arr.h"

namespace PACE2025_HS {
	struct SingleVertexTabuTable {
		Vec<Count>tabu_status_;			//禁忌状态
		Count table_len_;				//禁忌表长度

		SingleVertexTabuTable(int _vNum) { tabu_status_ = Vec<Count>(table_len_ = _vNum, 0); }

		void clear() { tabu_status_ = Vec<Count>(table_len_, 0); }
		void update_tabu_table(int u, int curr_iter) { tabu_status_[u] = curr_iter; }
		bool is_tabu(int u, int curr_iter) const { return tabu_status_[u] >= curr_iter; }
	};

	struct WVNS4SCP {
		struct DeltaSetPair {
			uint64_t comparator_;
			DeltaSetPair(Weight d, SetId s) : comparator_(((uint64_t)d << 32) | s) {}
			const bool operator < (const DeltaSetPair& p) const {
				return comparator_ < p.comparator_;
			}
			SetId s() const { return SetId(comparator_ & 0xFFFFFFFF); }
			Weight delta() const { return Weight(int32_t(comparator_ >> 32)); }
		};

		struct SwapMoveAction { SetId add_s_, rev_s_; Weight cost_; };

		enum TabuStrategyStrategy { PairTabu, RemoveTabu, AddTabu };

		const SimplifiedSCInstance& ins_;
		Log logger_;
		const ElementId& element_num_;
		const SetId& set_num_;
		// 每个元素由哪些集合覆盖
		const Vec<Vec<SetId>>& elements_;
		// 每个集合可覆盖哪些元素
		const Vec<Vec<ElementId>>& sets_;
		const SetId &set_component_number_;
		const Vec<SetId>& set_component_id_map_;
		const Vec<SetId>& set_component_size_map_;
		const Vec<SetId>& element_component_id_map_;
		const Vec<Vec<SetId>> &component_sets_;
		const Vec<Vec<ElementId>> &component_elements_;

		//各个元素与集合的二跳邻居（不包含自身!!!）
		const bool is_hop2_neighbor_initialized_;
		const Vec<Vec<ElementId>>& elements_hop2_;
		const Vec<Vec<SetId>>& sets_hop2_;

		
		const double FULL_WEIGHT_DENSITY_THRESHOLD = 0.02;
		//删除节点时评估的最大等价最优集合数目
		const Count MAX_BEST_REMOVE_TRY_NUM = 4;
		//每个元素的初始权重
		const Weight ELEMENT_INITIAL_WEIGHT = 16;
		//权重平滑阈值（暂未使用）
		const Weight WEIGHT_SMOOTH_THRESHOLD = (1ll << 16);

		const int rand_seed_;
		goal::Random rander;
		std::minstd_rand mini_rander;

		ConsecutiveIdSet<SetId> current_sets_;				//当前被选中的集合（解）
		Weight current_uncovered_weight_;					//当前未被覆盖点的总权重
		ConsecutiveIdSet<ElementId> uncovered_elements_;	//当前的未被覆盖点集合
		Vec<UnorderedSet<ElementId>> sets_cross_ue_;		//维护各个集合可覆盖集合与未被覆盖点集合的交集
		Vec<UnorderedSet<ElementId>> elements_cross_cs_;	//维护各个元素的覆盖集合与当前选中的集合的交集

		Vec<SetId> history_optimal_;

		Weight max_weight_value_;
		goal::Array<Weight>weight_values_;					//元素权重 
		/* -- 中间辅助数据 --
			1. 对于已选中集合 i : delta_values_[i] 表示删除集合 i 会导致有多少新增未覆盖权重
			2. 对于未选中集合 i : delta_values_[i] 表示添加集合 i 会产生新覆盖多少未覆盖权重
		*/
		goal::Array<Weight> delta_values_;
		//维护 删除已选中集合的代价：加速评估，但是带来了更新的代价
		BtreeSet<DeltaSetPair> remove_delta_values_;
		//集合最近一次被选中的迭代次数
		Vec<Count> set_add_operation_age_;

		Count _curr_modified_version_ = 0;
		Vec<std::pair<Count, Weight>> _modified_values_;
		Vec<Count> __operated_sets_;

		WVNS4SCP(const SimplifiedSCInstance& ins, const Vec<SetId>& init_sol, int seed);

		void init_delta_values();
		void increase_uncovered_element_weight(ElementId e, Weight inc_w);
		void increase_arbitrary_element_weight(ElementId e, Weight inc_w);

		void reset_element_weights();
		void smooth_element_weights();

		//寻找交换动作
		SwapMoveAction find_pair(Count curr_iter, 
			const SwapMoveAction& last_operation,
			const SwapMoveAction& last_operation2,
			TabuStrategyStrategy tabu_strategy);
		//添加一个未选中集合
		void add_to_open_set(SetId add_s);
		//删除一个已选中集合
		void remove_to_close_set(SetId rev_s);
		//执行一次交换动作
		void make_swap_move(SetId add_s, SetId rev_s);
		//执行一次交换动作，比make_swap_move()快约10%
		void make_swap_move_faster(SetId add_s, SetId rev_s);

		Count remove_redundant_sets();

		bool update_optimal_solution();

		void load_optimal_solution(const Vec<SetId>& sol);

		Vec<SetId> solve(Count max_iteration, long long time_out_sec);
	};
}