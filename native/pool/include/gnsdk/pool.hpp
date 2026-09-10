// Process-isolated worker supervisor.  The implementation deliberately owns
// child fds and pidfds so teardown is deterministic even on caller errors.
#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "worker/protocol.hpp"

namespace gnsdk::pool {

struct Config {
  std::filesystem::path worker;
  std::filesystem::path sleigh_home;
  std::filesystem::path tmpdir;
  // Test and embedding hook for worker-specific flags. Production callers
  // normally leave this empty; values are passed as distinct argv elements.
  std::vector<std::string> worker_args;
  std::size_t workers = 1;
  std::size_t max_queue = 64;
  std::size_t max_queue_bytes = 64u * 1024 * 1024;
  std::chrono::milliseconds cancel_grace{500};
  std::chrono::milliseconds term_grace{1000};
  std::uint64_t rlimit_as = 0;
  std::uint64_t rlimit_cpu = 0;
};

class Supervisor {
 public:
  explicit Supervisor(Config config);
  ~Supervisor();
  Supervisor(const Supervisor&) = delete;
  Supervisor& operator=(const Supervisor&) = delete;
  Supervisor(Supervisor&&) noexcept;
  Supervisor& operator=(Supervisor&&) noexcept;

  // Starts exactly ``workers`` child processes.  Failure leaves no child alive.
  void start();
  [[nodiscard]] gnsdk::proto::Message request(
      gnsdk::proto::Kind kind, std::string_view json, std::uint64_t request_id,
      std::chrono::milliseconds timeout);
  // Escalates SIGUSR1 -> SIGTERM -> SIGKILL and reaps every child.
  void stop() noexcept;
  [[nodiscard]] std::size_t live_workers() const noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace gnsdk::pool
