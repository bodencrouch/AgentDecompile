# Native SDK integration provenance

This integration merged `wip/native-sdk-local-agentdecompile` at
`6053525b8f1d9764563d29191091b3e71c022977` into consolidation base
`0532da9bcb18d0a1bee5119b7e2117d959f7766b`. Their merge base is
`71d19753ba373e2c487976e6233bee2fe47dc271`. The merge retains the native SDK,
snapshot producer and replay paths, process pool, consumers, fixtures, native
workflow, focused tests and their commit ancestry.

Current strategy and operating authority won every overlap. The integration
adds the JVM-free replay tier without replacing the current active plan,
recovery ladder, 8080 catalog or ownership rules. The current canonical tiered
analysis skill remains authoritative. The native branch's batch-decompile
registration and dispatch were added to the current corpus CLI. Old
formatting-only and default-gate repairs to unrelated recovery, dashboard and
workbench files were not replayed over their newer target versions.

The recorded `vendor/ghidra` gitlink is
`5a6cd6929690110e804194825b0424e0d8545725`. That object and its source are
available in the existing local `native-sdk/cmake-standalone` worktree. At
integration time it was not contained by the configured submodule
`origin/master`, the `Ghidra_12.1.3_build` tag or any checked remote ref. The
manual-only workflow therefore begins with a fetchability preflight. A fresh
checkout cannot build the SDK until this exact dependency becomes reachable or
is replaced by a separately reviewed reachable equivalent.

Source review also tightened snapshot boundaries: schema-v0 manifests now
require their fixed snapshot-relative artifact names and reject multiline
console `load_name` values; `gnsdk-batch` rejects snapshot savefiles outside
`functions/<name>.xml`; and the Rust wrapper frees result buffers on every
status, accepts documented warning/partial output statuses, and decodes UTF-8
instead of mapping bytes to Unicode scalar values.

Verification for this integration is source-level plus focused JVM-free Python
behavior. It does not establish a native build, installed package, live worker,
JVM/Ghidra export, CI, performance, whole-image or gameplay result. The living
native plan keeps its unchecked work packages and deferred backlog as the
authoritative statement of remaining scope.
