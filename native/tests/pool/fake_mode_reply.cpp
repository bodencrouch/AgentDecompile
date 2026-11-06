#include <chrono>
#include <string>
#include <thread>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

int main(int argc, char** argv) {
  REQUIRE(argc == 2);
  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.worker_args = {"--misbehave", argv[1]};
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  const auto reply = pool.request(proto::Kind::Decompile, R"({"addr":"0x401000"})", 1,
                                  std::chrono::seconds(5));
  REQUIRE(reply.kind == proto::to_u16(proto::Kind::Result));
  if (std::string(argv[1]) == "garbage-stderr") {
    std::this_thread::sleep_for(std::chrono::milliseconds(25));
  }
  pool.stop();
  if (std::string(argv[1]) == "garbage-stderr") {
    REQUIRE(!pool.stderr_tail().empty());
  }
  REQUIRE(pool.live_workers() == 0);
  return wtest::exit_code();
}
