// Immutable runtime and public API for certified AIG resynthesis candidates.
//
// This header parses ASCII AIGER, maintains the current Boolean DAG,
// validates every proposed local replacement exactly, and emits a replayable
// certificate. Search algorithms must not modify this file.

#pragma once

#include <algorithm>
#include <array>
#include <bitset>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <stack>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace certified_aig {

constexpr std::uint32_t kMaxCutLeaves = 8;
constexpr std::uint32_t kMaxDivisors = 16;
constexpr std::uint32_t kMaxLocalAnds = 64;
constexpr std::uint32_t kMaxRewrites = 20000;
constexpr std::uint32_t kMaxTotalNodes = 300000;

struct LocalAnd {
  std::uint32_t lhs;
  std::uint32_t rhs;
};

struct TruthTable {
  std::array<std::uint64_t, 4> words{};
  std::uint32_t variables = 0;

  bool operator==(const TruthTable& other) const {
    return variables == other.variables && words == other.words;
  }
};

struct NetworkStats {
  std::uint32_t live_ands = 0;
  std::uint32_t depth = 0;
};

class Optimizer {
 public:
  explicit Optimizer(const std::string& input_path,
                     const std::string& certificate_path) {
    load_aag(input_path);
    original_node_count_ = static_cast<std::uint32_t>(nodes_.size());
    certificate_.open(certificate_path, std::ios::out | std::ios::trunc);
    if (!certificate_) {
      throw std::runtime_error("cannot open certificate output: " +
                               certificate_path);
    }
    certificate_ << "CERT1\n";
    if (!certificate_) {
      throw std::runtime_error("cannot write certificate header");
    }
  }

  std::uint32_t first_and_id() const { return first_and_id_; }
  std::uint32_t original_node_count() const { return original_node_count_; }
  std::uint32_t node_count() const {
    return static_cast<std::uint32_t>(nodes_.size());
  }
  std::uint32_t input_count() const { return input_count_; }
  std::uint32_t output_count() const {
    return static_cast<std::uint32_t>(outputs_.size());
  }
  std::uint32_t output_literal(std::uint32_t index) const {
    if (index >= outputs_.size()) {
      throw std::out_of_range("output index is out of range");
    }
    return resolve(outputs_[index]);
  }
  std::uint32_t accepted_rewrites() const { return accepted_rewrites_; }

  bool is_and(std::uint32_t id) const {
    return id < nodes_.size() && nodes_[id].kind == Kind::kAnd;
  }

  bool is_primary_input(std::uint32_t id) const {
    return id < nodes_.size() && nodes_[id].kind == Kind::kInput;
  }

  bool is_active(std::uint32_t id) const {
    return id < redirect_.size() && redirect_[id] == (id << 1U);
  }

  // Resolve a global AIG literal through all previously accepted rewrites.
  // Literal encoding follows AIGER: 2*node_id is positive, xor 1 is inverted.
  std::uint32_t resolve(std::uint32_t literal) const {
    if ((literal >> 1U) >= redirect_.size()) {
      throw std::out_of_range("global literal references an unknown node");
    }
    std::uint32_t id = literal >> 1U;
    std::uint32_t inverted = literal & 1U;
    for (std::size_t steps = 0; steps <= redirect_.size(); ++steps) {
      const std::uint32_t mapped = redirect_[id];
      if (mapped == (id << 1U)) {
        return (id << 1U) | inverted;
      }
      inverted ^= mapped & 1U;
      id = mapped >> 1U;
      if (id >= redirect_.size()) {
        throw std::runtime_error("corrupt rewrite redirect");
      }
    }
    throw std::runtime_error("cycle in rewrite redirects");
  }

  std::pair<std::uint32_t, std::uint32_t> fanins(
      std::uint32_t id) const {
    if (!is_and(id) || !is_active(id)) {
      throw std::invalid_argument("fanins() needs an active AND node");
    }
    return {resolve(nodes_[id].lhs), resolve(nodes_[id].rhs)};
  }

