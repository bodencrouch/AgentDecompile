#include <chrono>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

int main() {
  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.worker_args = {"--misbehave", "exit-4"};
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);
  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();

  const auto first = pool.request(proto::Kind::Decompile, R"({"addr":"0x401000"})", 1,
                                  std::chrono::milliseconds(1000));
  REQUIRE(first.kind == proto::to_u16(proto::Kind::Result));
  const auto second = pool.request(proto::Kind::Decompile, R"({"addr":"0x401000"})", 2,
                                   std::chrono::milliseconds(1000));
  REQUIRE(second.kind == proto::to_u16(proto::Kind::Result));

  pool.stop();
  REQUIRE(pool.live_workers() == 0);
  return wtest::exit_code();
}
