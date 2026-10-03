# Task11.5 P3.1 current signed observation — implementation report

Date: 2026-10-02. Base supplied by controller: `adf0bbb4d14c7a7721873fa42da6dbfc49f141a2`.
Status: **READY_TO_COMMIT (source-only; execution unqualified).**

## Owned paths

- `src/agentdecompile_recovery/corpus/current_admission.py` (new)
- `src/agentdecompile_grid/config.py` (narrow AdmissionConfig, GridConfig field, validation and generated field documentation)
- `tests/test_current_admission.py` (new regression source)
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-11-admission-report.md` (this report)

No existing config regression file needed editing. No staging, commits, public PRs, dashboard/provider changes, P2 edits or deletion-registry edits were performed by this worker.

## Implemented boundary

`load_current_admission(cfg)` and `authenticate_native_observation(cfg, selection)` implement the adopted `current-signed-observation-v1` read predicate. The selection contains only partition, TASK/RESULT/VERIFIED digests and result ref. It cannot supply trust roots, methods, key metadata, a policy pin, revocations or a callback.

The owner-only configuration addition is `AdmissionConfig(snapshot_path, snapshot_sha256, policy_id, generation)`, frozen and entirely unset by default (generation uses -1 as its unset sentinel). Existing dataclass mapping/TOML/environment/describe machinery discovers the section. Validation requires all fields together when configured. The reader also requires an explicit public trust directory and owner-selected root. No default admission pin, public file, private key or actual owner config was created.

The public snapshot uses the adopted exact schema. Concrete member spellings are `filename`, `sha256`, `key_id`, `algorithm`, `role`, `lineage` for selected public keys; `task_operator_keys`, `producer_keys`, `verifier_keys` for observation key sets; and `scope_id`, `generation`, `snapshot_ref` for a nonnull corpus scope. Scope is only a declared scope; it is not a corpus/source association. All observation entries require explicit nonempty basis and key sets, native checker identity, supported version/method/profile, complete explicitly present revocations, disjoint lineage and no execution profile declarations.

The implementation constructs a fresh public-only `Keyring`, checks selected Ed25519 signatures over existing `unsigned_bytes`, invokes existing `refusal_reason` authorization, checks current revocations including every ancestor, and calls `Keyring.independent`. Selected signatures and evidence are authenticated before a policy exclusion returns stale. Missing historical public material returns unavailable rather than claiming authentication. Null/HMAC/hash-token/development/local-node trust paths are absent.

It captures a complete bounded partition from genesis, validates strict outer JSON/schema/types and existing record invariants, verifies predecessor linkage, selects exactly the ordered causal tuple, and requires task/result/basis/partition/producer/verifier associations. Duplicate selected statements refuse. Every relevant current trusted REFUTED record in the entire captured partition is considered; a trusted contradiction cannot be erased by selecting a positive record. Unrelated retired signers need no current key, but their records must remain structurally valid in the chain.

Signed RESULT outputs must equal the actual canonical, untagged worker TaskResult object. Inline and referenced signed evidence both work; both/neither/extra fields refuse. The reader authenticates every named proposed/recomputed receipt and raw output, plus both task input byte strings, from actual CAS bytes. Receipt identity, sides, symbol, checker, basis, grade, status, exit code and differences must bind exactly. It uses the existing pure native report parser to reconstruct the existing receipt normalization from each raw output; it never executes a checker and does not strengthen the legacy parser into a P2 coverage predicate. Proposed/recomputed receipts must be byte-identical, while match/mismatch/error remain distinct authentic observations.

Success returns frozen results with signed envelope bytes, task/result/evidence bytes, exact selection and consumed refs, admission/observation identities, and grade. Implementation source closure, implementation runtime closure and source acceptance are all `not_evaluated`. No accepted flag, verified-function count or reusable process capability is returned.

## Bounds and currentness

A single cooperative monotonic 10-second deadline covers the operation. Caps are 256 KiB snapshot; 16 KiB public files; 16 MiB/4096-record log; 128 KiB log line; 64 KiB selected TASK/RESULT envelope and result object; 1 MiB receipts/evidence; 4 MiB raw reports; 64 MiB each input; 160 MiB total distinct CAS byte reads; and 16 distinct CAS refs. Reads use 64-KiB chunks and limit+1 detection. Local SHA-256 CAS layout/schema/shard configuration must agree; the supported immutable configuration uses `write_once_strategy=link`.

Traversal starts at a no-follow root descriptor and opens every directory/file component descriptor-relatively, including configured root ancestry. Only read flags are used. Symlinks, nonregular files, traversal/control-character names and unsupported transports/layouts refuse. There are no store get/put calls, named-pointer lookups, quarantine/touch/repair/replay/DB operations or network fallback.

Authority files and the complete log are reread and hashed before success; the captured effective config is compared again. CAS bytes are retained immutably for this single operation, and their file identities are rechecked through no-follow descriptors. Persistent CAS identity changes trigger retained-byte reauthentication and an unavailable result, never a cached positive. Stable CAS inputs are not reread a second time, preserving the 160 MiB total CAS read ceiling even for two 64 MiB inputs. No positive authentication cache exists.

A future route must reload effective owner configuration before every invocation, or provide a coherent already reloaded revision. This source-only function cannot discover that an external long-lived GridConfig was never refreshed. Kernel-stalled reads exceed the guarantee of a cooperative deadline. Owner-controlled rollback and withheld remote revocations are not independently detectable; no monotonic remote authority is invented.

## Existing record compatibility decision

The signed tuple needed no schema change. Source references are `worker/records.py:105` (`result_body`), `worker/records.py:121` (`verification_body`), `core.py:116` (`TaskSpec.to_record`) and `core.py:163` (`TaskResult.to_record`). The existing collection path can legitimately put evidence inline or behind `evidence_ref`; no unsigned named verdict is used.

One concrete public-key schema detail was escalated to the controller before support was added. `src/agentdecompile_grid/worker/identity.py:174` emits `created_at`, `expires_at` and `previous_key_ids` alongside algorithm/key_id/public. `src/agentdecompile_grid/log/signing.py:395` accepts the public trust fields and deliberately does not enforce lifecycle expiry or infer lineage from previous IDs. The controller explicitly clarified that existing lifecycle fields may be strictly typed, bounded, pinned metadata, while explicit role/lineage and current owner policy remain authoritative. The reader therefore supports those optional existing metadata fields (finite timestamps and unique string prior IDs), hashes their complete file bytes, and does not invent expiry authorization/renewal. Missing explicit role/lineage still refuses. A regression source covers expired lifecycle metadata and a producer ID placed in previous IDs without allowing either to supply trust or ancestry.

The reader imports the existing actual primitives rather than a local truthiness substitute: `log/signing.py:488` (disjoint trusted lineage), `log/signing.py:505` (public signature verification), `log/signing.py:554` (signature plus role authorization), `verify/policy.py:RevocationList.is_revoked`, `objects/base.py:Layout.relpath`, and existing log validators/chain verification. Native receipt semantics follow `grid_lanes/parity.py:513` and `:545`; emitted P1 evidence follows `:720`. Scheduling dispatch follows `verify/loop.py:180`: the supported dispatch is `kind`, while the signed emitted method must be `parity-binding-v1`.

## Regression source and self-review

Authored 29 focused test functions with parameterized cases. The synthetic fixture uses actual existing Ed25519 operator/node signers, existing canonical TASK/RESULT/VERIFIED builders, two explicit disjoint ancestor lineages, native report bytes, CAS objects and a public owner-pin fixture. Signing seeds are deterministic test-only source literals; this worker did not execute them or generate any keys.

Cases cover all three grades and both evidence forms, immutable result fields, all selected revocation dimensions including ancestors, missing old keys, forged signatures despite revocation, same key/shared ancestry/body lineage claims, method/checker/basis/role changes, trusted and untrusted negatives, retired unrelated records, duplicate tuples, unsupported tagged result encoding, changed referenced evidence, raw/receipt substitution, generation identity changes, missing pins, unsigned named revocations, malformed JSON and bool sequence, unsafe paths/symlinks, torn/pruned history, changed authority/CAS files, deadline and size limits, optional config roundtrip/validation and no write/mtime changes during successful reads.

Self-review corrected: legitimate internal ObjectRef subclasses must retain exact ref validation; original NodeKey lifecycle metadata must not be mistaken for an unsupported invented record; existing GridError refusals must be returned rather than escape; selected task/result envelope limits must apply before expensive interpretation; partition validation must precede opening the selected path; and unchanged retained CAS objects must not be read twice past the total byte budget. The reader stays one focused module, but the schema/association/bounded-I/O surface is substantial and merits independent source review before commit.

## Checks actually performed and remaining qualification

Performed only source inspection, read-only Git diff checks, and stdlib AST parsing of the three owned Python files. AST syntax passed. The tracked config diff passed `git diff --check`; new source whitespace was also checked with no-index diff checks. Tests were counted from AST, not collected.

**Not performed:** tests or collection, project imports, typechecking, builds, proof scripts, actual signing/key generation, actual owner configuration loading/provisioning, database reads/creation, compiler/checker/Ghidra execution, process/service/catalog operations, hot reload, server activation, live installed-consumer validation or publication. No live claim follows from the authored regressions.

P3.2 measured implementation/runtime closure, compile closure, exact source/candidate/corpus join, current corpus read validation, final dashboard connection, fresh whole-image acceptance and runtime readiness remain open. Existing dashboard provider state remains disconnected and verified counts remain null because no consumer was changed.

## Task11.5 fix round1 — canonical Ed25519 independence

Date: 2026-10-02. Fix base supplied by controller: `689f6dd1e8b45d1f4a20e7e48d7dd49cb623108b`.
Status: **READY_TO_COMMIT (source-only; regression execution unqualified).**

Read the exact fix brief, original task brief, adopted admission contract, durable implementation report, and review Important issue 1 in full. Read the SDD implementer prompt; this dispatch's explicit source-only/no-commit constraints govern its generic execution and commit recipes.

### Exact owned paths and change

- `src/agentdecompile_recovery/corpus/current_admission.py`
- `tests/test_current_admission.py`
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-11-admission-report.md` (appended section only)

