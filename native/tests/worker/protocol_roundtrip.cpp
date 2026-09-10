// protocol_roundtrip.cpp - codec, limit and JSON tests for native/worker.
//
// Covers: header encode/decode, short/bad-magic/bad-major headers, FrameReader
// byte-at-a-time feeding, oversize and truncated frames (sticky fatal), the
// pre-handshake limit, pipe round trips through FrameWriter, MORE assembly
// with caps and interleave detection, HELLO negotiation (major mismatch,
// minor = min, max_frame = min, 64 KiB floor), ERROR helpers, hex helpers,
// JSON edge cases (\uXXXX, surrogates, UTF-8, depth, numbers, duplicates),
// and 100k fixed-seed random feeds that must never crash.

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>
#include <thread>
#include <vector>

#include <unistd.h>

#include "worker/json_min.hpp"
#include "worker/protocol.hpp"
#include "wtest.hpp"

namespace proto = gnsdk::proto;
namespace json = gnsdk::json;

namespace {

// splitmix64: tiny, deterministic, good enough for feeding bytes.
struct Rng {
  std::uint64_t s;
  explicit Rng(std::uint64_t seed) : s(seed) {}
  std::uint64_t next() {
    std::uint64_t z = (s += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
  }
  std::uint32_t below(std::uint32_t n) { return static_cast<std::uint32_t>(next() % n); }
};

std::vector<std::uint8_t> frame_bytes(const proto::FrameHeader& h, std::string_view payload) {
  proto::FrameHeader hh = h;
  hh.payload_len = static_cast<std::uint32_t>(payload.size());
  std::uint8_t hdr[proto::kHeaderSize];
  proto::encode_header(hh, hdr);
  std::vector<std::uint8_t> out(hdr, hdr + proto::kHeaderSize);
  out.insert(out.end(), payload.begin(), payload.end());
  return out;
}

void test_header() {
  WTEST_SECTION("header");
  CHECK_EQ(proto::kHeaderSize, std::size_t{24});
  CHECK_EQ(proto::kMagic, std::uint32_t{0x4B534E47u});
  proto::FrameHeader h;
  h.kind = proto::to_u16(proto::Kind::Decompile);
  h.flags = proto::kFlagMore | proto::kFlagRawPayload | 0x80000000u;
  h.payload_len = 0xDEADBEEFu;
  h.request_id = 0x0102030405060708ull;
  std::uint8_t buf[proto::kHeaderSize];
  proto::encode_header(h, buf);
  CHECK_EQ(buf[0], std::uint8_t{'G'});
  CHECK_EQ(buf[1], std::uint8_t{'N'});
  CHECK_EQ(buf[2], std::uint8_t{'S'});
  CHECK_EQ(buf[3], std::uint8_t{'K'});
  CHECK_EQ(buf[4], std::uint8_t{1});
  CHECK_EQ(buf[5], std::uint8_t{0});
  CHECK_EQ(buf[6], std::uint8_t{7});
  CHECK_EQ(buf[7], std::uint8_t{0});
  CHECK_EQ(buf[8], std::uint8_t{3});
  CHECK_EQ(buf[11], std::uint8_t{0x80});
  CHECK_EQ(buf[12], std::uint8_t{0xEF});
  CHECK_EQ(buf[15], std::uint8_t{0xDE});
  CHECK_EQ(buf[16], std::uint8_t{0x08});
  CHECK_EQ(buf[23], std::uint8_t{0x01});

  proto::FrameHeader d;
  CHECK_EQ(proto::decode_header(buf, sizeof buf, d), proto::HeaderError::Ok);
  CHECK_EQ(d.major, h.major);
  CHECK_EQ(d.minor, h.minor);
  CHECK_EQ(d.kind, h.kind);
  CHECK_EQ(d.flags, h.flags);
  CHECK_EQ(d.payload_len, h.payload_len);
  CHECK_EQ(d.request_id, h.request_id);
  CHECK(d.more());
  CHECK(d.raw());

  CHECK_EQ(proto::decode_header(buf, 23, d), proto::HeaderError::ShortBuffer);
  CHECK_EQ(proto::decode_header(nullptr, 24, d), proto::HeaderError::ShortBuffer);
  std::uint8_t bad[proto::kHeaderSize];
  std::memcpy(bad, buf, sizeof buf);
  bad[0] = 'X';
  CHECK_EQ(proto::decode_header(bad, sizeof bad, d), proto::HeaderError::BadMagic);
  std::memcpy(bad, buf, sizeof buf);
  bad[4] = 2;
  CHECK_EQ(proto::decode_header(bad, sizeof bad, d), proto::HeaderError::BadMajor);
  // a different minor is not an error at header level
  std::memcpy(bad, buf, sizeof buf);
  bad[5] = 9;
  CHECK_EQ(proto::decode_header(bad, sizeof bad, d), proto::HeaderError::Ok);
  CHECK_EQ(d.minor, std::uint8_t{9});

  CHECK_EQ(std::string(proto::kind_name(1)), std::string("HELLO"));
  CHECK_EQ(std::string(proto::kind_name(103)), std::string("PONG"));
  CHECK_EQ(std::string(proto::kind_name(77)), std::string("?"));
  CHECK(proto::is_request_kind(11));
  CHECK(!proto::is_request_kind(2));
  CHECK(proto::is_reply_kind(2));
  CHECK(proto::is_reply_kind(100));
  CHECK(!proto::is_known_kind(0));
  CHECK(!proto::is_known_kind(12));
  CHECK(!proto::is_known_kind(104));
  CHECK(proto::is_connection_kind(10));
  CHECK(!proto::is_connection_kind(7));
}

void test_reader_basic() {
  WTEST_SECTION("reader basic");
  proto::FrameHeader h;
  h.kind = proto::to_u16(proto::Kind::Ping);
  h.request_id = 42;
  const auto bytes = frame_bytes(h, "hello");

  // byte at a time
  proto::FrameReader r;
  for (std::size_t i = 0; i < bytes.size(); ++i) {
    CHECK_EQ(r.feed(&bytes[i], 1), std::size_t{1});
    if (i + 1 < bytes.size()) CHECK(!r.has_frame());
  }
  CHECK(r.has_frame());
  proto::Frame f;
  REQUIRE(r.next(f));
  CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Ping));
  CHECK_EQ(f.header.request_id, std::uint64_t{42});
  CHECK_EQ(std::string(f.payload_view()), std::string("hello"));
  CHECK(!r.next(f));
  CHECK_EQ(r.bytes_consumed(), bytes.size());
  CHECK(!r.fatal());

