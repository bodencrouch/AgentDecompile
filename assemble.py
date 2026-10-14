from pathlib import Path
import json,re,hashlib,xml.etree.ElementTree as ET
base=Path('/home/brunner56/agentdecompile-plan-consolidation'); snap=base/'sources'; repo=Path('/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile'); out=repo/'docs/plans'
meta=json.loads((base/'sources.json').read_text())
for i,m in enumerate(meta,1):m['sid']=f'S{i:03}'
by_path={m['path']:m for m in meta}
def fence(s,lang='text'):
 n=max([len(x) for x in re.findall(r'`+',s)]+[2])+1
 return '`'*n+lang+'\n'+s.rstrip('\n')+'\n'+'`'*n+'\n'
def clean(s):return s.replace('|','\\|').replace('\n',' ').strip()
units=[]
for filename,pattern,end in [('synthesis.md',r'^### (W\d+) [—-] (.+)$','## Dependency'),('frontend-synthesis.md',r'^### ((?:FE|EX|BE|DX)\d+) (.+)$','## Required global')]:
 text=(base/filename).read_text(); matches=list(re.finditer(pattern,text,re.M))
 for k,m in enumerate(matches):
  stop=matches[k+1].start() if k+1<len(matches) else text.find(end,m.end())
  body=text[m.end():stop if stop>=0 else len(text)].strip()
  units.append(dict(id=f'U{len(units)+1}',old=m[1],title=m[2],body=body))
mp=(snap/'docs/research/swkotor-multiplayer/README.md').read_text()
seq=mp.split('## Required implementation sequence\n')[1].split('## Directory metadata contract')[0]
for m in re.finditer(r'(?ms)^([1-7])\. \*\*(.+?)\*\* (.*?)(?=^\d\. \*\*|\Z)',seq):units.append(dict(id=f'U{len(units)+1}',old='MP'+m[1],title=m[2].strip('.'),body=m[3].strip()))
extra=[('Semantic findings and extensibility','Make Atlas/semantic rule, capability and match hierarchies navigable to exact code locations with static/dynamic evidence separated. Retain language/engine extension seams and provider-unavailable states. Connect F01–F28 and the donor/guide inventory to real shared backend operations. Acceptance: each inventory workflow has a reachable action or explicit scoped missing prerequisite; a semantic finding resolves to the selected program and evidence rather than a fabricated universal claim.'),('Collaboration, CI and controlled reporting','Preserve linkable analysis, durable workspace sharing, CI consumers, plugin/docs/code consolidation, and explicitly authorized report integrations including historical Discord reporting. Use bounded redacted payloads and retained evidence basis. External publication and messaging require current authorization. Acceptance: a second qualified reader/CI consumer resolves the same artifact basis, revoked access refuses, and local report generation does not transmit data.'),('Packaging, standalone reload and final integration','Reconcile source and package manifests, standalone in-process reload, asset version retention and documentation across the canonical and implementation worktrees without overwriting owner changes. Validate the actual consumer on unchanged process/state identities when authorized. Acceptance: rejected edit leaves the serving state intact, stale chunks remain retrievable during atomic index rollout, installed files match the selected revision, and both complete interfaces satisfy their scenario matrices.')]
for j,(title,body) in enumerate(extra,1):units.append(dict(id=f'U{len(units)+1}',old='INT'+str(j),title=title,body=body))
uid={u['old']:u['id'] for u in units}
# Integration ownership is explicit by source family; multiple owners are deliberately retained for cross-cutting clauses.
def owners(path):
 p=path.lower()
 if 'swkotor-multiplayer' in p:return [u['id'] for u in units if u['old'].startswith('MP')]
 if 'forgiving-input' in p:return [uid['BE02']]
 if 'program-info' in p:return [uid['BE01']]
 if 'browser-rewrite' in p:return [uid['DX01']]
 if 'exchange-' in p:return [uid['DX02'],uid['DX01']]
 if 'distributed' in p or 'grid-of-one' in p or 'donated-compute' in p:return [uid['W11'],uid['W09'],uid['DX01'],uid['DX02']]
 if 'autonomous' in p:return [uid['W12'],uid['W09']]
 if any(x in p for x in ['failure-prevention','task-acceptance','acceptance-and-budget','resilience','execution-contracts']):return [uid['W09'],uid['W01']]
 if 'external-validation' in p or 'external-execution' in p:return [uid['W10'],uid['W04']]
 if 'ghidra-guide' in p:return [uid['FE04'],uid['FE03'],uid['BE01']]
 if 'kotorxid-capability' in p:return [uid['FE05'],uid['FE06'],uid['FE09']]
 if 'export_scope' in p:return [uid['EX06'],uid['W12']]
 if any(x in p for x in ['front','workstation','wb-control','delivery-reconciliation','product_and']):return [u['id'] for u in units if u['old'].startswith(('FE','EX','INT'))]
 if 'runtime_reuse' in p:return [uid['W05'],uid['W06'],uid['W07'],uid['W08'],uid['W12']]
 return [u['id'] for u in units if u['old'].startswith('W')]+[uid['FE08'],uid['INT1'],uid['INT2']]
