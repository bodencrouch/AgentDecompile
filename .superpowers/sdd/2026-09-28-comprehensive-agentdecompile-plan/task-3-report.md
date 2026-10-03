# Task3.1 implementation report

Status: READY_TO_COMMIT. Source implementation and authored regression cases are
ready for controller review. No staging or commits were performed; controller
owns the Git index and commit. This report establishes source checks only.

## Exact implemented claim and binding

Added `target-macho-stabs-n-fun-name-at-va-v1`, with status
`accepted-target-macho-stabs-n-fun` and reason
`accepted_unique_embedded_n_fun`. The existing PE scope, accepted status,
admission body and `recorded_export_name()` reader remain compatible.

One `identify_binary(..., retain_snapshot=True)` observation supplies the image
SHA-256 and the retained bytes used for strict qualification, retained
`MachO`/`parse_stabs` parsing and candidate-region comparison. There is no second
target read inside semantic observation or candidate comparison. The corpus
digest and candidate target digest must equal that snapshot digest; candidate,
binary and observation binary IDs must agree.

This lane accepts one thin image of a recognized explicitly selected
`binary.arch`. Existing explicit aliases normalize names (for example, x86 to
i386); missing/unknown architecture is a refusal. Header CPU type must match
that selection, and header width must agree with CPU ABI64. A stored width or
format contradiction refuses admission. CPU subtype is taken from the header;
no selected subtype is fabricated. Exact CPU type/subtype, width, endianness and
slice `{offset: 0, size: snapshot length}` are recorded in target and witness.
The VA lane qualifies image file types execute/dylib/bundle; relocatable objects
and other file types are explicitly unsupported.

The observation helper validates the complete declared load-command envelope,
command sizes/alignment, unique LC_SYMTAB, segment/section layouts, VM/file
extents and section relocation extents. Every declared nlist record and its
bounded, terminated, strict UTF-8 string is checked before calling the retained
parser. Symbol and string tables cannot overlap each other or the header/load
commands. A malformed unrelated symbol or attribution string invalidates the
whole observation. No permissive exploratory-parser success is promoted into
semantic authority.

Every named N_FUN row retains raw type, nlist index, record/string offsets,
string index/end, declaration, parsed name, n_value VA and source/object context.
Parsed empty names are refused. Admission requires one globally unique root for
the exact candidate name, exact VA equality, and exactly one named root at that
VA. Duplicate identical roots and conflicting roots are refused without
deduplication. Anonymous closing records do not establish an inferred size.

The entire positive candidate size must map through one complete file-backed
segment mapping, with no second file-backed overlap even when the alternative
only overlaps part of the region. The recorded offset and exact candidate
machine bytes must match the retained snapshot. Virtual tails, partial regions,
ambiguous mappings, wrong offsets and changed bytes refuse admission. Semantic
refusals preserve the already admitted target-local candidate.

The recorded STABS reader checks scope/status/reason/schema; digest and binary
equality; exact duplicated slice and architecture; CPU/width coherence; selected
architecture; raw type and table/record/string bounds; declaration-to-name
parsing; and witness/claim/row name and VA equality. It also checks recorded
region bounds and row size when supplied. It checks internal recorded evidence,
not target currentness or fresh bytes. `recorded_name_witness()` dispatches the
separate scopes, with `recorded_target_name()` serving package naming.

## Consumers and compatibility

`package_recovered.py` uses the dispatcher after its existing source snapshot
freshness and readable-C gates. Witnessed STABS names become filenames; refused
names remain address labels. Its claim text states ingestion-time recording and
absence of a packaging-time target recheck. The selected row now includes size
for STABS recorded-region coherence.

`export_run_report.py` uses the dispatched scope and kind in the identity note
and plugin name. It keeps overall success false, byte comparison unperformed,
and logical IDs advisory. `ingest_recovered.py` only changes summary accounting:
both scoped accepted lanes are excluded from `recovered_without_identity`, and
a separate STABS count preserves the existing PE export count.

The Task8 `parse_recovered(..., coverage_index=...)` seam and
`test_preloaded_coverage_index_pins_observation_and_empty_is_not_absent` were
preserved. None still loads coverage; explicit empty coverage remains empty.
No matching, propagation, identity-edge, seed-ownership or donor distribution
contract was added. A witness is tied to its physical binary snapshot and VA;
unrelated seed/family withdrawal cannot confer or remove this raw-image root.

## Changed paths

