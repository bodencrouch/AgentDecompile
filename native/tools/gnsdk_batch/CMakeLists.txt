add_executable(gnsdk-batch main.cpp)
target_include_directories(gnsdk-batch PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../../pool/include ${CMAKE_CURRENT_SOURCE_DIR}/../..)
target_link_libraries(gnsdk-batch PRIVATE gnsdk::pool gnsdk::protocol)
target_compile_features(gnsdk-batch PRIVATE cxx_std_20)
target_compile_definitions(gnsdk-batch PRIVATE GNSDK_WORKER_PATH="$<TARGET_FILE:gnsdk-worker>")
add_dependencies(gnsdk-batch gnsdk-worker)

if(TARGET fake-worker)
  add_executable(gnsdk-batch-fake main.cpp)
  target_include_directories(gnsdk-batch-fake PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../../pool/include ${CMAKE_CURRENT_SOURCE_DIR}/../..)
  target_link_libraries(gnsdk-batch-fake PRIVATE gnsdk::pool gnsdk::protocol)
  target_compile_features(gnsdk-batch-fake PRIVATE cxx_std_20)
  target_compile_definitions(gnsdk-batch-fake PRIVATE
    GNSDK_WORKER_PATH="$<TARGET_FILE:fake-worker>"
    GNSDK_BATCH_EXTRA_WORKER_ARG="--misbehave=slow-reply")
  add_dependencies(gnsdk-batch-fake fake-worker)
endif()
