# Task11.6c — scoped M1 correction review

Date: 2026-10-03. **READY_FOR_CONTROLLER. M1: ADDRESSED. Scoped specification/quality: PASS. New findings: none.** No outstanding finding remains from the prior native-removal source review. This is one source-only correction review, not test execution or runtime qualification.

## Reviewed boundary

Inspected only the diagnostic-budget correction in `src/agentdecompile_grid/worker/native_removal.py:1177–1186`, surrounding poll byte/event/time guards and cancellation interaction, and the newly authored paired regression at `tests/test_grid_native_removal.py:988–1029`. The existing adjacent pressure/overflow specifications and the producer's M1 correction note supply context. Broader removal ownership, traversal, installation and protocol review was not reopened.

## Why M1 is addressed

The diagnostic branch now determines `diagnostic_cap = min(4096, bytes_left)` and subtracts that reservation **before** calling `_drain_log`. A successful read followed by cumulative-cap refusal therefore cannot skip the per-poll debit. Short reads, EOF and `BlockingIOError` also retain the conservative reservation. This can end a poll earlier, but cannot widen its read allowance or change terminal qualification.

Every scheduled control read still reserves4,097 bytes. The event guard requires more than4,096 remaining, so that reservation fits. Every diagnostic read requests no more than its already-subtracted reservation. Neither exception handler refunds it. Consequently, requested control/log payload bytes cannot exceed the initial65,536-byte budget even if cumulative diagnostic validation raises after every read. The16-event and5ms cooperative guards remain in place.

For the exact former M1 sequence—control, stdout, stderr repeatedly—the fixed source charges `4,097 + 4,096 + 4,096 = 12,289` per readiness group. Five groups consume15 events and61,445 bytes, leaving4,091. The existing guard stops before the formerly admitted sixteenth control read. This is a source derivation, not a performed reproduction.

The exception still reaches the same idempotent `request_cancel` branch. The correction changes neither refusal reason selection nor cancellation timestamps, TERM/KILL ceilings, claim/lane ownership, descriptor release or completion conditions. It adds no blocking operation or filesystem work.

## Paired regression assessment

The new parametrized model pairs initially zero diagnostic counters with already-over-cap counters while supplying full-size malformed control datagrams and full-size data on both diagnostic streams. It measures actual discarded log bytes from counter deltas, so the assertion does not depend on `_drain_log` successfully returning. The over-cap case would expose the original skipped-debit schedule; the normal case preserves its control.

Two successive polls assert at most65,536 actual bytes and16 events each, pressure remaining in the queues, both streams visited, unchanged cancellation reason/timestamps/deadline, only the original TERM signal, no closes, and the same quarantine/claim/original anchors. Beginning with an explicit cancellation usefully checks that later malformed frames and log-overflow errors cannot restart or replace cancellation. The test remains an unrun model, not evidence about kernel reads, credentials or helper exit.

No new source regression was identified within this scoped change. The conservative reservation on short/empty/would-block reads is consistent with the scheduled-read ceiling.

## Verification limit

Performed bounded source/text reads and wrote only this report. No source/test edits, Git, tests or collection, project imports, fixture invocation, DB, helper/process/runtime execution, filesystem mutation experiments or live operations occurred. The prior review report is preserved as the historical finding record; this report resolves M1 only. Actual removal, installed helper and runtime acceptance remain open.

**READY_FOR_CONTROLLER — M1 addressed; source adoption remains the controller's decision.**
