# External validation integration design

Status: **designed; integration implementation and tool-backed acceptance outstanding**.
This document originally covered design only. The later explicit user build request
authorizes implementation under the existing catalog and process-ownership rules.
[Session obligation audit](2026-09-22-session-obligation-audit.md) tracks completion.
Command examples below remain interface specifications rather than bypasses around
the operational catalog.

## Implementation progress after build authorization

Pinned real ReAgent benchmark/snapshot-plan and reccmp annotation-lint canaries
have now run against original tiny fixtures. See the [tool receipt](../verification/2026-09-22-external-tool-canaries.md).
The bounded `corpus.normalize-validation-report` CLI/catalog action reads ReAgent
benchmark and reccmp comparison JSON as unaccepted diagnostic proposals. It records
the raw report digest, rejects unknown/malformed/empty schemas, and explicitly leaves
actual provider invocation, input binding and freshness unverified. It never writes
accepted recovery state. It is a report-reader portion of the adapter, not the full
job-owned execution and acceptance integration specified below.

The new `corpus.export-reagent-snapshot` adapter now exports bounded selected cache
rows through a read-only transaction. Actual existing cache evidence has been
consumed by pinned ReAgent; see the [cache-export receipt](../verification/2026-09-22-reagent-cache-export.md).
This closes a cache-format seam, while original-binary identity, complete context,
and scientific candidate acceptance remain open.

Upstream ReAgent already supports the `ghidra-json` snapshot backend. Prefer adapting
existing cached AgentDecompile evidence into that format before building another
bridge or starting analysis. Missing cross-references must remain missing evidence;
empty lists may be emitted only when the source actually established emptiness.
Its benchmark exit zero means expected outcomes were met, including expected
mismatches. reccmp annotation lint emits text/exit status, not the comparison JSON
schema. Its comparison serializer omits unmatched entities; report row count is
never the eligible denominator. Real PE/PDB comparison remains outstanding.

## Selected integration architecture

The selected future integration is optional external CLI adapters for reccmp and
ReAgent, using AgentDecompile's task and acceptance contracts. This avoids duplicating
their comparison/checker engines while preserving independent acceptance. A shared
Python import is rejected because it would couple the server environment and
internal APIs; vendoring is rejected because no required capability currently
justifies maintaining a fork. Reconsider only if a measured CLI limitation blocks
a required contract and an alternative meets the same isolation/receipt criteria.

The following revisions were inspected in the earlier design pass. They are
**proposed baseline references**, not installed dependencies or a transitive lock:

| Tool | Reference revision | Planned use |
|---|---|---|
| reccmp | `e91a51bfadfbb600adfdc750589ac40ae9742883` | Supported MSVC/PDB comparison diagnostics |
| ReAgent (`auto-re-agent`) | `d12cea338c61898b06a86fe8adb25275fa9d5615` | Independent candidate/checker and configured validation |
| isle | `8119bd013645972c72480e4de21529f1e91ce5c7` | Recovered-project output reference |

Before implementation chooses install pins, resolve transitive dependencies in an
isolated environment and record supported host/target capabilities. That is a
future implementation gate, not a prerequisite for completing this design.

[Recovery contracts](2026-09-22-recovery-contracts-and-validation-plan.md) define
proof scopes. [Task and acceptance design](2026-09-22-task-acceptance-and-continuation-design.md)
defines execution ownership. The following command forms are documentary provider
interface examples, **not instructions to run them during planning**:

| Provider | Upstream command | Inputs / claim |
|---|---|---|
| reccmp | `reccmp-reccmp --target TARGET --json report.json --silent` | Project/build/user configuration, annotated source, original and rebuilt binary, matching PDB; comparison report |
| reccmp | `reccmp-decomplint --target TARGET` | Annotation consistency |
| reccmp | `reccmp-vtable --target TARGET` | Vtable diagnostic |
| reccmp | `reccmp-datacmp --target TARGET` | Global-data diagnostic |
| ReAgent | `re-agent --config CONFIG doctor` | Tool/configuration readiness; not recovery proof |
| ReAgent | `re-agent --config CONFIG plan --address ADDRESS --max-functions N --output manifest.json` | Bounded stored evidence; no model calls |
| ReAgent | `re-agent --config CONFIG parity --address ADDRESS --strict-exit` | Source/binary heuristic checks; RED must fail, GREEN is not exactness |
| ReAgent | `re-agent --config CONFIG status --manifest manifest.json --format json` | Stored checks, coverage and stale results |
| AgentDecompile | `agentdecompile-cli --server-url http://127.0.0.1:8080/mcp tool --list-tools` | Existing server tool discovery; no recovery submission |

The future adapter must execute tools without shell interpolation, in a job-owned working directory with
timeouts and bounded output. Pin executable versions and retain argv, cwd, exit
code, stdout/stderr hashes and raw report hashes. Original/rebuilt/PDB/source and
analysis dependency hashes must match the scheduled snapshot. Reject missing,
empty, malformed or stale reports; keep diagnostic failures separate from tool
execution failures. Never parse a success banner or aggregate score as proof.

