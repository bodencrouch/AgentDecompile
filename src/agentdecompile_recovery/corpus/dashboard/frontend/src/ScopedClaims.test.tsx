import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { expect, it } from 'vitest';
import { ScopedClaims, safeClaimHref, readClaimProjection, selectClaimProjection, type ClaimProjection } from './ScopedClaims';
import { emptySelection } from './contracts';
import type { EntityActivity } from './activity';

const sha='a'.repeat(64);
const fixture=():ClaimProjection=>({schema:'agentdecompile.activity-claims/v1',state:'recorded',reason:'recorded',basis:'source only',targetSha256:sha,checkedAt:100,limit:64,truncated:false,contributionReason:'no_trusted_serving_process_observation',candidates:[{id:'candidate',address:'0x00401000',targetSha256:sha,recordedTargetSha256:sha,candidate:{program:'target.exe',name:'Foo',binary_id:7,addr:0x401000,path:'/configured/candidate.c',source_sha256:'b'.repeat(64)},sourceState:'stale',sourceReason:'source_digest_mismatch',claims:[{kind:'raw-local',state:'stale',accepted:false,scope:'recorded-target-region',label:'Recorded region bytes',summary:'Comparison not revalidated',reason:'source_digest_mismatch'},{kind:'named-identity',state:'recorded',accepted:false,scope:'target-pe-export-name-at-va-v1',label:'Named identity',summary:'Recorded PE export Foo',reason:'recorded_ingestion_witness_only'},{kind:'placed-contribution',state:'unavailable',accepted:false,scope:'anonymous-source-to-target-contribution',label:'Placed source contribution',summary:'No trusted serving-process observation',reason:'no_trusted_serving_process_observation'}],receipts:[{id:'c'.repeat(64),path:'reports/receipt.json',href:'/dashboard/artifact?p=reports%2Freceipt.json',label:'Recorded target/address receipt',candidateBound:false}]}]});
const staticSource=readFileSync(new URL('../../static/explorer-page.js',import.meta.url),'utf8');
function functions(first:string,last:string) {return staticSource.slice(staticSource.indexOf('  function '+first+'('),staticSource.indexOf('  function '+last+'('));}
function fakeNode(tag:string,attrs:Record<string,unknown>={},children:unknown[]=[]) {return {tag,attrs,children,appendChild(child:unknown){this.children.push(child);},addEventListener(){}};}
const staticViews=runInNewContext(functions('safeClaimHref','dimensionBlock')+'; ({safeClaimHref,scopedClaimView});',{URL, state:{connection:'disconnected'},node:fakeNode});

it('renders separate stale/raw historical/name and unavailable contribution in both real renderers',()=>{
 const p=fixture();
 const html=renderToStaticMarkup(createElement(ScopedClaims,{projection:p,address:'0x401000'}));
 const staticHtml=JSON.stringify(staticViews.scopedClaimView(p,'0x401000'));
 for(const text of [html,staticHtml]){
  expect(text).toContain('source_digest_mismatch');expect(text).toContain('Recorded PE export Foo');expect(text).toContain('serving-process');expect(text).toContain('Target/address reference');expect(text).toContain('disconnected');
 }
});
it('preserves multiple candidates and truthful truncated absence',()=>{
 const p=fixture();p.candidates.push({...p.candidates[0],id:'candidate2'});p.truncated=true;
 expect(readClaimProjection(p)?.candidates).toHaveLength(2);
 for(const text of [renderToStaticMarkup(createElement(ScopedClaims,{projection:p,address:'0x499999'})),JSON.stringify(staticViews.scopedClaimView(p,'0x499999'))]){expect(text).toContain('outside this batch may still have evidence');expect(text).toContain('bounded batch');}
});
it('does not promote malformed or forged accepted payloads',()=>{
 const p=fixture();(p.candidates[0].claims[0] as any).accepted=true;
 expect(readClaimProjection(p)).toBeUndefined();
 expect(JSON.stringify(staticViews.scopedClaimView(p))).not.toContain('Recorded region bytes');
 for(const value of [{...fixture(),checkedAt:Infinity},{...fixture(),candidates:[null]}, {...fixture(),targetSha256:'wrong'}])expect(readClaimProjection(value)).toBeUndefined();
});
it('selects exact target and declines same-address wrong binary or ambiguous builds',()=>{
 const entity={kind:'binary',sha256:sha,slug:'a',aliasSlugs:['a'],projectBindings:[{locator:'p',program:'target.exe'}],claimProjection:fixture()} as EntityActivity;
 const selection={...emptySelection,slug:'a',locator:'p',program:'target.exe',addr:'0x401000'};
 expect(selectClaimProjection([entity],selection)).toBe(entity.claimProjection);
 expect(selectClaimProjection([entity],{...selection,binaryHash:'b'.repeat(64)})).toBeUndefined();
 expect(selectClaimProjection([entity,{...entity,sha256:'b'.repeat(64)}],selection)).toBeUndefined();
});
it('allows only server artifact-viewer relative links on both surfaces',()=>{
 for(const parse of [safeClaimHref,staticViews.safeClaimHref]){
  expect(parse('/dashboard/artifact?p=reports%2Freceipt.json')).toBeTruthy();
  for(const href of ['https://evil.invalid','javascript:alert(1)','/dashboard/artifact?p=../secret','/dashboard/artifact?p=%2Fetc%2Fpasswd','/dashboard/artifact?p=a&p=b','/dashboard/artifact?p=a&url=evil','/dashboard/artifact?p=foo%5Cbar'])expect(parse(href)).toBeFalsy();
 }
});

