add_executable(gnsdk-selftest selftest.cpp)
target_link_libraries(gnsdk-selftest PRIVATE gnsdk::gnsdk)
target_compile_features(gnsdk-selftest PRIVATE cxx_std_20)
target_compile_definitions(gnsdk-selftest PRIVATE
  GNSDK_SELFTEST_SLEIGH_HOME="$<SHELL_PATH:${GNSDK_SLEIGH_HOME}>")

add_test(NAME gnsdk_selftest COMMAND gnsdk-selftest)
set_tests_properties(gnsdk_selftest PROPERTIES LABELS "sdk;smoke")
