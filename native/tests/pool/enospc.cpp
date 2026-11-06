#include <chrono>
#include <stdexcept>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

int main() {
  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.tmpdir = "/dev/full/gnsdk-pool";
  config.startup_grace = std::chrono::milliseconds(100);
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  bool failed = false;
  try {
    pool.start();
  } catch (const std::runtime_error&) {
    failed = true;
  }
  REQUIRE(failed);
  REQUIRE(pool.live_workers() == 0);
  pool.stop();
  return wtest::exit_code();
}
