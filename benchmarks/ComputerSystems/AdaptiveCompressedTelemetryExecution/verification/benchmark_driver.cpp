#include "codec_api.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <utility>
#include <vector>

namespace ft = frontier_telemetry;

namespace {

constexpr std::array<char, 8> kRawMagic{'T', 'E', 'L', 'R', 'A', 'W', '0', '1'};
constexpr std::array<char, 8> kEncodedMagic{'T', 'E', 'L', 'C', 'M', 'P', '0', '1'};

struct RawDataset {
  std::size_t rows{};
  std::array<std::vector<std::uint64_t>, ft::kColumnCount> columns;
};

struct EncodedBlock {
  std::size_t count{};
  std::vector<std::uint8_t> bytes;
};

struct EncodedDataset {
  std::size_t rows{};
  std::size_t block_rows{};
  std::vector<EncodedBlock> blocks;
};

struct NamedQuery {
  std::string name;
  ft::QuerySpec spec;
};

using Clock = std::chrono::steady_clock;

std::uint64_t load_le64(const std::uint8_t *p) {
  std::uint64_t value = 0;
  for (unsigned shift = 0; shift < 64; shift += 8) {
    value |= static_cast<std::uint64_t>(*p++) << shift;
  }
  return value;
}

std::uint32_t load_le32(const std::uint8_t *p) {
  std::uint32_t value = 0;
  for (unsigned shift = 0; shift < 32; shift += 8) {
    value |= static_cast<std::uint32_t>(*p++) << shift;
  }
  return value;
}

void write_le64(std::ostream &out, std::uint64_t value) {
  std::array<char, 8> bytes{};
  for (unsigned index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<char>((value >> (index * 8)) & 0xffU);
  }
  out.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

void write_le32(std::ostream &out, std::uint32_t value) {
  std::array<char, 4> bytes{};
  for (unsigned index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<char>((value >> (index * 8)) & 0xffU);
  }
  out.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

std::vector<std::uint8_t> read_all(const std::string &path) {
  std::ifstream in(path, std::ios::binary | std::ios::ate);
  if (!in) {
    throw std::runtime_error("cannot open input: " + path);
  }
  const std::streamoff end = in.tellg();
  if (end < 0) {
    throw std::runtime_error("cannot determine input size: " + path);
  }
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(end));
  in.seekg(0);
  if (!bytes.empty()) {
    in.read(reinterpret_cast<char *>(bytes.data()),
            static_cast<std::streamsize>(bytes.size()));
  }
  if (!in) {
    throw std::runtime_error("failed while reading input: " + path);
  }
  return bytes;
}

RawDataset read_raw(const std::string &path) {
  const std::vector<std::uint8_t> bytes = read_all(path);
  if (bytes.size() < 16 ||
      !std::equal(kRawMagic.begin(), kRawMagic.end(), bytes.begin())) {
    throw std::runtime_error("invalid raw dataset header");
  }
  const std::uint64_t rows64 = load_le64(bytes.data() + 8);
  if (rows64 > std::numeric_limits<std::size_t>::max()) {
    throw std::runtime_error("raw dataset row count is too large");
  }
  const std::size_t rows = static_cast<std::size_t>(rows64);
  if (rows > (std::numeric_limits<std::size_t>::max() - 16) /
                 (ft::kColumnCount * sizeof(std::uint64_t))) {
    throw std::runtime_error("raw dataset size overflows");
  }
  const std::size_t expected =
      16 + rows * ft::kColumnCount * sizeof(std::uint64_t);
  if (bytes.size() != expected) {
    throw std::runtime_error("raw dataset length mismatch");
  }

  RawDataset dataset;
  dataset.rows = rows;
  const std::uint8_t *cursor = bytes.data() + 16;
  for (auto &column : dataset.columns) {
    column.resize(rows);
    for (std::size_t row = 0; row < rows; ++row) {
      column[row] = load_le64(cursor);
      cursor += sizeof(std::uint64_t);
    }
  }
  return dataset;
}

void write_raw(const std::string &path, const RawDataset &dataset) {
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  if (!out) {
    throw std::runtime_error("cannot open decoded output: " + path);
  }
  out.write(kRawMagic.data(), static_cast<std::streamsize>(kRawMagic.size()));
  write_le64(out, static_cast<std::uint64_t>(dataset.rows));
  for (const auto &column : dataset.columns) {
    if (column.size() != dataset.rows) {
      throw std::runtime_error("decoded column length mismatch");
    }
    for (const std::uint64_t value : column) {
      write_le64(out, value);
    }
  }
  if (!out) {
    throw std::runtime_error("failed while writing decoded output");
  }
}

void write_encoded(const std::string &path, const EncodedDataset &dataset) {
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  if (!out) {
    throw std::runtime_error("cannot open encoded output: " + path);
  }
  out.write(kEncodedMagic.data(),
            static_cast<std::streamsize>(kEncodedMagic.size()));
  write_le64(out, static_cast<std::uint64_t>(dataset.rows));
  write_le32(out, static_cast<std::uint32_t>(dataset.block_rows));
  write_le32(out, static_cast<std::uint32_t>(dataset.blocks.size()));
  for (const EncodedBlock &block : dataset.blocks) {
    write_le32(out, static_cast<std::uint32_t>(block.count));
    write_le64(out, static_cast<std::uint64_t>(block.bytes.size()));
    if (!block.bytes.empty()) {
      out.write(reinterpret_cast<const char *>(block.bytes.data()),
                static_cast<std::streamsize>(block.bytes.size()));
    }
  }
  if (!out) {
    throw std::runtime_error("failed while writing encoded output");
  }
}

EncodedDataset read_encoded(const std::string &path) {
  const std::vector<std::uint8_t> bytes = read_all(path);
  if (bytes.size() < 24 ||
      !std::equal(kEncodedMagic.begin(), kEncodedMagic.end(), bytes.begin())) {
    throw std::runtime_error("invalid encoded dataset header");
  }
  const std::uint8_t *cursor = bytes.data() + 8;
  const std::uint8_t *end = bytes.data() + bytes.size();
  EncodedDataset dataset;
  dataset.rows = static_cast<std::size_t>(load_le64(cursor));
  cursor += 8;
  dataset.block_rows = static_cast<std::size_t>(load_le32(cursor));
  cursor += 4;
  const std::size_t block_count = static_cast<std::size_t>(load_le32(cursor));
  cursor += 4;
  if (dataset.block_rows == 0 || block_count == 0) {
    throw std::runtime_error("encoded dataset has no blocks");
  }
  dataset.blocks.reserve(block_count);
  std::size_t total_rows = 0;
  for (std::size_t index = 0; index < block_count; ++index) {
    if (static_cast<std::size_t>(end - cursor) < 12) {
      throw std::runtime_error("truncated encoded block header");
    }
    EncodedBlock block;
    block.count = static_cast<std::size_t>(load_le32(cursor));
    cursor += 4;
    const std::uint64_t size64 = load_le64(cursor);
    cursor += 8;
    if (size64 > static_cast<std::uint64_t>(end - cursor)) {
      throw std::runtime_error("truncated encoded block payload");
    }
    const std::size_t size = static_cast<std::size_t>(size64);
    block.bytes.assign(cursor, cursor + size);
    cursor += size;
    if (block.count == 0 || block.count > dataset.block_rows) {
      throw std::runtime_error("invalid encoded block row count");
    }
    total_rows += block.count;
    dataset.blocks.push_back(std::move(block));
  }
  if (cursor != end || total_rows != dataset.rows) {
    throw std::runtime_error("encoded dataset totals do not match header");
  }
  return dataset;
}

std::uint64_t file_size_bytes(const std::string &path) {
  std::ifstream in(path, std::ios::binary | std::ios::ate);
  if (!in) {
    throw std::runtime_error("cannot inspect file size: " + path);
  }
  const std::streamoff size = in.tellg();
  if (size < 0) {
    throw std::runtime_error("invalid file size: " + path);
  }
  return static_cast<std::uint64_t>(size);
}

double percentile_median(std::vector<double> values) {
  if (values.empty()) {
    throw std::runtime_error("no timing samples were collected");
  }
  std::sort(values.begin(), values.end());
  const std::size_t middle = values.size() / 2;
  if (values.size() % 2 == 1) {
    return values[middle];
  }
  return (values[middle - 1] + values[middle]) / 2.0;
}

long peak_rss_kib() {
  rusage usage{};
  if (getrusage(RUSAGE_SELF, &usage) != 0) {
    return 0;
  }
  return usage.ru_maxrss;
}

void add_timing_metrics(std::map<std::string, double> &metrics,
                        const std::vector<double> &samples) {
  metrics["median_ns"] = percentile_median(samples);
  metrics["min_ns"] = *std::min_element(samples.begin(), samples.end());
  metrics["max_ns"] = *std::max_element(samples.begin(), samples.end());
  metrics["timing_rounds"] = static_cast<double>(samples.size());
  for (std::size_t index = 0; index < samples.size(); ++index) {
    metrics["sample_" + std::to_string(index) + "_ns"] = samples[index];
  }
}

void write_metrics(const std::string &path,
                   const std::map<std::string, double> &metrics) {
  std::ofstream out(path, std::ios::trunc);
  if (!out) {
    throw std::runtime_error("cannot open metrics output: " + path);
  }
  out << std::setprecision(17);
  for (const auto &[key, value] : metrics) {
    if (!std::isfinite(value)) {
      throw std::runtime_error("non-finite metric: " + key);
    }
    out << key << '=' << value << '\n';
  }
}

std::size_t parse_size(const char *text, const std::string &label) {
  try {
    const unsigned long long value = std::stoull(text);
    if (value == 0 || value > std::numeric_limits<std::size_t>::max()) {
      throw std::out_of_range("range");
    }
    return static_cast<std::size_t>(value);
  } catch (const std::exception &) {
    throw std::runtime_error("invalid " + label + ": " + text);
  }
}

double parse_positive_double(const char *text, const std::string &label) {
  try {
    const double value = std::stod(text);
    if (!std::isfinite(value) || value <= 0.0) {
      throw std::out_of_range("range");
    }
    return value;
  } catch (const std::exception &) {
    throw std::runtime_error("invalid " + label + ": " + text);
  }
}

ft::BlockView block_view(const RawDataset &dataset, std::size_t offset,
                         std::size_t count) {
  ft::BlockView view;
  view.count = count;
  for (std::size_t column = 0; column < ft::kColumnCount; ++column) {
    view.columns[column] = dataset.columns[column].data() + offset;
  }
  return view;
}

EncodedDataset encode_all(const RawDataset &raw, std::size_t block_rows,
                          double max_encoded_ratio) {
  EncodedDataset result;
  result.rows = raw.rows;
  result.block_rows = block_rows;
  for (std::size_t offset = 0; offset < raw.rows; offset += block_rows) {
    const std::size_t count = std::min(block_rows, raw.rows - offset);
    EncodedBlock block;
    block.count = count;
    if (!ft::encode_block(block_view(raw, offset, count), block.bytes)) {
      throw std::runtime_error("candidate encode_block returned false");
    }
    const double raw_bytes =
        static_cast<double>(count * ft::kColumnCount * sizeof(std::uint64_t));
    const double allowed = raw_bytes * max_encoded_ratio + 4096.0;
    if (static_cast<double>(block.bytes.size()) > allowed) {
      throw std::runtime_error("candidate encoded block exceeds size limit");
    }
    result.blocks.push_back(std::move(block));
  }
  return result;
}

int run_encode(int argc, char **argv) {
  if (argc != 9) {
    throw std::runtime_error(
        "encode usage: driver encode RAW ENCODED METRICS BLOCK_ROWS WARMUP "
        "ROUNDS MAX_RATIO");
  }
  const RawDataset raw = read_raw(argv[2]);
  const std::size_t block_rows = parse_size(argv[5], "block rows");
  const std::size_t warmup = parse_size(argv[6], "warmup rounds");
  const std::size_t rounds = parse_size(argv[7], "measured rounds");
  const double max_ratio = parse_positive_double(argv[8], "max encoded ratio");

  for (std::size_t index = 0; index < warmup; ++index) {
    EncodedDataset ignored = encode_all(raw, block_rows, max_ratio);
    if (ignored.blocks.empty()) {
      throw std::runtime_error("candidate produced no encoded blocks");
    }
  }

  std::vector<double> samples;
  samples.reserve(rounds);
  EncodedDataset final_result;
  for (std::size_t index = 0; index < rounds; ++index) {
    const auto started = Clock::now();
    EncodedDataset current = encode_all(raw, block_rows, max_ratio);
    const auto finished = Clock::now();
    samples.push_back(static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(finished - started)
            .count()));
    final_result = std::move(current);
  }
  write_encoded(argv[3], final_result);

  const double logical_bytes = static_cast<double>(
      raw.rows * ft::kColumnCount * sizeof(std::uint64_t));
  const double median_ns = percentile_median(samples);
  std::map<std::string, double> metrics{
      {"rows", static_cast<double>(raw.rows)},
      {"block_count", static_cast<double>(final_result.blocks.size())},
      {"logical_bytes", logical_bytes},
      {"encoded_bytes", static_cast<double>(file_size_bytes(argv[3]))},
      {"throughput_gib_s", logical_bytes / (median_ns * (1ULL << 30) / 1e9)},
      {"peak_rss_kib", static_cast<double>(peak_rss_kib())},
  };
  add_timing_metrics(metrics, samples);
  write_metrics(argv[4], metrics);
  return 0;
}

RawDataset allocate_decoded(std::size_t rows) {
  RawDataset output;
  output.rows = rows;
  for (auto &column : output.columns) {
    column.resize(rows);
  }
  return output;
}

void decode_all(const EncodedDataset &encoded, RawDataset &output) {
  std::size_t offset = 0;
  for (const EncodedBlock &block : encoded.blocks) {
    ft::MutableBlock destination;
    destination.count = block.count;
    for (std::size_t column = 0; column < ft::kColumnCount; ++column) {
      destination.columns[column] = output.columns[column].data() + offset;
    }
    const ft::EncodedView view{block.bytes.data(), block.bytes.size(), block.count};
    if (!ft::decode_block(view, destination)) {
      throw std::runtime_error("candidate decode_block returned false");
    }
    offset += block.count;
  }
  if (offset != output.rows) {
    throw std::runtime_error("decoded row count mismatch");
  }
}

int run_decode(int argc, char **argv) {
  if (argc != 7) {
    throw std::runtime_error(
        "decode usage: driver decode ENCODED RAW_OUT METRICS WARMUP ROUNDS");
  }
  const EncodedDataset encoded = read_encoded(argv[2]);
  RawDataset output = allocate_decoded(encoded.rows);
  const std::size_t warmup = parse_size(argv[5], "warmup rounds");
  const std::size_t rounds = parse_size(argv[6], "measured rounds");

  for (std::size_t index = 0; index < warmup; ++index) {
    decode_all(encoded, output);
  }
  std::vector<double> samples;
  samples.reserve(rounds);
  for (std::size_t index = 0; index < rounds; ++index) {
    const auto started = Clock::now();
    decode_all(encoded, output);
    const auto finished = Clock::now();
    samples.push_back(static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(finished - started)
            .count()));
  }
  write_raw(argv[3], output);