  // Return the primary-input support when it fits within limit.  An empty
  // optional means that the limit was exceeded or the root was invalid.
  std::optional<std::vector<std::uint32_t>> primary_support(
      std::uint32_t root, std::uint32_t limit = kMaxCutLeaves) const {
    if (root >= nodes_.size() || !is_active(root) || limit > kMaxCutLeaves) {
      return std::nullopt;
    }
    std::set<std::uint32_t> support;
    std::unordered_set<std::uint32_t> visiting;
    std::unordered_set<std::uint32_t> done;
    std::function<bool(std::uint32_t)> visit_literal;
    visit_literal = [&](std::uint32_t literal) -> bool {
      literal = resolve(literal);
      const std::uint32_t id = literal >> 1U;
      if (id == 0) return true;
      if (is_primary_input(id)) {
        support.insert(id);
        return support.size() <= limit;
      }
      if (!is_and(id)) return false;
      if (done.count(id)) return true;
      if (!visiting.insert(id).second) return false;
      const bool ok = visit_literal(nodes_[id].lhs) &&
                      visit_literal(nodes_[id].rhs);
      visiting.erase(id);
      done.insert(id);
      return ok;
    };
    if (!visit_literal(root << 1U) || support.size() > limit) {
      return std::nullopt;
    }
    return std::vector<std::uint32_t>(support.begin(), support.end());
  }

  bool truth_table(std::uint32_t root,
                   const std::vector<std::uint32_t>& leaves,
                   TruthTable* output) const {
    if (output == nullptr || root >= nodes_.size() || !is_active(root)) {
      return false;
    }
    std::string error;
    return evaluate_cut(root << 1U, leaves, kNoForbiddenRoot, true, output,
                        &error);
  }

  // Propose an arbitrary local AIG replacement.
  //
  // Local literal encoding is 2*reference xor polarity:
  //   reference 0                   : constant false
  //   references 1..k              : positive cut leaves
  //   references k+1..k+d          : supplied global divisor literals
  //   later references             : LocalAnd results, in order
  //
  // Divisors may come from outside the root cone, but they must themselves be
  // functions of the same cut leaves and must not depend on root.  This is the
  // usual DAG-aware resynthesis setting: existing equivalent logic can be
  // reused without adding gates.  The method returns false for an invalid or
  // non-equivalent proposal and changes nothing.
  bool try_rewrite(std::uint32_t root,
                   const std::vector<std::uint32_t>& leaves,
                   const std::vector<std::uint32_t>& divisors,
                   const std::vector<LocalAnd>& local_ands,
                   std::uint32_t local_output) {
    if (accepted_rewrites_ >= kMaxRewrites || root >= nodes_.size() ||
        !is_and(root) || !is_active(root) ||
        leaves.size() > kMaxCutLeaves || divisors.size() > kMaxDivisors ||
        local_ands.size() > kMaxLocalAnds ||
        nodes_.size() + local_ands.size() > kMaxTotalNodes) {
      return false;
    }

    std::unordered_set<std::uint32_t> unique_leaves;
    for (const std::uint32_t leaf : leaves) {
      if (leaf == 0 || leaf == root || leaf >= nodes_.size() ||
          !is_active(leaf) || !unique_leaves.insert(leaf).second) {
        return false;
      }
    }

    TruthTable old_function;
    std::string error;
    if (!evaluate_cut(root << 1U, leaves, kNoForbiddenRoot, true,
                      &old_function, &error)) {
      return false;
    }

    const std::uint32_t assignments = 1U << leaves.size();
    const std::uint32_t word_count = (assignments + 63U) / 64U;
    const std::uint64_t final_mask =
        (assignments % 64U == 0U)
            ? std::numeric_limits<std::uint64_t>::max()
            : ((std::uint64_t{1} << (assignments % 64U)) - 1U);

    std::vector<TruthTable> values;
    values.reserve(1 + leaves.size() + divisors.size() + local_ands.size());
    TruthTable constant;
    constant.variables = static_cast<std::uint32_t>(leaves.size());
    values.push_back(constant);

    for (std::size_t index = 0; index < leaves.size(); ++index) {
      TruthTable variable;
      variable.variables = static_cast<std::uint32_t>(leaves.size());
      for (std::uint32_t assignment = 0; assignment < assignments;
           ++assignment) {
        if ((assignment >> index) & 1U) {
          variable.words[assignment / 64U] |=
              std::uint64_t{1} << (assignment % 64U);
        }
      }
      values.push_back(variable);
    }

    std::vector<std::uint32_t> normalized_divisors;
    normalized_divisors.reserve(divisors.size());
    for (const std::uint32_t divisor : divisors) {
      if ((divisor >> 1U) >= nodes_.size()) return false;
      std::uint32_t normalized;
      try {
        normalized = resolve(divisor);
      } catch (const std::exception&) {
        return false;
      }
      if ((normalized >> 1U) == root) return false;
      TruthTable divisor_function;
      if (!evaluate_cut(normalized, leaves, root, false, &divisor_function,
                        &error)) {
        return false;
      }
      normalized_divisors.push_back(normalized);
      values.push_back(divisor_function);
    }

    auto local_value = [&](std::uint32_t literal,
                           TruthTable* result) -> bool {
      const std::uint32_t reference = literal >> 1U;
      if (reference >= values.size()) return false;
      *result = values[reference];
      if (literal & 1U) {
        for (std::uint32_t word = 0; word < word_count; ++word) {
          result->words[word] = ~result->words[word];
        }
        result->words[word_count - 1U] &= final_mask;
      }
      return true;
    };

    for (const LocalAnd gate : local_ands) {
      TruthTable lhs;
      TruthTable rhs;
      if (!local_value(gate.lhs, &lhs) || !local_value(gate.rhs, &rhs)) {
        return false;
      }
      TruthTable result;
      result.variables = static_cast<std::uint32_t>(leaves.size());
      for (std::uint32_t word = 0; word < word_count; ++word) {
        result.words[word] = lhs.words[word] & rhs.words[word];
      }
      values.push_back(result);
    }

    TruthTable replacement;
    if (!local_value(local_output, &replacement) ||
        !(replacement == old_function)) {
      return false;
    }

    certificate_ << "R " << root << ' ' << leaves.size() << ' '
                 << normalized_divisors.size() << ' ' << local_ands.size();
    for (const std::uint32_t leaf : leaves) certificate_ << ' ' << leaf;
    for (const std::uint32_t divisor : normalized_divisors) {
      certificate_ << ' ' << divisor;
    }
    for (const LocalAnd gate : local_ands) {
      certificate_ << ' ' << gate.lhs << ' ' << gate.rhs;
    }
    certificate_ << ' ' << local_output << '\n';
    if (!certificate_) {
      throw std::runtime_error("failed while writing rewrite certificate");
    }

    std::vector<std::uint32_t> global_values;
    global_values.reserve(values.size());
    global_values.push_back(0U);
    for (const std::uint32_t leaf : leaves) {
      global_values.push_back(leaf << 1U);
    }
    for (const std::uint32_t divisor : normalized_divisors) {
      global_values.push_back(divisor);
    }
    auto translate_local = [&](std::uint32_t literal) -> std::uint32_t {
      const std::uint32_t reference = literal >> 1U;
      if (reference >= global_values.size()) {
        throw std::runtime_error("internal local-literal translation failure");
      }
      return global_values[reference] ^ (literal & 1U);
    };
    for (const LocalAnd gate : local_ands) {
      const std::uint32_t lhs = translate_local(gate.lhs);
      const std::uint32_t rhs = translate_local(gate.rhs);
      Node node;
      node.kind = Kind::kAnd;
      node.lhs = lhs;
      node.rhs = rhs;
      nodes_.push_back(node);
      const std::uint32_t new_id =
          static_cast<std::uint32_t>(nodes_.size() - 1U);
      redirect_.push_back(new_id << 1U);
      global_values.push_back(new_id << 1U);
    }
    redirect_[root] = translate_local(local_output);
    ++accepted_rewrites_;
    return true;
  }

