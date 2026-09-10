#include "boundary.hpp"

#include <algorithm>
#include <cstring>
#include <memory>
#include <new>
#include <string>

#include "gnsdk/gnsdk_version.h"
#include "pcode_collector.hpp"
#include "runtime.hpp"
#include "session.hpp"

struct gnsdk_session { gnsdk::Session value; explicit gnsdk_session(std::string language) : value(std::move(language)) {} };

namespace {
using gnsdk::Session;
constexpr std::uint32_t request_prefix = offsetof(gnsdk_request_options, deadline_ms);
constexpr std::uint32_t decompile_prefix = offsetof(gnsdk_decompile_options, deadline_ms);
constexpr std::size_t init_required = offsetof(gnsdk_init_options, sleigh_home) + sizeof(const char*);
constexpr std::size_t session_required = offsetof(gnsdk_session_options, language_id) + sizeof(const char*);
constexpr std::size_t image_required = offsetof(gnsdk_image_desc, name) + sizeof(const char*);
constexpr std::size_t request_required = offsetof(gnsdk_request_options, deadline_ms) + sizeof(std::uint64_t);
constexpr std::size_t decompile_required = offsetof(gnsdk_decompile_options, deadline_ms) + sizeof(std::uint64_t);

bool has(const void* p, std::uint32_t supplied, std::size_t end) {
  return p != nullptr && supplied >= end;
}
gnsdk_status require_ready(gnsdk_session* s) {
  if (!gnsdk::runtime::ready()) return GNSDK_NOT_INITIALIZED;
  return s == nullptr ? GNSDK_INVALID_ARGUMENT : GNSDK_OK;
}
void clear_buf(gnsdk_buf* b) { if (b != nullptr) std::memset(b, 0, sizeof(*b)); }
gnsdk_status put(gnsdk_buf* b, const std::string& value, std::uint32_t format) {
  clear_buf(b);
  if (value.empty()) return GNSDK_OK;
  auto* data = new (std::nothrow) std::uint8_t[value.size() + 1];
  if (!data) return GNSDK_RESOURCE_LIMITED;
  std::memcpy(data, value.data(), value.size()); data[value.size()] = 0;
  b->data = data; b->len = value.size(); b->format = format; b->_owner = data;
  return GNSDK_OK;
}
void copy(char* dst, std::size_t cap, const char* src) {
  if (cap == 0) return;
  std::strncpy(dst, src, cap - 1); dst[cap - 1] = '\0';
}
gnsdk_request_options request_opts(const gnsdk_request_options* in) {
  gnsdk_request_options out{}; out.struct_size = sizeof(out);
  if (in != nullptr && in->struct_size >= request_prefix) {
    out.deadline_ms = in->deadline_ms;
    if (has(in, in->struct_size, offsetof(gnsdk_request_options, max_instructions) + sizeof(in->max_instructions))) out.max_instructions = in->max_instructions;
  }
  return out;
}
gnsdk_decompile_options decompile_opts(const gnsdk_decompile_options* in) {
  gnsdk_decompile_options out{}; out.struct_size = sizeof(out);
  if (in != nullptr && in->struct_size >= decompile_prefix) {
    out.deadline_ms = in->deadline_ms;
    if (has(in, in->struct_size, offsetof(gnsdk_decompile_options, max_instructions) + sizeof(in->max_instructions))) out.max_instructions = in->max_instructions;
    if (has(in, in->struct_size, offsetof(gnsdk_decompile_options, want_tokens) + sizeof(in->want_tokens))) out.want_tokens = in->want_tokens;
    if (has(in, in->struct_size, offsetof(gnsdk_decompile_options, printer) + sizeof(in->printer))) out.printer = in->printer;
    if (has(in, in->struct_size, offsetof(gnsdk_decompile_options, follow_flow_limit) + sizeof(in->follow_flow_limit))) out.follow_flow_limit = in->follow_flow_limit;
    if (has(in, in->struct_size, offsetof(gnsdk_decompile_options, options_xml) + sizeof(in->options_xml))) out.options_xml = in->options_xml;
    if (has(in, in->struct_size, offsetof(gnsdk_decompile_options, function_name) + sizeof(in->function_name))) out.function_name = in->function_name;
  }
  return out;
}
}  // namespace

