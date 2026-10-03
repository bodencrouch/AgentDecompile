#include "runtime.hpp"

#include <atomic>
#include <sstream>

#include "gnsdk/gnsdk_version.h"
#include "upstream.hpp"

namespace gnsdk::runtime {

namespace {

struct Globals {
  bool initialized = false;   // engine registries + spec paths populated
  bool shut_down = false;     // API disabled by gnsdk_shutdown
  std::string home;
  std::string init_messages;
  Session* live = nullptr;
  std::atomic<std::uint64_t> caps{
      GNSDK_CAP_RAW_IMAGE | GNSDK_CAP_SNAPSHOT_XML_V0 | GNSDK_CAP_DISASM | GNSDK_CAP_LIFT |
      GNSDK_CAP_DECOMPILE_C | GNSDK_CAP_TOKENS_XML_V0 | GNSDK_CAP_CANCEL_COOPERATIVE |
      GNSDK_CAP_CANCEL_IN_ACTION_LOOP | GNSDK_CAP_JAVA_PRINTER |
      (GNSDK_HAVE_BFD ? GNSDK_CAP_BFD : UINT64_C(0))};
};

Globals& g() {
  static Globals instance;
  return instance;
}

}  // namespace

gnsdk_status init(const std::string& sleigh_home, std::string& error) {
  Globals& G = g();
  if (G.initialized) {
    if (sleigh_home != G.home) {
      error = "engine already initialised with sleigh home '" + G.home + "'";
      return GNSDK_STALE;
    }
    G.shut_down = false;  // re-enable after gnsdk_shutdown
    return GNSDK_OK;
  }
  try {
    // libdecomp.cc startDecompilerLibrary(), called directly so the console
    // headers stay out. The registries clear themselves, so a retry after a
    // failed scan is safe.
    ghidra::AttributeId::initialize();
    ghidra::ElementId::initialize();
    ghidra::CapabilityPoint::initializeAll();
    ghidra::ArchitectureCapability::sortCapabilities();
    ghidra::SleighArchitecture::scanForSleighDirectories(sleigh_home);
    // Eager: .ldefs parse errors surface here, not at the first session.
    const auto& descs = ghidra::SleighArchitecture::getDescriptions();
    if (descs.empty()) {
      error = "no .ldefs language definitions found under '" + sleigh_home + "'";
      return GNSDK_PROVIDER_FAILURE;
    }
    std::ostringstream msg;
    msg << descs.size() << " languages from " << sleigh_home;
    G.init_messages = msg.str();
  } catch (const ghidra::DecoderError& e) {
    error = "language definitions failed to parse: " + e.explain;
    return GNSDK_PROVIDER_FAILURE;
  } catch (const ghidra::LowlevelError& e) {
    error = "engine initialisation failed: " + e.explain;
    return GNSDK_PROVIDER_FAILURE;
  }
  G.home = sleigh_home;
  G.initialized = true;
  G.shut_down = false;
  return GNSDK_OK;
}

gnsdk_status shutdown() {
  Globals& G = g();
  if (!G.initialized || G.shut_down) return GNSDK_NOT_INITIALIZED;
  if (G.live != nullptr) return GNSDK_BUSY;
  // A state transition only: the engine keeps its translators and spec
  // paths until the process exits (there is no upstream teardown).
  G.shut_down = true;
  return GNSDK_OK;
}

bool ready() noexcept {
  const Globals& G = g();
  return G.initialized && !G.shut_down;
}

const std::string& sleigh_home() noexcept { return g().home; }

Session* live_session() noexcept { return g().live; }
void set_live_session(Session* s) noexcept { g().live = s; }

std::uint64_t capabilities() noexcept { return g().caps.load(std::memory_order_relaxed); }
void clear_capability(std::uint64_t bit) noexcept { g().caps.fetch_and(~bit, std::memory_order_relaxed); }

const std::string& init_messages() noexcept { return g().init_messages; }

}  // namespace gnsdk::runtime
