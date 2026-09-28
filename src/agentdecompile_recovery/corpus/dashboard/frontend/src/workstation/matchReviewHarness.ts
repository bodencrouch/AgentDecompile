/*
 * Test-only hooks shim for driving MatchReview (and the mirrored ReviewReact
 * section of static/workbench-app.js) without a DOM. There is no jsdom and no
 * @testing-library/react in this project's node_modules, and installing one
 * is out of scope for this change, so useState/useEffect/useRef/useCallback/
 * useMemo are reimplemented here as a minimal, single-instance dispatcher.
 * createElement / the JSX runtime are NOT touched: only the four (five with
 * useMemo) hooks are swapped in, via `vi.mock('react', ...)` in the test
 * files. The component function is then called directly, and its returned
 * element tree is walked with the helpers below.
 *
 * This approximates React's own scheduling: state updates made synchronously
 * inside a render are NOT supported (none of the two components need that);
 * state updates made from event handlers or resolved promises mark the
 * instance dirty, and the test re-invokes the component function to obtain
 * the next tree. Effects run after each render that changed their deps, in
 * useEffect() call order; cleanups run before the following changed run and
 * on unmount.
 */

type Cleanup = (() => void) | void;
interface EffectSlot {
  deps?: unknown[];
  cleanup?: Cleanup;
}
interface MemoSlot {
  value: unknown;
  deps?: unknown[];
}

let stateSlots: unknown[] = [];
let refSlots: {current: unknown}[] = [];
let memoSlots: MemoSlot[] = [];
let effectSlots: EffectSlot[] = [];
let pendingEffects: Array<() => void> = [];
let stateIdx = 0;
let refIdx = 0;
let memoIdx = 0;
let effectIdx = 0;
let mounted = false;
let dirty = false;
let setStateAfterUnmount = 0;

function depsChanged(prevDeps: unknown[] | undefined, deps: unknown[] | undefined): boolean {
  if (!deps || !prevDeps) return true;
  if (deps.length !== prevDeps.length) return true;
  return deps.some((value, index) => !Object.is(value, prevDeps[index]));
}

export function useState<T>(initial: T | (() => T)): [T, (value: T | ((prev: T) => T)) => void] {
  const i = stateIdx++;
  if (i >= stateSlots.length) {
    stateSlots.push(typeof initial === 'function' ? (initial as () => T)() : initial);
  }
  const setState = (value: T | ((prev: T) => T)) => {
    if (!mounted) {setStateAfterUnmount++; return;}
    const prev = stateSlots[i] as T;
    const next = typeof value === 'function' ? (value as (prev: T) => T)(prev) : value;
    if (!Object.is(next, prev)) {stateSlots[i] = next; dirty = true;}
  };
  return [stateSlots[i] as T, setState];
}

export function useRef<T>(initial: T): {current: T} {
  const i = refIdx++;
  if (i >= refSlots.length) refSlots.push({current: initial});
  return refSlots[i] as {current: T};
}

export function useCallback<T>(fn: T, _deps?: unknown[]): T {
  return fn;
}

export function useMemo<T>(factory: () => T, deps?: unknown[]): T {
  const i = memoIdx++;
  const prev = memoSlots[i];
  if (!prev || depsChanged(prev.deps, deps)) memoSlots[i] = {value: factory(), deps};
  return memoSlots[i].value as T;
}

export function useEffect(callback: () => Cleanup, deps?: unknown[]): void {
  const i = effectIdx++;
  const prev = effectSlots[i];
  const changed = !prev || depsChanged(prev.deps, deps);
  effectSlots[i] = {deps, cleanup: prev?.cleanup};
  if (changed) {
    pendingEffects.push(() => {
      effectSlots[i].cleanup?.();
      effectSlots[i].cleanup = callback() || undefined;
    });
  }
}

/** Call before invoking the component function for a render. */
export function beginRender(): void {
  stateIdx = 0; refIdx = 0; memoIdx = 0; effectIdx = 0; dirty = false; pendingEffects = [];
}

/** Call after the component function returns, to run any changed effects. */
export function commitEffects(): void {
  const list = pendingEffects;
  pendingEffects = [];
  list.forEach(run => run());
}

export function markMounted(): void {
  mounted = true;
}

