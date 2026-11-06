#include "diagnostics.hpp"

#include <cstdio>

namespace gnsdk {

Diagnostics::Diagnostics(std::size_t capacity)
    : capacity_(capacity), start_(std::chrono::steady_clock::now()) {}

void Diagnostics::log(std::string_view line) {
  const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                      std::chrono::steady_clock::now() - start_)
                      .count();
  char stamp[32];
  std::snprintf(stamp, sizeof stamp, "[+%lldms] ", static_cast<long long>(ms));
  buf_ += stamp;
  buf_.append(line.data(), line.size());
  if (line.empty() || line.back() != '\n') buf_ += '\n';
  trim();
}

void Diagnostics::append_prefixed(std::string_view prefix, std::string_view text) {
  std::size_t pos = 0;
  while (pos < text.size()) {
    std::size_t nl = text.find('\n', pos);
    std::string_view line = text.substr(pos, nl == std::string_view::npos ? std::string_view::npos : nl - pos);
    buf_.append(prefix.data(), prefix.size());
    buf_.append(line.data(), line.size());
    buf_ += '\n';
    if (nl == std::string_view::npos) break;
    pos = nl + 1;
  }
  trim();
}

void Diagnostics::trim() {
  if (buf_.size() <= capacity_) return;
  std::size_t cut = buf_.size() - capacity_;
  std::size_t nl = buf_.find('\n', cut);
  if (nl == std::string::npos) {
    dropped_ += buf_.size();
    buf_.clear();
    return;
  }
  dropped_ += nl + 1;
  buf_.erase(0, nl + 1);
}

std::string Diagnostics::text() const {
  if (dropped_ == 0) return buf_;
  std::string out = "[... " + std::to_string(dropped_) + " earlier bytes dropped]\n";
  out += buf_;
  return out;
}

}  // namespace gnsdk
