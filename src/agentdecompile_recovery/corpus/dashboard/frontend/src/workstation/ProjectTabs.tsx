import type {Selection} from '../contracts';
import {sessionKey} from './navigation';
import type {ProjectSession} from './projectSessions';
import './project-tabs.css';

export function ProjectTabs({projects,currentKey,selection,onSelect,onClose,onOpen,onManage}:{
  projects:ProjectSession[];currentKey:string;selection:Selection;
  onSelect:(selection:Selection)=>void;onClose:(key:string)=>void;onOpen:()=>void;onManage:()=>void;
}){
  const current=projects.find(project=>project.key===currentKey);
  const selectedMember=current?.members.find(member=>sessionKey(member.selection)===sessionKey(selection));
  return <section className="ws-project-tabs" aria-label="Project workspace">
    <nav className="ws-sessions" aria-label="Open projects">
      {projects.map(project=><div key={project.key} className={project.key===currentKey?'active':''}>
        <button type="button" aria-current={project.key===currentKey?'page':undefined} aria-pressed={project.key===currentKey} title={project.scope} onClick={()=>onSelect(project.selection)}>{project.name}</button>
        <button type="button" aria-label={`Close workspace tab ${project.name}`} title="Close this tab; recorded work remains available" onClick={()=>onClose(project.key)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="m6 6 12 12 M18 6 6 18"/></svg></button>
      </div>)}
      {!projects.length&&<span>No project open</span>}
      <button type="button" onClick={onOpen}>Open project…</button>
      <button type="button" onClick={onManage}>Project manager…</button>
    </nav>
    {current&&<div className="ws-project-focus">
      <span className="ws-project-scope" title={current.scope}>{current.scope}</span>
      <label>Inspected build <select aria-label="Inspected build in this project" value={selectedMember?sessionKey(selectedMember.selection):''} onChange={event=>{const member=current.members.find(value=>sessionKey(value.selection)===event.target.value);if(member)onSelect(member.selection);}}>
        <option value="" disabled>{current.members.length?'Project overview':'No build inspected'}</option>
        {current.members.map(member=><option key={sessionKey(member.selection)} value={sessionKey(member.selection)}>{member.name}{member.selection.program&&member.name!==member.selection.program?` · ${member.selection.program}`:''}</option>)}
      </select></label>
      <small>Previously inspected builds</small>
    </div>}
  </section>;
}
