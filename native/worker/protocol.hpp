// protocol.hpp - gnsdk local worker protocol, version 1.0.  FROZEN CONTRACT.
//
// This header is the wire contract between the pool supervisor (native/pool) and
// a worker process (gnsdk-worker, or tools/fake_worker for fault injection).
// Changing anything under "Wire format" is a protocol version bump.
//
// ---------------------------------------------------------------------------
// Wire format
// ---------------------------------------------------------------------------
// Every frame is a 24-byte little-endian header followed by payload_len bytes:
//
//   offset size field         notes
//   0      4    magic         0x4B534E47; bytes on the wire are 'G','N','S','K'
//   4      1    major         1
//   5      1    minor         0 (sender's minor; receivers ignore it after HELLO)
//   6      2    kind          see Kind
//   8      4    flags         bit0 MORE: more frames of this message follow
//                             bit1 RAW_PAYLOAD: payload is raw bytes, not JSON
//                             unknown bits are ignored by receivers
//   12     4    payload_len   bytes following the header
//   16     8    request_id    0 is reserved for connection-level frames
//                             (HELLO, HELLO_ACK, PING, PONG, BYE)
//
// A *message* is one frame without MORE, or a contiguous run of frames that
// share kind and request_id where all but the last carry MORE. Frames of two
// messages never interleave on one connection.
//
// Kinds (u16). supervisor -> worker:
//   HELLO=1 HELLO_ACK=2(worker->supervisor) OPEN_RAW=3 OPEN_SNAPSHOT=4 DISASM=5
//   LIFT=6 DECOMPILE=7 CLOSE_SESSION=8 CANCEL=9 PING=10 BYE=11
// worker -> supervisor:
//   RESULT=100 ERROR=101 PROGRESS=102 PONG=103
//
// Handshake: the supervisor sends HELLO, the worker answers HELLO_ACK. Both
// payloads are JSON:
//   {"protocol":{"major":1,"minor":0},"max_frame":67108864,
//    "max_image_bytes":536870912,"capabilities":["decompile","lift",...],
//    "engine":{"source":"ghidra-12.1.3","abi":"0.1.0"}}
// Equal major is required; effective minor = min(minor); effective max_frame =
// min(max_frame) and each side enforces it on receive. Before HELLO_ACK the
// receive limit is kPreHandshakeMaxFrame (64 KiB). max_image_bytes is likewise
// min()ed and bounds the concatenated RAW payload of one OPEN_RAW message.
//
// Fatal conditions (the receiver stops reading; a supervisor kills and respawns
// the worker; a worker exits 2): bad magic, wrong major in a header,
// payload_len over the current limit, or EOF inside a header or payload.
// Non-fatal protocol errors get an ERROR reply with code "protocol"; an unknown
// kind gets ERROR {"code":"unsupported_kind","kind":N}.
//
// Request payloads (JSON unless noted; addresses are "0x..." hex strings):
//   OPEN_RAW      {"language":"x86:LE:64:default","base":"0x401000",
//                  "length":N,"readonly":true}            with MORE set, then
//                 one or more RAW_PAYLOAD frames carrying the image bytes
//                 (the last without MORE). Reply RESULT {"status":"ok"}.
//   OPEN_SNAPSHOT {"path":"/dir/of/manifest.json"}
//   DISASM        {"start":"0x..","end":"0x..","max_instructions":N,"deadline_ms":N}
//   LIFT          same as DISASM
//   DECOMPILE     {"addr":"0x..","name":null|"..","tokens":false,
//                  "deadline_ms":N,"printer":"c"}
//   CLOSE_SESSION {}            CANCEL {}   (cancels a not-yet-started request
//                 with the same request_id; in-flight cancel is SIGUSR1)
//   PING / BYE    empty payload or {}
//
// Reply payloads:
//   RESULT (decompile) {"status":"ok|warnings|partial","c":"...",
//                       "tokens":null|"...","warnings":[...],"elapsed_ms":N}
//   RESULT (lift)      JSON header {"num_ops":N,"num_varnodes":N,"num_instrs":N,
//                       "spaces":["ram","register",...]} with MORE, then ONE
//                       RAW_PAYLOAD frame: ops[num_ops] || varnodes[num_varnodes]
//                       || instrs[num_instrs], packed little-endian with the
//                       layouts of PcodeOpWire / VarnodeWire / InstrWire below
//                       (32 / 16 / 24 bytes each, no padding between arrays).
//   RESULT (disasm)    {"instructions":[{"addr":"0x..","length":N,
//                       "mnemonic":"..","text":".."}],"elapsed_ms":N}
//   ERROR              {"code":"busy|invalid_argument|provider_failure|
//                       engine_failure|resource|cancelled|timeout|unsupported|
//                       protocol|unsupported_kind","message":"...","status":N}
//   PROGRESS           optional, {"pct":N}; PONG empty or {}
//
// Signals: SIGUSR1 = cancel the in-flight request (worker replies ERROR
// cancelled). SIGTERM = cancel, finish the reply, exit 0. The worker's stderr
// is diagnostics only and never carries protocol bytes.
//
// ---------------------------------------------------------------------------
// Threading: every class here is single-threaded. A FrameReader and a
// FrameWriter on different fds may live on different threads; one object must
// never be touched by two threads at once. Nothing here throws except for
// std::bad_alloc from payload vectors.
// ---------------------------------------------------------------------------
#pragma once