The pinned public-key loader now maintains an invocation-local set of exact normalized Ed25519 public bytes across **every** selected trust entry. Raw operator files supply their existing 32-byte material after the existing raw-key validity guard. Node records supply `bytes.fromhex` only after the existing exact lowercase 64-character hex/type/metadata guards. Existing Keyring population and key-ID validation remain in place. Repeated material returns `failed:duplicate_public_key_material` before the policy can grant an admission identity or authenticate any observation. No ID, role, lineage, JSON encoding, filename or insertion order can make identical public material independent. Ancestors are subject to the same check even when leaf producer/verifier keys differ.

Existing `Keyring` signature verification, `refusal_reason` role authorization and `Keyring.independent` calls remain intact. No generic Keyring change, trust callback, ID rewrite, producer/log/record/public-result interface change, source/runtime closure, config provisioning or consumer connection was added. Authority still comes from the explicit owner pin; role and lineage metadata cannot confer independence on aliases.

### Authored regression sources (unrun)

Added two actual-crypto regression functions, each parameterized over both selected-public-key insertion orders and inline/referenced evidence (eight authored alias cases total):

- `test_raw_operator_and_node_aliases_cannot_verify_each_other`: one deterministic test seed (`bytes([4]) * 32`) backs the existing node producer and an operator-format verifier. The fixture asserts identical public bytes and distinct valid IDs, adjusts the exact policy/verdict signer associations, and signs the real tuple through existing signers/builders.
- `test_alias_ancestors_cannot_split_distinct_leaf_lineages`: producer/verifier leaf material is explicitly distinct, while raw and node ancestor IDs share the deterministic seed (`bytes([2]) * 32`). The selected public metadata and signed verifier lineage agree with their respective distinct ancestor IDs.