function transport(){
 const requests:Array<{url:string,resolve:(value:unknown)=>void}>=[];
 const sources:any[]=[];
 class Source {events:Record<string,(event:any)=>void>={};onerror?:()=>void;constructor(){sources.push(this);}addEventListener(name:string,fn:any){this.events[name]=fn;}close(){}emit(name:string,data:any){this.events[name]?.({data:JSON.stringify(data)});}}
 const state:any={selection:{slug:'a',locator:'p',program:'target.exe'},entities:[],revision:0,connection:'connecting',source:null,reconnectTimer:0};
 const context={state,URLSearchParams,AbortSignal,EventSource:Source,fetch:(url:string)=>new Promise(resolve=>requests.push({url,resolve})),setTimeout:()=>1,clearTimeout:()=>{},renderTrees(){},renderFeed(){},renderAll(){},renderFunctionTree(){},maybeStartWorkflow(){},API:{snapshot:'/snapshot',activity:'/activity',activityEvents:'/events',functions:'/functions'}};
 const code=functions('selectionKey','binaryKey')+functions('applySnapshot','loadPreparations')+functions('activityQuery','bindResize');
 const api=runInNewContext(code+';({watchActivity,loadSnapshot,loadFunctions,pollActivity,applySnapshot});',context);
 const respond=async(index:number,payload:any)=>{requests[index].resolve({json:async()=>payload});for(let i=0;i<8;i++)await Promise.resolve();};
 return {state,sources,requests,api,respond};
}
const activity=(revision:number,id:string)=>({ok:true,revision,entities:[{id}]});
it('hydrates library when initial SSE wins and never rewinds embedded activity',async()=>{
 const t=transport();t.api.watchActivity();t.api.loadSnapshot();t.sources[0].emit('snapshot',activity(10,'new'));
 await t.respond(0,{ok:true,binaries:[{slug:'a'}],activity:activity(9,'old')});
 expect(t.state.binaries).toEqual([{slug:'a'}]);expect(t.state.entities[0].id).toBe('new');
 t.api.loadSnapshot();t.sources[0].emit('activity',activity(12,'newer'));
 await t.respond(1,{ok:true,binaries:[{slug:'updated'}],activity:activity(11,'old')});
 expect(t.state.binaries[0].slug).toBe('updated');expect(t.state.revision).toBe(12);
});
it('ignores old target responses and closed-stream events',async()=>{
 const t=transport();t.api.watchActivity();t.api.loadSnapshot();t.api.pollActivity();
 t.state.selection={slug:'b',locator:'p',program:'other.exe'};t.api.watchActivity();
 t.sources[1].emit('snapshot',activity(3,'b'));
 await t.respond(0,{ok:true,binaries:[{slug:'a'}],activity:activity(99,'a')});await t.respond(1,activity(99,'a'));
 t.sources[0].emit('snapshot',activity(100,'a'));
 expect(t.state.entities[0].id).toBe('b');expect(t.state.revision).toBe(3);expect(t.state.binaries).toBeUndefined();
});
it('serializes poll, prevents SSE rewind, accepts explicit reset and fallback server restart',async()=>{
 const t=transport();t.api.watchActivity();t.api.pollActivity();t.api.pollActivity();expect(t.requests).toHaveLength(1);
 t.sources[0].emit('snapshot',activity(20,'live'));await t.respond(0,activity(2,'old'));expect(t.state.revision).toBe(20);
 t.api.pollActivity();t.sources[0].emit('reset',activity(1,'reset'));await t.respond(1,activity(25,'prior'));expect(t.state.revision).toBe(1);
 t.sources[0].emit('activity',activity(9,'before-restart'));t.sources[0].onerror();
 await t.respond(2,activity(1,'restart'));expect(t.state.revision).toBe(1);expect(t.state.entities[0].id).toBe('restart');
});

it('ignores old-target function inventory before projecting address-scoped claims',async()=>{
 const t=transport();t.api.loadFunctions();t.state.selection={slug:'b',locator:'p',program:'other.exe'};
 await t.respond(0,{ok:true,results:[{addr:'0x401000',name:'WrongTarget'}],total:1});
 expect(t.state.rows).toBeUndefined();
});
