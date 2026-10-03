# Task11.6c — owned native removal source report

Date: 2026-10-03. **READY_TO_COMMIT**, subject to independent source review. This is authored source, not a successful removal, passing regression, installed helper or runtime qualification receipt.

## Exact ownership and authority

Changed only:

- `src/agentdecompile_grid/worker/native_removal.py` — new removal-only protocol, runtime binding, descriptor primitive, preparation/run and maintenance transfer.
- `src/agentdecompile_grid/worker/native_removal_entry.py` — new fixed immutable six-descriptor entry.
- `src/agentdecompile_grid/worker/native_capture.py` — narrow quarantine provenance, removal claim/finalization bridge and original job/no-writer acquisition bookkeeping.
- `.superpowers/sdd/2026-09-28-comprehensive-agentdecompile-plan/task-11-native-removal-report.md` — this report.

The independent regression author owns new `tests/test_grid_native_removal.py`, three appended capture bridge tests and `task-11-native-removal-tests-report.md`. This author edited none of those files. Profile/capture entry, existing capture protocol and binding schema, scheduler, loops, configuration, stores, outbox, recovery adapters and all unrelated edits are preserved. No Git operation or subagent was used.

Controller supplied integration baseline `bd979ae3` (superseding the brief's stale `fc9828e1`) and native source predecessor `403c86f8`. Those commit identities were not independently checked with Git. The complete adopted removal contract, appended adoption/corrections, independent contract review, both briefs, predecessor capture contracts/reviews/reports/regression source and actual capture/profile/entry source governed implementation. Historical memory informed only the source-versus-runtime boundary; no memory-derived live fact or serving checkout claim is made. The source-only controller scope excludes live process/API verification and activation.

## Original authority, claims and qualified release

The capture bridge records creation-branch provenance when quarantine is acquired: exact quarantine/lane/allocation/process/slot identities, original FD and root/parent/boot/name snapshot, original writer PID/pidfd/identity object, retained transport list, writer-attempt flag and original admitted job deadline or null. Preparation sets writer-attempt provenance before spawn. Expired never-admitted slots retain null original job deadlines. Successful `OwnedCapture` retirement remains unsupported.

Removal requires the original live quarantine to occupy its lane, exact `OwnedAllocation` rather than an uncertain or successful allocation subtype, unmodified original anchors and provenance, and qualified exit of the original attempted capture writer. A no-writer branch must have recorded that no spawn was attempted. Unknown spawn, missing/lost identity, replaced records, closed anchors and reconstructed dataclasses cannot obtain a claim through normal source acquisition. These are trusted in-process provenance checks, not protection against malicious supervisor Python.

A `RemovalClaim` is private, one use, and bound to exact quarantine plus UInt64 generation. Every prepared/run IPC, cancellation and finalization checks that current claim before effects. It separately retains remover process identity/PID/pidfd without replacing capture-writer provenance. The claim records preparation/spawn failure, unchanged deadline, diagnostics, cancellation and possible partial removal. Replayed/retired claims cannot act on the current generation.

Authenticated COMPLETE remains provisional. A private completion object is minted only after exact binding, matching direct-child zero exit, all three EOFs, bounded drain and the unchanged deadline. `take_disposition` rechecks this object and exchanges it through the capture bridge for an exact private terminal gate. The bridge rechecks the live run/claim/process/identity/deadline before closing original descriptors, releasing capture transport and publishing an internal tombstone. Only that tombstone supports idempotent `request_cleanup(...).state == removed` after lane release. Mutable state strings, closing handles or another claim cannot do so; a later lane occupant is never cleared by an old tombstone read. Completed removal transport and retained retired-attempt transports are disposed of under the qualified terminal result.

## Generation transfer and retained debt

`RemovalDebtHolder` is a one-entry in-memory holder for one exact lane, with no callback, IO, persistence or driver. `transfer_removal_debt` requires quiescence, exact original resources and qualified exit of every attempted writer/remover. It allocates its next permit/history before the acknowledgment transition, then installs the exact recipient, retires the old claim, advances generation once and mints one permit. Capacity, identity, generation, prior-exit or acknowledgment refusal leaves the previous owner untouched. A conservative64-transfer history ceiling refuses further rearm while preserving all existing debt; no history is dropped to make room.

Initial transfer with `expected_claim=None` requires original unclaimed generation zero with no prior claim/preparation/spawn/transfer, authentic capture-failure/expired-slot provenance and qualified writer retirement. It retains the real capture debt and null-or-real original job deadline without inventing an old remover. None cannot bypass any prior attempted/failed claim.

Maintenance preparation consumes the exact holder-bound permit before installation/spawn. Failure consumes the new claim too. Retry requires another acknowledged transfer after qualified exit; pendingIO and unknown spawn never mint a permit. Prior run references become stale immediately. A later confirmed exit never restores removal success. An absent root after an uncertain final rmdir still fails the next attempt's ordinary name-present gate and remains reconciliation debt. No automatic retry, background maintenance, durable replay or successful-capture cleanup is installed.

## Actual descriptor primitive

`remove_owned_tree` is synchronous fixed-child code invoked only after BEGIN. Its view contains inherited parent/root FDs plus parent-bound identities and32-hex allocation ID. It creates no allocation and accepts no user-selected root path. The sole root component is internally derived `capture-` plus that identifier; a temporary O_PATH/no-follow name anchor only corroborates the retained root and never replaces it.

Before mutation it checks parent/root type, owner, permitted modes, device/inode/mount, security-xattr support and exact parent-name association. It rejects missing/replaced/symlink roots and same-device mount crossings. Every descendant is pinned no-follow before type classification; directory enumeration opens dot relative to that pinned directory. Regular files are never opened for content, and symlink targets are neither read nor traversed. Hardlinked regular files/symlinks, special types, special mode bits, security attributes, foreign ownership, unsupported metadata and changing identities refuse.

A complete read-only metadata pass builds a bounded plan, followed by a second matching metadata pass. Limits retain depth24, path512 UTF-8 bytes,16,384 descendants,8MiB plan accounting,256MiB per file and1GiB total ordinary file sizes. Names are capped before retention/sort. Plan nodes use slots and fixed packed metadata instead of retaining nine Python integers per inode; conservative path reservations are supplemented by measured object-size accounting before plan append. Depth-bounded descriptor guards and one final empty check per directory are separate from the two capped enumeration passes. These are source bounds, not measured runtime memory/performance receipts.

Every mutation rechecks original root/name and retained ancestor chain, then re-pins the exact named entry. Only retained checked directories can receive fchmod0555 to0700; parent, files and symlinks never receive permission repair. Expected directory metadata changes only for the remover's own chmod and child removal, with unrelated type/inode/owner/mode/link changes refused. Leaves unlink relative to retained parents; empty directories use relative rmdir. The helper never removes private parent or siblings.

Root completion requires its own successful final rmdir, exact-name ENOENT afterward, the original retained detached root with link count zero, retained parent identity, exact removed count and remaining deadline. Initial/remnant ENOENT is never success. Errors, unsupported detached semantics or timeouts after a syscall preserve uncertainty; no rollback reconstructs deleted files.

## Fixed helper and bounded lifecycle

Removal has its own runtime schema, independent role pins, installation metadata directory and wire schema. Capture's constants, FD0–7 launcher and codec are unchanged. Removal installation validation explicitly authenticates interpreter, removal entry/controller, capture/profile modules and the full immutable source stdlib/lib-dynload inventory. Only `.native-removal/binding.json` and `inventory.json` are excluded metadata and their bytes must match retained owner inputs. The supported layout remains self-contained static ELF64 x86-64, with no host PT_INTERP/dynamic dependency/search/filter fallback, bytecode/zip/pth/venv aliases or mount crossings. A usable static installation is neither provisioned nor qualified here.

The separate six-FD launcher uses high collision-safe duplicates, explicit close actions, fixed interpreter/entry/argv/cwd/environment and no preexec callback. FD0 is read-only null,1/2 distinct nonblocking diagnostic pipes,3 private credential-bearing seqpacket,4 original parent duplicate,5 original root duplicate. The child replaces search paths before fixed private module imports, validates inherited descriptors, parent-death association and exact hard/soft CORE0/NOFILE128/FSIZE0/AS2GiB/CPU20/NPROC32 limits. It reads only fixed installation/proc metadata and tree metadata. It starts no subprocess/thread and executes no donor/checker/capture operation.

Preparation records the single attempt ceiling before any IO: min(entry+20s, supplied unchanged ceiling). It checks writer retirement and root anchors, authenticates installation, records unknown spawn before entering the syscall, binds mandatory pidfd/direct-child PID/start/UID/GID/executable/argv/runtime, and accepts HELLO/READY under that same ceiling. Prepared parking, BEGIN, deletion, report, drain and exit share it; BEGIN performs no hash/read/spawn/wait and never refreshes time. In-job cleanup retains the actual original600s ceiling; maintenance has its separate acknowledged one-use budget and never changes the job outcome.

Canonical bounded removal frames reject unknown/duplicate/missing fields, noncanonical encoding, invalid scalar forms, wrong nonce/sequence/schema/identity, unsolicited rights and truncation. Every delivered right closes before refusal. Every nonempty received frame needs exactly one matching SCM_CREDENTIALS tuple. Child reports cannot create parent authority. Wire reasons exclude local cancellation and capture-only integrity reasons; unexpected primitive errors map to cleanup_incomplete in the fixed entry.

One poll schedules at most16 events,64KiB control/log bytes and5ms cooperative work, using only nonblocking readiness/reads and existing matching P_PIDFD peek/reap logic. Log caps are1MiB per stream/2MiB aggregate. Cancellation invalidates provisional completion immediately, uses retained pidfd TERM/KILL, truncates5s/5s grace to the same deadline, and returns finite pendingIO debt if exit is unconfirmed. No numeric-PID fallback or tree work occurs in polling.

## Coordination, checks and remaining evidence

Production/test authors aligned exact RootView, Timing, OwnerInputs, Claim, Holder/Permit, preparation/run and private provenance interfaces before finalization. Static review strengthened finalization from a mutable success label to a run-bound completion/gate/tombstone; tests reflect the actual modeled run. It also added exact capture/remover identity and transport provenance, one-use generation transfer, history disposal, and removed redundant directory empty checks. The direct primitive intentionally exposes underlying OSError/ProfileRefused to its fixed caller, which maps them to the fixed wire vocabulary; test expectations distinguish that from wire API refusal.

Performed bounded text reads/edits and standard-library AST parsing of the three production modules. Final source sizes at this check: native_capture1229 lines, native_removal1284 lines, native_removal_entry205 lines. AST inspection enumerated direct call names in begin/poll/cancel/transfer; no direct tree/read/spawn operation was present in those methods. This is source inspection only, not an execution-path or performance proof. Independently authored test source and report were read for interface correspondence; no test was executed or collected. No project module or defined API was imported/invoked.

No tests/collection, build/typecheck, DB/query/hash/crypto/fingerprint/compiler/checker work, process/helper/capture/removal or filesystem-fixture execution, API/live/service inspection, provisioning, restart/systemctl, activation, Git or publication occurred. Source-writing scripts used text/AST only. No installed consumer, current serving revision, physical cleanup or runtime acceptance is claimed.

Mandatory later evidence remains real static installation/bootstrap/import closure; domain exclusion and actual FD/credential/pidfd/reap/parent-death/rlimit behavior; supported mount/xattr and detached-root semantics; actual interruption before BEGIN/first chmod/mid-unlink/after-rmdir; and practical cooperative timing under safe conditions. No source check proves hard kernel walltime, instant D-state termination, hostile same-UID containment or atomic compare-and-unlink. Scheduler/debt driver, successful-capture retirement, full native lifecycle/confinement/stage/export/collection/seal/current reader, whole-image C+assembly-floor/max-C and game acceptance remain separate open work.

**READY_TO_COMMIT — source only, independent review required.**

## Independent review correction M1 — diagnostic poll byte debit

The independent source review identified a Minor exception-path accounting defect: `_drain_log` could successfully read diagnostic bytes and then raise for its cumulative stream cap before `poll` subtracted those bytes from its local64KiB budget. With malformed full-size control frames and two already-over-cap diagnostic streams, the existing16-event bound still permitted65,542 payload bytes in one poll. This was source reasoning, not a performed reproduction.

The correction reserves `min(4096, bytes_left)` before calling `_drain_log`. A successful read followed by cumulative-cap refusal therefore cannot skip the local debit. The reservation also remains conservatively charged on EOF, short reads or BlockingIOError. No drain signature, cumulative log accounting, exception reason, cancellation timing,16-event/5ms bound, descriptor ownership or lane-release branch changed.

This correction edited only `native_removal.py` and this report. The producer inspected the independent review and exact source hunk, compared the before/after text using standard-library unified diff, parsed the resulting1,288-line removal module with `ast.parse`, and checked for trailing whitespace. No project imports, defined production/test APIs, tests/collection, builds, process/runtime/filesystem fixtures, hash/crypto, live API/service operations or Git commands ran. The separately assigned regression author owns the paired pressure/overflow test and its report.

**READY_TO_COMMIT — M1 source correction complete; independent re-review and all real qualification remain separate.**
