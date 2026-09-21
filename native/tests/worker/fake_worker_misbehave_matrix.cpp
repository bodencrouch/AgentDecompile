// fake_worker_misbehave_matrix.cpp - every --misbehave mode of fake-worker
// against the observable the pool supervisor (WP6) will rely on.
//
//   mode              observable
//   none              full happy path, exit 0 on BYE
//   hang              HELLO_ACK, then no reply in 500 ms; SIGTERM -> exit 0
//   hang-ignore-term  no reply in 500 ms; SIGTERM ignored; SIGKILL kills
//   die-midframe      12 header bytes then EOF -> FrameReader Truncated; exit 9
//   oversize          header payload_len 0xFFFFFFFF -> FrameReader PayloadTooLarge
//   bad-magic         FrameReader BadMagic (sticky)
//   garbage-stderr    replies keep flowing while stderr floods (> 1 MiB seen)
//   slow-reply        HELLO_ACK incomplete at 500 ms, complete later
//   eat-memory        no reply, exit 4 (RLIMIT_AS or the env cap stops it)
//   exit-4            RESULT then exit 4
//   reply-wrong-id    RESULT carries a request_id other than the request's
//   honor-cancel      no reply until SIGUSR1 -> ERROR cancelled; next request ok
//   pdeathsig         parent SIGKILLed -> worker gone within 1 s
//   (input faults)    bad magic / oversize on stdin -> worker exits 2
//   (ppid)            GNSDK_EXPECTED_PPID mismatch -> exit 7

#include <csignal>
#include <cstdio>
#include <string>
#include <thread>

#include <sys/prctl.h>
#include <sys/wait.h>

#include "spawn_util.hpp"
#include "wtest.hpp"

using namespace wtest;

namespace {

constexpr long kNoReplyMs = 500;

struct Session {
  Spawned w;
  proto::FrameReader r;
  proto::HelloInfo remote;
  proto::Frame f;

  explicit Session(const SpawnOpts& o) : w(spawn_fake_worker(o)) {}
  bool hello(long timeout_ms = 5000) { return do_hello(w, r, remote, timeout_ms); }
  Wait decompile(std::uint64_t id, long timeout_ms, std::int64_t deadline_ms = 1000) {
    if (!send_json(w, proto::Kind::Decompile, id, decompile_request(deadline_ms))) return Wait::Error;
    return wait_frame(r, w, timeout_ms, f);
  }
  Wait ping(long timeout_ms) {
    if (!send_empty(w, proto::Kind::Ping)) return Wait::Error;
    return wait_frame(r, w, timeout_ms, f);
  }
};

Session make(const char* mode) {
  SpawnOpts o;
  o.mode = mode;
  return Session(o);
}

void mode_none() {
  WTEST_SECTION("none");
  Session s = make("none");
  REQUIRE(s.hello());
  CHECK(s.ping(5000) == Wait::Frame);
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Pong));
  CHECK(s.decompile(1, 5000) == Wait::Frame);
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Result));
  CHECK_EQ(s.f.header.request_id, std::uint64_t{1});
  CHECK(send_empty(s.w, proto::Kind::Bye));
  REQUIRE(s.w.wait_exit(5000));
  CHECK_EQ(s.w.exit_code(), 0);
}

void mode_hang() {
  WTEST_SECTION("hang");
  Session s = make("hang");
  REQUIRE(s.hello());
  const long t0 = now_ms();
  CHECK(s.decompile(1, kNoReplyMs) == Wait::Timeout);
  CHECK(now_ms() - t0 >= kNoReplyMs);
  CHECK(s.w.alive());
  // SIGUSR1 is ignored by a hung worker (it must not die from it)
  CHECK(s.w.signal(SIGUSR1));
  CHECK(!s.w.wait_exit(200));
  // SIGTERM: the fake exits 0 like the real worker would after finishing
  CHECK(s.w.signal(SIGTERM));
  REQUIRE(s.w.wait_exit(2000));
  CHECK_EQ(s.w.exit_code(), 0);
}

