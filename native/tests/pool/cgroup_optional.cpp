#include <chrono>

#include <unistd.h>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

int main() {
  const bool delegated =
      ::access("/sys/fs/cgroup/cgroup.subtree_control", W_OK) == 0;

  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.cgroup_memory_max = 128ull << 20;
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  REQUIRE(pool.live_workers() == 1);
  REQUIRE(pool.hard_memory_cap() == delegated);
  pool.stop();
  REQUIRE(pool.live_workers() == 0);
  return wtest::exit_code();
}
