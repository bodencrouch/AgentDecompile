# Delivery status and prioritized closeout

Status date: 2026-09-27. This is the implementation/acceptance ledger for the
[September 18–21 design scope](plans/2026-09-27-weekend-design-scope.md), the later
[September 22 contract package](plans/2026-09-22-design-package.md) and
[autonomous capability roadmap](plans/2026-09-22-autonomous-capability-product-roadmap.md).
The [current progress and live track](plans/2026-09-27-implementation-progress-and-live-track.md)
orders their remaining work. [FRONTEND_INTENT.md](FRONTEND_INTENT.md), the
[workstation spec](dashboard-design/2026-09-20-unified-workstation-spec.md), and
its [implementation plan](plans/2026-09-20-unified-reversing-workstation.md)
remain the frontend requirements and implementation references within that program.
Requirements being documented or source code being present is not delivery.

## Current continuation receipt — 2026-10-10

Outside-writer boundary audit: current account UID1000 has subordinate UID/GID
range524288:65536 and newuidmap/newgidmap; SELinux is enforcing but the session
is unconfined_t, deny_ptrace0. None of the specifically checked dedicated worker
accounts (agentdecompile, agentdecompile-worker, adcompile, recovery-worker)
exists. These tools are not proof of an effective worker boundary. Independent
review of Linux commoncap.c cap_capable_helper confirms that the parent-namespace
UID owning a rootless user namespace can retain capabilities over descendants;
ptrace.c consults that capability. A mapped subuid alone therefore does not
qualify exclusion of other UID1000 writers. No namespaces, accounts, MAC rules,
sudo policy or services were created/changed. Isolated successor admission needs
a separately controlled initial-namespace worker identity or independently
validated MAC boundary, plus its exact launch/snapshot/lifecycle contract.
This host-level expansion requires explicit direction; current verifier remains
unadmitted and full-image recovery remains unproven.
Primary code reviewed:
https://github.com/torvalds/linux/blob/master/security/commoncap.c
https://github.com/torvalds/linux/blob/master/kernel/ptrace.c

Fresh-output producer integrity repair is source-complete at direct verifier
SHA477172fd73543d72464727fe77c13df7466e90b96c15fd9db8a7cd27b41ac74a.
The verifier now requires an existing parent, exclusively creates the fresh child
relative to a held parent descriptor, captures physical parent/child identity,
and retains descriptors through build/publication/receipt lifetime. Identity
checks precede compilation, diagnostic writes, native publication and receipt
writing. Existing/dangling children are refused without cleanup; replacement
detected at a checkpoint yields stdout diagnostics rather than writing to an
unqualified tree. Derived candidate/diagnostic paths now use the captured path,
fixing a reviewer-found '..'/symlink spelling discrepancy. Mocked OS checks,
AST/signature/closure checks and independent scoped review passed. This is not
atomic unmanaged-writer exclusion or admission authority. Module has not run
in a verifier process; no fresh compiler receipt was produced.
Live8080 remains3639986/zero restarts;19bf0594c7cb remains historical interrupted
and never-started. Its proposed output is still absent; existing parent is
device41/inode146501034. Historical compile/local-recovery overlap holds remain.
Read-only isolation audit found bwrap installed, but no qualified recovery
sandbox contract. An enforced private successor effect set could narrow new
resource intersections while retaining all old assessments. Ordinary same-UID
private directories/read-only binds alone do not exclude outside writers;
dedicated ownership/MAC or an explicitly qualified cooperative writer boundary
is still required. No sandbox was launched or namespace availability tested.
Any such future route must bind snapshots, policy/attempt/argv and actual
namespace/mount/descriptor identities, remain fail-closed without isolation,
and observe complete namespace lifecycle. This is an unimplemented admission
option, not a clearance receipt or permission to dispatch current verification.

Post-drain admission implementation advanced without another restart:
jobs SHA340ee0b1dbdf07936a82244acc5d85446cbfa86c88f754a6917a02c682e8415a
now scopes direct-verifier diagnostics to retained explicit absolute toolkit,
prefix and work-directory operands. Missing/malformed operands yield unknown;
current defaults cannot replace them. Twelve extracted-function memory-only
checks and independent scoped review passed. Catalog report4ee9e4594e23 confirms
the exact successor output scope and K1 daemon idle, but remains ineligible for
historical release. Compiler/output process coverage remains unqualified.

compile_link SHA712c2d0c25f1cbaa733055e0636271bef15dbb3c551127d46396fdd1251ef7f0
holds the canonical adapter's cooperative prefix lease across output mutation,
all translation units, worker shutdown and linking. A live/unknown exact-prefix
daemon refuses dispatch before this function mutates output. Completion records
a bounded daemon observation under that lease; it does not resolve historical
or unmanaged writers. Foreign compiler paths are unchanged, including avoiding
Wine-specific imports. Memory-only fake cases, signature/closure checks and
independent source review passed. Both revisions are applied on8080 PID3639986
with zero restarts. No compiler/linker job has run: successor output qualification
and authority-bearing scoped admission are still missing. These changes are
implementation progress, not fresh matching-C or full-image proof.

User-authorized controlled legacy drain completed: watcher2325 was paused before
further launches; six verified K1 shard-loop parents and five queued generator
waiters received PID-boundTERM. Active generator3603057 was left untouched and
finished naturally. Only watcher/sleep remained in the legacy service cgroup
before its owner-manager D-Bus StopUnit; service nowinactive/MainPID0, and no
shard/generation locks remain. No systemctl or force kill was used. Wineserver
2384 belongs to PotPlayer and was explicitly left alone. Actual K1 Wine prefix
wine64_nvme (device41/inode157924635) reportslock_unheld/socketPresentfalse via
the read-only exact-prefix kernel probe. This is scoped daemon-idle evidence,
not historical-owner or all-writer clearance.

Dashboard3286755 was absent before drain. Authorized one-shot restoration reused
the sameNVMe workspace/GPR/runtime-owner flock asPID3639986; Playwright confirms
HTTP200/zero in-process restarts. Request19bf0594c7cb is now an interrupted
historical record, never-started, not a live queued handle; total retained
assessments251. Its missing before-dispatch receipt was not fabricated.
Future direct-verifier requests now issue guarded durable no-dispatch intent
before allocation/freeze persistence, rebound on pending failure/cancellation,
and invalidated durably before any executor. The catalog ownership report now
includes the exact-prefix daemon observation with an explicit non-authorizing
boundary. jobs SHA356c48fe71ab5a8b46ce1f75d00502211d5ce058ad1b572de3cb175000fd2f2f
is live/applied on3639986. No verification was resumed or owner blanket-cleared;
successor-only scoped admission capability/lease consumption remains missing.

Catalog report782168458914 completed as ineligible, not as recovery failure:
missing executionOwner/resourceKeys/complete_dependency_owner_clearance for
19bf0594c7cb. It independently records the K1 daemon as clear, but compiler,
prefix and output process-use domains remain unknown (physical disjointness
unqualified; changing process inventory). No evidence was promoted to permission.
Independent memory-only review passed the future no-dispatch issuer/validator
and dispatch ordering at current jobs SHA356c48fe. Final drain recheck confirms
legacy service inactive/MainPID0; only dashboard3639986 holds its dashboard
owner lock. Verification remains paused pending authority-bearing, resource-
scoped admission; no fresh compiler receipt or matching-C increment exists.
Independent process audit identifies the sole Wine candidate as PotPlayer2384:
its live prefix descriptor is device41/inode178252686, physically distinct
from K1 device41/inode157924635. This resolves that candidate's prefix identity,
not output-writer clearance. The report's output scope is the entire workspace;
successor admission still needs exact-output physical qualification/exclusive
creation and a held whole-attempt lease, not a transient process snapshot.

### Historical observations before the authorized drain

Final admission-blocker audit confirmed19bf0594c7cb still queued, never started,
with155 retained-owner holds and zero running catalog jobs. All155 owners were
retrievable:97 text-permuter,33 preparation,8 workflow-control,7 Ghidra-bulk,
6 reconstruct, and one each source ZIP, byte verifier, direct verifier and
source-parity synthesis. Total incomplete assessments remain250. External
watchdog2325 and wineserver2384 are still alive. Old boot/PID evidence and
interrupted projections are not complete descendant/provider clearance.
The same ownership blocker has persisted across three goal turns despite
compiler/configuration/lease progress. Recovery needs an explicitly authorized
controlled legacy-owner drain and a resource-scoped reconciliation procedure;
no existing generic action can mint the missing clearance evidence. Keep the
queued request and every source/object/diagnostic receipt; do not blanket-clear
reservations or duplicate the job. Full-image proof remains absent.

Owned MSVC compilation and linking now share a nonblocking cooperative physical
Wine-prefix lease. Refusal precedes object deletion/link artifact changes;
matching inherited descriptors propagate through the wrapper, adapter and Wine.
Post-acquisition directory/lock inode checks refuse replacement races before
yield. Descriptor numbers do not enter semantic cache identity. Independent
source review and mocked memory-only checks passed. This coordinates cooperating
direct subprocesses only: Wine daemons, unmanaged writers, historical owners and
post-yield hostile filesystem replacement are not proven excluded or cleared.
Reviewed adapter SHA1eb1b0eb7b13160e50bdf38dc757d959ae7a655ebe3f376545401ce4603a3941;
compile_link SHA2a1a2adc73f70638185e139dedcbff814c201d47a8ea543564c362710d06c2b0.
No compiler/linker execution or filesystem test was performed.

The direct verifier also captures explicit compiler/toolkit/prefix/output paths
as admission resource claims. Bare PATH command names and absent operands do not
invent physical identities/defaults. Existing local-clearance authority is not
expanded. A dynamic captured-claim guard protects retained queued frames from
hot-reloaded contracts; a final frozen-key guard precedes reservation/dispatch.
Independent fake-only checks passed.8080 PID3286755 hot-applied jobs SHA
e4431dc92806aeb289562085462c687f5212f91151ea2a339eae64be3b4f6c40,
without restarting. Never-started request1d96a7e1e2fe was cancelled through8080
and replaced once by19bf0594c7cb to capture the new contract. Historical holds
were not released. Fresh verification remains queued and recovery proof missing.

Latest six-hour dashboard-history audit,13:37:26–19:37:26UTC, inspected1594
retained jobs through8080/Playwright. Three jobs were created in that window:
one native-object replay completed in3.338seconds, one resource reconciliation
report failed, and fresh direct verification1d96a7e1e2fe was submitted at19:36UTC
and remains queued. No fresh compilation or accepted matching-C increment was
demonstrated in this window. The earlier08:56–14:56UTC audit below is a different
window, not the latest six hours. Source implementation is not recovery throughput.

