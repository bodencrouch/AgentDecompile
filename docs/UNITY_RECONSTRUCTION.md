# Unity game → editable Unity project

Point the front door at a shipped Unity game and get a project that opens in the
Unity Editor:

```bash
uv run agentdecompile-cli reconstruct "/path/to/TheVillainSimulator" \
  --unity-project-out /path/to/output-project
```

Every Unity-specific decision is derived from the shipped player. You do not
tell it the Unity version, the scene list, the build order, which packages the
project needs, or how to avoid running out of memory on a large title.

## Stages

Unity stages run between `snapshot-existing-recovery` and `report`. They are
inert for non-Unity targets: each writes a `skipped` receipt and returns, so
adding them changed nothing for PE/ELF runs.

| Stage | Receipt | Does |
|---|---|---|
| `unity-probe` | `unity/probe.json` | Facts only: `*_Data` layout, Unity version, scripting backend, scene inventory, managed assemblies, XR markers, container sizes |
| `unity-plan` | `unity/plan.json` | Decisions only: memory-budgeted export mode, editor selection, implied package set |
| `unity-export-assets` | `unity/assetripper.json` | AssetRipper headless export → `ExportedProject/` |
| `unity-decompile-managed` | `unity/managed.json` | `ilspycmd` on the game assemblies + scaffolding strip |
| `unity-compose-project` | `unity/compose.json` | Compose the openable project at `--unity-project-out` |
| `unity-recover-excluded-media` | `unity/primary-content.json` | Extract importable media from data files excluded by the memory-budgeted AssetRipper plan into `Assets/RecoveredPrimaryContent/` |
| `unity-editor-validate` | `unity/validate.json` | Headless batchmode open; parse compile/scene/package errors |
| `unity-repair` | `unity/repair.json` | Diagnostic-driven repair loop, re-validating each attempt |

Facts and decisions are deliberately split across the first two receipts: a plan
can be re-derived under a different budget without re-probing, and a surprising
plan is always traceable to the fact that produced it.

## What is derived, and from where

| Decision | Derived from |
|---|---|
| Unity version | ASCII version run in the `globalgamemanagers` header — available *before* any export tool runs, which is what makes editor selection possible up front |
| Scripting backend | `Managed/*.dll` → Mono; `GameAssembly` + `il2cpp_data` → IL2CPP |
| Scene list **and build order** | `levelN` filenames — `N` *is* the build index |
| Package dependencies | Shipped assembly names mapped to UPM ids (AssetRipper emits only `com.unity.modules.*` built-ins, so third-party packages must come from assembly evidence) |
| Export memory mode | Container sizes vs. host available RAM |
| Editor to use | Unity Hub scan, exact version preferred |

## The memory decision

Whole-graph exporters load the asset graph before writing anything, so a title
larger than RAM dies partway through — which is exactly how an earlier run of
this pipeline lost its scenes to an `OutOfMemoryException`.

When the budget is short, `resources.assets` is dropped first: it is the largest
container and the only large one scene export does not need. The remaining
containers are exposed to the exporter through a **symlink** tree, so staging a
2 GiB subset of a 15 GiB install costs kilobytes.

On a real 15.1 GiB title with ~4.5 GiB available, the planner independently
reproduced a staging set that had previously been hand-tuned: 2.42 GiB, dropping
exactly `resources.assets` and `resources.assets.resS`.

The cost is recorded, not hidden — `claimBoundary` states that assets loaded at
runtime from excluded containers become unresolved references.

## Compose what the tools emit

The composition stage copies rather than synthesizes. AssetRipper's
`ExportedProject/` already contains `ProjectSettings/EditorBuildSettings.asset`
with the correct scene build order **and** GUIDs, `ProjectVersion.txt`, a
`Packages/manifest.json`, per-scene lighting folders, and a `.meta` for every
plugin DLL. Hand-writing any of that is duplicated work and a source of drift.

Only two things are genuinely synthesized: package entries implied by shipped
assemblies (merged into AssetRipper's manifest as the base, never clobbering an
existing pin), and `validateReferences: 0` on shipped-plugin `.meta` files.

## Verification, not the MCP bridge