# Exact source spans: each non-binary source is partitioned without dropping lines.
clauses=[]
for m in meta:
 p=m['path']; file=snap/p
 if p.endswith('.png'):
  clauses.append(dict(key=m['sid']+'-C0001',sid=m['sid'],path=p,start=0,end=0,title='Visual rendition; compare editable companion',body='',owners=owners(p),kind='rendition'))
  continue
 text=file.read_text(); lines=text.splitlines(keepends=True)
 starts=[0]
 if p.endswith('.md'):
  inside=False
  for i,l in enumerate(lines):
   if re.match(r'^\s*(`{3,}|~{3,})',l):inside=not inside
   if i and not inside and re.match(r'^#{1,6} ',l):starts.append(i)
 starts=sorted(set(starts)); starts.append(len(lines))
 for n,(a,b) in enumerate(zip(starts,starts[1:]),1):
  if a==b:continue
  body=''.join(lines[a:b]); title=next((l.strip().lstrip('# ').strip() for l in lines[a:b] if l.strip()),p)
  if len(title)>170:title=title[:167]+'...'
  clauses.append(dict(key=f"{m['sid']}-C{n:04}",sid=m['sid'],path=p,start=a+1,end=b,title=title,body=body,owners=owners(p),kind='source'))
# Diagram text and cells receive element-level source keys; topology and geometry stay in retained XML.
for m in meta:
 if not m['path'].endswith(('.svg','.drawio')):continue
 root=ET.fromstring((snap/m['path']).read_text()); n=0
 for elem in root.iter():
  tag=elem.tag.rsplit('}',1)[-1]
  if tag not in ('text','mxCell'):continue
  if tag=='mxCell' and not elem.attrib.get('value') and not elem.attrib.get('edge'):continue
  n+=1
  label=''.join(elem.itertext()).strip() if tag=='text' else elem.attrib.get('value') or ('Edge '+elem.attrib.get('source','?')+' -> '+elem.attrib.get('target','?'))
  clauses.append(dict(key=f"{m['sid']}-E{n:04}",sid=m['sid'],path=m['path'],start=0,end=0,title=label,body=ET.tostring(elem,encoding='unicode'),owners=owners(m['path']),kind='diagram-element'))