/** Run every registered cleanup, in useEffect() call order, and stop accepting state updates. */
export function unmount(): void {
  effectSlots.forEach(slot => slot.cleanup?.());
  mounted = false;
}

export function isDirty(): boolean {
  return dirty;
}

export function setStateAfterUnmountCount(): number {
  return setStateAfterUnmount;
}

/** Reset all slots. Call between tests (and before mounting a second instance). */
export function reset(): void {
  stateSlots = []; refSlots = []; memoSlots = []; effectSlots = []; pendingEffects = [];
  stateIdx = 0; refIdx = 0; memoIdx = 0; effectIdx = 0;
  mounted = false; dirty = false; setStateAfterUnmount = 0;
}

/** Render the component once: reset render-local indices, call it, commit its effects. */
export function render<P>(component: (props: P) => unknown, props: P): unknown {
  beginRender();
  const element = component(props);
  // Mark mounted before committing effects: React runs effects only after a
  // component is mounted, and MatchReview's load effect calls setLoading()
  // synchronously on first render. If markMounted() ran after commitEffects()
  // here, that first setLoading() would see mounted === false and get counted
  // as a post-unmount state update, poisoning setStateAfterUnmountCount()
  // before any real unmount happens.
  markMounted();
  commitEffects();
  return element;
}

/**
 * Await pending microtasks, then re-render while the instance is dirty (state
 * changed as a result of those microtasks, or of the render itself scheduling
 * more work). Capped so a runaway effect loop fails the test instead of hanging it.
 */
export async function flush<P>(component: (props: P) => unknown, props: P, last: unknown, ticks = 6): Promise<unknown> {
  let element = last;
  for (let i = 0; i < ticks; i++) {
    await Promise.resolve();
    await Promise.resolve();
    if (!isDirty()) continue;
    element = render(component, props);
  }
  return element;
}

// --- Element tree helpers -------------------------------------------------

type Node = null | undefined | boolean | string | number | Node[] | {type?: unknown; props?: {children?: Node}};

function visit(node: Node, fn: (n: {type?: unknown; props?: Record<string, unknown>}) => void): void {
  if (node == null || typeof node === 'boolean' || typeof node === 'string' || typeof node === 'number') return;
  if (Array.isArray(node)) {node.forEach(child => visit(child, fn)); return;}
  if (typeof node === 'object') {
    fn(node as {type?: unknown; props?: Record<string, unknown>});
    const children = (node as {props?: {children?: Node}}).props?.children;
    if (children !== undefined) visit(children, fn);
  }
}

// The exported helpers below take `unknown`, not `Node`: callers only ever
// have the `unknown` that `render()`/`flush()` return (React's own element
// type isn't `Node`, and callers shouldn't need to import this internal
// type just to hold a tree). Node is re-validated internally by `visit`.

export function text(node: unknown): string {
  const n = node as Node;
  if (n == null || typeof n === 'boolean') return '';
  if (typeof n === 'string' || typeof n === 'number') return String(n);
  if (Array.isArray(n)) return n.map(text).join('');
  if (typeof n === 'object') return text((n as {props?: {children?: Node}}).props?.children ?? null);
  return '';
}

export function findAll(node: unknown, predicate: (n: {type?: unknown; props?: Record<string, unknown>}) => boolean): {type?: unknown; props?: Record<string, unknown>}[] {
  const out: {type?: unknown; props?: Record<string, unknown>}[] = [];
  visit(node as Node, n => {if (predicate(n)) out.push(n);});
  return out;
}

export function findByTagAndText(node: unknown, tag: string, needle: string): {type?: unknown; props?: Record<string, unknown>}[] {
  // Exact match, not substring: with substring matching, needle 'Accept' also
  // matches the bulk "Accept selected" button, which renders earlier in the
  // tree than the per-row "Accept" button and would be picked as [0] instead
  // — a real bug that made every decision-flow test click the (disabled,
  // no-op when nothing is checked) bulk button and then fail to find
  // "Confirm accept", since ask() with an empty rows array never opens the
  // confirm step.
  return findAll(node, n => n.type === tag && text(n.props?.children) === needle);
}

export function findInputs(node: unknown): {type?: unknown; props?: Record<string, unknown>}[] {
  return findAll(node, n => n.type === 'input');
}