`agentdecompile-recover unity-project-audit --project-root <project>` inventories
Unity-YAML GUID candidates and reports missing file/folder `.meta` sidecars.
Its YAML scan is gated by Unity headers (including `.texture2D` and
`.shadervariants` serialized extensions). Missing sidecars and unresolved GUIDs
are audit findings, not proof of a failed Editor import; package and external
source resolution remain outside this local-Assets audit. Use `--json` for the
complete path-level candidate report.

`agentdecompile-cli recover unity-project-compare --project-root <project>
--reference-project <AssetRipper-export> [--reference-project <other-export>]`
classifies those unresolved local GUIDs against paired `.meta` files in one or
more alternate exports. It reports byte-identical same-path C# candidates,
same-path content conflicts, locally absent paths, and GUIDs not found in the
provided exports. The command is report-only: it does not merge assets or
rewrite GUIDs, and its classifications are not proof that an export is
authoritative or that Unity will resolve/import the proposed content. Use
`--json` for per-GUID paths, occurrence counts, and hashes when same-path files
were compared. Traversal errors, unreadable/malformed metadata, and candidate
files that could not be scanned are surfaced as incomplete coverage and produce
a nonzero exit status rather than being treated as absent GUIDs.

`agentdecompile-recover unity-package-audit --install-root <shipped-game>
--project-root <project> [--project-root <reference-project>]` reports package
IDs mapped from shipped managed assemblies alongside package IDs and literal
versions read from each project's `Packages/manifest.json`. It preserves `*`
and conflicting observations as-is; it never selects a version or writes a
manifest. `--json` includes the supporting assembly names, per-project manifest
observations, scan completeness, and claim boundaries. A DLL-to-package map is
an inference signal, not proof that the recovered source requires a particular
UPM package. The report does not prove package resolution, Editor import,
compilation, or runtime compatibility.

Validation uses `Unity -batchmode -quit -nographics -projectPath … -executeMethod`.
A cold batchmode open performs a full asset import, so nothing depends on an
Editor window having OS focus — an interactive Editor's background asset scanner
is unreliable when unfocused and can take minutes to notice externally-written
files.

An injected `ADRecoveryValidate.Run` opens every build-settings scene and writes
a JSON report: per-scene root object count and missing-script count, plus
compile state. `validatorRan: false` is a normal first-pass outcome rather than a
bug — Unity refuses `-executeMethod` when compilation fails, so the log becomes
the sole evidence.

## Repair loop

Errors are classified into recipes rather than fixed by hardcoded special cases:

| Signature | Recipe | Status |
|---|---|---|
| `CS0579` duplicate assembly attribute | `delete-file` (path comes from the error) | implemented |
| `CS0101` / `CS0111` duplicate type | `dedupe-type` | not implemented |
| `CS0246` / `CS0234` type not found | `resolve-missing-type` | not implemented |
| missing script / GUID | `remap-guid` (via `AuxiliaryFiles/path_id_map.json`) | not implemented |
| package resolution failure | `relax-package` | not implemented |

Unimplemented recipes return `{"status": "not-implemented"}` — they are counted
and reported, never faked. `delete-file` generically catches ILSpy's
`Properties/AssemblyInfo.cs` without hardcoding that filename, and refuses any
path resolving outside `<project>/Assets`.

The loop stops when the project is clean, when no recipe matches, when the error
count fails to decrease (non-convergence), or at `--unity-repair-attempts`.

## Supplemental serialized-media extraction

`agentdecompile-recover unity-export` extracts supported media from a Unity
player's serialized data files. The reconstruction pipeline invokes this
after composition for top-level serialized files that its memory-budgeted
AssetRipper plan explicitly excluded, placing results in
`Assets/RecoveredPrimaryContent/`. In the plan, a file such as
`resources.assets` is the serialized owner; `resources.assets.resS` and
`resources.resource` are external payload companions that UnityPy resolves
while reading that owner. The stage selects and scans owners only. Present
companions associated by the conventional basename are recorded as dependency
evidence and included in the resume fingerprint, but are never treated as
independent serialized inputs. Consequently, an absent owner remains a
`missingPlannedContainers` error, while a planned companion is not put in that
field. A missing, unreadable, or malformed companion is reflected as `partial`
evidence when object extraction reports skipped or failed payloads; it is not
promoted to a complete media-recovery claim or relabeled as a missing owner.

