/*
 * gnsdk.h - C ABI (v0) over Ghidra's unmodified native SLEIGH + decompiler.
 *
 * Pure C99. Every identifier starts with gnsdk_ / GNSDK_.
 *
 * Numeric tables (status codes, capability bits, session states, buffer
 * formats, status details) are mirrored in native/conformance/status_codes.json
 * which is the single source for the Python and Rust consumers. Keep them in
 * sync; ctest abi_status_table checks this header against that file.
 *
 * ---------------------------------------------------------------------------
 * PROCESS MODEL AND THREADING
 * ---------------------------------------------------------------------------
 * The upstream engine keeps process-global state (loaded .sla translators,
 * language descriptions, an append-only spec path list) and its XML / bison /
 * flex parsers are not reentrant. Therefore:
 *
 *   - gnsdk_init() is once per process. Calling it again with the same
 *     sleigh home returns GNSDK_OK; a different home returns GNSDK_STALE.
 *   - gnsdk_shutdown() is a state transition, not a teardown. Process exit is
 *     the teardown. After shutdown every call except gnsdk_init, gnsdk_version,
 *     gnsdk_capabilities, gnsdk_status_name and gnsdk_buf_free returns
 *     GNSDK_NOT_INITIALIZED. gnsdk_init with the same home re-enables the API.
 *   - Exactly ONE live session per process. A second gnsdk_session_create /
 *     gnsdk_session_open_snapshot while one is live returns GNSDK_BUSY.
 *   - No function is thread-safe and no handle may be used from two threads,
 *     with ONE exception: gnsdk_session_cancel() may be called from any thread
 *     or from a signal handler while a request is in flight on that session.
 *   - Fatal signals inside the engine kill the process; there is no recovery.
 *
 * ---------------------------------------------------------------------------
 * SESSION STATE MACHINE
 * ---------------------------------------------------------------------------
 *   CREATED --create--> CONFIGURED --load_image--> READY <--> BUSY
 *   open_snapshot ------------------------------> READY
 *   any hard failure inside the engine ---------> POISONED
 *   destroy ------------------------------------> DESTROYED (handle is freed)
 *
 * A request (disassemble / lift / decompile) requires READY. Requests on a
 * POISONED session return GNSDK_STALE; destroy it and create a new one. A
 * failed load_image / open_snapshot leaves the session POISONED (its
 * diagnostics explain why) and the handle must still be destroyed.
 *
 * Status classes for a request:
 *   engine LowlevelError          -> GNSDK_ENGINE_FAILURE, session stays READY
 *   UnimplError / BadDataError in
 *   lift or disassemble           -> GNSDK_PARTIAL_UNSUPPORTED, READY
 *   std::bad_alloc                -> GNSDK_RESOURCE_LIMITED, POISONED
 *   any other C++ exception       -> GNSDK_ENGINE_FAILURE, POISONED
 *   cancel flag observed          -> GNSDK_CANCELLED, READY
 *   deadline observed             -> GNSDK_TIMEOUT, READY
 *   failure during load/restore   -> GNSDK_PROVIDER_FAILURE, POISONED
 *
 * ---------------------------------------------------------------------------
 * OWNERSHIP
 * ---------------------------------------------------------------------------
 *   - Every gnsdk_buf the library fills is owned by the library. Release it
 *     with gnsdk_buf_free() and nothing else (not free()). data is always
 *     NUL-terminated; len excludes the terminator. An empty result has
 *     data == NULL, len == 0. Freeing a zeroed gnsdk_buf is a no-op.
 *   - gnsdk_pcode_out arrays are owned by the library; release with
 *     gnsdk_pcode_free(). space_names strings live as long as the out struct.
 *   - Strings returned by gnsdk_status_name() are static.
 *   - Input pointers (bytes, paths, XML) are only read during the call;
 *     the library copies what it must keep (image bytes are copied).
 *   - A session handle is freed by gnsdk_session_destroy() only.
 *
 * ---------------------------------------------------------------------------
 * STRUCT VERSIONING
 * ---------------------------------------------------------------------------
 * Every options / out struct starts with uint32_t struct_size. Set it with
 * GNSDK_INIT_STRUCT(&s) (zero-fills, then writes sizeof). The library reads
 * only the fields that fit inside the caller's struct_size and treats missing
 * trailing fields as zero; a larger struct_size than the library knows is
 * accepted and the extra bytes are ignored. struct_size smaller than the
 * first known layout returns GNSDK_INVALID_ARGUMENT.
 *
 * All functions are noexcept in effect: a catch-all sits at the boundary.
 */
