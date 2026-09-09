// protocol.cpp - see protocol.hpp.
#include "protocol.hpp"

#include <cerrno>
#include <charconv>
#include <cstring>
#include <poll.h>
#include <sys/uio.h>
#include <unistd.h>

#include "json_min.hpp"

namespace gnsdk::proto {

namespace {

inline void put_u16(std::uint8_t* p, std::uint16_t v) {
  p[0] = static_cast<std::uint8_t>(v);
  p[1] = static_cast<std::uint8_t>(v >> 8);
}
inline void put_u32(std::uint8_t* p, std::uint32_t v) {
  for (int i = 0; i < 4; ++i) p[i] = static_cast<std::uint8_t>(v >> (8 * i));
}
inline void put_u64(std::uint8_t* p, std::uint64_t v) {
  for (int i = 0; i < 8; ++i) p[i] = static_cast<std::uint8_t>(v >> (8 * i));
}
inline std::uint16_t get_u16(const std::uint8_t* p) {
  return static_cast<std::uint16_t>(p[0] | (p[1] << 8));
}
inline std::uint32_t get_u32(const std::uint8_t* p) {
  std::uint32_t v = 0;
  for (int i = 3; i >= 0; --i) v = (v << 8) | p[i];
  return v;
}
inline std::uint64_t get_u64(const std::uint8_t* p) {
  std::uint64_t v = 0;
  for (int i = 7; i >= 0; --i) v = (v << 8) | p[i];
  return v;
}

constexpr std::size_t kReadChunk = 64u * 1024u;

}  // namespace

// ---- names -----------------------------------------------------------------

const char* kind_name(std::uint16_t k) noexcept {
  switch (static_cast<Kind>(k)) {
    case Kind::Hello: return "HELLO";
    case Kind::HelloAck: return "HELLO_ACK";
    case Kind::OpenRaw: return "OPEN_RAW";
    case Kind::OpenSnapshot: return "OPEN_SNAPSHOT";
    case Kind::Disasm: return "DISASM";
    case Kind::Lift: return "LIFT";
    case Kind::Decompile: return "DECOMPILE";
    case Kind::CloseSession: return "CLOSE_SESSION";
    case Kind::Cancel: return "CANCEL";
    case Kind::Ping: return "PING";
    case Kind::Bye: return "BYE";
    case Kind::Result: return "RESULT";
    case Kind::Error: return "ERROR";
    case Kind::Progress: return "PROGRESS";
    case Kind::Pong: return "PONG";
  }
  return "?";
}

const char* header_error_name(HeaderError e) noexcept {
  switch (e) {
    case HeaderError::Ok: return "ok";
    case HeaderError::ShortBuffer: return "short_buffer";
    case HeaderError::BadMagic: return "bad_magic";
    case HeaderError::BadMajor: return "bad_major";
  }
  return "?";
}

const char* fatal_reason_name(FatalReason r) noexcept {
  switch (r) {
    case FatalReason::None: return "none";
    case FatalReason::BadMagic: return "bad_magic";
    case FatalReason::BadMajor: return "bad_major";
    case FatalReason::PayloadTooLarge: return "payload_too_large";
    case FatalReason::Truncated: return "truncated";
    case FatalReason::ReadError: return "read_error";
  }
  return "?";
}

const char* assemble_status_name(AssembleStatus s) noexcept {
  switch (s) {
    case AssembleStatus::NeedMore: return "need_more";
    case AssembleStatus::Complete: return "complete";
    case AssembleStatus::CapExceeded: return "cap_exceeded";
    case AssembleStatus::Interleaved: return "interleaved";
    case AssembleStatus::TooManyParts: return "too_many_parts";
  }
  return "?";
}

const char* error_code_name(ErrorCode c) noexcept {
  switch (c) {
    case ErrorCode::Busy: return "busy";
    case ErrorCode::InvalidArgument: return "invalid_argument";
    case ErrorCode::ProviderFailure: return "provider_failure";
    case ErrorCode::EngineFailure: return "engine_failure";
    case ErrorCode::Resource: return "resource";
    case ErrorCode::Cancelled: return "cancelled";
    case ErrorCode::Timeout: return "timeout";
    case ErrorCode::Unsupported: return "unsupported";
    case ErrorCode::Protocol: return "protocol";
  }
  return "?";
}

// ---- header ----------------------------------------------------------------

void encode_header(const FrameHeader& h, std::uint8_t (&out)[kHeaderSize]) noexcept {
  put_u32(out + 0, kMagic);
  out[4] = h.major;
  out[5] = h.minor;
  put_u16(out + 6, h.kind);
  put_u32(out + 8, h.flags);
  put_u32(out + 12, h.payload_len);
  put_u64(out + 16, h.request_id);
}

HeaderError decode_header(const std::uint8_t* buf, std::size_t len, FrameHeader& out) noexcept {
  if (buf == nullptr || len < kHeaderSize) return HeaderError::ShortBuffer;
  if (get_u32(buf) != kMagic) return HeaderError::BadMagic;
  FrameHeader h;
  h.major = buf[4];
  h.minor = buf[5];
  h.kind = get_u16(buf + 6);
  h.flags = get_u32(buf + 8);
  h.payload_len = get_u32(buf + 12);
  h.request_id = get_u64(buf + 16);
  if (h.major != kProtocolMajor) return HeaderError::BadMajor;
  out = h;
  return HeaderError::Ok;
}

// ---- writer ----------------------------------------------------------------

bool FrameWriter::write_frame(const FrameHeader& hin, const void* payload, std::size_t len) noexcept {
  if (len > 0xFFFFFFFFu || (max_payload_ != 0 && len > max_payload_)) {
    errno_ = EMSGSIZE;
    return false;
  }
  FrameHeader h = hin;
  h.payload_len = static_cast<std::uint32_t>(len);
  std::uint8_t hdr[kHeaderSize];
  encode_header(h, hdr);

  iovec iov[2];
  iov[0].iov_base = hdr;
  iov[0].iov_len = kHeaderSize;
  iov[1].iov_base = const_cast<void*>(payload);
  iov[1].iov_len = len;
  int iovcnt = len > 0 ? 2 : 1;
  iovec* cur = iov;

  while (iovcnt > 0) {
    const ssize_t n = ::writev(fd_, cur, iovcnt);
    if (n < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == EWOULDBLOCK) {
        pollfd pfd{fd_, POLLOUT, 0};
        const int pr = ::poll(&pfd, 1, -1);
        if (pr < 0 && errno != EINTR) { errno_ = errno; return false; }
        continue;
      }
      errno_ = errno;
      return false;
    }
    std::size_t left = static_cast<std::size_t>(n);
    while (iovcnt > 0 && left >= cur->iov_len) {
      left -= cur->iov_len;
      ++cur;
      --iovcnt;
    }
    if (iovcnt > 0 && left > 0) {
      cur->iov_base = static_cast<std::uint8_t*>(cur->iov_base) + left;
      cur->iov_len -= left;
    }
  }
  errno_ = 0;
  return true;
}

