#include <chrono>
#include <cstdlib>
#include <filesystem>

#include <unistd.h>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

namespace {
std::filesystem::path marker_path() {
  const char* tmp = std::getenv("TMPDIR");
  std::filesystem::path root = tmp != nullptr && *tmp != '\0' ? tmp : ".";
  return root / ("gnsdk-pool-kill9-once-" + std::to_string(static_cast<unsigned long long>(::getpid())));
}
}  // namespace

int main() {
  const std::filesystem::path marker = marker_path();
  std::filesystem::remove(marker);
  REQUIRE(::setenv("GNSDK_FAKE_ONCE_FILE", marker.c_str(), 1) == 0);

  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.worker_args = {"--misbehave", "die-midframe-once"};
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  const auto reply = pool.request(proto::Kind::Decompile, R"({"addr":"0x401000"})", 1,
                                  std::chrono::seconds(5));
  REQUIRE(reply.kind == proto::to_u16(proto::Kind::Result));
  REQUIRE(pool.live_workers() == 1);
  pool.stop();
  REQUIRE(pool.live_workers() == 0);
  REQUIRE(std::filesystem::exists(marker));
  std::filesystem::remove(marker);
  REQUIRE(::unsetenv("GNSDK_FAKE_ONCE_FILE") == 0);
  return wtest::exit_code();
}
