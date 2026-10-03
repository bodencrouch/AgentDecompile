#include "buffer_loadimage.hpp"

#include <cstring>
#include <sstream>

namespace gnsdk {

BufferLoadImage::BufferLoadImage(std::string name, std::vector<std::uint8_t> bytes, std::uint64_t base)
    : ghidra::LoadImage(name), bytes_(std::move(bytes)), base_(base) {}

void BufferLoadImage::loadFill(ghidra::uint1* ptr, ghidra::int4 size, const ghidra::Address& addr) {
  if (size <= 0) return;
  const std::uint64_t filesize = bytes_.size();
  std::uint64_t cur = addr.getOffset();
  std::size_t want = static_cast<std::size_t>(size);
  std::size_t done = 0;

  cur -= base_;  // relative offset of the first byte (wraps when below base)
  if (cur < filesize) {
    std::size_t avail = static_cast<std::size_t>(filesize - cur);
    std::size_t n = want < avail ? want : avail;
    std::memcpy(ptr, bytes_.data() + cur, n);
    done = n;
    if (done < want) {
      std::memset(ptr + done, 0, want - done);  // zero-fill past the end, like RawLoadImage
      done = want;
    }
  }
  if (done < want) {
    std::ostringstream err;
    err << "Unable to load " << std::dec << (want - done) << " bytes at " << addr.getShortcut();
    addr.printRaw(err);
    throw ghidra::DataUnavailError(err.str());
  }
}

std::string BufferLoadImage::getArchType() const { return "unknown"; }

void BufferLoadImage::adjustVma(long adjust) { base_ += static_cast<std::uint64_t>(adjust); }

}  // namespace gnsdk