bool FrameWriter::write_json(Kind kind, std::uint64_t request_id, std::string_view json,
                             std::uint32_t flags) noexcept {
  FrameHeader h;
  h.kind = to_u16(kind);
  h.flags = flags & ~kFlagRawPayload;
  h.request_id = request_id;
  return write_frame(h, json.data(), json.size());
}

bool FrameWriter::write_raw(Kind kind, std::uint64_t request_id, const void* data, std::size_t len,
                            std::uint32_t flags) noexcept {
  FrameHeader h;
  h.kind = to_u16(kind);
  h.flags = flags | kFlagRawPayload;
  h.request_id = request_id;
  return write_frame(h, data, len);
}

bool FrameWriter::write_empty(Kind kind, std::uint64_t request_id) noexcept {
  FrameHeader h;
  h.kind = to_u16(kind);
  h.request_id = request_id;
  return write_frame(h, nullptr, 0);
}

// ---- reader ----------------------------------------------------------------

FrameReader::FrameReader(std::size_t max_payload) : max_payload_(max_payload) {}

void FrameReader::complete_frame() {
  Frame f;
  f.header = cur_;
  f.payload = std::move(payload_);
  payload_ = std::vector<std::uint8_t>();
  ready_.push_back(std::move(f));
  in_payload_ = false;
  hdr_have_ = 0;
}

std::size_t FrameReader::feed(const std::uint8_t* data, std::size_t len) {
  std::size_t taken = 0;
  while (len > 0 && fatal_ == FatalReason::None) {
    if (!in_payload_) {
      const std::size_t need = kHeaderSize - hdr_have_;
      const std::size_t take = len < need ? len : need;
      std::memcpy(hdr_ + hdr_have_, data, take);
      hdr_have_ += take;
      data += take;
      len -= take;
      taken += take;
      if (hdr_have_ < kHeaderSize) break;
      const HeaderError e = decode_header(hdr_, kHeaderSize, cur_);
      if (e == HeaderError::BadMagic) { fatal_ = FatalReason::BadMagic; break; }
      if (e != HeaderError::Ok) { fatal_ = FatalReason::BadMajor; break; }
      if (cur_.payload_len > max_payload_) { fatal_ = FatalReason::PayloadTooLarge; break; }
      in_payload_ = true;
      payload_.clear();
      if (cur_.payload_len == 0) { complete_frame(); continue; }
      payload_.reserve(cur_.payload_len);
    } else {
      const std::size_t need = cur_.payload_len - payload_.size();
      const std::size_t take = len < need ? len : need;
      payload_.insert(payload_.end(), data, data + take);
      data += take;
      len -= take;
      taken += take;
      if (payload_.size() == cur_.payload_len) complete_frame();
    }
  }
  consumed_ += taken;
  return taken;
}

