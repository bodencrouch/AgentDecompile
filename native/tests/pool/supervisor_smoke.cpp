#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <sys/wait.h>
#include <unistd.h>

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

  auto pattern = (std::filesystem::temp_directory_path() / "gnsdk-sweep-XXXXXX").string();
  REQUIRE(::mkdtemp(pattern.data()) != nullptr);
  const std::filesystem::path root(pattern);
  config.tmpdir = root;
  const pid_t dead = ::fork();
  REQUIRE(dead >= 0);
  if (dead == 0)
    ::_exit(0);
  int status = 0;
  REQUIRE(::waitpid(dead, &status, 0) == dead);
  const auto stale = root / (".gnsdk-pool-" + std::to_string(dead));
  const auto live = root / (".gnsdk-pool-" + std::to_string(::getpid()));
  const auto overflow = root / (".gnsdk-pool-" + std::to_string((1ULL << 32) + dead));
  const auto regular = root / (".gnsdk-pool-0" + std::to_string(dead));
  const auto link = root / (".gnsdk-pool-00" + std::to_string(dead));
  std::filesystem::create_directory(stale);
  std::filesystem::create_directory(live);
  std::filesystem::create_directory(overflow);
  std::ofstream(regular) << "preserve";
  std::filesystem::create_directory_symlink(live, link);

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  REQUIRE(!std::filesystem::exists(stale));
  REQUIRE(std::filesystem::exists(live));
  REQUIRE(std::filesystem::exists(overflow));
  REQUIRE(std::filesystem::is_regular_file(regular));
  REQUIRE(std::filesystem::is_symlink(link));
  REQUIRE(pool.live_workers() == 2);
  const auto engines = pool.engine_infos();
  REQUIRE(engines.size() == 2);
  REQUIRE(engines[0].engine_source == "fake-worker");
  REQUIRE(engines[0].engine_abi == "0.1.0");
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
  std::filesystem::remove(link);
  std::filesystem::remove(regular);
  std::filesystem::remove(overflow);
  std::filesystem::remove(live);
  std::filesystem::remove(root);
  return wtest::exit_code();
}