  // Convenience wrapper for replacing root by an existing global literal.
  // `leaves` must be a structural cut for root and for any external divisor.
  bool replace(std::uint32_t root, std::uint32_t replacement,
               const std::vector<std::uint32_t>& leaves) {
    try {
      replacement = resolve(replacement);
    } catch (const std::exception&) {
      return false;
    }
    const std::uint32_t replacement_id = replacement >> 1U;
    if (replacement_id == 0U) {
      return try_rewrite(root, leaves, {}, {}, replacement & 1U);
    }
    for (std::size_t index = 0; index < leaves.size(); ++index) {
      if (leaves[index] == replacement_id) {
        const std::uint32_t local_literal =
            (static_cast<std::uint32_t>(index) + 1U) << 1U;
        return try_rewrite(root, leaves, {}, {},
                           local_literal ^ (replacement & 1U));
      }
    }
    const std::uint32_t divisor_reference =
        static_cast<std::uint32_t>(leaves.size()) + 1U;
    return try_rewrite(root, leaves, {replacement}, {},
                       divisor_reference << 1U);
  }

  NetworkStats stats() const {
    std::unordered_set<std::uint32_t> reachable;
    std::unordered_map<std::uint32_t, std::uint32_t> depths;
    std::unordered_set<std::uint32_t> visiting;
    std::function<std::uint32_t(std::uint32_t)> depth_literal;
    depth_literal = [&](std::uint32_t literal) -> std::uint32_t {
      literal = resolve(literal);
      const std::uint32_t id = literal >> 1U;
      if (id == 0U || is_primary_input(id)) return 0U;
      const auto cached = depths.find(id);
      if (cached != depths.end()) return cached->second;
      if (!is_and(id) || !visiting.insert(id).second) {
        throw std::runtime_error("invalid or cyclic live AIG");
      }
      reachable.insert(id);
      const std::uint32_t result =
          1U + std::max(depth_literal(nodes_[id].lhs),
                        depth_literal(nodes_[id].rhs));
      visiting.erase(id);
      depths[id] = result;
      return result;
    };
    std::uint32_t max_depth = 0;
    for (const std::uint32_t output : outputs_) {
      max_depth = std::max(max_depth, depth_literal(output));
    }
    return {static_cast<std::uint32_t>(reachable.size()), max_depth};
  }