The new single-candidate verification has154 retained-owner holds
(154 local-recovery domains and9 compile domains), zero running jobs and no
resource-pressure hold. Independent audits found an implementation gap:
incomplete legacy ownership can be retained indefinitely but generic
resource-reconcile has no authority-bearing transition for it. Compiler/prefix
identities are not yet process-shared leased resources. Removing the domain
holds or declaring clearance from absent processes would not be a safe repair.
Next critical implementation is concrete producer resource leases and bounded
domain-scoped reconciliation; legacy external owner lifetimes still require
positive evidence. No owner was cleared or external watchdog signalled.

Independent review completed for source-candidate selection and explicit
compiler options without a blocking finding. A follow-up repair also passes the
captured environment into both MSVC and generic linking, preserving existing
linker policies and explicitVCROOT/WINEPREFIX. Source SHA for compile_link.py
is now1c9d29b2befea576819700252d44c97970a55352c162df1bf0c31aee703743fb.
Inline AST/environment checks and independent review passed.8080 health
reported compile_link reload rejected for callable signature changes, with
applied SHA03f862c8d1710f5672ccef5887f0eefa7e6e77377e76c40d9212216edb15a584.
This is source-only for the serving interpreter; a fresh subprocess imports
current source. No linker execution or server restart is claimed.

Fresh direct-build diagnostics now support repeatable source-relative
`candidate` selection through the same8080 catalog and compiler frontdoor.
Explicit selection shares ordinary unit eligibility, rejects traversal,
duplicates and ineligible paths before output creation, and avoids walking the
whole source tree. Default full-tree builds remain unchanged. Receipts record
selected files/count and distinguish subset inventory from full-tree inventory;
neither constitutes recovery proof. Native closure contracts must bind a selected
source rather than an unselected file elsewhere in the tree.

The same route now accepts opt-in `compiler-options` through the existing owned
MSVC adapter validator. Captured child environment, cache identity, actual
compiler invocation and native observation agree; server environment is not
modified. VCROOT/WINEPREFIX use the explicit request. This removes the known
default `/O2 /Gd` versus retained C++ `/O2 /Gd /GX` discrepancy without hardcoding
product-specific flags. Source hashes: compile_link.py
`1cef80e589b90aa23d73db34be3cd3e5111e284ca7eab40358e1c3e05568c0e6`,
verify_direct_full_image.py
`8f90fc16248f01e7eaef4027b98ab33ff907c68341e93ce56982ab0b609c6498`.
The serving CLI hot-applied SHA
`7ce9a941044e96e6b15b918ff0df57e5df5e87829b6738e47362dce85a9b9d86`
on PID3286755 with zero restarts. A catalog dry-run returned200 for the single
CameraStyle candidate, owned adapter, explicit `/GX`, captured Ghidra target and
v2 closure contract. This validates command wiring only; it did not compile or
publish. Independent source review was still pending at this receipt point.

Bounded legacy-owner inspection found watchdog PID2325 still alive, with a
sleep child and no held shardloop locks. Its log recorded all six shard restart
attempts at14:28:14–14:28:24 local; source shows a300-second retry interval.
Latest shard1 launch log reports zero prompts/zero concrete build instances.
This corroborates repeated empty legacy preparation, not active productive
compiler work or clearance of historical claims. The watchdog remains untouched.

Follow-up restoration under the existing user authorization is now live:
PID3286755, started14:22:24 local, canonical NVMe cwd, independent session and
the existing `dashboard-8080.owner.lock`, with no respawn supervisor. Startup
reused32 programs and explicitly selected the external corpus DB/workspace.
Playwright confirmed8080 HTTP200 and the optional native-placement contract in
the action catalog. Supported database selection restored250 incomplete
ownership assessments (including one policy mismatch) and strict hold772e68366608;
no historical owner was cleared or job resumed. Zero jobs were running.
The prior shutdown cause remains unknown; this is availability, not uptime proof.

The first admission status formerly showed zero retained assessments until an
explicit database selection restored them, even with the correct startup DB.
It now performs the existing scoped restoration once, under its lock, before
reporting holds; subsequent snapshots avoid receipt rescans. Inline checks and
independent review passed, including refusal on owner conflicts. PID3286755
hot-applied jobs SHA
`3a4cf8e170565aee7d4cc5d29c1502a8b284207b3c56357a323dcc2ce2d2d6cd`
with zero restarts, including the severe-pressure repair. Fresh compilation,
native image publication and matching-C acceptance remain unverified.

The pre-restoration check superseded older activation receipts: PID2417358
was absent,8080 had no listener and Playwright reported connection refused.
The bounded server log had no shutdown cause. Native closure integration then
had source-only evidence. The follow-up activation above does not supply fresh
recovery proof. External watchdog PID2325 was not signalled.

The CLI's duplicate `main.run_it` callback paths also caused the installed
reloader to reject even an unchanged baseline. Distinct rebaseline/backfill
callback names fix that ambiguity without changing dispatch or exception
semantics. Inline checks reproduced the old rejection, accepted the corrected
baseline and a compatible body edit, and showed AST equality after normalizing
only those names/references. Independent review passed. Latest cli.py SHA
`f254ee4a8becda30899cbba572369496a0695ee85beac9cd508345eeb8d9ca26`
supersedes the integration-only hash below; this is not live reload evidence.

The native COFF selector is now connected to the producer-owned placement,
evaluation and publication path, with optional `native-placement-contract`
collector input. Independent review passed: actual retained regions are
155/21/12/36bytes, sanitized audit serializes, counterfeit capabilities refuse,
ordinary and closure placements share overlap checks, and floor overwrites
withdraw C contribution credit. Target policy is checked before compilation.
Reviewed source hashes: source_contribution.py
`ad9e64f5e2a40ab3cd9676c1d14b31b728e8cd6edff61f91b85fc9cd9027b97d`,
verify_direct_full_image.py
`d245814e05f96cb2eddc19acf750c4043f7a7b60e631cb85a1f9046dee7a0f5b`,
cli.py `3badeb09fab41d8a30ed55c08b408d18d5ba5d297bfd659b18a71cadf523a523`.
Genuine fresh-build capability issuance and end-to-end image publication remain
unverified. Diagnostic exact placement is not original-link or whole-image proof.

Memory-pressure admission now holds expensive compiler/analyzer/matching work
when Linux full-memory PSI averages at least5% over10seconds and swap headroom
is below512MiB, or full PSI reaches20% regardless of free swap. The latter is
a conservative admission threshold, added after observing34.19% full stalls
despite17GiB free swap; it is not a measured optimal throughput setting.
Six inline boundary cases and malformed observations passed without files/jobs.
Pre-restoration jobs source SHA
`0bdf685e63b25ebc1a20857b3cfe3e6d6b394602d1c16532b75121cea917502f`
was source-only and is superseded by the live-applied hash above.
Missing observations remain explicitly unknown; occupied swap
alone is not a hold. Sampling is cached5seconds, and measurement-only changes
do not force durable job writes. The same predicate filters fair-queue eligibility,
so a pressure-held old compile cannot starve cheap reads; control remains usable.
Independent actual-AST checks covered that starvation path and expensive read-only
work. PID2417358 hot-applied jobs SHA
`adbd17fe8952d96315162fde6dea857c7707d5ceca5b013bb417d7f87104ccd2`,
zero restarts. This does not retire external watchdogs or clear historical owners.

`select_native_coff_closure` now selects bounded, digest-bound explicit native
object inputs and applies existing section fixups. The retained CameraStyle object
emits sections3/4/5/6 (155/21/12/36bytes), records LIBC/OLDNAMES suppression and
SafeSEH/debug policies, and refuses missing bindings/associated regions, duplicate
roots or unsupported policies. Independent review checked16 metadata flag mutations:
executable/uninitialized/writable sections cannot hide behind metadata names.
Reviewed source SHA `c3f24216487d71ad4ff4e548dc81cd7b703fd012f1844e426024f7fe69b08bdd`.
That selector-only receipt is superseded by the reviewed integration above.
Fresh producer/publication verification is the next active task. No fresh compilation, build,
filesystem test, accepted matching-C increment or whole-image proof is claimed.

Retained CameraStyle replay `a8d1a9490c35` completed through8080 in3.338seconds,
without compilation. The v2 binding ledger independently corroborates selected
VC71 allocation/deletion bodies, exception-handler fixed instructions/hidden
EAX ABI and the absolute-zero FS exception-chain symbol. Game member names
remain analysis-derived. All four declared contributions (155/21/12/36bytes)
compare with zero differences under15 fixups; source/object/target digests are
unchanged. This is historical emission under declared placements, not accepted
matching C: COMDAT selection, associated closure, SafeSEH, compiler-option basis
and the copy-constructor hypothesis remain unresolved. The v1 receipt is retained.
Current memory observation:31GiB RAM,7.8GiB available;39GiB of42GiB swap occupied.
No compiler concurrency was added, no owner cleared and no runtime restarted.
Independent document review confirmed contract compatibility but also that the
replay parser treats the attached binding ledger as explanatory provenance,
not an independently validated identity authority.

The common identity gate now refuses recorded authentic-name conflicts and
actionable selected-contract contradictions. Newly persisted contradictory
candidates remain review/quarantined with alternatives and dependency lineage;
existing dependency invalidation can exclude their descendants. Disabled,
unqualified ABI shadow inference is not converted into a cross-platform veto.
Historical rows were not automatically migrated.13 inline gate cases and5
in-memory SQLite producer cases passed. Review caught already-review ABI vetoes
missing a dependency-quarantine marker; the corrected shared classifier passed
6 producer-loop cases and8 independent reviewer cases. The canonical source
SHA `1b6358225e055dea743a871cefb7f69e9a42a504e2586c9a16d6db03f3a01546`
matches its hot-applied SHA on PID2417358, zero restarts. The broader matcher
seed/propagation qualification order remains unfinished; no matching run or
compiler acceptance is claimed from this source repair.

Six-hour throughput audit (08:56–14:56UTC): four verifier attempts, three fresh
CameraStyle compilations totaling37.836 compiler seconds, one parser failure,
zero accepted matching-C results and no whole-image verification in the inspected
receipt roots. Two empty permuter jobs spent1078.23seconds repeating17 context
repairs/zero-pending passes. Eight parent turns re-reported project-button
acceptance; their combined140.8minute durations include other activity and are
not an exclusive UI timing measure. The last fresh compile ended10:47:11UTC.

The canonical permuter now checks queue/state eligibility before context repair
and idles on cheap input revisions when no actionable work exists. Production
COFF objects now yield independently FPO-bound primary mismatch diagnostics
without recompilation: the114/177/155-byte CameraStyle variants respectively
show134/101/0 relocation-masked differences. The155-byte variant has10 masked
relocations and is not raw-equal or accepted matching C. COMDAT selection,
associated regions and link closure still require qualification. Both changes
were checked in memory; fresh workers load them, but no new compiler job or
live watcher activation is claimed.