void mode_hang_ignore_term() {
  WTEST_SECTION("hang-ignore-term");
  Session s = make("hang-ignore-term");
  REQUIRE(s.hello());
  CHECK(s.decompile(1, kNoReplyMs) == Wait::Timeout);
  CHECK(s.w.signal(SIGTERM));
  CHECK(!s.w.wait_exit(500));  // still there
  CHECK(s.w.signal(SIGKILL));
  REQUIRE(s.w.wait_exit(2000));
  CHECK_EQ(s.w.term_signal(), SIGKILL);
}

void mode_die_midframe() {
  WTEST_SECTION("die-midframe");
  Session s = make("die-midframe");
  REQUIRE(s.hello());
  const Wait wt = s.decompile(1, 5000);
  CHECK(wt == Wait::Fatal);
  CHECK_EQ(s.r.fatal_reason(), proto::FatalReason::Truncated);
  CHECK_EQ(s.r.header_bytes_pending(), std::size_t{12});
  REQUIRE(s.w.wait_exit(5000));
  CHECK_EQ(s.w.exit_code(), 9);
}

void mode_oversize() {
  WTEST_SECTION("oversize");
  Session s = make("oversize");
  REQUIRE(s.hello());
  CHECK(s.decompile(1, 5000) == Wait::Fatal);
  CHECK_EQ(s.r.fatal_reason(), proto::FatalReason::PayloadTooLarge);
  CHECK_EQ(s.r.current_header().payload_len, std::uint32_t{0xFFFFFFFFu});
  CHECK(s.r.fatal());  // sticky
  CHECK(s.w.alive());  // the supervisor has to kill it
  CHECK(s.w.signal(SIGKILL));
  REQUIRE(s.w.wait_exit(2000));
}

void mode_bad_magic() {
  WTEST_SECTION("bad-magic");
  Session s = make("bad-magic");
  REQUIRE(s.hello());
  CHECK(s.decompile(1, 5000) == Wait::Fatal);
  CHECK_EQ(s.r.fatal_reason(), proto::FatalReason::BadMagic);
  // nothing more is ever consumed
  const std::size_t consumed = s.r.bytes_consumed();
  CHECK(s.r.read(s.w.out) == proto::ReadStatus::Fatal);
  CHECK_EQ(s.r.bytes_consumed(), consumed);
  CHECK(s.w.signal(SIGKILL));
  REQUIRE(s.w.wait_exit(2000));
}

void mode_garbage_stderr() {
  WTEST_SECTION("garbage-stderr");
  Session s = make("garbage-stderr");
  std::size_t drained = 0;
  const int err_fd = s.w.err;
  std::thread drain([&] { drained = drain_bytes(err_fd, 1500); });
  REQUIRE(s.hello());
  CHECK(s.decompile(1, 5000) == Wait::Frame);
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Result));
  CHECK(s.ping(5000) == Wait::Frame);
  drain.join();
  std::fprintf(stderr, "garbage-stderr: drained %zu bytes\n", drained);
  CHECK(drained >= 1u << 20);
  // Stop draining: the flood thread blocks on the full pipe, the protocol
  // thread must still answer.
  CHECK(s.ping(5000) == Wait::Frame);
  CHECK(send_empty(s.w, proto::Kind::Bye));
  REQUIRE(s.w.wait_exit(5000));
  CHECK_EQ(s.w.exit_code(), 0);
}

void mode_slow_reply() {
  WTEST_SECTION("slow-reply");
  Session s = make("slow-reply");
  proto::HelloInfo local;
  REQUIRE(send_json(s.w, proto::Kind::Hello, 0, proto::make_hello(local)));
  const long t0 = now_ms();
  CHECK(wait_frame(s.r, s.w, kNoReplyMs, s.f) == Wait::Timeout);
  CHECK(s.r.bytes_consumed() > 0);  // bytes trickle in
  CHECK(wait_frame(s.r, s.w, 30000, s.f) == Wait::Frame);
  const long took = now_ms() - t0;
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::HelloAck));
  CHECK(took >= 1000);  // ~200 bytes at 10 ms each
  std::fprintf(stderr, "slow-reply: HELLO_ACK after %ld ms\n", took);
  CHECK(proto::parse_hello(s.f.payload_view(), s.remote));
  CHECK(s.w.signal(SIGKILL));
  REQUIRE(s.w.wait_exit(2000));
}