#ifndef GNSDK_H
#define GNSDK_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --------------------------------------------------------------------- */
/* Export macro                                                          */
/* --------------------------------------------------------------------- */
#if defined(_WIN32)
#  if defined(GNSDK_BUILDING) && defined(GNSDK_SHARED_BUILD)
#    define GNSDK_API __declspec(dllexport)
#  elif defined(GNSDK_SHARED_BUILD)
#    define GNSDK_API __declspec(dllimport)
#  else
#    define GNSDK_API
#  endif
#elif defined(__GNUC__) || defined(__clang__)
#  define GNSDK_API __attribute__((visibility("default")))
#else
#  define GNSDK_API
#endif

/* --------------------------------------------------------------------- */
/* ABI version                                                           */
/* --------------------------------------------------------------------- */
#define GNSDK_ABI_MAJOR 0
#define GNSDK_ABI_MINOR 1
#define GNSDK_ABI_PATCH 0

/* Zero-fill a struct and set its struct_size. Use on every options/out struct. */
#define GNSDK_INIT_STRUCT(p)                                   \
  do {                                                          \
    memset((p), 0, sizeof(*(p)));                               \
    (p)->struct_size = (uint32_t)sizeof(*(p));                  \
  } while (0)

/* --------------------------------------------------------------------- */
/* Status codes (mirror of status_codes.json "status")                   */
/* --------------------------------------------------------------------- */
typedef enum gnsdk_status {
  GNSDK_OK = 0,
  GNSDK_OK_WARNINGS = 1,
  GNSDK_PARTIAL_UNSUPPORTED = 2,
  GNSDK_CANCELLED = 10,
  GNSDK_TIMEOUT = 11,
  GNSDK_RESOURCE_LIMITED = 12,
  GNSDK_BUSY = 13,
  GNSDK_STALE = 14,
  GNSDK_PROVIDER_FAILURE = 20,
  GNSDK_ENGINE_FAILURE = 21,
  GNSDK_INVALID_ARGUMENT = 30,
  GNSDK_NOT_INITIALIZED = 31
} gnsdk_status;

/* Secondary detail for a request result ("status_detail" in the JSON). */
typedef enum gnsdk_status_detail {
  GNSDK_DETAIL_NONE = 0,
  GNSDK_DETAIL_PERFORM_BREAK = 1,     /* action perform() returned < 0        */
  GNSDK_DETAIL_NO_CODE = 2,           /* function has no code body            */
  GNSDK_DETAIL_MISSING_BYTES = 3,     /* engine read past the loaded image    */
  GNSDK_DETAIL_UNIMPLEMENTED = 4,     /* SLEIGH: unimplemented instruction    */
  GNSDK_DETAIL_BAD_DATA = 5,          /* SLEIGH: bytes do not decode          */
  GNSDK_DETAIL_FLOW_ERROR = 6,        /* followFlow raised RecovError         */
  GNSDK_DETAIL_INSTRUCTION_LIMIT = 7  /* max_instructions reached             */
} gnsdk_status_detail;

/* --------------------------------------------------------------------- */
/* Capability bits (bit index; mirror of "capabilities")                 */
/* --------------------------------------------------------------------- */
#define GNSDK_CAP_RAW_IMAGE             (UINT64_C(1) << 0)
#define GNSDK_CAP_SNAPSHOT_XML_V0       (UINT64_C(1) << 1)
#define GNSDK_CAP_DISASM                (UINT64_C(1) << 2)
#define GNSDK_CAP_LIFT                  (UINT64_C(1) << 3)
#define GNSDK_CAP_DECOMPILE_C           (UINT64_C(1) << 4)
#define GNSDK_CAP_TOKENS_XML_V0         (UINT64_C(1) << 5)
#define GNSDK_CAP_CANCEL_COOPERATIVE    (UINT64_C(1) << 6)
#define GNSDK_CAP_CANCEL_IN_ACTION_LOOP (UINT64_C(1) << 7)
#define GNSDK_CAP_BFD                   (UINT64_C(1) << 8)
#define GNSDK_CAP_JAVA_PRINTER          (UINT64_C(1) << 9)

