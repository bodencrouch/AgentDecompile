#include <chrono>
#include <stdexcept>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

int main() {
  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.worker_args = {"--misbehave", "hang-ignore-term"};
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);
  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  const auto begin = std::chrono::steady_clock::now();
  bool timed_out = false;
  try {
    (void)pool.request(proto::Kind::Decompile, R"({"addr":"0x401000","deadline_ms":1})", 1,
                       std::chrono::milliseconds(10));
  } catch (const std::runtime_error&) { timed_out = true; }
  const auto elapsed = std::chrono::steady_clock::now() - begin;
  REQUIRE(timed_out);
  REQUIRE(elapsed < std::chrono::seconds(1));
  REQUIRE(pool.live_workers() == 0);
  pool.stop();
  return wtest::exit_code();
}