- `src/agentdecompile_recovery/corpus/macho_semantic_witness.py` (new strict observation helper)
- `src/agentdecompile_recovery/corpus/semantic_identity.py`
- `src/agentdecompile_recovery/corpus/package_recovered.py`
- `src/agentdecompile_recovery/corpus/export_run_report.py`
- `src/agentdecompile_recovery/corpus/ingest_recovered.py` (summary accounting only)
- `tests/test_macho_semantic_identity.py` (new regression source)
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-3-report.md`

## Verification actually performed

- Read-only brief, implementation-template, existing producer, target snapshot,
  admission, consumer and schema source inspection; initial ownership/status
  inspection. Memory lookup found no task-specific retained guidance and did not
  inform the implementation.
- `python3 -I` with stdlib `ast.parse` and `pathlib` only: AST parsing passed for
  the five changed production modules, new regression source, and unchanged
  `tests/test_ingest_target_binding.py` (seven files). No project module was
  imported or executed, and no bytecode was generated.
- `git diff --check --` the four changed tracked production modules: exit 0,
  no whitespace diagnostics. A stdlib source-text whitespace check then passed
  all seven owned files, including the helper/regression/report, with no trailing
  whitespace or missing final newline.
- Scoped `git diff` and `rg` call-site checks: both recorded-name consumers use
  the dispatcher; the new status counter exists; coverage-index selection and
  its None-versus-explicit-empty regression remain present.

TDD execution was not authorized. No RED or GREEN execution evidence is claimed.
Regression code was authored but not imported, collected or run. No tests,
suites, builds, proof scripts, DB creation/query, Ghidra/compiler/Wine, runtime,
catalog, service, process-management or systemctl actions were performed.

## Authored but unrun qualification cases

The new regression source covers thin 32/64-bit images in both byte orders;
snapshot-only parsing/mapping; raw record/architecture/attribution binding;
C++ qualified declarations; independently named positive and Foo-labelled-Bar
refusal; repeated/conflicting roots; malformed command/symbol/string extents,
unterminated/invalid UTF-8 names and table overlaps; digest, binary-ID,
architecture, selected-width and selected-format mismatch; unsupported CPU,
object file and ordinary-symbol roots; no symtab; wrong offsets/bytes, zero
sizes, partial overlapping mappings, file-tail crossing and virtual-only VA;
classic FAT and FAT64 refusal; recorded witness tampering; real ingress status
accounting; recorded consumers after target removal; independence from identity
edge deletion; and source freshness refusal during packaging.

## Self-review and remaining gates

Self-review checked the whole-symbol-table fail-closed boundary, exact-name/VA
uniqueness, partial mapping ambiguity, consumer-record consistency, PE reader
compatibility, and bounded file ownership. It added relocation extents, explicit
empty parsed-name refusal, candidate binary-ID binding and recorded table/region
coherence checks. No controller documents or concurrent target/frontend worker
paths were edited by this worker.

Behavioral correctness remains unverified until the authorized focused
regressions run. Strict rejection may exclude old or unusual images whose
metadata the exploratory reader tolerates; that is explicit refusal, never
fallback acceptance. Thin image executable/dylib/bundle qualification is the
exact source scope here. Fat images, ordinary symbols, DWARF/PDB/external debug
roots, cross-build semantic promotion and donor/recipient compatibility remain
outside this slice.

No installed consumer, usable retained real-image STABS input, loaded-module
activation, live 8080 acceptance, fresh current-source rebuild, whole-image
comparison, runtime reuse or terminal recovery proof was verified. The local
changes are not a claim that the serving checkout was activated. Those remain
separate authorized acceptance gates.

## Fix round 1: I1 and M1 source responses

Resumed from reviewed head `000d400a5c83ea38501b5c54f47de1033652c8a5`.
Read the complete `task-3-review.md` and confirmed the segment-flag value and
32/64-bit field layouts against Apple's
[Mach-O loader header](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/EXTERNAL_HEADERS/mach-o/loader.h#L334-L369).
No project imports or runtime operations were used for this inspection.

I1: the strict helper now reads the segment flags alongside `nsects`, at the
32/64-bit command field offsets, and refuses any segment carrying `SG_HIGHVM`
with `unsupported_macho_highvm_layout`. This occurs during whole-snapshot
qualification, before the permissive parser or candidate mapper can run.
`region_offset()` is unchanged; no high-VM mapping implementation or claim was
added. The exact lane now excludes high-VM layouts explicitly.

Authored six high-VM refusal cases across 32/64-bit fixtures with
`vmsize=0x800 > filesize=0x600`: a low zero-filled VA, a shifted file-backed VA
with its high-VM-correct recorded file offset, and that shifted VA with the
formerly unchecked ordinary offset. Each asserts local-only status, the
specific unsupported-layout reason and absence of a recorded named witness.
These cases are source only and remain unrun.

M1: the existing ingestion/consumer regression now inserts an unrelated
seed/family edge, asserts its full tuple exists, and confirms the independently
witnessed Bar name. It then deletes that exact edge, asserts absence, reloads
the recorded Bar row and confirms its name still resolves before the existing
report/package checks. The former deletion of an empty table is gone. These
database operations are authored test code; none were executed.

Fix-round changed paths are limited to `macho_semantic_witness.py`,
`tests/test_macho_semantic_identity.py` and this report. Other worker paths,
semantic admission/consumer modules, and the Task8 coverage-index seam were not
edited in this round. No staging, commit or subagent dispatch was performed.

Fix-round checks: stdlib-only `python3 -I` source parsing with `ast.parse` passed
the two changed Python files; source-text whitespace checks passed those files
and this report. Scoped `git diff --check --` on those same three paths returned
exit 0 with no diagnostics. Read-only scoped diff inspection confirmed flags are
read at command offsets52/68, refusal precedes retained parsing/mapping, the
authored fixtures cover both widths and all three address/offset scenarios, and
edge existence/deletion/independent-name assertions are explicit.

No tests, collection, suites, builds, proof scripts, project imports, DB
creation/query, compiler/Ghidra, runtime/catalog/process/service/systemctl
actions or activation were performed. Behavioral execution, installed consumer,
current-target and real recovery acceptance remain unverified. Source checks do
not discharge those gates. Status: READY_TO_COMMIT; controller owns review and
Git index/commit operations.