Verifier admission now accounts for its optional Ghidra FileBytes extraction:
omitted or malformed `raw` claims wildcard Ghidra access in frozen resource keys,
current admission and retained dependency assessments. An explicit valid image
path preserves the provider-independent route; this does not prove image identity
or clear historical owners. The unchanged 8080 PID2417358 reports source and
applied SHA `36829c55334aaa2d422ec9e4e9aad7786cb4d79453e88d2499d9b92dab2594e5`
for `actions/jobs.py`, zero restarts. Inline checks are not a compiler receipt.
The current dashboard reports zero running jobs and249 incomplete retained
ownership assessments; external watchdog PID2325 remains alive. No reservations
were released and no compiler was dispatched during this repair.

Captured callee declaration generation now refuses unsupported or missing return
types instead of silently emitting `void`. Its limited x86 C thiscall proxy
requires a captured first pointer and modeled builtin scalar/pointer arguments
and return; no first argument is discarded to invent `this`. Multiple arguments
require the second EDX slot. Ordinary non-thiscall declarations retain known
by-value structures without applying this proxy restriction. Prompt wording
distinguishes these generated C proxies from recovered native member declarations.
Source/facts remain retained on refusal. This change was checked with inline
memory-only cases, not a compiler run, native C++ ABI proof or recovery acceptance.

Full-project compile/link discovery now uses the canonical C/C++ language policy:
native `.cpp` units are included, their script invocations do not receive the C
compatibility preamble, explicit frontend selection prevents suffix-case drift,
and source language participates in object-cache identity. Colliding relative
object paths refuse before compilation. Traversal prunes only the owned
`.compiler-diagnostics` directory, preventing retained normalized failure inputs
from being compiled again as ordinary source. Default native mixed/C++ trees
select a C++ driver; explicit compiler and configured wrapper choices remain
unchanged. These are implementation fixes, not a newly compiled project.

Independent review and memory-only discovery/frontend/cache/refusal checks were
performed without compiler or filesystem tests. The final compile/link source
SHA `48696d633fd4f28fc7db191dce92e9b9a3106eda991ea4c4a060acc7b73037b2`
matches the live in-process applied SHA on PID213100, zero restarts. Initial
signature/import/closure-incompatible revisions were refused, then repaired in
source without restarting or forcing a runtime migration. Whole-image linking
still needs one authoritative source selection per function/variant; multiple
CameraStyle proposals may define the same symbol and cannot be arbitrated by
the donor `/FORCE` link as recovery. Same-build object provenance and original
PE layout/link closure remain required.

The direct-full-image diagnostic route now consumes source/object observations
from its own compile/link invocation instead of running a second compiler pass.
The owner captures bounded, stable source and object bytes, separates cached
objects from fresh compilation, invokes comparison on the collector thread,
and checks observed object digests before and after deterministic linking.
Generated entrypoint observations are excluded from recovered-function rows.
Selected/dispatched/successful/failed/not-dispatched/observed counts remain
explicit, are reconciled against rows, and expose unobserved units; a missing
coverage summary is not silently counted as complete. Target/raw captures and
candidate bytes are bounded and stable; database identity and function extents
come from one read transaction. Final raw and target recaptures are separately
scoped.

Observer staging does not yet capture a compiler include closure. Source-relative
include directives and filename-sensitive builtins therefore refuse before
compilation in observation mode, rather than silently changing header resolution.
Ordinary compile/link operation remains available; this restriction identifies
an unfinished observation capability, not completed whole-project recovery.
Independent review, AST and memory-only checks were used; no fresh compiler/link
job was run for this change. The parent reloader rejected the changed
`compile_and_link_tree` signature and retains the earlier applied revision;
fresh catalog workers import current source. No server restart or forced
migration occurred. Same-build local object diagnostics remain
`byteVerified:false`, `wholeImageVerified:false`; certified linked contributions,
toolchain closure and the fresh complete-image acceptance receipt remain open.

The following link-owner repair removes the donor `/FORCE` default: duplicate
or unresolved symbols must fail instead of being arbitrated into a candidate.
Linking uses an owned sibling temporary candidate and publishes only a successful,
nonempty output after checking the captured object inventory. Previous candidate
bytes survive a failed attempt, but their output-specific success stamp is
invalidated. Stamps bind exact ordered object paths/digests and output bytes;
the former shared directory stamp is preserved but ignored. This is artifact
cache evidence, not linker/library/Wine/environment closure. Automatic link-cache
skips are disabled until the execution-input closure is qualified; retained
artifacts remain usable diagnostics, not discarded work. Link timeout does not
establish that Wine descendants have drained: manual owner/process corroboration
remains required before any retry. Source review and memory-only checks are not
a fresh link receipt.
Independent review caught and repaired a stamp-enrollment race and a post-link
refusal that discarded timeout owner-reconciliation flags. Memory-only owner
checks cover failed/timeout links, changed input/output bytes, reordered/removed
objects, missing linkers and mandatory relinking without qualified closure.
Final link-owner source SHA:
`fffe4b039709e3fd615bae84fa949426317c044c5ab313ac61d855418dd47520`.

A bounded fresh K1 candidate was identified: existing
`GetLength_00406040.c`, an 18-byte CResRef loop without calls or data relocations.
Its historical exact-match comment is not a current receipt. PID213100 later
disappeared for an unknown reason; the authorized restoration now serves8080 as
PID1615148. Catalog job `af3c8d56af62` failed before compilation because an exact
candidate was combined with `limit`. Shared preflight now rejects that invalid
request with HTTP400 and accepts the corrected candidate-only request. Supported
database selection now binds the real external corpus and its sibling workspace,
rather than the checkout-local shadow default. The transactional JobStore
handoff is now applied on the unchanged PID, with root-bound receipt writes,
scoped history/cache, cancellation serialization and write-first preferences.
Independent review and memory-only rollback checks passed. The real selection
request safely refused receipt `772e68366608`: its unresolved historical
database reservation differs from current action requirements. No reservation
was cleared and target selection was not committed. Conservative policy-drift
import now preserves the original database hold plus the current Ghidra-project
hold, labels their unresolved mismatch, and refuses partial release. It passed
independent review and applied on the same PID (jobs SHA
`0f424ea25a028bc0fc02f88f0408934f9b8ce56adb986f3872298b982de202c5`).
The next real selection request refused legacy `193e0253cb0b`, an interrupted
function-evidence query with no captured database identity or ownership envelope.
The read-only audit now covers all 1,591 target receipts: 242 have unresolved,
queued, running or interrupted state; 176 of those lack execution-root
provenance and 241 lack resource keys. Actual nested-log parsing found 25
explicit unresolved-ownership envelopes, including terminal coordinator jobs.
All nine legacy cross-place receipts also require output-ownership assessment.
Function-evidence jobs are real provider executions, not disposable cache rows.
The repair in progress separates loading retained history from admitting
execution, preserving explicit claims and exposing dependency-local unknown
ownership instead of guessing historical database identities. No history is
deleted or promoted to clearance. Current-process observation still contains
only the failed pre-compilation probe; it is not a census of historical owners.
No fresh compiler result or full-image match is claimed.

The verifier now retains exact-success COFF objects as well as failures and
mismatches through its existing bounded content-addressed evidence store, in
both single and batch paths. Previously a successful temporary object vanished,
forcing later placement work to compile it again. Four memory-only production
flow checks covered single/batch exact/mismatch retention once per object.
Retention remains diagnostic and grants no source or image acceptance; a store
failure still fails the result closed. Fresh compiler activation is pending the
workspace ownership handoff and the candidate probe.

Compiler-side primary extent is now extracted from symbol-bound x86 FPO records
in the shared COFF owner, independently of target comparison bytes. Supported
16-byte records require exact DIR32NB start binding, valid code ranges, flags,
associations and non-overlapping unique records. Unsupported or contradictory
metadata remains unqualified; preview limits do not hide the selected entry's
full-record lookup. This does not waive the existing COMDAT acceptance gate.

The owned MSVC compile/link callback now issues a separate process-local native
emission observation, bound to original/normalized source and object hashes and
explicit fresh/reused execution status. It does not reuse the clang acceptance
capability. A supported primary range requires a unique executable function,
symbol-bound FPO extent, no code relocations and no unsupported runtime closure.
The direct-build diagnostic consumer now compares this range against captured
target bytes with exact selected-database binary identity and function extent.
No second compilation is performed. Forged/imported records, altered capture
hashes, invalid execution flags and unsupported closures refuse. The retained
multi-function CameraStyle object correctly remains unqualified on this route.
Independent source review and inline memory-only checks passed; no fresh native
compiler invocation or linked-image qualification has been demonstrated. Native
observations remain diagnostic, with accepted/byteVerified/wholeImageVerified
false even when their raw region comparison is equal.
Live reload initially refused a new compiler-module global. Using the existing
owned producer function identity removed that structural change without
bypassing the compatibility guard. `/health` now reports the compiler module
applied at SHA `c6ece8cf80fc141474a1163c1437acdf4bcd93a7d62ade4eb91f103436786fc0`
on unchanged PID1615148 with zero restarts. This establishes module activation,
not an actual compiler/callback execution receipt.

The next native reconstruction slice is implemented as a bounded in-memory
writer and evaluator. Producer-issued, relocation-free FPO ranges must match
independently selected database extents; nonzero COMDAT selection refuses until
link-selection evidence is supported. Reserved holes receive captured object
bytes, while remaining bytes and later floor overwrites have separate writer
records. Replaying those writers reports native placement bytes and withdraws
them after floor replacement; it never grants source verification, qualified
link closure or whole-image acceptance. Inline memory-only qualification used
a COFF/FPO specimen and mocked database/PE selectors for arithmetic; it is not
a real K1 compiler, database-binding or output-file receipt. Integration with
an owned file publication path and live compiler evidence remains unfinished.

Native linking now requests a map in the same owned link invocation and captures
ordered object digests, exact argv, linker identity, bounded map content and
linked-output identity. Content-addressed map publication cannot overwrite a
concurrent artifact. The direct-build observer consumes the registered native
link capability and attaches symbol/object provenance to its unit diagnostics;
it does not perform a second link or import receipt JSON as authority. Duplicate
or ambiguous symbols, colliding object basenames and library-member origins
refuse selection evidence. Map evidence alone leaves COMDAT selection, folding
policy and complete library/dependency closure unqualified. Source review and
memory-only capture/publication/consumer checks passed; no native link ran.
The clean optional observer API is not applied in the existing dashboard Python
process because its signature change is rejected by the compatibility guard.
Fresh catalog CLI workers read the source version; no restart or bypass occurred.

