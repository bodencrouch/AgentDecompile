#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "gnsdk/gnsdk.h"

namespace {

constexpr const char* kHome = GNSDK_SELFTEST_SLEIGH_HOME;
constexpr const char* kLanguage = "x86:LE:64:default";
constexpr std::array<std::uint8_t, 8> kCode = {0x55, 0x48, 0x89, 0xe5, 0x31, 0xc0, 0x5d, 0xc3};

bool require(gnsdk_status actual, gnsdk_status expected, const char* operation) {
  if (actual == expected) return true;
  std::fprintf(stderr, "%s: %s\n", operation, gnsdk_status_name(actual));
  return false;
}

}  // namespace

int main() {
  gnsdk_version_info version{};
  GNSDK_INIT_STRUCT(&version);
  if (!require(gnsdk_version(&version), GNSDK_OK, "gnsdk_version")) return 1;

  gnsdk_init_options init{};
  GNSDK_INIT_STRUCT(&init);
  init.sleigh_home = kHome;
  if (!require(gnsdk_init(&init), GNSDK_OK, "gnsdk_init")) return 1;

  gnsdk_buf languages{};
  if (!require(gnsdk_language_list(&languages), GNSDK_OK, "gnsdk_language_list")) return 1;
  const bool found_language = languages.data != nullptr &&
      std::strstr(reinterpret_cast<const char*>(languages.data), kLanguage) != nullptr;
  gnsdk_buf_free(&languages);
  if (!found_language) {
    std::fputs("language not found in SLEIGH home\n", stderr);
    return 1;
  }

  gnsdk_session_options session_options{};
  GNSDK_INIT_STRUCT(&session_options);
  session_options.language_id = kLanguage;
  gnsdk_session* session = nullptr;
  if (!require(gnsdk_session_create(&session_options, &session), GNSDK_OK, "gnsdk_session_create")) return 1;

  gnsdk_image_desc image{};
  GNSDK_INIT_STRUCT(&image);
  image.bytes = kCode.data();
  image.len = kCode.size();
  image.base = 0x400000;
  image.name = "selftest-x86";
  if (!require(gnsdk_session_load_image(session, &image), GNSDK_OK, "gnsdk_session_load_image")) {
    gnsdk_session_destroy(session);
    return 1;
  }

  gnsdk_range range{0x400000, 0x400008};
  gnsdk_buf disassembly{};
  const gnsdk_status disasm_status = gnsdk_disassemble(session, &range, nullptr, &disassembly);
  const bool has_disassembly = disassembly.data != nullptr && disassembly.len > 0;
  if (disassembly.data != nullptr) std::fwrite(disassembly.data, 1, disassembly.len, stdout);
  gnsdk_buf_free(&disassembly);
  gnsdk_session_destroy(session);
  if (!require(disasm_status, GNSDK_OK, "gnsdk_disassemble") || !has_disassembly) return 1;

  std::printf("gnsdk %u.%u.%u; Ghidra %s; source=%s; caps=0x%llx\n",
              version.abi_major, version.abi_minor, version.abi_patch,
              version.ghidra_version, version.source,
              static_cast<unsigned long long>(gnsdk_capabilities()));
  return 0;
}
