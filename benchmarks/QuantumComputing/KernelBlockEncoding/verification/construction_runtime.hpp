#ifndef KERNEL_BLOCK_ENCODING_CONSTRUCTION_RUNTIME_HPP
#define KERNEL_BLOCK_ENCODING_CONSTRUCTION_RUNTIME_HPP

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace kernel_block_encoding {

inline constexpr std::int64_t kAngleDenominator = std::int64_t{1} << 28;
inline constexpr std::int64_t kMaximumAngleTicks = 4 * kAngleDenominator;
inline constexpr std::int64_t kMaximumScaleMultiplier = 16;
inline constexpr long double kRotationWeight = 16.0L;
inline constexpr long double kCnotWeight = 1.0L;
inline constexpr long double kHadamardWeight = 0.25L;
inline constexpr long double kDepthWeight = 0.25L;

struct InputData {
  std::string workload_id;
  std::size_t dimension = 0;
  std::int64_t matrix_scale = 0;
  std::int64_t epsilon_numerator = 0;
  std::vector<std::int64_t> matrix;
};

inline bool is_power_of_two(std::size_t value) {
  return value >= 2 && (value & (value - 1)) == 0;
}

inline std::size_t integer_log2(std::size_t value) {
  if (!is_power_of_two(value)) {
    throw std::runtime_error("dimension is not a supported power of two");
  }
  std::size_t result = 0;
  while ((std::size_t{1} << result) < value)
    ++result;
  return result;
}

inline void expect_token(std::istream &input, const std::string &expected) {
  std::string actual;
  if (!(input >> actual) || actual != expected) {
    throw std::runtime_error("malformed input: expected token " + expected);
  }
}

inline InputData read_input(const std::string &path) {
  std::ifstream input(path);
  if (!input)
    throw std::runtime_error("cannot open kernel input");
  InputData data;
  expect_token(input, "KBE_INPUT_V1");
  expect_token(input, "workload");
  if (!(input >> data.workload_id) || data.workload_id.empty()) {
    throw std::runtime_error("malformed workload id");
  }
  expect_token(input, "dimension");
  if (!(input >> data.dimension) || !is_power_of_two(data.dimension) ||
      data.dimension > 64) {
    throw std::runtime_error("dimension must be a power of two in [2, 64]");
  }
  expect_token(input, "matrix_scale");
  if (!(input >> data.matrix_scale) || data.matrix_scale <= 0) {
    throw std::runtime_error("matrix_scale must be positive");
  }
  expect_token(input, "epsilon_numerator");
  if (!(input >> data.epsilon_numerator) || data.epsilon_numerator <= 0) {
    throw std::runtime_error("epsilon_numerator must be positive");
  }
  expect_token(input, "matrix");
  const std::size_t entries = data.dimension * data.dimension;
  data.matrix.resize(entries);
  for (std::size_t index = 0; index < entries; ++index) {
    if (!(input >> data.matrix[index]) ||
        std::llabs(data.matrix[index]) > data.matrix_scale) {
      throw std::runtime_error("invalid fixed-point matrix entry");
    }
  }
  expect_token(input, "end");
  std::string trailing;
  if (input >> trailing)
    throw std::runtime_error("trailing kernel input data");
  return data;
}

inline std::uint64_t gray_code(std::uint64_t value) {
  return value ^ (value >> 1U);
}

inline unsigned popcount64(std::uint64_t value) {
#if defined(__GNUC__) || defined(__clang__)
  return static_cast<unsigned>(__builtin_popcountll(value));
#else
  unsigned count = 0;
  while (value != 0) {
    value &= value - 1;
    ++count;
  }
  return count;
#endif
}

inline unsigned trailing_zeroes64(std::uint64_t value) {
  if (value == 0)
    throw std::runtime_error("zero has no toggled Gray-code bit");
#if defined(__GNUC__) || defined(__clang__)
  return static_cast<unsigned>(__builtin_ctzll(value));
#else
  unsigned count = 0;
  while ((value & 1U) == 0U) {
    value >>= 1U;
    ++count;
  }
  return count;
#endif
}

struct ResourceEstimate {
  std::uint64_t rotations = 0;
  std::uint64_t oracle_cnots = 0;
  std::uint64_t cnots = 0;
  std::uint64_t hadamards = 0;
  std::uint64_t depth = 0;
  std::uint64_t qubits = 0;
  long double alpha = 0.0L;
  long double compiled_cost = 0.0L;
  long double objective = 0.0L;
};

class Construction {
public:
  Construction(std::string input_path, std::string certificate_path)
      : input_(read_input(input_path)),
        certificate_path_(std::move(certificate_path)) {
    qubits_ = integer_log2(input_.dimension);
    set_basis_mask(0);
  }

  std::size_t dimension() const { return input_.dimension; }
  std::size_t system_qubits() const { return qubits_; }
  std::size_t coefficient_count() const {
    return input_.dimension * input_.dimension;
  }
  std::uint32_t basis_mask() const { return basis_mask_; }
  std::int64_t matrix_scale() const { return input_.matrix_scale; }
  std::int64_t minimum_scale_numerator() const {
    return minimum_scale_numerator_;
  }
  std::int64_t scale_numerator() const { return scale_numerator_; }
  std::int64_t basis_denominator_multiplier() const {
    return basis_denominator_multiplier_;
  }
  long double epsilon() const {
    return static_cast<long double>(input_.epsilon_numerator) /
           static_cast<long double>(input_.matrix_scale);
  }
  const std::string &workload_id() const { return input_.workload_id; }

  long double target(std::size_t row, std::size_t column) const {
    check_matrix_index(row, column);
    return static_cast<long double>(
               input_.matrix[row * input_.dimension + column]) /
           static_cast<long double>(input_.matrix_scale);
  }

  long double basis_target(std::size_t row, std::size_t column) const {
    check_matrix_index(row, column);
    return static_cast<long double>(
               basis_numerators_[row * input_.dimension + column]) /
           basis_denominator();
  }

  void set_basis_mask(std::uint32_t mask) {
    const std::uint32_t valid_mask =
        static_cast<std::uint32_t>(input_.dimension - 1U);
    if ((mask & ~valid_mask) != 0U) {
      throw std::runtime_error(
          "basis mask addresses a nonexistent system qubit");
    }
    basis_mask_ = mask;
    basis_numerators_ = input_.matrix;
    basis_denominator_multiplier_ = 1;
    for (std::size_t bit = 0; bit < qubits_; ++bit) {
      if ((mask & (std::uint32_t{1} << bit)) == 0U)
        continue;
      apply_row_butterfly(bit);
      apply_column_butterfly(bit);
      basis_denominator_multiplier_ *= 2;
    }
    minimum_scale_numerator_ = 0;
    for (const std::int64_t value : basis_numerators_) {
      minimum_scale_numerator_ =
          std::max(minimum_scale_numerator_,
                   static_cast<std::int64_t>(std::llabs(value)));
    }
    if (minimum_scale_numerator_ <= 0) {
      throw std::runtime_error("kernel transformed to an all-zero matrix");
    }
    scale_numerator_ = minimum_scale_numerator_;
    committed_ = false;
    committed_angles_.clear();
  }

  void set_scale_numerator(std::int64_t numerator) {
    if (minimum_scale_numerator_ >
        std::numeric_limits<std::int64_t>::max() / kMaximumScaleMultiplier) {
      throw std::runtime_error("normalization scale range overflows int64");
    }
    const std::int64_t maximum =
        minimum_scale_numerator_ * kMaximumScaleMultiplier;
    if (numerator < minimum_scale_numerator_ || numerator > maximum) {
      throw std::runtime_error(
          "normalization scale is outside the public range");
    }
    scale_numerator_ = numerator;
    committed_ = false;
    committed_angles_.clear();
  }

  void set_scale_multiplier(long double multiplier) {
    if (!std::isfinite(multiplier) || multiplier < 1.0L ||
        multiplier > static_cast<long double>(kMaximumScaleMultiplier)) {
      throw std::runtime_error("normalization multiplier must lie in [1, 16]");
    }
    const long double requested =
        static_cast<long double>(minimum_scale_numerator_) * multiplier;
    const auto numerator = static_cast<std::int64_t>(std::ceil(requested));
    set_scale_numerator(std::max(numerator, minimum_scale_numerator_));
  }

  std::vector<std::int64_t> exact_angle_ticks() const {
    const std::size_t count = coefficient_count();
    std::vector<long double> transformed(count);
    for (std::size_t index = 0; index < count; ++index) {
      long double normalized =
          static_cast<long double>(basis_numerators_[index]) /
          static_cast<long double>(scale_numerator_);
      normalized = std::max(-1.0L, std::min(1.0L, normalized));
      transformed[index] = 2.0L * std::acos(normalized);
    }
    scaled_walsh_hadamard(transformed);
    const long double pi = std::acos(-1.0L);
    std::vector<std::int64_t> result(count, 0);
    for (std::size_t index = 0; index < count; ++index) {
      const long double ticks = transformed[gray_code(index)] *
                                static_cast<long double>(kAngleDenominator) /
                                pi;
      if (!std::isfinite(ticks) ||
          std::fabs(ticks) > static_cast<long double>(kMaximumAngleTicks)) {
        throw std::runtime_error(
            "generated angle lies outside certificate range");
      }
      result[index] = static_cast<std::int64_t>(std::llround(ticks));
    }
    return result;
  }

  long double
  frobenius_error(const std::vector<std::int64_t> &angle_ticks) const {
    validate_angles(angle_ticks);
    const std::vector<std::int64_t> entry_angle_ticks =
        inverse_angle_transform(angle_ticks);
    const long double pi = std::acos(-1.0L);
    const long double scale = static_cast<long double>(scale_numerator_);
    long double squared_error = 0.0L;
    for (std::size_t index = 0; index < coefficient_count(); ++index) {
      const long double approximate_numerator =
          scale *
          std::cos(pi * static_cast<long double>(entry_angle_ticks[index]) /
                   (2.0L * static_cast<long double>(kAngleDenominator)));
      const long double residual =
          (static_cast<long double>(basis_numerators_[index]) -
           approximate_numerator) /
          basis_denominator();
      squared_error += residual * residual;
    }
    return std::sqrt(std::max(0.0L, squared_error));
  }

  ResourceEstimate
  resources(const std::vector<std::int64_t> &angle_ticks) const {
    validate_angles(angle_ticks);
    ResourceEstimate estimate;
    const std::size_t count = coefficient_count();
    const std::size_t controls = 2 * qubits_;
    std::size_t index = 0;
    while (index < count) {
      std::uint64_t parity = 0;
      if (angle_ticks[index] != 0)
        ++estimate.rotations;
      while (true) {
        unsigned bit = 0;
        if (index + 1 == count) {
          bit = static_cast<unsigned>(controls - 1);
        } else {
          bit = trailing_zeroes64(gray_code(index) ^ gray_code(index + 1));
        }
        parity ^= std::uint64_t{1} << bit;
        ++index;
        if (index >= count || angle_ticks[index] != 0)
          break;
      }
      estimate.oracle_cnots += popcount64(parity);
    }
    estimate.cnots = estimate.oracle_cnots + 3 * qubits_;
    estimate.hadamards =
        2 * qubits_ + 2 * popcount64(static_cast<std::uint64_t>(basis_mask_));
    estimate.depth = estimate.rotations + estimate.oracle_cnots + 5 +
                     (basis_mask_ == 0 ? 0 : 2);
    estimate.qubits = 2 * qubits_ + 1;
    estimate.alpha = static_cast<long double>(input_.dimension) *
                     static_cast<long double>(scale_numerator_) /
                     basis_denominator();
    estimate.compiled_cost =
        kRotationWeight * static_cast<long double>(estimate.rotations) +
        kCnotWeight * static_cast<long double>(estimate.cnots) +
        kHadamardWeight * static_cast<long double>(estimate.hadamards) +
        kDepthWeight * static_cast<long double>(estimate.depth);
    estimate.objective = estimate.alpha * estimate.compiled_cost;
    return estimate;
  }

  long double objective(const std::vector<std::int64_t> &angle_ticks) const {
    return resources(angle_ticks).objective;
  }

  void commit(std::vector<std::int64_t> angle_ticks) {
    validate_angles(angle_ticks);
    committed_angles_ = std::move(angle_ticks);
    committed_ = true;
  }

  void write_certificate() const {
    if (!committed_) {
      throw std::runtime_error("optimizer did not commit a construction");
    }
    std::ofstream output(certificate_path_, std::ios::trunc);
    if (!output)
      throw std::runtime_error("cannot create construction certificate");
    std::size_t nonzero = 0;
    for (const auto tick : committed_angles_) {
      if (tick != 0)
        ++nonzero;
    }
    output << "KBE_CERTIFICATE_V1\n"
           << "dimension " << input_.dimension << '\n'
           << "basis_mask " << basis_mask_ << '\n'
           << "scale_numerator " << scale_numerator_ << '\n'
           << "angle_denominator " << kAngleDenominator << '\n'
           << "nonzero_count " << nonzero << '\n'
           << "angles\n";
    for (std::size_t index = 0; index < committed_angles_.size(); ++index) {
      if (committed_angles_[index] != 0) {
        output << index << ' ' << committed_angles_[index] << '\n';
      }
    }
    output << "end\n";
    output.flush();
    if (!output)
      throw std::runtime_error("failed to write construction certificate");
  }

private:
  long double basis_denominator() const {
    return static_cast<long double>(input_.matrix_scale) *
           static_cast<long double>(basis_denominator_multiplier_);
  }

  void check_matrix_index(std::size_t row, std::size_t column) const {
    if (row >= input_.dimension || column >= input_.dimension) {
      throw std::out_of_range("kernel matrix index out of range");
    }
  }

  static std::int64_t checked_add(std::int64_t lhs, std::int64_t rhs) {
    const auto minimum = std::numeric_limits<std::int64_t>::min();
    const auto maximum = std::numeric_limits<std::int64_t>::max();
    if ((rhs > 0 && lhs > maximum - rhs) || (rhs < 0 && lhs < minimum - rhs)) {
      throw std::runtime_error("integer overflow in basis transform");
    }
    return lhs + rhs;
  }

  static std::int64_t checked_subtract(std::int64_t lhs, std::int64_t rhs) {
    const auto minimum = std::numeric_limits<std::int64_t>::min();
    const auto maximum = std::numeric_limits<std::int64_t>::max();
    if ((rhs > 0 && lhs < minimum + rhs) || (rhs < 0 && lhs > maximum + rhs)) {
      throw std::runtime_error("integer overflow in basis transform");
    }
    return lhs - rhs;
  }

  void apply_row_butterfly(std::size_t bit) {
    const std::size_t stride = std::size_t{1} << bit;
    const std::size_t block = 2 * stride;
    for (std::size_t base = 0; base < input_.dimension; base += block) {
      for (std::size_t offset = 0; offset < stride; ++offset) {
        const std::size_t row0 = base + offset;
        const std::size_t row1 = row0 + stride;
        for (std::size_t column = 0; column < input_.dimension; ++column) {
          const std::size_t index0 = row0 * input_.dimension + column;
          const std::size_t index1 = row1 * input_.dimension + column;
          const std::int64_t lhs = basis_numerators_[index0];
          const std::int64_t rhs = basis_numerators_[index1];
          basis_numerators_[index0] = checked_add(lhs, rhs);
          basis_numerators_[index1] = checked_subtract(lhs, rhs);
        }
      }
    }
  }

  void apply_column_butterfly(std::size_t bit) {
    const std::size_t stride = std::size_t{1} << bit;
    const std::size_t block = 2 * stride;
    for (std::size_t row = 0; row < input_.dimension; ++row) {
      for (std::size_t base = 0; base < input_.dimension; base += block) {
        for (std::size_t offset = 0; offset < stride; ++offset) {
          const std::size_t column0 = base + offset;
          const std::size_t column1 = column0 + stride;
          const std::size_t index0 = row * input_.dimension + column0;
          const std::size_t index1 = row * input_.dimension + column1;
          const std::int64_t lhs = basis_numerators_[index0];
          const std::int64_t rhs = basis_numerators_[index1];
          basis_numerators_[index0] = checked_add(lhs, rhs);
          basis_numerators_[index1] = checked_subtract(lhs, rhs);
        }
      }
    }
  }

  static void scaled_walsh_hadamard(std::vector<long double> &values) {
    for (std::size_t stride = 1; stride < values.size(); stride *= 2) {
      for (std::size_t base = 0; base < values.size(); base += 2 * stride) {
        for (std::size_t offset = 0; offset < stride; ++offset) {
          const long double lhs = values[base + offset];
          const long double rhs = values[base + offset + stride];
          values[base + offset] = (lhs + rhs) / 2.0L;
          values[base + offset + stride] = (lhs - rhs) / 2.0L;
        }
      }
    }
  }

  void validate_angles(const std::vector<std::int64_t> &angle_ticks) const {
    if (angle_ticks.size() != coefficient_count()) {
      throw std::runtime_error("angle vector has invalid size");
    }
    for (const auto tick : angle_ticks) {
      if (std::llabs(tick) > kMaximumAngleTicks) {
        throw std::runtime_error("angle tick lies outside certificate range");
      }
    }
  }

  std::vector<std::int64_t>
  inverse_angle_transform(const std::vector<std::int64_t> &angle_ticks) const {
    std::vector<std::int64_t> values(angle_ticks.size(), 0);
    for (std::size_t index = 0; index < angle_ticks.size(); ++index) {
      values[gray_code(index)] = angle_ticks[index];
    }
    for (std::size_t stride = 1; stride < values.size(); stride *= 2) {
      for (std::size_t base = 0; base < values.size(); base += 2 * stride) {
        for (std::size_t offset = 0; offset < stride; ++offset) {
          const std::int64_t lhs = values[base + offset];
          const std::int64_t rhs = values[base + offset + stride];
          values[base + offset] = checked_add(lhs, rhs);
          values[base + offset + stride] = checked_subtract(lhs, rhs);
        }
      }
    }
    return values;
  }

  InputData input_;
  std::string certificate_path_;
  std::size_t qubits_ = 0;
  std::uint32_t basis_mask_ = 0;
  std::int64_t basis_denominator_multiplier_ = 1;
  std::vector<std::int64_t> basis_numerators_;
  std::int64_t minimum_scale_numerator_ = 0;
  std::int64_t scale_numerator_ = 0;
  bool committed_ = false;
  std::vector<std::int64_t> committed_angles_;
};

} // namespace kernel_block_encoding

#endif // KERNEL_BLOCK_ENCODING_CONSTRUCTION_RUNTIME_HPP
