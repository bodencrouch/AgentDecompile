import {normalizeSelection,type Selection} from '../contracts';
import {canonicalProjectLocator} from '../projectLocator';
import {sessionKey} from './navigation';

export type WorkstationSession={selection:Selection;name:string;lastFocusedAt?:number};
export type ProjectSession={key:string;name:string;scope:string;locator:string;selection:Selection;members:WorkstationSession[]};

export function hasWorkspaceSelection(selection:Selection):boolean {
  return Boolean(selection.locator||selection.projectId||selection.slug||selection.program||selection.binaryHash||selection.logicalId);
}

/** Local paths and project IDs have no global server namespace. */
function projectSessionIdentity(selection:Selection,sessions:WorkstationSession[]):{key:string;locator:string} {
  selection=normalizeSelection(selection);
  const corpusIdentity=selection.corpusIdentity||'';
  const located=(locator:string)=>({key:`locator:${JSON.stringify([corpusIdentity,locator])}`,locator});
  const locator=canonicalProjectLocator(selection.locator);
  if(locator)return located(locator);
  if(selection.projectId){
    const locators=new Set(sessions.map(session=>normalizeSelection(session.selection))
      .filter(saved=>saved.projectId===selection.projectId&&(saved.corpusIdentity||'')===corpusIdentity)
      .map(saved=>canonicalProjectLocator(saved.locator)).filter(Boolean));
    if(locators.size===1)return located([...locators][0]);
    return {key:`project:${JSON.stringify([corpusIdentity,selection.projectId])}`,locator:''};
  }
  // Unbound observations share a clearly labeled workspace, not an invented project.
  return {key:`corpus:${JSON.stringify(corpusIdentity)}`,locator:''};
}

export function projectSessionKey(selection:Selection,sessions:WorkstationSession[]):string {
  return projectSessionIdentity(selection,sessions).key;
}

function memberName(selection:Selection):string {
  return selection.program||selection.slug||selection.binaryHash?.slice(0,12)||'Project overview';
}

/** Project tabs are a projection; retain concrete saved sessions and their contexts. */
export function groupProjectSessions(sessions:WorkstationSession[],current:Selection):ProjectSession[] {
  const records=sessions.map(session=>({...session,selection:normalizeSelection(session.selection)}));
  if(hasWorkspaceSelection(current)&&!records.some(session=>sessionKey(session.selection)===sessionKey(current)))
    records.push({selection:current,name:memberName(current)});
  const groups=new Map<string,ProjectSession>();
  const latest=new Map<string,number>();
  for(const [index,session] of records.entries()){
    const selection=session.selection;
    if(!hasWorkspaceSelection(selection))continue;
    const {key,locator}=projectSessionIdentity(selection,records);
    const scope=`${locator||selection.projectId||'Unbound observations — no project binding'}${selection.corpusIdentity?` · corpus ${selection.corpusIdentity}`:''}`;
    const name=locator?locator.split('/').pop()||locator:selection.projectId==='local:workbench'?'Local workspace':selection.projectId||'Unbound observations';
    let group=groups.get(key);
    if(!group){group={key,name,scope,locator,selection,members:[]};groups.set(key,group);}
    const recency=Number.isFinite(session.lastFocusedAt)?session.lastFocusedAt!:index;
    if(recency>=(latest.get(key)??-1)){group.selection=selection;latest.set(key,recency);}
    if(selection.slug||selection.program||selection.binaryHash){
      const member={...session,name:session.name||memberName(selection)};
      const existing=group.members.findIndex(value=>sessionKey(value.selection)===sessionKey(selection));
      if(existing<0)group.members.push(member);else group.members[existing]=member;
    }
  }
  if(hasWorkspaceSelection(current)){
    const active=groups.get(projectSessionKey(current,records));
    if(active){
      active.selection=current;
      active.members=active.members.map(member=>sessionKey(member.selection)===sessionKey(current)?{...member,selection:current}:member);
    }
  }
  return [...groups.values()];
}
