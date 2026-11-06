# gnsdk: session lifecycle + C ABI over the unmodified upstream decompiler.

set(GNSDK_SDK_SOURCES
  src/abi.cpp
  src/buffer_architecture.cpp
  src/buffer_loadimage.cpp
  src/cancel_action.cpp
  src/diagnostics.cpp
  src/pcode_collector.cpp
  src/runtime.cpp
  src/session.cpp
)

# One object set feeds both the static and the optional shared library.
add_library(gnsdk_objs OBJECT ${GNSDK_SDK_SOURCES})
add_library(gnsdk STATIC $<TARGET_OBJECTS:gnsdk_objs>)
add_library(gnsdk::gnsdk ALIAS gnsdk)

foreach(_t gnsdk_objs gnsdk)
  target_include_directories(${_t}
    PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${GNSDK_GENERATED_DIR}>
    PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src)
  # Upstream headers are C++11 code compiled here under C++20; keep their
  # warnings out of -Werror by marking the directory as a system include.
  target_include_directories(${_t} SYSTEM PRIVATE "${GNSDK_UPSTREAM_CPP}")
  target_compile_definitions(${_t} PRIVATE
    GNSDK_BUILDING=1
    $<$<BOOL:${GNSDK_ENABLE_TEST_HOOKS}>:GNSDK_ENABLE_TEST_HOOKS=1>)
  target_link_libraries(${_t} PUBLIC gnsdk_common PRIVATE ghidra::decomp)
  set_target_properties(${_t} PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
    POSITION_INDEPENDENT_CODE ${GNSDK_SHARED})
endforeach()
# The object library only compiles; the archive carries the link interface.
target_link_libraries(gnsdk PRIVATE ghidra::decomp)
if(TARGET ghidra_specs)
  # A usable SDK artifact needs its compiled language definitions, not merely
  # the C++ archives.  This makes `cmake --build --target gnsdk[_shared]`
  # sufficient for consumers and prevents an otherwise surprising
  # GNSDK_PROVIDER_FAILURE on first gnsdk_init().
  add_dependencies(gnsdk ghidra_specs)
endif()

if(GNSDK_SHARED)
  add_library(gnsdk_shared SHARED $<TARGET_OBJECTS:gnsdk_objs>)
  add_library(gnsdk::shared ALIAS gnsdk_shared)
  target_include_directories(gnsdk_shared PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${GNSDK_GENERATED_DIR}>)
  target_compile_definitions(gnsdk_shared INTERFACE GNSDK_SHARED_BUILD=1)
  target_link_libraries(gnsdk_shared PUBLIC gnsdk_common PRIVATE ghidra::decomp)
  if(TARGET ghidra_specs)
    add_dependencies(gnsdk_shared ghidra_specs)
  endif()
  set_target_properties(gnsdk_shared PROPERTIES
    OUTPUT_NAME gnsdk
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
    SOVERSION 0
    VERSION ${PROJECT_VERSION})
  if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    target_link_options(gnsdk_shared PRIVATE
      "-Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/gnsdk.map"
      "-Wl,--no-undefined")
    set_property(TARGET gnsdk_shared APPEND PROPERTY LINK_DEPENDS
      "${CMAKE_CURRENT_SOURCE_DIR}/gnsdk.map")
    find_program(GNSDK_NM nm)
    if(GNSDK_NM)
      # Every defined dynamic symbol must carry the gnsdk_ prefix.
      add_test(NAME abi_shared_exports
        COMMAND sh -c "out=$(${GNSDK_NM} -D --defined-only \"$<TARGET_FILE:gnsdk_shared>\" | grep -v ' gnsdk_'); if [ -n \"$out\" ]; then echo \"$out\"; exit 1; fi")
    endif()
  endif()
endif()