Both functions first author a genuine distinct-key positive read, then require both admission loading and observation reading to refuse the aliased snapshot with the exact reason. Refusal asserts no admission/observation identities. Existing positive regressions for all three grades and both evidence forms are retained. The source file now contains 31 test functions, counted by AST only; no tests were collected or executed and no signing seeds were evaluated by this worker.

### Self-review and source-check evidence

Reviewed the complete owned Python diff. The dedupe runs only after existing validity/identity guards, compares exact public bytes without coercion or ring-private-field inspection, is bounded by the existing 64-entry public-key cap, and rejects globally selected ancestor aliases before lineage validation can admit them. Both format orders encounter the same byte set. The distinct-key fixture continues through the same existing authorization/independence path by source reasoning. Each regression rebuilds the actual signed log tuple after changing relevant signer/lineage metadata; referenced evidence remains in its original signed storage form. Unselected old fixture public files are irrelevant because the loader reads only selected pinned files.

Checks performed:

- `git diff -- src/agentdecompile_recovery/corpus/current_admission.py tests/test_current_admission.py`: read the complete scoped source diff.
- `git diff --check -- src/agentdecompile_recovery/corpus/current_admission.py tests/test_current_admission.py`: exit 0, no output.
- `python -` with stdlib `ast`/`pathlib` only, reading the two owned Python files and calling `ast.parse`: both reported `AST syntax PASS`; test-function count was 31. No project import or fixture execution occurred.
- Final report/source whitespace check uses `git diff --check` scoped to all three owned paths.

**Not performed:** tests/collection/builds/typechecks/proof scripts/project imports, actual crypto signing or key generation, DB reads/creation, owner key/config/revocation operations, runtime/process/catalog/checker/compiler/Ghidra/service/systemctl/restart/port operations, hot reload/consumer activation, staging/commits or publication. Other agents' tracked edits were preserved.

The fix closes the reviewed alias bypass at the source gate. Actual Ed25519 regression execution, installed-consumer behavior and live qualification remain unverified. P3.2 implementation/runtime and compile closure, exact source/corpus join, dashboard connection, whole-image acceptance and runtime readiness remain open.
