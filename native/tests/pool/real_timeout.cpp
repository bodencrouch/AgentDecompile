#include <chrono>
#include <stdexcept>

#include "gnsdk/pool.hpp"
#include "worker/protocol.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

int main() {
  gnsdk::pool::Config config;
  config.worker = GNSDK_WORKER_PATH;
  config.sleigh_home = GNSDK_SLEIGH_HOME;
  config.worker_args = {"--test-decompile-delay-ms", "200"};
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  const auto opened = pool.request(proto::Kind::OpenSnapshot,
      R"({"path":")" GNSDK_TIMEOUT_SAVEFILE R"("})", 1,
      std::chrono::seconds(5));
  REQUIRE(opened.kind == proto::to_u16(proto::Kind::Result));

  bool timed_out = false;
  try {
    (void)pool.request(proto::Kind::Decompile,
        R"({"addr":"0x400000","tokens":false,"deadline_ms":5000,"printer":"c"})", 2,
        std::chrono::milliseconds(10));
  } catch (const std::runtime_error&) {
    timed_out = true;
  }
  REQUIRE(timed_out);
  REQUIRE(pool.live_workers() == 0);
  pool.stop();
  return wtest::exit_code();
}