Link-map diagnostics now select the primary external executable symbol from
the issued capability's captured COFF independently of placement qualification.
Relocations or associated runtime sections can refuse placement without hiding
the observed map origin. The refusal remains explicit; object path/digest,
unique symbol and unique basename checks still apply. COMDAT selection and all
acceptance gates remain unchanged. AST and memory-only checks used retained
CameraStyle COFF with synthetic map/registry inputs, including copied-token and
basename-collision refusals; this is not a live linker receipt. Source SHA:
`45716c89c5ecc76c5831036b022ff04ef18d9965ee7ca0ca47f608c493f367c3`.
Independent source review approved the separated diagnostic boundary and
confirmed that map provenance does not grant placement or COMDAT authority.

Full-ledger memory-only restoration now retains 249 incomplete ownership
assessments, separate from strict captured reservations. The current verifier
probe intersects 154 assessments; declared retained-object reads and ownership
reports intersect none in that check. This is not live scope-selection or
clearance evidence. Ninety-one interrupted text-permuters lack owner/root facts;
six more have old boot IDs but no captured host identity or Wine-prefix facts.
Neither today's defaults nor missing PIDs establish their historical ownership.
The attempted live selection did not execute: its health precondition found
`jobs.py` rejected for `_retained_dependency_holds.<genexpr>` closure-layout
drift, with the previous `fe4c1c88…` revision still applied. Cross-role path
overlap now lives in an explicit-loop module helper, preserving the earlier
nested callable layout without dropping typed claims. Recursive code-layout and
memory-only overlap/disjoint checks passed; independent review also checked
inverse containment, provider tokens and domain deduplication. Source SHA is
`eb93166f32c18750908670e273ff2839f42a9244b901f577ec646b5b835d1a18`.
No database-selection POST or compiler submission occurred.

After the project-opening UI validation, the serving PID1615148 disappeared;
its owned server session64335 returned exit143 and port8080 had no listener.
The cause is not established; this is not an OOM diagnosis. Ghidra server2476
remains present. No restoration, ownership clearance or alternate-port fallback
was performed. New source checks do not establish runtime activation.

Subsequent authorized restoration reopened that same existing `repos.gpr`
(32 programs) in the canonical NVMe environment on8080 as PID2298900,
started08:46:31 local time. Playwright observed in-process reload mode,
zero restarts in the restored process and zero current jobs. The supported
database-selection POST then returned200 for the external `kotorxid.sqlite`
and restored its retained receipt scope without dispatching historical jobs.
The strict772e identity/Ghidra holds remain; no clearance was inferred from
the prior server exit.

The compact jobs API previously hid incomplete ownership assessments even
after loading them. It now reports249 assessments, with per-domain counts
database95, Ghidra136, output17, compile9 and local-recovery154, plus one
policy mismatch. Counts overlap; they are not distinct pending job totals.
Source review and memory-only aggregation/nonmutation checks passed. Playwright
verified the actual jobs consumer and matching applied/source openapi SHA
`d3d2bc5adf8f6f33fdffbf08bf2c895a8df71256bd0fa1fa9c901dedb5ffeceb`
on unchanged PID2298900. No compiler job was submitted and no assessment was
released.

That restored server subsequently also disappeared: session1440 returned143,
PID2298900 was absent and8080 again had no listener. The successful selection
and hot-reload receipts above remain historical observations, not current
availability. A second restoration is deliberately not attempted while the
repeated termination cause is unknown. Read-only kernel/oomd checks found no
corroborating entries; they do not prove who sent a signal or rule out every
host-level cause. The retained claims are unchanged.
Bounded Codex host-log inspection found no matching termination record.
Upstream managed exec-session pruning and handle-drop termination are a possible
lifetime mechanism, not confirmed attribution or installed-version equivalence.
Operational restoration must establish independent service lifetime and explicit
PID/start/cwd/resource ownership rather than repeat managed foreground launches.

The explicit resource-reconciliation report now has a source-level current-use
observer for incomplete compiler/local-recovery assessments. It snapshots the
assessment under the scheduler lock, then probes outside that lock. Dependency
paths come from the current canonical MSVC adapter and selected workspace,
explicitly not a reconstruction of the historical job's configuration.
PID/descriptor inventories and metadata reads are bounded; boot/machine,
namespace, stable process identity and coverage gaps remain visible. Reports
omit raw command/environment/cwd/descriptor data. Different Wine-prefix or
output path spellings do not prove physical disjointness; alias uncertainty
remains unknown. Positive observed use takes precedence. Non-atomic snapshots
and same-PID exec/classification races remain explicit limitations.
The private repair path never invokes this observer or changes eligibility.
Memory-only observer/classifier/consumer checks passed; no real process scan,
compiler invocation or live report consumer was exercised. Source hashes:
supervision `0ca29690751db0855ed027588a4dc54025e49be8a7a0d27b5827644d36ccc20c`,
jobs `2eecf329cdd7e2ea83c6241d519cccd8580870cc0004463f9a0e0ca706e12173`.
Independent final review approved the lock/authority boundaries and six pure
classification cases, including alias uncertainty and occupied precedence.

Subsequent authorized one-shot restoration serves8080 as PID2417358, started
09:03:28 local time, in an independent session holding an exclusive runtime-owner
flock. The launch command returned; no automatic replacement loop was added.
Startup reused32 programs. Supported external database selection returned200,
preserving249 incomplete assessments and strict retained holds. Read-only catalog
report `1bf423c82cea` then exercised the actual observer in179ms:823 process IDs,
three candidates and49 descriptors; all compiler/prefix/output domains remained
unknown, with incomplete metadata coverage. Its terminal failure represents
refused clearance, not a failed compiler invocation. Historical ownership and
admission authorization remain false. Subsequent health checks show the same
PID and zero restarts. No compiler ran and no reservation was released.

The bounded historical permuter audit found17 saved variants,17 closed entries,
2,386 unsuccessful-search priors and5,588 queue records on NVMe. All17 variants
differ from the current source pool and contain mixed C plus inline assembly;
they are reusable candidates, not17 recovered-C wins. Their retained32-byte
target slices agree with the current captured Ghidra image and selected DB
extents. Retained `target.o` files are synthetic target substrate, not compiler
emission; the historical scorer discarded its temporary compiler outputs.
Thus target/source priors survive, but no fresh compiler or whole-image proof
can be recovered from these files alone. No variants were overwritten or
promoted. Five historical execution boots were independently corroborated
against this machine's NVMe journal; that does not clear current dependencies
or authorize admission. One further boot remains uncorroborated.

Native placement now has an actual owned-file publication path in the direct
build consumer: a separate exclusively created `native-placement.exe`, leaving
the stock linked candidate and target untouched. Producer-issued captures,
independent DB-bound regions, current source/target bytes, readback identity and
final writers are rechecked. Remaining bytes are explicitly preserved target
floor, never source credit. COMDAT/EH/relocation refusals remain; copied JSON
cannot issue capabilities. Region-only qualification is shared by selection
and publication, removing up to64 redundant full-image copies. Independent
source review and eight inline memory-only checks passed; no publication file
was created during validation and no compiler ran. The current8080 health check
returned200 on unchanged PID2417358 with zero restarts but no applied-file
receipt for these modules. Source implementation is not live compiler evidence.
Final source SHA: contribution
`140faab5744760f0b34a222045c50819e8372c8911109dc226d1331c131ed903`,
direct verifier `86eb3a98fef7a9a7d36c2ebfa8999f7dc1bc026ecf57025b62dc390761d1ef37`.
The publication remains diagnostic-only: source, linked-contribution and
whole-image acceptance are false. Fresh compiler/toolchain closure and final
full-image objdiff acceptance remain unfinished.

A separate assembly-free Warp initializer candidate is preserved under external
`corpus_work/native-candidates/k1_win_gog_swkotor.exe/`, not inserted into the
default source pool or substituted for either historical variant. Captured-image
disassembly and DB8 corroborate constructor0x44c5c0: ECX carries this, name and
handler occupy the stack, and the callee pops8 bytes. The existing fastcall
declaration incorrectly assigns the name to EDX. The candidate uses native C++
placement construction; original symbol decoration, handler signature provenance,
literal placement and C++ runtime closure remain explicit uncertainties.
The supported8080 verifier action accepted a dry-run request with the exact
`.cpp` basename, workers1 and fresh-compilation selection, omitting an external
executable path. HTTP200/dryRun=true returned no job; this validates request
wiring only, not compiler execution, target extraction or ownership admission.
No fresh probe was submitted while incomplete resource claims remain unresolved.

The canonical permuter signature adapter had a concrete ECX/EDX regression:
it inserted the spare register argument before the original this parameter.
`ctxtypes.fix_thiscall_signatures` now owns the limited x86 C-only conversion;
the bulk, sanitize and permuter public wrappers delegate to it. Explicit pointer
`this` remains first, with the EDX dummy second. Native member contexts,
unknown first-parameter origins, preprocessing, unsupported shapes and uses
requiring independent call facts remain unchanged rather than guessed.
The existing shared scalar gate now distinguishes builtin ABI scalars from the
broader spelling vocabulary: unknown typedefs cannot silently bypass aggregate
or hidden-return uncertainty. This also applies to fact-bound call repair;
unsupported alias-valued calls now explicitly refuse until scalar facts exist.
Independent review and inline memory checks passed; all four files parse.
No compiler or serving-module activation is claimed. Already-generated incorrect
fastcall sources are not automatically repaired by a declaration-only helper.
Separate high-emitter/curated-enrichment proxy recipes remain outside this slice.

The subsequent ABI slice consolidated those remaining high-emitter and curated
declaration recipes into the same `ctxtypes` owner. Semantic emission and the
sourcegen acquired-source guard remain unchanged; native C++ members retain
their spelling. Only the stale sourcegen convention-equivalence comment changed.
Independent review and inline memory-only checks passed. No compiler or runtime
activation is claimed. This removes duplicated declaration lowering; it does
not replace fact-bound call repair or establish complete ABI recovery.

The current-use audit also identified a live legacy K1 watchdog outside the
dashboard: PID2325, started03:58:22 local time, running the donor
`recover_supervisor.sh watch /K1/k1_win_gog_swkotor.exe` path. Its current child
was a sleep process; none of16 inspected shard lock files had a kernel-held
lock at that snapshot (ten files were absent). Watch mode can nevertheless
launch replacement shard loops every300 seconds, so this is not future-writer
clearance. No signal, control request or donor edit was performed. The other
`.exe`-argument controller is a KPHarness application server, not an observed
compiler; the current classifier does not distinguish those roles. Different
selected/default Wine-prefix directory identities do not alone prove complete
tree disjointness. Current swap was42GiB used with9.1MiB free. Safe admission
still requires controller/prefix/resource ownership qualification; adding
workers or dismissing the live watchdog is not an acceptable workaround.