The receipt retains the plan's full `excludedContainers` list and records the
actual `selectedSerializedOwners`, associated `resourceCompanions`, planned
companion names, unavailable planned companions, present-but-unassociated
planned companions, and per-object extraction outcomes. These fields establish
which inputs and dependencies were observed; they do not establish that every
streamed payload was readable or that every object in an excluded owner was
recovered.

Use repeatable `--data-file` selectors to
process a large container independently rather than rescanning the full
`*_Data` directory. The receipt distinguishes exported, skipped, and failed
objects; any skipped or failed objects make its status `partial`.
Repeat `--type` to select a subset of `Texture2D`, `Sprite`, `AudioClip`,
`TextAsset`, and `Font`; without it, all supported types are included. The
receipt records `selectedTypes`. Type selection is useful when a container has
large streamed textures but a smaller independently recoverable audio or text
surface; it does not change Unity object references or make raw payloads
importable by themselves.

To bound texture decoding, pass `--max-texture-pixels N` to `unity-export`, or
`--unity-max-texture-pixels N` to `recover`/`reconstruct`, with a positive pixel
count. The exporter checks parsed Texture2D dimensions before image decoding.
For Sprite objects it resolves the backing color and optional alpha texture
references and checks both dimensions before accessing the cropped image; an
unresolvable or invalid Sprite texture is recorded as a failure without image
decoding. Objects exceeding the cap are skipped. The JSON receipt records
`maxTexturePixels` and each skipped object's file, path ID, texture dimensions,
pixel count, and reason; skipped objects make the receipt `partial`. Omitting
the option preserves the uncapped export behavior.

```bash
agentdecompile-recover unity-export --install-root <game> --out-dir <output> \
  --data-file resources.assets --type AudioClip
```

For example, recover only Texture2D objects up to 1,048,576 pixels each:

```bash
agentdecompile-recover unity-export --install-root <game> --out-dir <output> \
  --data-file resources.assets --type Texture2D --max-texture-pixels 1048576
```

For older exports that contain preserved `.audio.bin` files, run
`agentdecompile-recover unity-audio-decode --primary-content-dir <dir>` to
rebuild FSB5 samples as their native codec files (for example, Ogg Vorbis).
The raw banks remain alongside the decoded samples, and the command verifies
their recorded SHA-256 values before decoding.

If UnityPy's audio decoder rejects a clip, the exporter preserves the exact
inline or streamed payload bytes as `.audio.bin` with a JSON sidecar containing
the original stream offset, size, codec metadata, and source name. This keeps
the bytes available for later decoding without claiming they are a playable
WAV. This fallback is supplemental media evidence: it does not reconstruct
meshes, materials, scene/prefab references, or replace the AssetRipper project.

## Prerequisites

For large games, the AssetRipper stage can use an already-running remote service
while the rest of the reconstruction remains local. The remote game input must
already be present on that host; before export, the CLI compares the relative
path inventory and file sizes (without rereading file contents) and aborts on
any mismatch. The source copy should be transferred with rsync verification;
this preflight cannot detect same-size content differences. SSH
is forced to IPv4 and the forwarded API is
bound to local loopback only; normal SSH host-key verification remains enabled.
The remote output option is an absolute base directory that does not overlap the
input; each invocation creates a fresh unique child beneath it so stale exports
cannot satisfy the current run. The remote AssetRipper API awaits export work
before returning its expected HTTP 302 redirect. After export, `rsync --checksum` retrieves the
project into a fresh local stage directory, first requiring the remote
`ProjectSettings/ProjectVersion.txt`, then a read-only checksum/tree comparison
verifies that copy against the remote output before the local marker check.
Remote mode honors the planned full or staged container set. Staged remote mode
creates a symlink-only input tree as a run-specific sibling of the unique
AssetRipper export directory under the validated remote output base, after
verifying the complete source inventory. The receipt records both the verified
original input and exact staged container list. Excluded containers remain
explicit unresolved asset coverage, never a successful full export claim. A
remote OOM is reported as a failed export, never as a partial success.

```bash
uv run agentdecompile-cli reconstruct "/path/to/TheVillainSimulator" \
  --unity-project-out "/path/to/output-project" \
  --unity-assetripper-remote-host root@100.111.132.16 \
  --unity-assetripper-remote-input /root/work/tvs/input \
  --unity-assetripper-remote-output /root/work/tvs/export/assetripper \
  --unity-assetripper-remote-port 18086
```