/* --------------------------------------------------------------------- */
/* Session states (mirror of "session_states")                           */
/* --------------------------------------------------------------------- */
typedef enum gnsdk_session_state {
  GNSDK_STATE_CREATED = 0,
  GNSDK_STATE_CONFIGURED = 1,
  GNSDK_STATE_READY = 2,
  GNSDK_STATE_BUSY = 3,
  GNSDK_STATE_POISONED = 4,
  GNSDK_STATE_DESTROYED = 5
} gnsdk_session_state;

/* --------------------------------------------------------------------- */
/* Buffers (mirror of "buffer_formats")                                  */
/* --------------------------------------------------------------------- */
typedef enum gnsdk_buf_format {
  GNSDK_BUF_NONE = 0,       /* empty                                        */
  GNSDK_BUF_UTF8_TEXT = 1,  /* free-form UTF-8 text                         */
  GNSDK_BUF_UTF8_LINES = 2, /* UTF-8, one record per '\n', tab-separated     */
  GNSDK_BUF_XML_UTF8 = 3    /* UTF-8 XML document                           */
} gnsdk_buf_format;

/*
 * Library-owned byte buffer. Zero-initialise before passing in; free with
 * gnsdk_buf_free(). Never touch _owner.
 */
typedef struct gnsdk_buf {
  uint8_t *data;       /* NUL-terminated; NULL when len == 0                 */
  size_t len;          /* bytes, excluding the terminator                    */
  uint32_t format;     /* gnsdk_buf_format                                   */
  uint32_t _reserved;
  void *_owner;        /* library bookkeeping                                */
} gnsdk_buf;

/* --------------------------------------------------------------------- */
/* Opaque session                                                        */
/* --------------------------------------------------------------------- */
typedef struct gnsdk_session gnsdk_session;

/* --------------------------------------------------------------------- */
/* Structs                                                               */
/* --------------------------------------------------------------------- */

typedef struct gnsdk_version_info {
  uint32_t struct_size;
  uint32_t abi_major;
  uint32_t abi_minor;
  uint32_t abi_patch;
  uint32_t sla_format_version;   /* upstream slaformat.cc FORMAT_VERSION     */
  uint32_t _reserved;
  char ghidra_version[32];       /* e.g. "12.1.3"                            */
  char source[64];               /* git describe of vendor/ghidra at build   */
  char engine_hash[48];          /* full commit hash of vendor/ghidra        */
  char build_flags[128];         /* "type=RelWithDebInfo;sanitize=;shared=0" */
} gnsdk_version_info;

typedef struct gnsdk_init_options {
  uint32_t struct_size;
  uint32_t flags;                /* reserved, must be 0                      */
  const char *sleigh_home;       /* dir scanned like Ghidra's install root   */
} gnsdk_init_options;

typedef struct gnsdk_session_options {
  uint32_t struct_size;
  uint32_t flags;                /* reserved, must be 0                      */
  /*
   * Language id, "proc:endian:size:variant" or with a trailing ":compiler".
   * When the compiler segment is absent the language's first compiler is
   * used. Ignored by gnsdk_session_open_snapshot (the savefile carries it).
   */
  const char *language_id;
} gnsdk_session_options;

typedef struct gnsdk_image_desc {
  uint32_t struct_size;
  uint32_t flags;                /* reserved, must be 0                      */
  const uint8_t *bytes;          /* copied by the library                    */
  size_t len;                    /* > 0                                      */
  uint64_t base;                 /* address of bytes[0] in the code space    */
  const char *name;              /* optional image name for diagnostics      */
} gnsdk_image_desc;

