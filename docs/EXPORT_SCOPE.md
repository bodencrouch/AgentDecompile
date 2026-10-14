# Export scope and explicit exclusions

The [frontends and exports plan](plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md)
defines the required bundle artifacts and their acceptance gates. A required
artifact that cannot be produced or verified blocks successful bundle publication.
An unresolved entity inside a valid artifact is a different outcome: preserve its
explicit status and reason. Do not replace a missing required artifact with an
optional exclusion.

## WASM scoping receipt (U40)

```json
{
  "artifact": "wasm-consumable-pack-bindings-harness",
  "status": "not_in_scope",
  "reason_code": "export_target_unscoped",
  "reason": "No concrete WASM consumer ABI, binding format or harness export target is specified in the frontends export contract.",
  "scope": "frontends-export-bundle",
  "requirements": ["R64", "R65"],
  "unit": "U40"
}
```

This is a documentation scoping receipt, not a generated bundle, a verification
receipt, or a completed browser-runtime capability. The future bundle manifest
must retain this exclusion explicitly until an export target is defined. Its
content-addressed basis and artifact hashes belong to the actual bundle exporter;
this document does not fabricate those values.

Three distinct browser workstreams cannot satisfy this export implicitly:

- Browser-local analysis may use a WASM disassembly provider.
- Donated browser compute may return bounded proposals for independently verified
  tasks within the browser worker's qualified capabilities.
- The autonomous roadmap's M7 targets a whole game running interactively in the
  browser, requiring an executable route and rendering, input, audio, save and
  sustained-play evidence.

WASM and graphics/GL are first-class capability areas in the higher-level
reverse-engineering workbench: supported analysis, comparison, visualization or
target instrumentation may run through browser-portable providers. That does not
define a WASM hook-pack consumer, replace Ghidra's JVM-backed analysis, or
establish native compiler, objdiff, or whole-image recovery proof. Target-side
graphics observations and browser-side visualization are separate evidence.
Claims must name the actual operation and supported target rather than treating
“runs in the browser” as a capability or proof category.

None defines a WASM consumer of the hook pack, generated bindings or runtime
harness. Likewise, this narrowly scoped exclusion does not remove M7 from the
[autonomous capability roadmap](plans/2026-09-22-autonomous-capability-product-roadmap.md).
That delivery obligation and its acceptance evidence remain independent.

To replace this exclusion, specify the intended consumer and artifact, target ABI
and memory model, operation boundary, supported architectures, and deterministic
verification/consumer checks. A JavaScript wrapper, a compiled WASM utility or a
browser shell alone does not close that contract.

## Other optional rows

Recovered-source variants may receive `not_in_scope` only when source recovery is
outside the declared export run. If included, byte-accurate C+assembly-floor and
max-C retain separate manifests and acceptance. The required pack, bindings,
cave plans, headers, readiness and divergence artifacts cannot use this exemption.

The [product and workspace guide](PRODUCT_AND_WORKSPACE_GUIDE.md) explains how
both interfaces expose these boundaries before offering artifact downloads.
