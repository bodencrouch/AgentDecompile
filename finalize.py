from pathlib import Path
import json,re
b=Path('/home/brunner56/agentdecompile-plan-consolidation'); snap=b/'sources'; idx=json.loads((b/'assembled-index.json').read_text()); paths=[Path(x) for x in idx['files']]; master,living,todo=paths
extra=[]
def add(key,title,body,owner,path,line):extra.append(dict(key=key,title=title,owner=owner,disposition='required',historical='Retained source state; no fresh acceptance',record={'source':path,'line':line,'text':body},source=path))
p='docs/FRONTEND_INTENT.md'; lines=(snap/p).read_text().splitlines()
fowners={**{i:'U14' for i in range(1,7)},**{i:'U15' for i in range(7,13)},13:'U19',14:'U14',15:'U16',16:'U16',17:'U19',18:'U19',19:'U17',20:'U40',21:'U22',22:'U16',23:'U14',24:'U28',25:'U6',26:'U31',27:'U41',28:'U40'}
for i,l in enumerate(lines):
 m=re.match(r'- \*\*(F\d+) [—-] (.+)',l) or re.match(r'\| (F\d+) \| (.+)',l)
 if not m:continue
 end=i+1
 if l.startswith('- '):
  while end<len(lines) and lines[end].strip() and not lines[end].startswith(('- **F','#')):end+=1
 body='\n'.join(lines[i:end]);add('frontend-intent:'+m[1],m[1]+' '+m[2].split('|')[0].replace('**',''),body,fowners[int(m[1][1:])],p,i+1)
p='docs/dashboard-design/2026-09-20-ghidra-guide-capability-inventory.md'
for i,l in enumerate((snap/p).read_text().splitlines()):
 m=re.match(r'\| \[(\d+)\. ([^\]]+)\]',l)
 if m:add('ghidra-guide:chapter-'+m[1],m[2],l,'U16',p,i+1)
for p,ns,owners in [('docs/plans/2026-09-20-forgiving-input-cleanup.md','forgiving-input-2026-09-20',{i:'U30' for i in range(1,14)}),('docs/plans/2026-09-20-unified-reversing-workstation.md','workstation-2026-09-20',{1:'U16',2:'U13',3:'U15',4:'U16',5:'U16',6:'U17',7:'U20',8:'U42'}),('docs/plans/2026-09-10-program-info-call-scoped-refactor.md','program-context-2026-09-10',{i:'U29' for i in range(1,6)})]:
 text=(snap/p).read_text(); ms=list(re.finditer(r'^## Task (\d+): (.+)$',text,re.M))
 for m in ms:
  rest=text[m.end():]; nexthead=re.search(r'^## ',rest,re.M);end=m.end()+nexthead.start() if nexthead else len(text)
  add(ns+':Task'+m[1],m[2],text[m.start():end],owners[int(m[1])],p,text[:m.start()].count('\n')+1)
p='worktree/docs/plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md'
for i,l in enumerate((snap/p).read_text().splitlines()):
 m=re.match(r'- R(\d+)\. (.+)',l)
 if m:add('frontend-plan-2026-09-28:R'+m[1],m[2],l,'U42',p,i+1)
p='docs/plans/2026-09-22-autonomous-capability-product-roadmap.md'
for i,l in enumerate((snap/p).read_text().splitlines()):
 m=re.match(r'\| (M[0-7]) (.+?) \|',l)
 if m:add('autonomous-roadmap-2026-09-22:'+m[1],m[2],l,'U9' if m[1]=='M0' else 'U12',p,i+1)
assert len(extra)==148,len(extra)
text=master.read_text(); text=text.replace('permission during planning |\n\n| C19','permission during planning |\n| C19')
# Foreground security contract already preserved in source appendix.
pos=text.index('### U37. Directory');end=text.index('### U38.',pos)
part=text[pos:end]; part=part.replace('- **Completion:**','- **Directory acceptance:** Public metadata includes endpoint, server identity, mode, map, protocol/build/content identity, session-derived counts and passwordRequired only. Verify endpoint ownership and stale expiry. Never publish the actual password, reusable password hash or admin credential; password verification belongs to the authenticated/encrypted game join exchange. Clients measure their own ping and reject incompatible content.\n\n- **Completion:**')
text=text[:pos]+part+text[end:]
head='\n## Additional explicit requirement indexes\n\nThese requirements already exist in the retained source clauses. The separate keys make F01–F28, all guide chapters, earlier task families, newer R1–R70 and M0–M7 individually trackable. They add no new scope. U42 owns integration-level frontend requirement coverage; the concrete producer/consumer units above perform the work.\n\n'
for o in extra:
 body=o['record']['text'];f='`'*(max([len(x) for x in re.findall('`+',body)]+[2])+1)
 head+=f"### {o['key']}\n\n**Owner:** {o['owner']}. **Requirement disposition:** required. **Source:** `{o['source']}`:{o['record']['line']}. Apply C01–C24; historical checked status is not fresh acceptance.\n\n{f}text\n{body.rstrip()}\n{f}\n\n"
text=text.replace('## Appendix\n',head+'## Appendix\n',1);master.write_text(text)
l=living.read_text(); rows='\n## Explicit requirement and workflow ledger\n\n| Source-qualified ID | Owner | Current acceptance |\n|---|---|---|\n'
for o in extra:rows+=f"| {o['key']} | {o['owner']} | unassessed-current; full predicate in master |\n"
rows+='\nPortable U21 follows C20 (generic core, retained named provenance); portable U65 follows C19 (bounded continuation). Their historical labels are not active execution instructions.\n'
living.write_text(l+rows)
t=todo.read_text();rows='\n## Explicit requirements and inherited workflow tasks\n\n'
for o in extra:rows+=f"- [ ] `{o['key']}` — {o['owner']}: {o['title'].replace('|','/').strip()}; satisfy the full source predicate under C01–C24.\n"
todo.write_text(t+rows)
idx['obligations']+=extra;(b/'assembled-index.json').write_text(json.dumps(idx,indent=2));print('Named obligation count',len(idx['obligations']))
