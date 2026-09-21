#include <cstddef>
#include <cstdint>
#include <vector>

#include "worker/json_min.hpp"
#include "worker/protocol.hpp"

// The wire decoder is deliberately fed in hostile chunk boundaries: this is
// the same incremental entrypoint the pool uses after poll(2), not a separate
// fuzz-only parser.
extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
  gnsdk::proto::FrameReader reader(64 * 1024);
  std::size_t cursor = 0;
  while (cursor < size && !reader.fatal()) {
    const std::size_t step = 1 + (static_cast<std::size_t>(data[cursor]) % 97);
    const std::size_t take = step < size - cursor ? step : size - cursor;
    cursor += reader.feed(data + cursor, take);
    gnsdk::proto::Frame frame;
    while (reader.next(frame)) {
      gnsdk::json::Value ignored;
      (void)gnsdk::json::parse(frame.payload_view(), ignored);
    }
  }
  reader.end_of_input();
  return 0;
}
