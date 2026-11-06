// fake_worker_smoke.cpp - spawn fake-worker over pipes and run the happy path:
// HELLO -> HELLO_ACK, PING -> PONG, DECOMPILE -> RESULT, OPEN_RAW (MORE + RAW)
// -> RESULT, LIFT -> RESULT header + RAW, unknown kind -> ERROR
// unsupported_kind, BYE -> exit 0. Also checks that stderr never carries
// protocol bytes and that GNSDK_EXPECTED_PPID is honoured.

#include <csignal>
#include <cstdio>
#include <string>

#include "spawn_util.hpp"
#include "wtest.hpp"

using namespace wtest;

namespace {

void happy_path() {
  WTEST_SECTION("happy path");
  SpawnOpts o;
  Spawned w = spawn_fake_worker(o);
  proto::FrameReader r;
  proto::HelloInfo remote;
  REQUIRE(do_hello(w, r, remote));
  CHECK_EQ(remote.major, std::uint8_t{1});
  CHECK_EQ(remote.engine_source, std::string("fake-worker"));
  CHECK(!remote.capabilities.empty());
  CHECK_EQ(r.max_payload(), std::size_t{proto::kDefaultMaxFrame});

  proto::Frame f;
  // PING -> PONG
  REQUIRE(send_empty(w, proto::Kind::Ping));
  REQUIRE(wait_frame(r, w, 5000, f) == Wait::Frame);
  CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Pong));
  CHECK_EQ(f.header.request_id, std::uint64_t{0});

  // DECOMPILE -> RESULT ok with the same id
  REQUIRE(send_json(w, proto::Kind::Decompile, 17, decompile_request()));
  REQUIRE(wait_frame(r, w, 5000, f) == Wait::Frame);
  CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Result));
  CHECK_EQ(f.header.request_id, std::uint64_t{17});
  CHECK(!f.header.more());
  CHECK(!f.header.raw());
  json::Value v;
  REQUIRE(json::parse(f.payload_view(), v));
  std::string s;
  CHECK(v.get_string("status", s) && s == "ok");
  CHECK(v.get_string("c", s) && s == "/* fake */");
  CHECK(v.get_array("warnings") != nullptr);
  std::int64_t ms = -1;
  CHECK(v.get_int("elapsed_ms", ms) && ms >= 0);

  // OPEN_RAW: JSON with MORE, two RAW frames, the last without MORE
  REQUIRE(send_json(w, proto::Kind::OpenRaw, 18,
                    R"({"language":"x86:LE:64:default","base":"0x400000","length":6,"readonly":true})",
                    proto::kFlagMore));
  REQUIRE(send_raw(w, proto::Kind::OpenRaw, 18, "abc", 3, proto::kFlagMore));
  REQUIRE(send_raw(w, proto::Kind::OpenRaw, 18, "def", 3));
  REQUIRE(wait_frame(r, w, 5000, f) == Wait::Frame);
  CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Result));
  CHECK_EQ(f.header.request_id, std::uint64_t{18});
  REQUIRE(json::parse(f.payload_view(), v));
  CHECK(v.get_string("status", s) && s == "ok");

  // LIFT -> JSON header with MORE then one RAW frame
  REQUIRE(send_json(w, proto::Kind::Lift, 19, R"({"start":"0x400000","end":"0x400010","max_instructions":16,"deadline_ms":1000})"));
  proto::MessageAssembler asm_(1 << 20);
  proto::AssembleStatus st = proto::AssembleStatus::NeedMore;
  for (int i = 0; i < 2 && st == proto::AssembleStatus::NeedMore; ++i) {
    REQUIRE(wait_frame(r, w, 5000, f) == Wait::Frame);
    CHECK_EQ(f.header.request_id, std::uint64_t{19});
    st = asm_.push(std::move(f));
  }
  REQUIRE(st == proto::AssembleStatus::Complete);
  proto::Message m = asm_.take();
  CHECK_EQ(m.parts.size(), std::size_t{2});
  CHECK(m.parts[0].header.more() && !m.parts[0].header.raw());
  CHECK(!m.parts[1].header.more() && m.parts[1].header.raw());
  REQUIRE(json::parse(m.json(), v));
  std::int64_t n = -1;
  CHECK(v.get_int("num_ops", n) && n == 0);
  CHECK(v.get_array("spaces") != nullptr);
  CHECK_EQ(m.raw_size(), std::size_t{0});

  // unknown kind -> ERROR unsupported_kind
  REQUIRE(send_json(w, static_cast<proto::Kind>(77), 20, "{}"));
  REQUIRE(wait_frame(r, w, 5000, f) == Wait::Frame);
  CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Error));
  CHECK_EQ(f.header.request_id, std::uint64_t{20});
  REQUIRE(json::parse(f.payload_view(), v));
  CHECK(v.get_string("code", s) && s == "unsupported_kind");
  CHECK(v.get_int("kind", n) && n == 77);

  // CLOSE_SESSION -> RESULT ok
  REQUIRE(send_json(w, proto::Kind::CloseSession, 21, "{}"));
  REQUIRE(wait_frame(r, w, 5000, f) == Wait::Frame);
  CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Result));

  // BYE -> exit 0, stdout EOF
  REQUIRE(send_empty(w, proto::Kind::Bye));
  CHECK(wait_frame(r, w, 5000, f) == Wait::Eof);
  REQUIRE(w.wait_exit(5000));
  CHECK_EQ(w.exit_code(), 0);

  // stderr is diagnostics only: whatever it holds must not start with "GNSK"
  char buf[4096];
  const ssize_t got = ::read(w.err, buf, sizeof buf);
  if (got >= 4) CHECK(std::string(buf, 4) != "GNSK");
}

