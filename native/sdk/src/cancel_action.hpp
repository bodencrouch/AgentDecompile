// Cooperative cancellation: a flag + deadline checked at checkpoints and,
// when the upstream action tree has the expected shape, inside the main
// simplification loop through an extra Action.
#pragma once

#include <atomic>
#include <chrono>
#include <optional>
#include <string>

#include "upstream.hpp"

namespace gnsdk {

// Thrown from a checkpoint. A LowlevelError so upstream code that catches
// LowlevelError (and rethrows or records) keeps behaving.
struct CancelledError : ghidra::LowlevelError {
  bool timeout;
  explicit CancelledError(bool is_timeout)
      : ghidra::LowlevelError(is_timeout ? "deadline exceeded" : "cancelled"), timeout(is_timeout) {}
};

class CancelState {
 public:
  // Async-signal-safe: one relaxed store.
  void request_cancel() noexcept { flag_.store(true, std::memory_order_relaxed); }

  void begin_request(std::uint64_t deadline_ms) noexcept;
  void end_request() noexcept { deadline_.reset(); }

  // Throws CancelledError when the flag is set or the deadline has passed.
  void check() const;
  bool cancelled() const noexcept { return flag_.load(std::memory_order_relaxed); }

 private:
  std::atomic<bool> flag_{false};
  std::optional<std::chrono::steady_clock::time_point> deadline_;
};

// Inserted as the last member of universal::fullloop::mainloop so every
// iteration of the main loop observes cancellation.
class ActionCancelCheck final : public ghidra::Action {
 public:
  static constexpr const char* kName = "gnsdk_cancel";
  explicit ActionCancelCheck(const CancelState* state)
      : ghidra::Action(0, kName, "base"), state_(state) {}
  ghidra::Action* clone(const ghidra::ActionGroupList& grouplist) const override;
  ghidra::int4 apply(ghidra::Funcdata& data) override;

 private:
  const CancelState* state_;
};

// Installs (or re-finds) the check inside the architecture's current root
// action. Returns false when the expected group path does not exist; the
// caller then drops the CANCEL_IN_ACTION_LOOP capability bit.
bool install_cancel_action(ghidra::Architecture& arch, const CancelState* state);

}  // namespace gnsdk
