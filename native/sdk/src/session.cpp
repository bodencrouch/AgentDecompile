#include "session.hpp"

#include <exception>
#include <new>
#include <stdexcept>
#include <typeinfo>
#include <utility>

#include "buffer_architecture.hpp"
#include "pcode_collector.hpp"
#include "runtime.hpp"

namespace gnsdk {

namespace {

constexpr std::uint32_t kDefaultMaxInstructions = 65536;

std::string hex(std::uint64_t v) {
  char buf[32];
  std::snprintf(buf, sizeof buf, "0x%llx", static_cast<unsigned long long>(v));
  return buf;
}

std::vector<std::string> split_colon(const std::string& s) {
  std::vector<std::string> out;
  std::size_t pos = 0;
  for (;;) {
    std::size_t nl = s.find(':', pos);
    out.push_back(s.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos));
    if (nl == std::string::npos) break;
    pos = nl + 1;
  }
  return out;
}

}  // namespace

// ---------------------------------------------------------------------------
// Language resolution
// ---------------------------------------------------------------------------

std::string Session::resolve_language(const std::string& id, std::string& error) {
  auto parts = split_colon(id);
  if (parts.size() != 4 && parts.size() != 5) {
    error = "language id must be proc:endian:size:variant[:compiler]: " + id;
    return {};
  }
  for (const auto& p : parts) {
    if (p.empty()) {
      error = "language id has an empty segment: " + id;
      return {};
    }
  }
  const std::string base = parts[0] + ":" + parts[1] + ":" + parts[2] + ":" + parts[3];
  const ghidra::LanguageDescription* lang = nullptr;
  for (const auto& d : ghidra::SleighArchitecture::getDescriptions()) {
    if (d.getId() == base) {
      lang = &d;
      break;
    }
  }
  if (lang == nullptr) {
    error = "unknown language: " + base;
    return {};
  }
  if (lang->numCompilers() == 0) {
    error = "language has no compiler specs: " + base;
    return {};
  }
  if (parts.size() == 5) {
    for (ghidra::int4 i = 0; i < lang->numCompilers(); ++i) {
      if (lang->getCompiler(i).getId() == parts[4]) return base + ":" + parts[4];
    }
    error = "unknown compiler '" + parts[4] + "' for language " + base;
    return {};
  }
  return base + ":" + lang->getCompiler(0).getId();
}

// ---------------------------------------------------------------------------
// Construction / destruction
// ---------------------------------------------------------------------------

Session::Session(std::string language_id) : language_(std::move(language_id)) {
  diag_.log("session created; language=" + language_);
  state_ = GNSDK_STATE_CONFIGURED;
}

