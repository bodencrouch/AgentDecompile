/* Source-only regression additions. These use the existing Vitest hook shim;
 * they do not establish React DOM/browser acceptance and are not yet executed. */
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {createElement} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {Data} from '../contracts';
import {emptySelection} from '../contracts';
import {CoverageMatrix, matrixTierCell} from './coverageMatrix';
import * as H from './matchReviewHarness';

vi.mock('react', async orig => {
  const real = await (orig() as Promise<Record<string, unknown>>);
  const shim = await import('./matchReviewHarness');
  return {...real, useState: shim.useState, useEffect: shim.useEffect, useRef: shim.useRef};
});
vi.mock('../ui', async orig => ({
  ...await (orig() as Promise<Record<string, unknown>>),
  // Only the list/detail reads are isolated here; report requests use the real
  // request() path and controlled fetch promises (including ignored aborts).
  useData: (url: string | null) => ({key:url,loading:false,error:'',data:{
    corpus:{identity:'corpus-one'},rows:[],members:[],name:'Recorded root',
  }}),
}));
const {LogicalNavigator} = await import('./LogicalNavigator');

const source = readFileSync(new URL('../../../static/workbench-app.js', import.meta.url), 'utf8');
const start = source.indexOf('  function staticMatrixCell(');
const end = source.indexOf('  // Corpus status and corpus-db identity settle independently:', start);
if (start < 0 || end < 0) throw new Error('static matrix source markers missing');
const matrixCode = source.slice(start, end);
const htmContext: {htm?: (...args: unknown[]) => unknown} = {};
runInNewContext(readFileSync(new URL('../../../static/htm.js', import.meta.url), 'utf8'), htmContext);
const html = htmContext.htm!.bind(createElement);
const staticCell = runInNewContext(`${matrixCode}; staticMatrixCell;`, {}) as (body:Data,expected:Data)=>Data;
const hash = 'a'.repeat(64), digest = 'd'.repeat(64);
const expected = {logicalId:'7',corpusIdentity:'corpus-one',slug:'build-a',contentSha256:hash,expectedVersion:hash};

function report(logicalId=7, zero=false):Data {
  const keys=zero?[]:[`${hash}:64`,`${hash}:6e`];
  const binary={id:1,slug:'build-a',content_sha256:hash,version:hash};
  const scope={kind:'logical_function',logical_id:logicalId};
  return {ok:true,status:'available',report:{binary,selection_scope:{...scope},report_sha256:digest},matrix_projection:{
    corpus_identity:'corpus-one',binary:{...binary,report_sha256:digest},selection_scope:{...scope},
    freshness:{status:'current'},provider:{status:'not_connected',reason:'provider unavailable'},
    unbound:null,unbound_status:'not_requested',rows:[{
      logical_id:logicalId,stable_key:'RecordedRoot',physical_members:keys.length,member_keys:keys,
      verified:{status:'unavailable',functions:null,bytes:null,member_keys:[]},
      advisory:{functions:zero?0:1,bytes:zero?0:null,member_keys:keys.slice(0,1)},
      unclassified:{functions:zero?0:1,bytes:zero?0:20,member_keys:keys.slice(1)},
      unknown_extent_members:zero?0:1,
    }],
  }};
}

function cells(body:Data, basis=expected) {
  return {react:matrixTierCell(body,basis),static:staticCell(body,{
    logicalId:basis.logicalId,corpusIdentity:basis.corpusIdentity,slug:basis.slug,version:basis.expectedVersion,
  })};
}
function refused(body:Data, basis=expected) {
  const both=cells(body,basis);
  expect(both.react.status).toBe('unavailable');
  expect(both.static.advisory).toMatch(/^Unavailable/);
  expect(both.static.unclassified).toMatch(/^Unavailable/);
}

