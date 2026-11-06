// SleighArchitecture over an in-memory image (the raw-image path).
#pragma once

#include <cstdint>
#include <ostream>
#include <string>
#include <vector>

#include "buffer_loadimage.hpp"
#include "upstream.hpp"

namespace gnsdk {

// Same shape as upstream RawBinaryArchitecture (raw_arch.cc): the language
// id comes from the caller, the loader owns the bytes, and the loader is
// attached to the default code space once the translator exists.
class BufferArchitecture final : public ghidra::SleighArchitecture {
 public:
  BufferArchitecture(const std::string& name, const std::string& language_id, std::ostream* errs,
                     std::vector<std::uint8_t> bytes, std::uint64_t base);
  ~BufferArchitecture() override = default;

  BufferLoadImage* image() const noexcept { return image_; }

 protected:
  void buildLoader(ghidra::DocumentStorage& store) override;
  void resolveArchitecture() override;
  void postSpecFile() override;

 private:
  std::vector<std::uint8_t> pending_bytes_;
  std::uint64_t base_;
  BufferLoadImage* image_ = nullptr;  // owned by Architecture::loader
};

}  // namespace gnsdk
