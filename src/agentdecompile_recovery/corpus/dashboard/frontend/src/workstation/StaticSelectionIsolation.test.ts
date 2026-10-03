/* Source-authored only for Task15.1; NOT executed or collected in this mission.
 * Reuses the existing MatchReview VM/hook harness. Readers, state projection,
 * decompile rendering, and action-body construction are real App code. Only the
 * final shell return is replaced to expose those closures. Effects are deliberately
 * not committed: this fixture does not claim React scheduling, DOM focus, mount/
 * unmount, installed bundle, browser, or live-provider acceptance.
 */
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {createElement} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import * as H from './matchReviewHarness';

const source = readFileSync(new URL('../../../static/workbench-app.js', import.meta.url), 'utf8');
const htmSource = readFileSync(new URL('../../../static/htm.js', import.meta.url), 'utf8');
const A = {addr: '001000', name: 'FunctionA', logicalId: 7};
const B = {addr: '002000', name: 'FunctionB'};
const json = (body: unknown) => new Response(JSON.stringify(body));
const workspace = (row: {addr: string; name: string; logicalId?: number} = A, extra = {}) => ({ok: true, locator: '/project-a', program: 'game.exe',
  slug: 'mapped-artifact', selected: row, listing: {addr: row.addr, name: row.name, preview: row.name + ' listing'},
  decompile: {text: row.name + ' code', source: 'recovered'}, graph: {nodes: [row]}, ...extra});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return {promise, resolve};
}
// Instrumentation type is deliberately narrow to the owned seam; unknown payloads
// are asserted by values below, not converted into successful provider responses.
type AppProbe = {
  selected: typeof A | null; detail: any; graph: any; overview: any; lastDecompile: any;
  selectionKey: string; targetKey: string; decompileDockBody: () => unknown;
  selectRow: (row: typeof B) => Promise<unknown>; selectProgram: (program: string) => void;
  resetTabState: () => void; reloadProject: () => Promise<unknown>;
  setDossier: (value: unknown) => void; setSlug: (value: string) => void;
  setProgram: (value: string) => void; setActiveSession: (value: string) => void;
  setActions: (value: unknown[]) => void; liveToolContext: () => any;
  executeAction: (id: string, params?: unknown, options?: unknown) => Promise<unknown>;
  selectFunctionLeaf: (name: string, addr: string, scope: string) => void;
};
function harness(fetchImpl: (url: string, init?: RequestInit) => Promise<Response>) {
  const htmContext: {htm?: unknown} = {};
  runInNewContext(htmSource, htmContext);
  const attrs = new Map<string, string>();
  const page = {setAttribute: (key: string, value: string) => attrs.set(key, value)};
  const window: any = {location: {search: '?slug=project-slug&program=game.exe', href: 'http://example.test/dashboard',
    hostname: 'example.test'}, setTimeout, clearTimeout};
  const context: any = {React: {createElement, useState: H.useState, useRef: H.useRef,
    useMemo: H.useMemo, useCallback: H.useCallback, useEffect: H.useEffect}, htm: htmContext.htm,
    window, document: {getElementById: (id: string) => id === 'page-context' ? page : null},
    fetch: fetchImpl, URLSearchParams, URL, Response, AbortSignal, setTimeout, clearTimeout,
    localStorage: {getItem: () => null, setItem: () => undefined}};
  const returnMarker = '    return html`<div className="wb">';
  const exportMarker = '  const root = document.getElementById("wb-root");';
  if (!source.includes(returnMarker) || !source.includes(exportMarker)) throw new Error('App instrumentation boundary moved');
  const code = source.replace(returnMarker, `    return { selected, detail, graph, overview, lastDecompile,
    selectionKey, targetKey, decompileDockBody, selectRow, selectProgram, resetTabState, reloadProject,
    setDossier, setSlug, setProgram, setActiveSession, setActions, liveToolContext, executeAction,
    selectFunctionLeaf };\n${returnMarker}`).replace(exportMarker, `  window.TestApp = App;\n${exportMarker}`);
  runInNewContext(code, context);
  function render(): AppProbe {
    H.beginRender();
    H.markMounted();
    return window.TestApp();
  }
  let app = render();
  app.setDossier({ok: true, locator: '/project-a', programs: ['game.exe']});
  app.setActiveSession('session-a');
  app.setActions([{id: 'mcp.inspect-memory', danger: false, mutating: false}]);
  app = render();
  return {render, attrs, app};
}

beforeEach(() => { H.reset(); vi.useFakeTimers(); vi.clearAllTimers(); });
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });

