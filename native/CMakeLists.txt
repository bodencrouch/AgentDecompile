# native/: out-of-tree session layer and C ABI (gnsdk) over Ghidra's
# unmodified native decompiler. The upstream tree is consumed through the
# standalone CMake in vendor/ghidra (targets ghidra::decomp, sla, ...).
#
# Layout contract (other components rely on this order):
#   1. vendor/ghidra decompiler  -> build dir ghidra-decomp
#   2. sdk/                      -> gnsdk (static), gnsdk_shared (optional)
#   3. worker/, pool/            -> if their CMakeLists.txt exists
#   4. tools/*/, tests/*/, fuzz/ -> every CMakeLists.txt found, in that order
cmake_minimum_required(VERSION 3.24)

project(gnsdk VERSION 0.1.0 LANGUAGES C CXX)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
set(GNSDK_SANITIZE "" CACHE STRING
  "Sanitizer list for gnsdk targets and the upstream tree (e.g. address,undefined)")
option(GNSDK_SHARED "Also build libgnsdk.so with hidden visibility" OFF)
option(GNSDK_FUZZ "Build libFuzzer targets (clang only)" OFF)
option(GNSDK_WERROR "Treat warnings as errors on gnsdk* targets only" ON)
option(GNSDK_ENABLE_TEST_HOOKS "Compile test-only failure injection hooks into gnsdk" OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "Build type" FORCE)
endif()
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
enable_testing()

# ---------------------------------------------------------------------------
# Upstream decompiler (unmodified sources, standalone CMake from WP1)
# ---------------------------------------------------------------------------
get_filename_component(GNSDK_VENDOR_GHIDRA
  "${CMAKE_CURRENT_SOURCE_DIR}/../vendor/ghidra" ABSOLUTE)
set(GNSDK_UPSTREAM_CPP
  "${GNSDK_VENDOR_GHIDRA}/Ghidra/Features/Decompiler/src/decompile/cpp")
if(NOT EXISTS "${GNSDK_UPSTREAM_CPP}/CMakeLists.txt")
  message(FATAL_ERROR
    "Upstream CMake not found: ${GNSDK_UPSTREAM_CPP}/CMakeLists.txt\n"
    "Check out vendor/ghidra on branch native-sdk/cmake-standalone "
    "(Ghidra_12.1.3_build plus the standalone CMake files).")
endif()

# Defaults for the upstream options; a user may still override them on the
# command line because these are plain cache defaults, not FORCEd.
set(GHIDRA_DECOMP_BUILD_TESTS ON CACHE BOOL "Build upstream unit and data tests")
set(GHIDRA_DECOMP_INSTALL OFF CACHE BOOL "Install the upstream tree")
set(GHIDRA_DECOMP_CONSOLE ON CACHE BOOL "Build decomp_console and console TUs")
set(GHIDRA_DECOMP_BFD OFF CACHE BOOL "Link libbfd (never for gnsdk)")
set(GHIDRA_DECOMP_SANITIZE "${GNSDK_SANITIZE}" CACHE STRING "Sanitizers for the upstream tree")

if(GNSDK_SHARED)
  # libgnsdk.so links the upstream archives whole-archive, so they need PIC.
  set(CMAKE_POSITION_INDEPENDENT_CODE ON)
endif()

add_subdirectory("${GNSDK_UPSTREAM_CPP}" ghidra-decomp)

foreach(_t ghidra::decomp sla)
  if(NOT TARGET ${_t})
    message(FATAL_ERROR "Upstream target ${_t} is missing; the standalone CMake changed shape")
  endif()
endforeach()