# One accountable coverage owner per clause. Cross-cutting material belongs to final integration,
# never to every prerequisite unit. Specific acceptance remains on the relevant named child/unit.
def primary(c):
 p=c['path'].lower(); t=c['title'].lower(); b=c['body'].lower()
 if 'swkotor-multiplayer' in p:
  if 'directory' in t or 'lobby-research' in p:return uid['MP5']
  if 'gameplay scope' in t:return uid['MP3']
  if 'source baseline' in t or 'binding' in p or 'engine-evidence' in p:return uid['MP1']
  if any(x in p for x in ['disassembly','send-callers','netlayer','send-message','sendmessagetoplayer','nwn-evidence']):return uid['MP2']
  return uid['MP7']
 if c['kind']=='diagram-element':
  for terms,key in [(['quarantine','fence','attempt','lease','retry','wake','budget','ownership','control plane','recovery action'],'W09'),(['distributed','worker','fleet','grid','compute'],'W11'),(['lua','header','export','hookpack','readiness report','divergence report'],'W08'),(['runtime','callable','detour','preflight','hook install','cave'],'W06'),(['identity','logical','name precedence','types & layouts'],'W03'),(['compil','parity','whole-image','recovered-source','source recovery','reconstruction'],'W04'),(['m0','m1','m2','m3','m4','m5','m6','m7','scenario','f12','creative','checkpoint','native host','whole-game'],'W12')]:
   if any(x in t for x in terms):return uid[key]
  return uid['INT3']
 if c['kind']=='rendition':return uid['INT3']
 if 'guide-capability' in p:return uid['FE04']
 if 'kotorxid-capability' in p:return uid['FE05']
 if 'program-info' in p:return uid['BE01']
 if 'forgiving-input' in p:return uid['BE02']
 if 'browser-rewrite' in p:return uid['DX01']
 if 'exchange-' in p:return uid['DX02']
 if any(x in p for x in ['distributed','grid-of-one','donated-compute']):return uid['W11']
 if 'autonomous' in p:return uid['W12']
 if any(x in p for x in ['failure-prevention','task-acceptance','acceptance-and-budget','resilience','execution-contract']):return uid['W09']
 if 'external-validation' in p or 'external-execution' in p:return uid['W10']
 if 'runtime_reuse' in p:return uid['W06']
 if 'export_scope' in p:return uid['EX06']
 if c['path'].startswith('worktree/docs/plans/'):
  m=re.match(r'u(\d+)\.',t)
  if m and int(m[1]) in fowner:return uid[fowner[int(m[1])]]
 for terms,key in [(['abi','storage','struct field'],'EX01'),(['hook pack','hookpack','hook-pack'],'EX02'),(['cave','injection'],'EX03'),(['lua binding','per-build header'],'EX04'),(['divergence','readiness'],'EX05'),(['export artifact','export bundle','export listing'],'EX06'),(['match evidence','bsim','matching','cross-build','cross-match'],'FE06'),(['project','admission','tab context'],'FE02'),(['navigation','selection','accessib','chrome','dialogs'],'FE03'),(['codebrowser','code browser','guide','listing','decompile view','function editor'],'FE04'),(['metric','percentage','progress bar','count','publication'],'FE09'),(['optional ai','llm','configuration'],'FE10')]:
  if any(x in t for x in terms):return uid[key]
 if 'portable-signatures' in p:
  m=re.search(r'phase (\d+)',t)
  if m and int(m[1]) in phaseowner:return uid[phaseowner[int(m[1])]]
  return uid['W01']
 if any(x in p for x in ['front','workstation','wb-control','delivery-reconciliation','product_and']):return uid['INT3']
 if 'recovery-contracts' in p:return uid['W04']
 return uid['W01']

# Named obligations retain full record and acceptance, not a flattened description.
oblig=[]
portable=json.loads((snap/'docs/plans/2026-09-27-weekend-unit-delivery.json').read_text())
phaseowner={0:'W02',1:'W05',2:'W05',3:'W06',4:'W06',5:'W03',6:'W06',7:'W06',8:'W05',9:'W05',10:'W02',11:'W06',12:'W08',13:'W07',14:'FE08',15:'W11'}
for r in portable['records']:
 phase=r['source']['phase']; o=uid[phaseowner[int(phase)]]
 title=r['definition']['text'].splitlines()[0]
 oblig.append(dict(key=r['key'],title=title,owner=o,disposition=r['requirementStatus'],historical=r.get('delivery',{}),record=r,source='docs/plans/2026-09-27-weekend-unit-delivery.json'))
contracts=json.loads((snap/'docs/plans/2026-09-22-session-obligations.json').read_text())
for r in contracts['requirements']:
 rid=r['id']; owner=uid['W09'] if rid.startswith(('A','FP')) else uid['W01']
 oblig.append(dict(key='session-contract-2026-09-22:'+rid,title=r['requirement'],owner=owner,disposition='superseded' if r['status']=='superseded' else 'required',historical=r['status'],record=r,source='docs/plans/2026-09-22-session-obligations.json'))