`ssh` and `rsync` must be available locally; the remote host needs a reachable
SSH service and the configured AssetRipper HTTP service bound to its loopback
interface. The remote service itself is not terminated by the CLI; only the
temporary SSH tunnel it creates is closed. The receipt records the awaited API
response and input/output tree verification separately. This still does not
prove a successful Unity Editor import or recovery of original studio source.

| Tool | Resolution | Env override |
|---|---|---|
| AssetRipper | `target/assetripper/`, then PATH | `AGENTDECOMPILE_ASSETRIPPER_CLI` |
| `ilspycmd` | PATH, then `~/.dotnet/tools/` (`dotnet tool install -g ilspycmd`) | `AGENTDECOMPILE_ILSPYCMD` |
| Unity Editor | Unity Hub layouts (Linux/macOS/Windows) | `AGENTDECOMPILE_UNITY_EDITOR`, `AGENTDECOMPILE_UNITY_HUB_ROOT` |

All three land in `capabilities.json` under `tools.*`. A missing tool raises
`ToolchainError` → `blocked:toolchain` (exit 2) rather than silently degrading.

## Claim boundary

A successful run proves: the Editor opened the composed project in batchmode
with N compile errors, resolved packages, and opened M/T build scenes with K
missing script references.

It does **not** prove byte-identity with the shipped build, correct gameplay
behavior, or that content excluded by a staged export left no dangling
references. Decompiled C# is behavioral reconstruction, not original source.

## Known gaps

- `agentdecompile-recover unity-export-meshes --install-root <game>
  --data-file resources.assets --out-dir <scratch> --format raw
  --max-object-mib 256` preserves each serialized Mesh object payload
  byte-for-byte in a standalone file. `--format obj` instead exports a lossy
  geometry derivative. Both decode one Mesh at a time when whole-graph
  AssetRipper import exceeds memory. UnityPy still builds an in-memory object
  index for each selected serialized file, so the per-object ceiling does not
  bound that index's memory. The receipt records source SHA-256, canonical
  source path, Unity path ID, serialized byte range, output size/hash, and
  per-object skips or failures; matching outputs can be resumed. Raw payloads
  do not include externally streamed resource bytes or repair the Unity
  reference graph; OBJ does not preserve serialization, materials, scene
  references, or complete skinning/blend-shape fidelity. Keep output outside
  `Assets/` unless deliberately reviewed as a separate salvage artifact.

- **IL2CPP is detected and blocked, not supported.** Managed code is compiled to
  native, so no decompilable assembly exists; real support needs
  Cpp2IL/Il2CppDumper.
- Four of five repair recipes are stubs.
- Editor **version drift** is reported (`editor.match`, `editor.versionDrift`)
  but not prevented: opening a 2022.3 project in Unity 6 silently upgrades
  assets. Pin with `--unity-editor-version` when that matters.
- The AssetRipper invocation is ported from a working PowerShell implementation
  and exercised against a stub server; it has not yet been run end-to-end
  against a real title from inside this pipeline.

## Serialized reference graph inventory

`agentdecompile-recover unity-reference-graph --source-file <serialized-file>
--out-jsonl <scratch>/references.jsonl` records source file identity, Unity
object PathID/type/name, and non-null PPtr edges including typetree field paths
and external file-table path/GUID/type. The adjacent SQLite checkpoint allows
decoded and partial objects to be resumed; failed objects are retried. The
JSONL graph schema is v2 and the SQLite checkpoint schema is v3. A strict
typetree failure is retried with lenient bounds checking; if that yields a
traversable mapping, the row is marked `partial`, retains the strict error, and
records any non-null PPtrs found. Partial rows keep the receipt `incomplete`;
`partialObjectCount` and `failedObjectCount` are reported separately. A
checkpoint with an older schema is rejected before the receipt or graph is
rewritten. Keep both outputs on NVMe for large files. This inventory does not
resolve missing project GUIDs, modify YAML, export assets, decode texture
pixels, or prove Editor import readiness. Use its source PathIDs as
reconciliation evidence only where a direct owner join is established; absent
joins and GUIDs remain unresolved. The CLI returns nonzero when the receipt is
`incomplete`.
