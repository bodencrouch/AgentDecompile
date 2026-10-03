### Spec Compliance

- ❌ Issues found: the independent-key requirement can be bypassed by two supported identifiers for the same Ed25519 public key (`src/agentdecompile_recovery/corpus/current_admission.py:273`, `:282`, `:298`, `:558`). The remaining reviewed P3.1 structure matches the scoped contract; P3.2 and final source/corpus acceptance remain open.
- ⚠️ Cannot verify execution from this diff: actual-crypto regressions are authored but unrun, as explicitly required for this dispatch. This review does not establish a passing positive path, owner provisioning, installed-consumer behavior, runtime closure or live acceptance (`tests/test_current_admission.py:139`; implementation report:59).

### Strengths

- Authority comes from the effective owner pin and bounded selected public files, with exact snapshot schema, current revocations and explicit policy sets; development trust is refused (`src/agentdecompile_recovery/corpus/current_admission.py:241-341`). Lifecycle metadata is pinned and typed without becoming role/lineage/expiry authority (`:287-299`).
- The reader uses descriptor-relative no-follow opens, byte/count/deadline limits, full genesis linkage, strict decoding and current rereads. It retains CAS bytes only within one invocation (`src/agentdecompile_recovery/corpus/current_admission.py:102-234`, `:358-383`, `:599-600`).
- The selected records use actual signature verification and existing authorization. TASK/result/evidence/raw/input associations are reconstructed, and the complete captured partition is scanned for currently trusted refutations (`src/agentdecompile_recovery/corpus/current_admission.py:463-550`, `:553-598`).
- Frozen outputs preserve distinct observation grades and explicitly leave implementation/source acceptance unevaluated; no consumer/provider activation is added (`src/agentdecompile_recovery/corpus/current_admission.py:50-65`, `:605-607`).

### Issues

#### Critical (Must Fix)

- None found within this observation-only source scope.

#### Important (Should Fix)

1. **Reject equivalent public-key material across the two key-ID encodings.** `src/agentdecompile_recovery/corpus/current_admission.py:273-301` deduplicates key IDs and filenames, but accepts the same 32 Ed25519 public bytes through both `add_ed25519_public` and `add_node_public`. These produce different legitimate IDs: `src/agentdecompile_grid/log/signing.py:197-198` uses `ed25519:sha256(public)`, whereas `src/agentdecompile_grid/worker/identity.py:155-157` uses the first 32 hex characters of the digest of `{alg, pub}`. `Keyring.independent` compares only IDs plus declared lineage (`src/agentdecompile_grid/log/signing.py:488-500`), so the call at `current_admission.py:558` treats those two aliases with empty/disjoint lineage as independent. A policy can therefore admit the node alias as producer and raw operator alias as verifier; one private key signs both records, both actual signatures pass, all body IDs match their respective aliases, and the function reaches `authenticated`. Distinct ancestor IDs backed by the same material likewise evade the disjoint-lineage check. This violates the required real independent verifier boundary even though the snapshot is owner pinned. Reject duplicate normalized Ed25519 public material across all selected entries (including ancestor entries), or use canonical cryptographic identities consistently for independence while preserving the required existing authorization call. Add an unrun actual-crypto regression source using the same deterministic seed for the raw and node forms and asserting refusal; also cover ancestor aliases. Do not change generic Keyring/producer/log APIs for this scoped fix.

#### Minor (Nice to Have)

- None.

### Checks and evidence scope

- Read the reviewer prompt, task brief, complete admission contract including lifecycle clarification, implementation report and complete scoped diff for `adf0bbb4d14c7a7721873fa42da6dbfc49f141a2..689f6dd1e8b45d1f4a20e7e48d7dd49cb623108b`. Read the diff in bounded chunks; did not reread changed source files or rerun Git.
- Named risk: hidden identity/authorization checks in unchanged helpers could change tuple findings. Checked `worker/records.py` builders and decoder; `log/records.py` selected body validators and `validate_record`; `log/signing.py` verification, authorization and independence; `core.py` TaskSpec identity/record projection. Existing validation does enforce RESULT producer and VERIFIED/REFUTED verifier body ID equality with the signer.
- Named risk: the reader's native receipt/spec normalization might contradict real P1 emission. Checked `grid_lanes/parity.py` spec validation, normalization and evidence construction, plus `objdiff_verification.py` parser. Its current native diagnostic messages are fixed strings, so the producer's message path scrub does not establish a current mismatch.
- Named risk: dispatch/layout interpretation could reject the supported existing formats. Checked `verify/loop.py:_method_for` and `objects/base.py` ref/layout definitions. No additional finding established.
- Named risk: distinct public loader branches could alias cryptographic identities. Checked `log/signing.py:197-198,356-381,488-500` and `worker/identity.py:155-157`; this established Important issue 1 by source reasoning.
- Ran only bounded text reads/searches and a stdlib text-only diff line-number extraction. No tests, collection, builds, typechecking, project imports, signing/key generation, DB, compiler/checker, runtime/process/catalog/service/port operations or publication. Only this review report was written.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The source implements a substantial fail-closed observation boundary and preserves the P3.1 acceptance limits, but distinct identifiers for the same Ed25519 key defeat the required verifier independence. Close that identity gap and add the corresponding regression source before approving this source-only task gate; execution qualification remains separate.