Microsoft's [FPO_DATA layout](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-fpo_data)
defines the function byte count used by this reader.

Read-only dashboard job `fbcc420b02aa` exercised that implementation in 3.368 s:
retained copydecl object metadata section8 binds primary symbol11 to section3
offset0/155 bytes, agreeing with the captured 155-byte region. Four contribution
comparisons and 15 relocations still ran. `byteVerified:false` and
`wholeImageVerified:false` remain explicit. No new compilation, filesystem test,
source acceptance or restart occurred. The emitted extent resolves one specific
unknown; independent symbol bindings, actual COMDAT/EH/SafeSEH linkage and
same-build contribution to a complete exact-placement image remain open.

The existing dashboard dispatcher now exposes read-only catalog action
`corpus.replay-native-object`. It requires source, diagnostic id and a digest-bound
retained object; binding contracts are now optional. The target defaults to the retained Ghidra FileBytes snapshot,
not an externally supplied executable. It validates retained/current source and
object identity, normalized input, whole target/region hashes, PE machine/base,
explicit binding provenance and duplicate entries. Output previews are bounded
without truncating actual fixup execution or section comparisons. It does not
compile, update verifier caches, publish substitutions or grant acceptance.

Automatic target-derived constraints are now the normal replay path. Numeric
section identities and the existing relocation equations derive reachable
contribution bases and external addresses only after all non-relocation bytes
match. Conflicting bindings, malformed/unsupported relocations, overlapping
placements, missing data and overflow refuse. The entry defaults to one unique
external function symbol; ambiguous objects require an explicit `entry-symbol`.
An explicit digest-bound contract remains available as an opt-in override.
Both modes share the existing placement/comparison owner and bound contracts to
2 MiB; neither selects COMDAT winners or interprets unreferenced metadata.

Live job `a61c00b5e35b` completed in 0.797 s with no manual contract or target path:
four contributions, seven inferred externals, 15 relocations, zero differing
bytes under those constraints. Contract digest:
`581da1ff79d8527a9903777ca40676b8a5babcb5fdcdcf014dcb81c70fa6ced6`.
Its report explicitly records `independentBindingEvidence:false` and all recovery
acceptance flags false. Target-derived operand agreement is not independent
identity proof. Earlier wrong-shaped emission `3533130c…` was then refused by
job `2cd26941fb90` in 1.211 s (`target_section_shape_mismatch: 3`), without another
compiler run. Independent source review and memory-only conflict/refusal checks
passed. Server PID213100 stayed unchanged, zero restarts, final active jobs empty.
No filesystem tests, compiler invocations or substitutions were produced.

Live dashboard job `ad4fadae81ac` finished successfully in 0.837 s on unchanged
server PID `213100`, applying 15 relocations to four contributions; all four
equal their declared target regions. The report records `diagnosticOnly:true`,
`freshCompilation:false`, `byteVerified:false` and `wholeImageVerified:false`.
The binding contract digest is
`ee0d1349898a01e6ce8dcdee053d5ae9a579d0922374f7d2fc1069e3ef3742c1`;
its ABI/type/target-derived assumptions remain explicit and unqualified.
Unplaced sections are 1, 2, 7 and 8. Parser-derived catalog discovery and generic
`/dashboard/api/jobs` dispatch were observed; the startup-mounted typed URL for
this newly added action returns 404 and was not used as an execution path.
No restart, new compiler run or filesystem test occurred for this replay.

Explicit multi-section placement is now implemented in the existing
`coff_fixup_roundtrip.place_sections` owner, reusing bounded COFF inventory and
the existing relocation arithmetic. Section-index bindings avoid duplicate local
name collisions; missing internal placements, overlapping spans/fixups, BSS,
common/weak/debug symbols and unsupported relocations refuse. COMDAT associations
are preserved without selecting winners or inferring function extents. This is
a pure diagnostic API, now used by catalog replay but not an acceptance path;
the existing verifier gate is unchanged.

Read-only placement of retained object `2b1a809e…` reproduced four captured target
regions with zero differences: entry `0x5c2540`/155 bytes, cleanup+handler
`0x723170`/21, string `0x747a14`/12 and unwind map+FuncInfo `0x772a44`/36.
Bindings remain explicit hypotheses: stored GOG call edges resolve allocation to
`0x6fa7e6` (not the nearby unwind routine), while delete/free equivalence and the
segment-relative `FS:[0]` external require separate qualification. Some placements
come from observed target associations, not independent symbol authority.
Directives/debug/SafeSEH metadata are unplaced. These equalities are diagnostic
only, with zero new accepted recovery and no whole-image proof. Independent
source review and inline memory-only refusal checks passed; no new compiler,
filesystem test, dashboard restart or substitution publication occurred.

The retained CameraStyle `/GX` calibration job `aa19592f0514` is terminal
(exit 2), with zero byte-exact results. Its fresh compiler invocation took
10.960 s; object SHA-256
`4e0c33ca01145a0e0f1c66007c8b6273ee46e73b7e43b928949b8e62fae31a84`
and normalized-source digest were corroborated from the retained manifest.
The main section is 177 bytes versus the target's 155. Native EH contributions
are present: 21-byte cleanup/handler code and 36-byte exception data, associated
with entry section 3. The remaining observed discrepancy is aggregate argument
construction: a temporary plus four DWORD copies rather than direct construction
in outgoing storage. Original class/copy semantics and compiler qualification
remain unresolved; COMDAT extent/contribution closure is still refused.

Per-job `compiler-options` now reaches single, batch and fallback invocations
through a captured child environment, participates in cache identity, and does
not modify dashboard/global defaults. The `/GX` policy is a calibration, not a
qualified original profile. Future diagnostic previews now include bounded
section sizes/hashes, associative COMDAT links and relocation records (64 sections,
64 total relocation previews); unknown/ignored bindings remain unresolved and
hashes explicitly cover raw section data. Inline AST/memory checks and inspection
of the retained object passed; no filesystem tests or additional compilation were
performed for this diagnostic change. Historical objects/source remain intact.
The verifier is absent from the server's loaded modules; this change applies to
future worker imports, not an asserted hot-reload of an active verifier.

The subsequent one-candidate dashboard job `2196d08c9eb7` compiled the preserved
`Load2DArrays_CameraStyle_copydecl_005c2540.cpp` hypothesis with the same flags
in 13.318 s. Adding only `CResRef(const CResRef&)` reduced the main section to
155 bytes and reproduced direct outgoing-argument construction. Independent
read-only comparison found zero differences outside the ten declared 4-byte
relocation operands; raw bytes still differ (21 byte positions). This is a
diagnostic observation, **not** function or whole-image acceptance. Scoped Mac
authentic symbols identify the nearby constructor as `CResRef(unsigned char*)`,
not a copy constructor; no emitted copy/destructor symbol was found there, which
does not exclude an inline implementation. The added declaration remains an
unverified reconstruction hypothesis.

The retained object is SHA-256
`2b1a809ec96e79c51508497de365a9855763d8cdc43c05bdbe392a39688e3e12`,
diagnostic id `ea6e3eb5cb20fc0fb4ee52d40ccde40e4f82e99246bf68eeec4ea5a7ecac7e67`.
Its new bounded contribution preview was exercised by the actual fresh worker.
The job exited 2 at the unchanged COMDAT extent gate, published zero substitutions
and recorded zero byte-exact results. Next work is authoritative symbol/extent,
target relocation binding and associated EH/data closure—not another blind
compile, relocation masking for acceptance, or counting this as matching C.

The authorized post-boot restoration is now serving 8080 as PID `213100`,
started 04:23:32. Its existing local `repos.gpr` reopened with 32 programs;
this is not a shared-server synchronization receipt. Playwright `/health`
confirms canonical NVMe module paths and in-process reload with zero restarts.
The project virtualenv now uses the complete 115 MiB Python 3.14.5 runtime copied
to NVMe; a read-only directory comparison found no differences. The original
runtime and the previous virtualenv interpreter symlink remain recoverable.

All five Open-project roots have live Playwright receipts: work lists 222 entries
in 4.0 s (previously a 12 s timeout), cwd lists 40 in 3.3 s, projects and repos
open in 1.8 s, home opens in 1.5 s. Five tabs remain, repos restored active.
Opening/reopening used session PUT with `admitOpen:false`, not recovery admission.
Folder listings defer sibling program inventory and binary inspection until open.

The legacy startup watchdog recreated a cancelled text-permuter even though its
passes had zero pending candidates and repeatedly compiled the context. Scheduler
scope `lane:undeclared` was paused through terminal control job `38f2b3ae7216`;
job `5c8274276aab` is cancelled and PID `249531` and its children are absent.
The source retirement initially failed (`None.__code__`); `unified_pages.py`
remains quarantined. A scoped coordinator control, `retire-legacy-watchdog`,
requires paused admission, verifies the captured thread/callable/module/path,
and conforms only its explicit retirement guard without executing module code
or clearing quarantine. Job `8ae90b94dfd3` succeeded on PID `213100`; independent
`ps -T` confirms the previously observed watchdog thread `221450` is absent.
Fourteen ownerless queued legacy replacements reached terminal `cancelled`.
With no active jobs and the old thread absent, control job `682b49316ec2`
resumed `lane:undeclared`. The old startup hook was
removed from source after observed daemon exit (module quarantine is retained).
The
catalog now invalidates cached actions on executing-definition changes as well
as source stamps, preventing stale controls across the reload timing window.
This is scoped watchdog retirement, not recovery of the quarantined module.
Existing compiler workers stay stopped. No missing
historical reservations were released. No full-image recovery proof exists.

Earlier post-boot revalidation (superseded by the restoration above): the host reports a
2026-10-10 03:58:09 boot, PID 1761367 is absent and port 8080 has no listener.
Playwright project-open validation returned `ERR_CONNECTION_REFUSED`. The prior
startup log in `/tmp` is also absent. The persisted `repos.gpr` still exists;
these observations do not establish native database health or safe clearance of
every retained resource claim. No dashboard was launched or restarted and no
recovery jobs were admitted during this revalidation.

The project-open client additionally bounds tab persistence to 45 seconds,
normalizes HTTP failures to `ok:false`, and keeps save errors visible inside the
dialog instead of relying on a toast. Syntax and memory-only flow checks passed;
these new failure-path changes have no current live-browser acceptance receipt.

Earlier live receipt: 8080 was PID 1761367 in the NVMe checkout; `/health` reported zero
restarts. Playwright verified shared `repos` opening (32 programs), local project
opening in a separate tab, and restoration of all four persisted tabs after
reload. The client no longer discards the tab list merely because concurrent
context discovery changed function navigation. The observed session read still
took 17.1 seconds; that latency is unresolved.

