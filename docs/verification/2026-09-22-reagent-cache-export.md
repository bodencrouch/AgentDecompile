# Existing cache → ReAgent consumer — 2026-09-22

**Implemented and observed:** a bounded read-only AgentDecompile cache exporter
produced a ReAgent schema-1 snapshot, and the real pinned ReAgent CLI consumed an
existing cached function. This closes the real-cache interoperability canary; it
does **not** establish verified cache-to-binary identity or recovery acceptance.

## Implemented contract

[export_reagent_snapshot.py](../../src/agentdecompile_recovery/corpus/export_reagent_snapshot.py)
exposes:

```python
export_reagent_snapshot(
    *, knowledge_db: Path, program: str,
    addresses: Sequence[str | int], output_dir: Path,
    max_functions: int = 100,
) -> dict
```

It uses the existing `func_knowledge` `(program, entry_hex)` indexed lookup
contract, materializes selected rows in one short read-only SQLite transaction,
and closes the database before hashing or writing artifacts. Selection is explicit,
nonempty and capped at 1,000 functions. Duplicate/invalid addresses are rejected.
The source database is opened with `mode=ro` and `query_only=ON`.

Code, assembly, name, signature and calling convention are preserved when present.
Absent context stays absent: callers, callees, CFG, P-code, data references and
strings have explicit gaps rather than fabricated empty evidence. Cached row
metadata and canonical row digests are retained. The current source schema contains
no original-image digest; `binary_binding` remains `unverified`, and no caller
argument can promote a binary hash into verified provenance.

A new private output directory is required; existing paths are rejected. Files
are individually flushed, a manifest is atomically renamed into place last, and
the directory/parent are flushed. An interrupted write retains incomplete files
without a manifest; consumers must require the manifest before admission. Output
is a provider input proposal with no recovery acceptance authority.

## Isolated regression evidence

[The tests](../../tests/test_reagent_snapshot_export.py) cover preservation,
read-only database behavior, output hashes, missing rows/code, invalid/duplicate/
over-budget selection, existing-destination protection, changed-row identity and
injected output-write failure withholding the manifest. Twelve checks passed using
system Python and pytest with automatic plugins/conftest disabled, a copied test
module in `/tmp`, and the canonical source on `PYTHONPATH`.

## Real existing cache consumption

Input cache:
`/home/brunner56/agentdecompile-nvme/agentdecompile_projects/db/ghidra_knowledge.sqlite`.
Selected stored program: `JadeEmpire.exe`; selected address: `00401000`.
No new analysis, binary download, model call or live server operation occurred.

The exporter selected one existing row containing 228 decompiled characters and
14 assembly lines. Its materialized-row digest was:

```text
61926523cad2284fdda002516f764ca36677f21e81fc79c83b92c7acee2f97bc
```

The installed ReAgent revision
`d12cea338c61898b06a86fe8adb25275fa9d5615` (`0.4.0`) then ran in
`/tmp/agentdecompile-reagent-real-cache-20260922`:

```text
/tmp/agentdecompile-external-canaries-20260922/bin/re-agent --config re-agent.yaml plan --address 0x401000 --max-depth 0 --max-functions 1 --output plan-report.json
```

It exited zero. Independent report-content checks confirmed exact cached source
consumption, exactly one function, retention of the binary-identity gap, retention
of missing-callee evidence, and no invented CFG in the snapshot. The resulting
plan contained nine evidence gaps, including the exported gaps and upstream's
missing-call-context gaps. Zero exit was not interpreted as complete evidence.

[The durable receipt](../../tests/fixtures/external_validation/observed-2026-09-22/real-cache-consumer-receipt.json)
records command/cwd, tool revision, lengths, hashes, all five checks, and raw local
artifact paths. Raw decompiled content remains in private `/tmp` artifacts and
is not embedded in repository documentation or fixtures. The original binary has
not been corroborated against the cache row. CLI/catalog integration is owned by
the parent task and is not established by this module/consumer check alone.

## Final validation environment correction

After tightening new snapshot directory permissions to `0700`, a `/tmp` rerun
reported five passes and seven SQLite fixture-creation `disk I/O error` failures
before the exporter was invoked for those cases. Filesystem inspection showed
`/tmp` is a quota-enabled tmpfs (16 GiB total, about 3.2 GiB available); this
observation does not establish the exact cause of the SQLite errors. A bounded
rerun using `/dev/shm/agentdecompile-reagent-export-final` as pytest's isolated
base directory passed **all 12 checks in 0.60 seconds** with the final source.
No product logic was changed to hide the fixture errors. Scoped whitespace
validation also passed.