 private:
  enum class Kind : std::uint8_t { kUnused, kInput, kAnd };
  struct Node {
    Kind kind = Kind::kUnused;
    std::uint32_t lhs = 0;
    std::uint32_t rhs = 0;
  };

  static constexpr std::uint32_t kNoForbiddenRoot =
      std::numeric_limits<std::uint32_t>::max();

  static std::vector<std::uint64_t> parse_numbers(const std::string& line) {
    std::istringstream stream(line);
    std::vector<std::uint64_t> values;
    std::uint64_t value = 0;
    while (stream >> value) values.push_back(value);
    if (!stream.eof()) throw std::runtime_error("malformed numeric AAG line");
    return values;
  }

  void load_aag(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open AAG input: " + path);
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("empty AAG input");
    std::istringstream header(line);
    std::string magic;
    std::uint64_t maximum = 0, inputs = 0, latches = 0, outputs = 0, ands = 0;
    if (!(header >> magic >> maximum >> inputs >> latches >> outputs >> ands) ||
        magic != "aag" || latches != 0 || maximum > kMaxTotalNodes ||
        maximum != inputs + ands || inputs == 0 || outputs == 0) {
      throw std::runtime_error("unsupported AAG header");
    }
    input_count_ = static_cast<std::uint32_t>(inputs);
    first_and_id_ = input_count_ + 1U;
    nodes_.assign(static_cast<std::size_t>(maximum) + 1U, Node{});
    redirect_.resize(nodes_.size());
    for (std::uint32_t id = 0; id < redirect_.size(); ++id) {
      redirect_[id] = id << 1U;
    }
    for (std::uint32_t index = 0; index < input_count_; ++index) {
      if (!std::getline(input, line)) throw std::runtime_error("truncated inputs");
      const auto fields = parse_numbers(line);
      const std::uint32_t expected_id = index + 1U;
      if (fields.size() != 1U || fields[0] != (expected_id << 1U)) {
        throw std::runtime_error("inputs must use consecutive positive literals");
      }
      nodes_[expected_id].kind = Kind::kInput;
    }
    outputs_.reserve(static_cast<std::size_t>(outputs));
    for (std::uint64_t index = 0; index < outputs; ++index) {
      if (!std::getline(input, line)) throw std::runtime_error("truncated outputs");
      const auto fields = parse_numbers(line);
      if (fields.size() != 1U || fields[0] > 2U * maximum + 1U) {
        throw std::runtime_error("invalid output literal");
      }
      outputs_.push_back(static_cast<std::uint32_t>(fields[0]));
    }
    for (std::uint64_t index = 0; index < ands; ++index) {
      if (!std::getline(input, line)) throw std::runtime_error("truncated ANDs");
      const auto fields = parse_numbers(line);
      const std::uint32_t id = first_and_id_ + static_cast<std::uint32_t>(index);
      if (fields.size() != 3U || fields[0] != (id << 1U) ||
          fields[1] >= fields[0] || fields[2] >= fields[0]) {
        throw std::runtime_error("AND nodes must be consecutive and topological");
      }
      nodes_[id].kind = Kind::kAnd;
      nodes_[id].lhs = static_cast<std::uint32_t>(fields[1]);
      nodes_[id].rhs = static_cast<std::uint32_t>(fields[2]);
    }
  }

