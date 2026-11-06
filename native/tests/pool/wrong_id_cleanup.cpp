#include <chrono>
#include <stdexcept>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

int main() {
  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.worker_args = {"--misbehave", "reply-wrong-id"};
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);
  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  bool rejected = false;
  try {
    (void)pool.request(proto::Kind::Decompile, R"({"addr":"0x401000","deadline_ms":100})", 17,
                       std::chrono::milliseconds(500));
  } catch (const std::runtime_error&) { rejected = true; }
  REQUIRE(rejected);
  REQUIRE(pool.live_workers() == 0);
  pool.stop();
  return wtest::exit_code();
}
