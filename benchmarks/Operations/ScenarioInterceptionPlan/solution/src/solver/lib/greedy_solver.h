#pragma once

#include "instance.h"

namespace PACE2025_HS {
	struct GreedyGenerator {
		const SimplifiedSCInstance& ins_;
		Log logger_;

		GreedyGenerator(const SimplifiedSCInstance& ins) : ins_(ins), logger_(ins_.logger_) {};

		Vec<SetId> greedy_by_cover_count(long long max_time_limit);
		Vec<SetId> greedy_by_surprisal(long long max_time_limit);
		Vec<SetId> greedy_by_pagerank(long long max_time_limit);
		Vec<SetId> greedy_by_iterated_pagerank(Count max_iteration, long long max_time_limit);
	};
}