  static TruthTable inverted(TruthTable value) {
    const std::uint32_t assignments = 1U << value.variables;
    const std::uint32_t word_count = (assignments + 63U) / 64U;
    for (std::uint32_t word = 0; word < word_count; ++word) {
      value.words[word] = ~value.words[word];
    }
    if (assignments % 64U != 0U) {
      value.words[word_count - 1U] &=
          (std::uint64_t{1} << (assignments % 64U)) - 1U;
    }
    return value;
  }

  bool evaluate_cut(std::uint32_t literal,
                    const std::vector<std::uint32_t>& leaves,
                    std::uint32_t forbidden_root, bool require_all_leaves,
                    TruthTable* output, std::string* error) const {
    if (leaves.size() > kMaxCutLeaves) return false;
    std::unordered_map<std::uint32_t, std::size_t> leaf_indices;
    for (std::size_t index = 0; index < leaves.size(); ++index) {
      if (!leaf_indices.emplace(leaves[index], index).second) return false;
    }
    std::vector<bool> used(leaves.size(), false);
    std::unordered_map<std::uint32_t, TruthTable> memo;
    std::unordered_set<std::uint32_t> visiting;
    bool failed = false;
    const std::uint32_t assignments = 1U << leaves.size();

    std::function<TruthTable(std::uint32_t)> evaluate_literal;
    std::function<TruthTable(std::uint32_t)> evaluate_node;
    evaluate_node = [&](std::uint32_t id) -> TruthTable {
      TruthTable zero;
      zero.variables = static_cast<std::uint32_t>(leaves.size());
      if (failed) return zero;
      const auto leaf = leaf_indices.find(id);
      if (leaf != leaf_indices.end()) {
        used[leaf->second] = true;
        TruthTable variable = zero;
        for (std::uint32_t assignment = 0; assignment < assignments;
             ++assignment) {
          if ((assignment >> leaf->second) & 1U) {
            variable.words[assignment / 64U] |=
                std::uint64_t{1} << (assignment % 64U);
          }
        }
        return variable;
      }
      if (id == 0U) return zero;
      if (id == forbidden_root) {
        failed = true;
        if (error) *error = "divisor depends on rewritten root";
        return zero;
      }
      if (is_primary_input(id)) {
        failed = true;
        if (error) *error = "cut does not cover a primary-input path";
        return zero;
      }
      const auto cached = memo.find(id);
      if (cached != memo.end()) return cached->second;
      if (!is_and(id) || !visiting.insert(id).second) {
        failed = true;
        if (error) *error = "invalid or cyclic cut cone";
        return zero;
      }
      TruthTable lhs = evaluate_literal(nodes_[id].lhs);
      TruthTable rhs = evaluate_literal(nodes_[id].rhs);
      visiting.erase(id);
      TruthTable result = zero;
      for (std::size_t word = 0; word < result.words.size(); ++word) {
        result.words[word] = lhs.words[word] & rhs.words[word];
      }
      memo[id] = result;
      return result;
    };
    evaluate_literal = [&](std::uint32_t input_literal) -> TruthTable {
      TruthTable zero;
      zero.variables = static_cast<std::uint32_t>(leaves.size());
      if (failed) return zero;
      std::uint32_t normalized = 0;
      try {
        normalized = resolve(input_literal);
      } catch (const std::exception& exc) {
        failed = true;
        if (error) *error = exc.what();
        return zero;
      }
      TruthTable value = evaluate_node(normalized >> 1U);
      return (normalized & 1U) ? inverted(value) : value;
    };

    *output = evaluate_literal(literal);
    if (failed) return false;
    if (require_all_leaves &&
        std::find(used.begin(), used.end(), false) != used.end()) {
      if (error) *error = "cut contains a leaf outside the root cone";
      return false;
    }
    return true;
  }

  std::vector<Node> nodes_;
  std::vector<std::uint32_t> redirect_;
  std::vector<std::uint32_t> outputs_;
  std::uint32_t input_count_ = 0;
  std::uint32_t first_and_id_ = 0;
  std::uint32_t original_node_count_ = 0;
  std::uint32_t accepted_rewrites_ = 0;
  std::ofstream certificate_;
};

static std::vector<std::uint32_t> boundary_nodes(
    std::uint32_t lhs, std::uint32_t rhs) {
  std::vector<std::uint32_t> leaves;
  const std::uint32_t lhs_id = lhs >> 1U;
  const std::uint32_t rhs_id = rhs >> 1U;
  if (lhs_id != 0U) leaves.push_back(lhs_id);
  if (rhs_id != 0U && rhs_id != lhs_id) leaves.push_back(rhs_id);
  return leaves;
}

}  // namespace certified_aig
