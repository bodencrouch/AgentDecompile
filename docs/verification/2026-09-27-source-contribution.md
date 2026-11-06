# Observed compiled source contribution — 2026-09-27

Status: independently reviewed source and verified installed development package. This is partial
P0.4/RC-02 delivery, not terminal recovery or a general linker implementation.

## Concrete behavior

The `pe-coff-relocation-free-exact-placement-v1` backend runs an explicitly supported
native Clang `-cc1` invocation over a self-contained C translation unit, retains its
source/object/toolchain evidence, parses one unambiguous standard COFF code section,
and places those actual object bytes into a reserved PE image region. Original bytes
are copied only into the remaining floor spans. Equality alone never grants source
contribution credit.

The independent evaluator reopens the source, object, target, output, toolchain and
selected database row, derives the final writer from ordered writes, and checks the
candidate's actual output span. Discarding or overwriting candidate A gives A zero
credit even when fallback preserves exact image bytes; valid independent B survives.
Source/object/target/output changes withdraw only the affected eligible claims.

Selected-function coverage additionally requires the exact producer database, binary,
address and size. Standalone regions remain region/byte observations. The dashboard
does not turn them into completed functions, and watch progress uses the selected
corpus denominator. SQLite failures return zero credit with an explicit reason.

## Authority and supported domain

Repository-owned compiler and resolved dependency fingerprints identify the supported
Fedora Clang 22.1.8-4.fc44 installation. Unknown executables are rejected before
invocation; an ELF merely named clang cannot mint an observation. The producer uses
fixed arguments and fresh private outputs. Actual native compiler canaries cover
synthetic PE32/i386 and PE32+/AMD64 targets.

Trust is process-local. Only registered producer/writer objects enter acceptance;
imported JSON, cached objects, filenames, historical success booleans and constructed
lookalike objects remain diagnostic. Process/store loss does not restore positive
credit from audit files. The subsequent [fresh revalidation increment](2026-09-27-fresh-source-revalidation.md)
requests new supported production after process loss and hands its live observation
to the existing consumer. Durable trust restoration without reexecution remains
open; this original receipt records the earlier source snapshot.

The supported object subset excludes relocations, ambiguous/split/multiple code bodies,
COMDAT, LTCG/bigobj, nonempty data and unresolved external dependencies. General
toolchains, source contexts, original-style linking and semantic name composition
remain open. `compilerProducedWholeImage` stays false for a preserved-floor image.

## Review and software evidence

Independent review initially rejected arbitrary compiler admission, address-only
function attribution and uncaught SQLite errors. The corrected revision received
scoped approval. Source execution passed 148 cases; the final two consumer corrections
then passed five focused cases. The final seven-file installed selection passed
**149 tests in 174.59 seconds** against the isolated `.9` installation. These suites
overlap; their counts are not added together. Import-origin/version assertions and
the test process's installed-first module path establish which package was exercised.

Root independently checked the built `.9` wheel against all eight current reviewed
module/static files and the 21 locked React assets. The asset hashes match the clean
frontend build recorded in [the live-projection receipt](2026-09-27-live-projection.md).

- Package: `2.0.1.dev0+autonomy20260927.9`.
- Wheel SHA-256: `8954f81788adb8c6d8bc62804c216422c3c89fbbfb1cd0c71907f51e028795e8`.
- Isolated stage: `/dev/shm/ad-source-contribution-final-zwfgFe`.
- Initial build refused outdated host build dependencies. Stage-only build tools were
  installed and the subsequent build and isolated installation succeeded.
- Unchanged package members reuse the verified `.8` snapshot; reviewed changed files
  and newly built frontend assets are explicit overlays. The provenance manifest
  classifies all 596 wheel members: 560 byte-equal reused members, 29 reviewed
  source/static/React overlays and seven generated version/metadata members.
- A subsequently completed read-only canonical snapshot corroborated all 537
  non-generated Python modules with zero missing files or byte differences. It excludes
  generated version metadata and separately verified staged React assets. Later source
  edits require their own build; this receipt applies to this recorded snapshot.
- Durable wheel, logs, source hashes, review and provenance are retained under
  `/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-source-contribution/`.

No recovery/catalog job, Wine/Ghidra/game workload, alternate service or serving asset
replacement occurred. Catalog-driven game-target qualification, runtime capability,
general reconstruction and fresh whole-image recovery remain unverified.
