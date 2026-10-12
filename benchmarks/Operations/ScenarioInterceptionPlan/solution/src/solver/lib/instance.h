#pragma once

#include<iostream>
#include<fstream>
#include<sstream>
#include<algorithm>
#include<queue>

#include "solver/tools/Typedef.h"
#include "solver/tools/Timer.h"
#include "solver/tools/Log.h"
#include "solver/tools/StringUtil.h"
#include "solver/tools/ConsecutiveIdSet.h"
#include "solver/tools/ConsecutiveIdMap.h"
#include "solver/parallel_hashmap/phmap.h"
#include "solver/parallel_hashmap/btree.h"
#include "solver/tools/robin_hood.h"
#include "solver/tools/dary_priority_queue.h"

#ifndef mkp
#define mkp(a, b) std::make_pair(a, b)
#endif // !mkp(a, b)

#ifndef fatalif
#define fatalif(pred,s,...) (void)((pred)? fprintf(stderr, (s)[sizeof s-2]==':'?s" %s\n":s"%.0s\n",##__VA_ARGS__,strerror(errno)), exit(-1), 0: 0)
#endif // !fatalif(pred,s,...)

// 核心递归构造器，构造 "name = value, ..." 形式的输出
// 由ChatGPT 4o实现
template <typename T>
void __dbg_impl(std::ostringstream& oss, const char* name, const T& value) {
	while (*name == ' ') ++name;  // 去除前导空格
	const char* comma = strchr(name, ',');
	std::string varname = comma ? std::string(name, comma) : std::string(name);
	while (!varname.empty() && varname.back() == ' ') varname.pop_back(); // 去除尾空格
	oss << varname << " = " << value;
}

template <typename T, typename... Args>
void __dbg_impl(std::ostringstream& oss, const char* names, const T& value, const Args&... args) {
	while (*names == ' ') ++names;  // 去除前导空格
	const char* comma = strchr(names, ',');
	std::string varname = comma ? std::string(names, comma) : std::string(names);
	while (!varname.empty() && varname.back() == ' ') varname.pop_back(); // 去除尾空格
	oss << varname << " = " << value;
	if (comma) {
		oss << ", ";
		__dbg_impl(oss, comma + 1, args...);
	}
}

// dbg 宏：将所有变量按 "name = value" 格式打印在一行
#define dbg(...) do { \
    std::ostringstream __oss; \
    __dbg_impl(__oss, #__VA_ARGS__, __VA_ARGS__); \
    std::cerr << "[ " << __oss.str() << " ]\n"; \
} while(0)


namespace PACE2025_HS {
	extern bool global_exit_signal_reached;

	/*template<typename T>
	using PriorityQueue = goal::dary_priority_queue<4, T>;*/
	template<typename T>
	using PriorityQueue = std::priority_queue<T>;
	template<typename ArbitraryId = int, typename ConsecutiveId = int>
	using ConsecutiveIdMap = goal::ConsecutiveIdMap<ArbitraryId, ConsecutiveId>;
	template<typename ItemType = long long>
	using ConsecutiveIdSet = goal::ConsecutiveIdSet<ItemType>;
	template<typename T>
	using Vec = std::vector<T>;
	template<typename ArbitraryId = int>
	using BtreeSet = phmap::btree_set<ArbitraryId>;
	template<typename ArbitraryId = int>
	using UnorderedSet = robin_hood::unordered_flat_set<ArbitraryId>;
	//ska::bytell_hash_set<ArbitraryId>; 
	//phmap::flat_hash_set<ArbitraryId>;// std::unordered_set<ArbitraryId>;
	template<typename ArbitraryId = int, typename ConsecutiveId = int>
	using UnorderedMap = phmap::flat_hash_map<ArbitraryId, ConsecutiveId>;

	using Log = goal::Log;
	using Str = std::string;
	using SetId = int;
	using ElementId = int;
	using Count = long long;
	using Weight = long long;
	static constexpr Count MAX_COUNT_VALUE = Count(1e18);
	static constexpr Count MIN_COUNT_VALUE = Count(-1e18);
	static constexpr Weight MAX_WEIGHT_VALUE = Weight(1e18);
	static constexpr Weight MIN_WEIGHT_VALUE = Weight(-1e18);

	struct OriginalSCInstance {
		Str instname_;
		ElementId element_num_;
		SetId set_num_;

		//每个元素由哪些集合覆盖
		Vec<Vec<SetId>> elements_;
		//每个集合可覆盖哪些元素
		Vec<Vec<ElementId>> sets_;

		void read_hs_instance(const Str& filename);
		void read_hs_instance(FILE* input);

		bool is_valid_solution(const Vec<SetId>& res) const;
	};

	struct SimplifiedSCInstance {
		const OriginalSCInstance& osci_;
		Log logger_;

		ElementId element_num_;
		SetId set_num_;

		//每个元素由哪些集合覆盖
		Vec<Vec<SetId>> elements_;
		//每个集合可覆盖哪些元素
		Vec<Vec<ElementId>> sets_;

		double graph_density_ = 1.0;

		bool is_hop2_neighbor_initialized_ = false;
		SetId max_set_num_cover_element_ = 0;
		SetId avg_set_num_cover_element_ = 0;
		ElementId max_element_num_cover_by_set_ = 0;
		ElementId avg_element_num_cover_by_set_ = 0;
		//每个元素的二跳邻居元素【v1(自身)-> s(所有能覆盖u的集合) -> v2(所有s能覆盖的元素)】
		Vec<Vec<ElementId>> elements_hop2_;
		//每个集合的二跳邻居集合【s1(自身)-> u(所有被s1覆盖的元素) -> s2(所有能覆盖u的集合)】
		Vec<Vec<SetId>> sets_hop2_;

		//连通分量数目
		SetId set_component_number_ = 0;
		//set_component_id_map_[s]表示集合s所属的连通分量
		Vec<SetId> set_component_id_map_;
		//element_component_id_map_[e]表示集合e所属的连通分量
		Vec<SetId> element_component_id_map_;
		//set_component_size_map_[s]表示集合s所属的连通分量大小
		Vec<SetId> set_component_size_map_;
		Vec<Vec<SetId>> component_sets_;
		Vec<Vec<ElementId>> component_elements_;

		SimplifiedSCInstance(const OriginalSCInstance &inst, Log logger);

		//化简辅助变量
		//必选的集合
		UnorderedSet<SetId> ori_fixed_sets_;
		//同时包含必选以及必不选的集合
		UnorderedSet<SetId> ori_removed_sets_;
		//可忽略覆盖的元素
		UnorderedSet<ElementId> ori_removed_elements_;

		Vec<SetId> cur_set_id_to_ori_;
		Vec<ElementId> cur_ele_id_to_ori_;

		SetId fixed_set_number() const { return SetId(ori_fixed_sets_.size()); }

		ElementId initialize_connected_component() ;

		Vec<SetId> solve_small_component_and_rebuild(long long max_time_limit);

		void print_statistics() const ;

		void reduction(long long max_time_limit);

		bool try_to_initialize_hop2_neighbor(long long max_time_limit);

		Vec<SetId> generate_complete_sol(const Vec<SetId>& res) const;

		bool is_valid_solution(const Vec<SetId>& res) const ;
	};
}