#include <chrono>
#include <cerrno>
#include <fstream>
#include <string>
#include <string_view>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include "gnsdk/pool.hpp"
#include "wtest.hpp"

namespace {

std::string own_cgroup_path() {
  std::ifstream input("/proc/self/cgroup");
  std::string line;
  while (std::getline(input, line)) {
    constexpr std::string_view marker = "0::";
    if (!std::string_view(line).starts_with(marker)) continue;
    std::string_view relative(line);
    relative.remove_prefix(marker.size());
    while (!relative.empty() && relative.front() == '/') relative.remove_prefix(1);
    std::string path = "/sys/fs/cgroup";
    if (!relative.empty()) {
      path.push_back('/');
      path.append(relative);
    }
    return path;
  }
  return {};
}

bool write_text_file(const std::string& path, std::string_view text) {
  const int fd = ::open(path.c_str(), O_WRONLY | O_CLOEXEC);
  if (fd < 0) return false;
  const char* p = text.data();
  std::size_t n = text.size();
  while (n > 0) {
    const ssize_t wrote = ::write(fd, p, n);
    if (wrote < 0) {
      if (errno == EINTR) continue;
      (void)::close(fd);
      return false;
    }
    p += wrote;
    n -= static_cast<std::size_t>(wrote);
  }
  return ::close(fd) == 0;
}

bool hard_cap_capable(const std::string& cgroup) {
  if (cgroup.empty() || ::access((cgroup + "/cgroup.subtree_control").c_str(), W_OK) != 0) return false;
  (void)write_text_file(cgroup + "/cgroup.subtree_control", "+memory\n");
  const std::string probe = cgroup + "/gnsdk-cgroup-probe-" + std::to_string(::getpid());
  if (::mkdir(probe.c_str(), 0700) != 0) return false;
  const bool capable = ::access((probe + "/memory.max").c_str(), W_OK) == 0;
  (void)::rmdir(probe.c_str());
  return capable;
}

}  // namespace

int main() {
  const std::string cgroup = own_cgroup_path();
  const bool delegated = hard_cap_capable(cgroup);

  gnsdk::pool::Config config;
  config.worker = GNSDK_FAKE_WORKER_PATH;
  config.sleigh_home = "/nonexistent";
  config.cgroup_memory_max = 128ull << 20;
  config.cancel_grace = std::chrono::milliseconds(20);
  config.term_grace = std::chrono::milliseconds(20);

  gnsdk::pool::Supervisor pool(std::move(config));
  pool.start();
  REQUIRE(pool.live_workers() == 1);
  REQUIRE(pool.hard_memory_cap() == delegated);
  pool.stop();
  REQUIRE(pool.live_workers() == 0);
  return wtest::exit_code();
}