#include <bit>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>
#include <string_view>
#include <vector>

namespace gnsdk::proto {

// ---- constants -------------------------------------------------------------
inline constexpr std::uint32_t kMagic = 0x4B534E47u;  // 'G','N','S','K' on the wire
inline constexpr std::uint8_t kProtocolMajor = 1;
inline constexpr std::uint8_t kProtocolMinor = 0;
inline constexpr std::size_t kHeaderSize = 24;
inline constexpr std::uint32_t kFlagMore = 0x1u;
inline constexpr std::uint32_t kFlagRawPayload = 0x2u;
inline constexpr std::uint32_t kKnownFlags = kFlagMore | kFlagRawPayload;
inline constexpr std::uint32_t kPreHandshakeMaxFrame = 64u * 1024u;          // 64 KiB
inline constexpr std::uint32_t kDefaultMaxFrame = 64u * 1024u * 1024u;       // 64 MiB
inline constexpr std::uint64_t kDefaultMaxImageBytes = 512ull * 1024 * 1024;  // 512 MiB
inline constexpr std::uint64_t kConnectionRequestId = 0;

static_assert(std::endian::native == std::endian::little,
              "gnsdk protocol code assumes a little-endian host");

enum class Kind : std::uint16_t {
  Hello = 1,
  HelloAck = 2,
  OpenRaw = 3,
  OpenSnapshot = 4,
  Disasm = 5,
  Lift = 6,
  Decompile = 7,
  CloseSession = 8,
  Cancel = 9,
  Ping = 10,
  Bye = 11,
  Result = 100,
  Error = 101,
  Progress = 102,
  Pong = 103,
};

constexpr std::uint16_t to_u16(Kind k) { return static_cast<std::uint16_t>(k); }
constexpr bool is_request_kind(std::uint16_t k) { return k >= 1 && k <= 11 && k != 2; }
constexpr bool is_reply_kind(std::uint16_t k) { return k == 2 || (k >= 100 && k <= 103); }
constexpr bool is_known_kind(std::uint16_t k) { return is_request_kind(k) || is_reply_kind(k); }
// Kinds that must use request_id 0.
constexpr bool is_connection_kind(std::uint16_t k) { return k == 1 || k == 2 || k == 10 || k == 11 || k == 103; }
const char* kind_name(std::uint16_t k) noexcept;  // "HELLO", ..., "?" for unknown

// ---- header ----------------------------------------------------------------
struct FrameHeader {
  std::uint8_t major = kProtocolMajor;
  std::uint8_t minor = kProtocolMinor;
  std::uint16_t kind = 0;
  std::uint32_t flags = 0;
  std::uint32_t payload_len = 0;
  std::uint64_t request_id = 0;

  bool more() const { return (flags & kFlagMore) != 0; }
  bool raw() const { return (flags & kFlagRawPayload) != 0; }
};

enum class HeaderError : std::uint8_t { Ok = 0, ShortBuffer, BadMagic, BadMajor };
const char* header_error_name(HeaderError e) noexcept;

// Serializes `h` (magic added) into 24 bytes. Never allocates, never fails.
void encode_header(const FrameHeader& h, std::uint8_t (&out)[kHeaderSize]) noexcept;
// Parses 24 bytes. Checks magic and major only; payload_len limits are the
// reader's job. Never allocates, never throws.
HeaderError decode_header(const std::uint8_t* buf, std::size_t len, FrameHeader& out) noexcept;

// ---- frames ----------------------------------------------------------------
struct Frame {
  FrameHeader header;
  std::vector<std::uint8_t> payload;

  std::string_view payload_view() const {
    return {reinterpret_cast<const char*>(payload.data()), payload.size()};
  }
};

// Blocking writer over a file descriptor. Handles partial writes and EINTR;
// on EAGAIN it poll()s for writability so it also works on non-blocking fds.
// Returns false on any error (last_errno() tells which); EPIPE is the usual
// "peer is gone". Never throws.
class FrameWriter {
 public:
  explicit FrameWriter(int fd) noexcept : fd_(fd) {}

