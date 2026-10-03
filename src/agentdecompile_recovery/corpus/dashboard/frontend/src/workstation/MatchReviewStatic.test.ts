/*
 * Equivalent behaviour tests for the ReviewReact section of
 * static/workbench-app.js (the /dashboard mirror of MatchReview.tsx), sliced
 * with node:vm the same way src/preparationBudget.test.tsx and
 * src/ScopedClaims.test.tsx already slice this file. Hooks are the same
 * test-only shim used for MatchReview.test.tsx: there is no jsdom or
 * @testing-library/react here, so useState/useEffect/useRef/useMemo are
 * provided as plain functions in the vm sandbox instead of the real
 * React global the file normally destructures them from.
 */
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {createElement} from 'react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import * as H from './matchReviewHarness';

const source = readFileSync(new URL('../../../static/workbench-app.js', import.meta.url), 'utf8');
const htmSource = readFileSync(new URL('../../../static/htm.js', import.meta.url), 'utf8');
const htmContext: {htm?: (...args: unknown[]) => unknown} = {};
runInNewContext(htmSource, htmContext);
const html = (htmContext.htm as (...args: unknown[]) => unknown).bind(createElement) as (...args: unknown[]) => unknown;

function slice(startMarker: string, endMarker: string): string {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  if (start < 0 || end < 0) throw new Error(`marker not found: ${startMarker} .. ${endMarker}`);
  return source.slice(start, end);
}

const reviewCode = slice('  const REVIEW_ERRORS = {', '  function StepLadder(');
const API = {matchReview: '/api/matchReview', matchDecideBatch: '/api/matchDecideBatch', jobs: '/api/v1/jobs'};

function makeReviewReact(locationSearch: string, fetchImpl: (url: string, init?: unknown) => Promise<Response>) {
  const context: Record<string, unknown> = {
    html, API, URLSearchParams, encodeURIComponent, Number, String, Boolean, Array, JSON, Promise,
    useState: H.useState, useEffect: H.useEffect, useRef: H.useRef, useMemo: H.useMemo,
    window: {location: {search: locationSearch}},
    fetch: (...args: [string, unknown?]) => fetchImpl(...args),
    setTimeout: (...args: [() => void, number]) => (globalThis as typeof globalThis).setTimeout(...args),
    clearTimeout: (...args: [number]) => (globalThis as typeof globalThis).clearTimeout(...args),
  };
  const ReviewReact = runInNewContext(`${reviewCode}; ReviewReact;`, context) as (props: {onRefresh?: () => void}) => unknown;
  return ReviewReact;
}

function row(id: number, token: string) {
  return {match: {id, src_binary: 'a.exe', dst_binary: 'b.exe', src_addr: 0x1000, dst_addr: 0x2000, score: 0.9, margin: 0.1}, binaries: [{}, {}], token};
}
function page(rows: ReturnType<typeof row>[], selection = 'sel-1') {
  return {rows, total: rows.length, nextAfterId: null, selection};
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});

