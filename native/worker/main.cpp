#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

#include <sys/prctl.h>
#include <sys/resource.h>
#include <unistd.h>

#include "gnsdk/gnsdk.h"
#include "worker/json_min.hpp"
#include "worker/protocol.hpp"

namespace proto = gnsdk::proto;
namespace json = gnsdk::json;

namespace {

gnsdk_session* g_session = nullptr;
volatile std::sig_atomic_t g_terminating = 0;

void on_cancel(int) { if (g_session != nullptr) gnsdk_session_cancel(g_session); }
void on_term(int) { g_terminating = 1; on_cancel(0); }

proto::ErrorCode error_code(gnsdk_status status) {
  switch (status) {
    case GNSDK_BUSY: return proto::ErrorCode::Busy;
    case GNSDK_INVALID_ARGUMENT: return proto::ErrorCode::InvalidArgument;
    case GNSDK_PROVIDER_FAILURE: return proto::ErrorCode::ProviderFailure;
    case GNSDK_RESOURCE_LIMITED: return proto::ErrorCode::Resource;
    case GNSDK_CANCELLED: return proto::ErrorCode::Cancelled;
    case GNSDK_TIMEOUT: return proto::ErrorCode::Timeout;
    default: return proto::ErrorCode::EngineFailure;
  }
}

bool number(const json::Value& value, std::string_view key, std::uint64_t& out) {
  std::string text;
  if (value.get_string(key, text)) return proto::parse_hex(text, out);
  std::int64_t integer = 0;
  if (!value.get_int(key, integer) || integer < 0) return false;
  out = static_cast<std::uint64_t>(integer);
  return true;
}

bool range_request(const proto::Message& message, gnsdk_range& range,
                   gnsdk_request_options& options, json::Value& request) {
  std::uint64_t start = 0;
  std::uint64_t end = 0;
  if (!json::parse(message.json(), request) || !number(request, "start", start) ||
      !number(request, "end", end) || end < start) return false;
  GNSDK_INIT_STRUCT(&options);
  std::int64_t integer = 0;
  if (request.get_int("deadline_ms", integer) && integer > 0)
    options.deadline_ms = static_cast<std::uint64_t>(integer);
  if (request.get_int("max_instructions", integer) && integer > 0 &&
      static_cast<std::uint64_t>(integer) <= std::numeric_limits<std::uint32_t>::max())
    options.max_instructions = static_cast<std::uint32_t>(integer);
  range = {start, end};
  return true;
}

bool parse_limit(const char* text, rlim_t& out) {
  if (text == nullptr || *text == '\0') return false;
  char* end = nullptr;
  errno = 0;
  const unsigned long long value = std::strtoull(text, &end, 10);
  if (errno != 0 || end == text || *end != '\0' || value > static_cast<unsigned long long>(RLIM_INFINITY)) return false;
  out = static_cast<rlim_t>(value);
  return true;
}

bool set_limit(int resource, rlim_t value) {
  if (value == 0) return true;
  const rlimit limit{value, value};
  return ::setrlimit(resource, &limit) == 0;
}

struct Worker {
  proto::FrameReader reader{proto::kPreHandshakeMaxFrame};
  proto::MessageAssembler assembler{proto::kDefaultMaxImageBytes + proto::kDefaultMaxFrame};
  proto::FrameWriter writer{1};
  proto::HelloInfo local;
  bool handshaken = false;
  int exit_after_reply = 0;

  Worker() {
    local.capabilities = {"open_raw", "open_snapshot", "disasm", "lift", "decompile", "cancel"};
    gnsdk_version_info version{};
    GNSDK_INIT_STRUCT(&version);
    (void)gnsdk_version(&version);
    local.engine_source = version.source;
  }

  bool reply_error(std::uint64_t id, gnsdk_status status, std::string_view message) {
    return writer.write_json(proto::Kind::Error, id, proto::make_error(error_code(status), message, status));
  }

  bool hello(const proto::Message& message) {
    proto::HelloInfo peer;
    std::string error;
    if (!proto::parse_hello(message.json(), peer, &error)) return reply_error(0, GNSDK_INVALID_ARGUMENT, error);
    const proto::Negotiated negotiated = proto::negotiate(local, peer);
    if (!negotiated.ok) return reply_error(0, GNSDK_INVALID_ARGUMENT, negotiated.error);
    reader.set_max_payload(negotiated.max_frame);
    writer.set_max_payload(negotiated.max_frame);
    assembler.set_max_total_bytes(static_cast<std::size_t>(negotiated.max_image_bytes) + negotiated.max_frame);
    handshaken = true;
    return writer.write_json(proto::Kind::HelloAck, 0, proto::make_hello(local));
  }