fpath='worktree/docs/plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md'; ft=(snap/fpath).read_text(); fm=list(re.finditer(r'^### (U\d+)\. (.+)$',ft,re.M))
fowner={1:'FE02',2:'FE02',3:'BE01',4:'FE02',5:'FE02',6:'FE04',7:'FE02',8:'FE06',9:'FE06',10:'FE06',11:'FE06',12:'FE06',13:'FE06',14:'FE06',15:'FE10',16:'FE10',17:'FE10',18:'FE07',19:'FE07',20:'FE07',21:'FE07',22:'FE07',23:'FE08',24:'FE08',25:'FE08',26:'FE09',27:'FE09',28:'FE09',29:'FE09',30:'INT3',31:'EX01',32:'EX01',33:'EX02',34:'EX03',35:'EX04',36:'EX04',37:'EX05',38:'EX05',39:'EX06',40:'EX06',41:'EX06',42:'EX06',43:'FE09'}
for k,m in enumerate(fm):
 stop=fm[k+1].start() if k+1<len(fm) else ft.index('## Verification Contract',m.end()); body=ft[m.start():stop]
 oblig.append(dict(key='frontend-plan-2026-09-28:'+m[1],title=m[2],owner=uid[fowner[int(m[1][1:])]],disposition='required',historical='See newer frontend implementation status; source implementation is not acceptance',record={'id':m[1],'definition':body},source=fpath))
for c in clauses:
 c['owners']=[primary(c)]

# Resolve active labels without destroying historical record text.
for o in oblig:
 if o['key']=='portable-plan-2026-09-21:U65':
  o['title']='Bound analyzer lifecycle with durable progress, deadlines and checkpoint continuation (C19 replaces effectively-unbounded wording)'
  o['active_override']='C19; original unbounded wording is superseded, other unit predicates remain required.'
 if o['key']=='portable-plan-2026-09-21:U21':
  o['title']='Keep generic core defaults engine-independent while retaining named fixture, adapter and research provenance (C20)'
  o['active_override']='C20; product-name purge cannot erase named evidence or target-specific adapter data.'
