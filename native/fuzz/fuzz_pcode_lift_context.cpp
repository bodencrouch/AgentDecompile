#include <array>
#include <cstddef>
#include <cstdint>

#include "gnsdk/gnsdk.h"

namespace {
constexpr std::uint64_t kBase = 0x400000;
constexpr std::array<std::uint8_t, 16> kImage = {
    0x55,        // push rbp
    0x48, 0x89, 0xe5,  // mov rbp, rsp
    0x31, 0xc0,        // xor eax, eax
    0x48, 0x83, 0xc0, 0x2a,  // add rax, 0x2a
    0x5d,        // pop rbp
    0xc3,        // ret
    0x90, 0x90, 0x0f, 0x1f};

bool ready() {
  static const bool value = [] {
    gnsdk_init_options options{};
    GNSDK_INIT_STRUCT(&options);
    options.sleigh_home = GNSDK_FUZZ_SLEIGH_HOME;
    return gnsdk_init(&options) == GNSDK_OK;
  }();
  return value;
}

gnsdk_session* session() {
  static gnsdk_session* value = [] {
    if (!ready()) return static_cast<gnsdk_session*>(nullptr);
    gnsdk_session_options session_options{};
    GNSDK_INIT_STRUCT(&session_options);
    session_options.language_id = "x86:LE:64:default";
    gnsdk_session* created = nullptr;
    if (gnsdk_session_create(&session_options, &created) != GNSDK_OK) return static_cast<gnsdk_session*>(nullptr);
    gnsdk_image_desc image{};
    GNSDK_INIT_STRUCT(&image);
    image.bytes = kImage.data();
    image.len = kImage.size();
    image.base = kBase;
    image.name = "fuzz-lift";
    if (gnsdk_session_load_image(created, &image) != GNSDK_OK) {
      gnsdk_session_destroy(created);
      return static_cast<gnsdk_session*>(nullptr);
    }
    return created;
  }();
  return value;
}
}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
  if (size == 0) return 0;
  gnsdk_session* s = session();
  if (!s) return 0;
  const std::size_t start = data[0] % kImage.size();
  const std::size_t width = 1 + (data[size - 1] % (kImage.size() - start));
  gnsdk_range range{kBase + start, kBase + start + width};
  gnsdk_request_options options{};
  GNSDK_INIT_STRUCT(&options);
  if (size > 1) options.max_instructions = 1 + (data[1] % 16);
  if (size > 2) options.deadline_ms = data[2] % 8;
  gnsdk_pcode_out out{};
  GNSDK_INIT_STRUCT(&out);
  (void)gnsdk_lift(s, &range, &options, &out);
  gnsdk_pcode_free(&out);
  return 0;
}