  bool open_raw(const proto::Message& message) {
    json::Value request;
    std::string language;
    std::uint64_t base = 0;
    std::uint64_t length = 0;
    if (!json::parse(message.json(), request) || !request.get_string("language", language) ||
        !number(request, "base", base) || !number(request, "length", length) || length != message.raw_size() || length == 0) {
      return reply_error(message.request_id, GNSDK_INVALID_ARGUMENT, "invalid OPEN_RAW request");
    }
    if (g_session != nullptr) { gnsdk_session_destroy(g_session); g_session = nullptr; }
    gnsdk_session_options options{};
    GNSDK_INIT_STRUCT(&options);
    options.language_id = language.c_str();
    gnsdk_status status = gnsdk_session_create(&options, &g_session);
    if (status != GNSDK_OK) return reply_error(message.request_id, status, gnsdk_status_name(status));
    std::vector<std::uint8_t> image;
    message.copy_raw(image);
    gnsdk_image_desc descriptor{};
    GNSDK_INIT_STRUCT(&descriptor);
    descriptor.bytes = image.data(); descriptor.len = image.size(); descriptor.base = base; descriptor.name = "worker-image";
    status = gnsdk_session_load_image(g_session, &descriptor);
    if (status != GNSDK_OK) {
      if (status == GNSDK_RESOURCE_LIMITED) exit_after_reply = 4;
      return reply_error(message.request_id, status, gnsdk_status_name(status));
    }
    return writer.write_json(proto::Kind::Result, message.request_id, R"({"status":"ok"})");
  }

  bool open_snapshot(const proto::Message& message) {
    json::Value request;
    std::string path;
    if (!json::parse(message.json(), request) || !request.get_string("path", path) || path.empty())
      return reply_error(message.request_id, GNSDK_INVALID_ARGUMENT, "invalid OPEN_SNAPSHOT request");
    if (g_session != nullptr) { gnsdk_session_destroy(g_session); g_session = nullptr; }
    gnsdk_session_options options{};
    GNSDK_INIT_STRUCT(&options);
    const gnsdk_status status = gnsdk_session_open_snapshot(&options, path.c_str(), &g_session);
    if (status != GNSDK_OK) {
      if (status == GNSDK_RESOURCE_LIMITED) exit_after_reply = 4;
      return reply_error(message.request_id, status, gnsdk_status_name(status));
    }
    return writer.write_json(proto::Kind::Result, message.request_id, R"({"status":"ok"})");
  }

  bool disassemble(const proto::Message& message) {
    json::Value request;
    gnsdk_range range{};
    gnsdk_request_options options{};
    if (g_session == nullptr || !range_request(message, range, options, request))
      return reply_error(message.request_id, GNSDK_INVALID_ARGUMENT, "invalid DISASM request");
    gnsdk_buf text{};
    const gnsdk_status status = gnsdk_disassemble(g_session, &range, &options, &text);
    if (status != GNSDK_OK && status != GNSDK_PARTIAL_UNSUPPORTED) {
      if (status == GNSDK_RESOURCE_LIMITED) exit_after_reply = 4;
      return reply_error(message.request_id, status, gnsdk_status_name(status));
    }
    json::Value result = json::Value::object();
    json::Value instructions = json::Value::array();
    std::string_view lines(reinterpret_cast<const char*>(text.data), text.len);
    std::size_t begin = 0;
    while (begin < lines.size()) {
      const std::size_t end = lines.find('\n', begin);
      const std::string_view line = lines.substr(begin, end == std::string_view::npos ? lines.size() - begin : end - begin);
      const std::size_t a = line.find('\t');
      const std::size_t b = a == std::string_view::npos ? a : line.find('\t', a + 1);
      if (a != std::string_view::npos && b != std::string_view::npos) {
        json::Value item = json::Value::object();
        item.set("addr", std::string(line.substr(0, a)));
        item.set("mnemonic", std::string(line.substr(a + 1, b - a - 1)));
        item.set("text", std::string(line.substr(b + 1)));
        instructions.push(std::move(item));
      }
      if (end == std::string_view::npos) break;
      begin = end + 1;
    }
    gnsdk_buf_free(&text);
    result.set("instructions", std::move(instructions));
    result.set("elapsed_ms", 0);
    return writer.write_json(proto::Kind::Result, message.request_id, result.dump());
  }