Session::~Session() {
  // Architecture first (it may reference registered XML elements), then the
  // document storage. The static Sleigh translator survives on purpose:
  // ~SleighArchitecture only nulls its pointer (sleigh_arch.cc).
  arch_.reset();
  store_.reset();
  state_ = GNSDK_STATE_DESTROYED;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

void Session::poison(const char* why) {
  state_ = GNSDK_STATE_POISONED;
  diag_.log(std::string("session poisoned: ") + why);
}

void Session::flush_engine_messages(std::string* into) {
  std::string msgs = errstream_.str();
  if (msgs.empty()) return;
  errstream_.str(std::string());
  errstream_.clear();
  diag_.append_prefixed("[engine] ", msgs);
  if (into != nullptr) *into += msgs;
}

void Session::checkpoint() {
#ifdef GNSDK_ENABLE_TEST_HOOKS
  if (inject_ != InjectKind::None) {
    const InjectKind k = inject_;
    inject_ = InjectKind::None;
    diag_.log("test hook: injecting failure kind " + std::to_string(static_cast<int>(k)));
    switch (k) {
      case InjectKind::BadAlloc:
        throw std::bad_alloc();
      case InjectKind::Unknown:
        throw std::runtime_error("injected unknown failure");
      case InjectKind::Lowlevel:
        throw ghidra::LowlevelError("injected engine failure");
      default:
        break;
    }
  }
#endif
  cancel_.check();
}

ghidra::Address Session::code_address(std::uint64_t off) const {
  return ghidra::Address(arch_->getDefaultCodeSpace(), static_cast<ghidra::uintb>(off));
}

// Build phase (load_image / open_snapshot): any failure poisons the session.
template <class F>
gnsdk_status Session::run_build(const char* what, F&& body) {
  try {
    body();
    flush_engine_messages(nullptr);
    state_ = GNSDK_STATE_READY;
    diag_.log(std::string(what) + ": ready; " + arch_->getDescription());
    return GNSDK_OK;
  } catch (const std::bad_alloc&) {
    diag_.log(std::string(what) + ": allocation failed");
    poison("bad_alloc during build");
    return GNSDK_RESOURCE_LIMITED;
  } catch (const ghidra::DecoderError& e) {
    flush_engine_messages(nullptr);
    diag_.log(std::string(what) + ": decoder error: " + e.explain);
    poison("provider failure during build");
    return GNSDK_PROVIDER_FAILURE;
  } catch (const ghidra::LowlevelError& e) {
    flush_engine_messages(nullptr);
    diag_.log(std::string(what) + ": engine error: " + e.explain);
    poison("provider failure during build");
    return GNSDK_PROVIDER_FAILURE;
  } catch (const std::exception& e) {
    flush_engine_messages(nullptr);
    diag_.log(std::string(what) + ": exception: " + e.what());
    poison("unexpected exception during build");
    return GNSDK_ENGINE_FAILURE;
  } catch (...) {
    flush_engine_messages(nullptr);
    diag_.log(std::string(what) + ": unknown exception");
    poison("unexpected exception during build");
    return GNSDK_ENGINE_FAILURE;
  }
}

// Request phase. Classification follows the table in gnsdk.h.
template <class F>
gnsdk_status Session::run_request(Kind kind, std::uint64_t deadline_ms, std::int32_t& detail, F&& body) {
  switch (state_) {
    case GNSDK_STATE_READY:
      break;
    case GNSDK_STATE_BUSY:
      return GNSDK_BUSY;
    case GNSDK_STATE_POISONED:
      return GNSDK_STALE;
    default:
      diag_.log("request refused: session is not READY");
      return GNSDK_INVALID_ARGUMENT;
  }
  detail = GNSDK_DETAIL_NONE;
  state_ = GNSDK_STATE_BUSY;
  cancel_.begin_request(deadline_ms);
  gnsdk_status st;
  try {
    st = body();
    state_ = GNSDK_STATE_READY;
  } catch (const CancelledError& e) {
    state_ = GNSDK_STATE_READY;
    diag_.log(e.timeout ? "request timed out" : "request cancelled");
    st = e.timeout ? GNSDK_TIMEOUT : GNSDK_CANCELLED;
  } catch (const ghidra::UnimplError& e) {
    state_ = GNSDK_STATE_READY;
    diag_.log("unimplemented instruction: " + e.explain);
    detail = GNSDK_DETAIL_UNIMPLEMENTED;
    st = kind == Kind::Decompile ? GNSDK_ENGINE_FAILURE : GNSDK_PARTIAL_UNSUPPORTED;
  } catch (const ghidra::BadDataError& e) {
    state_ = GNSDK_STATE_READY;
    diag_.log("bad instruction data: " + e.explain);
    detail = GNSDK_DETAIL_BAD_DATA;
    st = kind == Kind::Decompile ? GNSDK_ENGINE_FAILURE : GNSDK_PARTIAL_UNSUPPORTED;
  } catch (const ghidra::DataUnavailError& e) {
    state_ = GNSDK_STATE_READY;
    diag_.log("bytes unavailable: " + e.explain);
    detail = GNSDK_DETAIL_MISSING_BYTES;
    st = kind == Kind::Decompile ? GNSDK_ENGINE_FAILURE : GNSDK_PARTIAL_UNSUPPORTED;
  } catch (const ghidra::LowlevelError& e) {
    state_ = GNSDK_STATE_READY;
    diag_.log("engine error: " + e.explain);
    st = GNSDK_ENGINE_FAILURE;
  } catch (const ghidra::DecoderError& e) {
    state_ = GNSDK_STATE_READY;
    diag_.log("decoder error: " + e.explain);
    st = GNSDK_ENGINE_FAILURE;
  } catch (const std::bad_alloc&) {
    poison("bad_alloc during request");
    st = GNSDK_RESOURCE_LIMITED;
  } catch (const std::exception& e) {
    diag_.log(std::string("unexpected exception: ") + e.what());
    poison("unexpected exception during request");
    st = GNSDK_ENGINE_FAILURE;
  } catch (...) {
    poison("unknown exception during request");
    st = GNSDK_ENGINE_FAILURE;
  }
  cancel_.end_request();
  return st;
}

// ---------------------------------------------------------------------------
// Build: raw image
// ---------------------------------------------------------------------------

gnsdk_status Session::load_image(const std::uint8_t* bytes, std::size_t len, std::uint64_t base,
                                 const char* name) {
  if (state_ != GNSDK_STATE_CONFIGURED) {
    diag_.log("load_image refused: session is not CONFIGURED");
    return state_ == GNSDK_STATE_POISONED ? GNSDK_STALE : GNSDK_INVALID_ARGUMENT;
  }
  image_name_ = (name != nullptr && *name != '\0') ? name : "image";
  diag_.log("load_image: " + std::to_string(len) + " bytes at " + hex(base) + " as " + image_name_);
  return run_build("load_image", [&] {
    std::vector<std::uint8_t> copy(bytes, bytes + len);
    store_ = std::make_unique<ghidra::DocumentStorage>();
    auto arch = std::make_unique<BufferArchitecture>(image_name_, language_, &errstream_, std::move(copy), base);
    arch->init(*store_);
    arch_ = std::move(arch);
  });
}

// ---------------------------------------------------------------------------
// Build: <xml_savefile> snapshot (consolemain.cc IfcRestore)
// ---------------------------------------------------------------------------

gnsdk_status Session::open_snapshot(const std::string& path) {
  if (state_ != GNSDK_STATE_CONFIGURED) {
    return state_ == GNSDK_STATE_POISONED ? GNSDK_STALE : GNSDK_INVALID_ARGUMENT;
  }
  image_name_ = path;
  diag_.log("open_snapshot: " + path);
  return run_build("open_snapshot", [&] {
    store_ = std::make_unique<ghidra::DocumentStorage>();
    ghidra::Document* doc = store_->openDocument(path);
    if (doc == nullptr || doc->getRoot() == nullptr) throw ghidra::LowlevelError("empty snapshot document");
    if (doc->getRoot()->getName() != "xml_savefile") {
      throw ghidra::LowlevelError("snapshot root is <" + doc->getRoot()->getName() +
                                  ">, expected <xml_savefile>");
    }
    store_->registerTag(doc->getRoot());
    ghidra::ArchitectureCapability* cap = ghidra::ArchitectureCapability::findCapability(doc);
    if (cap == nullptr) throw ghidra::LowlevelError("no architecture capability accepts this snapshot");
    std::unique_ptr<ghidra::Architecture> arch(cap->buildArchitecture("", "", &errstream_));
    if (!arch) throw ghidra::LowlevelError("capability returned no architecture");
    arch->restoreXml(*store_);
    arch_ = std::move(arch);
    language_ = arch_->getDescription();
  });
}

// ---------------------------------------------------------------------------
// Disassemble / lift
// ---------------------------------------------------------------------------

gnsdk_status Session::disassemble(const gnsdk_range& range, const gnsdk_request_options& opts,
                                  std::string& text, std::int32_t& detail) {
  return run_request(Kind::Disasm, opts.deadline_ms, detail, [&]() -> gnsdk_status {
    checkpoint();
    const std::uint32_t limit = opts.max_instructions != 0 ? opts.max_instructions : kDefaultMaxInstructions;
    AsmCollector emit(text);
    bool partial = false;
    std::uint64_t cur = range.start;
    std::uint32_t count = 0;
    while (cur < range.end) {
      checkpoint();
      if (count >= limit) {
        detail = GNSDK_DETAIL_INSTRUCTION_LIMIT;
        partial = true;
        break;
      }
      ghidra::int4 len = 0;
      try {
        len = arch_->translate->printAssembly(emit, code_address(cur));
      } catch (const ghidra::UnimplError& e) {
        text += hex(cur) + "\t?unimpl\t\n";
        partial = true;
        if (detail == GNSDK_DETAIL_NONE) detail = GNSDK_DETAIL_UNIMPLEMENTED;
        len = e.instruction_length;
        if (len <= 0) break;
      } catch (const ghidra::BadDataError&) {
        text += hex(cur) + "\t?baddata\t\n";
        partial = true;
        if (detail == GNSDK_DETAIL_NONE) detail = GNSDK_DETAIL_BAD_DATA;
        break;
      } catch (const ghidra::DataUnavailError&) {
        partial = true;
        if (detail == GNSDK_DETAIL_NONE) detail = GNSDK_DETAIL_MISSING_BYTES;
        break;
      }
      if (len <= 0) break;
      cur += static_cast<std::uint64_t>(len);
      ++count;
    }
    std::string warn;
    flush_engine_messages(&warn);
    if (partial) return GNSDK_PARTIAL_UNSUPPORTED;
    return warn.empty() ? GNSDK_OK : GNSDK_OK_WARNINGS;
  });
}

gnsdk_status Session::lift(const gnsdk_range& range, const gnsdk_request_options& opts, PcodeStore& store,
                           std::int32_t& detail) {
  return run_request(Kind::Lift, opts.deadline_ms, detail, [&]() -> gnsdk_status {
    checkpoint();
    const std::uint32_t limit = opts.max_instructions != 0 ? opts.max_instructions : kDefaultMaxInstructions;
    PcodeCollector emit(store);
    bool partial = false;
    std::uint64_t cur = range.start;
    std::uint32_t count = 0;
    while (cur < range.end) {
      checkpoint();
      if (count >= limit) {
        detail = GNSDK_DETAIL_INSTRUCTION_LIMIT;
        partial = true;
        break;
      }
      gnsdk_pcode_instr instr{};
      instr.addr = cur;
      instr.first_op = static_cast<std::uint32_t>(store.ops.size());
      ghidra::int4 len = 0;
      bool stop = false;
      try {
        len = arch_->translate->oneInstruction(emit, code_address(cur));
      } catch (const ghidra::UnimplError& e) {
        instr.flags |= GNSDK_INSTR_UNIMPLEMENTED;
        partial = true;
        if (detail == GNSDK_DETAIL_NONE) detail = GNSDK_DETAIL_UNIMPLEMENTED;
        len = e.instruction_length;
        if (len <= 0) stop = true;
      } catch (const ghidra::BadDataError&) {
        instr.flags |= GNSDK_INSTR_BAD_DATA;
        partial = true;
        if (detail == GNSDK_DETAIL_NONE) detail = GNSDK_DETAIL_BAD_DATA;
        stop = true;
      } catch (const ghidra::DataUnavailError&) {
        partial = true;
        if (detail == GNSDK_DETAIL_NONE) detail = GNSDK_DETAIL_MISSING_BYTES;
        break;
      }
      instr.length = len > 0 ? static_cast<std::uint32_t>(len) : 0u;
      instr.num_ops = static_cast<std::uint32_t>(store.ops.size()) - instr.first_op;
      store.instrs.push_back(instr);
      if (stop || len <= 0) break;
      cur += static_cast<std::uint64_t>(len);
      ++count;
    }
    store.finalize();
    std::string warn;
    flush_engine_messages(&warn);
    if (partial) return GNSDK_PARTIAL_UNSUPPORTED;
    return warn.empty() ? GNSDK_OK : GNSDK_OK_WARNINGS;
  });
}

// ---------------------------------------------------------------------------
// Decompile (ifacedecomp.cc IfcAddrrangeLoad / IfcDecompile / IfcPrintCStruct)
// ---------------------------------------------------------------------------

void Session::apply_decompile_options(const gnsdk_decompile_options& opts) {
  // Per-request reset, then options, then the printer, then the cancel hook
  // (resetDefaults rebuilds the root action and drops any earlier hook).
  arch_->resetDefaults();
  if (opts.options_xml != nullptr && *opts.options_xml != '\0') {
    std::istringstream s(opts.options_xml);
    ghidra::XmlDecode decoder(arch_.get());
    decoder.ingestStream(s);
    arch_->options->decode(decoder);
  }
  arch_->setPrintLanguage(opts.printer == 1 ? "java-language" : "c-language");
  if (opts.max_instructions != 0) arch_->max_instructions = opts.max_instructions;
  if (!install_cancel_action(*arch_, &cancel_)) {
    runtime::clear_capability(GNSDK_CAP_CANCEL_IN_ACTION_LOOP);
    diag_.log("cancel hook: universal::fullloop::mainloop not found; in-loop cancel disabled");
  }
}

gnsdk_status Session::decompile(std::uint64_t addr, const gnsdk_decompile_options& opts, std::string& c_text,
                                std::string& tokens, std::string& warnings, std::int32_t& detail) {
  return run_request(Kind::Decompile, opts.deadline_ms, detail, [&]() -> gnsdk_status {
    checkpoint();
    try {
      apply_decompile_options(opts);
    } catch (const ghidra::DecoderError& e) {
      diag_.log("options_xml rejected: " + e.explain);
      flush_engine_messages(&warnings);
      return GNSDK_PROVIDER_FAILURE;
    } catch (const ghidra::LowlevelError& e) {
      diag_.log("options rejected: " + e.explain);
      flush_engine_messages(&warnings);
      return GNSDK_PROVIDER_FAILURE;
    }

    const ghidra::Address entry = code_address(addr);
    ghidra::Scope* scope = arch_->symboltab->getGlobalScope();
    ghidra::Funcdata* fd = scope->queryFunction(entry);
    if (fd == nullptr) {
      std::string name = (opts.function_name != nullptr) ? opts.function_name : std::string();
      if (name.empty()) arch_->nameFunction(entry, name);
      fd = scope->addFunction(entry, name)->getFunction();
      diag_.log("decompile: created function " + name + " at " + hex(addr));
    }
    checkpoint();
    if (fd->hasNoCode()) {
      detail = GNSDK_DETAIL_NO_CODE;
      flush_engine_messages(&warnings);
      return GNSDK_PARTIAL_UNSUPPORTED;
    }
    if (fd->isProcStarted()) arch_->clearAnalysis(fd);

    // Follow flow first, exactly like the console; a RecovError is reported
    // and decompilation still proceeds on whatever flow was recovered.
    try {
      if (opts.follow_flow_limit == 0) {
        ghidra::AddrSpace* spc = fd->getAddress().getSpace();
        fd->followFlow(ghidra::Address(spc, 0), ghidra::Address(spc, spc->getHighest()));
      } else {
        fd->followFlow(fd->getAddress(), fd->getAddress() + static_cast<ghidra::int4>(opts.follow_flow_limit));
      }
    } catch (const ghidra::RecovError& e) {
      diag_.log("followFlow: " + e.explain);
      detail = GNSDK_DETAIL_FLOW_ERROR;
    }
    checkpoint();

    ghidra::Action* root = arch_->allacts.getCurrent();
    root->reset(*fd);
    const ghidra::int4 res = root->perform(*fd);
    if (res < 0) {
      std::ostringstream st;
      root->printState(st);
      diag_.log("perform() broke: " + st.str());
      if (detail == GNSDK_DETAIL_NONE) detail = GNSDK_DETAIL_PERFORM_BREAK;
    }
    checkpoint();

    {
      std::ostringstream out;
      arch_->print->setOutputStream(&out);
      arch_->print->docFunction(fd);
      c_text = out.str();
    }
    if (opts.want_tokens != 0) {
      std::ostringstream out;
      arch_->print->setOutputStream(&out);
      arch_->print->setMarkup(true);
      arch_->print->setPackedOutput(false);
      try {
        arch_->print->docFunction(fd);
      } catch (...) {
        arch_->print->setMarkup(false);
        throw;
      }
      arch_->print->setMarkup(false);
      tokens = out.str();
    }
    flush_engine_messages(&warnings);
    if (res < 0 || detail != GNSDK_DETAIL_NONE) return GNSDK_PARTIAL_UNSUPPORTED;
    return warnings.empty() ? GNSDK_OK : GNSDK_OK_WARNINGS;
  });
}

std::string Session::diagnostics() const { return diag_.text(); }

}  // namespace gnsdk
