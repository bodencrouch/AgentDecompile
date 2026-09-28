#include <chrono>
#include <string>

#include "gnsdk/pool.hpp"
#include "worker/json_min.hpp"
#include "worker/protocol.hpp"
#include "wtest.hpp"

namespace json = gnsdk::json;
namespace proto = gnsdk::proto;

int main() {
  gnsdk::pool::Config config;
  config.worker = GNSDK_WORKER_PATH;
  config.sleigh_home = GNSDK_SLEIGH_HOME;
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  const auto opened = pool.request(proto::Kind::OpenSnapshot,
      R"({"path":")" GNSDK_SAVEFILE R"("})", 1,
      std::chrono::seconds(5));
  REQUIRE(opened.kind == proto::to_u16(proto::Kind::Result));

  const auto reply = pool.request(proto::Kind::Decompile,
      R"({"addr":"0x0000000100000470","tokens":false,"deadline_ms":5000,"printer":"c"})", 2,
      std::chrono::seconds(5));
  REQUIRE(reply.kind == proto::to_u16(proto::Kind::Result));
  json::Value payload;
  REQUIRE(json::parse(reply.json(), payload));
  std::string c_text;
  REQUIRE(payload.get_string("c", c_text));
  REQUIRE(c_text.find("_add") != std::string::npos);
  pool.stop();
  REQUIRE(pool.live_workers() == 0);
  return wtest::exit_code();
}