The project-wide recorded-source ZIP catalog action is mounted. Its worker and
frontend reconnect logic are implemented, but no end-to-end archive execution
receipt exists. A tab switch now leaves its existing export reconnectable rather
than permanently disabling the download control. Inline JavaScript syntax and
Python AST checks passed; no filesystem tests or builds were run.

The current jobs endpoint reported 57 queued jobs and zero running admissions:
54 provider reads, one bookmark operation, one match operation and one binary
source export. Resource maps retain five owners missing from the in-memory job
list and one quarantined failed provider. Individual historical receipts remain
readable; their empty execution-owner fields do not prove process clearance.
No reservations were released and no new recovery jobs were admitted.

The admission observer now reads exact retained receipts outside the scheduler
lock (no full-history scan), reports their action identities separately from
missing live records, and names paused scopes. Live Playwright corroborated the
new consumer on the same PID. The explicit static jobs refresh previously timed
out after five seconds while session reads took 17 seconds; it now permits a
bounded 30-second response without adding polling. Retained ownership remains
unresolved, not automatically released. The undeclared lane is explicitly paused.

The latest retained K1 offset-5000 slice selected ten of 24,276 sources: ten
compiled, zero byte-exact, total 41.733 seconds and three compiler batches totaling
23.697 seconds. Its captured target/region digests were independently checked.
The Load2DArrays family has a concrete ABI discrepancy: the captured CResRef
constructor receives its string on the stack, but generated fastcall declares it
in EDX. Ordinary ExceptionList globals, invented stack globals and invalid
GhidraBlob overlays independently prevent trusting that source. Correcting ABI
alone does not prove exactness. Discarded mismatch objects also prevent detailed
retrospective emitted-instruction diagnosis.

The bounded ABI repair is implemented in `ctxtypes.py` and `ghidra_bulk.py`:
captured direct scalar/pointer thiscall calls and their shared declarations are
adapted together. Ambiguous syntax, missing types and by-value aggregates refuse
before compilation; semantic mode does not approximate native member ABI. The
family's by-value CResRef/SEH/layout reconstruction remains unresolved. Historical
source artifacts were not overwritten; no repaired source was compiled.

The verifier now retains normalized inputs, emitted COFF objects and bounded
diagnostics/relocations for single/batch failures and non-raw-exact comparisons,
separate from accepted substitution artifacts. Atomic content-addressed storage
has a 4 GiB/50,000-entry cap and constant-sized capacity accounting; timing remains
in invocation receipts, not artifact identity. AST and memory-only checks covered
invocation counts, retention handoff, timing-independent identity and ABI refusal.
No diagnostic-store filesystem execution or compiler qualification occurred.
Verifier body changes conservatively change the cache basis; old receipts remain
available, but separating observational retention from semantic cache invalidation
is still unfinished. These modules were absent from serving `modulePaths`; their
changes apply to future worker imports, not an asserted current-job activation.

The next source increment adds exact-entry diagnostic replay before compiler
dispatch: bounded no-follow reads verify manifest/input/object digests and current
source/normalized-input/adapter identity, then compare the preserved COFF without
publishing substitutions. V1 lacks a complete invocation basis, so replay remains
explicitly diagnostic-only (`freshCompilation:false`, no verification credit),
and ambiguous batch emissions refuse. It does not skip a required fresh compile.
AST and memory-only checks passed; filesystem behavior and mounted operation are
unqualified. All ten retained slice rows lack object-retention references, so this
increment cannot resurrect their discarded objects or demonstrate a speedup yet.

The extraction owner no longer silently chooses the first `.text` section.
It validates COFF table/range/relocation bounds and refuses ambiguous code,
COMDAT extents and unsupported operand widths with explicit comparison details.
Retained diagnostic replay uses that same owner instead of a second parser.
AST and memory-only malformed/ambiguous-object checks passed, including independent
valid/truncated-code checks. No compiler run qualified this change; it applies
to future worker imports. Native C++ still requires captured function-symbol
extents plus associated exception/data contributions, not just section selection.

The verifier/MSVC adapter now discover, select and stage `.cpp` alongside `.c`.
Native C++ input is preserved without the recovered-C preamble; per-file `/Tc`
or `/Tp` selects the frontend. Language is recorded in comparison/retention
identity, and same-stem/casefolded batch output collisions refuse before launch.
Memory-only checks passed; no native C++ compiler probe or byte-match receipt
exists. One bounded COFF inventory owner now preserves primary and auxiliary
symbols, section bytes, relocation records/addends and COMDAT associations.
It does not infer function extents. The verifier and retained-object summaries
use that owner; existing fixups import its unchanged relocation definitions.
The verifier still refuses COMDAT/split code and unsupported masks. Parser source
identity participates in cache invalidation; old results cannot silently inherit
the new comparison policy. Name decoding is memoized and bounded (64 KiB per
name, 8 MiB unique-offset total). Standard auxiliary unused bytes remain raw,
and malformed COMDAT symbol ordering refuses. Memory-only projection checks
accepted ordinary i386/amd64 objects and rejected auxiliary relocation targets;
the retained 915-byte AIActionAppear object remains COMDAT inventory, not proof.
The canonical shim classifier also rejects unmarked embedded-machine-code sources
before compiler dispatch; classifier identity participates in cache policy.
No compiler job ran, no fresh matches were gained, and these modules are not
loaded in the current serving process: changes apply to future worker imports.
Scope correction: a new arbitrary-source submission UI is not a prerequisite.
Authoring actual recovery source with `apply_patch` and submitting its exact
basename through the existing catalog is the current native MSVC frontdoor.
The GNU workbench scratch action is a different compiler path.
Next: exact compiler-symbol/target-extent binding and contribution/relocation
comparison, reusing retained emissions before another compiler invocation.
Retained
objects demonstrate function-size auxiliary records cannot be assumed present.

Fresh native C++ observation: dashboard job `8b8ad5f6532c` compiled the separate
`Load2DArrays_CameraStyle_005c2540.cpp` candidate through the owned MSVC adapter.
Historical `.c` SHA remains
`db1236fc83ba39cbb5281a2ad0bff528cbcd63619907eeab62b84e49b7f4856e`.
Receipt: `corpus_work/k1-gog-native-cpp-camerastyle-20261010-v1.json` under
the NVMe projects root. One candidate, zero byte-exact results; compilation
13.558 s, verifier 15.448 s, dashboard job 18.595 s. Terminal exit 2 reflects
`unsupported-coff-comdat-function-extent`, not a compiler syntax rejection.
The 1,117-byte object is retained with SHA
`3c68618034886bf6957ebf9b6d556894120ade505f90ee07d66c7a882d67e9e3`;
retention id `9f9df4a72cab217aab05dca3e51ee6335fcae4bc1ad2077597b15e4cd711f9d6`.
The normalized input equals the complete `.cpp` source, without a C preamble.
Its sole function symbol is the proposed decorated entry, at section 3 offset 0,
with no function-size auxiliary. The text section is 114 bytes, not the target's
155; read-only disassembly shows an aggregate copy and no SEH registration,
unlike the captured target. This identifies compiler-policy/type-construction
residue for the next calibrated probe; it does not qualify an original compiler
profile, emitted extent or contribution closure. No substitution artifacts were
published; complete toolchain basis and whole-image proof remain absent.

A fresh read-only audit corroborated all ten source and target-region digests and
the captured image digest. Every selected original uses `fs:[0]` SEH registration.
CameraStyle at `0x5c2540` (155 bytes) is the bounded family probe: it constructs a
16-byte CResRef directly in outgoing argument storage, invokes the C2DA constructor
(callee `ret 0x14`), stores at `[this+0x74]`, then loads the table. Native C++
construction, qualified layouts and exception settings are required; ordinary
ExceptionList globals and dummy-EDX repair cannot reproduce that behavior alone.
No new candidate was compiled. The virtualenv Python executable currently resolves
onto MyBook rather than NVMe, an unresolved runtime placement dependency.

The earlier runtime reported an `actions/jobs.py` hot-reload partial failure (`NoneType.__code__`);
disk changes must not be described as fully activated. Closure recoding in the
installed Jurigged/Codefind path contains a corresponding unsafe `None` case,
but the exact failing closure has not been identified. The standalone package
now has a source-only preflight refusal with callable location and merge-failure
traceback diagnostics; it has not been installed or activated. Fixing activation and
qualifying retained ownership precede further admissions. No fresh whole-image
compiler/objdiff zero-difference receipt has been demonstrated.

## Project lifecycle implementation — 2026-10-09

Implementation is proceeding in the existing NVMe checkout while the independent
MyBook transfer continues. Neither the unfinished Git merge nor the source
transfer has been declared complete.

Current source changes separate HTTP Project API locators from native RMI,
expose ambiguous local project choices, and recognize `.gar` as a project
archive rather than a program. Workspace/revision/operation/conflict storage
is additive migration 15; historical bindings remain retained. Complete
memory-only migration and reader-admission checks pass (basis hashing stubbed).
The running process has rejected structural schema edits; no live migration
or server restart was performed.

Native Save now checks the captured owner, dispatches exact program paths,
includes locally saved changes awaiting shared check-in, and requires server
revision evidence. Captured Save does not use synthetic-bookmark retry paths.
Open-program persistence is explicitly partial until project metadata/history
is confirmed; the static Save toast honors this distinction. Unsupported remote
Save As no longer substitutes a bookmark or skeleton. Existing destinations
are not deleted, and owned source databases are not copied by the file helper.

Fallback reintegration retains existing programs as unresolved alternatives,
does not overwrite or delete projects, and does not mark skipped work complete.
This is a safety correction, not delivery of native conflict-aware comparison.

Verification so far: inline AST checks, in-memory identity/migration/save-handle
checks, independent read-only review, and Playwright health receipts on 8080.
No filesystem tests, test files, builds, native save/conversion writes or
independent reopen/publication receipts have been run. Full HTTP operations,
staged conversion, native category reconciliation, durable resumability and
dashboard acceptance remain incomplete.

## Match-review frontend and backend — 2026-09-27

Match-review is implemented in source across the workstation, the static
`/dashboard` window and the full app: token- and selection-bound decisions, a
pending HTTP 202 response, a two-step confirm before sending a decision, and
select-all for the current page. Every UI now pages the review queue by match
ID; the old score-ordered cursor is refused by name instead of being misread.