# All implementation units receive requirements, real dependency gate, code seams and concrete scenarios via substantive dossier body.
reqmap={'W01':'R1–R8','W02':'R1–R3,R9–R10,R14','W03':'R2–R3,R8–R9','W04':'R4–R7','W05':'R9–R12','W06':'R12–R13','W07':'R11–R13','W08':'R14–R15','W09':'R16–R20,R31','W10':'R4–R6,R17','W11':'R21–R22','W12':'R31–R34'}
seams={'W01':'src/agentdecompile_recovery/corpus/ ingest, ledger, packaging and parity consumers','W02':'src/agentdecompile_recovery/corpus/ schema, migrations, logical and basis modules','W03':'src/agentdecompile_recovery/corpus/ identity, match_store, propagation and recipient acceptance','W04':'src/agentdecompile_recovery/ compiler, reconstruction, collect_source and finish_binary paths','W05':'src/agentdecompile_recovery/corpus/ entity, signature, layout, ABI and decoder providers','W06':'Corpus runtime export interfaces and qualified KotorPhasor consumer adapters','W07':'Corpus resolver and learn-build adapters; ordered member receipts','W08':'src/agentdecompile_recovery/corpus/ export modules and recovered-project packaging','W09':'src/agentdecompile_recovery/corpus/dashboard/ preparation, continuation, action and ownership boundaries','W10':'src/agentdecompile_recovery/corpus/external_execution.py and recovered-project recipe adapters','W11':'agentdecompile_grid package, exchange and corpus task-kind adapters','W12':'Shared capability catalog, scenario manifests and KotorPhasor operation/UI/harness adapters'}
deps={'W01':[],'W02':['W01'],'W03':['W01','W02'],'W04':['W01','W02'],'W05':['W02','W03'],'W06':['W05','W09'],'W07':['W05','W06'],'W08':['W05','W07'],'W09':['W01'],'W10':['W01','W04','W09'],'W11':['W01','W09'],'W12':['W06','W09'],'FE01':[],'FE02':['FE01','BE01','W09'],'FE03':['FE01'],'FE04':['FE03','BE01'],'FE05':['FE03','W01'],'FE06':['FE03','W03'],'FE07':['FE03','W04'],'FE08':['FE03','W09'],'FE09':['FE05','W01'],'FE10':['FE02','W09'],'EX01':['W05'],'EX02':['EX01','W02'],'EX03':['W05'],'EX04':['EX01','EX02'],'EX05':['W03','EX02'],'EX06':['EX02','EX03','EX04','EX05'],'BE01':['FE01'],'BE02':['FE01'],'DX01':['W11'],'DX02':['W09'],'MP1':['W04'],'MP2':['MP1'],'MP3':['MP2','W09'],'MP4':['MP3'],'MP5':['MP3'],'MP6':['MP3','MP5'],'MP7':['MP4','MP6'],'INT1':['FE04','FE05'],'INT2':['W01','FE01'],'INT3':['FE01']}
core=(base/'core.md').read_text()
# Source corrections added to the governing decision table before assumptions.
more='''| C19 | Analyzer lifetime is effectively unbounded | Portable U65 yields to bounded progress/deadline/checkpoint and containment contracts; legitimate long work renews through evidence |
| C20 | Genericity requires deleting named research | Generic defaults remain engine-independent; fixtures, adapters, user intent and provenance keep their real names |
| C21 | Recovery Start ban removes contribution consent | Browser contribution retains explicit opt-in Start; normal recovery has no pipeline Start controls |
| C22 | All old completed input work must be reimplemented | Preserve and reconcile the 13 forgiving-input tasks and their implementation before adding missing acceptance |
| C23 | Grid role alone qualifies computation | Capability canaries qualify worker lanes; signing/verifying/applying roles and current publication constraints remain separate |
| C24 | Runtime feedback may directly establish identity | Keep runtime claims and independent binding separate; non-discriminating evidence cannot authenticate the chosen label |

'''
core=core.replace('### Assumptions and unresolved dependencies',more+'### Assumptions and unresolved dependencies')
core=core.replace('instructions |\n\n| C19', 'instructions |\n| C19')
core=core.replace('Their source-qualified child obligations and clause ledger are part of their acceptance, not optional reading. A unit closes only when every applicable child is accepted, or explicitly withdrawn/absorbed with winning evidence.', 'Each named child has one accountable integration owner. Each source clause has one coverage owner, responsible for preserving and applying every detail through the relevant child acceptance. Clause ownership is not a prerequisite edge: cross-cutting clauses close at final integration without blocking independently accepted earlier slices. A unit closes its own acceptance predicates and assigned named children; it does not inherit unrelated downstream acceptance merely because a source section mentions it.')
core+='\n### Unit index\n\n| Unit | Deliverable | Prerequisite units | Primary implementation seam |\n|---|---|---|---|\n'
for u in units:
 d=[uid[x] for x in deps.get(u['old'],[])]; u['deps']=d
 seam=seams.get(u['old'],'Existing shared backend and static/Vite consumer modules identified in the unit; multiplayer additions belong to shared recovered-engine/runtime adapters' if u['old'].startswith('MP') else 'Existing backend/provider, static workbench and Vite modules named below; no duplicate root')
 u['seam']=seam
 core+=f"| {u['id']} | {u['title']} | {', '.join(d) or 'None; reconciliation can start read-only'} | {seam} |\n"
for u in units:
 old=u['old']; req=reqmap.get(old,'R35–R38' if old.startswith('MP') else 'R23–R30' if old.startswith(('FE','BE','INT')) else 'R14–R15' if old.startswith('EX') else 'R21–R22')
 body=u['body']
 legacy_ns='portable-plan-2026-09-21' if old.startswith('W') else 'frontend-plan-2026-09-28'
 body=re.sub(r'(?<![\w:])([UD]\d+[a-z]?)(?![\w])', lambda m: legacy_ns+':'+m[1], body)
 for before,after in uid.items():
  if before.startswith('W'):body=re.sub(r'\b'+before+r'\b',after,body)
 core+=f"\n### {u['id']}. {u['title']}\n\n- **Requirements:** {req}; assigned named obligations and applicable source details are mandatory; cross-cutting clause coverage does not add unrelated prerequisite edges.\n- **Dependencies:** {', '.join(u['deps']) or 'Read-only reconciliation may begin immediately'}. These denote consumed predicates, not a requirement to finish every unrelated child of a predecessor.\n- **Files and interfaces:** {u['seam']}. Preserve existing public routing and inspect current symbols before changes; paths in archived contracts are version-specific leads.\n- **Execution:** reconcile retained implementation and evidence first; implement the missing vertical slice, exercise the named positive and refusal cases, then integrate the real consumer and capture the required proof.\n\n{body}\n\n- **Completion:** close assigned named child obligations and unit-specific predicates against the exact input/version scope; discharge owned source-clause coverage through explicit child evidence or contextual disposition; record changed paths, verification receipts and any remaining blocked predicates in the living plan. Commit only owned, reviewed changes during a separately authorized implementation run.\n"
