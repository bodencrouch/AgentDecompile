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

add_executable(pool_cancel_ladder cancel_ladder.cpp)
target_include_directories(pool_cancel_ladder PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../.. ${CMAKE_CURRENT_SOURCE_DIR}/../worker)
target_link_libraries(pool_cancel_ladder PRIVATE gnsdk::pool gnsdk_protocol Threads::Threads)
target_compile_features(pool_cancel_ladder PRIVATE cxx_std_20)
target_compile_definitions(pool_cancel_ladder PRIVATE GNSDK_FAKE_WORKER_PATH="$<TARGET_FILE:fake-worker>")
add_dependencies(pool_cancel_ladder fake-worker)
add_test(NAME pool_cancel_ladder COMMAND pool_cancel_ladder)
set_tests_properties(pool_cancel_ladder PROPERTIES LABELS "pool;fault")

add_executable(pool_truncated_frame truncated_frame.cpp)
target_include_directories(pool_truncated_frame PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../.. ${CMAKE_CURRENT_SOURCE_DIR}/../worker)
target_link_libraries(pool_truncated_frame PRIVATE gnsdk::pool gnsdk_protocol Threads::Threads)
target_compile_features(pool_truncated_frame PRIVATE cxx_std_20)
target_compile_definitions(pool_truncated_frame PRIVATE GNSDK_FAKE_WORKER_PATH="$<TARGET_FILE:fake-worker>")
add_dependencies(pool_truncated_frame fake-worker)
add_test(NAME pool_truncated_frame COMMAND pool_truncated_frame)
set_tests_properties(pool_truncated_frame PROPERTIES LABELS "pool;fault")

add_test(NAME gnsdk_batch_version COMMAND gnsdk-batch --version)
set_tests_properties(gnsdk_batch_version PROPERTIES
  LABELS "pool;batch"
  PASS_REGULAR_EXPRESSION "gnsdk-batch 0\\.1\\.0")
