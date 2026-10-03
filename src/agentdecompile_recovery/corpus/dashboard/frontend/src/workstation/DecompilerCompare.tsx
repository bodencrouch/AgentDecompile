import {API, query, type Data, type Selection} from '../contracts';
import {useData} from '../ui';

/** One configured local runner's output for the current selection.
 *
 * Fetched independently per runner so a slow or failed runner never blocks
 * the others — each column shows its own loading/empty/failed state.
 */
function RunnerColumn({runner, selection, revision}: {runner: Data; selection: Selection; revision: number}) {
  const url = selection.addr ? `${API}/decompiler-output?${query(selection, {runner: runner.id})}` : null;
  const output = useData(url, revision);
  return <section className="decompiler-column" aria-label={`${runner.label} output`}>
    <header><strong>{runner.label}</strong></header>
    {!selection.addr ? <p role="status">Select a function to compare decompiler output.</p>
      : output.loading ? <p role="status">Reading {runner.label} output…</p>
      : output.error ? <p role="alert">{output.error}</p>
      : typeof output.data.output === 'string' ? <pre>{output.data.output}</pre>
      : <p role="status">{runner.label} returned no output for this function.</p>}
  </section>;
}

/** Dogbolt-style multi-decompiler compare, licensed-local-only (R41).
 *
 * This never calls or uploads to the public Dogbolt service. Every column
 * is sourced from a runner the operator configured locally; with none
 * configured the view says so explicitly rather than rendering empty.
 */
export function DecompilerCompare({selection, revision}: {selection: Selection; revision: number}) {
  const runners = useData(`${API}/decompiler-runners`, revision);
  const list: Data[] = Array.isArray(runners.data.runners) ? runners.data.runners : [];
  if (runners.loading) return <div className="ws-document"><p role="status">Reading configured local decompiler runners…</p></div>;
  if (runners.error) return <div className="ws-document"><p role="alert">{runners.error}</p></div>;
  if (!list.length) return <div className="ws-document">
    <p role="status">No local decompiler runner is configured. This view never calls the public Dogbolt service — configure a licensed local runner (AGENTDECOMPILE_DECOMPILER_RUNNERS) to compare outputs here.</p>
  </div>;
  return <div className="decompiler-compare" aria-label="Multi-decompiler compare">
    {list.map(runner => <RunnerColumn key={String(runner.id)} runner={runner} selection={selection} revision={revision}/>)}
  </div>;
}
