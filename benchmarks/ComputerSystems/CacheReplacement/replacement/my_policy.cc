// CacheReplacement — my_policy implementation
// Code outside EVOLVE-BLOCK is READ-ONLY.

#include "my_policy.h"
#include <algorithm>
#include <cassert>

my_policy::my_policy(CACHE* cache) : my_policy(cache, cache->NUM_SET, cache->NUM_WAY) {}
my_policy::my_policy(CACHE* cache, long sets, long ways) : replacement(cache), NUM_WAY(ways), last_used_cycles(static_cast<std::size_t>(sets * ways), 0) {}

// EVOLVE-BLOCK-START
// Agent may modify method bodies below. Keep function signatures unchanged.

long my_policy::find_victim(uint32_t, uint64_t, long set, const champsim::cache_block* b, champsim::address, champsim::address, access_type) {
  auto begin = std::next(std::begin(last_used_cycles), set * NUM_WAY);
  auto end = std::next(begin, NUM_WAY);
  auto victim = std::min_element(begin, end);
  return static_cast<long>(std::distance(begin, victim));
}

void my_policy::replacement_cache_fill(uint32_t, long set, long way, champsim::address, champsim::address, champsim::address, access_type) {
  last_used_cycles.at(static_cast<std::size_t>(set * NUM_WAY + way)) = cycle++;
}

void my_policy::update_replacement_state(uint32_t, long set, long way, champsim::address, champsim::address, champsim::address, access_type, uint8_t hit) {
  if (hit) last_used_cycles.at(static_cast<std::size_t>(set * NUM_WAY + way)) = cycle++;
}

// EVOLVE-BLOCK-END