This is staged, synthetic qualification only, not a mounted-consumer check.
Backend: 90 tests passed and 3 were skipped (no native `clang`, so the
compiler-backed consumer half is not qualified). Frontend: 23 tests passed and
`tsc --noEmit` is clean. The mounted consumer on port 8080 is blocked: no
process owns 8080 in this session (see the 8080 diagnosis below), so none of
this was exercised in a browser. The Vite bundle under `static/react/` predates
this work and is stale; it needs to be rebuilt from current sources before the
optional Vite app can show any of it. The hand-written `static/workbench-app.js`
has no behavior tests of its own; only `node --check` (syntax) and the parallel
TypeScript logic, which `tsc` covers, back it.

**2026-09-28 flag, not resolved:** this section reports 90 tests passed and 3
skipped, and other 2026-09-27 sections report further test runs (23 frontend
tests, `tsc --noEmit` clean), while Phase 15 adapters and other units remain
open. This tension is with the test moratorium
(`docs/plans/2026-09-21-loop-charter.md` §6b, 2026-09-21: no tests are created
or run until the plan, design and diagrams are fully completed and built to
completion). Needs an explicit decision: was the moratorium lifted, scoped to
the SDD build units only, or is this a breach — not resolved here.

Packaging status is separate from this frontend work: the `.18` overlay is in
qualification (built from the accepted `.16` wheel plus checkpoint fixes; it
excludes match-review and frontend changes). `.16` remains the accepted wheel.

## Cross-place and weekend export qualification — 2026-09-27

The subsequent [D3 destination-isolation receipt](verification/2026-09-27-d3-destination-scope.md)
records accepted `.16`: conflict demotion is scoped to the actual destination
binary, with an explicit phase0.4 basis revision and retained phase0.3 history.
Its affected installed selection passed 32 cases and independent final artifact
review approved. Historical rows were not repaired or rebaselined; universal direct
mutator basis enforcement and live activation remain open. This quick matching
correctness prerequisite precedes the larger watch-continuation implementation.