extern "C" {
gnsdk_status gnsdk_init(const gnsdk_init_options* opts) { return gnsdk::guard([&] { if (!opts || opts->struct_size < init_required || !opts->sleigh_home || !*opts->sleigh_home || opts->flags) return GNSDK_INVALID_ARGUMENT; std::string e; return gnsdk::runtime::init(opts->sleigh_home, e); }); }
gnsdk_status gnsdk_shutdown(void) { return gnsdk::guard([] { return gnsdk::runtime::shutdown(); }); }
gnsdk_status gnsdk_version(gnsdk_version_info* out) { return gnsdk::guard([&] { if (!out || out->struct_size < sizeof(std::uint32_t)) return GNSDK_INVALID_ARGUMENT; const auto size = out->struct_size; std::memset(out, 0, std::min<std::size_t>(size, sizeof(*out))); out->struct_size = size; if (has(out,size,offsetof(gnsdk_version_info,abi_major)+sizeof(out->abi_major))) out->abi_major=GNSDK_ABI_MAJOR; if (has(out,size,offsetof(gnsdk_version_info,abi_minor)+sizeof(out->abi_minor))) out->abi_minor=GNSDK_ABI_MINOR; if (has(out,size,offsetof(gnsdk_version_info,abi_patch)+sizeof(out->abi_patch))) out->abi_patch=GNSDK_ABI_PATCH; if (has(out,size,offsetof(gnsdk_version_info,sla_format_version)+sizeof(out->sla_format_version))) out->sla_format_version=GNSDK_SLA_FORMAT_VERSION; if (has(out,size,offsetof(gnsdk_version_info,ghidra_version)+sizeof(out->ghidra_version))) copy(out->ghidra_version,sizeof(out->ghidra_version),GNSDK_GHIDRA_VERSION); if (has(out,size,offsetof(gnsdk_version_info,source)+sizeof(out->source))) copy(out->source,sizeof(out->source),GNSDK_VENDOR_DESCRIBE); if (has(out,size,offsetof(gnsdk_version_info,engine_hash)+sizeof(out->engine_hash))) copy(out->engine_hash,sizeof(out->engine_hash),GNSDK_VENDOR_COMMIT); if (has(out,size,offsetof(gnsdk_version_info,build_flags)+sizeof(out->build_flags))) copy(out->build_flags,sizeof(out->build_flags),GNSDK_BUILD_FLAGS); return GNSDK_OK; }); }
uint64_t gnsdk_capabilities(void) { return gnsdk::runtime::capabilities(); }
const char* gnsdk_status_name(int32_t s) { switch (s) { case GNSDK_OK:return "GNSDK_OK"; case GNSDK_OK_WARNINGS:return "GNSDK_OK_WARNINGS"; case GNSDK_PARTIAL_UNSUPPORTED:return "GNSDK_PARTIAL_UNSUPPORTED"; case GNSDK_CANCELLED:return "GNSDK_CANCELLED"; case GNSDK_TIMEOUT:return "GNSDK_TIMEOUT"; case GNSDK_RESOURCE_LIMITED:return "GNSDK_RESOURCE_LIMITED"; case GNSDK_BUSY:return "GNSDK_BUSY"; case GNSDK_STALE:return "GNSDK_STALE"; case GNSDK_PROVIDER_FAILURE:return "GNSDK_PROVIDER_FAILURE"; case GNSDK_ENGINE_FAILURE:return "GNSDK_ENGINE_FAILURE"; case GNSDK_INVALID_ARGUMENT:return "GNSDK_INVALID_ARGUMENT"; case GNSDK_NOT_INITIALIZED:return "GNSDK_NOT_INITIALIZED"; default:return "GNSDK_UNKNOWN_STATUS"; } }
gnsdk_status gnsdk_language_list(gnsdk_buf* out) { return gnsdk::guard([&] { clear_buf(out); if (!out) return GNSDK_INVALID_ARGUMENT; if (!gnsdk::runtime::ready()) return GNSDK_NOT_INITIALIZED; std::string text; for (const auto& d : ghidra::SleighArchitecture::getDescriptions()) text += d.getId() + "\t" + d.getDescription() + "\t" + d.getProcessor() + "\n"; return put(out,text,GNSDK_BUF_UTF8_LINES); }); }
gnsdk_status gnsdk_session_create(const gnsdk_session_options* opts, gnsdk_session** out) { return gnsdk::guard([&] { if (!out || !opts || opts->struct_size < session_required || opts->flags || !opts->language_id) return GNSDK_INVALID_ARGUMENT; if (!gnsdk::runtime::ready()) return GNSDK_NOT_INITIALIZED; if (gnsdk::runtime::live_session()) return GNSDK_BUSY; std::string e; auto lang=Session::resolve_language(opts->language_id,e); if (lang.empty()) return GNSDK_INVALID_ARGUMENT; auto p=std::unique_ptr<gnsdk_session>(new gnsdk_session(lang)); gnsdk::runtime::set_live_session(&p->value); *out=p.release(); return GNSDK_OK; }); }
gnsdk_status gnsdk_session_load_image(gnsdk_session* s,const gnsdk_image_desc* image) { return gnsdk::guard([&] { auto st=require_ready(s); if(st!=GNSDK_OK) return st; if(!image||image->struct_size<image_required||image->flags||!image->bytes||!image->len) return GNSDK_INVALID_ARGUMENT; return s->value.load_image(image->bytes,image->len,image->base,image->name); }); }
gnsdk_status gnsdk_session_open_snapshot(const gnsdk_session_options* opts, const char* path, gnsdk_session** out) { return gnsdk::guard([&] { if (!out || !opts || opts->struct_size < session_required || opts->flags || !path || !*path) return GNSDK_INVALID_ARGUMENT; if (!gnsdk::runtime::ready()) return GNSDK_NOT_INITIALIZED; if (gnsdk::runtime::live_session()) return GNSDK_BUSY; auto p=std::unique_ptr<gnsdk_session>(new gnsdk_session("")); gnsdk::runtime::set_live_session(&p->value); const auto st=p->value.open_snapshot(path); if (st == GNSDK_OK || st == GNSDK_PROVIDER_FAILURE || st == GNSDK_ENGINE_FAILURE || st == GNSDK_RESOURCE_LIMITED) { *out=p.release(); return st; } gnsdk::runtime::set_live_session(nullptr); return st; }); }
gnsdk_status gnsdk_disassemble(gnsdk_session* s,const gnsdk_range* range,const gnsdk_request_options* opts,gnsdk_buf* out) { return gnsdk::guard([&] { clear_buf(out); auto st=require_ready(s); if(st!=GNSDK_OK||!range||!out||range->end<range->start || (opts && opts->struct_size<request_required)) return st==GNSDK_OK?GNSDK_INVALID_ARGUMENT:st; std::string text; std::int32_t detail=0; st=s->value.disassemble(*range,request_opts(opts),text,detail); auto putst=put(out,text,GNSDK_BUF_UTF8_LINES); return putst==GNSDK_OK?st:putst; }); }
gnsdk_status gnsdk_lift(gnsdk_session* s,const gnsdk_range* range,const gnsdk_request_options* opts,gnsdk_pcode_out* out) { return gnsdk::guard([&] { const auto size=out?out->struct_size:0; if(out && size >= sizeof(std::uint32_t)) { std::memset(out,0,std::min<std::size_t>(size,sizeof(*out))); out->struct_size=size; } auto st=require_ready(s); if(st!=GNSDK_OK||!range||!out||size<sizeof(*out)||range->end<range->start || (opts && opts->struct_size<request_required)) return st==GNSDK_OK?GNSDK_INVALID_ARGUMENT:st; auto store=std::make_unique<gnsdk::PcodeStore>(); std::int32_t detail=0; st=s->value.lift(*range,request_opts(opts),*store,detail); store->finalize(); out->status_detail=detail; out->num_spaces=store->space_ptrs.size(); out->num_ops=store->ops.size(); out->num_varnodes=store->varnodes.size(); out->num_instrs=store->instrs.size(); out->space_names=store->space_ptrs.data(); out->ops=store->ops.data(); out->varnodes=store->varnodes.data(); out->instrs=store->instrs.data(); out->_owner=store.release(); return st; }); }
void gnsdk_pcode_free(gnsdk_pcode_out* out) { if (!out) return; delete static_cast<gnsdk::PcodeStore*>(out->_owner); std::memset(out,0,sizeof(*out)); }
gnsdk_status gnsdk_decompile(gnsdk_session* s,uint64_t addr,const gnsdk_decompile_options* opts,gnsdk_decompile_out* out) { return gnsdk::guard([&] { const auto size=out?out->struct_size:0; if(out && size >= sizeof(std::uint32_t)) { std::memset(out,0,std::min<std::size_t>(size,sizeof(*out))); out->struct_size=size; } auto st=require_ready(s); if(st!=GNSDK_OK||!out||size<sizeof(*out) || (opts && opts->struct_size<decompile_required)) return st==GNSDK_OK?GNSDK_INVALID_ARGUMENT:st; std::string c,t,w; std::int32_t detail=0; st=s->value.decompile(addr,decompile_opts(opts),c,t,w,detail); out->status_detail=detail; auto a=put(&out->c_text,c,GNSDK_BUF_UTF8_TEXT), b=put(&out->tokens,t,GNSDK_BUF_XML_UTF8), d=put(&out->warnings,w,GNSDK_BUF_UTF8_TEXT); return a!=GNSDK_OK?a:(b!=GNSDK_OK?b:(d!=GNSDK_OK?d:st)); }); }
void gnsdk_session_cancel(gnsdk_session* s) { if(s) s->value.cancel(); }
gnsdk_status gnsdk_session_diagnostics(gnsdk_session* s,gnsdk_buf* out) { return gnsdk::guard([&] { clear_buf(out); auto st=require_ready(s); if(st!=GNSDK_OK||!out) return st==GNSDK_OK?GNSDK_INVALID_ARGUMENT:st; return put(out,s->value.diagnostics(),GNSDK_BUF_UTF8_TEXT); }); }
gnsdk_status gnsdk_session_get_state(gnsdk_session* s,uint32_t* out) { return gnsdk::guard([&] { if(!s||!out) return GNSDK_INVALID_ARGUMENT; *out=s->value.state(); return GNSDK_OK; }); }
gnsdk_status gnsdk_session_destroy(gnsdk_session* s) { return gnsdk::guard([&] { if(!s) return GNSDK_OK; if(gnsdk::runtime::live_session()==&s->value) gnsdk::runtime::set_live_session(nullptr); delete s; return GNSDK_OK; }); }
void gnsdk_buf_free(gnsdk_buf* b) { if(!b) return; delete[] static_cast<std::uint8_t*>(b->_owner); clear_buf(b); }
}
