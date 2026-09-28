// spawn_util.hpp - spawn fake-worker over pipes and talk protocol 1.0 to it.
// Shared by fake_worker_smoke.cpp and fake_worker_misbehave_matrix.cpp.
#pragma once

#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

#include <fcntl.h>
#include <poll.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#include "worker/json_min.hpp"
#include "worker/protocol.hpp"

namespace wtest {

namespace proto = gnsdk::proto;
namespace json = gnsdk::json;

inline const char* fake_worker_path() {
#ifdef GNSDK_FAKE_WORKER_PATH
  if (const char* e = std::getenv("GNSDK_FAKE_WORKER")) return e;
  return GNSDK_FAKE_WORKER_PATH;
#else
  const char* e = std::getenv("GNSDK_FAKE_WORKER");
  if (!e) {
    std::fprintf(stderr, "set GNSDK_FAKE_WORKER to the fake-worker binary\n");
    std::exit(2);
  }
  return e;
#endif
}

inline long now_ms() {
  return static_cast<long>(std::chrono::duration_cast<std::chrono::milliseconds>(
                               std::chrono::steady_clock::now().time_since_epoch())
                               .count());
}

inline void sleep_ms(long ms) {
  timespec ts{ms / 1000, (ms % 1000) * 1000000L};
  while (nanosleep(&ts, &ts) < 0 && errno == EINTR) {
  }
}

struct SpawnOpts {
  std::string mode = "none";
  bool set_expected_ppid = true;   // GNSDK_EXPECTED_PPID = our pid
  long expected_ppid_override = 0; // when != 0, use this value instead
  rlim_t rlimit_as = 0;            // 0 = unchanged
  std::vector<std::pair<std::string, std::string>> env;
  bool capture_stderr = true;      // false = inherit ours
};

struct Spawned {
  pid_t pid = -1;
  int in = -1;   // we write requests here (worker stdin)
  int out = -1;  // we read replies here (worker stdout)
  int err = -1;  // worker stderr, or -1
  bool reaped = false;
  int status = 0;

  Spawned() = default;
  Spawned(const Spawned&) = delete;
  Spawned& operator=(const Spawned&) = delete;
  Spawned(Spawned&& o) noexcept { *this = std::move(o); }
  Spawned& operator=(Spawned&& o) noexcept {
    if (this != &o) {
      close_all();
      pid = o.pid; in = o.in; out = o.out; err = o.err; reaped = o.reaped; status = o.status;
      o.pid = -1; o.in = o.out = o.err = -1;
    }
    return *this;
  }
  ~Spawned() {
    close_all();
    if (pid > 0 && !reaped) {
      ::kill(pid, SIGKILL);
      ::waitpid(pid, &status, 0);
      reaped = true;
    }
  }

  void close_in() { if (in >= 0) { ::close(in); in = -1; } }
  void close_all() {
    close_in();
    if (out >= 0) { ::close(out); out = -1; }
    if (err >= 0) { ::close(err); err = -1; }
  }

