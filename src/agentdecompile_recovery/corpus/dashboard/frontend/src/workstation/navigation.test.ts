import {expect, test} from 'vitest';
import {emptySelection} from '../contracts';
import {readRoute,routeUrl} from './navigation';
test('shared URL restores exact target and view instead of mixing another saved binary',()=>{
  const target={selection:{...emptySelection,slug:'elf one',addr:'0x401000',locator:'/a & b/project.gpr'},tab:'Graph' as const};
  const url=routeUrl('http://localhost/react/?binary=stale&other=keep',target);
  const restored=readRoute(new URL(url,'http://localhost').search,{selection:{...emptySelection,program:'unrelated.exe'},tab:'Decompiler'});
  expect(restored).toEqual(target);
  expect(url).toContain('other=keep');
  expect(url).not.toContain('binary=');
  expect(readRoute('?view=invalid',target).tab).toBe('Graph');
});

test('hex page changes survive share and reload, including zero boundary',async()=>{
  const {hexPageSelection}=await import('./navigation');
  const selection={...emptySelection,binaryHash:'local-hash',addr:'0x400'};
  const next={selection:{...selection,...hexPageSelection(selection.addr,1)},tab:'Hex' as const};
  expect(next.selection.addr).toBe('0x800');
  expect(readRoute(new URL(routeUrl('http://localhost/react/',next),'http://localhost').search,{selection:emptySelection,tab:'Info'})).toEqual(next);
  expect(hexPageSelection('0x20',-1).addr).toBe('0x0');
});
test('modal and handled keyboard events cannot invoke global shortcuts',async()=>{
  const {shellShortcut}=await import('./navigation');
  const event={key:'p',ctrlKey:true,metaKey:false,defaultPrevented:false};
  expect(shellShortcut(event,false)).toBe('functions');
  expect(shellShortcut({...event,key:'k'},false)).toBe('commands');
  for(const key of ['p','k','Escape']){
    expect(shellShortcut({...event,key},true)).toBeNull();
    expect(shellShortcut({...event,key,defaultPrevented:true},false)).toBeNull();
  }
});
test('reference adapter pages beyond first backend prefix for every direction',async()=>{
  const {referenceParams}=await import('./navigation');
  for(const mode of ['to','from','function'] as const){
    expect(referenceParams('0x401000',mode,80)).toEqual({addressOrSymbol:'0x401000',mode,offset:0,limit:160});
    expect(referenceParams('0x401000',mode,800).limit).toBe(800);
  }
});
test('prepare is offered only for a successfully loaded unfiltered recorded inventory',async()=>{
  const {canPrepareAnalysis}=await import('./navigation');
  const loaded={local:false,selected:true,loading:false,error:'',filter:'',count:0,advertised:true};
  expect(canPrepareAnalysis(loaded)).toBe(true);
  for(const patch of [{local:true},{selected:false},{loading:true},{error:'offline'},{filter:'no match'},{count:1},{advertised:false},{offset:80}])expect(canPrepareAnalysis({...loaded,...patch})).toBe(false);
});
