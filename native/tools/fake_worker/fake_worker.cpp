// fake_worker.cpp - a stand-in for gnsdk-worker that speaks protocol 1.0 on
// stdin/stdout and can be told to misbehave. It exists so the pool supervisor
// (WP6) and its fault matrix can be tested without SLEIGH or the decompiler.
//
//   fake-worker [--misbehave MODE] [--sleigh-home DIR] [--max-frame N] ...
//
// Unknown "--flag value" pairs are accepted and ignored so the supervisor can
// pass the real worker's command line unchanged.
//
// Modes:
//   none             HELLO->HELLO_ACK, PING->PONG, DECOMPILE->RESULT ok,
//                    OPEN_*/CLOSE_SESSION->RESULT ok, LIFT->empty arrays,
//                    DISASM->empty list, CANCEL->ERROR cancelled, unknown
//                    kind->ERROR unsupported_kind, BYE or EOF->exit 0.
//   hang             handshake, then never reply to a request. SIGTERM exits 0.
//   hang-ignore-term same, plus SIGTERM ignored (only SIGKILL works).
//   die-midframe     on the first request write 12 header bytes, _exit(9).
//   oversize         on the first request send a header with payload_len
//                    0xFFFFFFFF, then keep reading.
//   bad-magic        on the first request send a frame whose magic is "XXXX".
//   garbage-stderr   behave, while a thread writes ~50 MB/s to stderr.
//   slow-reply       behave, but every reply goes out 1 byte per 10 ms.
//   eat-memory       on the first request mmap+touch 64 MiB chunks until it
//                    fails, then _exit(4). Without RLIMIT_AS the run stops
//                    at GNSDK_FAKE_EAT_MAX_MIB (default 1024) to spare the host.
//   exit-4           reply to the first request, then _exit(4).
//   reply-wrong-id   replies carry request_id + 1000.
//   honor-cancel     requests block until SIGUSR1 (-> ERROR cancelled) or
//                    deadline_ms (-> RESULT ok). PING/BYE are immediate.
//   pdeathsig        prctl(PR_SET_PDEATHSIG, SIGKILL), then hang forever
//                    (no handshake).
//
// Env: GNSDK_EXPECTED_PPID - if set and != getppid(), _exit(7) before any I/O.
//
// Exit codes mirror the real worker where they overlap: 0 clean, 2 protocol
// (bad magic / oversize / truncated input), 6 stdout write failure, 7 wrong
// parent, plus the mode-specific 4 and 9 above.
//
// stderr carries diagnostics only. stdout carries protocol bytes only.

#include <atomic>
#include <cerrno>
#include <cstdarg>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <poll.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

#include "worker/json_min.hpp"
#include "worker/protocol.hpp"

namespace proto = gnsdk::proto;
namespace json = gnsdk::json;