describe('ReviewReact (static workbench-app.js)', () => {
  beforeEach(() => {
    H.reset();
    vi.useFakeTimers({toFake: ['setTimeout', 'clearTimeout']});
    // A test that clicks 'Stop waiting' (or otherwise abandons a poll loop)
    // without draining it leaves a pending fake setTimeout queued on the
    // clock. Vitest's own useFakeTimers() re-install does not discard it, so
    // a LATER test's own vi.advanceTimersByTimeAsync() can fire that stale
    // callback: it resumes a previous test's send()/watch() closure, which
    // reads its OWN mountedRef (a stale, never-invalidated object reference,
    // still true) and this module's *current* `mounted` (now false, from the
    // current test's own H.unmount()) — passing that closure's own guard while
    // still incrementing this test's setStateAfterUnmountCount. Clearing timers
    // up front removes the leftover callback before it can fire here.
    vi.clearAllTimers();
  });

  it('shows pending after a 202, and the outcome only after a terminal job result', async () => {
    // Same shape as the React test: observeReviewDecision's internal loop and
    // its 750ms delay run inside one await with no re-render mid-loop, so two
    // "running" responses require two timer advances before the outcome shows.
    let jobPolls = 0;
    const ReviewReact = makeReviewReact('', async (url: string) => {
      if (url.includes('matchDecideBatch')) return json({job_id: 'job-1'}, 202);
      if (url.includes('/api/v1/jobs/')) {
        jobPolls++;
        if (jobPolls < 3) return json({job: {status: 'running'}});
        return json({job: {status: 'ok', log: JSON.stringify({ok: true, acceptance: 'review-decision-only', decisions: [{matchId: 1, status: 'verify'}]})}});
      }
      return json(page([row(1, 'tok-1')]));
    });

    let tree = H.render(ReviewReact, {});
    tree = await H.flush(ReviewReact, {}, tree);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(ReviewReact, {});
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(ReviewReact, {}, tree);
    expect(H.text(tree)).toContain('Decision sent as job job-1');
    expect(H.text(tree)).not.toContain('moved to verification');
    expect(jobPolls).toBe(1);

    await vi.advanceTimersByTimeAsync(750);
    tree = await H.flush(ReviewReact, {}, tree);
    expect(H.text(tree)).toContain('Decision sent as job job-1');
    expect(H.text(tree)).not.toContain('moved to verification');
    expect(jobPolls).toBe(2);

    await vi.advanceTimersByTimeAsync(750);
    tree = await H.flush(ReviewReact, {}, tree);
    expect(H.text(tree)).toContain('Match 1 moved to verification.');
  });

  it('"Stop waiting" keeps the job ID and the "Check result" control', async () => {
    const ReviewReact = makeReviewReact('', async (url: string) => {
      if (url.includes('matchDecideBatch')) return json({job_id: 'job-9'}, 202);
      if (url.includes('/api/v1/jobs/')) return json({job: {status: 'running'}});
      return json(page([row(9, 'tok-9')]));
    });

    let tree = H.render(ReviewReact, {});
    tree = await H.flush(ReviewReact, {}, tree);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(ReviewReact, {});
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(ReviewReact, {}, tree);

    (H.findByTagAndText(tree, 'button', 'Stop waiting')[0].props!.onClick as () => void)();
    tree = H.render(ReviewReact, {});
    expect(H.text(tree)).toContain('Stopped waiting for job job-9');
    const checkResult = H.findByTagAndText(tree, 'button', 'Check result')[0];
    expect(checkResult).toBeTruthy();
    expect(checkResult.props!.disabled).toBeFalsy();
  });

  it('starts no poll after unmount during an in-flight submit', async () => {
    let resolveSubmit!: (value: Response) => void;
    const ReviewReact = makeReviewReact('', async (url: string) => {
      if (url.includes('matchDecideBatch')) return new Promise<Response>(resolve => {resolveSubmit = resolve;});
      if (url.includes('/api/v1/jobs/')) return json({job: {status: 'running'}});
      return json(page([row(5, 'tok-5')]));
    });

    let tree = H.render(ReviewReact, {});
    tree = await H.flush(ReviewReact, {}, tree);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(ReviewReact, {});
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    H.unmount();

    resolveSubmit(json({job_id: 'job-5'}, 202));
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    await vi.advanceTimersByTimeAsync(750 * 3);
    await Promise.resolve(); await Promise.resolve();

    expect(H.setStateAfterUnmountCount()).toBe(0);
  });

  it('shows the refusal text for a stale_basis decision and refreshes the rows', async () => {
    let reviewFetches = 0;
    // Gate the 2nd matchReview response (from reload() inside send()'s catch)
    // behind an explicit resolve: that reload's own success handler does
    // setError("") (workbench-app.js, same load effect as line ~1054), which
    // races the "still shows the refusal text" assertion below against
    // H.flush()'s fixed tick count. This happened to keep passing because the
    // extra .then()/.catch() hop in this fetch chain takes one more microtask
    // tick than the flush budget drains before the assertion — an accident of
    // this component's exact chain shape, not a guarantee. Gating removes the
    // race outright (see the equivalent, previously-flaky fix in
    // MatchReview.test.tsx for the TSX component, which the same race did trip).
    let resolveSecondReview: (() => void) | null = null;
    const ReviewReact = makeReviewReact('', async (url: string) => {
      if (url.includes('matchDecideBatch')) return json({error: 'stale_basis'}, 409);
      if (url.includes('matchReview')) {
        reviewFetches++;
        if (reviewFetches > 1) await new Promise<void>(resolve => {resolveSecondReview = resolve;});
        return json(page([row(3, 'tok-3')]));
      }
      throw new Error(`unhandled: ${url}`);
    });

    let tree = H.render(ReviewReact, {});
    tree = await H.flush(ReviewReact, {}, tree);
    expect(reviewFetches).toBe(1);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(ReviewReact, {});
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(ReviewReact, {}, tree);

    expect(reviewFetches).toBe(2);
    expect(H.text(tree)).toContain('A row changed after you loaded it');

    resolveSecondReview!();
    tree = await H.flush(ReviewReact, {}, tree);
  });

  it('select-all covers only decidable rows on the current page', async () => {
    const rows = [row(1, 'tok-a'), row(2, 'tok-b'), row(3, 'tok-c')];
    const ReviewReact = makeReviewReact('', async (url: string) => {
      if (url.includes('matchDecideBatch')) return json({job_id: 'job-lock'}, 202);
      if (url.includes('/api/v1/jobs/')) return json({job: {status: 'running'}});
      return json(page(rows));
    });

    let tree = H.render(ReviewReact, {});
    tree = await H.flush(ReviewReact, {}, tree);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(ReviewReact, {});
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(ReviewReact, {}, tree);

    const selectAll = H.findAll(tree, n => n.type === 'input' && n.props?.['aria-label'] === 'Select all rows on this page')[0];
    (selectAll.props!.onChange as (e: {target: {checked: boolean}}) => void)({target: {checked: true}});
    tree = H.render(ReviewReact, {});

    const boxes = H.findAll(tree, n => n.type === 'input' && typeof n.props?.['aria-label'] === 'string' && (n.props?.['aria-label'] as string).startsWith('Select match'));
    expect(boxes.find(n => n.props?.['aria-label'] === 'Select match 1')!.props!.checked).toBe(false);
    expect(boxes.find(n => n.props?.['aria-label'] === 'Select match 2')!.props!.checked).toBe(true);
    expect(boxes.find(n => n.props?.['aria-label'] === 'Select match 3')!.props!.checked).toBe(true);
  });

  it('keeps a checked row that is still on the page after a revision bump, by token identity', async () => {
    let fetchImpl = async () => json(page([row(1, 'tok-a'), row(2, 'tok-b')]));
    const ReviewReact = makeReviewReact('', () => fetchImpl());
    let tree = H.render(ReviewReact, {});
    tree = await H.flush(ReviewReact, {}, tree);

    let boxes = H.findInputs(tree).filter(n => (n.props?.['aria-label'] as string || '').startsWith('Select match'));
    (boxes.find(n => n.props?.['aria-label'] === 'Select match 1')!.props!.onChange as (e: {target: {checked: boolean}}) => void)({target: {checked: true}});
    (boxes.find(n => n.props?.['aria-label'] === 'Select match 2')!.props!.onChange as (e: {target: {checked: boolean}}) => void)({target: {checked: true}});
    tree = H.render(ReviewReact, {});

    fetchImpl = async () => json(page([row(1, 'tok-a'), row(2, 'tok-b-new')]));
    // ReviewReact keys its reload effect on [afterId, nonce]; there is no
    // external "revision" prop like MatchReview.tsx's, so the equivalent
    // trigger is its own reload() (exercised here via a forced refetch after
    // reusing the same rows call, matching the token-survives-refetch case).
    tree = H.render(ReviewReact, {});
    const refreshRows = H.findByTagAndText(tree, 'button', 'Refresh rows')[0];
    (refreshRows.props!.onClick as () => void)();
    tree = H.render(ReviewReact, {});
    tree = await H.flush(ReviewReact, {}, tree);

    boxes = H.findInputs(tree).filter(n => (n.props?.['aria-label'] as string || '').startsWith('Select match'));
    expect(boxes.find(n => n.props?.['aria-label'] === 'Select match 1')!.props!.checked).toBe(true);
    expect(boxes.find(n => n.props?.['aria-label'] === 'Select match 2')!.props!.checked).toBe(false);
  });
});