  // three frames in one feed, one empty
  proto::FrameHeader e;
  e.kind = proto::to_u16(proto::Kind::Pong);
  std::vector<std::uint8_t> all = bytes;
  const auto empty = frame_bytes(e, "");
  all.insert(all.end(), empty.begin(), empty.end());
  all.insert(all.end(), bytes.begin(), bytes.end());
  proto::FrameReader r2;
  CHECK_EQ(r2.feed(all.data(), all.size()), all.size());
  CHECK_EQ(r2.pending_frames(), std::size_t{3});
  REQUIRE(r2.next(f));
  CHECK_EQ(f.payload.size(), std::size_t{5});
  REQUIRE(r2.next(f));
  CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Pong));
  CHECK(f.payload.empty());
  REQUIRE(r2.next(f));
  CHECK(!r2.next(f));

  // clean EOF on a boundary
  r2.end_of_input();
  CHECK(r2.eof());
  CHECK(!r2.fatal());
}

void test_reader_fatal() {
  WTEST_SECTION("reader fatal");
  proto::FrameHeader h;
  h.kind = proto::to_u16(proto::Kind::Result);
  h.request_id = 1;

  // truncated header
  {
    proto::FrameReader r;
    const auto b = frame_bytes(h, "abc");
    r.feed(b.data(), 12);
    CHECK_EQ(r.header_bytes_pending(), std::size_t{12});
    r.end_of_input();
    CHECK(r.fatal());
    CHECK_EQ(r.fatal_reason(), proto::FatalReason::Truncated);
    // sticky: nothing more is consumed
    CHECK_EQ(r.feed(b.data(), b.size()), std::size_t{0});
  }
  // truncated payload
  {
    proto::FrameReader r;
    const auto b = frame_bytes(h, "abcdef");
    r.feed(b.data(), b.size() - 2);
    CHECK(r.in_payload());
    CHECK_EQ(r.current_header().payload_len, std::uint32_t{6});
    CHECK(!r.has_frame());
    r.end_of_input();
    CHECK_EQ(r.fatal_reason(), proto::FatalReason::Truncated);
  }
  // bad magic mid-stream, after one good frame
  {
    proto::FrameReader r;
    auto b = frame_bytes(h, "x");
    auto bad = frame_bytes(h, "y");
    bad[2] = 'Z';
    b.insert(b.end(), bad.begin(), bad.end());
    const std::size_t taken = r.feed(b.data(), b.size());
    CHECK(r.fatal());
    CHECK_EQ(r.fatal_reason(), proto::FatalReason::BadMagic);
    CHECK_EQ(taken, std::size_t{25 + 24});  // good frame + the offending header
    CHECK_EQ(r.pending_frames(), std::size_t{1});
    CHECK_EQ(r.feed(b.data(), 1), std::size_t{0});
  }
  // bad major
  {
    proto::FrameReader r;
    auto bad = frame_bytes(h, "");
    bad[4] = 3;
    r.feed(bad.data(), bad.size());
    CHECK_EQ(r.fatal_reason(), proto::FatalReason::BadMajor);
  }
  // oversize: pre-handshake limit is 64 KiB
  {
    proto::FrameReader r;
    CHECK_EQ(r.max_payload(), std::size_t{proto::kPreHandshakeMaxFrame});
    proto::FrameHeader big = h;
    std::uint8_t hdr[proto::kHeaderSize];
    big.payload_len = proto::kPreHandshakeMaxFrame + 1;
    proto::encode_header(big, hdr);
    r.feed(hdr, sizeof hdr);
    CHECK(r.fatal());
    CHECK_EQ(r.fatal_reason(), proto::FatalReason::PayloadTooLarge);
    CHECK_EQ(r.current_header().payload_len, proto::kPreHandshakeMaxFrame + 1);
  }
  // exactly at the limit is fine; raising the limit admits more
  {
    proto::FrameReader r;
    std::string payload(proto::kPreHandshakeMaxFrame, 'p');
    auto b = frame_bytes(h, payload);
    CHECK_EQ(r.feed(b.data(), b.size()), b.size());
    CHECK(!r.fatal());
    CHECK_EQ(r.pending_frames(), std::size_t{1});
    r.set_max_payload(proto::kDefaultMaxFrame);
    std::string bigger(proto::kPreHandshakeMaxFrame * 2, 'q');
    auto b2 = frame_bytes(h, bigger);
    CHECK_EQ(r.feed(b2.data(), b2.size()), b2.size());
    CHECK(!r.fatal());
    CHECK_EQ(r.pending_frames(), std::size_t{2});
  }
  // 0xFFFFFFFF payload_len against the default limit
  {
    proto::FrameReader r(proto::kDefaultMaxFrame);
    proto::FrameHeader big = h;
    big.payload_len = 0xFFFFFFFFu;
    std::uint8_t hdr[proto::kHeaderSize];
    proto::encode_header(big, hdr);
    r.feed(hdr, sizeof hdr);
    CHECK_EQ(r.fatal_reason(), proto::FatalReason::PayloadTooLarge);
  }
  CHECK_EQ(std::string(proto::fatal_reason_name(proto::FatalReason::PayloadTooLarge)),
           std::string("payload_too_large"));
}

