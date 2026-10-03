# Next reconstruction prerequisite: same-build linked contribution

Source-only investigation, 2026-10-02. This report follows
`reconstruction-prerequisite-brief.md` and the bounded consumed source chain.
Only this report was written. No tests, builds, imports, database queries,
compiler/Ghidra/proof execution, runtime/catalog/process operations, Git mutation
or publication occurred. Historical game receipts and completed Task1 target
binding / Task13 owner-slot fixes were not re-audited. The memory registry was
used only to retain the distinction between source and live acceptance; the
findings below come from current source reads.

**Answer: the retained chain is incomplete in source, not merely awaiting an
acceptance run.** There is an actual direct compile/link/whole-file comparison
runner, and a separate trustworthy bounded compiled-region contribution
mechanism. The direct runner does not consume an observed relationship between
its linked objects and the replacements in its checked final image. Its local
verification pass recompiles different temporary objects. The terminal static
consumer explicitly has no supported evaluator. Neither changing
`finish_binary.compilerProducedWholeImage` nor importing a successful-looking
JSON receipt supplies the missing predicate.

**One next bounded source task:** make the direct full-image acceptance decision
require a producer-bound **same-build linked replacement contribution** verdict.
The verdict must bind the final candidate being compared to the objects actually
compiled and linked by that invocation, its captured current source and exact
toolchain inputs, and the expected emitted regions/fixups. It must refuse missing
or changed bindings, incomplete required contributions, and discarded, folded or
preserved-fallback replacements. The decision seam is
`verify_direct_full_image.py:99–116`; the existing link result at
`compile_link.py:407–416` cannot supply that verdict. This is one acceptance
predicate slice, not permission to implement a game engine, invent a linker
oracle, widen the supported native-clang backend, or claim U4/U33 complete.

## Required contract

`unit-4-requirements.md:8–10` requires exact compiler/context calibration,
reconstructed fixups and metadata, compiled replacement ownership of compared
output, a fresh complete-current-source whole-image run, and independent
C+assembly-floor / max-C accounting. `unit-33-requirements.md:8–13` also requires
hash-bound executable/project/toolchain/inventory/source/receipts, real startup,
data/import/resource context, a clean semantic C/C++ link and an original-game
launch. `STRATEGY.md:209`, `:215` and `:219` explicitly distinguish reconstruction
from original-style rebuilding, local parity from final equality, and preserved
floor from recovered-C credit. Thus final file equality and a generic link
success alone are insufficient.

All source paths below are relative to the repository root; line locators name
the actual retained sources read during this investigation.

## Retained mechanisms and their limits

| Predicate | Current retained mechanism | Disposition |
|---|---|---|
| Fresh current source capture | `src/agentdecompile_recovery/corpus/source_contribution.py:276–296` captures a self-contained C TU into an owned snapshot; `:318–327` rechecks source, target, implementation and toolchain before publishing a process-local capability. | Present for one supported relocation-free region. It is not a complete engine-source capture. |
| Exact invocation / provenance | `source_contribution.py:31–38`, `:211–228`, `:294–317` pin native clang and its loader closure, fix argv/environment and record source/target/object/snapshot hashes. `:331–355` rechecks current inputs and refuses untrusted imported capabilities. | Present for this explicit native-clang backend. It does not authenticate arbitrary VC7 wrappers or a full compiler/linker/header/library environment. |
| Actual compiled replacement reaches output | `source_contribution.py:367–387`, `:432–447`, `:502–523` derive final ownership from actual byte writes and withdraw credit after floor overwrites. `:471–501` rejects untrusted inputs and distinguishes discard/collision/overlap/fallback. | Present for the bounded reconstruction. This is an independent retained invariant, not a link map for the direct full-image build. |
| Supported scope | `source_contribution.py:96–103`, `:134–143`, `:175–184`, `:265–269` restrict objects to one full code section/function, no relocations, substantive associated data, COMDAT, LTCG or link metadata, and no includes/preamble. | Deliberate refusal boundary. Real relocation-bearing engine compilation is not supplied by this backend. |
| Final file comparison | `source_contribution.py:403–418`, `:529–545` reopen/check the complete reconstruction and record output hashes; `verify_direct_full_image.py:80–103` computes complete target/candidate size and SHA-256 equality. | Both exist, with different provenance scopes. Equality cannot transfer contribution credit between them. |
| Summary scope | `finish_binary.py:1–5`, `:109–112`, `:164–189` reconcile local observations and optionally evaluate the typed reconstruction; compiler-produced whole-image and semantic/toolchain acceptance remain false. | Honest retained boundary. No flag repair is indicated. |
| Recovered-project manifest | `recovered_project_manifest.py:3–19`, `:301–335` validate declared TU source/image hashes, provenance and pinned/unpinned toolchain records. `package_project.py:249–260` emits floor TUs as `placeholder`, unpinned and `rebuildable=False`. | Useful identity/placement schema, expressly no compile/link/rebuilt-image proof. The direct terminal runner does not consume it. |

## Concrete source gap in the consumed direct chain

`verify_direct_full_image.py:58–74` actually calls `compile_and_link_tree` in a
new work directory, then calls `verify_recovered_byteexact` separately with
`--no-incremental`. A new directory and candidate/receipt modification-time
checks (`:50–60`, `:84–98`) supply useful freshness boundaries. They do not bind
both passes to one immutable complete source snapshot or one link provenance
record.