void stdin_eof_exits_clean() {
  WTEST_SECTION("stdin EOF -> exit 0");
  SpawnOpts o;
  Spawned w = spawn_fake_worker(o);
  proto::FrameReader r;
  proto::HelloInfo remote;
  REQUIRE(do_hello(w, r, remote));
  w.close_in();
  REQUIRE(w.wait_exit(5000));
  CHECK_EQ(w.exit_code(), 0);
}

void expected_ppid() {
  WTEST_SECTION("GNSDK_EXPECTED_PPID");
  SpawnOpts o;
  o.expected_ppid_override = 1;  // never our pid
  Spawned w = spawn_fake_worker(o);
  REQUIRE(w.wait_exit(5000));
  CHECK_EQ(w.exit_code(), 7);

  SpawnOpts ok;
  ok.set_expected_ppid = false;  // unset: no check at all
  Spawned w2 = spawn_fake_worker(ok);
  proto::FrameReader r;
  proto::HelloInfo remote;
  CHECK(do_hello(w2, r, remote));
}

void pre_handshake_request_is_rejected() {
  WTEST_SECTION("request before HELLO");
  SpawnOpts o;
  Spawned w = spawn_fake_worker(o);
  proto::FrameReader r;
  REQUIRE(send_json(w, proto::Kind::Decompile, 3, decompile_request()));
  proto::Frame f;
  REQUIRE(wait_frame(r, w, 5000, f) == Wait::Frame);
  CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Error));
  CHECK_EQ(f.header.request_id, std::uint64_t{3});
  json::Value v;
  std::string s;
  REQUIRE(json::parse(f.payload_view(), v));
  CHECK(v.get_string("code", s) && s == "protocol");
  // the worker is still usable afterwards
  proto::HelloInfo remote;
  CHECK(do_hello(w, r, remote));
}

}  // namespace

int main() {
  std::signal(SIGPIPE, SIG_IGN);
  happy_path();
  stdin_eof_exits_clean();
  expected_ppid();
  pre_handshake_request_is_rejected();
  return wtest::exit_code();
}
