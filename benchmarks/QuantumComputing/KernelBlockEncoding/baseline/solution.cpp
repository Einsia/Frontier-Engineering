// Kernel block-encoding construction policy.
// The evaluator permits edits only inside the marked region.

#include "construction_runtime.hpp"

namespace kernel_block_encoding {

// EVOLVE-BLOCK-START
void optimize(Construction &construction) {
  // Valid starter: direct-basis FABLE with a single global pruning threshold.
  // Better policies can search partial-Hadamard bases and normalization scales,
  // allocate the error budget per coefficient, and alter retained angles.
  construction.set_basis_mask(0);
  construction.set_scale_numerator(construction.minimum_scale_numerator());

  const std::vector<std::int64_t> exact = construction.exact_angle_ticks();
  std::vector<std::int64_t> magnitudes;
  magnitudes.reserve(exact.size());
  for (const std::int64_t tick : exact) {
    if (tick != 0)
      magnitudes.push_back(std::llabs(tick));
  }
  std::sort(magnitudes.begin(), magnitudes.end());
  magnitudes.erase(std::unique(magnitudes.begin(), magnitudes.end()),
                   magnitudes.end());

  std::vector<std::int64_t> best = exact;
  const long double error_budget = 0.75L * construction.epsilon();
  std::ptrdiff_t low = 0;
  std::ptrdiff_t high = static_cast<std::ptrdiff_t>(magnitudes.size()) - 1;
  while (low <= high) {
    const std::ptrdiff_t middle = low + (high - low) / 2;
    const std::int64_t threshold = magnitudes[static_cast<std::size_t>(middle)];
    std::vector<std::int64_t> trial = exact;
    for (std::int64_t &tick : trial) {
      if (std::llabs(tick) <= threshold)
        tick = 0;
    }
    if (construction.frobenius_error(trial) <= error_budget) {
      best = std::move(trial);
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  construction.commit(std::move(best));
}
// EVOLVE-BLOCK-END

} // namespace kernel_block_encoding

int main(int argc, char **argv) {
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
    std::cerr
        << "usage: candidate --input kernel.kbe --certificate circuit.kbc\n";
    return 2;
  }
  try {
    kernel_block_encoding::Construction construction(input_path,
                                                     certificate_path);
    kernel_block_encoding::optimize(construction);
    construction.write_certificate();
    std::cout << "workload=" << construction.workload_id()
              << " dimension=" << construction.dimension() << '\n';
    return 0;
  } catch (const std::exception &exception) {
    std::cerr << "candidate failure: " << exception.what() << '\n';
    return 1;
  }
}
