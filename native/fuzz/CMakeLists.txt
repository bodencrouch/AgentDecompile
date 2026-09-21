if(NOT GNSDK_FUZZ)
  return()
endif()
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  message(FATAL_ERROR "GNSDK_FUZZ requires clang/libFuzzer")
endif()

function(gnsdk_add_fuzzer target source)
  add_executable(${target} ${source})
  target_include_directories(${target} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/..)
  target_link_libraries(${target} PRIVATE gnsdk::common ${ARGN})
  target_compile_features(${target} PRIVATE cxx_std_20)
  target_compile_options(${target} PRIVATE -fsanitize=fuzzer,address)
  target_link_options(${target} PRIVATE -fsanitize=fuzzer,address)
endfunction()

gnsdk_add_fuzzer(protocol_fuzzer protocol_fuzzer.cpp gnsdk::protocol)
gnsdk_add_fuzzer(sleigh_disasm_fuzzer fuzz_sleigh_disasm.cpp gnsdk::gnsdk)
gnsdk_add_fuzzer(pcode_lift_context_fuzzer fuzz_pcode_lift_context.cpp gnsdk::gnsdk)

foreach(_name IN ITEMS protocol_fuzzer sleigh_disasm_fuzzer pcode_lift_context_fuzzer)
  set(_corpus_dir "${CMAKE_CURRENT_SOURCE_DIR}/corpus/${_name}")
  set(_work_dir "${CMAKE_CURRENT_BINARY_DIR}/corpus/${_name}")
  set(_artifact_dir "${CMAKE_CURRENT_BINARY_DIR}/artifacts/${_name}")
  add_test(NAME fuzz_smoke_${_name}
    COMMAND ${CMAKE_COMMAND}
      "-DFUZZ_EXECUTABLE=$<TARGET_FILE:${_name}>"
      "-DFUZZ_CORPUS_DIR=${_corpus_dir}"
      "-DFUZZ_WORK_DIR=${_work_dir}"
      "-DFUZZ_ARTIFACT_DIR=${_artifact_dir}"
      -P "${CMAKE_CURRENT_SOURCE_DIR}/../cmake/FuzzSmoke.cmake")
  set_tests_properties(fuzz_smoke_${_name} PROPERTIES LABELS "fuzz;smoke" TIMEOUT 300)
endforeach()

foreach(_target IN ITEMS sleigh_disasm_fuzzer pcode_lift_context_fuzzer)
  target_compile_definitions(${_target} PRIVATE
    GNSDK_FUZZ_SLEIGH_HOME="$<SHELL_PATH:${GNSDK_SLEIGH_HOME}>")
endforeach()