void mode_eat_memory() {
  WTEST_SECTION("eat-memory");
  SpawnOpts o;
  o.mode = "eat-memory";
  // Cap the run either way so the host is never at risk. Sanitizer builds
  // cannot live under RLIMIT_AS (shadow memory), so they rely on the env cap.
#if !defined(__SANITIZE_ADDRESS__) && !(defined(__has_feature) && __has_feature(address_sanitizer))
  o.rlimit_as = 256ull << 20;
#endif
  o.env.emplace_back("GNSDK_FAKE_EAT_MAX_MIB", "192");
  Session s(o);
  REQUIRE(s.hello());
  const Wait wt = s.decompile(1, 20000);
  CHECK(wt == Wait::Eof || wt == Wait::Fatal);
  REQUIRE(s.w.wait_exit(20000));
  CHECK_EQ(s.w.exit_code(), 4);
}

void mode_exit_4() {
  WTEST_SECTION("exit-4");
  Session s = make("exit-4");
  REQUIRE(s.hello());
  CHECK(s.decompile(5, 5000) == Wait::Frame);
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Result));
  CHECK_EQ(s.f.header.request_id, std::uint64_t{5});
  REQUIRE(s.w.wait_exit(5000));
  CHECK_EQ(s.w.exit_code(), 4);
}

void mode_reply_wrong_id() {
  WTEST_SECTION("reply-wrong-id");
  Session s = make("reply-wrong-id");
  REQUIRE(s.hello());  // connection-level ids stay 0
  CHECK(s.decompile(7, 5000) == Wait::Frame);
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Result));
  CHECK(s.f.header.request_id != 7);
  CHECK(s.ping(5000) == Wait::Frame);
  CHECK_EQ(s.f.header.request_id, std::uint64_t{0});
}

void mode_honor_cancel() {
  WTEST_SECTION("honor-cancel");
  Session s = make("honor-cancel");
  REQUIRE(s.hello());
  CHECK(s.decompile(9, 200, 60000) == Wait::Timeout);
  CHECK(s.w.signal(SIGUSR1));
  REQUIRE(wait_frame(s.r, s.w, 5000, s.f) == Wait::Frame);
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Error));
  CHECK_EQ(s.f.header.request_id, std::uint64_t{9});
  json::Value v;
  std::string code;
  REQUIRE(json::parse(s.f.payload_view(), v));
  CHECK(v.get_string("code", code) && code == "cancelled");
  // the worker serves the next request
  CHECK(s.ping(5000) == Wait::Frame);
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Pong));
  // a request whose deadline passes without a signal completes normally
  CHECK(s.decompile(10, 5000, 50) == Wait::Frame);
  CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Result));
  CHECK(send_empty(s.w, proto::Kind::Bye));
  REQUIRE(s.w.wait_exit(5000));
  CHECK_EQ(s.w.exit_code(), 0);
}

// The pdeathsig mode needs an intermediate parent we can SIGKILL. We become
// a child subreaper so the orphaned worker is reparented to us and can be
// waited for.
void mode_pdeathsig() {
  WTEST_SECTION("pdeathsig");
  REQUIRE(::prctl(PR_SET_CHILD_SUBREAPER, 1) == 0);
  int pidpipe[2];
  REQUIRE(::pipe(pidpipe) == 0);
  const pid_t mid = ::fork();
  REQUIRE(mid >= 0);
  if (mid == 0) {
    ::close(pidpipe[0]);
    SpawnOpts o;
    o.mode = "pdeathsig";
    o.capture_stderr = false;
    Spawned w = spawn_fake_worker(o);  // its GNSDK_EXPECTED_PPID = this intermediate
    const long p = w.pid;
    (void)!::write(pidpipe[1], &p, sizeof p);
    ::close(pidpipe[1]);
    w.pid = -1;  // do not kill it from the destructor
    for (;;) pause();
  }
  ::close(pidpipe[1]);
  long gpid = 0;
  REQUIRE(::read(pidpipe[0], &gpid, sizeof gpid) == static_cast<ssize_t>(sizeof gpid));
  ::close(pidpipe[0]);
  REQUIRE(gpid > 0);
  sleep_ms(100);  // let the worker reach prctl()
  CHECK(::kill(static_cast<pid_t>(gpid), 0) == 0);
  REQUIRE(::kill(mid, SIGKILL) == 0);
  int st = 0;
  REQUIRE(::waitpid(mid, &st, 0) == mid);
  // the worker must be gone within 1 s
  const long deadline = now_ms() + 1000;
  bool gone = false;
  int gst = 0;
  while (now_ms() < deadline) {
    const pid_t r = ::waitpid(static_cast<pid_t>(gpid), &gst, WNOHANG);
    if (r == gpid) { gone = true; break; }
    if (r < 0) { gone = true; break; }
    sleep_ms(5);
  }
  CHECK(gone);
  if (gone && WIFSIGNALED(gst)) CHECK_EQ(WTERMSIG(gst), SIGKILL);
  if (!gone) ::kill(static_cast<pid_t>(gpid), SIGKILL);
  ::prctl(PR_SET_CHILD_SUBREAPER, 0);
}

