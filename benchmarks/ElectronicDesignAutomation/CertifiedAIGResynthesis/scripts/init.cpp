// Certified AIG resynthesis candidate policy.
// The evaluator permits edits only inside the marked region.

#include "rewrite_runtime.hpp"

namespace certified_aig {

// EVOLVE-BLOCK-START
void optimize(Optimizer& optimizer) {
  // Valid starter: constant propagation, idempotence, complement elimination,
  // and exact structural hashing. More capable policies can enumerate cuts,
  // synthesize smaller local AIGs, reuse divisors, and balance depth through
  // Optimizer::try_rewrite().
  for (std::uint32_t pass = 0; pass < 8U; ++pass) {
    std::unordered_map<std::uint64_t, std::uint32_t> representative;
    std::uint32_t changes = 0;
    const std::uint32_t limit = optimizer.node_count();
    for (std::uint32_t root = optimizer.first_and_id(); root < limit; ++root) {
      if (!optimizer.is_and(root) || !optimizer.is_active(root)) continue;
      auto [lhs, rhs] = optimizer.fanins(root);
      if (lhs > rhs) std::swap(lhs, rhs);
      const auto leaves = boundary_nodes(lhs, rhs);

      std::optional<std::uint32_t> replacement;
      if (lhs == 0U || rhs == 0U) {
        replacement = 0U;
      } else if (lhs == 1U) {
        replacement = rhs;
      } else if (rhs == 1U) {
        replacement = lhs;
      } else if (lhs == rhs) {
        replacement = lhs;
      } else if ((lhs ^ rhs) == 1U) {
        replacement = 0U;
      }
      if (replacement.has_value() &&
          optimizer.replace(root, *replacement, leaves)) {
        ++changes;
        continue;
      }

      const std::uint64_t key =
          (static_cast<std::uint64_t>(lhs) << 32U) | rhs;
      const auto found = representative.find(key);
      if (found == representative.end()) {
        representative.emplace(key, root << 1U);
      } else {
        const std::uint32_t prior = optimizer.resolve(found->second);
        if (prior != (root << 1U) && optimizer.replace(root, prior, leaves)) {
          ++changes;
        }
      }
    }
    if (changes == 0U) break;
  }
}
// EVOLVE-BLOCK-END

}  // namespace certified_aig

int main(int argc, char** argv) {
  std::string input_path;
  std::string certificate_path;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--input" && index + 1 < argc) {
      input_path = argv[++index];
    } else if (argument == "--certificate" && index + 1 < argc) {
      certificate_path = argv[++index];
    } else {
      std::cerr << "unknown or incomplete argument: " << argument << '\n';
      return 2;
    }
  }
  if (input_path.empty() || certificate_path.empty()) {
    std::cerr << "usage: candidate --input circuit.aag --certificate proof.cert\n";
    return 2;
  }
  try {
    certified_aig::Optimizer optimizer(input_path, certificate_path);
    certified_aig::optimize(optimizer);
    const certified_aig::NetworkStats stats = optimizer.stats();
    std::cout << "accepted_rewrites=" << optimizer.accepted_rewrites()
              << " live_ands=" << stats.live_ands
              << " depth=" << stats.depth << '\n';
    return 0;
  } catch (const std::exception& exc) {
    std::cerr << "candidate failure: " << exc.what() << '\n';
    return 1;
  }
}
