// LoadImage over a byte buffer the session owns.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "upstream.hpp"

namespace gnsdk {

// Mirrors upstream RawLoadImage (loadimage.cc) but reads from memory:
// bytes[0] lives at `base` in the attached space; reads past the end are
// zero-filled, reads that start outside the image throw DataUnavailError.
class BufferLoadImage final : public ghidra::LoadImage {
 public:
  BufferLoadImage(std::string name, std::vector<std::uint8_t> bytes, std::uint64_t base);

  void attachToSpace(ghidra::AddrSpace* spc) { space_ = spc; }
  std::uint64_t base() const noexcept { return base_; }
  std::size_t size() const noexcept { return bytes_.size(); }

  void loadFill(ghidra::uint1* ptr, ghidra::int4 size, const ghidra::Address& addr) override;
  std::string getArchType() const override;
  void adjustVma(long adjust) override;

 private:
  std::vector<std::uint8_t> bytes_;
  std::uint64_t base_;
  ghidra::AddrSpace* space_ = nullptr;
};

}  // namespace gnsdk
