# Grid of one: walkthrough (U125 integration acceptance)

One laptop, one temp root, two self-rooted node keys, the `adgrid` CLI only. No tests were written
or run; one throwaway driver script under `/tmp` ran the commands below and was deleted.
Interpreter 3.14, `PYTHONPATH=src`, `ADGRID_ROOT=<root>` a fresh temp dir. Output is `--json`, abridged.

## Commands and outputs

```
$ adgrid describe
task_kinds [hash-object, python-canary, subprocess-verb]  canaries [analyzer, browser, parity, python, toolchain]
verifiers [hash-lookup, parity, recompute]  transports [https, local, peer]  lanes []   (+ object/log/head stores, signers, appliers, providers)

$ adgrid objects put <root>/sample.txt          # 1200 bytes, streamed through put_path
ref sha256:1d00ff5781fffc0ea582444efa233434a3682542f0b3a7c9265404c6a5f9fdab

$ adgrid publish hash-object --snapshot sha256:1d00ff57…
planned 1  published 1  existing 0  cached 0   partitions {hash-object: {head 1, seqs [1]}}
basis_hash 587a4b71511ee2f27a61a2eec006731209027c091a65d2d057bf733818d755f1   (builtin_basis: kind + version)
task_id    69eed5538956d73d4951121f049a60e2dcea012c0adcfabb3eedd9452ddd7897
$ adgrid publish hash-object --snapshot sha256:1d00ff57…      # idempotent
planned 1  published 0  existing 1  cached 0

$ adgrid work --once --max-wall-s 120            # node "node", role donor, key 40067ab3…, capability python (canary)
events [pulled, launched, idle…, collected]  stopped_by collected
launched  {deadline_s 10.0, op run, kind hash-object}              # MICRO class, subprocess sandbox, kill deadline owned by the worker
collected {status ok, result_ref sha256:97941fe3dc906ac143391f81be2d0a552ca7171d33d21e108407d3ed1fd9bdb7}
flush     {records 3, named 1, objects 0, failed [], remaining 0}  # INTENT hold, RESULT, INTENT release + results/<task>/<key>

$ adgrid verify --once --max-wall-s 120          # node "verifier", role operator, key 000ec27c…, independent (disjoint lineage)
pulled    {awaiting_verification 1, ready 1, eligible 1}
launched  {deadline_s 10.0, op method}                              # method = the kind's verify_method: recompute
verified  {method recompute, producer_key 40067ab3…, result_ref sha256:97941fe3…}
flush     {records 3, named 1, remaining 0}                         # INTENT hold, INTENT release, VERIFIED + verifications/<task>/<key>

$ adgrid log tail hash-object --limit 50          # one hash chain, seq dense, prev = digest of seq-1
seq 1 task      signer null            seq 5 intent    signer 000ec27c…
seq 2 intent    signer 40067ab3…       seq 6 intent    signer 000ec27c…
seq 3 result    signer 40067ab3…       seq 7 verified  signer 000ec27c…
seq 4 intent    signer 40067ab3…

$ adgrid view materialize <root>/view.sqlite
partitions {hash-object: {applied 7, task_rows 1, verified_rows 1, events [], state ""}}  stale []
grid_results: (69eed553…, hash-object, sha256:97941fe3…, {"digest":"sha256:f07bc367099e844a95a9f062e291cfe79b4881f68cff2668d20e96cc3a78c394"},
               verified_seq 7, verifier_key 000ec27c…, method recompute, status ok)
grid_view_position: (hash-object, seq 7, basis 587a4b71…, state "")

$ adgrid objects get sha256:f07bc367…             # the child's output, read back from the parent's store
{"algorithm":"sha256","hex":"1d00ff5781fffc0ea582444efa233434a3682542f0b3a7c9265404c6a5f9fdab","size":1200}   == sha256 of sample.txt
```

Second pass (idempotence): `publish` → existing 1; `work --once` and `verify --once` → `idle:nothing-eligible`,
nothing launched; `view materialize --resume` → 0 applied, 0 skipped; the log head stays at seq 7.

Root layout after the run: `objects/{layout.json, objects/<ab>/<hex>, named/{results,verifications}/<task>/<key>}`,
`log/hash-object/records.jsonl`, `heads/hash-object.head`, `nodes/{node,verifier}/{keys, identity.json, outbox, work}`.

