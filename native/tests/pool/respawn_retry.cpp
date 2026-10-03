#include <chrono>
#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <thread>
#include <vector>
#include <unistd.h>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;

int main() {
  auto pattern = (std::filesystem::temp_directory_path() / "gnsdk-retry-XXXXXX").string();
  std::vector<char> name(pattern.begin(), pattern.end());
  name.push_back('\0');
  REQUIRE(::mkdtemp(name.data()) != nullptr);
  const auto marker = std::filesystem::path(name.data()) / "once";
  REQUIRE(::setenv("GNSDK_FAKE_ONCE_FILE", marker.c_str(), 1) == 0);
  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.worker_args = {"--misbehave", "die-midframe-once"};
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);
  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();

  std::atomic_int ready{0}, succeeded{0};
  std::atomic_bool go{false};
  auto request = [&](std::uint64_t id) {
    ++ready;
    while (!go) std::this_thread::yield();
    try {
      const auto reply = pool.request(proto::Kind::Decompile, R"({"addr":"0x401000"})",
                                      id, std::chrono::seconds(5));
      if (reply.kind == proto::to_u16(proto::Kind::Result) && reply.request_id == id)
        ++succeeded;
    } catch (const std::exception &) {}
  };
  std::thread first(request, 1), second(request, 2);
  while (ready != 2) std::this_thread::yield();
  go = true;
  first.join();
  second.join();
  REQUIRE(succeeded == 2);
  REQUIRE(std::filesystem::exists(marker));

  pool.stop();
  REQUIRE(pool.live_workers() == 0);
  REQUIRE(::unsetenv("GNSDK_FAKE_ONCE_FILE") == 0);
  std::filesystem::remove(marker);
  std::filesystem::remove(name.data());
  return wtest::exit_code();
}