# Sleigh home: where the compiled specs live. Order of precedence:
# explicit cache var, upstream variable, property on the ghidra_specs target.
if(NOT DEFINED GNSDK_SLEIGH_HOME OR GNSDK_SLEIGH_HOME STREQUAL "")
  set(_gnsdk_home "")
  if(DEFINED GHIDRA_DECOMP_SLEIGH_HOME AND NOT GHIDRA_DECOMP_SLEIGH_HOME STREQUAL "")
    set(_gnsdk_home "${GHIDRA_DECOMP_SLEIGH_HOME}")
  elseif(TARGET ghidra_specs)
    get_property(_gnsdk_home TARGET ghidra_specs PROPERTY GHIDRA_SLEIGH_HOME)
  endif()
  set(GNSDK_SLEIGH_HOME "${_gnsdk_home}" CACHE PATH "Directory scanned for compiled SLEIGH specs" FORCE)
endif()
if(TARGET ghidra_specs AND NOT GNSDK_SLEIGH_HOME STREQUAL "")
  set(GNSDK_HAVE_SPECS ON CACHE BOOL "Compiled specs are available for spec-dependent tests" FORCE)
else()
  set(GNSDK_HAVE_SPECS OFF CACHE BOOL "Compiled specs are available for spec-dependent tests" FORCE)
endif()
message(STATUS "gnsdk: sleigh home = '${GNSDK_SLEIGH_HOME}' (have specs: ${GNSDK_HAVE_SPECS})")

# ---------------------------------------------------------------------------
# Common interface for our own code: C++20, warnings, sanitizers.
# Never applied to upstream targets.
# ---------------------------------------------------------------------------
add_library(gnsdk_common INTERFACE)
add_library(gnsdk::common ALIAS gnsdk_common)
target_compile_features(gnsdk_common INTERFACE cxx_std_20 c_std_99)
set_property(TARGET gnsdk_common PROPERTY INTERFACE_COMPILE_OPTIONS
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang,AppleClang>:-Wall;-Wextra;-Wpedantic;-Wshadow;-Wnon-virtual-dtor;-Woverloaded-virtual;-Wcast-align;-Wformat=2;-Wno-unused-parameter>
  $<$<COMPILE_LANG_AND_ID:C,GNU,Clang,AppleClang>:-Wall;-Wextra;-Wpedantic;-Wformat=2>)
if(GNSDK_WERROR)
  target_compile_options(gnsdk_common INTERFACE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang,AppleClang>:-Werror>
    $<$<COMPILE_LANG_AND_ID:C,GNU,Clang,AppleClang>:-Werror>)
endif()
if(NOT GNSDK_SANITIZE STREQUAL "")
  target_compile_options(gnsdk_common INTERFACE -fsanitize=${GNSDK_SANITIZE} -fno-omit-frame-pointer)
  target_link_options(gnsdk_common INTERFACE -fsanitize=${GNSDK_SANITIZE})
endif()
# Our code that is not a gnsdk* target (tools, tests) still gets the warnings
# but the same -Werror choice; keep it uniform.
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
# The upstream subdirectory already captured its own CXX standard before this
# point (add_subdirectory above), so these only affect targets defined below.

# ---------------------------------------------------------------------------
# Generated version header (vendor git describe, build flags)
# ---------------------------------------------------------------------------
include(GnsdkVersion)
gnsdk_generate_version_header()

# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
add_subdirectory(sdk)

foreach(_dir worker pool)
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${_dir}/CMakeLists.txt")
    add_subdirectory(${_dir})
  endif()
endforeach()

file(GLOB _gnsdk_tool_lists LIST_DIRECTORIES false
  "${CMAKE_CURRENT_SOURCE_DIR}/tools/*/CMakeLists.txt")
list(SORT _gnsdk_tool_lists)
foreach(_f IN LISTS _gnsdk_tool_lists)
  get_filename_component(_d "${_f}" DIRECTORY)
  add_subdirectory("${_d}")
endforeach()

file(GLOB _gnsdk_test_lists LIST_DIRECTORIES false
  "${CMAKE_CURRENT_SOURCE_DIR}/tests/*/CMakeLists.txt")
list(SORT _gnsdk_test_lists)
foreach(_f IN LISTS _gnsdk_test_lists)
  get_filename_component(_d "${_f}" DIRECTORY)
  add_subdirectory("${_d}")
endforeach()

if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/fuzz/CMakeLists.txt")
  add_subdirectory(fuzz)
endif()
