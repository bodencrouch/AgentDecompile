import {useEffect, useMemo, useRef, useState} from 'react';
import type {InstructionDiffRow} from '../integration/boundaries';
import './InstructionDiff.css';

const registerPattern = /\b(?:[re]?(?:ax|bx|cx|dx|si|di|sp|bp)|[abcd][lh]|r\d+[bwd]?|[xwvsdq]\d+|(?:xmm|ymm|zmm|mm|cr|dr)\d+|rip|eip|pc|lr|fp|sp|zero|ra|a[0-7]|t[0-6]|s(?:[0-9]|1[01]))\b/gi;

export function assemblyTokens(value: string): {text: string; register: boolean}[] {
  const parts: {text: string; register: boolean}[] = [];
  let offset = 0;
  for (const match of value.matchAll(new RegExp(registerPattern))) {
    const index = match.index!;
    if (index > offset) parts.push({text: value.slice(offset, index), register: false});
    parts.push({text: match[0], register: true});
    offset = index + match[0].length;
  }
  if (offset < value.length) parts.push({text: value.slice(offset), register: false});
  return parts;
}

function Assembly({text, peer}: {text: string; peer: string}) {
  const otherRegisters = new Set(assemblyTokens(peer).filter(token => token.register).map(token => token.text.toLowerCase()));
  return <code>{text ? assemblyTokens(text).map((token, index) => token.register
    ? <span key={index} className={otherRegisters.has(token.text.toLowerCase()) ? 'diff-register' : 'diff-register changed'}>{token.text}</span>
    : <span key={index}>{token.text}</span>) : <span className="diff-gap" aria-label="No instruction on this side">—</span>}</code>;
}

/** Presentation of provider-recorded alignment; display equality is not byte proof. */
export function InstructionDiff({rows, verified = false, onNavigate}: {
  rows: InstructionDiffRow[]; verified?: boolean; onNavigate?: (address: string) => void;
}) {
  const [differencesOnly, setDifferencesOnly] = useState(false);
  const [selected, setSelected] = useState('');
  const activeRow = useRef<HTMLTableRowElement>(null);
  const differences = useMemo(() => rows.filter(row => row.differs), [rows]);
  const visible = differencesOnly ? differences : rows;
  useEffect(() => {setSelected('');}, [rows]);
  useEffect(() => {activeRow.current?.scrollIntoView({block: 'nearest'});}, [selected]);
  function move(direction: number) {
    if (!differences.length) return;
    const current = differences.findIndex(row => row.id === selected);
    const next = current < 0 ? (direction > 0 ? 0 : differences.length - 1)
      : (current + direction + differences.length) % differences.length;
    const row = differences[next];
    setSelected(row.id);
    if (row.address) onNavigate?.(row.address);
  }
  return <section className="instruction-diff" aria-label="Aligned instruction comparison">
    <div className="instruction-diff-toolbar">
      <strong>Target / candidate instructions</strong>
      <button type="button" disabled={!differences.length} onClick={() => move(-1)}>Previous difference</button>
      <button type="button" disabled={!differences.length} onClick={() => move(1)}>Next difference</button>
      <label><input type="checkbox" checked={differencesOnly} onChange={event => setDifferencesOnly(event.target.checked)}/> Differences only</label>
      <span role="status">{differences.length} recorded differing rows</span>
    </div>
    {verified && <p className="diff-verified">Byte match verified by the receipt for its named candidate and target revisions.</p>}
    {!rows.length ? <p role="status">No aligned instruction receipt is available for this selection. Mismatch summaries below remain separate evidence.</p>
      : <div className="instruction-diff-scroll" tabIndex={0} aria-label="Scrollable instruction comparison">
        <table><caption>Recorded provider alignment; register highlighting is a visual aid.</caption>
          <thead><tr><th scope="col">Target address</th><th scope="col">Original target</th><th scope="col">Candidate address</th><th scope="col">Compiled candidate</th><th scope="col">Difference</th></tr></thead>
          <tbody>{visible.map(row => <tr key={row.id} ref={selected === row.id ? activeRow : undefined} data-differs={row.differs} data-selected={selected === row.id}>
            <td>{row.address && onNavigate ? <button type="button" onClick={() => {setSelected(row.id); onNavigate(row.address!);}}>{row.address}</button> : row.address || 'not recorded'}</td>
            <td><Assembly text={row.target} peer={row.candidate}/></td>
            <td>{row.candidateAddress || 'not recorded'}</td>
            <td><Assembly text={row.candidate} peer={row.target}/></td>
            <td>{row.kind}</td>
          </tr>)}</tbody>
        </table>
        {!visible.length && <p>No differing rows in this receipt. This does not independently establish byte equality.</p>}
      </div>}
  </section>;
}