void test_pipe_roundtrip() {
  WTEST_SECTION("pipe roundtrip");
  int fds[2];
  REQUIRE(::pipe(fds) == 0);
  std::string big(40000, 'z');
  bool wrote_json = false, wrote_raw = false, wrote_ping = false;
  // A 40 KiB frame is intentionally larger than common pipe capacities.
  // Drain concurrently so this tests FrameWriter's partial-write loop rather
  // than deadlocking before FrameReader gets a chance to run.
  std::thread writer([&] {
    proto::FrameWriter w(fds[1]);
    wrote_json = w.write_json(proto::Kind::Decompile, 7, "{\"addr\":\"0x1\"}", proto::kFlagRawPayload);
    wrote_raw = w.write_raw(proto::Kind::OpenRaw, 8, big.data(), big.size(), proto::kFlagMore);
    wrote_ping = w.write_empty(proto::Kind::Ping);
    ::close(fds[1]);
  });

  proto::FrameReader r;
  proto::Frame f;
  int frames = 0;
  for (;;) {
    const proto::ReadStatus st = r.read(fds[0]);
    while (r.next(f)) {
      ++frames;
      if (frames == 1) {
        CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Decompile));
        CHECK(!f.header.raw());
        CHECK_EQ(f.header.request_id, std::uint64_t{7});
      } else if (frames == 2) {
        CHECK(f.header.raw());
        CHECK(f.header.more());
        CHECK_EQ(f.payload.size(), big.size());
      } else {
        CHECK_EQ(f.header.kind, proto::to_u16(proto::Kind::Ping));
        CHECK_EQ(f.header.request_id, std::uint64_t{0});
      }
    }
    if (st == proto::ReadStatus::Eof || st == proto::ReadStatus::Fatal || st == proto::ReadStatus::Error) {
      CHECK_EQ(st, proto::ReadStatus::Eof);
      break;
    }
  }
  CHECK_EQ(frames, 3);
  CHECK(r.eof());
  CHECK(!r.fatal());
  CHECK_EQ(r.read(fds[0]), proto::ReadStatus::Eof);
  ::close(fds[0]);
  writer.join();
  CHECK(wrote_json);  // RAW is stripped for JSON frames
  CHECK(wrote_raw);
  CHECK(wrote_ping);

  // writer send-side cap
  REQUIRE(::pipe(fds) == 0);
  proto::FrameWriter capped(fds[1]);
  capped.set_max_payload(10);
  CHECK(!capped.write_json(proto::Kind::Ping, 0, "0123456789ab"));
  CHECK_EQ(capped.last_errno(), EMSGSIZE);
  CHECK(capped.write_json(proto::Kind::Ping, 0, "0123456789"));
  ::close(fds[0]);
  // EPIPE when the reader is gone (SIGPIPE ignored in main)
  CHECK(!capped.write_json(proto::Kind::Ping, 0, "x"));
  CHECK_EQ(capped.last_errno(), EPIPE);
  ::close(fds[1]);
}

