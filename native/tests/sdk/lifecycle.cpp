#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>

#include "gnsdk/gnsdk.h"

#include "wtest.hpp"

using namespace wtest;

namespace {

constexpr const char* kHome = GNSDK_TEST_SLEIGH_HOME;
constexpr const char* kLanguage = "x86:LE:64:default";
constexpr std::array<std::uint8_t, 8> kCode = {0x55, 0x48, 0x89, 0xe5, 0x31, 0xc0, 0x5d, 0xc3};

gnsdk_status init() {
  gnsdk_init_options options{};
  GNSDK_INIT_STRUCT(&options);
  options.sleigh_home = kHome;
  return gnsdk_init(&options);
}

gnsdk_session* ready_x86() {
  gnsdk_session_options options{};
  GNSDK_INIT_STRUCT(&options);
  options.language_id = kLanguage;
  gnsdk_session* session = nullptr;
  REQUIRE(gnsdk_session_create(&options, &session) == GNSDK_OK);
  gnsdk_image_desc image{};
  GNSDK_INIT_STRUCT(&image);
  image.bytes = kCode.data();
  image.len = kCode.size();
  image.base = 0x400000;
  image.name = "lifecycle-x86";
  REQUIRE(gnsdk_session_load_image(session, &image) == GNSDK_OK);
  return session;
}

void repeat() {
  CHECK_EQ(init(), GNSDK_OK);
  CHECK_EQ(init(), GNSDK_OK);
  gnsdk_init_options alternate{};
  GNSDK_INIT_STRUCT(&alternate);
  alternate.sleigh_home = "/definitely/not/the/loaded/home";
  CHECK_EQ(gnsdk_init(&alternate), GNSDK_STALE);
  gnsdk_buf languages{};
  CHECK_EQ(gnsdk_language_list(&languages), GNSDK_OK);
  CHECK(languages.data != nullptr && std::strstr(reinterpret_cast<const char*>(languages.data), kLanguage) != nullptr);
  gnsdk_buf_free(&languages);
}

void program_change() {
  REQUIRE(init() == GNSDK_OK);
  gnsdk_session* session = ready_x86();
  std::uint32_t state = GNSDK_STATE_CREATED;
  CHECK_EQ(gnsdk_session_get_state(session, &state), GNSDK_OK);
  CHECK_EQ(state, std::uint32_t{GNSDK_STATE_READY});
  gnsdk_range range{0x400000, 0x400008};
  gnsdk_buf text{};
  CHECK(gnsdk_disassemble(session, &range, nullptr, &text) == GNSDK_OK);
  CHECK(text.data != nullptr && text.len > 0);
  gnsdk_buf_free(&text);
  CHECK_EQ(gnsdk_session_destroy(session), GNSDK_OK);
}

void second_session_busy() {
  REQUIRE(init() == GNSDK_OK);
  gnsdk_session_options options{};
  GNSDK_INIT_STRUCT(&options);
  options.language_id = kLanguage;
  gnsdk_session* first = nullptr;
  REQUIRE(gnsdk_session_create(&options, &first) == GNSDK_OK);
  gnsdk_session* second = nullptr;
  CHECK_EQ(gnsdk_session_create(&options, &second), GNSDK_BUSY);
  CHECK(second == nullptr);
  CHECK_EQ(gnsdk_session_destroy(first), GNSDK_OK);
}

void partial_init() {
  struct Partial { std::uint32_t struct_size; std::uint32_t flags; } partial{sizeof(Partial), 0};
  CHECK_EQ(gnsdk_init(reinterpret_cast<const gnsdk_init_options*>(&partial)), GNSDK_INVALID_ARGUMENT);
  CHECK_EQ(init(), GNSDK_OK);
}

void after_shutdown() {
  REQUIRE(init() == GNSDK_OK);
  CHECK_EQ(gnsdk_shutdown(), GNSDK_OK);
  gnsdk_buf languages{};
  CHECK_EQ(gnsdk_language_list(&languages), GNSDK_NOT_INITIALIZED);
  CHECK_EQ(init(), GNSDK_OK);
}

void status_table() {
  struct Expected { gnsdk_status status; const char* name; };
  constexpr Expected expected[] = {
      {GNSDK_OK, "GNSDK_OK"}, {GNSDK_OK_WARNINGS, "GNSDK_OK_WARNINGS"},
      {GNSDK_PARTIAL_UNSUPPORTED, "GNSDK_PARTIAL_UNSUPPORTED"}, {GNSDK_CANCELLED, "GNSDK_CANCELLED"},
      {GNSDK_TIMEOUT, "GNSDK_TIMEOUT"}, {GNSDK_RESOURCE_LIMITED, "GNSDK_RESOURCE_LIMITED"},
      {GNSDK_BUSY, "GNSDK_BUSY"}, {GNSDK_STALE, "GNSDK_STALE"},
      {GNSDK_PROVIDER_FAILURE, "GNSDK_PROVIDER_FAILURE"}, {GNSDK_ENGINE_FAILURE, "GNSDK_ENGINE_FAILURE"},
      {GNSDK_INVALID_ARGUMENT, "GNSDK_INVALID_ARGUMENT"}, {GNSDK_NOT_INITIALIZED, "GNSDK_NOT_INITIALIZED"},
  };
  for (const auto& entry : expected) CHECK_EQ(std::string(gnsdk_status_name(entry.status)), std::string(entry.name));
  CHECK_EQ(std::string(gnsdk_status_name(999)), std::string("GNSDK_UNKNOWN_STATUS"));
}

void version_source() {
  gnsdk_version_info version{};
  GNSDK_INIT_STRUCT(&version);
  CHECK_EQ(gnsdk_version(&version), GNSDK_OK);
  CHECK_EQ(version.abi_major, std::uint32_t{GNSDK_ABI_MAJOR});
  CHECK_EQ(version.sla_format_version, std::uint32_t{4});
  CHECK(std::string(version.ghidra_version) == "12.1.3");
  CHECK(std::string(version.source).starts_with("Ghidra_12.1.3_build"));
}

void struct_prefix() {
  struct Prefix { std::uint32_t struct_size; } prefix{sizeof(Prefix)};
  CHECK_EQ(gnsdk_version(reinterpret_cast<gnsdk_version_info*>(&prefix)), GNSDK_OK);
  CHECK_EQ(prefix.struct_size, std::uint32_t{sizeof(Prefix)});
  CHECK_EQ(gnsdk_init(nullptr), GNSDK_INVALID_ARGUMENT);
}

void snapshot_invalid() {
  REQUIRE(init() == GNSDK_OK);
  gnsdk_session_options options{};
  GNSDK_INIT_STRUCT(&options);
  gnsdk_session* session = nullptr;
  const auto status = gnsdk_session_open_snapshot(&options, "/definitely/not/a/snapshot.xml", &session);
  CHECK(status == GNSDK_PROVIDER_FAILURE || status == GNSDK_ENGINE_FAILURE);
  REQUIRE(session != nullptr);
  std::uint32_t state = GNSDK_STATE_CREATED;
  CHECK_EQ(gnsdk_session_get_state(session, &state), GNSDK_OK);
  CHECK_EQ(state, std::uint32_t{GNSDK_STATE_POISONED});
  CHECK_EQ(gnsdk_session_destroy(session), GNSDK_OK);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const std::string name = argv[1];
  if (name == "repeat") repeat();
  else if (name == "program_change") program_change();
  else if (name == "second_session_busy") second_session_busy();
  else if (name == "partial_init") partial_init();
  else if (name == "after_shutdown") after_shutdown();
  else if (name == "status_table") status_table();
  else if (name == "version_source") version_source();
  else if (name == "struct_prefix") struct_prefix();
  else if (name == "snapshot_invalid") snapshot_invalid();
  else return 2;
  return exit_code();
}
