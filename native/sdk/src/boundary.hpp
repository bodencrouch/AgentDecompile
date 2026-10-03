// Outermost exception boundary for every exported C function.
#pragma once

#include <exception>
#include <new>

#include "gnsdk/gnsdk.h"

namespace gnsdk {

// Runs f() and converts anything that escapes into a status. Every export is
// noexcept in effect because of this wrapper; the session layer classifies
// engine errors more finely before they get here.
template <class F>
gnsdk_status guard(F&& f) noexcept {
  try {
    return f();
  } catch (const std::bad_alloc&) {
    return GNSDK_RESOURCE_LIMITED;
  } catch (...) {
    return GNSDK_ENGINE_FAILURE;
  }
}

}  // namespace gnsdk