proto::Frame mk(proto::Kind k, std::uint64_t id, std::string payload, std::uint32_t flags) {
  proto::Frame f;
  f.header.kind = proto::to_u16(k);
  f.header.request_id = id;
  f.header.flags = flags;
  f.header.payload_len = static_cast<std::uint32_t>(payload.size());
  f.payload.assign(payload.begin(), payload.end());
  return f;
}

void test_assembler() {
  WTEST_SECTION("assembler");
  using AS = proto::AssembleStatus;
  proto::MessageAssembler a(100);
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 5, "{\"language\":\"x\"}", proto::kFlagMore)), AS::NeedMore);
  CHECK(a.in_progress());
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 5, "AAAA", proto::kFlagMore | proto::kFlagRawPayload)), AS::NeedMore);
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 5, "BB", proto::kFlagMore | proto::kFlagRawPayload)), AS::NeedMore);
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 5, "C", proto::kFlagRawPayload)), AS::Complete);
  CHECK(a.complete());
  proto::Message m = a.take();
  CHECK_EQ(m.kind, proto::to_u16(proto::Kind::OpenRaw));
  CHECK_EQ(m.request_id, std::uint64_t{5});
  CHECK_EQ(m.parts.size(), std::size_t{4});
  CHECK_EQ(std::string(m.json()), std::string("{\"language\":\"x\"}"));
  CHECK_EQ(m.raw_size(), std::size_t{7});
  std::vector<std::uint8_t> raw;
  m.copy_raw(raw);
  CHECK_EQ(std::string(raw.begin(), raw.end()), std::string("AAAABBC"));
  CHECK_EQ(m.total_bytes, std::size_t{16 + 7});
  CHECK(!a.in_progress());
  CHECK(!a.complete());

  // single frame message
  CHECK_EQ(a.push(mk(proto::Kind::Ping, 0, "", 0)), AS::Complete);
  m = a.take();
  CHECK_EQ(m.parts.size(), std::size_t{1});
  CHECK(m.json().empty());

  // cap: total would exceed 100
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 6, std::string(60, 'a'), proto::kFlagMore)), AS::NeedMore);
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 6, std::string(41, 'b'), proto::kFlagRawPayload)), AS::CapExceeded);
  CHECK(!a.in_progress());
  // a single part over the cap
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 6, std::string(101, 'b'), 0)), AS::CapExceeded);
  // exactly at cap is fine
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 6, std::string(100, 'b'), 0)), AS::Complete);
  a.take();

  // interleaved: id changes mid-message
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 7, "x", proto::kFlagMore)), AS::NeedMore);
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 8, "y", 0)), AS::Interleaved);
  CHECK(!a.in_progress());
  // kind changes mid-message
  CHECK_EQ(a.push(mk(proto::Kind::OpenRaw, 7, "x", proto::kFlagMore)), AS::NeedMore);
  CHECK_EQ(a.push(mk(proto::Kind::Decompile, 7, "y", 0)), AS::Interleaved);

  // too many parts
  proto::MessageAssembler small(1000, 3);
  CHECK_EQ(small.push(mk(proto::Kind::Lift, 1, "a", proto::kFlagMore)), AS::NeedMore);
  CHECK_EQ(small.push(mk(proto::Kind::Lift, 1, "b", proto::kFlagMore)), AS::NeedMore);
  CHECK_EQ(small.push(mk(proto::Kind::Lift, 1, "c", proto::kFlagMore)), AS::NeedMore);
  CHECK_EQ(small.push(mk(proto::Kind::Lift, 1, "d", 0)), AS::TooManyParts);

  // forgotten take(): the next push starts a new message
  CHECK_EQ(small.push(mk(proto::Kind::Ping, 0, "", 0)), AS::Complete);
  CHECK_EQ(small.push(mk(proto::Kind::Pong, 0, "", 0)), AS::Complete);
  CHECK_EQ(small.take().kind, proto::to_u16(proto::Kind::Pong));
  CHECK_EQ(std::string(proto::assemble_status_name(AS::CapExceeded)), std::string("cap_exceeded"));
}