The [living ledger](plans/2026-09-27-implementation-progress-and-live-track.md#accepted-admission-active-implementation-cross-place-continuation)
records the cross-place repair of address-only receipts and direct recipient
writes. All three placement entry paths now use the reviewed candidate admission
source. Repair3 passed 24 affected source cases, and a separate actual native
negative/replay case passed; earlier attempts and failures remain recorded. The
`.15` wheel passed **203 installed checks** and independent final artifact review
approved its bounded scope; the [receipt](verification/2026-09-27-cross-place-admission.md)
retains exact artifact hashes, earlier attempts and evidence classifications. No live propagation
was run. Its first constant-leaf provider does not establish general variant/ABI
compatibility or recipient source acceptance.

Continuous watch remains unfinished: the current process-local 128-key limit has
no automatic successor/cursor mechanism. Durable failure budgets, bounded epochs
and uninterrupted output ownership across session-cleared generations are the next
required increment. `.15` is a bounded safety increment, not completion of this
workstream. The [weekend unit ledger](plans/2026-09-27-weekend-unit-delivery.json)
now enumerates all 193 original D/U identifiers. Delivery starts unverified and
advances only on scoped evidence; D1/D9 have the first partial evidence entries,
without inheriting historical checkmarks as completion.

The same ledger now records a source-qualified Phase 12 U87–U90 audit: the v1
exporter and legacy header path are partial prerequisites, while the aggregate v2
bundle, generated Lua and readiness/v1 outputs remain open. The header producer
requires exact-layout improvements. These findings preserve the full weekend
scope and are not test or runtime acceptance claims.

## Native package-verifier ownership — 2026-09-27

The [native ownership receipt](verification/2026-09-27-native-verify-ownership.md)
records the bounded `recover.verify-package` output-tree and native compiler
lifecycle contract. Actual child metadata, environment, compiler and selected
input/output checks qualify the supported profile; release requires exact
executor/session evidence. Modern requests known never to have dispatched retain
durable proof through cancellation and restoration. Independent review corrected
both initial receipt durability and command-freeze cancellation races. All 139
affected source checks passed; the later test-only readiness correction passed
its two affected source cases. Both source review scopes and the fixture repair
are approved. The `.14` wheel passed all 139 installed checks and final independent
artifact review approved. General compiler/Wine/project/store
ownership, cross-version receipt migration and live activation remain open;
P0.3/D36 and M0 remain partial.

## Fresh source revalidation — 2026-09-27

The [fresh revalidation receipt](verification/2026-09-27-fresh-source-revalidation.md)
records an explicit offline restart route using the existing supported compiler,
writer and matching-status consumer. Old audit JSON never restores authority.
A changed candidate is rejected while an independent sibling is freshly produced
and credited; later audit import still yields zero. The final new-module suite
passed 27 cases and independent source review approved. The `.13` wheel passed
the complete 60-case installed selection and independent artifact review approved. P0.4/RC-02 and M0 remain
partial; catalog/game-target qualification and durable trust without reexecution
remain open.

## Nested MCP dispatch accounting — 2026-09-27

The [nested MCP budget receipt](verification/2026-09-27-nested-mcp-budget.md)
records a distinct preparation-owned tool-call allowance, durable intent charging,
lease-bound private dispatch authority, revision controls and explicit exhaustion
projection in both frontends. Unknown effects survive later quota refusal; normal
transport wrappers do not invent uncertainty. Backend source checks passed 113
cases after correcting unresolved-effect replay with spare budget. Frontend checks
passed 38, full TypeScript and locked asset build passed, and UI review is approved.
Final backend re-review approved the correction; development wheel `.12` passed
all 113 installed checks and final artifact review approved. Shared
circuits, other usage dimensions and live activation remain open; this is partial
P1.1/M0 delivery.

## Qualified local output ownership — 2026-09-27

The [local-output ownership receipt](verification/2026-09-27-resource-claims.md)
records a source increment for the real ReAgent snapshot export action. It replaces
generic parameter-name inference with an explicit destination-tree contract,
binds execution to that path, checks overlapping paths across resource kinds and
retains unknown ownership across restart. Qualified executor clearance permits
automatic release. The receipt records focused product tests and independent
review status. The increment is packaged in `.12` with installed regression
coverage. Activation and general compiler/Wine/project/store lifecycle coverage
remain open; P0.3 and M0 remain partial.

## Scoped activity evidence — 2026-09-27

The [scoped activity-evidence receipt](verification/2026-09-27-live-evidence.md)
records the `.10` package: one selected target's recorded region bytes, historical
PE export witness and unavailable process-local contribution are visible in static
Explorer and React Explorer/Workstation Evidence. Source digests are freshly checked;
target/compile acceptance is not inferred. Selection/reset races, malformed siblings
and receipt-link scope were corrected after independent review. Eight backend checks
pass in source and installed package; 12 frontend checks, TypeScript and locked
production build pass. Serving activation and live browser qualification remain open.

## Effective-scenario operation identity — 2026-09-27

The [effective-scenario admission receipt](verification/2026-09-27-effective-scenario-admission.md)
records the first G3 subincrement in KotorPhasor. A generated-operation scenario now
pins its operation ID plus exact contract, target, deployed-script, fixture and runtime
digests; invalid, incomplete or noncanonical declarations are refused and the pin is
retained in `report.json`. Before `GameSession` construction, the CLI requires and
compares an operation-contract and generated hook pack. Explicit staged
script/fixture/runtime bytes are rechecked under staging. A canonical operation manifest
then holds a stable stage lock and creates a prepared lease before any staged-game mutation.
Owned, stale, malformed and quarantined predecessor records reject successor admission;
rejection cleanup cannot disturb a foreign game/session, and only the exact lease written
by the current session can be transitioned during teardown. The receipt records the terminal offline suite and exact
source hashes. Actual game/process ownership reconciliation and a live mutation receipt
remain open, and no game/harness scenario ran. This is partial G3 preparation, not M1
acceptance.

## Generated native-operation contract — 2026-09-27

The [generated-operation receipt](verification/2026-09-27-generated-operation-contract.md)
records the `.11` package and paired KotorPhasor parser/runtime increment. A
model-scale operation can now be exported only after raw-image digest and byte-bound
adapter-role checks; the runtime reader preserves selected pack identity and adapter
keys, and the native model adapter consumes the admitted generated role addresses.
The compiled profile still separately supplies its ABI/layout guards. No ABI call,
game/harness scenario, actor/world lifetime check, independent observation or
restoration ran. This is M2 preparation, not M1/M2 acceptance.

## Preparation admission accounting — 2026-09-27

The [preparation freshness and admission display](verification/2026-09-27-live-projection.md)
adds admission spending/uncertainty and retained-state freshness to static and React
views, rejects malformed/error snapshots and serializes static polling. Twelve focused
checks, TypeScript and an isolated production build passed after independent review.
The asset bundle is prepared with hashes; serving activation and live browser acceptance
remain open. This is partial delivery of the current usable live track.

The [objective admission receipt](verification/2026-09-27-objective-admission-accounting.md) records
durable preparation spending, explicit allocation revision and crash-boundary checks.
79 tests pass against source and installed wheel. This is partial P1.1 delivery;
nested provider spending and live consumer qualification remain open.

## Autonomous foundation implementation — 2026-09-22

The [observed source-contribution increment](verification/2026-09-27-source-contribution.md)
now traces a supported native compiler's COFF bytes through actual PE placement and
independent final-writer evaluation. Discarded/overwritten candidates earn zero credit,
and selected-function counters require exact database/binary/address/size binding.
The `.9` installed suite passed 149 tests after independent review; its wheel includes
the locked live-projection assets. This is a bounded relocation-free backend with
process-local trust. General linking, durable re-admission, game-target acceptance and
serving activation remain open.

The subsequent explicit build request authorizes product changes following the
[autonomous capability roadmap](plans/2026-09-22-autonomous-capability-product-roadmap.md).
Durable supervisor admission, preparation retry preservation, and content-based
verification reuse are implemented in existing paths. CLI/catalog controls and both
preparation views expose the changes. The [implementation receipt](verification/2026-09-22-autonomy-foundation.md)
records the exact software checks, package and remaining boundaries. This supersedes
the earlier design-only execution scope for these changes; it does not turn future
M1–M7 roadmap features or live recovery into delivered outcomes.

No server was listening on 8080 at source preflight. No service was launched or
replaced. Built packages have not been installed into a serving recovery process.

The next [quarantine and external-report increment](verification/2026-09-22-quarantine-and-provider-reports.md)
adds durable catalog resource reservations and unknown remote-outcome propagation,
with 126 focused checks passing against source and the installed development wheel.
Real pinned external-tool canaries now have separate receipts. Broader adapter,
reconciliation and native acceptance remain open in the session audit.

The [committed-release reconciliation/cache-export increment](verification/2026-09-22-reconciliation-and-cache-package.md)
adds qualified stale-reservation repair and a cached-evidence ReAgent input adapter.
The combined source and installed-wheel checks each passed 153 cases. Actual existing
cached evidence was consumed by pinned ReAgent, retaining unknown binary identity
and missing context. General uncertain-owner reconciliation and scientific acceptance
remain open. On 2026-09-26, the packaged wheel digest and all 15 recorded source members
were rechecked against current files without drift; all 110 obligations remain tracked.
There is still no 8080 listener, and no replacement service was started.

The [current-source binding increment](verification/2026-09-26-current-source-binding.md)
updates actual local-comparison producers, collection and ingestion so stale/name-only
coverage cannot certify edited source. 51 regression cases pass against source and
installed wheel. This is partial P0.4 delivery; semantic identity, linked contribution
and general downstream invalidation remain open.

The [database-consumer freshness increment](verification/2026-09-26-recovered-source-freshness.md)
persists nullable producer source digests and rechecks them in covered work-selection
and packaging paths. Restoration emits reused/unverified observations. 84 tests passed
against both source and installed development wheel on 2026-09-27. Full acceptance
and comprehensive downstream invalidation remain open.

The [target-local queue correction](verification/2026-09-27-target-local-recovery-selection.md)
prevents current donor source from automatically suppressing recipient work by logical
ID, and validates existing local source before already-successful counting. 87 tests
pass against source and installed wheel. Full recipient acceptance remains open.

The [target snapshot increment](verification/2026-09-27-target-snapshot-provenance.md)
records captured whole-image and region digests in the three local-comparison producers.
Cache entries no longer collide across roots sharing a slug. Seed-result reuse requires
matching image/region/source bindings. 100 source and installed-wheel tests pass; current
target-file verification and compiler closure remain open.

The [target-consistency ingestion increment](verification/2026-09-27-target-consistency-gates.md)
checks image/region content before promotion and rejects contradictory aliases. Seed
raw equality no longer accepts prefixes or normalized-only matches. 129 tests pass in
source and installed-wheel runs; intended-build identity and VA mapping remain unverified.

The [seed compile-input increment](verification/2026-09-27-seed-compile-input-basis.md)
requires a matching complete declared compiler/context/verifier basis for positive reuse.
Configured audit tests demonstrate reuse and invalidation; 140 tests pass against source
and installed wheel. Automatic dependency discovery and real compiler-profile qualification
remain open.

The [raw local-observation increment](verification/2026-09-27-raw-local-observations.md)
keeps ordinary artifacts raw, confines masked comparisons to diagnostics, and withdraws
owned positives after cache loss or dependency invalidation. Restoration republishes only
after the dependency is valid again. Its 67 focused cases pass against source and the
installed development wheel. This does not establish independent function identity or
linked-source contribution.

The [target-embedded PE export-identity increment](verification/2026-09-27-target-pe-export-identity.md)
adds a bounded independent witness for supported PE32/PE32+ named exports. It binds the
captured image, exact case-sensitive name, VA and raw region through ingestion, storage,
reporting and packaging. A false name over another export's identical bytes remains local
only. Its 124 focused cases pass against source and the installed development wheel after
independent review. Non-export identity, current-at-consumption checks, linked-source
contribution and whole-image acceptance remain open.

## Recovery design revision — 2026-09-22

The [design package](plans/2026-09-22-design-package.md) integrates the architecture
and hindsight reviews into recovery, task/acceptance, runtime and external-tool
contracts with synchronized editable diagrams. Completion here means document
coverage, mechanism consistency, explicit future falsifiers and independent design
review. It does not mean product code, adapters, recovered outputs or runtime proof.

The earlier out-of-scope requirements declaration is now a
[documentary integration proposal](plans/2026-09-22-external-validation-design.md).
At that design-only stage, no installation or runtime demonstration was performed.
The later authorized implementation increments above supersede that stage for their
explicitly recorded checks. They do not establish live recovery or game-runtime
acceptance. Existing implementation evidence below retains its original date and scope.

The [failure prevention and recovery refinement](plans/2026-09-22-failure-prevention-and-recovery-contracts.md)
extends this design with explicit responses for the historical incidents and
failures of the coordinator, storage, detection and repair paths themselves. The
resilience diagram and UI failure-state contract are design artifacts. Their
presence does not establish deployed self-healing or measured optimality.

## Evidence boundary

Completed in documentation only:

- The current correction is explicit: deliver both a complete static HTML/CSS/JS
  alternative on8080 and an optional full Vite application (default5174 and
  packageable at `/react/`) over shared backend/state semantics.
- Recovery operations remain exclusively on the existing8080 service. No new
  server, port, recovery scheduler or state owner is authorized.
- The consolidated F01-F28 scope, conflicts/supersessions, acceptance scenarios,
  and archive/source limitations are recorded in `FRONTEND_INTENT.md`.

Observed by bounded source review, but not runtime-accepted:

- The inspected runtime routes static `/dashboard` separately from packaged
  `/react/`; packaged assets existed when inspected. Presence is not execution,
  currency or parity proof.
- The delivery investigation found different runtime and isolated roots. Commit
  `7b3ff60` now mounts WorkstationApp in the isolated source and reconciles its
  missing native dependencies. Task1 parameter storage (`a6bbe36`) has source
  review approval. Task2 and its stale-navigation/hidden-editor lifecycle fixes
  are source-reviewed at `275d50a`; neither React task is deployed or accepted
  in the browser. App/AtlasApp are not mounted by the reconciled entry.

Verified bounded delivery, not whole-workstation acceptance:

- The static job-activity correction in `275d50a` was selectively activated on
  NVMe. A Playwright reload retained the exact K1 selection, kept the duplicate
  Functions widget absent, and no longer announced historical completions.
  Only measured work totals produce determinate progress. The served asset was
  inspected after polling; server PID616810 and existing job50f7fc81e7ab remained
  unchanged. Two session-state PUTs occurred; no recovery POST was observed.
- Standalone hot-reload package `inplace-hotreload` exists independently under
  `/home/brunner56/inplace-hotreload`; its `0.1.0` wheel SHA256 is
  `6e65fbacd1bed118b2118dc6a4a2485049c7175aa12da3b82b55837e5185abca`.
  Installed metadata and the live in-process engine were inspected. This does
  not promise migration of active frames, native code or incompatible class
  layouts, and is not a PyPI publication or fresh behavioral reload receipt.

**2026-09-28:** a process now owns 8080 again (PID observed at capture time,
in-process hot reload, NVMe runtime tree), correcting the "no process owns
8080 in this session" statement above for that date. This does not by itself
mean the 2026-09-27 match-review UI work has now been exercised in a browser;
that still needs its own dated observation. Also landed as source, uncommitted
at the time of that observation: add-to-project upload-staging/identity fix,
indexed shard-folder placement fix, Honest Save As, and new CLI save-as/save
commands qualified by an 11-case acceptance matrix (all pass) including a real
reversing-tool open of the converted 32-program project; receipt:
`cli-qualification/save-as-20260928/ACCEPTANCE.md` (machine-local). No package
or installed-artifact evidence exists for any of this yet.

Still open: end-to-end parity, the current max-C ZIP, runtime-reuse proof,
distributed worker flow, optional Vite runtime acceptance, and fresh whole-image
recovery proof. The historical `k1gog_byteaccurate_build.zip` is not a current
max-C source archive. Existing compiler-owned source must reach a safe snapshot
boundary before export; cancel is not pause.

Runtime update after that observation: server616810 disappeared for an unknown
reason, while compiler701843 survived. After checking startup had no eligible
preparation/batch/inventory work, the exact NVMe server was restored as1102130;
Playwright confirmed healthy and the same selected K1 corpus. Existing history
projection observes the surviving process as running but non-cancellable. It is
not a reattached controllable job, and its retained log is not fresh progress.
No overlapping recovery was submitted. Durable child-output/ownership and
resource admission remain an explicit closeout item, not a reason to overwrite
the live compiler or fabricate completion.

## Actionable delivery checklist

These IDs track delivery dependencies, not recovery priorities. STRATEGY remains
the sole recovery ordering authority; this is not another priority-zero gate.

| ID | Delivery action | Evidence required to close |
|---|---|---|
| Delivery 0 | Reconcile executing, canonical and isolated source/build identities; preserve live owners and durable state. | File/revision/loaded-module and process-owner receipt; reviewed selective-transfer list. |
| Delivery 1 | Keep `/dashboard` complete as the static alternative; reconcile the optional Vite root around WorkstationApp without App/AtlasApp auto-prepare behavior. **2026-09-28: superseded.** Per the 2026-09-28 directive, "reconcile the optional Vite root around WorkstationApp" is superseded: Vite is not reconciled around the static surface's app root but built as a fundamentally different real-time workstation; static instead reconciles toward the Ghidra-guide CodeBrowser layout (7-slice spec). | Source review plus explicit proof that selecting/browsing cannot admit recovery. |
| Delivery 2 | Unify project/logical-entity/concrete-build selection, navigation, compatibility links and stale-response rejection across both alternatives. | Real reload/back/forward/deep-link/target-switch interactions with preserved identity and no duplicate work. |
| Delivery 3 | Deliver the corpus-first Code Browser, Compare, Recovery and Evidence workflows, all guide/KotORXID inventory rows, and genuine target-bound editing. | Requirement-to-live-evidence matrix; unsupported backend gaps named rather than represented by inert controls. |
| Delivery 4 | Connect one backend-owned start/pause/resume flow and evidence-bound actual-work events; remove routine manual stage launch controls. | Owner transitions, safe pause/resume, reconnect/failover and inspected entity/diff/event evidence; no fabricated progress. |
| Delivery 5 | Package and activate safely without replacing live state: static8080 independently useful, packaged `/react/` current, optional standalone5174 validated only when separately authorized. | Installed-artifact hashes/revision, atomic asset handoff, desktop/narrow real interactions for each claimed mode, and shared-state parity. |
| Delivery 6 | Close broader requested outcomes: durable project import/merge/export, max-C and byte-accurate variants, runtime reuse, distributed contribution, collaboration/CI, hot-reload packaging and reporting integrations. | Outcome-specific live/artifact receipts; current authorization for any external post or publication. |
| Delivery 7 | Claim a recovered build only after current STRATEGY terminal acceptance. | Fresh complete source/toolchain build, object evidence, exact-placement relink and whole-file comparison for that exact build/variant. |

## Source traceability limits

`FRONTEND_INTENT.md` defines every shorthand key it uses (D1-D2, H1-H3,
C1-C9, P1, A1 and R14). Both H3 source locators were subsequently resolved and
their duplicated originating request is explicitly identified. The coverage
section records bounded scans, giant-record and missing pasted-text gaps.
Treat those remaining gaps as open provenance work, not unnamed
evidence or proof that all prior conversations were exhausted. New recovered
requirements must be added to the consolidated ledger with an explicit source
and supersession decision; do not create another competing intent document.
