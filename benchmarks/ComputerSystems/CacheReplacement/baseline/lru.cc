// baseline/lru.cc — LRU reference (official baseline)

#include "cache.h"
#include "modules.h"

struct lru : public champsim::modules::replacement {
  long NUM_WAY;
  std::vector<uint64_t> last_used_cycles;
  uint64_t cycle = 0;
  lru(CACHE* cache) : lru(cache, cache->NUM_SET, cache->NUM_WAY) {}
  lru(CACHE* cache, long sets, long ways) : replacement(cache), NUM_WAY(ways), last_used_cycles(static_cast<std::size_t>(sets * ways), 0) {}
  long find_victim(uint32_t, uint64_t, long set, const champsim::cache_block* b, champsim::address, champsim::address, access_type) {
    return static_cast<long>(std::distance(std::begin(last_used_cycles) + set * NUM_WAY, std::min_element(std::begin(last_used_cycles) + set * NUM_WAY, std::begin(last_used_cycles) + (set + 1) * NUM_WAY)));
  }
  void replacement_cache_fill(uint32_t, long set, long way, champsim::address, champsim::address, champsim::address, access_type) {
    last_used_cycles.at(static_cast<std::size_t>(set * NUM_WAY + way)) = cycle++;
  }
  void update_replacement_state(uint32_t, long set, long way, champsim::address, champsim::address, champsim::address, access_type, uint8_t hit) {
    if (hit) last_used_cycles.at(static_cast<std::size_t>(set * NUM_WAY + way)) = cycle++;
  }
};
