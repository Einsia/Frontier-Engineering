"""CacheReplacement Layer 1 validation tests (fast, no compile needed)."""

import sys, tempfile, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluator as ev

HEADER = """#ifndef REPLACEMENT_MY_POLICY_H
#define REPLACEMENT_MY_POLICY_H
#include <vector>
#include "cache.h"
#include "modules.h"
struct my_policy : public champsim::modules::replacement {
  long NUM_WAY; std::vector<uint64_t> last_used_cycles; uint64_t cycle = 0;
  // EVOLVE-BLOCK-START
  // EVOLVE-BLOCK-END
  my_policy(CACHE*); my_policy(CACHE*,long,long);
  long find_victim(uint32_t,uint64_t,long,const champsim::cache_block*,champsim::address,champsim::address,access_type);
  void replacement_cache_fill(uint32_t,long,long,champsim::address,champsim::address,champsim::address,access_type);
  void update_replacement_state(uint32_t,long,long,champsim::address,champsim::address,champsim::address,access_type,uint8_t);
};
#endif"""

PREFIX = '#include "my_policy.h"\n#include <algorithm>\n#include <cassert>\nmy_policy::my_policy(CACHE*c):my_policy(c,c->NUM_SET,c->NUM_WAY){}\nmy_policy::my_policy(CACHE*c,long s,long w):replacement(c),NUM_WAY(w),last_used_cycles(static_cast<std::size_t>(s*w),0){}\n// EVOLVE-BLOCK-START\n'
SUFFIX = "\n// EVOLVE-BLOCK-END\n"
def cc(body): return PREFIX + body + SUFFIX

def test(name, cc_text, hdr_text, expect_errors):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td); (p/"my_policy.cc").write_text(cc_text); (p/"my_policy.h").write_text(hdr_text or HEADER)
        errs = ev._static_validation(p/"my_policy.cc", p/"my_policy.h")
        ok = (len(errs) > 0) == expect_errors
        detail = errs[0][:80] if errs else "clean"
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        return ok

all_pass = True
print("="*50+"\nCacheReplacement — Static Validation Tests\n"+"="*50+"\n")

all_pass &= test("1. Normal LRU", cc("long my_policy::find_victim(...){return 0;}void my_policy::replacement_cache_fill(...){}void my_policy::update_replacement_state(...){}"), HEADER, False)
all_pass &= test("2. Forbidden header <iostream>", cc('#include <iostream>\nlong my_policy::find_victim(...){}'), HEADER, True)
all_pass &= test("3. rand() usage", cc("long my_policy::find_victim(...){return rand()%4;}"), HEADER, True)
all_pass &= test("4. fopen() file I/O", cc('long my_policy::find_victim(...){FILE*f=fopen("x","r");return 0;}'), HEADER, True)
all_pass &= test("5. std::vector in EVOLVE-BLOCK", cc("std::vector<int> v;\nlong my_policy::find_victim(...){return 0;}"), HEADER, True)
all_pass &= test("6. new operator", cc("long my_policy::find_victim(...){int*p=new int;return 0;}"), HEADER, True)
all_pass &= test("7. mt19937 randomness", cc("long my_policy::find_victim(...){std::mt19937 g;return 0;}"), HEADER, True)
all_pass &= test("8. system() call", cc('long my_policy::find_victim(...){system("ls");return 0;}'), HEADER, True)
all_pass &= test("9. Missing EVOLVE-BLOCK-END", "// EVOLVE-BLOCK-START\n", HEADER, True)
all_pass &= test("10. Budget exceeded", cc("long my_policy::find_victim(...){return 0;}"),
    HEADER.replace("// EVOLVE-BLOCK-START\n  // EVOLVE-BLOCK-END","// EVOLVE-BLOCK-START\nuint8_t huge[100000];\n// EVOLVE-BLOCK-END"), True)

print(f"\n{'ALL TESTS PASSED' if all_pass else 'SOME FAILED'}")
sys.exit(0 if all_pass else 1)