void test_hello() {
  WTEST_SECTION("hello");
  proto::HelloInfo a;
  a.capabilities = {"decompile", "lift"};
  a.engine_source = "Ghidra_12.1.3_build";
  const std::string text = make_hello(a);
  json::Value v;
  REQUIRE(json::parse(text, v));
  std::int64_t i = 0;
  REQUIRE(v.get_object("protocol") != nullptr);
  CHECK(v.get_object("protocol")->get_int("major", i) && i == 1);
  CHECK(v.get_object("protocol")->get_int("minor", i) && i == 0);
  CHECK(v.get_int("max_frame", i) && i == 67108864);
  CHECK(v.get_int("max_image_bytes", i) && i == 536870912);
  REQUIRE(v.get_array("capabilities") != nullptr);
  CHECK_EQ(v.get_array("capabilities")->size(), std::size_t{2});
  std::string s;
  REQUIRE(v.get_object("engine") != nullptr);
  CHECK(v.get_object("engine")->get_string("source", s) && s == "Ghidra_12.1.3_build");
  CHECK(v.get_object("engine")->get_string("abi", s) && s == "0.1.0");

  proto::HelloInfo b;
  std::string err;
  REQUIRE(proto::parse_hello(text, b, &err));
  CHECK_EQ(b.major, std::uint8_t{1});
  CHECK_EQ(b.minor, std::uint8_t{0});
  CHECK_EQ(b.max_frame, proto::kDefaultMaxFrame);
  CHECK_EQ(b.max_image_bytes, proto::kDefaultMaxImageBytes);
  CHECK_EQ(b.capabilities.size(), std::size_t{2});
  CHECK_EQ(b.engine_source, std::string("Ghidra_12.1.3_build"));

  // minimal hello: only protocol; defaults apply
  REQUIRE(proto::parse_hello(R"({"protocol":{"major":1,"minor":3}})", b, &err));
  CHECK_EQ(b.minor, std::uint8_t{3});
  CHECK_EQ(b.max_frame, proto::kDefaultMaxFrame);
  CHECK(b.capabilities.empty());

  CHECK(!proto::parse_hello("{}", b, &err));
  CHECK(!err.empty());
  CHECK(!proto::parse_hello("not json", b, &err));
  CHECK(!proto::parse_hello(R"({"protocol":{"major":1}})", b, &err));
  CHECK(!proto::parse_hello(R"({"protocol":{"major":256,"minor":0}})", b, &err));
  CHECK(!proto::parse_hello(R"({"protocol":{"major":1,"minor":0},"max_frame":-1})", b, &err));
  CHECK(!proto::parse_hello(R"({"protocol":{"major":1,"minor":0},"max_frame":4294967296})", b, &err));
  CHECK(!proto::parse_hello(R"({"protocol":{"major":1,"minor":0},"capabilities":"x"})", b, &err));
  CHECK(!proto::parse_hello(R"({"protocol":{"major":1,"minor":0},"capabilities":[1]})", b, &err));
  CHECK(!proto::parse_hello("[1]", b, &err));

  // negotiation
  proto::HelloInfo local, remote;
  local.minor = 2;
  remote.minor = 5;
  remote.max_frame = 1u << 20;
  remote.max_image_bytes = 1ull << 30;
  proto::Negotiated n = proto::negotiate(local, remote);
  CHECK(n.ok);
  CHECK_EQ(n.major, std::uint8_t{1});
  CHECK_EQ(n.minor, std::uint8_t{2});
  CHECK_EQ(n.max_frame, std::uint32_t{1u << 20});
  CHECK_EQ(n.max_image_bytes, proto::kDefaultMaxImageBytes);  // min(512 MiB, 1 GiB)
  local.minor = 7;
  n = proto::negotiate(local, remote);
  CHECK_EQ(n.minor, std::uint8_t{5});

  remote.major = 2;
  n = proto::negotiate(local, remote);
  CHECK(!n.ok);
  CHECK(n.error.find("major") != std::string::npos);

  remote.major = 1;
  remote.max_frame = proto::kPreHandshakeMaxFrame - 1;
  n = proto::negotiate(local, remote);
  CHECK(!n.ok);
  remote.max_frame = proto::kPreHandshakeMaxFrame;
  n = proto::negotiate(local, remote);
  CHECK(n.ok);
}

void test_error_and_hex() {
  WTEST_SECTION("error + hex");
  json::Value v;
  REQUIRE(json::parse(proto::make_error(proto::ErrorCode::Timeout, "too slow \"quoted\"", 42), v));
  std::string s;
  std::int64_t i = 0;
  CHECK(v.get_string("code", s) && s == "timeout");
  CHECK(v.get_string("message", s) && s == "too slow \"quoted\"");
  CHECK(v.get_int("status", i) && i == 42);
  REQUIRE(json::parse(proto::make_unsupported_kind(77), v));
  CHECK(v.get_string("code", s) && s == "unsupported_kind");
  CHECK(v.get_int("kind", i) && i == 77);
  for (int c = 0; c <= static_cast<int>(proto::ErrorCode::Protocol); ++c) {
    CHECK(std::string(proto::error_code_name(static_cast<proto::ErrorCode>(c))) != "?");
  }
  CHECK_EQ(std::string(proto::error_code_name(proto::ErrorCode::InvalidArgument)), std::string("invalid_argument"));

  CHECK_EQ(proto::format_hex(0), std::string("0x0"));
  CHECK_EQ(proto::format_hex(0x401000), std::string("0x401000"));
  CHECK_EQ(proto::format_hex(~0ull), std::string("0xffffffffffffffff"));
  std::uint64_t x = 0;
  CHECK(proto::parse_hex("0x401000", x) && x == 0x401000);
  CHECK(proto::parse_hex("0X1A", x) && x == 0x1A);
  CHECK(proto::parse_hex("ff", x) && x == 0xff);
  CHECK(proto::parse_hex("0xffffffffffffffff", x) && x == ~0ull);
  CHECK(!proto::parse_hex("", x));
  CHECK(!proto::parse_hex("0x", x));
  CHECK(!proto::parse_hex("0x1g", x));
  CHECK(!proto::parse_hex("0x10000000000000000", x));
  CHECK(!proto::parse_hex("-1", x));
}

