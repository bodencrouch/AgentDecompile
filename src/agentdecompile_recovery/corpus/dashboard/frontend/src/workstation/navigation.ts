import {emptySelection, normalizeSelection, type Data, type Selection} from '../contracts';
import {canonicalProjectLocator} from '../projectLocator';
export const analysisTabs = ['Logical','Disassembly','Decompiler','Hex','Strings','Graph','Xrefs','Imports','Exports','Sections','Info','Matching','Compare'] as const;
export type AnalysisTab = typeof analysisTabs[number] | 'Scripts' | 'Flags' | 'Types' | 'Providers' | 'Expert' | 'Container' | 'Decompilers';
export const extraTabs: AnalysisTab[] = ['Scripts','Flags','Types','Providers','Expert','Container','Decompilers'];
export type Route = {selection: Selection; tab: AnalysisTab};
const routeKeys = ['slug','program','addr','logicalId','corpusIdentity','locator','binaryHash','projectId','functionId','lastFunctionAddr'] as const;
const routeAliases = {binary:'slug',function:'addr',logical_id:'logicalId',corpus_identity:'corpusIdentity',project:'locator',binary_hash:'binaryHash',project_id:'projectId',function_id:'functionId'} as const;
const legacyViews:Record<string,AnalysisTab> = {logical:'Logical',listing:'Disassembly',fnbrowse:'Disassembly',functions:'Disassembly',decompile:'Decompiler',decompiler:'Decompiler',disassembly:'Disassembly',hex:'Hex',strings:'Strings',graph:'Graph',xrefs:'Xrefs',imports:'Imports',exports:'Exports',sections:'Sections',overview:'Info',corpus:'Logical',info:'Info',matching:'Matching',scratch:'Matching',compare:'Compare',scripts:'Scripts',flags:'Flags',types:'Types',stabs:'Types',providers:'Providers',expert:'Expert',container:'Container',decompilers:'Decompilers',dogbolt:'Decompilers'};
export function readRoute(search: string, fallback: Route): Route {
  const p = new URLSearchParams(search);
  const linked = routeKeys.some(k=>p.has(k)) || Object.keys(routeAliases).some(k=>p.has(k));
  const selection: Selection = linked ? {...emptySelection} : {...fallback.selection};
  for(const key of routeKeys) if(p.has(key)) selection[key] = p.get(key)!;
  for(const [alias,key] of Object.entries(routeAliases)) if(p.has(alias)&&!p.has(key)) selection[key as typeof routeKeys[number]]=p.get(alias)!;
  const raw=p.get('view')??p.get('window')??p.get('focus')??p.get('tool')??'';
  const tab=legacyViews[raw.replace(/^wb-/,'').toLowerCase()]||raw;
  return {selection:normalizeSelection(selection),tab:[...analysisTabs,...extraTabs].includes(tab as AnalysisTab)?tab as AnalysisTab:fallback.tab};
}
export function routeUrl(url: string, route: Route): string {
  const next=new URL(url);
  for(const key of [...routeKeys,...Object.keys(routeAliases),'view','window','focus','tool']) next.searchParams.delete(key);
  const selection=normalizeSelection(route.selection);
  // Keep an empty selection explicit so refresh cannot resurrect saved state.
  next.searchParams.set('slug',selection.slug);
  for(const key of routeKeys) if(selection[key]) next.searchParams.set(key,selection[key]!);
  next.searchParams.set('view',route.tab);
  return next.pathname+next.search+next.hash;
}
export function sessionKey(s:Selection) {return [s.locator,s.projectId,s.slug,s.program,s.binaryHash,s.corpusIdentity].join('\u001f');}
/** Only an explicitly selected returned member can carry an identity between builds. */
export function mergeSelection(current:Selection,patch:Partial<Selection>,member=false):Selection {
  const changed=(['locator','projectId','slug','program','binaryHash'] as const).some(key=>patch[key]!==undefined&&patch[key]!==current[key]);
  const logicalOnly=Boolean(patch.logicalId)&&!Object.hasOwn(patch,'addr')&&!Object.hasOwn(patch,'slug')&&!Object.hasOwn(patch,'program');
  const corpusChanged=patch.corpusIdentity!==undefined&&patch.corpusIdentity!==current.corpusIdentity;
  const base=logicalOnly?{...emptySelection,locator:current.locator,projectId:current.projectId}:changed||corpusChanged?{...emptySelection}:current;
  const next=normalizeSelection({...base,...patch});
  if(patch.addr!==undefined&&patch.addr!==current.addr){
    next.functionId=patch.functionId??'';next.logicalId=patch.logicalId??'';
    next.region=patch.region;next.evidenceIds=patch.evidenceIds;
  }
  if(changed&&!member)next.logicalId='';
  if(patch.logicalId&&!patch.corpusIdentity)next.corpusIdentity='';
  return next;
}
export function memberSelection(member:Data,binaries:Data[],current:Selection):Selection {
  const matches=binaries.filter(binary=>binary.slug===member.slug||binary.aliasSlugs?.includes(member.slug));
  const bindings=matches.flatMap(binary=>(binary.projectBindings||[]).map((binding:Data)=>({...binding,binaryHash:binary.sha256||''})));
  const unique=[...new Map(bindings.filter(binding=>binding.locator&&binding.program).map(binding=>[[canonicalProjectLocator(binding.locator),binding.projectId||binding.project_id||'',binding.program].join('\u001f'),binding])).values()];
  const scoped=unique.filter(binding=>
    (!current.locator||canonicalProjectLocator(binding.locator)===canonicalProjectLocator(current.locator))&&
    (!current.projectId||((binding.projectId||binding.project_id)?(binding.projectId||binding.project_id)===current.projectId:Boolean(current.locator))));
  const available=current.locator||current.projectId?scoped:unique;
  const binding=matches.length===1&&available.length===1?available[0]:undefined;
  return {...emptySelection,slug:String(member.slug||''),addr:addressOf(member),lastFunctionAddr:addressOf(member),logicalId:current.logicalId,
    corpusIdentity:current.corpusIdentity,projectId:current.projectId||binding?.projectId||binding?.project_id||'',
    locator:current.locator||binding?.locator||'',program:binding?.program||'',binaryHash:binding?.binaryHash||''};
}
export function addressOf(row:Record<string,any>):string {return String(row.addr||row.address||row.fromAddress||row.start||'');}
export function shellShortcut(event:Pick<KeyboardEvent,'defaultPrevented'|'ctrlKey'|'metaKey'|'key'>,modalOpen:boolean) {
  if(event.defaultPrevented||modalOpen)return null;
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k')return 'commands';
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='p')return 'functions';
  return event.key==='Escape'?'dismiss':null;
}
export function fileOffset(addr:string):number {
  if(!/^(?:0x)?[0-9a-f]+$/i.test(addr))return 0;
  const value=Number.parseInt(addr.replace(/^0x/i,''),16);
  return Number.isSafeInteger(value)&&value>=0?value:0;
}
export function hexPageSelection(addr:string,direction:-1|1):Partial<Selection> {
  return {addr:'0x'+Math.max(0,fileOffset(addr)+direction*1024).toString(16),logicalId:''};
}
export function referenceParams(addr:string,mode:'to'|'from'|'function',offset:number) {
  // ponytail: backend ignores offset; page a bounded prefix until server pagination is fixed.
  return {addressOrSymbol:addr,mode,offset:0,limit:Math.min(800,offset+80)};
}
export function canPrepareAnalysis({local,selected,loading,error,filter,count,advertised,offset=0}:{offset?:number;local:boolean;selected:boolean;loading:boolean;error:string;filter:string;count:number;advertised:boolean}) {
  return !local&&selected&&!loading&&!error&&!filter.trim()&&offset===0&&count===0&&advertised;
}
