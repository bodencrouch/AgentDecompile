# Seed compile-input reuse contract — 2026-09-27

This extends the [source/target gates](2026-09-27-target-consistency-gates.md) under
the active session goal. Complete autonomous dependency discovery remains open.

Seed reuse previously ran before compiler resolution. Unchanged source/target bytes
could therefore reuse a result after changes to the compiler, context or environment.
The revised decision resolves the compiler first and compares a content fingerprint
of the observed compilation inputs. A complete declared dependency manifest is required
for positive reuse. Missing or incomplete configuration allows a fresh attempt but
cannot qualify cached success.

The manifest follows the existing complete/files/environment convention. Listed files
are hashed by content. Known inputs include compiler-wrapper bytes, selected context,
working directory, verifier policy/source and selected comparison artifacts. Environment
values are represented only by a digest in recorded evidence. The actual compiler and
objdiff subprocess use the frozen merged environment. Inputs are checked again after
compilation; changed inputs invalidate a fresh positive result.

A declaration is not automatic proof that every transitive dependency has been found.
Before/after checks do not prove immunity to a change-and-restore race in external
executables. No monetary/CPU objective budgets or general runtime self-healing are
claimed by this increment. Independent semantic identity and linked contribution
remain required acceptance gates.

## Configured path and verification

The audit API accepts `compile_input_manifest`, `objdiff_check`, `coff_functions`
and `elf_symbol_bytes`. Known selected parser modules, target object/spec selection,
checker and resolved Node executable join the basis. Unavailable parser/checker setup
keeps closure incomplete. The manifest is exposed through the existing corpus CLI
and generated catalog; standalone compiler-selection setup remains a separate existing
integration boundary. No real compiler profile was qualified by these tests.

The final combined suite passed **140 tests in 1.22 seconds** against staged source and
**140 tests in 1.29 seconds** against the installed wheel. An audit integration test uses
actual snapshot/configuration handling and a controlled compiler: the second unchanged
run reuses its persisted result; wrapper/dependency changes force a compile; missing
parser configuration forbids reuse. Other negatives exercise changed context/environment,
working directory, target-artifact selection and in-flight input changes. The CLI/catalog
test verifies manifest forwarding.

PEP 517 build and isolated install succeeded; both changed modules match canonical source
and wheel members. Stage: `/dev/shm/ad-seed-compile-basis-20260927`. No live service,
compiler recovery workload, or production corpus was modified.

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-seed-compile-basis/agentdecompile-2.0.1.dev0+autonomy20260927.4-py3-none-any.whl)

SHA-256: `f74b1e55490505e86aa25397a5bfce79c458cb5a477d5dc75101df3f23246b9d`.

[Package evidence](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-seed-compile-basis/build-evidence.json).
