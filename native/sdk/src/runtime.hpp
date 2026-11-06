// Process-level state: init/shutdown, the single live session, capabilities.
#pragma once

#include <cstdint>
#include <string>

#include "gnsdk/gnsdk.h"

namespace gnsdk {

class Session;

namespace runtime {

// Engine initialisation (once per process; see gnsdk.h). Returns
// GNSDK_STALE for a different sleigh home after a successful init.
gnsdk_status init(const std::string& sleigh_home, std::string& error);
gnsdk_status shutdown();
bool ready() noexcept;          // initialised and not shut down
const std::string& sleigh_home() noexcept;

Session* live_session() noexcept;
void set_live_session(Session* s) noexcept;

std::uint64_t capabilities() noexcept;
void clear_capability(std::uint64_t bit) noexcept;

// Global diagnostic text produced during init (ldefs warnings etc.).
const std::string& init_messages() noexcept;

}  // namespace runtime
}  // namespace gnsdk
