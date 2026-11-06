#include "buffer_architecture.hpp"

#include <memory>

namespace gnsdk {

BufferArchitecture::BufferArchitecture(const std::string& name, const std::string& language_id,
                                       std::ostream* errs, std::vector<std::uint8_t> bytes,
                                       std::uint64_t base)
    : ghidra::SleighArchitecture(name, language_id, errs),
      pending_bytes_(std::move(bytes)),
      base_(base) {}

void BufferArchitecture::buildLoader(ghidra::DocumentStorage& /*store*/) {
  collectSpecFiles(*errorstream);
  auto ldr = std::make_unique<BufferLoadImage>(getFilename(), std::move(pending_bytes_), base_);
  image_ = ldr.get();
  loader = ldr.release();
}

void BufferArchitecture::resolveArchitecture() {
  archid = getTarget();  // nothing to derive from raw bytes; the caller named the language
  ghidra::SleighArchitecture::resolveArchitecture();
}

void BufferArchitecture::postSpecFile() {
  ghidra::Architecture::postSpecFile();
  if (image_ != nullptr) image_->attachToSpace(getDefaultCodeSpace());
}

}  // namespace gnsdk
