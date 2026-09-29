# Catalog contracts for Code Browser parity

Date: 2026-09-29

Status: **proposed design contracts only.** Nothing here is implemented, advertised
in `GET /api/v1/actions`, or authorized to run. Every catalog name below is
**proposed**. No server, test, build, job, detector or 8080 request was run to
write it, and nothing under `src/` or any frontend was read. Live use follows
[AGENTS](../../AGENTS.md) (see [Authorization](#authorization)).

This is the backend contract the parity designs assume. It starts from the
"Backend and catalog gaps" of the
[Code Browser parity specification](2026-09-29-ghidra-code-browser-parity.md)
(16 read, 25 write and 3 contract gaps) and adds every "catalog action needed"
and every consumer-provided field named in the design-system component READMEs
under [`docs/design-system/project/components/`](../design-system/project/components/):
the 20 parity components, the 11 "Parity extensions (2026-09-29)" sections, and
the compiler-aware and outputs components (PointerWalk, CompilerLayer,
TransformTimeline, MatchExplain, FrameLayout, VTableBrowser, OutputsCatalog,
ArtifactCard, ToolchainEvidence, VariantRelation).

**Counts.** 107 contract entries: 36 reads (R01–R36), 37 writes (W01–W37),
18 jobs (J01–J18) and 16 contract or schema gaps (G01–G16). R35–R36, W35–W37 and J16–J18 were added in round 3 (see "Round 3 additions"). The parity rows each
entry unblocks are named in the entry; the parity matrix's "Backend status"
column names the entry ids per row.

## What the docs already provide

Existing surface this contract builds on, so nothing is designed twice:

- **Catalog shape.** Catalog verbs are `group.verb`, posted as
  `POST /api/v1/actions/{id}` on 8080
  ([ladder plan](../plans/2026-09-08-0156-feat-recovery-pipeline-ladder-plan.md):120);
  examples are `corpus.extract-stabs` → `corpus.match-pair`
  ([consolidated plan](2026-09-21-consolidated-design-plan.md):87),
  `corpus.objdiff-check` and `corpus.diff-builds`
  ([outputs inventory](../research/2026-09-29-exports-and-outputs-inventory.md):84, :78).
  Catalog job receipts with reservations are delivered (bounded)
  (outputs inventory:105).
- **Admission flags.** U104 assigns `mutating`, `long_running` and
  `identity_scope` to expert verbs
  ([portable-substrate plan](../plans/2026-09-21-portable-signatures-codecaves-generic-plan.md):1898-1903);
  risk H5 records that admission cannot drain verbs without them
  ([risk register](../plans/2026-09-21-risk-register.md):51). Admission must use
  real owner state, not the flag: a bulk verb advertises `mutating:false` while it
  writes (consolidated plan:464-467).
- **MCP tools** ([TOOLS_LIST](../../TOOLS_LIST.md)): reads `get-references`
  (:844, `direction`, `includeFlow` :875, `resolve-thunk` :884),
  `inspect-memory` (:924; `get-memory-blocks` :944 and `list_data_items` :942),
  `get-data` (:754), `get-function` (:772, a stub), `decompile-function` (:466),
  `get-call-graph` (:660, `common_callers` :669), `analyze-data-flow` (:215),
  `analyze-vtables` (:284), `search-code` (:1558), `search-constants` (:1591),
  `search-everything` (:1622), `manage-strings` (:1269). Writes
  `manage-function` (:1236), `manage-structures` (:1294), `manage-data-types`
  (:1146), `manage-symbols` (:1334), `manage-comments` (:1115),
  `manage-bookmarks` (:1088), `manage-function-tags` (:1218), `create-label`
  (:455), `apply-data-type` (:325), `change-processor` (:360), `export` (:551,
  formats :560), `checkout-program` (:424), `checkin-program` (:394),
  `checkout-status` (:440), `sync-project` (:522), `svr-admin` (:1693),
  `execute-script` (:1459, a placeholder with no documented parameters),
  `migrate-metadata` (:1435), `match-function` (:1362) and
  `resolve-modification-conflict` (:1543). Most `manage-*` mode lists read only
  "See MCP schema / `registry.py` TOOL_PARAMS" (for example :1239).
- **Function editing.** `manage-function` routes property, storage, prototype,
  convention, variable, create and delete operations through program
  transactions and conflicts, with `set_calling_convention` and `set_storage`
  modes; parameter storage is partial or defective
  ([guide inventory](2026-09-20-ghidra-guide-capability-inventory.md):36-38).
  Structures have list, info, create, update, delete and validate (:39);
  vtables have candidate analysis only (:40).
- **Patch and script.** No bounded patch or assemble tool exists; scripting
  exposes `setBytes`, `clearListing`, `removeDataAt` and `disassemble`
  (guide inventory:99-101), and a first-class patch needs original-byte preview,
  exact target, confirmation, a transaction or conflict receipt and a post-write
  read (:105).
- **Evidence and receipts.** `identity`, `match`, `logical_function` are partial
  (outputs inventory:95); `logical_entity` and struct, field and vtable tables
  are future (:99); the calibration record is future (:101); content-addressed
  receipts are future (:79); the `basis_hash` determinism object is partial
  (:108); `program_binding` project state is delivered (:119); the divergence
  report is future (:78). Persisted results are collected by submission index
  in a total order (portable-substrate plan:1125-1133).
- **Compiler-aware views.** Units U192–U198 are design only and read stored
  parses, detector output, records, receipts and comparison results; none of them
  compiles, compares, detects, binds, exports or opens a program to draw itself
  ([linked views](2026-09-29-linked-views-and-accessibility.md):426, :436).
  Whether anchor pairs are exposed to both surfaces is not verified from docs
  (:177, :566, :576). The toolchain research names Rich header, linker, PDB and
  pinning evidence ([MSVC research](../research/2026-09-29-msvc-optimization-for-decomp.md):1392, :1434, :1475);
  STRATEGY requires toolchain records with compiler and linker hashes
  ([STRATEGY](../../STRATEGY.md):136).

What is new: every entry below except where "Today" names an existing tool that
already does the whole job. The `program.` group name is new; `corpus.` and
`workbench.` follow the existing groups.

## Conventions every entry follows

These are the shared contract terms. An entry restates a term only when it
differs.

- **Naming.** Catalog ids are `group.verb-noun`. `program.` acts on one Ghidra
  program of one build; `corpus.` acts across builds or on the evidence store;
  `workbench.` acts on the workbench. Where an MCP tool already owns the domain,
  the provider is a new mode of that tool (for example "new `manage-function`
  modes") and the catalog id is how it is advertised. A second implementation of
  the same mutation is not proposed (guide inventory:36).
- **Build target.** `build` is one project program (build slug plus
  `programPath`). Reads take `build` or `builds` (a list or `"all"`). Writes take
  exactly one `build`; `"all"` is refused, and another build is another call
  (PatchEditor, TypeManager and SignatureEditor READMEs).
- **Read envelope (G04).** Every read returns `scope`, and per build
  `state` (`read` · `not_loaded` · `unsupported` · `not_indexed`), `basis`
  (`generation`, `digest`), `read_at`, `truncated` with the limit, and rows.
  A build that was not read is never reported as zero.
- **Evidence fields (G05)** and **variance fields (G06)** are attached to any
  value whose certainty varies.
- **Read defaults.** `mutating=false`, `long_running=false`,
  `identity_scope=none`. No receipt; the read stamp is the basis and time.
  Deterministic: rows in a total order (address, then stable id). No conflicts.
  A read never analyzes, decompiles, re-disassembles or opens a program; a closed
  program answers `not_loaded`. Nothing propagates.
- **Write defaults (G08).** `mutating=true`, `long_running=false`,
  `identity_scope=program` (the build's one Ghidra writer). Inputs always
  include `build`, `expected_basis` and `idempotency_key`. The job receipt
  (outputs inventory:105) plus a transaction record (`transaction_id`, name,
  change count) and a post-write re-read of the changed object are the receipts.
  A repeated key returns the existing job; an unchanged draft posts nothing and
  answers "no change to submit". A changed basis or overwritten custom data
  returns `conflictId` for `resolve-modification-conflict`. A held writer makes
  the job wait at admission with the owner as recorded (PID, start time,
  command); nothing is killed or restarted. No analysis follows (NA).
  **Never propagated**: J14 is the only propagation path.
- **Job defaults.** `long_running=true`; admitted through the catalog and the
  workflow's pause/resume; produces a content-addressed receipt with its basis
  and inputs. Reuse first: a receipt whose basis is unchanged is returned and
  labelled reused, and a fresh run is only on request.
- **identity_scope vocabulary (G07), proposed:** `none`, `program` (one build's
  Ghidra program), `archive` (one type archive), `project` (the Ghidra project or
  repository), `database` (the corpus store, as U104 assigns to backfill),
  `output-tree` (an artifact tree, as U104 assigns to export verbs) and
  `evidence-store` (detector, toolchain and classifier records; new).

## Reads

Every read uses the read defaults above unless stated.

### R01 · `program.listing-rows` · proposed · read
- **In:** `build`; an address range or section and page (`start`, `limit`,
  `cursor`); optional field set.
- **Out:** code units in address order: address, bytes, mnemonic, operands
  (typed: register, scalar, address, symbol), labels (primary first, with source
  tier), comments by kind (EOL, pre, post, plate, repeatable), flow targets with
  ref-type, xref counts, the function header (signature, signature source,
  call-fixup, purge, tags, repeatable comment), variable rows, and expandable data
  components with field names and offsets. A computed flow target carries
  evidence `hypothesis` with basis "jump-table inference".
- **Per build:** one build per call; builds are compared only through R25.
- **Consumers:** Listing, ListingFieldLayout, OverviewBar (cursor rule),
  SplitCompare, HeldPane.
- **Unblocks:** L01, and the section-wide form of L06–L09, L13, N03.
- **Today:** `inspect-memory` `disasm` (TOOLS_LIST:924) reads a bounded range;
  `get-function` is a stub (:772). **New:** paging over a whole section and the
  typed row schema.

### R02 · `program.code-unit-extras` · proposed · read
- **In:** `build`; a loaded range; `fields` from p-code, stack depth, register
  transitions, file offset, source map.
- **Out:** per code unit: p-code ops (raw varnodes optional), stack depth or
  `unknown` (never a bogus number), register transitions, file offset or
  `not_mapped`, source-map entries (file, line, digest).
- **Consumers:** ListingFieldLayout optional columns; Peek basis.
- **Unblocks:** L10, L11; the source-map part of Z09.
- **Today:** nothing documented. **New.**

### R03 · `program.instruction-info` · proposed · read
- **In:** `build`; one address, or a selection (for masks).
- **Out:** language id, instruction prototype, operand objects with kinds,
  inputs and outputs (registers, memory), raw bytes; per operand the value and
  mask bits for the three mask presets (operands, scalars, addresses).
- **Consumers:** Peek (instruction card), SearchWorkbench pattern builder.
- **Unblocks:** L27, Q03, Q04 (with R10).
- **Today:** nothing documented. **New.**

### R04 · `program.decode-preview` · proposed · read
- **In:** `build`; address; optional processor-mode variant; `max_units`.
- **Out:** instructions decoded at the address with the build's language, where
  decoding stopped and why. Every row is evidence `hypothesis`, basis "decoded at
  ‹addr› with ‹build›'s language · not committed".
- **Consumers:** Peek (speculative disassembly), PatchEditor Disassemble
  preview.
- **Unblocks:** L28; the preview half of E01.
- **Today:** only the unrestricted script `disassemble`, which commits (guide
  inventory:99). **New**, and non-committing by contract.

### R05 · `program.assemble-preview` · proposed · read
- **In:** `build`; address; one or more assembly lines; `wildcards` (bool).
- **Out:** per line, candidate encodings (bytes, length) and the code units a
  write would overwrite or leave as leftover bytes; with `wildcards`, a value and
  mask pattern per line for search.
- **Consumers:** PatchEditor Assemble mode, SearchWorkbench wildcard line.
- **Unblocks:** X01, N12 (assemble part), Q11.
- **Today:** none (guide inventory:101). **New.**

### R06 · `program.overview-map` · proposed · read
- **In:** `build`; view (whole image or a ProgramTreeView restriction); lanes
  (`address_type`, `byte_entropy`); entropy chunk size (256, 512, 1024).
- **Out:** address-range runs with code-unit type (function, external reference,
  instruction outside a function, defined data, undefined, uninitialized); entropy
  per chunk (a measured value). Range labels such as "compressed" are evidence
  `hypothesis` with basis "entropy range heuristic".
- **Consumers:** OverviewBar.
- **Unblocks:** L17, L18.
- **Today:** memory blocks only (`get-memory-blocks`, TOOLS_LIST:944). **New.**

### R07 · `program.block-graph` · proposed · read
- **In:** `build`; function or bounded program scope; block model (basic,
  isolated entry, multiple entry, partitioned, overlapped); graph kind (blocks,
  block flow, code flow, calls, data references); optional path query (from, to);
  node limit.
- **Out:** vertices (blocks with ranges), typed edges, the path set for a path
  query, `truncated` in words.
- **Consumers:** GraphPane (Blocks, program scope, block-model selector, path
  highlight, grouping), Listing select-by-flow, ProgramTreeView "Organize by
  subroutine" (block model list).
- **Unblocks:** G01, G02, G08, P10, L22.
- **Today:** calls only (`get-call-graph`, TOOLS_LIST:660); data references via
  `get-references` (G09). **New:** blocks, models, flows, paths.

### R08 · `program.pcode-graph` · proposed · read
- **In:** `build`; function; `kind` (data flow or control flow).
- **Out:** p-code ops and varnodes as a bounded graph with typed edges.
- **Consumers:** GraphPane data-flow mode.
- **Unblocks:** D07.
- **Today:** `analyze-data-flow` traces (TOOLS_LIST:215), no graph. **New.**

### R09 · `program.evaluate-address` · proposed · read
- **In:** `build` or `builds`; an expression (numbers, symbols, arithmetic,
  logic and bit operators) or `file_offset`.
- **Out:** the address, the parse, and value forms (hex, decimal, signed,
  char); an ambiguous symbol lists every candidate and picks none; a file offset
  maps per build or reads "outside every block".
- **Consumers:** NavigationBar (`=` and `file:` prefixes), Peek scalar
  conversions, ListingFieldLayout file-offset column.
- **Unblocks:** N02, I04, the file-offset part of L10.
- **Today:** name lookup through `search-everything` and `manage-symbols`
  (N01). **New.**

### R10 · `program.search-memory` · proposed · read
- **In:** `builds` (`"all"` allowed), scope (whole, selection on one build,
  view); a pattern as format plus input (hex, binary, string, regex, decimal,
  float, double) or value-and-mask bytes; endianness, alignment, sizes,
  encoding, case, code-type filters; direction and start for incremental; limit;
  `recheck` with a prior hit set (changed, not changed, increased, decreased;
  other builds only through R25 anchors); `encoded_strings` with charset and
  allowed scripts.
- **Out:** hits per build, never joined across builds: address, matched bytes,
  code unit, function; the per-build converted pattern actually searched;
  `truncated` per build; skipped builds with the reason (not loaded, pattern not
  convertible). Encoded-string validity is a score from the build's own bytes,
  evidence `hypothesis` with basis ("charset guess"), never a defined string.
- **Per build:** each build searched with its own endianness and pointer size.
- **Flags:** `long_running=true` for all-builds scans (still read-only,
  `identity_scope=none`).
- **Consumers:** SearchWorkbench (memory and instruction modes), ResultsTable,
  OverviewBar hits lane, Listing marker margin.
- **Unblocks:** Q01, Q03, Q04, Q11 (with R05), the encoded-strings part of Q06.
- **Today:** text searches only (`search-code` :1558, `search-everything`
  :1622). **New.**

### R11 · `program.scan-address-values` · proposed · read
- **In:** `builds`; `kind` (`direct_references` to target addresses, or
  `address_tables` with minimum length, alignment, skip).
- **Out:** direct references (from, preview, to) or candidate tables (location,
  length, entries). For all builds, each build is scanned for its own
  counterpart address from R25 and the identity edge; unresolved builds are
  skipped with the reason. An address value is never carried across builds.
- **Flags:** `long_running=true` for all-builds scans.
- **Consumers:** SearchWorkbench, ResultsTable (Direct references, Address
  tables).
- **Unblocks:** Q07, Q08, E11 (with W15).
- **Today:** none. **New.**

### R12 · `program.list-program-objects` · proposed · read
- **In:** `build` or `builds`; `kind`; filters; page.
- **Out, by kind:**
  - `defined_data`: location, data type, value, label, size (A02);
  - `relocations`: address, type, values, original bytes, symbol (P05);
  - `equates`: name, value, reference count, enum-backed, display (P06);
  - `program_trees`: trees, folders, fragments with ranges, sizes, code-unit
    counts and every parent (P01, P02);
  - `register_values`: register tree from the build's language with widths and
    context values, explicit ranges with source, language defaults (P07; the
    entry values of L06);
  - `property_maps`: property name and value at addresses, including stored
    listing colors (P12, L20).
- **Consumers:** ResultsTable, ProgramTreeView, RegisterValuesEditor, Listing
  function header, Peek (Properties), ObjectDiff (relocation-aware equality).
- **Unblocks:** A02 (type filter), P01, P02, P05, P06, P07, P12, L06, L20.
- **Today:** `list_data_items(offset, limit)` (TOOLS_LIST:942) enumerates data
  items without a documented type filter. **New:** every other kind.

### R13 · `program.change-history` · proposed · read
- **In:** `build`; kinds (`comment`, `label`); address or entity; time range.
- **Out:** events: kind, address, before, after, source (user, analysis,
  imported, default), who (you, agent, external as recorded), job or inline
  edit, time. Edits before recording began read "not recorded before ‹time›".
- **Consumers:** EntityTimeline (Comments and Labels filters), NameProvenance.
- **Unblocks:** A07, S10.
- **Today:** none. **New.**

### R14 · `program.validate` · proposed · read
- **In:** `build`; the validation checks to run (read-only).
- **Out:** findings as predicates with address, check id and evidence.
- **Consumers:** ProblemsList.
- **Unblocks:** P11 (the design is still missing).
- **Today:** none. **New.**

### R15 · `corpus.range-diff` · proposed · read
- **In:** a build pair (`cmp`); address ranges on the first build;
  categories (bytes, code units, references, comments, symbols, functions,
  bookmarks, properties, context).
- **Out:** the stored diff receipt from J05: difference ranges per category,
  each mapped to the other build through R25 anchor pairs with the anchor named;
  ranges without an anchor read "no anchor"; the variance fields where J12 has
  classified the range.
- **Consumers:** SplitCompare (range diff mode, difference-detail Peek),
  OverviewBar divergence lane, ImageDeltaMap.
- **Unblocks:** X02, X04.
- **Today:** entity-level comparison only (`match-function`, TOOLS_LIST:1362);
  `corpus.diff-builds` is future (outputs inventory:78). **New.**

### R16 · `program.checksums` · proposed · read
- **In:** `build` or `builds`; range; algorithms (checksum-8/16/32, Adler-32,
  CRC-16, CRC-32, MD5, SHA family); on every build, the anchor-mapped range from
  R25.
- **Out:** algorithm, value, range, build, anchor used; "no anchor on ‹build›".
  Differing values are divergence evidence with variance class `unknown` unless
  a record states one.
- **Consumers:** HexStrip and Peek (Checksums).
- **Unblocks:** I03.
- **Today:** none. **New.**

### R17 · `program.program-options` · proposed · read
- **In:** `build` or `builds`; `sections` (`analysis`, `decompiler`,
  `spec_extensions`).
- **Out:** per build, stored analyzer enablement and options with defaults,
  whether each analyzer applies to the language, supports one-shot use, is a
  prototype; named configurations; the analysis state and receipt; the decompiler
  program options (today Prototype evaluation, from that build's compiler spec);
  prototype and call-fixup extensions per build, compared by name across builds,
  never shared. Values are read, never inferred; a value the program never stored
  reads "unknown · not stored", never the default. The decompiler analysis
  options are per-viewer request fields of the decompile read (G16), not program
  options.
- **Consumers:** AnalyzerPanel, OptionsPanel program section, ProvenanceStamp
  basis (builds compared under different options are flagged).
- **Unblocks:** Z02, Z08, D30 (program option), D31.
- **Today:** `analyze-program` takes `analyzers` (TOOLS_LIST:259) but nothing
  reads the configuration. **New.**

### R18 · `program.transactions` · proposed · read
- **In:** `build`.
- **Out:** the undo stack and redo list as the program holds them: name,
  position, time, submitter, the job or inline edit, change count, the
  propagation it belongs to; the stack limit; whether the stack was cleared and
  why; transactions since the last save and the last check-in; older
  transactions from the event store marked not undoable.
- **Consumers:** EditHistory, ScriptConsole (committed transaction link).
- **Unblocks:** V01 (with W27), V03.
- **Today:** none. **New.**

### R19 · `program.version-history` · proposed · read
- **In:** `build` or `builds`.
- **Out:** domain file kind (versioned, private, hijacked), local and latest
  version, checkout (exclusive or not, by whom as reported, since when),
  unsaved and un-checked-in counts, version history (version, time, submitter,
  comment), the server's checkout list, and after an update or check-in the merge
  job's per-category counts and each conflict's three values.
- **Consumers:** VersionControlPanel, MemoryMapTable header, EditHistory.
- **Unblocks:** V04, V05.
- **Today:** `checkout-status` (TOOLS_LIST:440) gives checkout state. **New:**
  history, server checkout list and merge summary.

### R20 · `program.stack-frame` · proposed · read
- **In:** `build`; function.
- **Out:** frame base, frame size, local size, parameter offset and size,
  return address offset, stack variables (offset, size, type, name, comment),
  register parameters with storage, and the stack-reference count or
  `not_indexed`.
- **Consumers:** StackFrameEditor (target build), SignatureEditor (purge
  cross-check), ReferenceEditor (stack binding).
- **Unblocks:** F13, F11 (with W07), E10 (binding).
- **Today:** variable operations through `manage-function` (guide
  inventory:36) cover part. **New:** the frame fields.

### R21 · `program.spec-facts` · proposed · read
- **In:** `build`.
- **Out:** from that build's own language and compiler spec only: calling
  conventions, registers with widths and sub-registers, stack model, named call
  fixups, address spaces, ref-type list, pointer width, endianness, default
  alignment, charsets, processor-mode variants.
- **Consumers:** SignatureEditor, ReferenceEditor, RegisterValuesEditor,
  PatchEditor, TypeEditor (language facts), SearchWorkbench (conversion).
- **Unblocks:** validation in D17, F06, F09, E07, E10, P07, N12; no row alone.
- **Today:** the convention list reaches the source FunctionEditor (guide
  inventory:37). **New:** the rest, as one read.

### R22 · `program.infer-structure` · proposed · read
- **In:** `build`; function and variable (or a pointer expression).
- **Out:** an inferred component list, each row evidence `hypothesis` with basis
  (access addresses and widths on that build). Never layout proof.
- **Consumers:** TypeEditor inferred mode, DecompileView Auto Create/Fill.
- **Unblocks:** D21 (with W05).
- **Today:** none. **New.**

### R23 · `corpus.type-presence` · proposed · read
- **In:** `builds`; category or type; find-by (`name`, `size`, `enum_value`,
  `struct_size`, `struct_offset`).
- **Out:** per logical type and build: present or `absent` or `not_loaded`,
  kind, size, alignment, layout digest, source-archive association and sync state
  (in sync, changes to commit, archive newer, conflicting, archive not open, not
  associated), use count or `not_indexed`, and variance fields where a witness is
  recorded (for example a packing flag). Archives with writable state,
  architecture, unsaved changes and archive undo depth. Hits are per build,
  never merged.
- **Consumers:** TypeManager (including Compare with…, two stored types side
  by side), ResultsTable (Types), TypeEditor per-build columns and its read-only
  following form.
- **Unblocks:** T01 (per-build columns), T03 (sync state), T07, T17.
- **Today:** `manage-data-types` and `manage-structures` list one program's
  types (TOOLS_LIST:1146, :1294) with a name filter. **New:** per-build
  columns, digest, sync state, use counts, find by size, offset or enum value.

### R24 · `corpus.layout-check` · proposed · read
- **In:** a proposal (a type layout, a prototype with storage, or a frame slot
  mapping) and the recipient `builds`.
- **Out:** per recipient: size before and after, fields that move, alignment,
  pointer width, register availability, the ABI gate result, and a verdict
  (`fits`, `identical`, `differs` with why, `absent`, `not_loaded`). A
  pointer-width or language difference is a solid compile-variance witness.
- **Consumers:** TypeEditor and TypeManager (layout check per build),
  SignatureEditor (ABI gate), StackFrameEditor (slot pairing), PropagationTransfer,
  every cross-build ConfirmDialog.
- **Unblocks:** the gate of D11, D14, T05, T10, T12, D17, F07, F13 proposals;
  it is contract gap G03.
- **Today:** none. **New.**

### R25 · `corpus.anchor-pairs` · proposed · read
- **In:** a build pair, or one build and `"all"`; an entity or address range.
- **Out:** recorded anchor pairs (G10) in address order on each side, each with
  kind, evidence level and source; for a queried address, the nearest preceding
  anchor and its partner, stated as such; "no anchor" otherwise. Nothing is
  interpolated by offset or order.
- **Consumers:** SplitCompare, OverviewBar (cursor on other bars), the
  position-keeping build switch (N06), Peek (type on every build), HexStrip
  checksums on every build, ReferenceEditor and PatchEditor counterparts,
  RegisterValuesEditor comparison, ScriptConsole script state, MatchExplain.
- **Unblocks:** X02, X04 (with R15), I03 on every build, and the anchor-mapped
  parts of many rows.
- **Today:** the rule is designed (linked views:170); availability is not
  verified from docs (:177, :566). Identity tables are partial (outputs
  inventory:95). **New:** a served read.

### R26 · `corpus.compiler-annotations` · proposed · read
- **In:** `builds`; entity or address range; kinds (INL, ICF, GS, EH, SEH, DIV,
  TAIL, SW, FPO, ILT, HP, STR, LOOP, INTR, CC, and RTC, PROBE, BOOL where
  detectors exist).
- **Out:** detector records (G09) with stable ids, affected ranges, parameters,
  stage, evidence fields, per-build presence keyed by entity and kind, and
  variance fields for a presence difference; "no detector output for ‹build›"
  where J10 has not run.
- **Consumers:** CompilerLayer, TransformTimeline.
- **Unblocks:** U196; no parity row.
- **Today:** design only (linked views:426). **New.**

### R27 · `corpus.pointer-chain` · proposed · read
- **In:** entity; inspected `build`; cursor instruction and operand;
  `builds` for columns.
- **Out:** the operand decomposition (base, index, scale, displacement), the
  register-origin dataflow to a parameter, `this` or a global, then steps
  (root, offset and dereference, index and stride, field, this-adjust thunk,
  vptr slot, union). Each step has the logical field or slot and type, and per
  build the offset, stride or slot (G11) with evidence fields; variance fields
  where builds differ; the struct layout with padding per build. An unresolved
  base is `unknown` with the reason.
- **Consumers:** PointerWalk.
- **Unblocks:** U195; supports T16 on every build.
- **Today:** `analyze-data-flow` (TOOLS_LIST:215) traces one build. **New.**

### R28 · `corpus.frame-layout` · proposed · read
- **In:** entity; `builds`.
- **Out:** per build: frame base (EBP, ESP normalised to entry, x64 RSP with
  home space, unknown), prologue parse, logical slots (arg, return, saved, EH
  node, cookie, buffer, local, spill, align) with offsets and raw ESP offsets,
  register-resident locals, stack-reference live ranges, decompiler variable per
  slot; the slot mapping between builds with pairing quality (bijective,
  non-bijective, insufficient alignment); flags (/GS ordering, slot reuse, FPO)
  as variance fields.
- **Consumers:** FrameLayout, StackFrameEditor (other builds and proposals),
  MatchExplain (stack slot class).
- **Unblocks:** U198; the proposal step of F13.
- **Today:** none. **New.**

### R29 · `corpus.vtable-model` · proposed · read
- **In:** logical class; `builds`.
- **Out:** per build: RTTI parse (object locator, type descriptor, hierarchy,
  base descriptors) or its recorded absence; vftable extents; slots keyed by
  logical method with target, identity-edge word, kind (override, inherited,
  scalar or vector deleting destructor, adjustor thunk with delta); the ICF alias
  map (every entity at a folded address); variance fields for slot order and
  folding.
- **Consumers:** VTableBrowser, PointerWalk vptr step.
- **Unblocks:** U198.
- **Today:** candidate vtable analysis (`analyze-vtables`, TOOLS_LIST:284;
  guide inventory:40). **New:** RTTI, logical slots, alias map.

### R30 · `corpus.match-explanation` · proposed · read
- **In:** target (entity at build, range) and candidate (revision and recipe),
  or a comparison receipt id.
- **Out:** from J13's stored classifier record: diff rows with class (register
  allocation only, scheduling, stack slot order, relocation only, constant,
  branch structure, inlining, toolchain or flags, source), evidence per row,
  stable register pairs, class counts, the separate Local match, Linked match and
  Whole-file equality states, the effective-match state, the fuzzy percentage
  (truncated, labelled not a claim), and identity opinions each with its own
  matcher and score; receipt provenance (fresh, reused, historical).
- **Consumers:** MatchExplain, ObjectDiff.
- **Unblocks:** U197.
- **Today:** objdiff receipts are delivered (outputs inventory:84;
  `run-decomp-match` TOOLS_LIST:1402). **New:** the classifier record.

### R31 · `corpus.toolchain-facts` · proposed · read
- **In:** `builds`.
- **Out:** fact rows (G12) per build: machine type and pointer width (a
  witness, which also makes x86-only facts such as /Oy "not applicable" on x64);
  Rich header entries (product id, build number, count, LTCG kinds) as witness
  with address; linker version; debug
  directory CodeView; PDB records when matched by GUID and age (compiler and
  linker command lines, source checksums); detector aggregates with sample size,
  detector id and example addresses (frame shape, ILT runs, hotpatch, folding,
  pooling, cookie and EH idioms, CRT matches) as hypotheses; the registry's
  pinned rebuild toolchain with hashes and whether it matches the evidence.
- **Consumers:** ToolchainEvidence, ArtifactCard (provider line),
  SignatureEditor and TypeManager (variance witnesses), VariantRelation.
- **Unblocks:** U193.
- **Today:** research only (MSVC research:1392-1498); STRATEGY requires
  toolchain records (STRATEGY:136); the calibration record is future (outputs
  inventory:101). **New.**

### R32 · `corpus.variant-relation` · proposed · read
- **In:** a pair (`cmp`) or all pairs; optional class filter.
- **Out:** per pair: toolchain, flag and link differences (from R31) with
  evidence; whether source, toolchain and flag identity are recorded for each
  build; counts per variance class with their level; per entity (drill-down) the
  class, evidence, basis, addresses on both builds and each tool's opinion. Pairs
  never compared read `unknown` and count nothing.
- **Consumers:** VariantRelation, OverviewBar divergence lane, MemoryMapTable
  Class column, TypeManager, SignatureEditor and StackFrameEditor variance cells.
- **Unblocks:** U194.
- **Today:** none served. **New.**

### R33 · `corpus.outputs-inventory` · proposed · read
- **In:** project; filters (status, build, group, tier, has file, observed).
- **Out:** the served inventory (G14): artifact id, group, purpose, format,
  producing verb and node, claim tier and "is not" sentence, scope; per artifact
  and build the status (delivered, partial, stale, future, never run, no report,
  reference) from stored receipts, receipt id, job, basis digest and age; stored
  file path, size and hash; bundle members; coverage measures kept separate;
  the 8080 observation record.
- **Consumers:** OutputsCatalog, ArtifactCard, ExportDialog (existing artifact
  with the same basis).
- **Unblocks:** U192; reuse in D03, V06.
- **Today:** the inventory is a research document (outputs inventory:72-140).
  **New:** a served form.

### R34 · `workbench.list-scripts` · proposed · read
- **In:** project.
- **Out:** scripts (file, category, description, author, declared menu path and
  key binding, directory, bundle, compile status with the first error line);
  bundles with kind and state.
- **Consumers:** ScriptConsole.
- **Unblocks:** C01 (list), C04 (read-only list).
- **Today:** `execute-script` has no documented parameters (TOOLS_LIST:1459).
  **New.**

## Writes

Every write uses the write defaults above unless stated: one build,
`identity_scope=program`, job and transaction receipts with a post-write re-read,
idempotency key, `conflictId` for modification conflicts, one writer, no
analysis and no propagation.

### W01 · `program.commit-decompiler-variables` · proposed · write
- **In:** `build`; function; `mode` (`params_return` or `local_names`).
- **Out:** the committed prototype or variable annotations; callers on the same
  build marked "predates job".
- **Confirm:** ConfirmDialog for `params_return` (a callee-signature change).
- **Propagation:** the prototype may be offered through J14 behind R24's ABI
  gate.
- **Consumers:** DecompileView Edit group.
- **Unblocks:** D15, D16.
- **Today:** none. **New `manage-function` modes.**

### W02 · `program.set-callsite-override` · proposed · write
- **In:** `build`; call instruction address; `mode` (`set`, `edit`,
  `remove`); override prototype.
- **Propagation:** never; counterpart call sites only by their own call.
- **Consumers:** SignatureEditor call-site mode.
- **Unblocks:** D18. **Today:** none. **New.**

### W03 · `program.split-variable` · proposed · write
- **In:** `build`; function; high variable and use location.
- **Consumers:** DecompileView Edit group. **Unblocks:** D19. **New.**

### W04 · `program.set-pointer-typedef` · proposed · write
- **In:** `build`; pointer typedef or variable; offset (shifted pointer),
  address space, image-base relative, component path (force field).
- **Confirm:** ConfirmDialog (layout-gated). **Propagation:** J14 only when R24
  finds equal pointer width.
- **Consumers:** TypeEditor typedef and pointer mode, DecompileView.
- **Unblocks:** D20, T12. **New.**

### W05 · `program.apply-inferred-structure` · proposed · write
- **In:** `build`; target (variable or type); the R22 proposal with the rows the
  operator named or retyped.
- **Out:** the created or filled structure; unnamed inferred rows stay
  hypotheses and are not applied.
- **Confirm:** ConfirmDialog. **Consumers:** TypeEditor inferred mode.
- **Unblocks:** D21. **Today:** `manage-structures` create (TOOLS_LIST:1294).
  **New:** usage-derived application.

### W06 · `program.manage-equates` · proposed · write
- **In:** `build`; operand (address, operand index) or equate name; `mode`
  (`convert_display` with format, `set`, `rename`, `remove`, `apply_enum`).
- **Propagation:** names offered through J14 only at anchor-aligned operands
  (R25).
- **Consumers:** DecompileView and Listing link menu, ResultsTable (Equates).
- **Unblocks:** D24, P06. **New.**

### W07 · `program.edit-stack-frame` · proposed · write
- **In:** `build`; function; frame fields (local size, parameter offset and
  size) and stack-variable operations (create, delete, clear, retype, array,
  rename, comment).
- **Confirm:** in place for one rename or comment; ConfirmDialog otherwise.
  Validation (overlaps, arrays over slots, alignment) refuses before posting.
- **Propagation:** names and types of paired slots only, through J14 with R28's
  bijective mapping; offsets and sizes never.
- **Consumers:** StackFrameEditor.
- **Unblocks:** F13, F11 (delete variable).
- **Today:** `manage-function` variable operations cover rename and retype
  (guide inventory:36). **New:** frame fields and delete.

### W08 · `program.set-purge-and-stack-depth` · proposed · write
- **In:** `build`; function purge (bytes or remove); or an instruction address
  and stack-depth change (set or remove).
- **Consumers:** SignatureEditor (purge); the stack-depth part has no design yet.
- **Unblocks:** F10. **New.**

### W09 · `program.disassemble` · proposed · write
- **In:** `build`; address or range; variant (follow flow, restricted, static,
  processor mode).
- **Confirm:** ActionStrip Run at one address; ConfirmDialog over a selection.
- **Flags:** NA holds: no follow-on analysis.
- **Consumers:** PatchEditor Disassemble, Peek "Disassemble (catalog)",
  ResultsTable (address table targets), RegisterValuesEditor (armed
  re-disassembly).
- **Unblocks:** E01. **Today:** script `disassemble` only (guide
  inventory:99). **New.**

### W10 · `program.set-flow-override` · proposed · write
- **In:** `build`; instruction address; `mode` (`flow` with none, branch,
  call, call-return, return; `length`; `fallthrough` with address, auto or
  clear).
- **Confirm:** ConfirmDialog for flow and length; in place for fallthrough.
- **Consumers:** ReferenceEditor. **Unblocks:** E02, E03. **New.**

### W11 · `program.clear-code-units` · proposed · write
- **In:** `build`; range; `mode` (`code_bytes`, `with_options` and the option
  set, `flow_and_repair`).
- **Out:** what was removed per option; bytes are kept.
- **Confirm:** ConfirmDialog (destructive). **Consumers:** PatchEditor Clear.
- **Unblocks:** E04. **Today:** script `clearListing` only. **New.**

### W12 · `program.set-data-settings` · proposed · write
- **In:** `build`; one or more data addresses; format, endianness, charset,
  string rendering.
- **Confirm:** in place for one data unit; ConfirmDialog for more than one row.
- **Consumers:** PatchEditor Create data, ResultsTable (defined strings
  Settings…). **Unblocks:** E05 (settings), A01 (string settings).
- **Today:** `apply-data-type` applies the type (TOOLS_LIST:325). **New:**
  settings.

### W13 · `program.edit-references` · proposed · write
- **In:** `build`; source code unit and operand; `mode` (`add`, `edit`,
  `delete`, `set_primary`, `create_default`, `delete_all`,
  `from_selection`, `offset_table` with base, entry size, count, signed);
  reference kind (memory, external, stack, register), destination, ref-type.
- **Confirm:** in place for one reference; ConfirmDialog for batches,
  delete-all and any deletion from XrefPanel or ResultsTable.
- **Propagation:** only when source and destination are both anchor-mapped
  (R25), through J14.
- **Consumers:** ReferenceEditor, XrefPanel (Delete reference), ResultsTable
  (symbols' references, direct references).
- **Unblocks:** E07, E08, E09, E10, L30, S07.
- **Today:** `get-references` is read-only (TOOLS_LIST:844). **New.**

### W14 · `program.make-string` · proposed · write
- **In:** `build`; address; string type or char array; offset; auto label.
- **Consumers:** SearchWorkbench and ResultsTable (Found strings).
- **Unblocks:** Q06. **Today:** a string-specific byte write exists in source
  per the guide inventory (:99). **New:** as a catalog verb.

### W15 · `program.make-address-table` · proposed · write
- **In:** `build`; table location and length; offset; auto label;
  `disassemble_targets` (arms W09, never runs it inside this call).
- **Consumers:** ResultsTable (Address tables). **Unblocks:** E11. **New.**

### W16 · `program.replace-names` · proposed · write
- **In:** `build`; the preview set from a search (element kinds, find, replace,
  regex with groups); the frozen list of targets.
- **Confirm:** ConfirmDialog with the count; a multi-build replace is one call
  per build inside a cross-build ConfirmDialog, each with its own outcome.
- **Consumers:** SearchWorkbench Replace mode. **Unblocks:** Q10.
- **Today:** search through `search-everything`. **New:** the batch.

### W17 · `program.manage-type-archives` · proposed · write
- **In:** target (`build` program types or one archive); `mode` (`open`,
  `create`, `open_for_editing`, `close_for_editing`, `close`, `save`,
  `save_as`, `set_architecture`, `clear_architecture`, `archive_undo`,
  `archive_redo`, `delete`, `remove_invalid`, `category_create`, `category_rename`,
  `category_delete`, `category_move`, `category_copy`, `sync_update`,
  `sync_commit`, `sync_revert`, `sync_disassociate`).
- **Flags:** `identity_scope=archive` for archive modes, `program` for
  program types; `mutating=true`.
- **Per build:** "all builds" is never a target; a shared archive reaches each
  build through a per-build `sync_update`, each layout-gated by R24.
- **Consumers:** TypeManager. **Unblocks:** T02, T03, T04. **New.**

### W18 · `program.edit-types` · proposed · write
- **In:** target; type; `mode` (`rename`, `move`, `copy`, `delete`,
  `replace`, `merge` with conflict mode, `create_function_definition` from a
  function, `labels_from_enum`).
- **Confirm:** ConfirmDialog with use counts per build for replace, merge, move
  and delete; conflict mode is an explicit field, never sticky.
- **Consumers:** TypeManager, TypeEditor. **Unblocks:** T05, T06, T09, T13.
- **Today:** composite create and edit through `manage-structures` and
  `manage-data-types` (T10, T11 are backed). **New:** these modes.

### W19 · `program.apply-function-types` · proposed · write
- **In:** `build` (apply) or archive (capture); `mode` (`apply`, `capture`);
  source archives; options.
- **Confirm:** ConfirmDialog (batch). **Consumers:** TypeManager.
- **Unblocks:** T08. **Today:** the API command is documented
  ([PyGhidra reference](../PyGhidra_API_Reference.md):1099). **New:** the verb.

### W20 · `program.edit-namespaces` · proposed · write
- **In:** `build`; `mode` (`create_namespace`, `create_class`,
  `convert_to_class`, `move` with destination, `delete` symbols,
  `pin_symbol` for keep-at-address on rebase, `set_external_entry`).
- **Confirm:** in place for one create or convert; ConfirmDialog for move,
  delete and batches, naming reference counts.
- **Propagation:** namespace paths per field through J14 on accepted edges,
  with a collision check per recipient.
- **Consumers:** SymbolTree, ResultsTable (Symbols).
- **Unblocks:** S02, S06, S11. **Today:** rename and labels through
  `manage-symbols` and `create-label` (TOOLS_LIST:1334, :455). **New.**

### W21 · `program.edit-external-locations` · proposed · write
- **In:** `build`; `mode` (`create_library`, `set_external_program`,
  `clear_external_program`, `move_library` (search order), `create_location`,
  `edit_location`, `restore_original_label`, `create_external_function`).
- **Propagation:** never (program-local).
- **Consumers:** SymbolTree Imports. **Unblocks:** S03. **New.**

### W22 · `program.edit-memory-map` · proposed · write
- **In:** `build`; `mode` (`set_fields` for name, R/W/X, volatile,
  artificial, comment on one block; `add`, `move`, `split`, `expand`, `merge`,
  `delete`, `initialize` with fill, `set_uninitialized`,
  `rename_overlay`; `set_image_base`).
- **Out:** for `set_image_base`, the anchors and pinned locators whose absolute
  addresses changed.
- **Confirm:** in place for `set_fields`; ConfirmDialog otherwise.
- **Propagation:** never. **Consumers:** MemoryMapTable. **Unblocks:** P04.
  **New.**

### W23 · `program.set-register-values` · proposed · write
- **In:** `build`; register; `mode` (`set` over a range, `edit`, `delete`,
  `clear_in_selection`); value validated against the register width and defined
  context values.
- **Confirm:** ConfirmDialog. **Flags:** NA: existing instructions are not
  re-disassembled; W09 is armed separately.
- **Propagation:** never. **Consumers:** RegisterValuesEditor.
- **Unblocks:** P07. **New.**

### W24 · `program.edit-program-tree` · proposed · write
- **In:** `build`; tree; `mode` (`create_tree`, `rename_tree`,
  `delete_tree` (never the last tree), `create_folder`, `create_fragment`,
  `rename`, `delete` (empty or shared only), `move`, `copy` (adds a parent, so
  the node becomes shared), `reorder`, `merge_with_parent`, `sort`,
  `move_code_units`).
- **Propagation:** never. **Consumers:** ProgramTreeView.
- **Unblocks:** P01. **New.** (Organizations are J03.)

### W25 · `program.edit-bookmarks` · proposed · write
- **In:** `build`; bookmark (address, type, category); `mode` (`edit`,
  `remove`, `remove_all` with category or type).
- **Confirm:** one bookmark posts on Run; bulk remove through ConfirmDialog.
- **Propagation:** only through `migrate-metadata` `propagateBookmarks`
  (TOOLS_LIST:1448) or J14.
- **Consumers:** MarksList. **Unblocks:** A05 (already backed by the tool).
- **Today:** `manage-bookmarks` accepts these fields (TOOLS_LIST:1088). **New:**
  only the catalog advertisement with admission flags.

### W26 · `program.patch-bytes` · proposed · write
- **In:** `build` (required; no default); address or range; `mode`
  (`instruction` with the R05 encoding chosen, `data` with a typed value,
  `bytes`); the preview's original, current and after bytes as the expected
  basis.
- **Out:** the post-write read and "read back equals" or "differs" with the byte.
- **Confirm:** ConfirmDialog for every byte write. **Conflicts:** a changed
  current byte refuses the write; nothing overwrites an unseen change.
- **Propagation:** never; patched bytes are not recovery evidence.
- **Consumers:** PatchEditor (Assemble, Patch data, Bytes), HexStrip.
- **Unblocks:** N12, X01. **Today:** script `setBytes` only (guide
  inventory:99, :105). **New.**

### W27 · `program.undo-transactions` · proposed · write
- **In:** `build`; `mode` (`undo`, `redo`, `undo_to` a position).
- **Out:** transactions reverted; receipts made stale on that build only.
- **Confirm:** in place for one top undo of a single-target edit; ConfirmDialog
  for batches and "undo to here".
- **Per build:** never undoes on another build; a propagated edit is undone per
  recipient in that recipient's own history. Jobs' logs, receipts and files are
  not undone.
- **Consumers:** EditHistory, SymbolTree and TypeManager status lines.
- **Unblocks:** V01. **New.**

### W28 · `program.set-analysis-options` · proposed · write
- **In:** `build`; analyzer enablement and options (the draft); optional
  configuration name to save or delete.
- **Confirm:** ConfirmDialog; applying one build's options to others is one
  call per recipient, with non-applicable analyzers skipped by name.
- **Flags:** NA: setting options starts no analysis.
- **Consumers:** AnalyzerPanel. **Unblocks:** Z02, Z08. **New.**

### W29 · `program.set-decompiler-options` · proposed · write
- **In:** `build`; the decompiler program options (today Prototype
  evaluation, one of that build's own conventions).
- **Confirm:** ConfirmDialog (changes every later decompile of that build);
  no re-decompile follows.
- **Consumers:** OptionsPanel program section. **Unblocks:** D30. **New.**

### W30 · `program.manage-spec-extensions` · proposed · write
- **In:** `build`; `mode` (`import`, `remove`); prototype or call-fixup
  extension; the compiler spec it must match.
- **Confirm:** ConfirmDialog; builds with another language or spec are
  excluded by name.
- **Consumers:** OptionsPanel. **Unblocks:** D31. **New.**

### W31 · `corpus.record-identity-decision` · proposed · write
- **In:** two entities on two builds; `decision` (`accept`, `reject`,
  `manual_match`); the evidence the reviewer cites.
- **Flags:** `identity_scope=database`.
- **Out:** the identity edge with its evidence and author; descendants whose
  support changes are listed for re-evaluation (STRATEGY:197).
- **Consumers:** ReviewDetail, MatchReview. **Unblocks:** X07.
- **Today:** matching creates edges (`corpus.match-pair`, consolidated
  plan:87). **New:** an operator decision verb.

### W32 · `program.save` · proposed · write
- **In:** `build`; `mode` (`save`, `save_as` with a new project path).
- **Out:** saved transaction count; the undo stack is kept.
- **Consumers:** EditHistory summary, VersionControlPanel. **Unblocks:** V03.
  **New.**

### W33 · `program.version-control` · proposed · write
- **In:** `build`; `mode` (`add`, `undo_checkout` with keep-copy,
  `undo_hijack`, `delete_version`, `resolve_merge_conflict` with the chosen
  value and optional "use for all in this category").
- **Flags:** `identity_scope=project` for server verbs.
- **Confirm:** ConfirmDialog for undo checkout, delete version and
  use-for-all; one conflict choice in place.
- **Consumers:** VersionControlPanel, MergeReview. **Unblocks:** V04, V05.
- **Today:** check-out, check-in and status tools (TOOLS_LIST:424, :394,
  :440). **New:** these modes. (Update with merge is J15.)

### W34 · `workbench.manage-scripts` · proposed · write
- **In:** `mode` (`create`, `rename`, `delete`, `edit`, `bundle_enable`,
  `bundle_disable`, `bundle_clean`, `bundle_refresh`); script or bundle.
- **Flags:** `identity_scope=project` (script files; bundles affect runs on
  every build).
- **Confirm:** ConfirmDialog for delete and bundle changes.
- **Consumers:** ScriptConsole (advanced). **Unblocks:** C01, C04. **New;**
  lowest priority.

## Jobs

Jobs use the job defaults: `long_running=true`, a content-addressed receipt with
basis and inputs, and reuse first.

### J01 · `program.debug-decompile` · proposed · job
- **In:** `build`; function. **Flags:** `mutating=false`,
  `identity_scope=output-tree`.
- **Out:** the debug-decompile capture as an artifact with its basis
  (OutputsCatalog). **Consumers:** DecompileView (not yet designed).
- **Unblocks:** D06. **New.**

### J02 · `program.run-one-shot-analyzer` · proposed · job
- **In:** `build`; analyzer; the frozen address set.
- **Flags:** `mutating=true`, `identity_scope=program`.
- **Out:** analysis receipt; changes may fall outside the selection and are
  reported as such. **Consumers:** AnalyzerPanel.
- **Unblocks:** Z04, Z08. **Today:** `analyze-program` with `analyzers`
  (TOOLS_LIST:259) has no address set. **New:** the bounded form.

### J03 · `program.organize-program-tree` · proposed · job
- **In:** `build`; tree; `organization` (subroutine with block model,
  dominance, complexity depth).
- **Flags:** `mutating=true`, `identity_scope=program`. Cancelling keeps the
  folders already created and says so.
- **Consumers:** ProgramTreeView. **Unblocks:** P02. **New.**

### J04 · `program.import-debug-info` · proposed · job
- **In:** `build`; source (`pdb` with symbol-server settings and parser
  options, `dwarf` external file, `sarif`); what to apply.
- **Flags:** `mutating=true`, `identity_scope=program`.
- **Out:** applied names, types and source map entries with the debug-info
  tier (NameProvenance); conflicts with stronger names are reported, never
  overwritten (STRATEGY name precedence).
- **Consumers:** ImportAdmission, ContextPlacement, NameProvenance,
  ListingFieldLayout source map. **Unblocks:** Z07, Z09.
- **Today:** `export` writes SARIF (TOOLS_LIST:560); no import path is
  documented. **New.**

### J05 · `corpus.compute-range-diff` · proposed · job
- **In:** a build pair; ranges; categories.
- **Flags:** `mutating=false`, `identity_scope=evidence-store`.
- **Out:** the stored diff receipt that R15 reads, aligned by R25 anchors only.
- **Unblocks:** X02, X04. **Today:** `corpus.diff-builds` is future (outputs
  inventory:78). **New;** could be that verb's program-range mode.

### J06 · `program.export` · proposed · job (extends `export`)
- **In:** `build`; what (function, selection, whole program, graph with its
  basis, type archive); format and options from the catalog.
- **Flags:** `mutating=false`, `identity_scope=output-tree`; one job per
  build, never one merged file.
- **Out:** artifacts with basis (program version, format, options, decompiler
  options) listed by R33; an existing artifact with the same basis is reused.
- **Consumers:** ExportDialog, GraphPane, TypeManager.
- **Unblocks:** G10, V06 (GDT, hex records, original file, raw bytes), T09
  (type export), V10 (one build's GZF).
- **Today:** `export` with `gzf`, `c`, `cpp`, `cxx`, `sarif`, `xml`, `html`,
  `ascii` (TOOLS_LIST:551-560; outputs inventory:121), including
  `createHeader`, `includeTypes`, `includeGlobals` (ExportDialog's Emit
  referenced globals) and `tags` (TOOLS_LIST:562-570). **New:** the extra
  formats (GDT, hex records, raw bytes, and original file, which may carry
  W26 byte patches and then says "patched bytes are not recovery evidence"),
  graph export, and catalog advertisement.

### J07 · `corpus.archive-project` · proposed · job
- **In:** project; `mode` (`archive`, `restore` into a new project).
- **Flags:** `mutating=false` for archive (`identity_scope=output-tree`);
  `mutating=true`, `identity_scope=project` for restore.
- **Unblocks:** V10. **New.**

### J08 · `program.translate-strings` · proposed · job
- **In:** `build`; strings; translation service and settings.
- **Flags:** `mutating=true`, `identity_scope=program`. An external service is
  a network dependency and needs explicit approval before use.
- **Round 3:** needs a service list from the catalog (Manual always offered),
  per-service settings (URL, credential never echoed, source/target language,
  batch size, timeouts) and an explicit network approval per send. Output is a
  per-build translation record (a hypothesis naming its service) that never
  replaces bytes and goes stale when bytes or charset change.
- **Consumers:** ResultsTable (Translate…). **Unblocks:** A03. **New;** low
  priority.

### J09 · `corpus.manage-fiddb` · proposed · job
- **In:** `mode` (`attach`, `detach`, `create`, `populate` from builds,
  `activate` to choose the active databases); database.
- **Flags:** `identity_scope=database` for the FidDb; `mutating=true`.
- **Out:** FID names are analysis-tier candidates only (NP).
- **Unblocks:** I01. **New;** low priority.

### J10 · `corpus.detect-transformations` · proposed · job
- **In:** `builds`; detector set (the CompilerLayer kinds, frame and EH/GS
  slots, RTTI and vftables, ICF alias map); scope (whole build or entities).
- **Flags:** `mutating=false` for programs, `identity_scope=evidence-store`.
- **Out:** detector records (G09) with stable ids, detector version, evidence
  and basis, feeding R26, R28, R29 and R31's aggregates.
- **Determinism:** the same basis and detector version yield byte-identical
  records in a total order.
- **Unblocks:** U195–U198 data; no parity row. **New.**

### J11 · `corpus.extract-toolchain-facts` · proposed · job
- **In:** `builds`.
- **Flags:** `mutating=false` for programs, `identity_scope=evidence-store`.
- **Out:** toolchain fact records (G12): Rich header, linker, CodeView, PDB
  command lines and checksums, imports, as witnesses or records with addresses.
- **Unblocks:** U193 (R31). STRATEGY stage 2 (calibration) uses them.
  **New.**

### J12 · `corpus.classify-variance` · proposed · job
- **In:** a build pair or all pairs; entity set.
- **Flags:** `identity_scope=evidence-store`.
- **Out:** per entity and pair: variance class with evidence level and basis
  (G06). A class is solid only when source, toolchain and flag identity are
  recorded for both builds; otherwise a hypothesis with basis. Bodies not
  compared are `unknown`.
- **Consumers:** R32, R15, R26, MemoryMapTable, OverviewBar.
- **Unblocks:** U194. **New.**

### J13 · `corpus.explain-match` · proposed · job
- **In:** a stored comparison receipt (target, candidate, recipe).
- **Flags:** `identity_scope=evidence-store`; it compiles and compares nothing.
- **Out:** the classifier record R30 reads.
- **Unblocks:** U197. **Today:** objdiff receipts exist (outputs
  inventory:84). **New.**

### J14 · `corpus.propose-field-propagation` · proposed · job
- **In:** donor (entity, build, transaction or job); one field (name, type,
  comment, prototype, storage, namespace, tag, bookmark, frame slot name or
  type, equate); recipient builds.
- **Flags:** `mutating=true`; `identity_scope=program` per recipient, admitted
  one recipient at a time.
- **Gating:** each recipient needs an accepted identity edge; types, storage and
  frames need R24 `fits` or `identical`; addresses move only through R25.
  Blocked recipients keep their value and say why.
- **Out:** PropagationTransfer rows: donor, field, recipient, gate result,
  per-recipient job and outcome, each with its own transaction receipt.
- **Consumers:** PropagationTransfer and every "Propose to…" step.
- **Unblocks:** contract gap G02; every propose→counterparts row.
- **Today:** bulk propagation through `migrate-metadata` (TOOLS_LIST:1435)
  and `match-function` (:1362). **New:** per field, per recipient, gated, with
  receipts.

### J15 · `program.update-from-repository` · proposed · job
- **In:** `build`.
- **Flags:** `mutating=true`, `identity_scope=project` plus the build's program
  writer, held until conflicts are chosen or the update is cancelled.
- **Out:** merge per-category counts and conflicts with three values (R19).
- **Consumers:** VersionControlPanel, MergeReview. **Unblocks:** V05.
- **Today:** `sync-project` pulls project files (TOOLS_LIST:522). **New:**
  checkout update with merge.

### Round 3 additions (2026-09-29)

These entries were added when parity round 3 designed the last 26 rows. Earlier ids are unchanged.

#### Notes on existing entries
- **W08** (stack depth / purge): the stack-depth change at an instruction is now designed in Listing's Function group (Local or Global on a call; Global goes to SignatureEditor's purge).
- **W20** `set_external_entry`: needs a `remove` mode as well as `set`. Removing an importer-recorded entry point uses ConfirmDialog (SymbolTree).
- **W26** (bytes): Listing Paste is a consumer; bytes paste only over undefined bytes, confirm every write, and read back.
- **W31** `manual_match`: needs `producing_channel=manual` and a required `reason`; the result is always a candidate edge, never auto-accepted (ReviewDetail).
- **J01** `program.debug-decompile`: consumer is DecompileView ("Capture decompiler debug XML…"); output is an artifact (OutputsCatalog, ArtifactCard), reuse-first by basis.

#### W35 · `program.set-colors` · proposed · write
- **In:** `build`; address set; `mode` (`set`, `clear`, `clear_all`); colour value for `set`.
- **Flags:** `mutating=true`, `identity_scope=program`. `clear_all` uses ConfirmDialog.
- **Rules:** program-local; never proposed to counterparts; R12 reads the stored colours.
- **Consumers:** Listing (program colours). **Unblocks:** L20. **New.**

#### R35 · `program.read-validation` · proposed · read
- **In:** `build`; validator ids (optional).
- **Out:** per-validator result word (no findings, warnings, errors, not run, stale, not applicable) and findings with address, severity, message, and receipt basis.
- **Consumers:** ProgramValidation. **Unblocks:** P11 (with J16). **New.**

#### J16 · `program.validate` · proposed · job
- **In:** `build`; validator set.
- **Flags:** `mutating=false` for the program, `long_running=true`, `identity_scope=evidence-store`. Offered only for a build with an analysis receipt; confirmed in a dialog.
- **Out:** validation receipt; findings are advisory, never unmet predicates.
- **Consumers:** ProgramValidation. **Unblocks:** P11. **New.**

#### J17 · `program.set-language` · proposed · job
- **In:** `build`; target language id and compiler spec (from the compatible list); dry run first.
- **Flags:** `mutating=true`, `long_running=true`, `identity_scope=program`; needs the exclusive checkout and one writer. Destructive: ConfirmDialog with the dry-run consequence counts.
- **Rules:** one build only; never proposed; re-analysis is NOT run (it needs its own admission); receipts that depended on the old language go stale; no undo.
- **Consumers:** ProgramSettings. **Unblocks:** P08. **New.**

#### J18 · `program.load-debug-info` · proposed · job (refines J04)
- **In:** `build`; `source` (`pdb`, `dwarf`, `sarif`); for PDB: search locations, symbol-server list, parser options, `dry_run`.
- **Flags:** `mutating=true` unless `dry_run`, `identity_scope=program`. A remote symbol server needs explicit approval, even for a status check.
- **Rules:** a PDB whose GUID and age do not match is a hypothesis and ranks with analysis names; SARIF only when its hash matches the build; imported names and types enter at their own tier with per-field provenance and never overwrite a stronger tier (the stronger value stays; the imported one is a rejected alternative); types pass each build's layout check (R24).
- **Consumers:** DebugInfoImport. **Unblocks:** Z07. **New.**

#### R36 · `program.read-source-files` · proposed · read
- **In:** `build`.
- **Out:** the source files table and source map entries (file, line, address range) with their origin record; path transforms are per viewer and never stored in the program.
- **Consumers:** DebugInfoImport, ListingFieldLayout (source-map column). **Unblocks:** Z09. **New.**

#### W36 · `program.save` · proposed · write
- **In:** `build` or builds; `mode` (`save`, `save_as` with a new name, `save_all`).
- **Flags:** `mutating=true`, `identity_scope=program`. `save_all` uses ConfirmDialog and lists builds it leaves out (for example one owned by an external writer).
- **Rules:** saving is not checking in (W33); never switches project.
- **Consumers:** ProjectWindow. **Unblocks:** V03. **New.**

#### W37 · `corpus.manage-project` · proposed · write
- **In:** `mode` (`create`, `delete`, `open_readonly`); project.
- **Flags:** `mutating=true`, `identity_scope=project` for create and delete; `open_readonly` admits nothing.
- **Rules:** opening another project always goes through the cross-project StateNotice; delete uses ConfirmDialog.
- **Consumers:** ProjectWindow. **Unblocks:** V09. **New.**

## Contract and schema gaps

### The three contract gaps from the parity specification

- **G01 · Mode lists in the catalog.** `manage-function`, `manage-symbols`,
  `manage-comments`, `manage-bookmarks`, `manage-data-types`,
  `manage-structures` and `manage-strings` document modes only as "see MCP
  schema" (for example TOOLS_LIST:1239). The catalog must list each mode with
  its target fields, its mutating flag and its resource claim, so each Edit-group
  item is derived, not hand-listed per frontend (F22). New modes in this document
  (W01, W07, W18 …) are listed the same way.
- **G02 · Per-field propagation companion.** Every write needs a propagation
  companion that produces PropagationTransfer rows for one field and a recipient
  set, with per-recipient gates and receipts. It is J14.
- **G03 · Layout-gated check before any cross-build ConfirmDialog.** For a type,
  storage or frame proposal, each build's size, alignment, pointer width and
  register availability must be read first. It is R24.

### Shared envelopes

- **G04 · Read envelope.** `scope`; per build `state`, `basis`
  (`generation`, `digest`), `read_at`, `truncated` (with the limit); rows in a
  total order. `not_loaded`, `not_indexed` and `unsupported` are states, never
  zero rows.
- **G05 · Evidence-level fields.** On any uncertain value:
  `evidence.level` (`witness` · `record` · `hypothesis` · `unknown`),
  `evidence.basis` (required for `hypothesis`: what was checked, the sample,
  what was not checked), `evidence.source_kind` (`bytes`, `pdb`,
  `command_line`, `registry`, `detector`, `analysis`, `operator`),
  `evidence.receipt_id`, `evidence.witness_address` with its build, and
  `evidence.reused` (bool). A hypothesis never becomes a witness by repetition
  or agreement.
- **G06 · Variance-class fields.** On any cross-build difference:
  `variance.class` (`compile` · `entropy` · `source` · `unknown`, plus
  `identical`, which is not a class), `variance.level` (as G05),
  `variance.basis`, `variance.cause` (for example `/Ob`, LTCG, `/GS`, `/Oy`, EH
  model, ICF, register allocation, packing), `variance.identity_recorded`
  per build (source, toolchain, flags). `variance.level` may be solid only when
  identity is recorded for both builds.
- **G07 · Admission flags on every new action (U104).** Each entry's
  `mutating`, `long_running` and `identity_scope` are part of the catalog
  entry; admission still checks the real owner (PID, start time, command), never
  the flag alone (consolidated plan:464-467).
- **G08 · Write envelope.** Inputs: `build` (one), `expected_basis`,
  `idempotency_key`, the frozen target, and the draft. Outputs: job id, terminal
  outcome, transaction record, the post-write re-read, stale dependents ("predates
  job") and `conflictId` when the stored value changed or custom data would be
  overwritten. "No change to submit" posts nothing.

### Data each compiler-aware view needs

| View | Data it needs | Schema | Produced by | Read by |
|---|---|---|---|---|
| CompilerLayer, TransformTimeline | Detector outputs with **stable ids** (detector id, version, kind, range, parameters, stage), evidence per record, presence per build keyed by entity and kind (never address), variance class of a presence difference, the research section id | G09 | J10 | R26 |
| SplitCompare (and every anchor-mapped view) | **Anchor pairs**: build A address ↔ build B address, kind (entity entry, instruction, data, block), evidence level and source (identity edge, byte match, operator), the owning entity, and the rule for between-anchor positions (nearest preceding anchor, stated) | G10 | identity stage (existing tables, partial) | R25 |
| PointerWalk, TypeEditor, TypeManager | **Per-build field offsets** keyed by logical field identity: offset, size, type, bit position, padding, the struct size per build, stride per array, slot per vtable, each with evidence; register-origin dataflow per build | G11 | type store, J10, R22 | R27, R23, R24 |
| FrameLayout, StackFrameEditor | Prologue parse, slot kinds, normalised and raw offsets, stack-reference live ranges, EH node, cookie, buffers, FPO data, slot mapping quality | G09, G11 | J10 | R28, R20 |
| VTableBrowser | RTTI parse or recorded absence, vftable extents, slots by logical method, adjustor deltas, ICF alias map | G09 | J10 | R29 |
| ToolchainEvidence | Machine type and pointer width, **Rich header** entries (product id, build number, count, LTCG kinds, address), **linker** version, CodeView and **PDB** (GUID, age, compiler and linker command lines, source checksums), detector aggregates with sample and examples, the pinned rebuild toolchain with hashes | G12 | J11, J10 | R31 |
| VariantRelation | Per pair toolchain, flag and link differences (from G12), identity-recorded flags per build, per-entity class results with basis and each tool's opinion | G06 | J12 | R32 |
| MatchExplain | Stored relocation-aware diff rows, classifier class per row with evidence, stable register pairs, stack comparison, separate Local, Linked and Whole-file states, identity opinions per matcher | G05 | J13 over existing objdiff receipts | R30 |
| OutputsCatalog, ArtifactCard | The served inventory, per artifact × build status from receipts, file path, size and hash, bundle members, coverage measures kept separate, the 8080 observation record | G14 | receipts of every exporter | R33 |

### Further schema gaps

- **G09 · Detector record.** `record_id` (stable across reruns on the same
  basis: a hash of detector id, version, build basis, kind and range),
  `detector_id`, `detector_version`, `kind`, `build`, `range`, `entity`,
  `parameters` (inlinee, folded entities, divisor and signedness, EH state and
  object, switch cases, intrinsic, convention), `stage` (front end, optimizer,
  code generation, link), evidence (G05), `research_ref`.
- **G10 · Anchor pair record.** `pair_id`, `build_a`, `addr_a`, `build_b`,
  `addr_b`, `kind`, `entity`, evidence (G05), `source`; ordered per side so the
  nearest preceding anchor is a lookup, not an inference.
- **G11 · Per-build field offset record.** `logical_field_id`, `type`,
  `build`, `offset`, `size`, `bit_offset`, `bit_size`, `stride`, `slot`,
  evidence (G05), and the containing type's size and alignment per build.
  Field identity never comes from offset or order.
- **G12 · Toolchain fact record.** `build`, `fact` (machine and pointer width,
  Rich entry, linker, CodeView,
  PDB command line, CRT, detector aggregate, pinned toolchain), `value`,
  evidence (G05) with `witness_address` or record source, `sample` and
  `not_checked` for hypotheses, and `matches_evidence` for the pinned row.
- **G13 · Scripts as catalog entries.** Script key bindings and quick launch
  (C05) need scripts to be catalog entries with declared write scope; until then
  each run is a mutating job with "writes: unknown".
- **G14 · Served outputs inventory.** A machine-readable form of the outputs
  inventory with the status vocabulary and the 8080 observation axis kept
  separate.
- **G15 · Stage mapping for new verbs.** `catalog_verbs` maps stages 1–7 only
  (linked views:242); every action here reads "stage: unmapped" in StageChip
  until a decision is recorded.

- **G16 · Decompile request options.** The design keeps the decompiler's
  analysis options (Eliminate unreachable code, Respect read-only flags,
  Simplify predication, Alias blocking and the rest) as per-viewer request
  options that enter the decompile basis (OptionsPanel). `decompile-function`
  documents neither them nor a basis echo (TOOLS_LIST:466-493); the guide
  inventory records only `showUnreachable` in source (:34). The decompile read
  must accept each option as a request field and return the options it used,
  so views decompiled under other options can say so. Unblocks D05 and the
  per-viewer part of D30.

## Delivery order

Reads come before writes, and evidence jobs come before the program writes that
depend on their gates. The order follows STRATEGY's ladder (stage 0 open and
resume, 1 identity, 2 calibration, then parity) and U104 landing first
(portable-substrate plan:1894-1903).

1. **Contracts before code.** G04–G08 envelopes, G07 flags on every entry,
   G01 mode lists (read-only description of existing tools), G16 request
   fields. No behavior changes.
2. **Reads over stored evidence that serve stages 0–2 and gates.** R25 anchor
   pairs, R23 type presence, R24 layout check, R21 spec facts, R01 listing rows,
   R31 toolchain facts, R32 variant relation, R33 outputs inventory,
   R30 match explanation. Each answers `unknown` or "no detector output" until
   its producer exists; nothing is inferred.
3. **Remaining program reads,** ordered by parity rows unblocked: R12, R10,
   R03, R07, R02, R09, R11, R17, R20, R13, R18, R19, R06, R04, R05, R15, R16,
   R22, R08, R14, R26–R29, R34.
4. **Evidence jobs** (write the evidence store, never a program): J11, J10,
   J12, J13, J05; then J01 and J06 (artifacts only).
5. **Per-build program writes with the most recovery value,** each behind G08:
   W01, W02, W04, W05, W07, W08, W13, W10, W09, W11, W12, W06, W18, W17, W19,
   W20, W21, W14, W15, W16.
6. **Identity and propagation:** W31, then J14 (needs R24, R25 and accepted
   edges).
7. **Program-level and lifecycle writes:** W22, W23, W24, J03, W25, W27, W32,
   W33, J15, W28, W29, W30, J02, J04, W26 (patched bytes are never recovery
   evidence), J07.
8. **Advanced and optional:** W34, G13, J09, J08 (external service; needs
   explicit approval).

## Authorization

None of this is authorized to run live. Implementing or exercising any entry
follows the [AGENTS](../../AGENTS.md) process: operate only through the existing
8080 workbench and `GET /api/v1/actions`; start no alternate port; corroborate
job and process ownership (PID, start time, command, cwd, target, workspace,
logs) before admitting work; keep one writer per program, archive and project and
never kill or restart another owner's process; reuse existing analysis and valid
receipts; activate Python changes only through the in-process reloader after
corroborating the serving process; never use systemctl; and, under the current
mission, run no filesystem tests, test suites or builds for documentation
validation. A finished job, a compiling C file or a screenshot is not verified
recovery.
