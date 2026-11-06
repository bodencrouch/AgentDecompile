// wtest.hpp - assertion macros for the worker tests.
//
// Uses the tree-wide <tests/check.hpp> (CHECK / CHECK_EQ / REQUIRE) when it is
// present and defines the same names otherwise, so the tests build standalone
// with plain g++ as well as inside the CMake tree.
#pragma once

#include <cstdio>
#include <cstdlib>
#include <string>
#include <type_traits>

#if __has_include(<tests/check.hpp>)
#include <tests/check.hpp>
#endif

namespace wtest {
inline int& failures() {
  static int n = 0;
  return n;
}
inline int& checks() {
  static int n = 0;
  return n;
}
inline void fail(const char* file, int line, const std::string& what) {
  ++failures();
  std::fprintf(stderr, "%s:%d: FAIL %s\n", file, line, what.c_str());
  std::fflush(stderr);
}
inline int exit_code() {
  std::fprintf(stderr, "%d checks, %d failures\n", checks(), failures());
  return failures() == 0 ? 0 : 1;
}
template <class T>
std::string show(const T& v) {
  if constexpr (std::is_convertible_v<T, std::string>) return std::string(v);
  else if constexpr (std::is_same_v<T, bool>) return v ? "true" : "false";
  else if constexpr (std::is_enum_v<T>) return std::to_string(static_cast<long long>(v));
  else return std::to_string(v);
}
}  // namespace wtest

#ifndef CHECK
#define CHECK(cond)                                                            \
  do {                                                                         \
    ++::wtest::checks();                                                       \
    if (!(cond)) ::wtest::fail(__FILE__, __LINE__, "CHECK(" #cond ")");        \
  } while (0)
#endif

#ifndef CHECK_EQ
#define CHECK_EQ(a, b)                                                                     \
  do {                                                                                     \
    ++::wtest::checks();                                                                   \
    const auto wt_a_ = (a);                                                                \
    const auto wt_b_ = (b);                                                                \
    if (!(wt_a_ == wt_b_))                                                                 \
      ::wtest::fail(__FILE__, __LINE__,                                                    \
                    std::string("CHECK_EQ(" #a ", " #b "): ") + ::wtest::show(wt_a_) +      \
                        " != " + ::wtest::show(wt_b_));                                    \
  } while (0)
#endif

#ifndef REQUIRE
#define REQUIRE(cond)                                                            \
  do {                                                                           \
    ++::wtest::checks();                                                         \
    if (!(cond)) {                                                               \
      ::wtest::fail(__FILE__, __LINE__, "REQUIRE(" #cond ")");                   \
      std::fprintf(stderr, "aborting: requirement failed\n");                    \
      std::exit(1);                                                              \
    }                                                                            \
  } while (0)
#endif

#define WTEST_SECTION(name) std::fprintf(stderr, "--- %s\n", name)
