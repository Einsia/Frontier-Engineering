// baseline/random.cc — sanity check only. Not official baseline.
#include "cache.h"
#include "modules.h"
struct random_policy : public champsim::modules::replacement {
  long NUM_WAY;
  random_policy(CACHE* cache) : random_policy(cache, cache->NUM_SET, cache->NUM_WAY) {}
  random_policy(CACHE* cache, long sets, long ways) : replacement(cache), NUM_WAY(ways) {}
  long find_victim(uint32_t, uint64_t, long, const champsim::cache_block*, champsim::address, champsim::address, access_type) { return rand() % NUM_WAY; }
  void replacement_cache_fill(uint32_t, long, long, champsim::address, champsim::address, champsim::address, access_type) {}
  void update_replacement_state(uint32_t, long, long, champsim::address, champsim::address, champsim::address, access_type, uint8_t) {}
};