describe('both exact selected matrix validators',()=>{
  it('keeps advisory, unknown bytes and unavailable verified metrics distinct',()=>{
    const both=cells(report());
    expect(both.react.status).toBe('available');
    expect(both.react.advisory).toMatchObject({functions:1,bytes:null});
    expect(both.react.verified.status).toBe('unavailable');
    expect(both.static.advisory).toBe('1');
    expect(both.static.verified).toBe('Unavailable · provider unavailable');
  });
  it('accepts one explicit empty selected row, while verified stays unavailable',()=>{
    const both=cells(report(7,true));
    expect(both.react.advisory.functions).toBe(0);
    expect(both.react.unclassified.functions).toBe(0);
    expect(both.react.verified.status).toBe('unavailable');
    expect(both.static.advisory).toBe('0');
  });
  it.each([
    (body:Data)=>{delete body.matrix_projection.selection_scope;},
    (body:Data)=>{delete body.report.selection_scope;},
    (body:Data)=>{body.matrix_projection.selection_scope.logical_id=8;},
    (body:Data)=>{body.report.selection_scope.logical_id=8;},
    (body:Data)=>{body.matrix_projection.selection_scope.logical_id='7';},
    (body:Data)=>{body.matrix_projection.selection_scope.extra=true;},
    (body:Data)=>{body.matrix_projection.rows.push({...body.matrix_projection.rows[0]});},
    (body:Data)=>{body.matrix_projection.rows.push({...body.matrix_projection.rows[0],logical_id:8});},
    (body:Data)=>{body.matrix_projection.rows=[];},
    (body:Data)=>{body.matrix_projection.rows[0].logical_id=8;},
    (body:Data)=>{body.matrix_projection.unbound={physical_members:0};},
    (body:Data)=>{delete body.matrix_projection.unbound_status;},
  ])('refuses absent, duplicate or mixed logical scopes (%#)',mutate=>{
    const body=report();mutate(body);refused(body);
  });
  it.each([
    (body:Data)=>{body.ok=false;body.status='unavailable';},
    (body:Data)=>{body.matrix_projection.corpus_identity='other';},
    (body:Data)=>{body.matrix_projection.freshness.status='stale';},
    (body:Data)=>{body.matrix_projection.binary.slug='other';},
    (body:Data)=>{body.matrix_projection.binary.version='b'.repeat(64);},
    (body:Data)=>{body.matrix_projection.binary.content_sha256='b'.repeat(64);},
    (body:Data)=>{body.matrix_projection.binary.report_sha256='bad';},
    (body:Data)=>{body.matrix_projection.binary.report_sha256=digest+'\n';body.report.report_sha256=digest+'\n';},
    (body:Data)=>{body.report.report_sha256='e'.repeat(64);},
    (body:Data)=>{body.report.binary.slug='other';},
    (body:Data)=>{body.matrix_projection.rows[0].physical_members=3;},
    (body:Data)=>{body.matrix_projection.rows[0].member_keys.push(body.matrix_projection.rows[0].member_keys[0]);},
    (body:Data)=>{body.matrix_projection.rows[0].advisory.member_keys.push('foreign');},
    (body:Data)=>{body.matrix_projection.rows[0].unclassified.member_keys=body.matrix_projection.rows[0].advisory.member_keys;},
    (body:Data)=>{body.matrix_projection.rows[0].unclassified.functions=0;},
    (body:Data)=>{body.matrix_projection.rows[0].verified.functions=0;},
    (body:Data)=>{body.matrix_projection.rows[0].verified.bytes=0;},
    (body:Data)=>{body.matrix_projection.rows[0].verified={status:'available',functions:0,bytes:0,member_keys:[]};},
  ])('preserves exact build, digest, conservation and provider gates (%#)',mutate=>{
    const body=report();mutate(body);refused(body);
  });
  it.each(['07','+7','-7','0','7\n','9007199254740992'])('refuses noncanonical expected selection %s',logicalId=>{
    refused(report(),{...expected,logicalId});
  });
});

const json=(body:Data)=>new Response(JSON.stringify(body));
type Pending={url:string;signal:AbortSignal;resolve:(body:Response)=>void};
let pending:Pending[];
let fetchImpl:(url:string,init?:RequestInit)=>Promise<Response>;

beforeEach(()=>{
  H.reset();pending=[];
  fetchImpl=(url,init)=>{
    if(url.includes('progress-report'))return new Promise(resolve=>pending.push({url,signal:init!.signal as AbortSignal,resolve}));
    if(url.includes('browse-block'))return Promise.resolve(json({corpus:{identity:'corpus-one'},rows:[{id:7},{id:8}]}));
    if(url.includes('/logical/'))return Promise.resolve(json({corpus:{identity:'corpus-one'},members:[]}));
    throw new Error('unhandled test fetch: '+url);
  };
  vi.stubGlobal('fetch',(url:string,init?:RequestInit)=>fetchImpl(String(url),init));
});
afterEach(()=>{H.unmount();vi.unstubAllGlobals();});

function makeStatic(){
  return runInNewContext(`${matrixCode}; LogicalMatrix;`,{
    html,API:{progressReport:'/dashboard/api/workbench/progress-report'},
    useState:H.useState,useEffect:H.useEffect,URLSearchParams,AbortController,AbortSignal,
    fetch:(url:string,init?:RequestInit)=>fetchImpl(url,init),
  }) as (props:{binaries:Data[];corpusIdentity:string;revision:number})=>unknown;
}
function reactReports(tree:unknown):Record<string,Data>{
  const node=H.findAll(tree,n=>n.type===CoverageMatrix)[0];
  return node?.props?.tierReportsBySlug as Record<string,Data>||{};
}
const builds=()=>[{slug:'build-a',content_sha256:hash}];

