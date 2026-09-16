#include <chrono>
#include <atomic>
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
  const bool flood = std::string(argv[1]) == "garbage-stderr";
  if (flood) config.workers = 2;

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  std::atomic_bool done{false};
  std::atomic_bool concurrent_ok{true};
  std::thread observer;
  std::thread requester;
  if (flood) {
    observer = std::thread([&] {
      while (!done) {
        if (pool.stderr_tail().size() > 64 * 1024) concurrent_ok = false;
        (void)pool.live_workers();
        (void)pool.engine_infos();
        std::this_thread::yield();
      }
    });
    requester = std::thread([&] {
      try {
        for (std::uint64_t id = 10; id < 30; ++id) {
          const auto reply = pool.request(proto::Kind::Decompile, R"({"addr":"0x401000"})",
                                           id, std::chrono::seconds(5));
          if (reply.request_id != id) concurrent_ok = false;
        }
      } catch (const std::exception &) { concurrent_ok = false; }
    });
  }
  const auto reply = pool.request(proto::Kind::Decompile, R"({"addr":"0x401000"})", 1,
                                  std::chrono::seconds(5));
  REQUIRE(reply.kind == proto::to_u16(proto::Kind::Result));
  if (std::string(argv[1]) == "garbage-stderr") {
    std::this_thread::sleep_for(std::chrono::milliseconds(25));
  }
  if (requester.joinable()) requester.join();
  pool.stop();
  done = true;
  if (observer.joinable()) observer.join();
  REQUIRE(concurrent_ok);
  if (std::string(argv[1]) == "garbage-stderr") {
    REQUIRE(!pool.stderr_tail().empty());
  }
  REQUIRE(pool.live_workers() == 0);
  return wtest::exit_code();
}
