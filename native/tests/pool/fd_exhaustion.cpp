#include <cerrno>
#include <chrono>
#include <stdexcept>
#include <vector>

#include <fcntl.h>
#include <sys/resource.h>
#include <unistd.h>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace {

struct Fd {
  int value = -1;
  explicit Fd(int fd) : value(fd) {}
  Fd(const Fd&) = delete;
  Fd& operator=(const Fd&) = delete;
  Fd(Fd&& other) noexcept : value(other.value) { other.value = -1; }
  Fd& operator=(Fd&& other) noexcept {
    if (this != &other) {
      if (value >= 0) (void)::close(value);
      value = other.value;
      other.value = -1;
    }
    return *this;
  }
  ~Fd() {
    if (value >= 0) (void)::close(value);
  }
};

}  // namespace

int main() {
  rlimit original{};
  REQUIRE(::getrlimit(RLIMIT_NOFILE, &original) == 0);
  const rlim_t cap = original.rlim_max < 32 ? original.rlim_max : 32;
  const rlimit limited{cap, cap};
  REQUIRE(::setrlimit(RLIMIT_NOFILE, &limited) == 0);

  std::vector<Fd> held;
  while (true) {
    const int fd = ::open("/dev/null", O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
      REQUIRE(errno == EMFILE || errno == ENFILE);
      break;
    }
    held.emplace_back(fd);
  }

  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.startup_grace = std::chrono::milliseconds(100);
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  bool failed = false;
  try {
    pool.start();
  } catch (const std::runtime_error&) {
    failed = true;
  }
  REQUIRE(failed);
  REQUIRE(pool.live_workers() == 0);
  pool.stop();
  return wtest::exit_code();
}
