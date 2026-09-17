#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace frontier_telemetry {

enum class Column : std::uint32_t {
  TimestampNs = 0,
  ServiceId = 1,
  Severity = 2,
  DurationUs = 3,
  PayloadBytes = 4,
};

constexpr std::size_t kColumnCount = 5;

struct BlockView {
  std::size_t count{};
  std::array<const std::uint64_t *, kColumnCount> columns{};
};

struct MutableBlock {
  std::size_t count{};
  std::array<std::uint64_t *, kColumnCount> columns{};
};

struct EncodedView {
  const std::uint8_t *data{};
  std::size_t size{};
  std::size_t count{};
};

enum class QueryKind : std::uint32_t {
  CountEqual = 0,
  CountRange = 1,
  SumWhereEqual = 2,
  SumWhereRange = 3,
};

struct QuerySpec {
  QueryKind kind{QueryKind::CountEqual};
  Column filter_column{Column::TimestampNs};
  Column value_column{Column::TimestampNs};
  std::uint64_t low{};
  std::uint64_t high{};
};

// The candidate owns the encoded block format. The immutable driver passes the
// row count separately, so the format does not need to repeat it.
bool encode_block(const BlockView &input, std::vector<std::uint8_t> &encoded);

// Decode every value into the supplied, preallocated column buffers.
bool decode_block(const EncodedView &encoded, const MutableBlock &output);

// Execute one exact query on an encoded block. A candidate may decode internally,
// but faster solutions can operate directly on their compressed representation.
std::uint64_t query_block(const EncodedView &encoded, const QuerySpec &query);

}  // namespace frontier_telemetry