namespace {

enum class Mode {
  None,
  Hang,
  HangIgnoreTerm,
  DieMidframe,
  Oversize,
  BadMagic,
  GarbageStderr,
  SlowReply,
  EatMemory,
  Exit4,
  ReplyWrongId,
  HonorCancel,
  PDeathSig,
};

struct ModeName {
  const char* name;
  Mode mode;
};
constexpr ModeName kModes[] = {
    {"none", Mode::None},
    {"hang", Mode::Hang},
    {"hang-ignore-term", Mode::HangIgnoreTerm},
    {"die-midframe", Mode::DieMidframe},
    {"oversize", Mode::Oversize},
    {"bad-magic", Mode::BadMagic},
    {"garbage-stderr", Mode::GarbageStderr},
    {"slow-reply", Mode::SlowReply},
    {"eat-memory", Mode::EatMemory},
    {"exit-4", Mode::Exit4},
    {"reply-wrong-id", Mode::ReplyWrongId},
    {"honor-cancel", Mode::HonorCancel},
    {"pdeathsig", Mode::PDeathSig},
};

volatile std::sig_atomic_t g_cancel_flag = 0;
volatile std::sig_atomic_t g_term_flag = 0;

void on_sigusr1(int) { g_cancel_flag = 1; }
void on_sigterm(int) {
  g_term_flag = 1;
  // The real worker cancels, finishes its reply and exits 0. The fake has no
  // reply worth finishing, so it leaves right away.
  _exit(0);
}

void diag(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
void diag(const char* fmt, ...) {
  char buf[512];
  va_list ap;
  va_start(ap, fmt);
  const int n = std::vsnprintf(buf, sizeof buf, fmt, ap);
  va_end(ap);
  if (n <= 0) return;
  std::string line = "fake-worker[" + std::to_string(getpid()) + "]: ";
  line.append(buf, static_cast<std::size_t>(n < static_cast<int>(sizeof buf) ? n : sizeof buf - 1));
  line.push_back('\n');
  // Best effort; stderr may be closed or full.
  ssize_t ignored = ::write(2, line.data(), line.size());
  (void)ignored;
}

void sleep_ms(long ms) {
  timespec ts{ms / 1000, (ms % 1000) * 1000000L};
  while (nanosleep(&ts, &ts) < 0 && errno == EINTR) {
  }
}

[[noreturn]] void hang_forever() {
  for (;;) pause();
}

// Blocking write of every byte, EINTR/EAGAIN tolerant. False on failure.
bool write_all(int fd, const std::uint8_t* p, std::size_t n) {
  while (n > 0) {
    const ssize_t w = ::write(fd, p, n);
    if (w < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == EWOULDBLOCK) {
        pollfd pfd{fd, POLLOUT, 0};
        ::poll(&pfd, 1, -1);
        continue;
      }
      return false;
    }
    p += w;
    n -= static_cast<std::size_t>(w);
  }
  return true;
}

class Replier {
 public:
  Replier(Mode mode) : mode_(mode), writer_(1) {}

  bool send_json(proto::Kind kind, std::uint64_t id, std::string_view body, std::uint32_t flags = 0) {
    proto::FrameHeader h;
    h.kind = proto::to_u16(kind);
    h.flags = flags & ~proto::kFlagRawPayload;
    h.request_id = fix_id(id);
    return send(h, body.data(), body.size());
  }
  bool send_raw(proto::Kind kind, std::uint64_t id, const void* data, std::size_t len, std::uint32_t flags = 0) {
    proto::FrameHeader h;
    h.kind = proto::to_u16(kind);
    h.flags = flags | proto::kFlagRawPayload;
    h.request_id = fix_id(id);
    return send(h, data, len);
  }
  bool send_empty(proto::Kind kind, std::uint64_t id) {
    proto::FrameHeader h;
    h.kind = proto::to_u16(kind);
    h.request_id = fix_id(id);
    return send(h, nullptr, 0);
  }

 private:
  std::uint64_t fix_id(std::uint64_t id) const {
    if (mode_ == Mode::ReplyWrongId && id != proto::kConnectionRequestId) return id + 1000;
    return id;
  }

  bool send(const proto::FrameHeader& hin, const void* payload, std::size_t len) {
    if (mode_ != Mode::SlowReply) {
      if (!writer_.write_frame(hin, payload, len)) {
        diag("stdout write failed: %s", std::strerror(writer_.last_errno()));
        _exit(6);
      }
      return true;
    }
    proto::FrameHeader h = hin;
    h.payload_len = static_cast<std::uint32_t>(len);
    std::uint8_t hdr[proto::kHeaderSize];
    proto::encode_header(h, hdr);
    std::vector<std::uint8_t> bytes(hdr, hdr + proto::kHeaderSize);
    const auto* p = static_cast<const std::uint8_t*>(payload);
    bytes.insert(bytes.end(), p, p + len);
    for (const std::uint8_t b : bytes) {
      if (!write_all(1, &b, 1)) {
        diag("stdout write failed: %s", std::strerror(errno));
        _exit(6);
      }
      sleep_ms(10);
    }
    return true;
  }

