find_package(Threads REQUIRED)

foreach(_test IN ITEMS protocol_roundtrip fake_worker_smoke fake_worker_misbehave_matrix)
  add_executable(${_test} ${_test}.cpp)
  target_include_directories(${_test} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../..)
  target_link_libraries(${_test} PRIVATE gnsdk_protocol Threads::Threads)
  target_compile_features(${_test} PRIVATE cxx_std_20)
  target_compile_definitions(${_test} PRIVATE
    GNSDK_FAKE_WORKER_PATH="$<TARGET_FILE:fake-worker>")
  add_test(NAME ${_test} COMMAND ${_test})
  set_tests_properties(${_test} PROPERTIES LABELS "worker;protocol")
endforeach()
