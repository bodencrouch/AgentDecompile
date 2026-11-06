#!/usr/bin/env python3
"""Author design artifacts only; no pipeline execution or runtime checks."""
from pathlib import Path
from html import escape
W,H=1800,1510
out=['<!--SEC:Canvas--> ',f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
def rect(x,y,w,h,fill='#20232a',stroke='#495364'):
 out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}"/>')
def text(x,y,s,size=17,color='#d8dbe0',bold=False):
 out.append(f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" font-size="{size}" fill="{color}" font-weight="{"bold" if bold else "normal"}">{escape(s)}</text>')
def box(x,y,w,h,title,rows,color='#8cbaff'):
 rect(x,y,w,h); text(x+16,y+29,title,20,color,True)
 for i,row in enumerate(rows): text(x+16,y+60+i*25,row)
def arrow(x1,y1,x2,y2,color='#8cbaff'):
 out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="3"/>')
 if x1==x2: points=f'{x2},{y2} {x2-6},{y2-11} {x2+6},{y2-11}'
 else: points=f'{x2},{y2} {x2-11},{y2-6} {x2-11},{y2+6}'
 out.append(f'<polygon points="{points}" fill="{color}"/>')
rect(0,0,W,H,'#16181c','#16181c')
text(35,43,'Execution and evidence contracts',32,'#f2f4f7',True)
text(35,76,'Design specification · companion to the recovery overview · future software acceptance checks NOT RUN',18,'#f0c060')
text(35,107,'Missing evidence blocks its claim. An unhealthy resource blocks its dependents. Ready independent work continues.',18)
out.append('<!--SEC:Task and acceptance contract-->')
box(35,135,550,240,'1 · Declare one task contract',[
'Immutable input manifest + dependency versions',
'Claim or capability requested; required evidence',
'Provider alternatives; prerequisite-producing tasks',
'Mutable resource set; process-tree resource budget',
'Progress units; outputs; deadline; retry owner/budget',
'Capability priority + capped aging / reservations'])
box(625,135,550,240,'2 · Admit one eligible attempt',[
'Complete input closure on healthy working storage',
'Capacity reserve + pressure + storage + limit events',
'Acquire entire resource set atomically or release',
'Current ownership generation + private outputs',
'Share nested build budget; external jobs not adopted',
'No provider: record exact dependency/wake condition'])
box(1215,135,550,240,'3 · Compute outside commit',[
'Stable analysis snapshot; immutable proposals',
'Durable completed-unit receipts, including negatives',
'Liveness ≠ execution progress ≠ goal progress',
'Uninstrumented external worker: progress unknown',
'No corpus transaction during compiler / model / game',
'Stage, validate, flush, rename BEFORE DB commit'])
arrow(585,255,625,255);arrow(1175,255,1215,255)
out.append('<!--SEC:Independent binding evidence-->')
text(35,423,'Runtime use requires presence, identity and operation evidence',24,'#f2f4f7',True)
box(35,445,550,205,'BYTES · Are these bytes here?',[
'Exact target digest + image/address mapping',
'Observed region and independent byte comparison',
'Receipt names region, input basis and verifier',
'Does not establish the selected function name'], '#7fd6a4')
box(625,445,550,205,'IDENTITY · Is this the intended entity?',[
'Target-side boundaries and discriminating evidence',
'Donor labels remain hypotheses until accepted',
'Signature from selected RVA cannot prove its label',
'Withdraw bad seed → invalidate dependent claims'], '#f0c060')
box(1215,445,550,205,'OPERATION · Is this use supported?',[
'ABI + layout + runtime state + policy requirements',
'Located / readable / callable / detourable / writable',
'Object lifetime and dynamic-root resolution recipe',
'Hook install AND removal; reclaim only when safe'], '#67d3d0')
out.append('<!--SEC:Acceptance and readiness fork-->')
box(35,710,550,215,'4 · Independent acceptance, short commit',[
'Verifier checks exact claimed level and raw evidence',
'Check input versions AND current generation',
'Commit manifest + ledger; no artifact IO here',
'Task complete only when required predicates pass',
'Producers cannot self-promote or change criteria'], '#c9a4f0')
box(625,710,550,215,'5A · Original-code capability',[
'Original implementation may remain assembly floor',
'Accept only operation-specific prerequisites',
'Scenario: build + fixture + driver + postconditions',
'Oracle and recording share one scenario attempt',
'Unknown command outcome → inspect before replay'], '#67d3d0')
box(1215,710,550,215,'5B · Recovered-source capability',[
'Recovery / compilation / comparison units may differ',
'Validated fixups + metadata + unchanged round trip',
'Compile ≠ local match ≠ linked match ≠ full equality',
'Prove replacement contributes; fallback is separate',
'C+assembly-floor and max-C have separate ledgers'], '#7fd6a4')

text(45,690,'All applicable proof receipts → acceptance (4) → original-code (5A) and recovered-source (5B) independently.',16,'#98a0ad')

text(1181,946,'Separate outputs, never an implied readiness ladder',16,'#98a0ad')
out.append('<!--SEC:Failure containment and continuation-->')
box(35,980,550,235,'FENCE · Reject obsolete publication',[
'Old generation or changed inputs → historical only',
'Keep artifact; refuse current acceptance/promotion',
'Re-key only affected dependency descendants',
'Collision discovery may reduce accepted coverage',
'Fencing does NOT prove a worker has stopped',
'Representation totals disjoint; capabilities overlap'], '#ef968b')
box(625,980,550,235,'QUARANTINE · Keep resources occupied',[
'Expired lease / timeout ≠ safe resource release',
'Late or kernel-blocked worker may still access state',
'Release needs corroborated end of access + owner',
'Atomic local locks; PID identity alone is insufficient',
'Private replacement only on disjoint safe resources',
'Bound isolated storage probes; never block scheduler'], '#ef968b')
box(1215,980,550,235,'CONTINUE · Only ready independent work',[
'Transient failure: one owner, bounded durable retry',
'Deterministic negative: changed hypothesis required',
'Provider circuit break; split task or compatible route',
'No ready work: persist dependency sets + wake event',
'Complete remote replica + worker needed for host loss',
'New user message does not reset retry budget'], '#f0c060')
out.append('<!--SEC:Design challenge and future evidence-->')
rect(35,1250,1730,215)
text(52,1282,'Concrete design challenge · the late worker',23,'#f2f4f7',True)
text(52,1316,'Attempt A loses its lease while still writing. B runs on disjoint resources. A later submits a byte-perfect artifact.',19)
text(52,1349,'Expected: reject A’s stale publication; retain A’s resource quarantine; permit B only with complete independent inputs.',19)
text(52,1382,'Future proof: inject this race and inspect accepted-generation receipts, ownership events and B’s dependency manifest.',19)
text(52,1421,'NOT RUN. This diagram defines the acceptance mechanism; it does not claim a scheduler, binding or recovery result exists.',18,'#f0c060')
text(35,1492,'Failure lifecycle and control-plane recovery: resilience-contracts.svg · detailed future checks in the linked plan',16,'#98a0ad')
out.append('</svg>')
Path(__file__).with_name('execution-contracts.svg').write_text('\n'.join(out)+'\n')
