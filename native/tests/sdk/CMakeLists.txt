find_package(Threads REQUIRED)

add_executable(gnsdk-lifecycle lifecycle.cpp)
target_include_directories(gnsdk-lifecycle PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../worker)
target_link_libraries(gnsdk-lifecycle PRIVATE gnsdk::gnsdk Threads::Threads)
target_compile_features(gnsdk-lifecycle PRIVATE cxx_std_20)
target_compile_definitions(gnsdk-lifecycle PRIVATE
  GNSDK_TEST_SLEIGH_HOME="$<SHELL_PATH:${GNSDK_SLEIGH_HOME}>")

foreach(_case IN ITEMS repeat program_change second_session_busy partial_init after_shutdown)
  add_test(NAME lifecycle_${_case} COMMAND gnsdk-lifecycle ${_case})
  set_tests_properties(lifecycle_${_case} PROPERTIES LABELS "sdk;lifecycle")
endforeach()

foreach(_case IN ITEMS status_table version_source struct_prefix snapshot_invalid)
  add_test(NAME abi_${_case} COMMAND gnsdk-lifecycle ${_case})
  set_tests_properties(abi_${_case} PROPERTIES LABELS "sdk;abi")
endforeach()