describe('static App captured selection and actual consumers (unrun source fixtures)', () => {
  it('ignores A after B, including follow-on evidence; action context and page remain B', async () => {
    const a = deferred<Response>(), b = deferred<Response>();
    const calls: string[] = []; let actionBody: any;
    const h = harness(async (url, init) => {
      calls.push(url);
      if (url.includes('/workspace?')) return url.includes('addr=001000') ? a.promise : b.promise;
      if (url === '/api/v1/actions/mcp/inspect-memory') { actionBody = JSON.parse(String(init?.body)); return json({ok: true}); }
      throw new Error('Unexpected read: ' + url);
    });
    const pa = h.app.selectRow(A), pb = h.app.selectRow(B);
    // Same event turn, before a render: action defaults still have to use B.
    await h.app.executeAction('mcp.inspect-memory', {}, {skipConfirm: true});
    expect(actionBody.context.addr).toBe(B.addr);
    b.resolve(json(workspace(B))); await pb;
    a.resolve(json(workspace(A, {decompile: null}))); await pa;
    const app = h.render();
    expect(app.selected?.addr).toBe(B.addr);
    expect(app.detail.decompile.text).toBe('FunctionB code');
    expect(calls.filter(url => url.includes('/function?'))).toHaveLength(0);
    expect(h.attrs.get('data-addr')).toBe(B.addr);
    expect(h.attrs.get('data-logical-id')).toBe('');
    await app.executeAction('mcp.inspect-memory', {}, {skipConfirm: true});
    expect(actionBody.context).toMatchObject({addr: B.addr, name: B.name, program: 'game.exe', slug: 'project-slug', locator: '/project-a'});
  });

  it('masks A on the first B render while preserving A as a labeled previous function', async () => {
    const b = deferred<Response>();
    const h = harness(async url => url.includes('addr=001000') ? json(workspace()) : b.promise);
    await h.app.selectRow(A);
    let app = h.render();
    const oldKey = app.selectionKey;
    void app.selectRow(B);
    app = h.render(); // No effects have run: masking must already hold.
    expect(app.selected?.addr).toBe(B.addr);
    expect(app.detail).toBeNull(); expect(app.graph).toBeNull(); expect(app.overview).toBeNull();
    expect(app.selectionKey).not.toBe(oldKey);
    expect(app.lastDecompile).toMatchObject({addr: A.addr, name: A.name});
    expect(H.text(app.decompileDockBody())).toContain('previous function @ ' + A.addr);
    expect(H.text(app.decompileDockBody())).not.toContain('Decompile: FunctionB');
  });

  it.each(['queued', 'empty', 'failed'])('refuses late fallback %s packets', async status => {
    const a = deferred<Response>(), b = deferred<Response>();
    const h = harness(async url => url.includes('addr=001000') ? a.promise : b.promise);
    h.app.setDossier({ok: true, locator: ''}); h.app.setProgram('');
    let app = h.render();
    const pa = app.selectRow(A); void app.selectRow(B);
    a.resolve(json(status === 'empty' ? {} : {ok: status !== 'failed', error: status === 'failed' ? 'A failed' : '', evidenceRequest: {status}}));
    await pa;
    app = h.render();
    expect(app.selected?.addr).toBe(B.addr); expect(app.detail).toBeNull(); expect(app.lastDecompile).toBeNull();
  });

  it('ignores A evidence that settles while B workspace is pending, without scheduling retries', async () => {
    const evidence = deferred<Response>(), b = deferred<Response>(); let reads = 0;
    const h = harness(async url => {
      if (url.includes('/workspace?')) return url.includes('addr=001000') ? json(workspace(A, {decompile: null})) : b.promise;
      if (url.includes('/function?')) { reads++; return evidence.promise; }
      throw new Error(url);
    });
    await h.app.selectRow(A);
    void h.app.selectRow(B);
    evidence.resolve(json({decompile: {text: 'late A'}, evidenceRequest: {status: 'queued'}}));
    for (let i = 0; i < 8; ++i) await Promise.resolve();
    await vi.advanceTimersByTimeAsync(3000);
    const app = h.render();
    expect(reads).toBe(1); expect(app.detail).toBeNull(); expect(app.lastDecompile).toBeNull();
    expect(app.selected?.addr).toBe(B.addr);
  });

  it('refuses delayed evidence and diagnostic lookup after B intent', async () => {
    const evidence = deferred<Response>(), diagnostic = deferred<Response>(), b = deferred<Response>();
    const calls: string[] = [];
    const h = harness(async url => {
      calls.push(url);
      if (url.includes('/workspace?')) return url.includes('addr=001000') ? json(workspace(A, {decompile: null})) : b.promise;
      if (url.includes('/function?')) return evidence.promise;
      if (url.endsWith('/jobs/job-a')) return diagnostic.promise;
      throw new Error(url);
    });
    await h.app.selectRow(A);
    evidence.resolve(json({decompile: {text: 'late A'}, evidenceRequest: {status: 'failed', jobId: 'job-a'}}));
    for (let i = 0; i < 8; ++i) await Promise.resolve();
    expect(calls.some(url => url.endsWith('/jobs/job-a'))).toBe(true);
    void h.app.selectRow(B);
    diagnostic.resolve(json({job: {log: '**State:** `authentication-failed`'}}));
    for (let i = 0; i < 8; ++i) await Promise.resolve();
    const app = h.render();
    expect(app.selected?.addr).toBe(B.addr); expect(app.detail).toBeNull(); expect(app.lastDecompile).toBeNull();
  });

  it('separates requested data address from mapped artifact and function center', async () => {
    const h = harness(async () => json(workspace(A)));
    await h.app.selectRow({addr: '001080', name: 'data'});
    const app = h.render();
    expect(app.selected?.addr).toBe('001080');
    expect(app.detail.resolvedFunction).toMatchObject(A);
    expect(app.detail.resolvedSlug).toBe('mapped-artifact');
    expect(app.liveToolContext()).toMatchObject({addr: '001080', slug: 'project-slug'});
    expect(app.graph).toBeNull();
    expect(H.text(app.decompileDockBody())).toContain('previous function @ ' + A.addr);
  });

  it('isolates same address/program across locator and session and refuses the old tree callback', async () => {
    const h = harness(async () => json(workspace()));
    await h.app.selectRow(A);
    let app = h.render(); const old = app; const oldKey = app.selectionKey;
    app.setDossier({ok: true, locator: '/project-b', programs: ['game.exe']});
    app.setActiveSession('session-b');
    app = h.render();
    expect(app.detail).toBeNull(); expect(app.lastDecompile).toBeNull();
    expect(app.selectionKey).not.toBe(oldKey);
    expect(h.attrs.get('data-addr')).toBe('');
    old.selectFunctionLeaf(A.name, A.addr, old.targetKey);
    expect(h.render().selected).toBeNull();
    expect(app.liveToolContext()).toMatchObject({addr: '', name: '', locator: '/project-b'});
  });

  it('ensure first-row and nested workspace cannot steal an explicit row', async () => {
    const ensure = deferred<Response>(), workspaceRead = deferred<Response>();
    const calls: string[] = [];
    const h = harness(async url => {
      calls.push(url);
      if (url.includes('/sessions')) return json({ok: true});
      if (url.includes('/ensure-program')) return ensure.promise;
      if (url.includes('/workspace?')) return workspaceRead.promise;
      throw new Error(url);
    });
    h.app.selectProgram('game.exe');
    void h.app.selectRow(B);
    ensure.resolve(json({ok: true, ensured: true, results: [A]}));
    workspaceRead.resolve(json(workspace()));
    for (let i = 0; i < 12; ++i) await Promise.resolve();
    const app = h.render();
    expect(app.selected?.addr).toBe(B.addr);
    expect(calls.filter(url => url.includes('/workspace?'))).toHaveLength(2);
  });

  it('reload cannot continue past its first await after a target switch', async () => {
    const inventory = deferred<Response>(); const calls: string[] = [];
    const h = harness(async url => { calls.push(url); return inventory.promise; });
    const reload = h.app.reloadProject();
    h.app.setDossier({ok: true, locator: '/project-b'});
    inventory.resolve(json({binaries: []})); await reload;
    expect(calls).toEqual(['/dashboard/api/workbench/binaries']);
    expect(h.render().detail).toBeNull(); expect(h.attrs.get('data-addr')).toBe('');
  });

  it('keeps the Listing identity stable during a current queued-to-complete refresh', async () => {
    let evidenceReads = 0;
    const h = harness(async url => {
      if (url.includes('/workspace?')) return json(workspace(A, {decompile: null}));
      if (url.includes('/function?')) {
        evidenceReads++;
        return json(evidenceReads === 1 ? {evidenceRequest: {status: 'queued'}}
          : {addr: A.addr, name: A.name, decompile: {text: 'fresh A'}, evidenceRequest: {status: 'ok'}});
      }
      throw new Error(url);
    });
    await h.app.selectRow(A);
    for (let i = 0; i < 8; ++i) await Promise.resolve();
    const before = h.render();
    await vi.advanceTimersByTimeAsync(3000);
    const after = h.render();
    expect(after.selectionKey).toBe(before.selectionKey);
    expect(after.detail.decompile.text).toBe('fresh A');
    expect(after.detail.resolvedSlug).toBe('mapped-artifact');
    expect(after.lastDecompile).toMatchObject({addr: A.addr, name: A.name, text: 'fresh A'});
  });

  it('clearing selection cancels retry admission and erases page address/name/logical id', async () => {
    let reads = 0;
    const h = harness(async url => {
      if (url.includes('/workspace?')) return json(workspace(A, {decompile: null}));
      if (url.includes('/function?')) { reads++; return json({evidenceRequest: {status: 'queued'}}); }
      throw new Error(url);
    });
    await h.app.selectRow(A);
    for (let i = 0; i < 8; ++i) await Promise.resolve();
    h.app.resetTabState();
    await vi.advanceTimersByTimeAsync(3000);
    expect(reads).toBe(1);
    expect(h.attrs.get('data-addr')).toBe(''); expect(h.attrs.get('data-name')).toBe('');
    expect(h.attrs.get('data-logical-id')).toBe(''); expect(h.render().detail).toBeNull();
  });
});
