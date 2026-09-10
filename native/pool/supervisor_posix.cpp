#include "gnsdk/pool.hpp"

#include <cerrno>
#include <csignal>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <utility>

#include <fcntl.h>
#include <poll.h>
#include <spawn.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;

namespace gnsdk::pool {
namespace proto = gnsdk::proto;
namespace {
constexpr std::size_t kStderrTailBytes = 8192;

int open_pidfd(pid_t pid) noexcept {
#ifdef SYS_pidfd_open
  return static_cast<int>(::syscall(SYS_pidfd_open, pid, 0));
#else
  (void)pid; return -1;
#endif
}
void close_fd(int& fd) noexcept { if (fd >= 0) { (void)::close(fd); fd = -1; } }
bool reaped(pid_t pid, std::chrono::milliseconds grace) noexcept {
  const auto end = std::chrono::steady_clock::now() + grace; int status = 0;
  do {
    const pid_t result = ::waitpid(pid, &status, WNOHANG);
    if (result == pid || (result < 0 && errno == ECHILD)) return true;
    if (result < 0 && errno != EINTR) return false;
    timespec nap{0, 5'000'000}; (void)::nanosleep(&nap, nullptr);
  } while (std::chrono::steady_clock::now() < end);
  return false;
}

void validate_tmpdir(const std::filesystem::path& tmpdir) {
  if (tmpdir.empty()) return;
  std::error_code ec;
  std::filesystem::create_directories(tmpdir, ec);
  if (ec) throw std::runtime_error("create pool tmpdir: " + ec.message());
  if (!std::filesystem::is_directory(tmpdir, ec) || ec) {
    throw std::runtime_error("pool tmpdir is not a directory");
  }
  const auto probe = tmpdir / (".gnsdk-pool-probe-" + std::to_string(::getpid()));
  {
    std::ofstream out(probe, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("write pool tmpdir probe");
    out << "gnsdk\n";
    out.flush();
    if (!out) throw std::runtime_error("flush pool tmpdir probe");
  }
  std::filesystem::remove(probe, ec);
  if (ec) throw std::runtime_error("remove pool tmpdir probe: " + ec.message());
}
}  // namespace

struct Supervisor::Impl {
  struct Child {
    pid_t pid = -1; int pidfd = -1; int in = -1; int out = -1; int err = -1;
    proto::FrameReader reader{proto::kPreHandshakeMaxFrame}; bool busy = false;
  };
  static Child spawn_child(const Config& config);
  void drain_stderr(Child& child) noexcept;
  explicit Impl(Config value) : config(std::move(value)) {}
  Config config; std::vector<Child> children; std::size_t next = 0; std::string stderr_tail;
};

Supervisor::Impl::Child Supervisor::Impl::spawn_child(const Config& config) {
  int to[2] = {-1, -1}; int from[2] = {-1, -1}; int errpipe[2] = {-1, -1};
  if (::pipe2(to, O_CLOEXEC) != 0 || ::pipe2(from, O_CLOEXEC) != 0 || ::pipe2(errpipe, O_CLOEXEC | O_NONBLOCK) != 0) {
    const std::string why = std::strerror(errno);
    close_fd(to[0]); close_fd(to[1]); close_fd(from[0]); close_fd(from[1]); close_fd(errpipe[0]); close_fd(errpipe[1]);
    throw std::runtime_error("pipe worker: " + why);
  }
  const std::string as = std::to_string(config.rlimit_as), cpu = std::to_string(config.rlimit_cpu);
  std::vector<char*> args{const_cast<char*>(config.worker.c_str()), const_cast<char*>("--sleigh-home"), const_cast<char*>(config.sleigh_home.c_str())};
  for (const std::string& extra : config.worker_args) args.push_back(const_cast<char*>(extra.c_str()));
  if (config.rlimit_as) { args.push_back(const_cast<char*>("--rlimit-as")); args.push_back(const_cast<char*>(as.c_str())); }
  if (config.rlimit_cpu) { args.push_back(const_cast<char*>("--rlimit-cpu")); args.push_back(const_cast<char*>(cpu.c_str())); }
  args.push_back(nullptr);
  posix_spawn_file_actions_t files; const int init = ::posix_spawn_file_actions_init(&files);
  if (init != 0) { close_fd(to[0]); close_fd(to[1]); close_fd(from[0]); close_fd(from[1]); close_fd(errpipe[0]); close_fd(errpipe[1]); throw std::runtime_error("spawn actions: " + std::string(std::strerror(init))); }
  (void)::posix_spawn_file_actions_adddup2(&files, to[0], STDIN_FILENO); (void)::posix_spawn_file_actions_adddup2(&files, from[1], STDOUT_FILENO);
  (void)::posix_spawn_file_actions_adddup2(&files, errpipe[1], STDERR_FILENO);
  (void)::posix_spawn_file_actions_addclose(&files, to[1]); (void)::posix_spawn_file_actions_addclose(&files, from[0]);
  (void)::posix_spawn_file_actions_addclose(&files, errpipe[0]);
  std::vector<std::string> env_storage;
  std::vector<char*> child_env;
  for (char** entry = environ; entry != nullptr && *entry != nullptr; ++entry) {
    if (std::string_view(*entry).starts_with("GNSDK_EXPECTED_PPID=")) continue;
    child_env.push_back(*entry);
  }
  env_storage.push_back("GNSDK_EXPECTED_PPID=" + std::to_string(::getpid()));
  child_env.push_back(env_storage.back().data());
  child_env.push_back(nullptr);
  pid_t pid = -1; const int rc = ::posix_spawn(&pid, config.worker.c_str(), &files, nullptr, args.data(), child_env.data());
  (void)::posix_spawn_file_actions_destroy(&files); close_fd(to[0]); close_fd(from[1]); close_fd(errpipe[1]);
  if (rc != 0) { close_fd(to[1]); close_fd(from[0]); close_fd(errpipe[0]); throw std::runtime_error("spawn gnsdk-worker: " + std::string(std::strerror(rc))); }
  Supervisor::Impl::Child child; child.pid = pid; child.pidfd = open_pidfd(pid); child.in = to[1]; child.out = from[0]; child.err = errpipe[0];
  const auto cleanup = [&child]() noexcept {
    if (child.pid > 0) {
      (void)::kill(child.pid, SIGKILL);
      (void)reaped(child.pid, std::chrono::milliseconds(100));
    }
    close_fd(child.in); close_fd(child.out); close_fd(child.err); close_fd(child.pidfd); child.pid = -1;
  };
  proto::HelloInfo local; local.capabilities = {"pool"}; local.engine_source = "gnsdk-pool"; proto::FrameWriter writer(child.in);
  if (!writer.write_json(proto::Kind::Hello, 0, proto::make_hello(local))) { cleanup(); throw std::runtime_error("write worker HELLO"); }
  proto::Frame frame;
  const auto startup_grace =
      config.startup_grace.count() > 0 ? config.startup_grace : std::chrono::milliseconds(1);
  const auto deadline = std::chrono::steady_clock::now() + startup_grace;
  for (;;) {
    if (child.reader.next(frame)) break;
    const auto now = std::chrono::steady_clock::now();
    if (now >= deadline) { cleanup(); throw std::runtime_error("worker HELLO_ACK failed"); }
    const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - now).count();
    pollfd pfd{child.out, POLLIN, 0};
    if (::poll(&pfd, 1, static_cast<int>(left > 0 ? left : 1)) <= 0 ||
        child.reader.read(child.out) != proto::ReadStatus::Progress) {
      cleanup();
      throw std::runtime_error("worker HELLO_ACK failed");
    }
  }
  if (frame.header.kind != proto::to_u16(proto::Kind::HelloAck)) { cleanup(); throw std::runtime_error("worker HELLO_ACK failed"); }
  proto::HelloInfo remote; if (!proto::parse_hello(frame.payload_view(), remote)) { cleanup(); throw std::runtime_error("invalid worker HELLO_ACK"); }
  const auto negotiated = proto::negotiate(local, remote); if (!negotiated.ok) { cleanup(); throw std::runtime_error("worker negotiation: " + negotiated.error); }
  child.reader.set_max_payload(negotiated.max_frame);
  return child;
}

void Supervisor::Impl::drain_stderr(Child& child) noexcept {
  if (child.err < 0) return;
  char buf[4096];
  for (;;) {
    const ssize_t n = ::read(child.err, buf, sizeof buf);
    if (n > 0) {
      stderr_tail.append(buf, static_cast<std::size_t>(n));
      if (stderr_tail.size() > kStderrTailBytes) {
        stderr_tail.erase(0, stderr_tail.size() - kStderrTailBytes);
      }
      continue;
    }
    if (n < 0 && errno == EINTR) continue;
    break;
  }
}

Supervisor::Supervisor(Config config) : impl_(std::make_unique<Impl>(std::move(config))) {
  if (impl_->config.worker.empty() || impl_->config.sleigh_home.empty() || impl_->config.workers == 0)
    throw std::invalid_argument("worker, sleigh_home, and workers are required");
}
Supervisor::~Supervisor() { stop(); }
Supervisor::Supervisor(Supervisor&&) noexcept = default;
Supervisor& Supervisor::operator=(Supervisor&&) noexcept = default;

void Supervisor::start() {
  if (!impl_->children.empty()) throw std::logic_error("supervisor already started");
  std::signal(SIGPIPE, SIG_IGN);
  validate_tmpdir(impl_->config.tmpdir);
  try { for (std::size_t count = 0; count < impl_->config.workers; ++count) {
    impl_->children.push_back(Impl::spawn_child(impl_->config));
  }} catch (...) { stop(); throw; }
}

proto::Message Supervisor::request(proto::Kind kind, std::string_view json, std::uint64_t id, std::chrono::milliseconds timeout) {
  if (impl_->children.empty()) throw std::logic_error("supervisor is not started");
  if (id == 0 || proto::is_connection_kind(proto::to_u16(kind))) throw std::invalid_argument("request must have a nonzero request id");
  if (json.size() > impl_->config.max_queue_bytes) throw std::runtime_error("pool request exceeds max_queue_bytes");
  const std::size_t slot = impl_->next++ % impl_->children.size();
  Impl::Child& child = impl_->children[slot];
  const auto retire = [&child, this]() noexcept {
    this->impl_->drain_stderr(child);
    if (child.pid > 0) {
      (void)::kill(child.pid, SIGUSR1);
      if (!reaped(child.pid, impl_->config.cancel_grace)) {
        (void)::kill(child.pid, SIGTERM);
        if (!reaped(child.pid, impl_->config.term_grace)) {
          (void)::kill(child.pid, SIGKILL);
          (void)reaped(child.pid, std::chrono::milliseconds(100));
        }
      }
    }
    this->impl_->drain_stderr(child);
    close_fd(child.in); close_fd(child.out); close_fd(child.err); close_fd(child.pidfd); child.pid = -1;
  };
  for (int attempt = 0; attempt < 2; ++attempt) {
    if (child.busy) throw std::runtime_error("no idle worker");
    if (child.pid <= 0) child = Impl::spawn_child(impl_->config);
    child.busy = true;
    struct Clear { bool& value; ~Clear() { value = false; } } clear{child.busy};
    proto::FrameWriter writer(child.in);
    if (!writer.write_json(kind, id, json)) {
      retire();
      if (attempt == 0) continue;
      throw std::runtime_error("write worker request failed");
    }
    proto::MessageAssembler assembler(proto::kDefaultMaxImageBytes + proto::kDefaultMaxFrame);
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    bool retry = false;
    for (;;) {
      proto::Frame frame; while (child.reader.next(frame)) {
        if (frame.header.request_id != id) { retire(); throw std::runtime_error("worker replied with wrong request id"); }
        const auto state = assembler.push(std::move(frame)); if (state == proto::AssembleStatus::Complete) return assembler.take();
        if (state != proto::AssembleStatus::NeedMore) { retire(); throw std::runtime_error("invalid worker frame sequence"); }
      }
      const auto now = std::chrono::steady_clock::now();
      if (now >= deadline) { retire(); throw std::runtime_error("worker request timed out"); }
      const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - now).count(); pollfd pfd{child.out, POLLIN, 0};
      const int polled = ::poll(&pfd, 1, static_cast<int>(left > 0 ? left : 1));
      impl_->drain_stderr(child);
      if (polled < 0) { if (errno == EINTR) continue; retire(); throw std::runtime_error("poll worker output failed"); }
      // A timeout is not readability. Calling FrameReader::read on its blocking
      // pipe here would defeat the supervisor's own deadline and leave a hung
      // worker alive forever.
      if (polled == 0) continue;
      const auto state = child.reader.read(child.out);
      impl_->drain_stderr(child);
      if (state == proto::ReadStatus::Eof || state == proto::ReadStatus::Fatal || state == proto::ReadStatus::Error) {
        retire();
        retry = attempt == 0;
        break;
      }
    }
    if (!retry) break;
  }
  throw std::runtime_error("worker died or emitted a fatal frame");
}

void Supervisor::stop() noexcept { if (!impl_) return; for (auto& child : impl_->children) { impl_->drain_stderr(child); if (child.pid > 0) { (void)::kill(child.pid, SIGUSR1); if (!reaped(child.pid, impl_->config.cancel_grace)) { (void)::kill(child.pid, SIGTERM); if (!reaped(child.pid, impl_->config.term_grace)) { (void)::kill(child.pid, SIGKILL); (void)reaped(child.pid, std::chrono::milliseconds(100)); } } } impl_->drain_stderr(child); close_fd(child.in); close_fd(child.out); close_fd(child.err); close_fd(child.pidfd); } impl_->children.clear(); }
std::size_t Supervisor::live_workers() const noexcept { std::size_t live = 0; for (const auto& child : impl_->children) if (child.pid > 0 && ::kill(child.pid, 0) == 0) ++live; return live; }
std::string Supervisor::stderr_tail() const { return impl_ ? impl_->stderr_tail : std::string{}; }
}  // namespace gnsdk::pool