  bool write_frame(const FrameHeader& h, const void* payload, std::size_t len) noexcept;
  bool write_json(Kind kind, std::uint64_t request_id, std::string_view json,
                  std::uint32_t flags = 0) noexcept;
  bool write_raw(Kind kind, std::uint64_t request_id, const void* data, std::size_t len,
                 std::uint32_t flags = 0) noexcept;  // RAW_PAYLOAD is OR'ed in
  bool write_empty(Kind kind, std::uint64_t request_id = 0) noexcept;

  // Optional send-side cap (the peer's negotiated max_frame). 0 = no cap
  // beyond the u32 payload_len field.
  void set_max_payload(std::size_t n) noexcept { max_payload_ = n; }
  int last_errno() const noexcept { return errno_; }
  int fd() const noexcept { return fd_; }

 private:
  int fd_;
  int errno_ = 0;
  std::size_t max_payload_ = 0;
};

enum class FatalReason : std::uint8_t {
  None = 0,
  BadMagic,
  BadMajor,
  PayloadTooLarge,
  Truncated,   // EOF inside a header or payload
  ReadError,   // read(2) failed with something other than EINTR/EAGAIN
};
const char* fatal_reason_name(FatalReason r) noexcept;

enum class ReadStatus : std::uint8_t {
  Progress,    // consumed some bytes (frames may be ready)
  WouldBlock,  // non-blocking fd has nothing yet
  Eof,         // clean EOF on a frame boundary
  Error,       // read(2) failed; reader is now fatal
  Fatal,       // protocol violation; reader is now fatal
};

// Incremental frame decoder. Feed it bytes (feed()) or let it read from an fd
// (read()); pop complete frames with next(). Header bytes are accumulated in a
// fixed member buffer (no allocation); payloads are std::vector<uint8_t> sized
// at most max_payload(). Once fatal() is true it stays true and no further
// bytes are consumed.
class FrameReader {
 public:
  explicit FrameReader(std::size_t max_payload = kPreHandshakeMaxFrame);

  // Raise/lower the payload limit (after HELLO negotiation). Applies to the
  // next header decoded; a frame already in flight keeps its accepted size.
  void set_max_payload(std::size_t n) noexcept { max_payload_ = n; }
  std::size_t max_payload() const noexcept { return max_payload_; }

  // Consumes bytes; returns how many were taken (< len only once fatal).
  std::size_t feed(const std::uint8_t* data, std::size_t len);
  // One read(2) into an internal buffer, then feed(). EINTR is retried.
  ReadStatus read(int fd);
  // Declares EOF for feed()-driven use: partial header/payload -> Truncated.
  void end_of_input() noexcept;

  bool has_frame() const noexcept { return !ready_.empty(); }
  std::size_t pending_frames() const noexcept { return ready_.size(); }
  bool next(Frame& out);  // false if nothing complete

  bool fatal() const noexcept { return fatal_ != FatalReason::None; }
  FatalReason fatal_reason() const noexcept { return fatal_; }
  bool eof() const noexcept { return eof_; }
  int last_errno() const noexcept { return errno_; }
  std::size_t bytes_consumed() const noexcept { return consumed_; }
  // Header of the frame whose payload is being collected (valid while
  // in_payload()); useful for diagnostics of oversize/truncated frames.
  bool in_payload() const noexcept { return in_payload_; }
  const FrameHeader& current_header() const noexcept { return cur_; }
  std::size_t header_bytes_pending() const noexcept { return hdr_have_; }

 private:
  void complete_frame();

  std::size_t max_payload_;
  std::uint8_t hdr_[kHeaderSize] = {};
  std::size_t hdr_have_ = 0;
  bool in_payload_ = false;
  FrameHeader cur_{};
  std::vector<std::uint8_t> payload_;
  std::deque<Frame> ready_;
  std::vector<std::uint8_t> rdbuf_;
  FatalReason fatal_ = FatalReason::None;
  bool eof_ = false;
  int errno_ = 0;
  std::size_t consumed_ = 0;
};

// ---- messages (MORE sequences) --------------------------------------------
struct Message {
  std::uint16_t kind = 0;
  std::uint64_t request_id = 0;
  std::vector<Frame> parts;
  std::size_t total_bytes = 0;  // sum of part payload sizes

