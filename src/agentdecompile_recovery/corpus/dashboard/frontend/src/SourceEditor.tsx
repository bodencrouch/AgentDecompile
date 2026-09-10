import {useEffect,useRef,useState} from 'react';
import type * as Monaco from 'monaco-editor';
import type {Data,Selection} from './contracts';
import {defaultSourceLanguage,languageFromPath,languageSpec} from './languages';
import {readWorkspaceDraft,patchWorkspaceState} from './workspaceState';
import './editor.css';
import {useData} from './ui';

type Mode='evidence'|'draft';
const models=new Map<string,{model:Monaco.editor.ITextModel;users:number}>();
const views=new Map<string,Monaco.editor.ICodeEditorViewState|null>();
export function useFunctionEvidence(url:string|null,revision:number) {
  const [tick,setTick]=useState(0);
  useEffect(()=>{if(!url)return;const timer=setInterval(()=>{if(!document.hidden)setTick(value=>value+1);},5000);return()=>clearInterval(timer);},[url]);
  const response=useData(url,revision+tick);
  const status=response.data.evidenceRequest?.status;
  return {...response,loading:response.loading||['submitting','queued','running','cancelling'].includes(status)};
}
export function sourceWitness(detail:Data):string {
  return detail.decompile?.text||detail.sourceText||((detail.previewKind==='source-excerpt'||(!detail.previewKind&&!detail.source&&detail.sourcePath))?detail.preview:'')||'';
}
export function sourceExtent(detail:Data):string {
  if(detail.decompile?.text){if(detail.decompile.truncated===true)return `Source excerpt · limited to ${detail.decompile.characterLimit||8000} characters`;if(detail.decompile.truncated===false)return 'Recorded source text';return 'Recorded source excerpt · completeness unknown';}
  if(detail.previewKind==='source-excerpt'||detail.sourcePath)return detail.previewTruncated===false?'Recorded source text':`Source preview · ${detail.previewCharacterLimit||4000} character limit`;
  return detail.decompile?.reason||detail.evidenceRequest?.reason||'No recorded source text';
}
type EditorProps={selection:Selection;value:string;sourcePath?:string;kind?:'source'|'assembly'|'comparison';loading?:boolean;extent?:string;allowDraft?:boolean;onInspectSymbol?:(symbol:string)=>void};
export function SourceEditor(props:EditorProps) {
  return props.selection.addr?<DocumentEditor key={JSON.stringify([props.selection.locator,props.selection.slug,props.selection.program,props.selection.addr,props.kind])} {...props}/>:<div className="source-editor-foot">Select a function to inspect its source and assembly.</div>;
}
function DocumentEditor({selection,value,sourcePath='',kind='source',loading=false,extent='',allowDraft=true,onInspectSymbol}:EditorProps) {
  const key=JSON.stringify([selection.locator,selection.slug,selection.program,selection.addr,kind]);
  const sourceLanguage=selection.program?languageFromPath(selection.program,{default:defaultSourceLanguage()}):defaultSourceLanguage();
  const sourceSpec=languageSpec(sourceLanguage);
  const monacoLanguageId=kind==='assembly'?'agentdecompile-asm':(sourceSpec.monacoId||'plaintext');
  const sourceLabel=kind==='assembly'?'Assembly':`${sourceSpec.displayName} source`;
  const downloadExtension=kind==='assembly'?'.asm':sourceSpec.defaultExportExtension;
  const runtimeConfig=useData('/dashboard/api/runtime-config');
  const [mode,setMode]=useState<Mode>('evidence'),[status,setStatus]=useState('Loading editor…'),[error,setError]=useState(''),[wrap,setWrap]=useState(false);
  const element=useRef<HTMLDivElement>(null),editor=useRef<Monaco.editor.IStandaloneCodeEditor|null>(null),latest=useRef(value),symbolCallback=useRef(onInspectSymbol);
  latest.current=value;symbolCallback.current=onInspectSymbol;
  useEffect(()=>setMode('evidence'),[key]);
  useEffect(()=>{
    let alive=true,instance:Monaco.editor.IStandaloneCodeEditor|null=null,model:Monaco.editor.ITextModel|null=null,subscription:Monaco.IDisposable|undefined,timer:ReturnType<typeof setTimeout>|undefined;
    setStatus('Loading editor…');setError('');
    const viewKey=key+':'+mode;
    const persist=()=>{if(mode!=='draft'||!model)return;const text=model.getValue();try{patchWorkspaceState('drafts',key,{text,updatedAt:Date.now()});if(alive)setStatus('Draft saved in this tab');}catch{if(alive)setError('Browser storage is unavailable. Download this draft to keep it.');}};
    void (async ()=>{
      let initial=latest.current;
      if(mode==='draft'){
        try{initial=(await readWorkspaceDraft(key))??initial;}catch{}
      }
      const {monaco,ensureMonacoLanguage}=await import('./monaco-runtime');
      if(!alive||!element.current)return;
      await ensureMonacoLanguage(monacoLanguageId);
      const cached=models.get(viewKey);
      if(cached&&!cached.model.isDisposed()){model=cached.model;cached.users+=1;if(mode==='evidence'&&model.getValue()!==initial)model.setValue(initial);}
      else {model=monaco.editor.createModel(initial,monacoLanguageId);models.set(viewKey,{model,users:1});}
      instance=monaco.editor.create(element.current,{model,theme:'vs-dark',readOnly:mode==='evidence',automaticLayout:true,minimap:{enabled:false},fontSize:12,lineHeight:19,fontFamily:'"DejaVu Sans Mono", "Liberation Mono", monospace',lineNumbers:'on',glyphMargin:false,folding:true,wordWrap:wrap?'on':'off',scrollBeyondLastLine:false,renderWhitespace:'selection',smoothScrolling:false,contextmenu:true,ariaLabel:`${sourceLabel} ${mode==='draft'?'draft editor':'read-only evidence editor'}`,tabSize:4,stickyScroll:{enabled:false}});
      instance.onMouseDown(event=>{if(mode==='evidence'&&event.event.detail===2&&event.target.position){const word=model?.getWordAtPosition(event.target.position)?.word;if(word)symbolCallback.current?.(word);}});
      editor.current=instance;instance.restoreViewState(views.get(viewKey)||null);
      if(mode==='draft')subscription=model.onDidChangeContent(()=>{setStatus('Saving draft…');clearTimeout(timer);timer=setTimeout(persist,150);});
      setStatus(mode==='draft'?'Workspace draft · not submitted to Ghidra':'Read-only evidence');
    })().catch(e=>{if(alive){setError(`Editor could not load: ${e instanceof Error?e.message:String(e)}`);setStatus('Editor unavailable');}});
    return()=>{alive=false;clearTimeout(timer);persist();if(instance){views.set(viewKey,instance.saveViewState());if(views.size>100)views.delete(views.keys().next().value!);instance.dispose();}subscription?.dispose();const cached=models.get(viewKey);if(cached&&model===cached.model)cached.users=Math.max(0,cached.users-1);if(models.size>40){for(const [oldKey,entry] of models){if(entry.users===0){entry.model.dispose();models.delete(oldKey);views.delete(oldKey);if(models.size<=40)break;}}}editor.current=null;};
  },[key,mode,kind,monacoLanguageId,sourceLabel]);
  useEffect(()=>{const instance=editor.current;if(mode!=='evidence'||!instance||instance.getValue()===value)return;const view=instance.saveViewState();instance.setValue(value);instance.restoreViewState(view);},[value,mode]);
  useEffect(()=>editor.current?.updateOptions({wordWrap:wrap?'on':'off'}),[wrap]);
  function find(){void editor.current?.getAction('actions.find')?.run().catch(failure=>{if(failure?.name!=='Canceled'&&failure?.message!=='Canceled')setError(`Find could not open: ${String(failure)}`);});}
  function download(){const content=editor.current?.getValue()??latest.current,blob=new Blob([content],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download=`${(selection.program||selection.slug||'function').replace(/[^a-zA-Z0-9_.-]/g,'_')}-${selection.addr||'source'}-${mode}${downloadExtension}`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  const codeTarget=sourcePath.startsWith('/')?`vscode://file/${encodeURI(sourcePath)}`:'';
  const configuredIde=runtimeConfig.data?.webIde;
  // The server endpoint makes this work in the packaged static bundle. The
  // Vite values remain a development fallback when the backend is unavailable.
  const webIde=(configuredIde?.url||import.meta.env.VITE_AGENTDECOMPILE_WEB_IDE_URL||'').replace(/\/$/,'');
  const embed=typeof configuredIde?.embed==='boolean'?configuredIde.embed:import.meta.env.VITE_AGENTDECOMPILE_WEB_IDE_EMBED==='1';
  const webIdeTarget=webIde?(()=>{try{const url=new URL(webIde,location.href);if(sourcePath.startsWith('/'))url.searchParams.set('folder',sourcePath.replace(/\/[^/]+$/,''));return url.toString();}catch{return webIde;}})():'';
  return <div className="source-editor" data-mode={mode}><div className="source-editor-toolbar"><span className="source-editor-state">{loading?'Receiving evidence…':status}</span>{allowDraft&&kind!=='assembly'&&<button aria-pressed={mode==='draft'} onClick={()=>setMode(mode==='draft'?'evidence':'draft')}>{mode==='draft'?'View evidence':'Edit local draft'}</button>}<button onClick={find}>Find</button><button aria-pressed={wrap} onClick={()=>setWrap(!wrap)}>Wrap</button><button onClick={download} disabled={!editor.current}>Download {mode==='draft'?'draft':'text'}</button>{codeTarget?<a href={codeTarget}>Open source in VS Code</a>:<span title="No recovered source file path is recorded for this evidence.">VS Code unavailable</span>}{webIdeTarget?<a href={webIdeTarget} target="_blank" rel="noreferrer">Open browser VS Code</a>:null}</div>{webIdeTarget&&embed?<iframe title="Browser VS Code" src={webIdeTarget} onError={()=>setError('Browser VS Code could not be embedded; use Open browser VS Code instead.')} />:null}<div className="source-editor-frame"><div className="source-editor-host" ref={element}/>{!value&&mode==='evidence'&&<div className="source-editor-empty">{loading?'Reading source, assembly, and references from Ghidra…':extent||(kind==='assembly'?'Ghidra supplied no assembly for this function.':'Ghidra supplied no source body for this function.')}</div>}</div>{error&&<p role="alert">{error}</p>}<div className="source-editor-foot"><span>{mode==='draft'?'Draft changes stay in this tab. They do not modify Ghidra or establish proof.':extent||'Tool observation · no byte-verification claim'}</span>{!value&&mode==='evidence'&&<span>No text supplied for this selection.</span>}</div></div>;
}
