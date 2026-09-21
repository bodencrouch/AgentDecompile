# tools/fake_worker: protocol stand-in for gnsdk-worker with fault injection.
# Used by tests/worker (smoke + misbehave matrix) and tests/pool.
if(NOT TARGET gnsdk_protocol)
  return()
endif()

find_package(Threads REQUIRED)

add_executable(fake-worker fake_worker.cpp)
target_link_libraries(fake-worker PRIVATE gnsdk_protocol Threads::Threads)
target_compile_features(fake-worker PRIVATE cxx_std_20)
if(TARGET gnsdk_common)
  target_link_libraries(fake-worker PRIVATE gnsdk_common)
endif()