bool parses(std::string_view t, json::Value* out = nullptr, const json::ParseOptions& o = json::ParseOptions{}) {
  json::Value v;
  const bool ok = json::parse(t, v, nullptr, o);
  if (out) *out = std::move(v);
  return ok;
}

void test_json() {
  WTEST_SECTION("json");
  json::Value v;
  // escapes and \uXXXX
  REQUIRE(parses(R"("a\"b\\c\/d\b\f\n\r\tAé€😀")", &v));
  CHECK_EQ(v.as_string(), std::string("a\"b\\c/d\b\f\n\r\tA\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80"));
  CHECK(!parses(R"("\ud83d")"));         // lone high surrogate
  CHECK(!parses(R"("\ud83dx")"));
  CHECK(!parses(R"("\ud83dA")"));   // high followed by non-low
  CHECK(!parses(R"("\ude00")"));         // lone low surrogate
  CHECK(!parses(R"("\u12")"));           // truncated
  CHECK(!parses(R"("\u12G4")"));
  CHECK(!parses(R"("\x41")"));           // invalid escape
  CHECK(!parses("\"a\nb\""));            // raw control char
  CHECK(!parses("\"abc"));               // unterminated
  CHECK(!parses(std::string_view("\"\0\"", 3)));   // raw NUL is a control char
  CHECK(parses("\"\x7f\"", &v));            // DEL is allowed raw
  CHECK_EQ(v.as_string().size(), std::size_t{1});
  // raw UTF-8
  CHECK(parses("\"\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80\"", &v));
  CHECK_EQ(v.as_string().size(), std::size_t{9});
  CHECK(!parses("\"\xC3\""));            // truncated sequence
  CHECK(!parses("\"\xC0\x80\""));        // overlong
  CHECK(!parses("\"\xED\xA0\x80\""));    // encoded surrogate
  CHECK(!parses("\"\xF4\x90\x80\x80\""));// > U+10FFFF
  CHECK(!parses("\"\xFF\""));
  CHECK(json::validate_utf8("ok \xC3\xA9"));
  CHECK(!json::validate_utf8("\x80"));

  // numbers
  REQUIRE(parses("9223372036854775807", &v));
  CHECK(v.is_int() && v.as_int() == INT64_MAX);
  REQUIRE(parses("-9223372036854775808", &v));
  CHECK(v.is_int() && v.as_int() == INT64_MIN);
  REQUIRE(parses("9223372036854775808", &v));
  CHECK(v.is_double());
  REQUIRE(parses("-0", &v));
  CHECK(v.is_int() && v.as_int() == 0);
  REQUIRE(parses("1.5e3", &v));
  CHECK(v.is_double() && v.as_double() == 1500.0);
  CHECK_EQ(v.as_int(), std::int64_t{1500});
  REQUIRE(parses("1e400", &v));
  CHECK(v.is_double() && std::isfinite(v.as_double()));
  REQUIRE(parses("1E-400", &v));
  CHECK(v.is_double() && v.as_double() == 0.0);
  REQUIRE(parses("-1e-400", &v));
  CHECK(v.is_double() && v.as_double() == 0.0);
  CHECK(!parses("01"));
  CHECK(!parses("1."));
  CHECK(!parses(".5"));
  CHECK(!parses("1e"));
  CHECK(!parses("1e+"));
  CHECK(!parses("-"));
  CHECK(!parses("+1"));
  CHECK(!parses("NaN"));
  CHECK(!parses("Infinity"));
  CHECK(!parses("0x10"));
  std::uint64_t u = 0;
  REQUIRE(parses(R"({"a":-1,"b":5})", &v));
  CHECK(!v.get_uint("a", u));
  CHECK(v.get_uint("b", u) && u == 5);

  // literals, structure, whitespace
  CHECK(parses(" \t\r\n true \n", &v) && v.as_bool());
  CHECK(parses("null", &v) && v.is_null());
  CHECK(!parses("tru"));
  CHECK(!parses("nul"));
  CHECK(!parses(""));
  CHECK(!parses("   "));
  CHECK(!parses("{} x"));
  CHECK(!parses("[1,]"));
  CHECK(!parses("[,1]"));
  CHECK(!parses("{\"a\":1,}"));
  CHECK(!parses("{a:1}"));
  CHECK(!parses("{\"a\" 1}"));
  CHECK(!parses("{\"a\":1"));
  CHECK(!parses("[1"));
  CHECK(!parses("]"));
  CHECK(parses("[]", &v) && v.is_array() && v.empty());
  CHECK(parses("{}", &v) && v.is_object() && v.empty());
  CHECK(parses("[[[]],{}]", &v) && v.size() == 2);

  // depth limit: default 64
  {
    std::string deep(64, '['), close(64, ']');
    CHECK(parses(deep + close));
    std::string deeper(65, '['), closer(65, ']');
    CHECK(!parses(deeper + closer));
    json::ParseOptions o;
    o.max_depth = 2;
    CHECK(parses("[[1]]", nullptr, o));
    CHECK(!parses("[[[1]]]", nullptr, o));
    CHECK(!parses("{\"a\":{\"b\":{\"c\":1}}}", nullptr, o));
    // a huge nesting must fail cleanly, not overflow the stack
    std::string huge(200000, '[');
    CHECK(!parses(huge));
    o.max_depth = 2;
    o.max_bytes = 3;
    CHECK(!parses("[1,2]", nullptr, o));
    CHECK(parses("[1]", nullptr, o));
    json::ParseError pe;
    json::Value tmp;
    CHECK(!json::parse("[1,2]", tmp, &pe, o));
    CHECK(std::string(pe.message).find("size") != std::string::npos);
    CHECK(!json::parse("[1, x]", tmp, &pe));
    CHECK_EQ(pe.offset, std::size_t{4});
  }

  // duplicates: last wins; order kept on dump
  REQUIRE(parses(R"({"a":1,"b":2,"a":3})", &v));
  std::int64_t i = 0;
  CHECK(v.get_int("a", i) && i == 3);
  CHECK_EQ(v.keys().size(), std::size_t{3});
  CHECK_EQ(v.dump(), std::string(R"({"a":1,"b":2,"a":3})"));

  // builders and dump round trip
  json::Value o = json::Value::object();
  o.set("s", "q\"\\\n\x01\x7f");
  o.set("i", -5);
  o.set("u", 18446744073709551615ull);  // does not fit int64 -> double
  o.set("d", 0.5);
  o.set("b", true);
  o.set("n", nullptr);
  json::Value arr = json::Value::array();
  arr.push(1).push("two").push(json::Value::object());
  o.set("a", std::move(arr));
  o.set("i", 6);  // replace
  const std::string dumped = o.dump();
  CHECK(dumped.find("\\u0001") != std::string::npos);
  CHECK(dumped.find("\\u007f") != std::string::npos);
  CHECK(dumped.find("\"i\":6") != std::string::npos);
  json::Value back;
  REQUIRE(parses(dumped, &back));
  CHECK_EQ(back.dump(), dumped);
  std::string s;
  CHECK(back.get_string("s", s) && s == "q\"\\\n\x01\x7f");
  CHECK(back.get("u")->is_double());
  double d = 0;
  CHECK(back.get_double("d", d) && d == 0.5);
  CHECK(back.get_double("i", d) && d == 6.0);
  bool bb = false;
  CHECK(back.get_bool("b", bb) && bb);
  CHECK(back.get("n") != nullptr && back.get("n")->is_null());
  CHECK(back.get("missing") == nullptr);
  CHECK(!back.get_int("s", i));
  CHECK(back.get_array("a") != nullptr && back.get_array("a")->size() == 3);
  CHECK((*back.get_array("a"))[1].as_string() == "two");
  CHECK(json::Value(std::numeric_limits<double>::infinity()).dump() == "null");
  CHECK(json::Value(static_cast<const char*>(nullptr)).as_string().empty());
  CHECK(json::Value(3).as_string().empty());
  CHECK_EQ(json::Value(1.0).as_int(), std::int64_t{1});
  CHECK_EQ(json::Value(1.5).as_int(7), std::int64_t{7});
  CHECK_EQ(json::Value(1e30).as_int(7), std::int64_t{7});
  // set() on a non-object is a no-op; push() on a non-array too
  json::Value str("x");
  str.set("k", 1);
  CHECK(str.is_string());
  str.push(1);
  CHECK(str.is_string());
  json::Value nul;
  nul.push(1);
  CHECK(nul.is_array());
}

// Random feeds: FrameReader and json::parse must never crash and must keep
// their invariants. Fixed seed so a failure is reproducible.
void test_fuzz() {
  WTEST_SECTION("fuzz 100k");
  Rng rng(0x5EEDULL);
  const char* alphabet = "{}[]\":,0123456789.eE+-tfnrulas\\ \n\xC3\xA9\x80GNSK";
  const std::size_t alen = std::strlen(alphabet);
  std::size_t reader_frames = 0, reader_fatal = 0, json_ok = 0;
  std::vector<std::uint8_t> buf;
  std::string text;
  const std::string good_doc =
      R"({"protocol":{"major":1,"minor":0},"max_frame":65536,"capabilities":["a","é"],"engine":{"source":"x"}})";
  for (int iter = 0; iter < 100000; ++iter) {
    const int which = static_cast<int>(rng.below(3));
    if (which == 0) {
      // FrameReader: random bytes, sometimes seeded with a valid header
      buf.clear();
      const std::size_t n = rng.below(200);
      if (rng.below(2) == 0) {
        proto::FrameHeader h;
        h.kind = static_cast<std::uint16_t>(rng.below(120));
        h.flags = rng.below(4);
        h.payload_len = rng.below(300);
        h.request_id = rng.next();
        std::uint8_t hdr[proto::kHeaderSize];
        proto::encode_header(h, hdr);
        buf.assign(hdr, hdr + proto::kHeaderSize);
        if (rng.below(4) == 0) buf[rng.below(24)] = static_cast<std::uint8_t>(rng.next());
      }
      for (std::size_t k = 0; k < n; ++k) buf.push_back(static_cast<std::uint8_t>(rng.next()));
      proto::FrameReader r(rng.below(2) == 0 ? 64 : 100000);
      std::size_t fed = 0;
      std::size_t pos = 0;
      while (pos < buf.size()) {
        const std::size_t chunk = 1 + rng.below(50);
        const std::size_t take = std::min(chunk, buf.size() - pos);
        const std::size_t got = r.feed(buf.data() + pos, take);
        fed += got;
        if (got < take) {
          REQUIRE(r.fatal());
          break;
        }
        pos += take;
      }
      r.end_of_input();
      REQUIRE(r.bytes_consumed() == fed);
      REQUIRE(fed <= buf.size());
      if (r.fatal()) {
        ++reader_fatal;
        REQUIRE(r.feed(buf.data(), 1) == 0);
      }
      proto::Frame f;
      while (r.next(f)) {
        ++reader_frames;
        REQUIRE(f.payload.size() == f.header.payload_len);
        REQUIRE(f.payload.size() <= r.max_payload());
      }
    } else if (which == 1) {
      // JSON: random alphabet soup
      text.clear();
      const std::size_t n = rng.below(64);
      for (std::size_t k = 0; k < n; ++k) text.push_back(alphabet[rng.below(static_cast<std::uint32_t>(alen))]);
      json::Value v;
      json::ParseError pe;
      json::ParseOptions o;
      o.max_depth = 1 + rng.below(8);
      if (json::parse(text, v, &pe, o)) {
        ++json_ok;
        json::Value again;
        REQUIRE(json::parse(v.dump(), again));
        REQUIRE(again.dump() == v.dump());
      } else {
        REQUIRE(pe.offset <= text.size());
      }
    } else {
      // JSON: mutated good document
      text = good_doc;
      const int muts = 1 + static_cast<int>(rng.below(4));
      for (int m = 0; m < muts; ++m) {
        const std::size_t at = rng.below(static_cast<std::uint32_t>(text.size()));
        switch (rng.below(3)) {
          case 0: text[at] = alphabet[rng.below(static_cast<std::uint32_t>(alen))]; break;
          case 1: text.erase(at, 1); break;
          default: text.insert(at, 1, alphabet[rng.below(static_cast<std::uint32_t>(alen))]); break;
        }
        if (text.empty()) break;
      }
      json::Value v;
      if (json::parse(text, v)) {
        ++json_ok;
        proto::HelloInfo h;
        proto::parse_hello(text, h);  // must not crash whatever came out
      }
    }
  }
  std::fprintf(stderr, "fuzz: frames=%zu fatal=%zu json_ok=%zu\n", reader_frames, reader_fatal, json_ok);
  CHECK(reader_frames > 0);
  CHECK(reader_fatal > 0);
  CHECK(json_ok > 0);
}

void test_wire_structs() {
  WTEST_SECTION("lift wire structs");
  CHECK_EQ(sizeof(proto::PcodeOpWire), std::size_t{32});
  CHECK_EQ(sizeof(proto::VarnodeWire), std::size_t{16});
  CHECK_EQ(sizeof(proto::InstrWire), std::size_t{24});
  // pack + unpack a tiny lift payload the way a worker would
  proto::PcodeOpWire op{1, 0, proto::kNoIndex, 0, 2, 0, 0x401000};
  proto::VarnodeWire vn[2] = {{0, 8, 0x10}, {1, 8, 0x20}};
  proto::InstrWire in{0x401000, 3, 0, 1, 0};
  std::vector<std::uint8_t> raw;
  auto append = [&](const void* p, std::size_t n) {
    const auto* b = static_cast<const std::uint8_t*>(p);
    raw.insert(raw.end(), b, b + n);
  };
  append(&op, sizeof op);
  append(vn, sizeof vn);
  append(&in, sizeof in);
  CHECK_EQ(raw.size(), std::size_t{32 + 32 + 24});
  proto::PcodeOpWire op2{};
  std::memcpy(&op2, raw.data(), sizeof op2);
  CHECK_EQ(op2.instr_addr, std::uint64_t{0x401000});
  CHECK_EQ(op2.output_index, proto::kNoIndex);
  proto::InstrWire in2{};
  std::memcpy(&in2, raw.data() + 64, sizeof in2);
  CHECK_EQ(in2.length, std::uint32_t{3});
}

}  // namespace

int main() {
  std::signal(SIGPIPE, SIG_IGN);
  test_header();
  test_reader_basic();
  test_reader_fatal();
  test_pipe_roundtrip();
  test_assembler();
  test_hello();
  test_error_and_hex();
  test_json();
  test_wire_structs();
  test_fuzz();
  return wtest::exit_code();
}