void FrameReader::end_of_input() noexcept {
  eof_ = true;
  if (fatal_ != FatalReason::None) return;
  if (hdr_have_ != 0 || in_payload_) fatal_ = FatalReason::Truncated;
}

ReadStatus FrameReader::read(int fd) {
  if (fatal_ != FatalReason::None) return ReadStatus::Fatal;
  if (eof_) return ReadStatus::Eof;
  if (rdbuf_.empty()) rdbuf_.resize(kReadChunk);
  for (;;) {
    const ssize_t n = ::read(fd, rdbuf_.data(), rdbuf_.size());
    if (n < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == EWOULDBLOCK) return ReadStatus::WouldBlock;
      errno_ = errno;
      fatal_ = FatalReason::ReadError;
      return ReadStatus::Error;
    }
    if (n == 0) {
      end_of_input();
      return fatal_ != FatalReason::None ? ReadStatus::Fatal : ReadStatus::Eof;
    }
    feed(rdbuf_.data(), static_cast<std::size_t>(n));
    return fatal_ != FatalReason::None ? ReadStatus::Fatal : ReadStatus::Progress;
  }
}

bool FrameReader::next(Frame& out) {
  if (ready_.empty()) return false;
  out = std::move(ready_.front());
  ready_.pop_front();
  return true;
}

// ---- messages --------------------------------------------------------------

std::string_view Message::json() const noexcept {
  for (const Frame& f : parts) {
    if (!f.header.raw()) return f.payload_view();
  }
  return {};
}

std::size_t Message::raw_size() const noexcept {
  std::size_t n = 0;
  for (const Frame& f : parts) {
    if (f.header.raw()) n += f.payload.size();
  }
  return n;
}

void Message::copy_raw(std::vector<std::uint8_t>& out) const {
  out.clear();
  out.reserve(raw_size());
  for (const Frame& f : parts) {
    if (f.header.raw()) out.insert(out.end(), f.payload.begin(), f.payload.end());
  }
}

void MessageAssembler::reset() noexcept {
  msg_.parts.clear();
  msg_.total_bytes = 0;
  msg_.kind = 0;
  msg_.request_id = 0;
  in_progress_ = false;
  complete_ = false;
}

AssembleStatus MessageAssembler::push(Frame&& f) {
  if (complete_) reset();  // caller forgot take(); start over
  if (!in_progress_) {
    msg_.kind = f.header.kind;
    msg_.request_id = f.header.request_id;
    msg_.total_bytes = 0;
    msg_.parts.clear();
  } else if (f.header.kind != msg_.kind || f.header.request_id != msg_.request_id) {
    reset();
    return AssembleStatus::Interleaved;
  }
  if (f.payload.size() > max_total_ || msg_.total_bytes + f.payload.size() > max_total_) {
    reset();
    return AssembleStatus::CapExceeded;
  }
  if (msg_.parts.size() >= max_parts_) {
    reset();
    return AssembleStatus::TooManyParts;
  }
  const bool more = f.header.more();
  msg_.total_bytes += f.payload.size();
  msg_.parts.push_back(std::move(f));
  if (more) {
    in_progress_ = true;
    return AssembleStatus::NeedMore;
  }
  in_progress_ = false;
  complete_ = true;
  return AssembleStatus::Complete;
}

Message MessageAssembler::take() {
  Message m = std::move(msg_);
  msg_ = Message();
  in_progress_ = false;
  complete_ = false;
  return m;
}

// ---- hello -----------------------------------------------------------------

std::string make_hello(const HelloInfo& info) {
  json::Value v = json::Value::object();
  json::Value proto = json::Value::object();
  proto.set("major", static_cast<int>(info.major));
  proto.set("minor", static_cast<int>(info.minor));
  v.set("protocol", std::move(proto));
  v.set("max_frame", static_cast<unsigned long long>(info.max_frame));
  v.set("max_image_bytes", static_cast<unsigned long long>(info.max_image_bytes));
  json::Value caps = json::Value::array();
  for (const std::string& c : info.capabilities) caps.push(c);
  v.set("capabilities", std::move(caps));
  json::Value engine = json::Value::object();
  engine.set("source", info.engine_source);
  engine.set("abi", info.engine_abi);
  v.set("engine", std::move(engine));
  return v.dump();
}