  const double logical_bytes = static_cast<double>(
      encoded.rows * ft::kColumnCount * sizeof(std::uint64_t));
  const double median_ns = percentile_median(samples);
  std::map<std::string, double> metrics{
      {"rows", static_cast<double>(encoded.rows)},
      {"logical_bytes", logical_bytes},
      {"throughput_gib_s", logical_bytes / (median_ns * (1ULL << 30) / 1e9)},
      {"peak_rss_kib", static_cast<double>(peak_rss_kib())},
  };
  add_timing_metrics(metrics, samples);
  write_metrics(argv[4], metrics);
  return 0;
}

ft::Column parse_column(std::uint32_t value) {
  if (value >= ft::kColumnCount) {
    throw std::runtime_error("query references an unknown column");
  }
  return static_cast<ft::Column>(value);
}

std::vector<NamedQuery> read_queries(const std::string &path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("cannot open query file: " + path);
  }
  std::vector<NamedQuery> queries;
  std::string line;
  while (std::getline(in, line)) {
    if (line.empty() || line.front() == '#') {
      continue;
    }
    std::istringstream row(line);
    NamedQuery query;
    std::uint32_t kind = 0;
    std::uint32_t filter = 0;
    std::uint32_t value = 0;
    if (!(row >> query.name >> kind >> filter >> value >> query.spec.low >>
          query.spec.high)) {
      throw std::runtime_error("invalid query row: " + line);
    }
    if (kind > static_cast<std::uint32_t>(ft::QueryKind::SumWhereRange)) {
      throw std::runtime_error("query uses an unknown kind");
    }
    query.spec.kind = static_cast<ft::QueryKind>(kind);
    query.spec.filter_column = parse_column(filter);
    query.spec.value_column = parse_column(value);
    queries.push_back(std::move(query));
  }
  if (queries.empty()) {
    throw std::runtime_error("query file contains no queries");
  }
  return queries;
}

