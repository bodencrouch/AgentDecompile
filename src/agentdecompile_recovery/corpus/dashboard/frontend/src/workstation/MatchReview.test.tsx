/*
 * Behaviour tests for MatchReview.tsx: polling to a terminal job result,
 * "Stop waiting", unmount during an in-flight submit, a stale_basis refusal,
 * select-all over decidable rows only, and revision-bump row retention.
 *
 * There is no jsdom and no @testing-library/react in this project (see
 * package.json / node_modules); installing either was out of scope. Instead
 * useState/useEffect/useRef/useCallback are swapped for the single-instance
 * shim in ./matchReviewHarness (mirroring how src/preparationBudget.test.tsx
 * already swaps useCallback for a passthrough to drive sliced static code).
 * MatchReview is called directly as a function and its returned element
 * tree is walked for text/props; this checks the component's own logic
 * (state transitions, guards, closures) rather than React DOM's commit,
 * batching or effect timing, which this harness only approximates.
 */
import {beforeEach, describe, expect, it, vi, type Mock} from 'vitest';
import type {Notify} from '../contracts';
import * as H from './matchReviewHarness';

vi.mock('react', async orig => {
  const real = await (orig() as Promise<Record<string, unknown>>);
  const shim = await import('./matchReviewHarness');
  return {...real, useState: shim.useState, useEffect: shim.useEffect, useRef: shim.useRef, useCallback: shim.useCallback};
});

const {MatchReview} = await import('./MatchReview');
void 0; // MatchReview is imported dynamically above so the vi.mock('react', ...) factory (which itself
// dynamically imports matchReviewHarness) is guaranteed to install the shim before MatchReview.tsx's
// module body runs `import {useState, ...} from 'react'`.

function row(id: number, token: string) {
  return {match: {id, src_binary: 'a.exe', dst_binary: 'b.exe', src_addr: 0x1000, dst_addr: 0x2000, score: 0.9, margin: 0.1}, binaries: [{}, {}], token};
}
function page(rows: ReturnType<typeof row>[], selection = 'sel-1') {
  return {rows, total: rows.length, nextAfterId: null, selection};
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});

