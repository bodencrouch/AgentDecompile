// One session = one Architecture plus the state machine around it.
#pragma once

#include <cstdint>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "cancel_action.hpp"
#include "diagnostics.hpp"
#include "gnsdk/gnsdk.h"
#include "upstream.hpp"

namespace gnsdk {

struct PcodeStore;

// Failure injection for lifecycle_exception_paths (GNSDK_ENABLE_TEST_HOOKS).
enum class InjectKind : int { None = 0, BadAlloc = 1, Unknown = 2, Lowlevel = 3 };

class Session {
 public:
  using State = gnsdk_session_state;

  // Validates the language id against the loaded descriptions and returns
  // the fully qualified id ("proc:endian:size:variant:compiler"). Empty on
  // failure, with `error` set.
  static std::string resolve_language(const std::string& id, std::string& error);

  explicit Session(std::string language_id);
  ~Session();
  Session(const Session&) = delete;
  Session& operator=(const Session&) = delete;

  State state() const noexcept { return state_; }
  const std::string& language() const noexcept { return language_; }

  gnsdk_status load_image(const std::uint8_t* bytes, std::size_t len, std::uint64_t base,
                          const char* name);
  gnsdk_status open_snapshot(const std::string& path);

  gnsdk_status disassemble(const gnsdk_range& range, const gnsdk_request_options& opts,
                           std::string& text, std::int32_t& detail);
  gnsdk_status lift(const gnsdk_range& range, const gnsdk_request_options& opts, PcodeStore& store,
                    std::int32_t& detail);
  gnsdk_status decompile(std::uint64_t addr, const gnsdk_decompile_options& opts, std::string& c_text,
                         std::string& tokens, std::string& warnings, std::int32_t& detail);

  void cancel() noexcept { cancel_.request_cancel(); }
  std::string diagnostics() const;

  void inject(InjectKind kind) noexcept { inject_ = kind; }

 private:
  enum class Kind { Disasm, Lift, Decompile };

  template <class F>
  gnsdk_status run_request(Kind kind, std::uint64_t deadline_ms, std::int32_t& detail, F&& body);
  template <class F>
  gnsdk_status run_build(const char* what, F&& body);

  void checkpoint();
  void poison(const char* why);
  void flush_engine_messages(std::string* into);
  ghidra::Address code_address(std::uint64_t off) const;
  void apply_decompile_options(const gnsdk_decompile_options& opts);

  State state_ = GNSDK_STATE_CREATED;
  std::string language_;
  std::string image_name_;
  std::ostringstream errstream_;                   // engine messages (SleighArchitecture::printMessage)
  std::unique_ptr<ghidra::DocumentStorage> store_;  // outlives arch_ (declared before it)
  std::unique_ptr<ghidra::Architecture> arch_;
  Diagnostics diag_;
  CancelState cancel_;
  InjectKind inject_ = InjectKind::None;
};

}  // namespace gnsdk
