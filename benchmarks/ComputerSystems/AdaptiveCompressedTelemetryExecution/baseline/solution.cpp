#include "codec_api.h"

// EVOLVE-BLOCK-START
#include <cstring>
#include <limits>

namespace frontier_telemetry {

namespace {

constexpr std::size_t column_index(Column column) {
  return static_cast<std::size_t>(column);
}

bool raw_size(std::size_t count, std::size_t &bytes) {
  constexpr std::size_t width = kColumnCount * sizeof(std::uint64_t);
  if (count > std::numeric_limits<std::size_t>::max() / width) {
    return false;
  }
  bytes = count * width;
  return true;
}

std::uint64_t load_value(const EncodedView &encoded, Column column,
                         std::size_t row) {
  const std::size_t offset =
      (column_index(column) * encoded.count + row) * sizeof(std::uint64_t);
  std::uint64_t value = 0;
  std::memcpy(&value, encoded.data + offset, sizeof(value));
  return value;
}

}  // namespace

bool encode_block(const BlockView &input, std::vector<std::uint8_t> &encoded) {
  std::size_t bytes = 0;
  if (!raw_size(input.count, bytes)) {
    return false;
  }
  encoded.resize(bytes);
  for (std::size_t column = 0; column < kColumnCount; ++column) {
    if (input.count != 0 && input.columns[column] == nullptr) {
      return false;
    }
    std::memcpy(encoded.data() + column * input.count * sizeof(std::uint64_t),
                input.columns[column], input.count * sizeof(std::uint64_t));
  }
  return true;
}

bool decode_block(const EncodedView &encoded, const MutableBlock &output) {
  std::size_t expected = 0;
  if (encoded.count != output.count || !raw_size(encoded.count, expected) ||
      encoded.size != expected) {
    return false;
  }
  for (std::size_t column = 0; column < kColumnCount; ++column) {
    if (output.count != 0 && output.columns[column] == nullptr) {
      return false;
    }
    std::memcpy(output.columns[column],
                encoded.data + column * output.count * sizeof(std::uint64_t),
                output.count * sizeof(std::uint64_t));
  }
  return true;
}

std::uint64_t query_block(const EncodedView &encoded, const QuerySpec &query) {
  std::uint64_t result = 0;
  for (std::size_t row = 0; row < encoded.count; ++row) {
    const std::uint64_t filter =
        load_value(encoded, query.filter_column, row);
    switch (query.kind) {
      case QueryKind::CountEqual:
        result += static_cast<std::uint64_t>(filter == query.low);
        break;
      case QueryKind::CountRange:
        result +=
            static_cast<std::uint64_t>(filter >= query.low && filter <= query.high);
        break;
      case QueryKind::SumWhereEqual:
        if (filter == query.low) {
          result += load_value(encoded, query.value_column, row);
        }
        break;
      case QueryKind::SumWhereRange:
        if (filter >= query.low && filter <= query.high) {
          result += load_value(encoded, query.value_column, row);
        }
        break;
    }
  }
  return result;
}
}  // namespace frontier_telemetry
// EVOLVE-BLOCK-END
