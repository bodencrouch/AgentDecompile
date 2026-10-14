from pathlib import Path
import json,re,hashlib,collections
b=Path('/home/brunner56/agentdecompile-plan-consolidation'); idx=json.loads((b/'assembled-index.json').read_text()); docs=[Path(x).read_text() for x in idx['files']]; errors=[]
for kind,items in [('unit',idx['units']),('obligation',idx['obligations']),('clause',idx['clauses'])]:
 key='id' if kind=='unit' else 'key'; ids=[x[key] for x in items]
 if len(ids)!=len(set(ids)):errors.append('duplicate '+kind)
 for i in ids:
  for n,d in enumerate(docs):
   if i not in d:errors.append(f'missing {kind} {i} in file {n}')
for c in idx['clauses']:
 if len(c['owners'])!=1:errors.append('nonunique owner '+c['key'])
 if c['owners'][0] not in {u['id'] for u in idx['units']}:errors.append('bad owner '+c['key'])
# Check every source line belongs to exactly one archived source range.
for m in idx['sources']:
 path=m['path']; raw=(b/'sources'/path).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=m['sha256']:errors.append('snapshot hash '+path)
 if path.endswith('.png'):continue
 n=len(raw.decode().splitlines()); counts=[0]*n
 for c in idx['clauses']:
  if c['path']==path and c['kind']=='source':
   for i in range(c['start']-1,c['end']):counts[i]+=1
 if any(x!=1 for x in counts):errors.append('source range gap/overlap '+path)
# Check unit-level dependency graph has no cycles or dangling references.
units={u['id']:u for u in idx['units']}; done=set(); active=set()
def walk(k):
 if k in active:errors.append('cycle '+k);return
 if k in done:return
 active.add(k)
 for d in units[k]['deps']:
  if d not in units:errors.append('missing dependency '+d)
  else:walk(d)
 active.remove(k);done.add(k)
for k in units:walk(k)
# Check fenced appendices cannot inject headings/instructions into active rendering.
fence=None
for i,l in enumerate(docs[0].splitlines(),1):
 m=re.match(r'^(`{3,}|~{3,})(.*)$',l)
 if m:
  if fence is None:fence=m[1]
  elif m[1][0]==fence[0] and len(m[1])>=len(fence) and not m[2].strip():fence=None
if fence:errors.append('unclosed markdown fence')
result={'sources':len(idx['sources']),'integration_units':len(units),'named_obligations':len(idx['obligations']),'source_clauses':sum(c['kind']!='diagram-element' for c in idx['clauses']),'diagram_elements':sum(c['kind']=='diagram-element' for c in idx['clauses']),'errors':errors,'scope':'Documentation structure, retained source coverage and cross-file identifiers only; no software or runtime tests.'}
(b/'document-check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
