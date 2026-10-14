# Unity reference reconciliation

`agentdecompile-cli recover unity-reference-reconcile` audits the selected
project without repairing references. It scans all regular files under `Assets`
for Unity YAML headers regardless of extension, and indexes every `.meta` file.
Symlinks and traversal/read/UTF-8 failures are reported as incomplete coverage.
Binary/non-YAML files are explicitly listed outside the syntax scan.

```sh
agentdecompile-cli recover unity-reference-reconcile \
  --project-root /path/to/exported-project \
  --graph-jsonl /home/user/Unity/source-graph.jsonl \
  --path-id-map /path/to/exported-project/AuxiliaryFiles/path_id_map.json \
  --out-json /home/user/Unity/reconciliation.json
```

Repeat `--graph-jsonl` for multiple graphs. Receipts are discovered as
`<graph>.receipt.json` or `<graph-stem>.receipt.json`; conflicting siblings require
explicit `--graph-receipt` arguments, one per graph in matching order. The map is
optional and is read only when explicitly selected. The output parent must exist.
Only the requested report is written: no checkpoint, temporary files, folders,
metas or Unity project updates. Project descendants and input/hard-link aliases
are rejected as output destinations. Use NVMe for large reports.

The deterministic JSON retains graph and receipt hashes, complete original
receipts (including incomplete status), declared raw source hashes and UnityPy
version, observed record counts, syntax/read errors, YAML/meta hashes, anchors,
serialized versions, and every non-null placeholder external PPtr occurrence.
Flow and block PPtr syntax is scanned with comments, quoted strings and block
scalars masked. This is a PPtr syntax audit, not a general YAML parser or Editor
validation. Raw source byte hashes are historical receipt claims, not freshly
rehashed game files. YAML line/column and owner anchors retain literal IDs.

An unresolved local GUID, orphan meta, synthetic uniform GUID, or repeated local
GUID is treated as placeholder evidence. Built-in GUIDs are excluded. A unique
local GUID with a present target is outside this placeholder audit; this does not
prove its target fileID is valid. Repeated local GUIDs are `ambiguous`; other
placeholders are `unresolved`. `unresolvedIncludingAmbiguous` counts both.

Candidate groups list numeric graph/map collisions as **rejected evidence**, never
as inferred joins. A number, name, class, type, basename, similarity, or synthetic
GUID cannot prove identity, and partial graph objects can never establish exact
recovery. These input formats contain no authenticated direct source-object to
exported YAML/meta identity binding. Accordingly this version always reports
zero `exact`; adding real identity binding requires a separately reviewed input
contract. Do not use this report to rewrite GUIDs or fileIDs.

Exit 0 means graph/receipt and syntax scans were complete, not that references
were resolved. Exit 1 preserves a report for incomplete inputs or scan/parse
errors. Exit 2 indicates invalid invocation or an output that cannot safely be
written. Malformed graph records/receipts are retained as diagnostics where the
rest of the scan can proceed. No test files or suites are needed for inline
library probes and repeated CLI output comparisons.
