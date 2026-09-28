#!/usr/bin/env python3
"""Generate a design-only resilience companion. No product operations."""
from pathlib import Path
from html import escape
W,H=1800,1700
out=['<!--SEC:Canvas-->',f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
def rect(x,y,w,h,fill='#20232a',stroke='#495364'):
 out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}"/>')
def text(x,y,s,size=17,color='#d8dbe0',bold=False):
 out.append(f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" font-size="{size}" fill="{color}" font-weight="{"bold" if bold else "normal"}">{escape(s)}</text>')
def box(x,y,w,h,title,rows,color='#8cbaff'):
 rect(x,y,w,h);text(x+16,y+30,title,21,color,True)
 for i,row in enumerate(rows):text(x+16,y+63+i*26,row)
def arrow(x1,y1,x2,y2):
 out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#8cbaff" stroke-width="3"/>')
 out.append(f'<polygon points="{x2},{y2} {x2-11},{y2-6} {x2-11},{y2+6}" fill="#8cbaff"/>')
rect(0,0,W,H,'#16181c','#16181c')
text(35,43,'Prevention, containment and recovery',32,'#f2f4f7',True)
text(35,78,'DESIGN ONLY · future failure-injection checks NOT RUN · implement locally first using existing task/corpus contracts',18,'#f0c060')
text(35,109,'One durable decision owner. Recover the affected dependency; retain the objective, evidence and independent work.',18)
out.append('<!--SEC:Failure lifecycle-->')
box(35,140,550,260,'1 · Prevent, detect, classify',[
'Fixture recheck after ownership, before mutation',
'Observe process tree, unit receipts and goal facts',
'Classify: mismatch / transient / resource / policy',
'Distinguish missing evidence from unhealthy resource',
'Unknown outcome stays unknown until reconciled',
'No health decision from one noisy sample alone',
'Capture exact input, policy and observation versions'])
box(625,140,550,260,'2 · Record the decision before effects',[
'Pure reducer: frozen facts + policy → next action',
'Atomically reserve attempt budget + effect intent',
'One durable retry budget; no nested retry owners',
'Persist reason, scope, wake predicate + event cursor',
'Deterministic negative requires changed hypothesis',
'New user message does not reset attempt spending',
'Ledger unavailable → pause new managed mutations'])
box(1215,140,550,260,'3 · Repair, reroute or wait',[
'Repair only classified prerequisites with evidence',
'Reroute only to declared compatible capabilities',
'Checkpoint/split within the unchanged claim scope',
'Reconcile cursor + exact version/owner/provider wake',
'Unknown non-idempotent effect: inspect, never replay',
'Quarantine resources until end of access is proven',
'Independent work continues only if fully supplied'])
arrow(585,269,625,269);arrow(1175,269,1215,269)
out.append('<!--SEC:Acceptance and preventive feedback-->')
text(35,449,'Every recovery action returns through independent acceptance; an available process is not a repaired capability.',21,'#f2f4f7',True)
box(35,480,550,260,'4 · Accept against the current basis',[
'Inspect new artifact and claim-specific proof roots',
'Recheck dependencies, generation and policy version',
'Prepare durable artifact outside acceptance commit',
'Short commit: manifest reference + corpus receipt',
'Required task predicates determine completion',
'Failure retains useful units without promoting claim',
'Resource release is separate from acceptance'], '#c9a4f0')
box(625,480,550,260,'5 · Resume only the justified capability',[
'Revalidate affected descendants, preserve others',
'Clear quarantine only on resource-release evidence',
'Expire old runtime preflight and reacquire live facts',
'Record liveness / unit progress / accepted progress',
'No ready work → durable wait, no repeated audit loop',
'Expose exact reason and next eligible wake condition',
'Unknown empirical results remain explicitly unknown'], '#7fd6a4')
box(1215,480,550,260,'6 · Prevent recurrence without blind tuning',[
'Aggregate failure signatures by input/policy basis',
'Propose narrow policy change with deciding metric',
'Canary uses frozen baseline and bounded population',
'Independent reviewer accepts evidence, not opinion',
'Regression → restore prior admission policy version',
'Preserve failure history; never reset spent budgets',
'Roll back policy, not arbitrary already-run effects'], '#f0c060')
arrow(585,610,625,610);arrow(1175,610,1215,610)
out.append('<!--SEC:Failure containment boundaries-->')
box(35,790,550,285,'CONTROL PLANE · Fail read-only',[
'Lost durable decision or acceptance authority:',
'pause new managed mutation/admission in that scope',
'Keep cached read-only evidence available with age',
'Old outputs stay private/quarantined until reconciled',
'Do not kill external owners or assume children stop',
'Reconcile owner/generation and durable log on return',
'Unknown command outcome → inspect before retry',
'Wake: healthy durable authority + reconciled state'], '#ef968b')
box(625,790,550,285,'DATA / PROVIDER · Isolate dependency',[
'Bound storage probes outside coordinator loop',
'One recovery probe per provider + shared retry budget',
'Complete input closure required for alternate worker',
'Partial copies never become launchable manifests',
'Tmpfs is budgeted cache, not durable rescue default',
'Host loss needs independent replica AND worker',
'Retry requires budget + safe resources + current basis',
'Wake: new verified inputs / capability / released owner'], '#ef968b')
box(1215,790,550,285,'POLICY / CANARY · Bound the change',[
'Policy is immutable versioned data; producer cannot edit',
'Canary declares baseline, population and abort rule',
'Compare acceptance errors, useful throughput and cost',
'No broader rollout from a successful process exit',
'Revert routing/admission version if metric regresses',
'Reassess active attempts under their recorded policy',
'Accept only with pinned/current policy compatibility',
'Wake: accepted policy version or corrected evidence'], '#f0c060')
out.append('<!--SEC:Distributed compute failure classes-->')
box(35,1115,1730,210,'Distributed compute · failure classes and their containment',[
'Hot key starves the shared object store → split heads, batch records, full-jitter backoff, rotate after 8 failures (H7)',
'Verification funnel livelocks → cap 4 proposals per task; verify before generating more (H8)',
'Analysis slice never converges → per-binary slice cap; mark task-poison and pin the last packed program (H10)',
'View applier lags → named view-stale state with an age bound; readers use pinned objects past it (H11)',
'Operator liveness → fleet keys sign invites, extend revocation, mirror objects, run appliers; no single laptop on a liveness path (H13)'], '#8cbaff')
out.append('<!--SEC:Worked interruption and evidence boundary-->')
rect(35,1355,1730,285)
text(52,1390,'Worked interruption · the command was sent, then the decision store disappeared',23,'#f2f4f7',True)
text(52,1429,'Observe: command ID C may have changed the game; the connection closed before its result was durably recorded.',19)
text(52,1464,'Contain: pause new managed mutations in this scope; preserve read-only status and existing evidence; do not replay C.',19)
text(52,1499,'Recover: reconcile C against observed engine state and ownership. Resume only after durable authority and state agree.',19)
text(52,1534,'Future proof: inject disconnect; show no blind duplicate dispatch, retained unknown outcome, reconciliation and scoped resumption.',19)
text(52,1569,'If the effect cannot be determined, keep the affected operation waiting and expose the exact required observation.',19)
text(52,1611,'NOT RUN · design acceptance is artifact consistency; runtime recovery needs the future measurements specified in the plan.',18,'#f0c060')
out.append('</svg>')
Path(__file__).with_name('resilience-contracts.svg').write_text('\n'.join(out)+'\n')
