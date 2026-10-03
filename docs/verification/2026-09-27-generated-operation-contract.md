# Generated native-operation contract increment — 2026-09-27

Status: packaged exporter and compiled consumer-parser increment. This is partial
M2 preparation for the first K1 GOG model-scale route. It does not establish a
live game operation, an ABI call, a durable actor lifetime, or M1 scenario
acceptance.

## Delivered contract boundary

`agentdecompile.operation-contract/v1` supplies a deliberately narrow native
operation declaration: exact target slug/SHA-256, unique adapter roles, calling
convention/pointer width, units, engine-thread constraint, lifetime rule,
inverse and independent-observation requirement. The hook-pack exporter refuses
to emit a declared operation unless all of these facts hold:

- The selected target exists in the pack and its stored pack hash agrees with
  the contract.
- A readable raw image exists now and hashes to the contract's selected digest.
  A database hash alone cannot authorize this export.
- Every required adapter role maps to exactly one site and that site has exactly
  one selected-build instance carrying an extracted byte window.

The emitted operation records its resolved logical site, adapter key, address,
logical ID and byte window per role, plus the raw-image digest that was actually
checked. It is a target-bound handoff, not an instruction to inject or invoke
the game. `agentdecompile-corpus export-hookpack` now exposes `--site-policy`,
`--adapter-map`, and `--operation-contract` so a catalog/CLI caller can produce
the same contract rather than relying on an internal Python call.

KotorPhasor's hook-pack parser now retains the selected binary's declared
SHA-256 and each site's `adapter_key`/aliases. `find_adapter()` returns no site
when an adapter role is absent or ambiguous, and a generated operation is kept
only when its target, role/site mapping, address and bytes match the selected
pack entries. Model/animation binding moved behind hook-pack admission. It now
requires the exact `target.a.model-scale.v1` operation, matching loaded image
digest and all five resolved adapter roles; the generated role addresses are
what the model adapter uses. Missing or stale generated evidence leaves the
optional model/animation API unavailable without failing ordinary hook startup.
The compiled profile still provides separately guarded ABI/layout data and code
guards; generated layout evidence is a later M2 obligation.

## Evidence

- AgentDecompile source and isolated installed package: **42 focused checks
  passed** (`test_corpus_export_hookpack.py` and `test_cli_refusals.py`). The
  new cases cover exact raw-image agreement, all five model-role bindings and
  refusal after an image mismatch. The only warnings are existing unregistered
  `pytest.mark.unit` warnings.
- The packaged wheel is `2.0.1.dev0+autonomy20260927.11`, SHA-256
  `ab271201d0631b2b6ad4ff6ad3da3147b6fa3c3cec7d852f02f98e14f300613c`.
  Installed module origins for the contract/exporter/CLI were asserted before
  the installed suite ran.
- KotorPhasor rebuilt its existing `kp_hooktool` target and its 32-bit
  hook-table/detour self-test passed with zero failures. The new parser cases
  prove selected-build SHA retention, adapter-key/alias lookup and generated
  operation target/role/address/byte agreement. Existing compiler warnings in
  `hook_bodies.cpp` concern `longjmp` clobbering and are unrelated to this
  parser increment.

The isolated wheel stage is `/dev/shm/ad-generated-operation-_uhvgowu`. The
first installed run was stopped by omitted test inputs in that compact stage;
after restoring `test_cli_refusals.py` and the existing hookpack fixtures, the
same installed package passed all 42 tests. No game, harness, 8080 service,
recovery job or live runtime was started.

## Remaining boundary

The loader now refuses a missing, stale, ambiguous or wrong-build generated
contract. A separate M1 run still needs an owned fixture, actor/world-lifetime
guard, independent before/during/after observation, restoration check and
cleanup receipt. Neither source presence nor this parser/runtime-gating test
proves those runtime facts.
