# Task 11.2 target binding — source-only verification note

Date: 2026-10-02. Implementation base supplied by controller:
`2590e25a5926d195f34e88b0675095cf1891e6c2`.

This note records source checks, not a producer run or independent acceptance.
No project module was imported. No tests, builds, proofs, databases, decoder,
compiler, Ghidra, workers, recovery CLI, catalog, service, process mutation or
systemctl operation was run. Regression source is intentionally unexecuted.

## Checked source

- `src/agentdecompile_recovery/grid_lanes/target.py`
- `src/agentdecompile_recovery/grid_lanes/__init__.py`
- `src/agentdecompile_recovery/grid_lanes/splitter.py`
- `src/agentdecompile_recovery/corpus/mkobj.py`
- `tests/test_grid_target_binding.py`

A standard-library-only `python3` heredoc read each file and called
`ast.parse(Path(name).read_text(), filename=name)`: all five parsed. AST counting
found 42 regression functions; parametrization expands many refusal cases.
This is syntax/source evidence only, not an import or behavioral result.

A second standard-library-only AST audit read `_CLOSURE`, resolved its explicit
module/source mappings, looked up function/class definitions, and applied
`ast.literal_eval` to the defaults of the listed functions. Result:

```text
Fixed closure: all 59 function names exist and all checked defaults are literal
Sole writer call explicitly uses reference_free_only=True and empty symbol_prefix
No subprocess call in target lane AST
```

The same audit found exactly one `mkobj.write_object` call and checked its keyword
AST values. It did not call that function, compile a project file, execute a
project source node or import the package. The implementation itself uses Python
`compile` without `exec` when it later reconciles loaded function code against
captured source; that future lane behavior was not invoked here.

The command below returned exit 0 and no whitespace diagnostics:

```bash
git diff --check -- src/agentdecompile_recovery/corpus/mkobj.py src/agentdecompile_recovery/grid_lanes/__init__.py src/agentdecompile_recovery/grid_lanes/splitter.py
```

Call-site review used:

```bash
rg -n 'reference_free_only|plan_mkobj_target|MkobjTarget' src/agentdecompile_recovery/corpus/mkobj.py src/agentdecompile_recovery/grid_lanes/{target,splitter,__init__}.py
```

The new untracked files were read directly and parsed with AST; tracked `git
diff` alone does not include their content. No staging or commit was performed.

## Transport refinement

The controller explicitly adopted LocalDirStore as the bounded first transport
scope. `size()` is checked before reading. The lane walks relative object/shard
paths with `dir_fd` and `O_NOFOLLOW`, rejects escapes and nonregular files,
copies in bounded chunks into newly owned scratch files, stops at the byte cap
even if the source grows, and hashes actual bytes. Scratch files are not hard
links to CAS. Unsupported adapters/platforms are unavailable; arbitrary
unbounded `get()` or `get_path()` is never invoked by this lane. Other grid
transports require a separately qualified bounded read route.

## Regression source prepared, unrun

Positive cases use synthetic i386 and AMD64 PE bytes, a minimal SQLite snapshot
with deliberately unenforced uniqueness/types, actual `write_object`, both
canonical output refs, and independent recomputation. Refusals cover:

- C7/XBEGIN, E8/E9, short branches, 0F, possible AMD64 RIP-relative ModRM;
  forbidden decoder instrumentation; backwards-compatible legacy decoder route.
- Snapshot singleton membership, view substitution, NULL/string/float/multirange
  extents, image identity, selection spoofing, generation/membership task IDs.
- Exact integer fields, extra request fields, scheduler fields outside task ID,
  timeout caps, address overflow, mapping truncation/padding/overlap/cross-section.
- Missing/corrupt input and output, missing/extra/forged proposal associations,
  duplicate JSON keys, changed objects and receipts, self-consistent forged output
  requiring recomputation, changed scratch input, false publication refs.
- Helper replacement, changed source/defaults without reimport, missing source,
  changed machine constants, constants changing during generation, different cwd,
  self-asserted implementation, unavailable transport/storage/SQLite and deadline.

## Open real gates

Separate authorization is still needed to execute regressions and observe the
producer. A real admitted raw-image/snapshot selection, measured resource
behavior, object-store/runtime capability qualification, producer/verifier
identities and independently persisted VERIFIED record have not been shown.
Revocation/same-lineage/unadmitted-implementation policy is retained in the
existing verifier machinery and needs actual integration evidence. No permissive
acceptance callback or test-only signer was added.

Current catalog admission and use of the existing 8080 action are not established.
No alternate-port or direct-CLI route was added. General decoder support is
unsupported. The dashboard remains outside this slice: it cannot connect until
this target binding plus exact source/compile binding, full parity and current
admission form one independently authenticated chain.