/* Half-open address range [start, end) in the default code space. */
typedef struct gnsdk_range {
  uint64_t start;
  uint64_t end;
} gnsdk_range;

typedef struct gnsdk_request_options {
  uint32_t struct_size;
  uint32_t flags;                /* reserved, must be 0                      */
  uint64_t deadline_ms;          /* 0 = none; advisory, checked at points    */
  uint32_t max_instructions;     /* 0 = default (65536) for lift/disasm      */
  uint32_t _reserved;
} gnsdk_request_options;

typedef struct gnsdk_decompile_options {
  uint32_t struct_size;
  uint32_t flags;                /* reserved, must be 0                      */
  uint64_t deadline_ms;          /* 0 = none                                 */
  uint32_t max_instructions;     /* 0 = engine default                       */
  uint32_t want_tokens;          /* 1 = also produce EmitMarkup XML tokens   */
  uint32_t printer;              /* 0 = c-language, 1 = java-language        */
  uint32_t follow_flow_limit;    /* 0 = whole space, else bytes from entry   */
  const char *options_xml;       /* optional <optionslist> applied per call  */
  const char *function_name;     /* optional name for a newly created func   */
} gnsdk_decompile_options;

typedef struct gnsdk_decompile_out {
  uint32_t struct_size;
  int32_t status_detail;         /* gnsdk_status_detail                      */
  gnsdk_buf c_text;              /* UTF8_TEXT                                */
  gnsdk_buf tokens;              /* XML_UTF8 when want_tokens                */
  gnsdk_buf warnings;            /* UTF8_TEXT; engine messages for this call */
} gnsdk_decompile_out;

/* One p-code operation. opcode is upstream OpCode (versioned by ghidra_version). */
typedef struct gnsdk_pcode_op {
  uint32_t opcode;
  int32_t output_index;          /* index into varnodes, or -1               */
  uint32_t first_input;          /* index into varnodes                      */
  uint32_t num_inputs;
  uint64_t instr_addr;
} gnsdk_pcode_op;

typedef struct gnsdk_varnode {
  uint32_t space;                /* index into space_names                   */
  uint32_t size;
  uint64_t offset;
} gnsdk_varnode;

typedef struct gnsdk_pcode_instr {
  uint64_t addr;
  uint32_t length;               /* bytes                                    */
  uint32_t first_op;             /* index into ops                           */
  uint32_t num_ops;
  uint32_t flags;                /* bit0: unimplemented, bit1: bad data      */
} gnsdk_pcode_instr;

#define GNSDK_INSTR_UNIMPLEMENTED 1u
#define GNSDK_INSTR_BAD_DATA      2u

typedef struct gnsdk_pcode_out {
  uint32_t struct_size;
  int32_t status_detail;         /* gnsdk_status_detail                      */
  uint32_t num_spaces;
  uint32_t num_ops;
  uint32_t num_varnodes;
  uint32_t num_instrs;
  const char *const *space_names;
  const gnsdk_pcode_op *ops;
  const gnsdk_varnode *varnodes;
  const gnsdk_pcode_instr *instrs;
  void *_owner;                  /* library bookkeeping                      */
} gnsdk_pcode_out;

/* --------------------------------------------------------------------- */
/* Process-level API                                                     */
/* --------------------------------------------------------------------- */

/* Initialise the engine once per process. See PROCESS MODEL above. */
GNSDK_API gnsdk_status gnsdk_init(const gnsdk_init_options *opts);

/*
 * Mark the API shut down. Returns GNSDK_BUSY while a session is live,
 * GNSDK_NOT_INITIALIZED if never initialised. Does not free engine state.
 */
GNSDK_API gnsdk_status gnsdk_shutdown(void);

/* Fill version info. Works before gnsdk_init. */
GNSDK_API gnsdk_status gnsdk_version(gnsdk_version_info *out);

/* Capability bit set. Works before gnsdk_init. */
GNSDK_API uint64_t gnsdk_capabilities(void);

/* Static enum name for a status ("GNSDK_OK"); "GNSDK_UNKNOWN_STATUS" otherwise. */
GNSDK_API const char *gnsdk_status_name(int32_t status);

