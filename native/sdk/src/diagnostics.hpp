// Bounded per-session event log.
#pragma once

#include <chrono>
#include <cstddef>
#include <string>
#include <string_view>

namespace gnsdk {

// Keeps the most recent `capacity` bytes of log text. Old text is dropped on
// line boundaries; the number of dropped bytes is reported at the top of
// text(). Appending never throws for the caller's benefit beyond
// std::bad_alloc from the underlying string.
class Diagnostics {
 public:
  static constexpr std::size_t kDefaultCapacity = 64 * 1024;

  explicit Diagnostics(std::size_t capacity = kDefaultCapacity);

  // One line, timestamped relative to construction. A trailing newline is
  // added when missing.
  void log(std::string_view line);
  // Raw text (e.g. engine messages), each line prefixed with `prefix`.
  void append_prefixed(std::string_view prefix, std::string_view text);

  std::string text() const;
  std::size_t size() const noexcept { return buf_.size(); }
  bool empty() const noexcept { return buf_.empty(); }

 private:
  void trim();

  std::string buf_;
  std::size_t capacity_;
  std::size_t dropped_ = 0;
  std::chrono::steady_clock::time_point start_;
};

}  // namespace gnsdk