  // Payload of the first non-RAW part, or empty.
  std::string_view json() const noexcept;
  // Concatenated RAW parts.
  std::size_t raw_size() const noexcept;
  void copy_raw(std::vector<std::uint8_t>& out) const;
};

enum class AssembleStatus : std::uint8_t {
  NeedMore,      // frame accepted, message incomplete
  Complete,      // message complete; call take()
  CapExceeded,   // total bytes would pass the cap; partial message dropped
  Interleaved,   // kind/request_id changed mid-message; partial message dropped
  TooManyParts,  // part count cap; partial message dropped
};
const char* assemble_status_name(AssembleStatus s) noexcept;

class MessageAssembler {
 public:
  explicit MessageAssembler(std::size_t max_total_bytes, std::size_t max_parts = 4096) noexcept
      : max_total_(max_total_bytes), max_parts_(max_parts) {}

  void set_max_total_bytes(std::size_t n) noexcept { max_total_ = n; }
  AssembleStatus push(Frame&& f);
  bool in_progress() const noexcept { return in_progress_; }
  bool complete() const noexcept { return complete_; }
  Message take();  // valid after Complete; resets the assembler
  void reset() noexcept;

 private:
  std::size_t max_total_;
  std::size_t max_parts_;
  Message msg_;
  bool in_progress_ = false;
  bool complete_ = false;
};

// ---- HELLO / HELLO_ACK -----------------------------------------------------
struct HelloInfo {
  std::uint8_t major = kProtocolMajor;
  std::uint8_t minor = kProtocolMinor;
  std::uint32_t max_frame = kDefaultMaxFrame;
  std::uint64_t max_image_bytes = kDefaultMaxImageBytes;
  std::vector<std::string> capabilities;
  std::string engine_source;
  std::string engine_abi = "0.1.0";
  std::uint32_t engine_sig_major = 0;
  std::uint32_t engine_sig_minor = 0;
};

std::string make_hello(const HelloInfo& info);
// Requires protocol.major/minor; max_frame and max_image_bytes default when
// absent; capabilities and engine are optional.
bool parse_hello(std::string_view json, HelloInfo& out, std::string* error = nullptr);

struct Negotiated {
  bool ok = false;
  std::uint8_t major = 0;
  std::uint8_t minor = 0;
  std::uint32_t max_frame = 0;
  std::uint64_t max_image_bytes = 0;
  std::string error;  // set when !ok
};
// Equal major required; minor/max_frame/max_image_bytes = min(); fails if the
// resulting max_frame is below kPreHandshakeMaxFrame.
Negotiated negotiate(const HelloInfo& local, const HelloInfo& remote);

// ---- ERROR helpers ---------------------------------------------------------
enum class ErrorCode : std::uint8_t {
  Busy,
  InvalidArgument,
  ProviderFailure,
  EngineFailure,
  Resource,
  Cancelled,
  Timeout,
  Unsupported,
  Protocol,
};
const char* error_code_name(ErrorCode c) noexcept;
std::string make_error(ErrorCode code, std::string_view message, int status = 0);
std::string make_unsupported_kind(std::uint16_t kind);

// ---- hex addresses ---------------------------------------------------------
std::string format_hex(std::uint64_t v);                          // "0x1a2b"
bool parse_hex(std::string_view s, std::uint64_t& out) noexcept;  // accepts optional 0x

// ---- LIFT raw payload layout ----------------------------------------------
// The RAW frame of a LIFT result is ops || varnodes || instrs, little-endian,
// each array tightly packed with the struct sizes asserted below. Indices are
// into the varnode array; kNoIndex means "none" (op without output).
inline constexpr std::uint32_t kNoIndex = 0xFFFFFFFFu;

struct PcodeOpWire {
  std::uint32_t opcode;        // ghidra OpCode value
  std::uint32_t flags;         // reserved, 0
  std::uint32_t output_index;  // varnode index or kNoIndex
  std::uint32_t first_input;   // index of first input varnode
  std::uint32_t num_inputs;
  std::uint32_t pad;           // 0
  std::uint64_t instr_addr;    // address of the owning instruction
};
struct VarnodeWire {
  std::uint32_t space;   // index into the header's "spaces" array
  std::uint32_t size;
  std::uint64_t offset;
};
struct InstrWire {
  std::uint64_t addr;
  std::uint32_t length;
  std::uint32_t first_op;  // index into ops
  std::uint32_t num_ops;
  std::uint32_t pad;       // 0
};
static_assert(sizeof(PcodeOpWire) == 32 && alignof(PcodeOpWire) == 8);
static_assert(sizeof(VarnodeWire) == 16 && alignof(VarnodeWire) == 8);
static_assert(sizeof(InstrWire) == 24 && alignof(InstrWire) == 8);
static_assert(offsetof(PcodeOpWire, instr_addr) == 24);
static_assert(offsetof(VarnodeWire, offset) == 8);
static_assert(offsetof(InstrWire, pad) == 20);

}  // namespace gnsdk::proto
