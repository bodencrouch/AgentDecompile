#include <chrono>
#include <string>

#include "gnsdk/pool.hpp"
#include "worker/json_min.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

int main() {
  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  // The fake accepts the real worker's required option but does not require a
  // real spec directory; keeping this explicit tests argument construction.
  config.sleigh_home = "/nonexistent";
  config.workers = 2;
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  REQUIRE(pool.live_workers() == 2);
  const auto reply = pool.request(proto::Kind::Decompile,
      R"({"addr":"0x401000","tokens":false,"deadline_ms":100})", 17,
      std::chrono::milliseconds(1000));
  REQUIRE(reply.kind == proto::to_u16(proto::Kind::Result));
  REQUIRE(reply.request_id == 17);
  gnsdk::json::Value value;
  REQUIRE(gnsdk::json::parse(reply.json(), value));
  std::string text;
  REQUIRE(value.get_string("c", text));
  REQUIRE(text == "/* fake */");
  pool.stop();
  REQUIRE(pool.live_workers() == 0);
  return wtest::exit_code();
}
