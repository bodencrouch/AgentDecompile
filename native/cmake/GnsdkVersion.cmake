# Generate <build>/generated/gnsdk/gnsdk_version.h from the vendor tree.
#
# Exposes at configure time:
#   GNSDK_VENDOR_DESCRIBE   git describe --tags --always of vendor/ghidra
#   GNSDK_VENDOR_COMMIT     full commit hash
#   GNSDK_GHIDRA_VERSION    application.version from Ghidra/application.properties
#   GNSDK_SLA_FORMAT_VERSION FORMAT_VERSION parsed from slaformat.cc
#   GNSDK_GENERATED_DIR     include dir holding gnsdk/gnsdk_version.h
function(gnsdk_generate_version_header)
  find_package(Git QUIET)
  set(_describe "unknown")
  set(_commit "unknown")
  if(GIT_EXECUTABLE)
    execute_process(
      COMMAND "${GIT_EXECUTABLE}" -C "${GNSDK_VENDOR_GHIDRA}" describe --tags --always
      OUTPUT_VARIABLE _describe OUTPUT_STRIP_TRAILING_WHITESPACE
      RESULT_VARIABLE _rc ERROR_QUIET)
    if(NOT _rc EQUAL 0)
      set(_describe "unknown")
    endif()
    execute_process(
      COMMAND "${GIT_EXECUTABLE}" -C "${GNSDK_VENDOR_GHIDRA}" rev-parse HEAD
      OUTPUT_VARIABLE _commit OUTPUT_STRIP_TRAILING_WHITESPACE
      RESULT_VARIABLE _rc ERROR_QUIET)
    if(NOT _rc EQUAL 0)
      set(_commit "unknown")
    endif()
  endif()

  set(_ghidra_version "unknown")
  set(_props "${GNSDK_VENDOR_GHIDRA}/Ghidra/application.properties")
  if(EXISTS "${_props}")
    file(STRINGS "${_props}" _line REGEX "^application\\.version=")
    if(_line)
      string(REGEX REPLACE "^application\\.version=" "" _ghidra_version "${_line}")
    endif()
  endif()

  set(_sla_format 0)
  set(_slaformat "${GNSDK_UPSTREAM_CPP}/slaformat.cc")
  if(EXISTS "${_slaformat}")
    file(STRINGS "${_slaformat}" _line REGEX "FORMAT_VERSION[ \t]*=[ \t]*[0-9]+")
    if(_line)
      list(GET _line 0 _line)
      string(REGEX MATCH "[0-9]+" _sla_format "${_line}")
    endif()
  endif()

  set(_shared 0)
  if(GNSDK_SHARED)
    set(_shared 1)
  endif()
  set(_hooks 0)
  if(GNSDK_ENABLE_TEST_HOOKS)
    set(_hooks 1)
  endif()
  set(_bfd 0)
  if(GHIDRA_DECOMP_BFD)
    set(_bfd 1)
  endif()
  set(_build_flags
    "type=${CMAKE_BUILD_TYPE};sanitize=${GNSDK_SANITIZE};shared=${_shared};hooks=${_hooks};bfd=${_bfd};cxx=${CMAKE_CXX_COMPILER_ID}-${CMAKE_CXX_COMPILER_VERSION}")

  set(GNSDK_VENDOR_DESCRIBE "${_describe}" PARENT_SCOPE)
  set(GNSDK_VENDOR_COMMIT "${_commit}" PARENT_SCOPE)
  set(GNSDK_GHIDRA_VERSION "${_ghidra_version}" PARENT_SCOPE)
  set(GNSDK_SLA_FORMAT_VERSION "${_sla_format}" PARENT_SCOPE)
  set(GNSDK_BUILD_FLAGS "${_build_flags}" PARENT_SCOPE)

  set(GNSDK_GENERATED_DIR "${CMAKE_BINARY_DIR}/generated")
  set(GNSDK_GENERATED_DIR "${GNSDK_GENERATED_DIR}" PARENT_SCOPE)

  # configure_file reads these from the current scope.
  set(GNSDK_VENDOR_DESCRIBE "${_describe}")
  set(GNSDK_VENDOR_COMMIT "${_commit}")
  set(GNSDK_GHIDRA_VERSION "${_ghidra_version}")
  set(GNSDK_SLA_FORMAT_VERSION "${_sla_format}")
  set(GNSDK_BUILD_FLAGS "${_build_flags}")
  set(GNSDK_HAVE_BFD "${_bfd}")
  configure_file("${CMAKE_CURRENT_FUNCTION_LIST_DIR}/gnsdk_version.h.in"
                 "${GNSDK_GENERATED_DIR}/gnsdk/gnsdk_version.h" @ONLY)

  message(STATUS "gnsdk: vendor/ghidra = ${_describe} (${_commit}), Ghidra ${_ghidra_version}, sla format ${_sla_format}")
  if(NOT _describe MATCHES "^Ghidra_12\\.1\\.3_build(-|$)")
    message(WARNING "gnsdk: vendor/ghidra describes as '${_describe}', expected a revision based on "
                    "'Ghidra_12.1.3_build'. ctest abi_version_source will fail.")
  endif()
endfunction()