core+='''
## Verification Contract

No software test suite, build, game run or live service probe was performed to create this plan. Source recipes below name future verification. Admission, ownership and the then-current authorization must be satisfied before executing them.

| Gate | Required evidence | Failure behavior |
|---|---|---|
| V1 Source coverage | Every snapshot source, named obligation and source clause has a stable ID and owner; original statuses and dispositions preserved | Unmapped/missing material blocks the completeness claim |
| V2 Software behavior | Exact positive, edge, refusal and integration cases from the owning unit and inherited contract; current revision and environment recorded | Failed predicate stays open; unrelated units continue |
| V3 Determinism | Same declared basis under reordered ingest/completion produces equal canonical semantic rows and byte-identical declared exports | Name differing key/artifact; no blanket SQLite-byte identity claim |
| V4 Recovery | Actual current source contribution, target/toolchain identity, local/linked scopes, fresh requested whole-image compile/link/hash comparison | Compilation/copied floor bytes do not earn source credit |
| V5 Runtime | Presence, independent identity, live operation preflight, behavior oracle and supported restoration for exact build | Refuse affected operation; preserve evidence |
| V6 Continuation | Every A and FP paired-negative case, unaffected control, stale publication race, quarantine, unknown-effect reconciliation and budget persistence | No blind replay or reset; exact durable wake |
| V7 Frontend parity | Both real consumers exercise the complete workflow matrix; keyboard, narrow viewport, error/loading/stale/read-only states and actual backend effects | Source/component presence cannot close browser acceptance |
| V8 Export consumer | Complete immutable bundle, same-basis artifacts, actual qualified consumer and explicit unsupported records | Missing required output blocks publishing the bundle |
| V9 Distributed foundation | Actual publish/work/verify/materialize, restart/replay, bad result, revoked worker and provider failure with complete inputs | Untrusted proposals never self-accept |
| V10 Capability product | Independent game behavior, capture integrity, presentation and restoration, separately for M0–M7 and each qualified host/build | A browser shell or successful job is insufficient |
| V11 Multiplayer | Clean source builds, headless server plus two real clients, both modes, public discovery, password/refusal/reconnect and real game UI | Local queue or synthetic socket test cannot close gameplay |

Specific test names, example commands, fixtures and expected outcomes from the input documents are preserved verbatim in the obligation records and source clauses. Before a future execution, bind each recipe to the current checkout and applicable unit; do not run an obsolete command merely because it appears in the appendix. Test-first work should capture a concrete missing behavior or negative case before its minimal implementation. Documentation-only changes use read-only link, source and diff checks.

## Definition of Done

The program is complete only when every required named obligation and applicable source clause has its owning unit's acceptance evidence, with all genuine supersessions linked to their winning decision. All 193 weekend records remain accounted for, including three disposed aliases; all 110 later rows retain their independent meanings; all 43 frontend units, F01–F28, guide chapters, diagram lanes, multiplayer modes and capability milestones remain covered.

Both frontends must consume the same qualified backend behavior. Complete exported artifacts, actual runtime capabilities and recovered source each need their own receipts. Cleanup removes abandoned experimental changes without deleting useful historical evidence. Source/installed/live status, host qualification and authorized publication are independently reported. A plan coverage count, test count or source commit never satisfies product completion.

## Source-qualified obligation register

IDs below are preserved namespaces, not aliases for this plan's U numbers. The owner is responsible for integration and gathering any additional producers/consumers identified in the full record. Required child obligations stay open until current applicable acceptance is established. Withdrawn/absorbed/superseded rows remain visible without becoming fabricated implementation work.

'''
for o in oblig:
 core+=f"### {o['key']}\n\n**Owner:** {o['owner']}. **Requirement disposition:** {o['disposition']}. **Original source:** `{o['source']}`.\n\n{clean(o['title'])}\n\n**Active interpretation:** {o.get('active_override', 'Apply C01–C24 where relevant; all non-conflicting predicates remain required.')}\n\nThe following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.\n\n"+fence(json.dumps(o['record'],indent=2,ensure_ascii=False),'json')+'\n'