std::vector<std::uint64_t> execute_queries(
    const EncodedDataset &encoded, const std::vector<NamedQuery> &queries) {
  std::vector<std::uint64_t> results(queries.size(), 0);
  for (std::size_t query_index = 0; query_index < queries.size(); ++query_index) {
    for (const EncodedBlock &block : encoded.blocks) {
      const ft::EncodedView view{block.bytes.data(), block.bytes.size(), block.count};
      results[query_index] += ft::query_block(view, queries[query_index].spec);
    }
  }
  return results;
}

void write_query_results(const std::string &path,
                         const std::vector<NamedQuery> &queries,
                         const std::vector<std::uint64_t> &results) {
  if (queries.size() != results.size()) {
    throw std::runtime_error("query result count mismatch");
  }
  std::ofstream out(path, std::ios::trunc);
  if (!out) {
    throw std::runtime_error("cannot open query result output: " + path);
  }
  for (std::size_t index = 0; index < queries.size(); ++index) {
    out << queries[index].name << '\t' << results[index] << '\n';
  }
}

int run_query(int argc, char **argv) {
  if (argc != 8) {
    throw std::runtime_error(
        "query usage: driver query ENCODED QUERIES RESULTS METRICS WARMUP "
        "ROUNDS");
  }
  const EncodedDataset encoded = read_encoded(argv[2]);
  const std::vector<NamedQuery> queries = read_queries(argv[3]);
  const std::size_t warmup = parse_size(argv[6], "warmup rounds");
  const std::size_t rounds = parse_size(argv[7], "measured rounds");

  for (std::size_t index = 0; index < warmup; ++index) {
    const std::vector<std::uint64_t> ignored = execute_queries(encoded, queries);
    if (ignored.size() != queries.size()) {
      throw std::runtime_error("candidate query warmup failed");
    }
  }
  std::vector<double> samples;
  samples.reserve(rounds);
  std::vector<std::uint64_t> final_results;
  for (std::size_t index = 0; index < rounds; ++index) {
    const auto started = Clock::now();
    std::vector<std::uint64_t> current = execute_queries(encoded, queries);
    const auto finished = Clock::now();
    samples.push_back(static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(finished - started)
            .count()));
    final_results = std::move(current);
  }
  write_query_results(argv[4], queries, final_results);

  const double logical_bytes = static_cast<double>(
      encoded.rows * ft::kColumnCount * sizeof(std::uint64_t));
  const double median_ns = percentile_median(samples);
  std::map<std::string, double> metrics{
      {"rows", static_cast<double>(encoded.rows)},
      {"logical_bytes", logical_bytes},
      {"query_count", static_cast<double>(queries.size())},
      {"scanned_gib_s",
       logical_bytes * static_cast<double>(queries.size()) /
           (median_ns * (1ULL << 30) / 1e9)},
      {"peak_rss_kib", static_cast<double>(peak_rss_kib())},
  };
  add_timing_metrics(metrics, samples);
  write_metrics(argv[5], metrics);
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  try {
    if (argc < 2) {
      throw std::runtime_error("missing driver mode");
    }
    const std::string mode = argv[1];
    if (mode == "encode") {
      return run_encode(argc, argv);
    }
    if (mode == "decode") {
      return run_decode(argc, argv);
    }
    if (mode == "query") {
      return run_query(argc, argv);
    }
    throw std::runtime_error("unknown driver mode: " + mode);
  } catch (const std::exception &error) {
    std::cerr << "benchmark_driver: " << error.what() << '\n';
    return 2;
  }
}
