#ifndef REPLACEMENT_MY_POLICY_H
#define REPLACEMENT_MY_POLICY_H
#include <vector>
#include "cache.h"
#include "modules.h"
struct my_policy : public champsim::modules::replacement {
  long NUM_WAY;
  std::vector<uint64_t> last_used_cycles;
  uint64_t cycle = 0;
  // EVOLVE-BLOCK-START
  // Agent may ADD member variables here (fixed-size arrays only)
  // Total EVOLVE-BLOCK storage ≤ 64 KB (checked by evaluator)
  // EVOLVE-BLOCK-END
  my_policy(CACHE* cache);
  my_policy(CACHE* cache, long sets, long ways);
  long find_victim(uint32_t, uint64_t, long, const champsim::cache_block*, champsim::address, champsim::address, access_type);
  void replacement_cache_fill(uint32_t, long, long, champsim::address, champsim::address, champsim::address, access_type);
  void update_replacement_state(uint32_t, long, long, champsim::address, champsim::address, champsim::address, access_type, uint8_t);
};
#endif