The build enumerator is recursive `*.c` with exclusions
(`compile_link.py:82–92`), whereas the verifier enumerates top-level `*.c`
(`verify_recovered_byteexact.py:509–511`). The verifier creates its own preambled
temporary TU and object, rather than consuming the linked objects
(`verify_recovered_byteexact.py:304–328`). Its accepted `ok` is relocation-masked;
it separately reports `rawEqual` and `reloc_linked=False` (`:331–359`). Its emitted
receipt explicitly says `local-relocation-masked; not whole-image or fresh-source
acceptance` (`:865–880`). These facts establish the missing same-build relationship
without executing or assuming a failure of any real target.

`verify_full_image_receipt._load_objdiff` (`:35–57`), consumed by the direct
runner at `verify_direct_full_image.py:92–98`, checks only a nonempty result list,
internal total/matched counts and truthy `ok`. It returns the receipt hash and
counts. It does not require a selected full function inventory, source/toolchain
currency, current target identity, linked relocation outcomes or final-writer
contribution. Therefore a count-consistent local receipt cannot discharge the
linked contribution predicate.

The generic compiler/link helper supplies a useful build, not that proof:

- `compile_link.py:165–229` invokes an operator wrapper and returns paths,
  return code and diagnostics, without an authenticated toolchain/input/output
  hash closure. `:358–359` adds the recovered-C preamble.
- `compile_link.py:157–162`, `:330–333` generate a trivial `main`; the direct
  runner explicitly requests it (`verify_direct_full_image.py:64`). This is not
  recovered original-game startup.
- `compile_link.py:105`, `:275–305` use `/FORCE` and `/OPT:NOREF`, with an object
  response file and generic libraries. No link map, final emitted-region/fixup
  verification or original-layout specification is returned there. An ordering
  or retention switch would not independently prove contribution.
- `compile_link.py:373–376`, `:403–416` link successful objects and return link
  `ok` even while recording compile failures separately. The direct runner only
  checks link `ok` (`verify_direct_full_image.py:75–76`) and derives its compiler
  flag from that same value (`:112–114`). A clean complete-source acceptance must
  not infer completeness from this value.

The arbitrary `--build-command` wrapper is intentionally still fail-closed:
`verify_full_image_receipt.py:129–148` unconditionally records missing direct
compiler/link provenance, `verified=False` and `compilerProducedWholeImage=False`.
It is not an alternate completion route.

The actual static terminal consumer is similarly explicit:
`dashboard/byte_parity.py:94–96` returns `{}` from `_full_image_receipt` because
there is no supported terminal link evaluator. `:110`, `:141–143` derive terminal
flags from that empty result. Its typed contribution evaluation at `:113–135`
stays separate. A future terminal verdict must eventually be consumed here;
simply teaching this function to trust JSON booleans would undermine the existing
process-local producer boundary.

## Variant and admission boundaries

`dashboard/byte_parity.py:43–66` keeps imported variants diagnostic; `:133–135`
sets byte-accurate C/floor counts from qualified contribution and retains
`byte_identical=False`. The direct terminal runner accepts no variant-specific
manifest and emits no C/floor provenance split
(`verify_direct_full_image.py:21–32`, `:105–118`). Independent C+floor and max-C
terminal accounting is therefore another undisclosed-to-the-runner prerequisite,
not something inferred from historical counts. Preserve the distinction when
designing the contribution verdict; one variant's artifact cannot certify the
other.

The action exists in source as `corpus.verify-direct-full-image`:
`corpus/cli.py:716–729` defines its parameters, `:1510–1519` dispatches it;
`dashboard/actions/introspect.py:120–161` derives corpus action IDs/fields from
that parser, `catalog.py:107–112` loads generated actions, and `:462–463` builds
the corpus backend command. This is the catalog route, not an operating
instruction to bypass 8080 with a direct CLI.

Source presence of this action does not establish compiler/Wine ownership:
the direct parser at `cli.py:716–729` sets no mutating/long-running flags;
introspection reads those flags at `introspect.py:132–148`. The audited external
resource map in `jobs.py:239–247` includes three other actions and no direct
full-image action. `_external_resource_entries` (`:423–439`) only emits those
mapped reservations. The external-owner guard at `:2147–2160` expects `workDir`,
`work_dir` or `out-dir`, while this action's parser field is `work-dir`. These are
named integration prerequisites for admitting this particular new route; they
do not reopen the completed generic worker-slot fix. No actual job/process or
live catalog state was inspected, and no safe admission is claimed.

## Smallest actionable slice and explicit remaining gates

The next task is the missing same-build linked contribution **consumption** at
the direct runner, using an observed producer contract instead of link `ok` plus
an independently recompiled local receipt. First establish what the supported
link producer can actually observe; if it cannot produce an independently
verified final-region/fixup mapping, make terminal acceptance explicitly refuse
that missing evidence. Retain the existing exact full-file hash comparison and
fresh-work-directory behavior. Preserve the bounded native-clang contribution
path and all honest summary flags. This task needs no speculation about game
implementation and must not treat refusal wiring as successful recovery.

This source slice alone will not close U4/U33. Separate remaining requirements
are a complete captured source/inventory context, supported exact compiler and
linker/header/library/options hashes, a verified placement/fixup backend for the
chosen image, per-variant receipts, terminal consumer integration, and safe
catalog admission of its compiler/Wine/output resources. The absent consuming
checks are source gaps; the real semantic engine project and target/toolchain
availability are runtime inputs not established by this investigation.

The already retained `game-baseline-prerequisites.md` disposition is reused as a
prior audit: it does not establish a clean semantic engine link or original-game
launch. No historical receipt was reopened and no conclusion about other
uninspected receipts is made. Establishing actual original-game launch for the
same chosen, hash-bound clean build remains U33 live acceptance. No successful
baseline, semantic recovery, fresh compiler run, platform qualification or live
consumer activation is claimed here.
