# native/worker: framed local worker protocol (WP4) and the gnsdk-worker
# executable (WP5, appended below the marker).

add_library(gnsdk_protocol STATIC
  protocol.cpp
  json_min.cpp
)
# Consumers include <worker/protocol.hpp> / <worker/json_min.hpp>.
target_include_directories(gnsdk_protocol PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/..)
target_compile_features(gnsdk_protocol PUBLIC cxx_std_20)
if(TARGET gnsdk_common)
  target_link_libraries(gnsdk_protocol PUBLIC gnsdk_common)
endif()
add_library(gnsdk::protocol ALIAS gnsdk_protocol)

# --- gnsdk-worker (WP5) appends below ---