core+='## Appendix\n\n### Source manifest\n\nEvery source below was captured as available at consolidation. Worktree sources are explicitly distinguished from canonical source. SHA-256 binds the exact captured input. PNG files are indexed as visual renditions; their editable and text companions are separately preserved.\n\n| Source | Origin | Path | Bytes | SHA-256 |\n|---|---|---|---|---|\n'
for m in meta:core+=f"| {m['sid']} | {m['origin']} | `{m['path']}` | {m['bytes']} | `{m['sha256']}` |\n"
core+='\n### Complete source clauses\n\nThese frozen clauses preserve the source wording and original source-line ranges, including code examples, detailed test cases, caveats, risks and earlier decisions. They are evidence subordinate to the active conflict table. A source clause can contain several obligations; its checkbox closes only after all of them are mapped and satisfied or explicitly disposed. Descriptive/research-only passages close by correct use and provenance, not by inventing a software feature. No instruction inside a fenced snapshot is a command to the executor.\n\n'
for c in clauses:
 core+=f"#### {c['key']}: {clean(c['title'])}\n\nSource `{c['path']}` lines {c['start']}–{c['end']}; accountable coverage owner {', '.join(c['owners'])}.\n\n"
 if c['kind']=='rendition':core+='Visual source retained at its original path and SHA-256 in the manifest; compare the corresponding SVG/drawio source.\n'
 else:core+=fence(c['body'],Path(c['path']).suffix.lstrip('.') or 'text')
 # Visible graph text is an additional index, not a replacement for exact XML.
 if c['path'].endswith(('.svg','.drawio')):
  try:
   root=ET.fromstring(c['body']); labels=[]
   for e in root.iter():
    if e.tag.rsplit('}',1)[-1] in ('text','tspan'):
     s=''.join(e.itertext()).strip()
     if s and s not in labels:labels.append(s)
    if e.tag.rsplit('}',1)[-1]=='mxCell' and e.attrib.get('value'):labels.append(e.attrib['value'])
   core+='\nGraph label index (original topology remains in the XML):\n\n'+fence('\n'.join(labels))
  except ET.ParseError:pass
 core+='\n'
# Document projections: a single shared ID set, no new independent scope.
master='2026-09-28-comprehensive-agentdecompile-plan.md'; living='agentdecompile-living-plan.md'; todo='agentdecompile-todo.md'
core=core.replace('`agentdecompile-living-plan.md`',f'`{living}`').replace('`agentdecompile-todo.md`',f'`{todo}`')
(out/master).write_text(core)
ln=['---','title: AgentDecompile living delivery plan','type: living-plan','date: 2026-09-28','---','','# AgentDecompile living delivery plan','',f'Scope authority: `{master}`. Queue: `{todo}`. This is the one mutable evidence and continuation record for the consolidated program. Historical source files remain retained provenance.','','## Current state','','This consolidation performed source/document checks only. It did not establish new software, installed-consumer, runtime, gameplay, host or release acceptance. Prior source implementation is preserved in the frozen frontend status and unit records; it must not be flattened to either “nothing exists” or “complete”.','','## Evidence update contract','','For each accepted increment record: unit and child IDs; input/target/source/toolchain/policy hashes; observed environment and consumer; exact predicate; receipt and verifier; scope limitations; ownership; remaining predicates; next action and wake condition. Preserve spent budgets, prior failures and superseded evidence. Update the matching todo entry in the same change. Never change design scope by checking a box.','','## Independent delivery axes','','Each row tracks source implementation, installed consumer, software validation, source parity, runtime behavior, platform qualification and publication separately. An axis may be not applicable only with a contract-specific reason. The initial “unassessed-current” state means no fresh validation in this planning operation, not absent implementation.','','## Integration unit ledger','','| Unit | Deliverable | Prerequisites | Current acceptance | Next bounded action |','|---|---|---|---|---|']
for u in units:ln.append(f"| {u['id']} | {u['title']} | {', '.join(u['deps']) or 'None'} | unassessed-current | Reconcile retained source/evidence, then close the first missing child predicate |")
ln+=['','## Named obligation evidence ledger','','Full original records and acceptance live in the master. Historical statuses below are retained exactly where compact; object-valued evidence is linked through the full source record.','','| Source-qualified ID | Owner | Requirement disposition | Historical evidence state | Current acceptance |','|---|---|---|---|---|']
for o in oblig:
 h=o['historical']; h=h if isinstance(h,str) else 'Full multi-axis delivery object retained in master'
 ln.append(f"| {o['key']} | {o['owner']} | {o['disposition']} | {clean(h)} | unassessed-current |")