ReAgent needs evidence from its supported bridge/backend. Implement conversion or
an adapter for existing AgentDecompile snapshots before claiming native integration.
Do not start a second Ghidra analyzer to satisfy that dependency. Bind meaningful
candidate-consuming build/test/runtime gates, independent checker evidence and
bounded provider calls before reversal; record configured trust and policy. No
provider credentials belong in the exported project or receipt.

reccmp source annotations and build-specific comparison addresses belong to the
recovered project. Runtime packs instead bind exact build identity plus RVAs/live
checks, or supported unknown-build discovery. Plan comparisons where supported;
objdiff and final image comparison remain separate gates. Preserve licenses and
upstream provenance rather than copying toolkit implementation into the core.

Upstream references: [reccmp](https://github.com/isledecomp/reccmp),
[ReAgent](https://github.com/Dryxio/reagent), [isle output example](https://github.com/isledecomp/isle).


## Adapter envelope and result normalization

All adapters consume a task envelope naming the original input digest, analysis
snapshot, candidate/group digest where applicable, target capability profile,
provider revision, expected output format, acceptance-policy digest and resource
claims. They emit immutable raw output plus a normalized **proposal**. Adapters
cannot update accepted bindings, source selections, runtime permissions or coverage.

| Result field | Contract |
|---|---|
| `task_id`, `attempt_id`, `generation` | Associate output with the admitted attempt; late generation cannot publish |
| `provider`, `provider_revision`, `argv_digest` | Exact provider and effective invocation, with secrets excluded |
| `input_digests`, `analysis_snapshot`, `candidate_digest` | Content identities, not filenames alone |
| `raw_report_digest`, `stdout_digest`, `stderr_digest` | Preserve original evidence; normalized summaries are traceable |
| `execution_state` | completed / crashed / timed_out / unavailable / unsupported / invalid_output |
| `checks[]` | kind, outcome, scope, assumptions, compared regions and evidence roots |
| `gaps[]` | Missing prerequisites with eligible fallback or wake condition |

A missing/empty/malformed report is `invalid_output`, not zero mismatches. A tool
that cannot express a proof yields `unsupported` for that check. A process exit 0
with a negative diagnostic retains the negative diagnostic. A nonzero exit with
partial valid results preserves the completed units but cannot manufacture a
complete comparison. Report-schema versions are explicit; unknown versions are
retained raw and require an adapter update before normalized acceptance.

## reccmp route

Inputs: exact original image; rebuilt image and matching PDB; source snapshot with
build-specific annotations; provider project/build configuration; supported target
profile. Validate these identities before comparing. The output proposal retains
per-function comparison details, excluded regions and tool-specific caveats; vtable,
data, exports and stack diagnostics remain separate check kinds. A top-line match
percentage cannot certify whole-file identity, ABI safety or behavioral equivalence.

The acceptor checks the emitted source-contribution map and independent original
linked bytes where a reconstructed object was used as the local oracle. No report
from another PDB/build can be re-keyed as current. Known unsupported compiler or
format is a named provider limitation; other providers and runtime lanes continue.

## ReAgent route

Input snapshot export/conversion is a dedicated read-only task. It maps exact
program digest, addresses/regions, decompile/assembly/CFG/type evidence, limitations
and provenance into the chosen supported backend format. Conversion records lost
or unsupported fields; it does not regenerate Ghidra analysis for uniformity.
A compatibility canary must demonstrate that the provider reads the intended
snapshot and cannot write the live program or acceptor store. This is specified,
**not run**.

A bounded manifest selects functions/groups, dependencies and source overlays.
Reverser/checker separation supplies critique but not an independent byte oracle.
The future configured build/test/runtime commands must consume the candidate and
produce declared postconditions. ReAgent's configured-command trust is granted
only by the operator-owned policy; model output cannot modify that policy.
Heuristic parity, structural checks, model opinion and executed behavioral gates
are separate records, including UNKNOWN. Preserve call limits, exact responses,
provider errors, usage and stale-result detection. Source-only mode must name its
missing binary evidence and cannot satisfy binary-backed acceptance.

## AgentDecompile route and test responsibilities

AgentDecompile's CLI/MCP is the planned access path to existing analysis and shared
capabilities. Recovery mutations use whichever owner-identified action catalog is
authorized at implementation time; planning never contacts it. A CLI listing is
interface discovery only. The design's future validation matrix uses ReAgent for
independent recovery/checker scenarios, reccmp for supported rebuild diagnostics,
and AgentDecompile CLI for shared consumer-path checks. Filesystem/unit regression
tests, if later authorized, supplement these tools; none is mislabeled as a
universal test runner for the others.

## Exported project layout (illustrative, not created)

```text
<family>/<build-id>/
  project-manifest.json      # image/toolchain/adapter/snapshot/policy identities
  recipes/project.yml       # declarative prepare/build/compare routes
  source/fragments/         # candidates distinct from accepted contributions
  source/groups/            # TU/LTCG assembly recipe, references fragments
  preserved-regions/        # explicitly accounted floor; input provenance
  headers/                  # build-specific layouts + opaque unknown spans
  comparison/reccmp/        # original raw reports + normalized proposals
  comparison/objdiff/       # validated references + declared relocation map
  evidence/                 # scoped receipts + independent roots + invalidations
  runtime/                  # pack, capabilities, locator/root recipes
  readiness.json            # per-entity/build/operation states and limitations
```

Manifest references are content-addressed and published last. Original retail
images and proprietary toolchains are externally supplied inputs, not silently
embedded distributable dependencies. The same family may export several builds;
logical field names can be shared, physical layouts and ABI profiles cannot be
assumed equal. Preserve upstream licensing and attribution when choosing any
later packaging strategy; the current plan vendors no upstream code.

## Future negative acceptance cases — NOT RUN

| Case | Expected result | Independent work that proceeds |
|---|---|---|
| Correct rebuild with wrong PDB | Comparison rejected for input identity | Other build's valid comparison |
| Exit 0 + empty JSON | invalid_output; no acceptance | Snapshot export/reporting |
| ReAgent GREEN but wrong constant | Candidate retained as proposal; byte/behavior gate rejects | Other functions and original-code runtime |
| ReAgent source-only report | Binary checks remain unknown | Source-only diagnostics |
| Unsupported target in reccmp | unsupported with capability reason | Suitable comparator or other ready tasks |
| Model changes configured validation commands | Policy mismatch; reject attempt proposal | Existing accepted work remains readable |
| Candidate compiled but linker discards it | No source-contribution credit | Floor remains honestly accounted |
| Provider timeout | Preserve durable prior units; bounded scheduler retry | Other provider/resource-independent tasks |


## Relocatable project recipe and input resolver

A project is not portable merely because its files can be copied. Its manifest
must reference a versioned declarative recipe that completely describes how to
prepare, build and compare the selected profile. A future generic runner exposes
three operations (`prepare`, `build`, `compare`) through the authorized task/catalog
adapter. These are proposed interface names, not existing CLI verbs to execute.

| Recipe field | Required meaning |
|---|---|
| `schema`, `profile_id`, `target` | Version, selected build/profile, format/architecture/ABI and supported host requirements |
| `inputs` | Logical input IDs, expected digests/sizes, required/optional status, toolchain/library/original roles |
| `path_bindings` | Project-relative paths or logical input roots; explicit target-platform path translation |
| `environment` | Declared locale, language/FP/packing/macros, required variables and tool revisions; secret variable names only |
| `compilation_groups` | Fragment IDs, includes/declarations, TU/LTCG relationships and scoped flags |
| `steps` | Provider operation or argv arrays, dependency IDs, logical cwd, input IDs, output IDs and timeout/resource profile |
| `placement_recipe` | Region/fixup/data/metadata layout identity consumed by reconstruction mode |
| `checks` | Ordered prerequisites and independent compile/local/linked/contribution/file predicates with policy revision |
| `output_manifest` | Logical output paths, content hashes, source/floor accounting and raw/normalized evidence references |

The resolver searches explicit operator-provided mappings and verified local
content stores for each logical input ID, verifies digest/size, and reports missing
or conflicting input candidates. It never guesses a replacement toolchain or
silently fetches proprietary binaries. All source and output paths are relative
to the project or declared input roots. Host A's absolute paths may appear only as
non-executable provenance, not invocation dependencies. A host-B Wine or container
path translation is a versioned environment adapter; unresolved translation is
unsupported/missing prerequisite, not a hardcoded fallback. Credentials and local
home directories are not exported in recipes.

The compiler/toolchain can be external while its immutable identity and required
components remain complete. The generated recipe records actual scoped flags and
verified supported operations; it does not assume a modern MSVC switch exists on
a legacy compiler. `prepare` yields a complete verified input closure; `build`
produces a job-private result and contribution map; `compare` submits scoped
proposals to independent acceptance. A recipe can select either reconstruction
or original-style build, but must name which method its results establish.

Illustrative resolution: `original-image` and `compiler-bundle` are content IDs.
Host A supplies `/inputs/original.exe` and a compiler root; host B supplies different
local paths for the same digests. The recipe refers only to those IDs and
`project/source/groups`. Different host mappings cannot change the task's semantic
input identities; any changed toolchain content requires a new basis.

**Future portability acceptance — NOT RUN:** export on host A, copy to a clean
directory/compatible host B without A's home directory or environment, supply
external originals/toolchain by verified input mapping, resolve the recipe, and
produce the same declared checks under the recorded basis. Deliberately leave one
absolute author-machine path in a step: preparation must reject the nonportable
recipe before execution. If hosts have unsupported execution capabilities, record
that limitation rather than claiming universal host portability. This scenario
establishes relocatable instructions for a supported environment, not cross-ABI
binary interchangeability or completed recovery.