void input_faults() {
  WTEST_SECTION("input faults -> exit 2");
  {
    Session s = make("none");
    REQUIRE(s.hello());
    std::uint8_t junk[proto::kHeaderSize] = {'X', 'X', 'X', 'X'};
    REQUIRE(send_bytes(s.w, junk, sizeof junk));
    REQUIRE(s.w.wait_exit(5000));
    CHECK_EQ(s.w.exit_code(), 2);
  }
  {
    // oversize before the handshake: the 64 KiB pre-handshake limit applies
    Session s = make("none");
    proto::FrameHeader h;
    h.kind = proto::to_u16(proto::Kind::Hello);
    h.payload_len = proto::kPreHandshakeMaxFrame + 1;
    std::uint8_t hdr[proto::kHeaderSize];
    proto::encode_header(h, hdr);
    REQUIRE(send_bytes(s.w, hdr, sizeof hdr));
    REQUIRE(s.w.wait_exit(5000));
    CHECK_EQ(s.w.exit_code(), 2);
  }
  {
    // truncated frame then EOF
    Session s = make("none");
    REQUIRE(s.hello());
    std::uint8_t half[10] = {'G', 'N', 'S', 'K', 1, 0, 10, 0, 0, 0};
    REQUIRE(send_bytes(s.w, half, sizeof half));
    s.w.close_in();
    REQUIRE(s.w.wait_exit(5000));
    CHECK_EQ(s.w.exit_code(), 2);
  }
  {
    // HELLO with the wrong major: ERROR protocol, exit 2
    Session s = make("none");
    REQUIRE(send_json(s.w, proto::Kind::Hello, 0, R"({"protocol":{"major":2,"minor":0}})"));
    REQUIRE(wait_frame(s.r, s.w, 5000, s.f) == Wait::Frame);
    CHECK_EQ(s.f.header.kind, proto::to_u16(proto::Kind::Error));
    REQUIRE(s.w.wait_exit(5000));
    CHECK_EQ(s.w.exit_code(), 2);
  }
}

void wrong_ppid() {
  WTEST_SECTION("expected ppid mismatch -> exit 7");
  SpawnOpts o;
  o.expected_ppid_override = 1;
  Spawned w = spawn_fake_worker(o);
  REQUIRE(w.wait_exit(5000));
  CHECK_EQ(w.exit_code(), 7);
}

}  // namespace

int main(int argc, char** argv) {
  std::signal(SIGPIPE, SIG_IGN);
  const std::string only = argc > 1 ? argv[1] : "";
  auto run = [&](const char* name, void (*fn)()) {
    if (only.empty() || only == name) fn();
  };
  run("none", mode_none);
  run("hang", mode_hang);
  run("hang-ignore-term", mode_hang_ignore_term);
  run("die-midframe", mode_die_midframe);
  run("oversize", mode_oversize);
  run("bad-magic", mode_bad_magic);
  run("garbage-stderr", mode_garbage_stderr);
  run("slow-reply", mode_slow_reply);
  run("eat-memory", mode_eat_memory);
  run("exit-4", mode_exit_4);
  run("reply-wrong-id", mode_reply_wrong_id);
  run("honor-cancel", mode_honor_cancel);
  run("pdeathsig", mode_pdeathsig);
  run("input-faults", input_faults);
  run("wrong-ppid", wrong_ppid);
  return wtest::exit_code();
}