  bool lift(const proto::Message& message) {
    json::Value request;
    gnsdk_range range{};
    gnsdk_request_options options{};
    if (g_session == nullptr || !range_request(message, range, options, request))
      return reply_error(message.request_id, GNSDK_INVALID_ARGUMENT, "invalid LIFT request");
    gnsdk_pcode_out output{};
    GNSDK_INIT_STRUCT(&output);
    const gnsdk_status status = gnsdk_lift(g_session, &range, &options, &output);
    if (status != GNSDK_OK && status != GNSDK_PARTIAL_UNSUPPORTED) {
      if (status == GNSDK_RESOURCE_LIMITED) exit_after_reply = 4;
      return reply_error(message.request_id, status, gnsdk_status_name(status));
    }
    json::Value header = json::Value::object();
    header.set("num_ops", static_cast<long long>(output.num_ops));
    header.set("num_varnodes", static_cast<long long>(output.num_varnodes));
    header.set("num_instrs", static_cast<long long>(output.num_instrs));
    json::Value spaces = json::Value::array();
    for (std::uint32_t i = 0; i < output.num_spaces; ++i) spaces.push(output.space_names[i]);
    header.set("spaces", std::move(spaces));
    std::vector<std::uint8_t> raw;
    raw.reserve(static_cast<std::size_t>(output.num_ops) * sizeof(proto::PcodeOpWire) +
                static_cast<std::size_t>(output.num_varnodes) * sizeof(proto::VarnodeWire) +
                static_cast<std::size_t>(output.num_instrs) * sizeof(proto::InstrWire));
    const auto append = [&raw](const void* data, std::size_t count, std::size_t size) {
      const auto* bytes = static_cast<const std::uint8_t*>(data);
      raw.insert(raw.end(), bytes, bytes + count * size);
    };
    for (std::uint32_t i = 0; i < output.num_ops; ++i) {
      const auto& in = output.ops[i];
      const proto::PcodeOpWire wire{in.opcode, 0u, in.output_index < 0 ? proto::kNoIndex : static_cast<std::uint32_t>(in.output_index), in.first_input, in.num_inputs, 0u, in.instr_addr};
      append(&wire, 1, sizeof wire);
    }
    for (std::uint32_t i = 0; i < output.num_varnodes; ++i) {
      const auto& in = output.varnodes[i]; const proto::VarnodeWire wire{in.space, in.size, in.offset}; append(&wire, 1, sizeof wire);
    }
    for (std::uint32_t i = 0; i < output.num_instrs; ++i) {
      const auto& in = output.instrs[i]; const proto::InstrWire wire{in.addr, in.length, in.first_op, in.num_ops, 0u}; append(&wire, 1, sizeof wire);
    }
    gnsdk_pcode_free(&output);
    return writer.write_json(proto::Kind::Result, message.request_id, header.dump(), proto::kFlagMore) &&
           writer.write_raw(proto::Kind::Result, message.request_id, raw.data(), raw.size());
  }

  bool decompile(const proto::Message& message) {
    json::Value request;
    std::uint64_t address = 0;
    if (g_session == nullptr || !json::parse(message.json(), request) || !number(request, "addr", address))
      return reply_error(message.request_id, GNSDK_INVALID_ARGUMENT, "invalid DECOMPILE request");
    gnsdk_decompile_options options{};
    GNSDK_INIT_STRUCT(&options);
    std::int64_t deadline = 0;
    (void)request.get_int("deadline_ms", deadline);
    options.deadline_ms = deadline > 0 ? static_cast<std::uint64_t>(deadline) : 0;
    bool tokens = false;
    (void)request.get_bool("tokens", tokens);
    options.want_tokens = tokens ? 1u : 0u;
    gnsdk_decompile_out output{};
    GNSDK_INIT_STRUCT(&output);
    const gnsdk_status status = gnsdk_decompile(g_session, address, &options, &output);
    json::Value result = json::Value::object();
    result.set("status", status == GNSDK_OK ? "ok" : status == GNSDK_OK_WARNINGS ? "warnings" : "partial");
    result.set("c", output.c_text.data ? reinterpret_cast<const char*>(output.c_text.data) : "");
    if (output.tokens.data) result.set("tokens", reinterpret_cast<const char*>(output.tokens.data)); else result.set("tokens", nullptr);
    result.set("warnings", json::Value::array());
    result.set("elapsed_ms", 0);
    gnsdk_buf_free(&output.c_text); gnsdk_buf_free(&output.tokens); gnsdk_buf_free(&output.warnings);
    if (status != GNSDK_OK && status != GNSDK_OK_WARNINGS && status != GNSDK_PARTIAL_UNSUPPORTED)
      return reply_error(message.request_id, status, gnsdk_status_name(status));
    return writer.write_json(proto::Kind::Result, message.request_id, result.dump());
  }