  // Polls waitpid until the child exits or timeout_ms elapses.
  bool wait_exit(long timeout_ms) {
    if (reaped) return true;
    const long deadline = now_ms() + timeout_ms;
    for (;;) {
      const pid_t r = ::waitpid(pid, &status, WNOHANG);
      if (r == pid) { reaped = true; return true; }
      if (r < 0 && errno != EINTR) { reaped = true; return true; }
      if (now_ms() >= deadline) return false;
      sleep_ms(5);
    }
  }
  bool alive() { return !wait_exit(0); }
  int exit_code() const { return WIFEXITED(status) ? WEXITSTATUS(status) : -1; }
  int term_signal() const { return WIFSIGNALED(status) ? WTERMSIG(status) : 0; }
  bool signal(int sig) const { return ::kill(pid, sig) == 0; }
};

inline Spawned spawn_fake_worker(const SpawnOpts& o) {
  int to_child[2], from_child[2], err_pipe[2] = {-1, -1};
  if (::pipe2(to_child, O_CLOEXEC) != 0 || ::pipe2(from_child, O_CLOEXEC) != 0) {
    std::perror("pipe2");
    std::exit(2);
  }
  if (o.capture_stderr && ::pipe2(err_pipe, O_CLOEXEC) != 0) {
    std::perror("pipe2");
    std::exit(2);
  }
  const char* path = fake_worker_path();
  const pid_t parent = ::getpid();
  const pid_t pid = ::fork();
  if (pid < 0) {
    std::perror("fork");
    std::exit(2);
  }
  if (pid == 0) {
    ::dup2(to_child[0], 0);
    ::dup2(from_child[1], 1);
    if (o.capture_stderr) ::dup2(err_pipe[1], 2);
    if (o.rlimit_as != 0) {
      rlimit rl{o.rlimit_as, o.rlimit_as};
      ::setrlimit(RLIMIT_AS, &rl);
    }
    if (o.set_expected_ppid) {
      const long v = o.expected_ppid_override != 0 ? o.expected_ppid_override : static_cast<long>(parent);
      ::setenv("GNSDK_EXPECTED_PPID", std::to_string(v).c_str(), 1);
    } else {
      ::unsetenv("GNSDK_EXPECTED_PPID");
    }
    for (const auto& kv : o.env) ::setenv(kv.first.c_str(), kv.second.c_str(), 1);
    ::execl(path, path, "--misbehave", o.mode.c_str(), "--sleigh-home", "/nonexistent", (char*)nullptr);
    std::fprintf(stderr, "execl(%s) failed: %s\n", path, std::strerror(errno));
    _exit(127);
  }
  ::close(to_child[0]);
  ::close(from_child[1]);
  if (o.capture_stderr) ::close(err_pipe[1]);
  Spawned s;
  s.pid = pid;
  s.in = to_child[1];
  s.out = from_child[0];
  s.err = o.capture_stderr ? err_pipe[0] : -1;
  return s;
}

// ---- protocol helpers -------------------------------------------------------

inline bool send_json(const Spawned& s, proto::Kind k, std::uint64_t id, std::string_view body,
                      std::uint32_t flags = 0) {
  proto::FrameWriter w(s.in);
  return w.write_json(k, id, body, flags);
}
inline bool send_raw(const Spawned& s, proto::Kind k, std::uint64_t id, const void* p, std::size_t n,
                     std::uint32_t flags = 0) {
  proto::FrameWriter w(s.in);
  return w.write_raw(k, id, p, n, flags);
}
inline bool send_empty(const Spawned& s, proto::Kind k, std::uint64_t id = 0) {
  proto::FrameWriter w(s.in);
  return w.write_empty(k, id);
}
inline bool send_bytes(const Spawned& s, const void* p, std::size_t n) {
  const auto* b = static_cast<const std::uint8_t*>(p);
  while (n > 0) {
    const ssize_t w = ::write(s.in, b, n);
    if (w < 0) {
      if (errno == EINTR) continue;
      return false;
    }
    b += w;
    n -= static_cast<std::size_t>(w);
  }
  return true;
}

enum class Wait { Frame, Timeout, Eof, Fatal, Error };

inline const char* wait_name(Wait w) {
  switch (w) {
    case Wait::Frame: return "frame";
    case Wait::Timeout: return "timeout";
    case Wait::Eof: return "eof";
    case Wait::Fatal: return "fatal";
    case Wait::Error: return "error";
  }
  return "?";
}

// Reads from s.out into `r` until a frame is available or timeout_ms elapses.
inline Wait wait_frame(proto::FrameReader& r, const Spawned& s, long timeout_ms, proto::Frame& out) {
  const long deadline = now_ms() + timeout_ms;
  for (;;) {
    if (r.next(out)) return Wait::Frame;
    if (r.fatal()) return r.fatal_reason() == proto::FatalReason::ReadError ? Wait::Error : Wait::Fatal;
    if (r.eof()) return Wait::Eof;
    const long left = deadline - now_ms();
    if (left <= 0) return Wait::Timeout;
    pollfd pfd{s.out, POLLIN, 0};
    const int pr = ::poll(&pfd, 1, static_cast<int>(left));
    if (pr < 0) {
      if (errno == EINTR) continue;
      return Wait::Error;
    }
    if (pr == 0) return Wait::Timeout;
    const proto::ReadStatus st = r.read(s.out);
    if (st == proto::ReadStatus::Fatal) return Wait::Fatal;
    if (st == proto::ReadStatus::Error) return Wait::Error;
    // Progress / Eof loop back: next() or eof() decide.
  }
}

// Full handshake; returns true on HELLO_ACK and fills `remote`.
inline bool do_hello(const Spawned& s, proto::FrameReader& r, proto::HelloInfo& remote, long timeout_ms = 5000) {
  proto::HelloInfo local;
  local.capabilities = {"test"};
  local.engine_source = "test-harness";
  if (!send_json(s, proto::Kind::Hello, 0, proto::make_hello(local))) return false;
  proto::Frame f;
  if (wait_frame(r, s, timeout_ms, f) != Wait::Frame) return false;
  if (f.header.kind != proto::to_u16(proto::Kind::HelloAck)) return false;
  if (!proto::parse_hello(f.payload_view(), remote)) return false;
  const proto::Negotiated n = proto::negotiate(local, remote);
  if (!n.ok) return false;
  r.set_max_payload(n.max_frame);
  return true;
}

inline std::string decompile_request(std::int64_t deadline_ms = 1000) {
  json::Value v = json::Value::object();
  v.set("addr", "0x401000");
  v.set("name", nullptr);
  v.set("tokens", false);
  v.set("deadline_ms", static_cast<long long>(deadline_ms));
  v.set("printer", "c");
  return v.dump();
}

// Drains an fd until EOF or `stop` is set; returns the byte count.
inline std::size_t drain_bytes(int fd, long max_ms) {
  const long deadline = now_ms() + max_ms;
  std::vector<char> buf(256 * 1024);
  std::size_t total = 0;
  for (;;) {
    const long left = deadline - now_ms();
    if (left <= 0) return total;
    pollfd pfd{fd, POLLIN, 0};
    const int pr = ::poll(&pfd, 1, static_cast<int>(left));
    if (pr <= 0) { if (pr < 0 && errno == EINTR) continue; return total; }
    const ssize_t n = ::read(fd, buf.data(), buf.size());
    if (n <= 0) { if (n < 0 && errno == EINTR) continue; return total; }
    total += static_cast<std::size_t>(n);
  }
}

}  // namespace wtest