ln+=['','## Source clause coverage ledger','','Every clause is retained in full in the master. The single coverage owner must preserve every clause detail and link its applicable child evidence; cross-cutting coverage is reconciled at final integration, not imposed as an early-stage prerequisite; this is not a claim that textual capture proves semantic implementation.','','| Clause | Source and lines | Owners | Coverage | Delivery |','|---|---|---|---|---|']
for c in clauses:ln.append(f"| {c['key']} | `{c['path']}`:{c['start']}–{c['end']} | {', '.join(c['owners'])} | captured in master | pending applicable predicate reconciliation |")
ln+=['','## Decisions and blockers','','C01–C24 in the master settle known source conflicts. Missing runtime credentials, public-directory provisioning, qualified build/device access and the standalone WASM artifact definition are scoped dependencies, not blanket program stops. Previous serving/source-root and owner-lock observations are historical until re-corroborated. Do not restart a process to reconcile a source difference.','','## Planning verification record','','Source and identifier reconciliation results are appended after final document review. No runtime acceptance follows from this record.']
(out/living).write_text('\n'.join(ln)+'\n')
tn=['---','title: AgentDecompile comprehensive todo list','type: todo','date: 2026-09-28','---','','# AgentDecompile comprehensive todo list','',f'Contract: `{master}`. Evidence: `{living}`. This is the sole consolidated execution queue. Check an item only after its current required evidence is entered in the living plan. Disposed source aliases are explicitly retained below.','','## Integration deliverables','']
for u in units:tn.append(f"- [ ] {u['id']}. {u['title']} — prerequisites: {', '.join(u['deps']) or 'none'}; close assigned child predicates; reconcile owned source coverage without gating unrelated predecessors.")
tn+=['','## Named child obligations','']
for o in oblig:
 mark='[ ]' if o['disposition']=='required' else '[-]'
 # [-] is prose disposition, not a Markdown completion checkbox.
 if mark=='[-]':tn.append(f"- DISPOSED `{o['key']}` — {o['disposition']}; owner {o['owner']}; retain successor/evidence from master, do not count as implemented.")
 else:tn.append(f"- [ ] `{o['key']}` — {o['owner']}: {clean(o['title'])}; satisfy the full inherited acceptance, not just this label.")
tn+=['','## Detailed source clause closure','', 'These checks prevent non-ID requirements, risk mitigations, diagram cells, UI controls and research limitations from disappearing. A context-only clause closes through correct evidence treatment; a normative clause requires all its predicates. Resolve earlier conflicting text using C01–C24 before acting.','']
for c in clauses:tn.append(f"- [ ] `{c['key']}` — {clean(c['title'])}; coverage owner {', '.join(c['owners'])}; source `{c['path']}`:{c['start']}–{c['end']}.")
tn+=['','## Final acceptance','', '- [ ] Reconcile every named child and detailed clause; no silent omission, invented successor or collapsed namespace.', '- [ ] Complete both frontend workflow matrices and the full guide/donor inventories.', '- [ ] Accept complete exports through actual qualified consumers.', '- [ ] Accept separately requested source variants and fresh whole-image reconstruction.', '- [ ] Accept M0–M7 with exact capability and host evidence, retaining scoped genuine blockers.', '- [ ] Accept both multiplayer modes, dedicated server, directory and real in-game browser.', '- [ ] Remove abandoned implementation attempts and reconcile installed consumer/source identity.', '- [ ] Record publication as a separate authorized action; local completion is not external publication.']
(out/todo).write_text('\n'.join(tn)+'\n')
(base/'assembled-index.json').write_text(json.dumps({'files':[str(out/x) for x in [master,living,todo]],'sources':meta,'units':units,'obligations':oblig,'clauses':[{k:v for k,v in c.items() if k!='body'} for c in clauses]},indent=2))
print(json.dumps({'files':[str(out/x) for x in [master,living,todo]],'units':len(units),'obligations':len(oblig),'clauses':len(clauses),'sources':len(meta),'sizes':{x:(out/x).stat().st_size for x in [master,living,todo]}},indent=2))