  bool dispatch(proto::Message&& message) {
    if (!handshaken && message.kind != proto::to_u16(proto::Kind::Hello)) return reply_error(message.request_id, GNSDK_INVALID_ARGUMENT, "HELLO required first");
    switch (static_cast<proto::Kind>(message.kind)) {
      case proto::Kind::Hello: return hello(message);
      case proto::Kind::Ping: return writer.write_empty(proto::Kind::Pong);
      case proto::Kind::Bye: return false;
      case proto::Kind::CloseSession:
        if (g_session != nullptr) { gnsdk_session_destroy(g_session); g_session = nullptr; }
        return writer.write_json(proto::Kind::Result, message.request_id, R"({"status":"ok"})");
      case proto::Kind::OpenRaw: return open_raw(message);
      case proto::Kind::OpenSnapshot: return open_snapshot(message);
      case proto::Kind::Disasm: return disassemble(message);
      case proto::Kind::Lift: return lift(message);
      case proto::Kind::Decompile: return decompile(message);
      case proto::Kind::Cancel: return reply_error(message.request_id, GNSDK_CANCELLED, "cancelled before start");
      default: return writer.write_json(proto::Kind::Error, message.request_id, proto::make_unsupported_kind(message.kind));
    }
  }

  int run() {
    for (;;) {
      proto::Frame frame;
      while (reader.next(frame)) {
        const auto state = assembler.push(std::move(frame));
        if (state == proto::AssembleStatus::Complete) {
          if (!dispatch(assembler.take())) return 0;
          if (exit_after_reply != 0) return exit_after_reply;
          if (g_terminating) return 0;
        } else if (state != proto::AssembleStatus::NeedMore) return 2;
      }
      const auto state = reader.read(0);
      if (state == proto::ReadStatus::Eof) return 0;
      if (state == proto::ReadStatus::Fatal || state == proto::ReadStatus::Error) return 2;
    }
  }
};

}  // namespace

int main(int argc, char** argv) {
  const char* sleigh_home = nullptr;
  rlim_t address_limit = 0;
  rlim_t cpu_limit = 0;
  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--sleigh-home") == 0 && i + 1 < argc) sleigh_home = argv[++i];
    else if (std::strcmp(argv[i], "--rlimit-as") == 0 && i + 1 < argc) {
      if (!parse_limit(argv[++i], address_limit)) return 64;
    } else if (std::strcmp(argv[i], "--rlimit-cpu") == 0 && i + 1 < argc) {
      if (!parse_limit(argv[++i], cpu_limit)) return 64;
    } else if (std::strcmp(argv[i], "--help") == 0) {
      std::puts("usage: gnsdk-worker --sleigh-home DIR [--rlimit-as BYTES] [--rlimit-cpu SECONDS]");
      return 0;
    } else return 64;
  }
  if (sleigh_home == nullptr) return 5;
  if (!set_limit(RLIMIT_AS, address_limit) || !set_limit(RLIMIT_CPU, cpu_limit)) return 4;
  std::signal(SIGPIPE, SIG_IGN);
  struct sigaction cancel{}; cancel.sa_handler = on_cancel; sigemptyset(&cancel.sa_mask); sigaction(SIGUSR1, &cancel, nullptr);
  struct sigaction term{}; term.sa_handler = on_term; sigemptyset(&term.sa_mask); sigaction(SIGTERM, &term, nullptr);
  if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0) return 5;
  gnsdk_init_options init{}; GNSDK_INIT_STRUCT(&init); init.sleigh_home = sleigh_home;
  if (gnsdk_init(&init) != GNSDK_OK) return 5;
  Worker worker;
  const int result = worker.run();
  if (g_session != nullptr) gnsdk_session_destroy(g_session);
  return result;
}