  Mode mode_;
  proto::FrameWriter writer_;
};

void stderr_flood_thread() {
  // ~50 MB/s: 512 KiB every 10 ms. If nobody drains the pipe this thread
  // blocks; the protocol thread must keep serving regardless.
  std::vector<char> chunk(512 * 1024, 'x');
  for (std::size_t i = 0; i < chunk.size(); i += 64) chunk[i] = '\n';
  for (;;) {
    const ssize_t n = ::write(2, chunk.data(), chunk.size());
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
      sleep_ms(10);
      continue;
    }
    if (n < 0) return;
    sleep_ms(10);
  }
}

[[noreturn]] void eat_memory() {
  constexpr std::size_t kChunk = 64u * 1024u * 1024u;
  std::size_t cap_mib = 1024;
  if (const char* e = std::getenv("GNSDK_FAKE_EAT_MAX_MIB")) cap_mib = std::strtoull(e, nullptr, 10);
  rlimit rl{};
  const bool bounded = getrlimit(RLIMIT_AS, &rl) == 0 && rl.rlim_cur != RLIM_INFINITY;
  std::size_t eaten = 0;
  for (;;) {
    if (!bounded && eaten >= cap_mib * 1024u * 1024u) {
      diag("eat-memory: no RLIMIT_AS; stopping at %zu MiB", eaten >> 20);
      _exit(4);
    }
    void* p = ::mmap(nullptr, kChunk, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (p == MAP_FAILED) {
      diag("eat-memory: mmap failed after %zu MiB: %s", eaten >> 20, std::strerror(errno));
      _exit(4);
    }
    // Touch every page so the memory is really committed.
    auto* bytes = static_cast<volatile std::uint8_t*>(p);
    for (std::size_t off = 0; off < kChunk; off += 4096) bytes[off] = 1;
    eaten += kChunk;
  }
}

// Sends a bogus header straight to fd 1 (bypasses FrameWriter on purpose).
void send_bogus_header(bool bad_magic, std::uint64_t id) {
  proto::FrameHeader h;
  h.kind = proto::to_u16(proto::Kind::Result);
  h.request_id = id;
  h.payload_len = bad_magic ? 2u : 0xFFFFFFFFu;
  std::uint8_t hdr[proto::kHeaderSize];
  proto::encode_header(h, hdr);
  if (bad_magic) std::memcpy(hdr, "XXXX", 4);
  if (!write_all(1, hdr, sizeof hdr)) _exit(6);
  if (bad_magic) {
    const std::uint8_t body[2] = {'{', '}'};
    if (!write_all(1, body, 2)) _exit(6);
  }
}

struct Worker {
  Mode mode;
  Replier out;
  proto::FrameReader reader{proto::kPreHandshakeMaxFrame};
  proto::MessageAssembler assembler{proto::kDefaultMaxImageBytes + proto::kDefaultMaxFrame};
  proto::HelloInfo local;
  bool handshaken = false;
  bool first_request_seen = false;

  explicit Worker(Mode m) : mode(m), out(m) {
    local.capabilities = {"decompile", "lift", "disasm", "open_raw", "open_snapshot", "fake"};
    local.engine_source = "fake-worker";
  }

  void handle_hello(const proto::Message& m) {
    proto::HelloInfo remote;
    std::string err;
    if (!proto::parse_hello(m.json(), remote, &err)) {
      out.send_json(proto::Kind::Error, 0, proto::make_error(proto::ErrorCode::Protocol, err));
      return;
    }
    const proto::Negotiated n = proto::negotiate(local, remote);
    if (!n.ok) {
      out.send_json(proto::Kind::Error, 0, proto::make_error(proto::ErrorCode::Protocol, n.error));
      diag("handshake failed: %s", n.error.c_str());
      _exit(2);
    }
    reader.set_max_payload(n.max_frame);
    assembler.set_max_total_bytes(static_cast<std::size_t>(n.max_image_bytes) + n.max_frame);
    handshaken = true;
    out.send_json(proto::Kind::HelloAck, 0, proto::make_hello(local));
  }

  // Waits for SIGUSR1 or the deadline; true if cancelled.
  bool wait_for_cancel(std::int64_t deadline_ms) {
    const auto start = std::chrono::steady_clock::now();
    for (;;) {
      if (g_cancel_flag) {
        g_cancel_flag = 0;
        return true;
      }
      if (deadline_ms > 0) {
        const auto el = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();
        if (el >= deadline_ms) return false;
      }
      sleep_ms(5);
    }
  }

  void first_request_hook(std::uint64_t id) {
    if (first_request_seen) return;
    first_request_seen = true;
    switch (mode) {
      case Mode::Hang:
      case Mode::HangIgnoreTerm:
        diag("hanging on request %llu", static_cast<unsigned long long>(id));
        hang_forever();
      case Mode::DieMidframe: {
        proto::FrameHeader h;
        h.kind = proto::to_u16(proto::Kind::Result);
        h.request_id = id;
        h.payload_len = 64;
        std::uint8_t hdr[proto::kHeaderSize];
        proto::encode_header(h, hdr);
        write_all(1, hdr, 12);
        _exit(9);
      }
      case Mode::Oversize:
        send_bogus_header(false, id);
        return;
      case Mode::BadMagic:
        send_bogus_header(true, id);
        return;
      case Mode::EatMemory:
        eat_memory();
      default:
        return;
    }
  }

  void reply_result(std::uint64_t id, std::string_view body) {
    out.send_json(proto::Kind::Result, id, body);
    if (mode == Mode::Exit4) {
      diag("exit-4 after replying to %llu", static_cast<unsigned long long>(id));
      _exit(4);
    }
  }

  std::int64_t deadline_of(const proto::Message& m) {
    json::Value v;
    if (!json::parse(m.json(), v) || !v.is_object()) return 0;
    std::int64_t d = 0;
    v.get_int("deadline_ms", d);
    return d;
  }

  // Returns false when the worker should exit (BYE).
  bool dispatch(proto::Message&& m) {
    const std::uint16_t k = m.kind;
    if (!handshaken && k != proto::to_u16(proto::Kind::Hello)) {
      out.send_json(proto::Kind::Error, m.request_id,
                    proto::make_error(proto::ErrorCode::Protocol, "HELLO required first"));
      return true;
    }
    switch (static_cast<proto::Kind>(k)) {
      case proto::Kind::Hello:
        handle_hello(m);
        return true;
      case proto::Kind::Ping:
        out.send_empty(proto::Kind::Pong, 0);
        return true;
      case proto::Kind::Bye:
        diag("BYE");
        return false;
      case proto::Kind::Cancel:
        // Only not-yet-started requests are cancelled by frame; the fake has
        // no queue, so every CANCEL refers to something already answered.
        out.send_json(proto::Kind::Error, m.request_id,
                      proto::make_error(proto::ErrorCode::Cancelled, "cancelled before start"));
        return true;
      case proto::Kind::OpenRaw:
      case proto::Kind::OpenSnapshot:
      case proto::Kind::CloseSession:
        first_request_hook(m.request_id);
        reply_result(m.request_id, R"({"status":"ok"})");
        return true;
      case proto::Kind::Disasm:
        first_request_hook(m.request_id);
        reply_result(m.request_id, R"({"instructions":[],"elapsed_ms":0})");
        return true;
      case proto::Kind::Lift: {
        first_request_hook(m.request_id);
        out.send_json(proto::Kind::Result, m.request_id,
                      R"({"num_ops":0,"num_varnodes":0,"num_instrs":0,"spaces":["ram","register","const","unique"]})",
                      proto::kFlagMore);
        out.send_raw(proto::Kind::Result, m.request_id, nullptr, 0);
        if (mode == Mode::Exit4) _exit(4);
        return true;
      }
      case proto::Kind::Decompile: {
        first_request_hook(m.request_id);
        if (mode == Mode::HonorCancel) {
          if (wait_for_cancel(deadline_of(m))) {
            out.send_json(proto::Kind::Error, m.request_id,
                          proto::make_error(proto::ErrorCode::Cancelled, "cancelled by SIGUSR1"));
            return true;
          }
        }
        reply_result(m.request_id,
                     R"({"status":"ok","c":"/* fake */","tokens":null,"warnings":[],"elapsed_ms":0})");
        return true;
      }
      default:
        out.send_json(proto::Kind::Error, m.request_id, proto::make_unsupported_kind(k));
        return true;
    }
  }

  int run() {
    for (;;) {
      proto::Frame f;
      while (reader.next(f)) {
        const proto::AssembleStatus st = assembler.push(std::move(f));
        if (st == proto::AssembleStatus::Complete) {
          if (!dispatch(assembler.take())) return 0;
        } else if (st != proto::AssembleStatus::NeedMore) {
          diag("message dropped: %s", proto::assemble_status_name(st));
          out.send_json(proto::Kind::Error, 0,
                        proto::make_error(proto::ErrorCode::Protocol, proto::assemble_status_name(st)));
        }
      }
      const proto::ReadStatus rs = reader.read(0);
      if (rs == proto::ReadStatus::Eof) {
        diag("stdin EOF");
        return 0;
      }
      if (rs == proto::ReadStatus::Fatal || rs == proto::ReadStatus::Error) {
        diag("fatal input: %s", proto::fatal_reason_name(reader.fatal_reason()));
        return 2;
      }
    }
  }
};

Mode parse_mode(const char* s) {
  for (const ModeName& m : kModes) {
    if (std::strcmp(m.name, s) == 0) return m.mode;
  }
  std::fprintf(stderr, "fake-worker: unknown --misbehave mode '%s'; known:", s);
  for (const ModeName& m : kModes) std::fprintf(stderr, " %s", m.name);
  std::fprintf(stderr, "\n");
  std::exit(64);
}

}  // namespace

