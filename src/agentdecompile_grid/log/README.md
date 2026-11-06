# agentdecompile_grid.log — records, heads, frontier, intents, checkpoints

## Partition naming
- Key = 1–8 components joined by `/`, each `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`; maps reversibly to a directory and cannot escape the root.
- Hot base partitions split by task-id prefix: `sub_partition(base, task_id, width)` = `base/<width hex chars>`. The head key *is* the partition name; `derive` reads a base as the family `base` + `base/*`.
- `TaskSpec.partition_key` (the kind name by default) must satisfy the component rule.

## Record types and bodies
- `TASK` = `TaskSpec.to_record()`; `task_id` must be the digest of the content.
- `INTENT` = `{task_id, key_id, ttl_s, issued_seq, issued_at}`; `ttl_s == 0` releases.
- `RESULT` = `{task_id, result_ref, producer_key, status}`; `VERIFIED`/`REFUTED` = `verification_to_body(Verification)`.
- `POISON` = `{task_id, reason, evidence}`; `CHECKPOINT` = `{through_seq, through_digest, summary_ref}`; `NOTE` = anything, never load-bearing.
- Validators are a registry (`BODY_VALIDATORS`). `key_id` / `producer_key` / `verifier_key` must equal `signer_key`.

## Chain rules
- `seq` is dense from 1 per partition; `prev` = digest of `seq - 1` (`""` for seq 1); digest and signature cover the canonical unsigned JSON.
- A batch is one contiguous chained run for one partition, sealed against a known head and landed atomically; a lost race is re-sealed, never patched.
- `verify_chain(records, head=, verifier=)` walks any run offline; `LocalFileLog.verify_chain(partition)` scans from the stored origin. Schema version is checked on decode.

## CAS rules
- `HeadStore.get` of an absent head is `(0, "")`; `cas` succeeds only on an exact match.
- `LocalFileLog` orders by its file tail: a non-chaining batch is refused with `ChainConflict` under an exclusive lock; `publish_head` then moves the head store forward, monotonic only; `HeadDiverged` names a fork.
- S3/HTTP adapters (declared) order by the head CAS: records are written by digest, the CAS makes them canonical, the seq index is written after. `rebuild_heads` recomputes heads by chain scan.
- Retries: full-jitter backoff (100 ms base, 5 s cap, seeded, 128 attempts then `AppendGaveUp` by name; `max_attempts: null` opts into forever); the outbox rotates to another partition after 8 consecutive conflicts (`HotHead`).

## Frontier rules — `derive(log, objects, now, *, proposal_cap, kinds, partitions, checkpoints, policy, keyring)`
- Pure (no clock reads); every list sorted by `(kind, task_id)`; identical on two nodes given the same records, objects, `now` and keyring.
- Every record passes `signing.authorize_record(record, keyring)` before it is folded: its signer is in the keyring, the signature verifies, and a TASK or CHECKPOINT is signed by an operator key. A refused record is not folded, the fold still moves past it, and `untrusted` names it as `(partition, seq, reason)`. No keyring means an empty one: everything is refused.
- `done` = has VERIFIED; `poisoned` = has POISON and no VERIFIED.
- `awaiting_verification` = ≥ 1 `ok` proposal whose object exists and is neither verified nor refuted; dangling refs never count.
- `ready` = published, not done/poisoned, fewer than `proposal_cap` pending proposals, not deterministically refused, no live INTENT at `now`, inputs present.
- `offer_order` lists every `verify` before any `run`. `FrontierPolicy(offer_while_pending=False)` is the stricter design-§2.6 variant.

## Intent rules
- Fence = `issued_seq` = the issuing record's own seq. Holder = highest fence; an equal fence from the same key renews or releases; a lower fence is stale; an equal fence from another key is ignored.
- Live iff `ttl_s > 0` and `issued_at + ttl_s > now`. `renew_intent` / `drop_intent` raise `IntentFenced` by name when a newer holder exists.

## Checkpoint rules
- `CheckpointSummary` = folded `PartitionState` through `through_seq` + `through_digest`, compacted: open tasks whole, done/poisoned tasks as one row (id, kind, verified refs, poison); no timestamp, no writer identity, so two nodes write the same object and its size is bounded by open work, not record count.
- Readers start at `latest_checkpoint`, check the tail's first `prev` equals `through_digest`, fold the tail. A pruned partition without a checkpoint raises `PrefixPruned`.
- `compact` never deletes. `prune(log, objects, partition, RetentionPolicy)` is the separate verb and refuses to drop anything no checkpoint covers.
- `LocalFileLog.read(since_seq)` rescans the stored file from its first line, so a checkpoint saves fold work, not read I/O; `prune` is what bounds the file.

## Acceptance tests (named in module docstrings; written in the verification phase)
U122 (a)–(e), U123, records-validators, records-identity, records-schema, local-atomic-batch, local-torn-tail, local-prune, heads-cas, heads-fork, backoff-deterministic, backoff-rotation, outbox-rotation, outbox-batch, outbox-seeded, frontier-cap, frontier-order, frontier-intent, intents-fence, intents-renew, intents-drop, intents-body, compaction-idempotent, compaction-tail-chains, compaction-prune-guard, signing-roundtrip, signing-null-policy, signing-hmac-labels, signing-ed25519-declared, s3-declared, http-declared.

## GridConfig fields read here (`CONFIG_FIELDS`)
`log.{adapter,root,torn_tail,fsync,verify,s3.*,http.*}`, `heads.{adapter,root,fsync,s3.*,http.*}`, `signing.{adapter,label,key_dir,secret_env,secret_file}`, `keyring.{allow_null,key_dir,trust_local_nodes}`, `frontier.{proposal_cap,offer_while_pending,reoffer_refused,require_inputs,require_result_object}`, `outbox.{max_batch,flush_interval_s}`, `backoff.{base_s,cap_s,multiplier,rotate_after,max_attempts,jitter}`, `intents.ttl_s`, `partitions.prefix_width.{default,<lane>}`, `compaction.{max_lag_records,retention.policy,retention.keep_checkpoints}`.
