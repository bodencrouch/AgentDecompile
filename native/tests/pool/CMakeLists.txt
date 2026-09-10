find_package(Threads REQUIRED)

add_executable(pool_supervisor_smoke supervisor_smoke.cpp)
target_include_directories(pool_supervisor_smoke PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/../..
  ${CMAKE_CURRENT_SOURCE_DIR}/../worker)
target_link_libraries(pool_supervisor_smoke PRIVATE gnsdk::pool gnsdk_protocol Threads::Threads)
target_compile_features(pool_supervisor_smoke PRIVATE cxx_std_20)
target_compile_definitions(pool_supervisor_smoke PRIVATE
  GNSDK_FAKE_WORKER_PATH="$<TARGET_FILE:fake-worker>")
add_dependencies(pool_supervisor_smoke fake-worker)
add_test(NAME pool_supervisor_smoke COMMAND pool_supervisor_smoke)
set_tests_properties(pool_supervisor_smoke PROPERTIES LABELS "pool;integration")