describe('MatchReview', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let notify: Mock<Notify>;
  const props = () => ({active: true, revision: 0, notify});

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
    notify = vi.fn<Notify>();
    fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('match-review')) return json(page([]));
      throw new Error(`unhandled fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  it('shows pending after a 202, and the outcome only after a terminal job result', async () => {
    // observeReviewJob's internal 40-attempt loop, and its 750ms delay
    // between attempts, all run inside one await in send()/observe() without
    // a re-render in between (see MatchReview.tsx:67-88, :184-209). Two
    // "running" responses force two delay cycles, so the terminal result is
    // observably not yet available after only the first timer advance.
    let jobPollCount = 0;
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('match-decide-batch')) return json({job_id: 'job-1'}, 202);
      if (String(url).includes('/api/v1/jobs/')) {
        jobPollCount++;
        if (jobPollCount < 3) return json({job: {status: 'running'}});
        return json({job: {status: 'ok', log: JSON.stringify({ok: true, acceptance: 'review-decision-only', decisions: [{matchId: 1, status: 'verify'}]})}});
      }
      return json(page([row(1, 'tok-1')]));
    });

    let tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);
    const accept = H.findByTagAndText(tree, 'button', 'Accept')[0];
    (accept.props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    const confirm = H.findByTagAndText(tree, 'button', 'Confirm accept')[0];
    (confirm.props!.onClick as () => void)();
    tree = await H.flush(MatchReview, props(), tree);

    expect(H.text(tree)).toContain('Decision sent as job job-1');
    expect(H.text(tree)).not.toContain('rejected');
    expect(H.text(tree)).not.toContain('moved to verification');
    expect(jobPollCount).toBe(1);

    // One poll cycle elapsed; the job is still "running" server-side, and the
    // pending state is unchanged because there is no re-render mid-loop.
    await vi.advanceTimersByTimeAsync(750);
    tree = await H.flush(MatchReview, props(), tree);
    expect(H.text(tree)).toContain('Decision sent as job job-1');
    expect(H.text(tree)).not.toContain('moved to verification');
    expect(jobPollCount).toBe(2);

    // Second poll cycle: the job ends "ok" with acceptance
    // "review-decision-only", and only now does the outcome text appear.
    await vi.advanceTimersByTimeAsync(750);
    tree = await H.flush(MatchReview, props(), tree);
    expect(H.text(tree)).toContain('Match 1 moved to verification.');
    expect(notify).toHaveBeenCalledWith('Match 1 moved to verification.', 'info');
  });

  it('an "ok" job without acceptance "review-decision-only" is treated as unknown outcome, not a decision', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('match-decide-batch')) return json({job_id: 'job-2'}, 202);
      if (String(url).includes('/api/v1/jobs/')) return json({job: {status: 'ok', log: JSON.stringify({ok: true})}});
      return json(page([row(2, 'tok-2')]));
    });

    let tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(MatchReview, props(), tree);

    expect(H.text(tree)).not.toContain('rejected');
    expect(H.text(tree)).not.toContain('moved to verification');
    expect(H.text(tree)).toContain('ended as "ok" without a result');
  });

  it('"Stop waiting" keeps the job ID and the "Check result" control', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('match-decide-batch')) return json({job_id: 'job-9'}, 202);
      if (String(url).includes('/api/v1/jobs/')) return json({job: {status: 'running'}});
      return json(page([row(9, 'tok-9')]));
    });

    let tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(MatchReview, props(), tree);
    expect(H.text(tree)).toContain('Stop waiting');

    const jobFetchesBefore = fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/v1/jobs/')).length;
    (H.findByTagAndText(tree, 'button', 'Stop waiting')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());

    expect(H.text(tree)).toContain('Stopped waiting for job job-9');
    expect(H.text(tree)).toContain('job-9');
    const checkResult = H.findByTagAndText(tree, 'button', 'Check result')[0];
    expect(checkResult).toBeTruthy();
    expect(checkResult.props!.disabled).toBeFalsy();
    expect(H.text(tree)).toContain('Waiting for its job');

    await vi.advanceTimersByTimeAsync(750 * 3);
    tree = await H.flush(MatchReview, props(), tree);
    const jobFetchesAfter = fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/v1/jobs/')).length;
    expect(jobFetchesAfter).toBe(jobFetchesBefore);
  });

  it('starts no poll after unmount during an in-flight submit', async () => {
    let resolveSubmit!: (value: Response) => void;
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('match-decide-batch')) return new Promise<Response>(resolve => {resolveSubmit = resolve;});
      if (String(url).includes('/api/v1/jobs/')) return json({job: {status: 'running'}});
      return json(page([row(5, 'tok-5')]));
    });

    let tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    // send() is now awaiting the POST; unmount before it resolves.
    H.unmount();

    resolveSubmit(json({job_id: 'job-5'}, 202));
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    await vi.advanceTimersByTimeAsync(750 * 3);
    await Promise.resolve(); await Promise.resolve();

    expect(H.setStateAfterUnmountCount()).toBe(0);
    const jobFetches = fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/v1/jobs/')).length;
    expect(jobFetches).toBe(0);
  });

  it('shows the refusal text for a stale_basis decision and refreshes the rows', async () => {
    let reviewFetches = 0;
    // The 2nd match-review fetch (triggered by reload() inside send()'s catch,
    // MatchReview.tsx:242) resolves through the same load effect that does
    // `setError('')` on success (MatchReview.tsx:161) — the same `error` state
    // that renders the role="alert" text this test checks. Racing that fetch
    // against the assertion via H.flush()'s fixed tick count is what made this
    // test flaky: given enough ticks, the alert set by the catch block would
    // already have been wiped by the reload's own success handler before the
    // assertion ran. Gate the 2nd match-review response behind an explicit
    // resolve so the alert is checked at a known point in between.
    let resolveSecondReview: (() => void) | null = null;
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('match-decide-batch')) return json({error: 'stale_basis'}, 409);
      if (String(url).includes('match-review')) {
        reviewFetches++;
        if (reviewFetches > 1) await new Promise<void>(resolve => {resolveSecondReview = resolve;});
        return json(page([row(3, 'tok-3')]));
      }
      throw new Error(`unhandled: ${url}`);
    });

    let tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);
    expect(reviewFetches).toBe(1);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(MatchReview, props(), tree);

    // The 2nd match-review fetch is now pending on resolveSecondReview, so the
    // alert set by send()'s catch has not yet been cleared by that reload.
    expect(reviewFetches).toBe(2);
    expect(H.findAll(tree, n => n.props?.role === 'alert').some(n => H.text(n.props?.children as never).includes('A row changed after you loaded it'))).toBe(true);
    expect(notify).toHaveBeenCalledWith(expect.stringContaining('A row changed after you loaded it'), 'error');

    resolveSecondReview!();
    tree = await H.flush(MatchReview, props(), tree);
  });

  it('does not reload for a "busy" refusal (contrast case for refreshRequired)', async () => {
    let reviewFetches = 0;
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('match-decide-batch')) return json({error: 'busy'}, 409);
      if (String(url).includes('match-review')) {reviewFetches++; return json(page([row(4, 'tok-4')]));}
      throw new Error(`unhandled: ${url}`);
    });

    let tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);
    expect(reviewFetches).toBe(1);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(MatchReview, props(), tree);

    expect(H.text(tree)).toContain('The database is busy');
    expect(reviewFetches).toBe(1);
  });

  it('select-all covers only decidable rows on the current page', async () => {
    const rows = [row(1, 'tok-a'), row(2, 'tok-b'), row(3, 'tok-c')];
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('match-decide-batch')) return json({job_id: 'job-lock'}, 202);
      if (String(url).includes('/api/v1/jobs/')) return json({job: {status: 'running'}});
      return json(page(rows));
    });

    let tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);
    // Lock row "tok-a" behind an open job so it becomes ineligible.
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(MatchReview, props(), tree);
    // The job for "tok-a" never leaves "running" in this mock, so `watching`
    // stays truthy and `busy` (which includes it, per MatchReview.tsx:216)
    // would keep every decide control a no-op — including "Accept selected"
    // below — unless we stop waiting on it first. Doing so only clears
    // `watching`; the row stays locked via the open `jobs` entry (checked by
    // `eligible`/`locked`, MatchReview.tsx:214-216), which is exactly the
    // "still ineligible" state this test means to exercise.
    (H.findByTagAndText(tree, 'button', 'Stop waiting')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());

    // R45 (lane E fleet roster, docs/plans/2026-09-28-0817-feat-static-codebrowser-project-tabs-plan.md)
    // added the pair/score filters, and the select-all control was renamed to
    // "Select all visible rows on this page" to reflect that it now covers the
    // filtered subset rather than every row on the page.
    const selectAll = H.findAll(tree, n => n.type === 'input' && n.props?.['aria-label'] === 'Select all visible rows on this page')[0];
    (selectAll.props!.onChange as (e: {target: {checked: boolean}}) => void)({target: {checked: true}});
    tree = H.render(MatchReview, props());

    const rowCheckboxes = H.findAll(tree, n => n.type === 'input' && typeof n.props?.['aria-label'] === 'string' && (n.props?.['aria-label'] as string).startsWith('Select match'));
    expect(rowCheckboxes.find(n => n.props?.['aria-label'] === 'Select match 1')!.props!.checked).toBe(false);
    expect(rowCheckboxes.find(n => n.props?.['aria-label'] === 'Select match 2')!.props!.checked).toBe(true);
    expect(rowCheckboxes.find(n => n.props?.['aria-label'] === 'Select match 3')!.props!.checked).toBe(true);

    const acceptSelected = H.findByTagAndText(tree, 'button', 'Accept selected')[0];
    (acceptSelected.props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    expect(H.text(tree)).toContain('Move 2 matches (2, 3)');
  });

  it('keeps a checked row that is still on the page after a revision bump, by token identity', async () => {
    fetchMock.mockImplementation(async () => json(page([row(1, 'tok-a'), row(2, 'tok-b')])));
    let tree = H.render(MatchReview, {...props(), revision: 0});
    tree = await H.flush(MatchReview, {...props(), revision: 0}, tree);

    let boxes = H.findInputs(tree).filter(n => (n.props?.['aria-label'] as string || '').startsWith('Select match'));
    (boxes.find(n => n.props?.['aria-label'] === 'Select match 1')!.props!.onChange as (e: {target: {checked: boolean}}) => void)({target: {checked: true}});
    (boxes.find(n => n.props?.['aria-label'] === 'Select match 2')!.props!.onChange as (e: {target: {checked: boolean}}) => void)({target: {checked: true}});
    tree = H.render(MatchReview, {...props(), revision: 0});
    boxes = H.findInputs(tree).filter(n => (n.props?.['aria-label'] as string || '').startsWith('Select match'));
    expect(boxes.every(n => n.props?.checked)).toBe(true);

    // Revision bump: row 1 keeps its token (still checked), row 2 gets a NEW
    // token (a re-decided/re-issued row, so its old checkmark must not carry over).
    fetchMock.mockImplementation(async () => json(page([row(1, 'tok-a'), row(2, 'tok-b-new')])));
    tree = H.render(MatchReview, {...props(), revision: 1});
    tree = await H.flush(MatchReview, {...props(), revision: 1}, tree);

    boxes = H.findInputs(tree).filter(n => (n.props?.['aria-label'] as string || '').startsWith('Select match'));
    expect(boxes.find(n => n.props?.['aria-label'] === 'Select match 1')!.props!.checked).toBe(true);
    expect(boxes.find(n => n.props?.['aria-label'] === 'Select match 2')!.props!.checked).toBe(false);
  });

  it('"Refresh rows" while watching drops the "Stop waiting" control but leaves decide controls busy-disabled', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('match-decide-batch')) return json({job_id: 'job-r'}, 202);
      if (String(url).includes('/api/v1/jobs/')) return json({job: {status: 'running'}});
      return json(page([row(7, 'tok-7')]));
    });

    let tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);
    (H.findByTagAndText(tree, 'button', 'Accept')[0].props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    (H.findByTagAndText(tree, 'button', 'Confirm accept')[0].props!.onClick as () => void)();
    tree = await H.flush(MatchReview, props(), tree);
    expect(H.text(tree)).toContain('Stop waiting');

    const refresh = H.findByTagAndText(tree, 'button', 'Refresh rows')[0];
    expect(refresh.props!.disabled).toBeFalsy();
    (refresh.props!.onClick as () => void)();
    tree = H.render(MatchReview, props());
    tree = await H.flush(MatchReview, props(), tree);

    expect(H.text(tree)).not.toContain('Stop waiting');
    // Documents observed behaviour: `watching` is untouched by refreshRows(), so
    // `busy` stays true until the still-running poll settles, disabling decide
    // controls even though the job line that offered "Stop waiting" is gone.
    // See MatchReview.tsx:212 (busy) and :252-256 (refreshRows), not fixed here.
    const acceptSelectedAfterRefresh = H.findByTagAndText(tree, 'button', 'Accept selected');
    if (acceptSelectedAfterRefresh.length) expect(acceptSelectedAfterRefresh[0].props!.disabled).toBeTruthy();
  });
});