bool parse_hello(std::string_view text, HelloInfo& out, std::string* error) {
  auto fail = [&](const char* m) {
    if (error) *error = m;
    return false;
  };
  json::Value v;
  json::ParseError pe;
  json::ParseOptions opt;
  opt.max_bytes = kPreHandshakeMaxFrame;
  if (!json::parse(text, v, &pe, opt)) {
    if (error) *error = std::string("hello is not valid JSON: ") + pe.message;
    return false;
  }
  if (!v.is_object()) return fail("hello is not a JSON object");
  const json::Value* proto = v.get_object("protocol");
  if (!proto) return fail("hello lacks \"protocol\"");
  std::int64_t major = 0, minor = 0;
  if (!proto->get_int("major", major) || major < 0 || major > 255) return fail("bad protocol.major");
  if (!proto->get_int("minor", minor) || minor < 0 || minor > 255) return fail("bad protocol.minor");
  HelloInfo h;
  h.major = static_cast<std::uint8_t>(major);
  h.minor = static_cast<std::uint8_t>(minor);
  std::uint64_t u = 0;
  if (v.has("max_frame")) {
    if (!v.get_uint("max_frame", u) || u > 0xFFFFFFFFu) return fail("bad max_frame");
    h.max_frame = static_cast<std::uint32_t>(u);
  }
  if (v.has("max_image_bytes")) {
    if (!v.get_uint("max_image_bytes", u)) return fail("bad max_image_bytes");
    h.max_image_bytes = u;
  }
  if (const json::Value* caps = v.get("capabilities")) {
    if (!caps->is_array()) return fail("capabilities is not an array");
    for (const json::Value& c : caps->items()) {
      if (!c.is_string()) return fail("capability is not a string");
      h.capabilities.push_back(c.as_string());
    }
  }
  if (const json::Value* eng = v.get("engine")) {
    if (!eng->is_object()) return fail("engine is not an object");
    eng->get_string("source", h.engine_source);
    eng->get_string("abi", h.engine_abi);
  }
  out = std::move(h);
  return true;
}

Negotiated negotiate(const HelloInfo& local, const HelloInfo& remote) {
  Negotiated n;
  if (local.major != remote.major) {
    n.error = "protocol major mismatch: local " + std::to_string(local.major) + ", remote " +
              std::to_string(remote.major);
    return n;
  }
  n.major = local.major;
  n.minor = local.minor < remote.minor ? local.minor : remote.minor;
  n.max_frame = local.max_frame < remote.max_frame ? local.max_frame : remote.max_frame;
  n.max_image_bytes =
      local.max_image_bytes < remote.max_image_bytes ? local.max_image_bytes : remote.max_image_bytes;
  if (n.max_frame < kPreHandshakeMaxFrame) {
    n.error = "negotiated max_frame " + std::to_string(n.max_frame) + " is below the 64 KiB minimum";
    return n;
  }
  n.ok = true;
  return n;
}

// ---- errors ----------------------------------------------------------------

std::string make_error(ErrorCode code, std::string_view message, int status) {
  json::Value v = json::Value::object();
  v.set("code", error_code_name(code));
  v.set("message", std::string(message));
  v.set("status", status);
  return v.dump();
}

std::string make_unsupported_kind(std::uint16_t kind) {
  json::Value v = json::Value::object();
  v.set("code", "unsupported_kind");
  v.set("kind", static_cast<int>(kind));
  v.set("message", std::string("unsupported frame kind ") + std::to_string(kind));
  v.set("status", 0);
  return v.dump();
}

// ---- hex -------------------------------------------------------------------

std::string format_hex(std::uint64_t v) {
  char buf[2 + 16 + 1];
  buf[0] = '0';
  buf[1] = 'x';
  const auto r = std::to_chars(buf + 2, buf + sizeof buf, v, 16);
  return std::string(buf, static_cast<std::size_t>(r.ptr - buf));
}

bool parse_hex(std::string_view s, std::uint64_t& out) noexcept {
  if (s.size() >= 2 && s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) s.remove_prefix(2);
  if (s.empty() || s.size() > 16) return false;
  std::uint64_t v = 0;
  const auto r = std::from_chars(s.data(), s.data() + s.size(), v, 16);
  if (r.ec != std::errc{} || r.ptr != s.data() + s.size()) return false;
  out = v;
  return true;
}

}  // namespace gnsdk::proto