/*
 * UTF8_LINES buffer: one "id\tdescription\tprocessor" line per language
 * known to the loaded sleigh home. Requires gnsdk_init.
 */
GNSDK_API gnsdk_status gnsdk_language_list(gnsdk_buf *out);

/* --------------------------------------------------------------------- */
/* Session API                                                           */
/* --------------------------------------------------------------------- */

/*
 * Create a session for a language (state CONFIGURED). Unknown language id
 * returns GNSDK_INVALID_ARGUMENT with *out untouched. GNSDK_BUSY when a
 * session is already live.
 */
GNSDK_API gnsdk_status gnsdk_session_create(const gnsdk_session_options *opts,
                                            gnsdk_session **out);

/*
 * Load a raw byte image (copied) at base and build the architecture
 * (CONFIGURED -> READY). On failure the session becomes POISONED.
 */
GNSDK_API gnsdk_status gnsdk_session_load_image(gnsdk_session *s,
                                                const gnsdk_image_desc *img);

/*
 * Open an <xml_savefile> snapshot (Ghidra DecompileDebug format) and build
 * the architecture (READY). On an engine or provider failure *out receives
 * a POISONED handle whose diagnostics explain the failure; destroy it. On
 * GNSDK_INVALID_ARGUMENT / GNSDK_BUSY / GNSDK_NOT_INITIALIZED *out is untouched.
 */
GNSDK_API gnsdk_status gnsdk_session_open_snapshot(const gnsdk_session_options *opts,
                                                   const char *path,
                                                   gnsdk_session **out);

/*
 * Disassemble [range.start, range.end). text is UTF8_LINES:
 * "0x<addr>\t<mnemonic>\t<operands>\n"; unimplemented / undecodable
 * instructions appear as "\t?unimpl\t" / "\t?baddata\t" and make the result
 * GNSDK_PARTIAL_UNSUPPORTED. opts may be NULL.
 */
GNSDK_API gnsdk_status gnsdk_disassemble(gnsdk_session *s, const gnsdk_range *range,
                                         const gnsdk_request_options *opts,
                                         gnsdk_buf *text);

/* Lift [range.start, range.end) to raw p-code. opts may be NULL. */
GNSDK_API gnsdk_status gnsdk_lift(gnsdk_session *s, const gnsdk_range *range,
                                  const gnsdk_request_options *opts,
                                  gnsdk_pcode_out *out);

/* Release arrays produced by gnsdk_lift. Safe on a zeroed struct. */
GNSDK_API void gnsdk_pcode_free(gnsdk_pcode_out *out);

/*
 * Decompile the function at addr. Creates the function if the symbol table
 * has none at that address. opts may be NULL. Results and their status:
 *   GNSDK_OK / GNSDK_OK_WARNINGS  c_text filled
 *   GNSDK_PARTIAL_UNSUPPORTED     c_text may be partial; see status_detail
 */
GNSDK_API gnsdk_status gnsdk_decompile(gnsdk_session *s, uint64_t addr,
                                       const gnsdk_decompile_options *opts,
                                       gnsdk_decompile_out *out);

/*
 * Request cancellation of the in-flight request on s. Async-signal-safe:
 * one relaxed atomic store, no locks, no allocation. A cancel with no request
 * in flight is a no-op (the flag is cleared when the next request starts).
 */
GNSDK_API void gnsdk_session_cancel(gnsdk_session *s);

/* UTF8_TEXT: bounded event log + engine messages for this session. */
GNSDK_API gnsdk_status gnsdk_session_diagnostics(gnsdk_session *s, gnsdk_buf *out);

/* Current gnsdk_session_state. */
GNSDK_API gnsdk_status gnsdk_session_state(gnsdk_session *s, uint32_t *state);

/* Destroy the session and free the handle. NULL is a no-op. */
GNSDK_API gnsdk_status gnsdk_session_destroy(gnsdk_session *s);

/* Release a library-owned buffer and zero the struct. NULL / zeroed = no-op. */
GNSDK_API void gnsdk_buf_free(gnsdk_buf *buf);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* GNSDK_H */