describe('existing matrix request lifecycles',()=>{
  it('React sends the selected ID and keeps equal-content binary refresh stable',async()=>{
    let props={selection:{...emptySelection,logicalId:'7',corpusIdentity:'corpus-one'},binaries:builds(),
      corpus:{key:null,data:{corpus:{identity:'corpus-one'}},error:'',loading:false},revision:0,onSelect:vi.fn(),onMember:vi.fn()};
    let tree=H.render(LogicalNavigator,props);
    tree=await H.flush(LogicalNavigator,props,tree,20);
    expect(pending).toHaveLength(1);
    expect(new URL(pending[0].url,'https://fixture.invalid').searchParams.get('logicalId')).toBe('7');
    pending[0].resolve(json(report()));
    tree=await H.flush(LogicalNavigator,props,tree,20);
    expect(reactReports(tree)['build-a'].matrix_projection.selection_scope.logical_id).toBe(7);
    props={...props,binaries:builds()};
    tree=H.render(LogicalNavigator,props);
    await H.flush(LogicalNavigator,props,tree,20);
    expect(pending).toHaveLength(1);
    H.unmount();
  });
  it('React aborts a changed selection and ignores its late completion',async()=>{
    let props={selection:{...emptySelection,logicalId:'7',corpusIdentity:'corpus-one'},binaries:builds(),
      corpus:{key:null,data:{corpus:{identity:'corpus-one'}},error:'',loading:false},revision:0,onSelect:vi.fn(),onMember:vi.fn()};
    let tree=H.render(LogicalNavigator,props);
    tree=await H.flush(LogicalNavigator,props,tree,20);
    const old=pending[0];
    props={...props,selection:{...props.selection,logicalId:'8'}};
    tree=H.render(LogicalNavigator,props);
    tree=await H.flush(LogicalNavigator,props,tree,20);
    expect(old.signal.aborted).toBe(true);
    expect(new URL(pending[1].url,'https://fixture.invalid').searchParams.get('logicalId')).toBe('8');
    pending[1].resolve(json(report(8)));
    tree=await H.flush(LogicalNavigator,props,tree,20);
    old.resolve(json(report(7)));
    tree=await H.flush(LogicalNavigator,props,tree,20);
    expect(reactReports(tree)['build-a'].matrix_projection.selection_scope.logical_id).toBe(8);
    H.unmount();
    expect(H.setStateAfterUnmountCount()).toBe(0);
  });
  it('static sends the selected ID and keeps equal-content binary refresh stable',async()=>{
    const Matrix=makeStatic();let props={binaries:builds(),corpusIdentity:'corpus-one',revision:0};
    let tree=H.render(Matrix,props);tree=await H.flush(Matrix,props,tree,20);
    (H.findAll(tree,n=>n.type==='select')[0].props!.onChange as (event:unknown)=>void)({target:{value:'7'}});
    tree=H.render(Matrix,props);tree=await H.flush(Matrix,props,tree,20);
    expect(pending).toHaveLength(1);
    expect(new URL(pending[0].url,'https://fixture.invalid').searchParams.get('logicalId')).toBe('7');
    pending[0].resolve(json(report()));tree=await H.flush(Matrix,props,tree,20);
    expect(H.text(tree)).toContain('Unavailable · provider unavailable');
    props={...props,binaries:builds()};tree=H.render(Matrix,props);
    await H.flush(Matrix,props,tree,20);
    expect(pending).toHaveLength(1);
    H.unmount();
  });
  it('static aborts changed selection and ignores its late completion',async()=>{
    const Matrix=makeStatic(),props={binaries:builds(),corpusIdentity:'corpus-one',revision:0};
    let tree=H.render(Matrix,props);tree=await H.flush(Matrix,props,tree,20);
    const choose=(value:string)=>{
      (H.findAll(tree,n=>n.type==='select')[0].props!.onChange as (event:unknown)=>void)({target:{value}});
      tree=H.render(Matrix,props);
    };
    choose('7');tree=await H.flush(Matrix,props,tree,20);const old=pending[0];
    choose('8');tree=await H.flush(Matrix,props,tree,20);
    expect(old.signal.aborted).toBe(true);
    expect(new URL(pending[1].url,'https://fixture.invalid').searchParams.get('logicalId')).toBe('8');
    const fresh=report(8,true);fresh.matrix_projection.provider.reason='fresh-eight';
    pending[1].resolve(json(fresh));tree=await H.flush(Matrix,props,tree,20);
    old.resolve(json(report(7)));tree=await H.flush(Matrix,props,tree,20);
    expect(H.text(tree)).toContain('Unavailable · fresh-eight');
    expect(H.text(tree)).not.toContain('Unavailable · provider unavailable');
    H.unmount();
    expect(H.setStateAfterUnmountCount()).toBe(0);
  });
});