int main(int argc, char** argv) {
  Mode mode = Mode::None;
  for (int i = 1; i < argc; ++i) {
    const std::string_view a = argv[i];
    if (a == "--misbehave" && i + 1 < argc) {
      mode = parse_mode(argv[++i]);
    } else if (a.rfind("--misbehave=", 0) == 0) {
      mode = parse_mode(argv[i] + 12);
    } else if (a == "--help" || a == "-h") {
      std::fprintf(stdout, "usage: fake-worker [--misbehave MODE] [other worker flags ignored]\n");
      return 0;
    } else if (a.rfind("--", 0) == 0 && a.find('=') == std::string_view::npos && i + 1 < argc) {
      ++i;  // "--flag value" pair meant for the real worker
    }
  }

  if (const char* e = std::getenv("GNSDK_EXPECTED_PPID")) {
    const long long want = std::strtoll(e, nullptr, 10);
    if (want != static_cast<long long>(getppid())) {
      diag("expected parent %lld, have %ld", want, static_cast<long>(getppid()));
      _exit(7);
    }
  }

  if (mode == Mode::PDeathSig) {
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0) {
      diag("prctl(PR_SET_PDEATHSIG) failed: %s", std::strerror(errno));
      _exit(5);
    }
    // The parent may have died between fork and prctl.
    if (const char* e = std::getenv("GNSDK_EXPECTED_PPID")) {
      if (std::strtoll(e, nullptr, 10) != static_cast<long long>(getppid())) _exit(7);
    }
    hang_forever();
  }

  std::signal(SIGPIPE, SIG_IGN);
  struct sigaction sa{};
  sa.sa_handler = on_sigusr1;
  sigemptyset(&sa.sa_mask);
  sa.sa_flags = 0;  // no SA_RESTART: blocking reads return EINTR, FrameReader retries
  sigaction(SIGUSR1, &sa, nullptr);
  if (mode == Mode::HangIgnoreTerm) {
    std::signal(SIGTERM, SIG_IGN);
  } else {
    struct sigaction st{};
    st.sa_handler = on_sigterm;
    sigemptyset(&st.sa_mask);
    st.sa_flags = 0;
    sigaction(SIGTERM, &st, nullptr);
  }

  std::thread flood;
  if (mode == Mode::GarbageStderr) {
    const int flags = ::fcntl(2, F_GETFL, 0);
    if (flags >= 0) (void)::fcntl(2, F_SETFL, flags | O_NONBLOCK);
    flood = std::thread(stderr_flood_thread);
    flood.detach();
  }

  Worker w(mode);
  const int rc = w.run();
  _exit(rc);
}