## What was proven

- The four slices agree on one root layout, one body contract and one chain writer: a TASK
  published by the operator signer (`null`), RESULT/INTENT/VERIFIED written by node keys through
  the node outbox into `log.outbox.Appender`, every record validated at append time.
- The sandbox child resolves the same object store as the parent (`from_locator`), so the
  produced object exists where the frontier, the verifier and the view look for it.
- Verification is by an independent key: the verifier is a second self-rooted identity
  (`nodes/verifier`, role operator); same-key or shared-lineage proposals are never candidates,
  so recompute by a second key was used rather than a pinned `hash-lookup` object.
- Done is an existence check both ways: the VERIFIED record drives the frontier and the view,
  and `verifications/<task>/<key>` makes `tasks.results.is_done()` true for the cache-hit branch.

## What was not proven

- Entry points (`agentdecompile_grid.lanes`, `agentdecompile_grid.task_kinds`) are in
  `pyproject.toml` only; the venv's installed metadata predates them, so lanes were exercised
  through `ADGRID_LANES` (describe then lists 14 kinds), not through discovery.
- Only the local transport, the null operator signer and ed25519 node keys ran: no fleet provider,
  HTTPS/S3 adapter, compaction, poison path, live `join`, or offline `Keyring` verification of node-signed records.

## What did not work at first and what changed

- `publish` read `results/<task_id>` (a directory on disk) and hand-signed records; it now uses
  `log.frontier.derive` for existing/done and `tasks.results.is_done` for cache hits, appending
  through `Appender`. The builtin kinds had no planner; `hash-object`/`python-canary` got `plan()`.
- `work`/`verify` called loop constructors that do not exist; they now build the loops the way
  `worker.agent.build_loops` does, with a `run_once` driver, a per-node identity under
  `nodes/<name>` (canary-proven capabilities) and `verify` defaulting to a second identity.
- INTENT bodies lacked the `issued_seq` fence and used a float `ttl_s`; POISON lacked
  `reason`/`evidence`; `Appender.write_batch`/`draft_for` seal every worker intent as a fresh issue.
- `transport.local.from_root` nested `log/log` and `heads/heads`; the object store root is
  `<root>/objects` everywhere (config `paths.objects`), the log and heads adapters own their subdirs.

## Addendum (2026-09-28): the trust config this walkthrough now needs

Line 77 above named "offline `Keyring` verification of node-signed records" as unproven. It
landed afterward (`authorize_record` enforcement on every reader: `log/frontier.py`,
`worker/records.py`, `view/applier.py`). Re-running the sequence above verbatim on a fresh root
now reproduces `ready 0, eligible 0` forever: the laptop-grid default operator signer is `null`
(`cli.py Grid.signer`), but the default `KeyringConfig` (`allow_null=False`,
`trust_local_nodes=False`) refuses every null-signed record by name, so the published TASK is
folded past as `unknown-signer` and never reaches the frontier. `worker/loop.py`'s `pulled` event
now names this directly (`untrusted` / `untrusted_sample`) instead of leaving `ready 0` to look
like an empty log.

To reproduce the sequence above on one host, export before `publish`/`work`/`verify`/`view`:

```
export ADGRID_KEYRING__ALLOW_NULL=true ADGRID_KEYRING__TRUST_LOCAL_NODES=true
```

This is the documented one-host opt-in (`KeyringConfig.allow_null`/`.trust_local_nodes`
docstrings: "turn it on only for a one-host dev grid"), not a code change: the secure default
(refuse an unattributed or unknown signer) is correct and is left alone. A second, harder
requirement surfaces once two separate roots are involved (two local state directories sharing
one objects/log/heads store, `ADGRID_PATHS__OBJECTS`/`__LOG`/`__HEADS` pointed cross-root): a
joining node's key is not enough to be *offered* an invite either — `verify_invite` requires the
invite's issuer to already be in the joiner's own keyring before the token can be validated at
all, and nothing in `join` distributes that seed. Every producing identity (including a node
trusting its own previously-written records on a later `view materialize`) needs an explicit
`keys/trusted/<name>.json` entry from whoever operates that reader. See
`docs/plans/2026-09-28-grid-multi-node-gaps.md` for the full two-root trace this was checked
against.
