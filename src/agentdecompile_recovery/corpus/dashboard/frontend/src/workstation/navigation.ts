import {emptySelection, normalizeSelection, type Selection} from '../contracts';
export const analysisTabs = ['Disassembly','Decompiler','Hex','Strings','Graph','Xrefs','Imports','Exports','Sections','Info','Matching'] as const;
export type AnalysisTab = typeof analysisTabs[number] | 'Scripts' | 'Flags' | 'Types' | 'Providers';
export const extraTabs: AnalysisTab[] = ['Scripts','Flags','Types','Providers'];
export type Route = {selection: Selection; tab: AnalysisTab};
export function readRoute(search: string, fallback: Route): Route {
  const p = new URLSearchParams(search);
  const keys = ['slug','program','addr','logicalId','locator','binaryHash','projectId','functionId'] as const;
  const linked = keys.some(k=>p.has(k)) || p.has('binary') || p.has('logical_id');
  const selection: Selection = linked ? {...emptySelection} : {...fallback.selection};
  for(const key of keys) if(p.has(key)) selection[key] = p.get(key)!;
  if(p.has('binary')&&!p.has('slug')) selection.slug=p.get('binary')!;
  if(p.has('logical_id')) selection.logicalId=p.get('logical_id')!;
  const tab=p.get('view');
  return {selection:normalizeSelection(selection),tab:[...analysisTabs,...extraTabs].includes(tab as AnalysisTab)?tab as AnalysisTab:fallback.tab};
}
export function routeUrl(url: string, route: Route): string {
  const next=new URL(url);
  for(const key of ['slug','program','addr','logicalId','logical_id','locator','binaryHash','projectId','functionId','binary','view']) next.searchParams.delete(key);
  for(const key of ['slug','program','addr','logicalId','locator','binaryHash','projectId','functionId'] as const) if(route.selection[key]) next.searchParams.set(key,route.selection[key]!);
  next.searchParams.set('view',route.tab);
  return next.pathname+next.search+next.hash;
}
export function sessionKey(s:Selection) {return [s.locator,s.slug,s.program,s.binaryHash].join('\u001f');}
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
