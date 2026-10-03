import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { createArtifactParserSession } from '../workers/artifactParser';
import type { ArtifactInspection } from '../workers/artifactParser.worker';


const HEADER_BYTES = 64 * 1024; // the parser only needs headers; never read whole builds into memory
const MAX_FILES = 2000;
const MAX_INSPECT = 400;

type Inspect = { status: 'pending' } | { status: 'ok'; value: ArtifactInspection } | { status: 'other'; reason: string };
export type DroppedFile = { path: string; size: number; file: File };
export type TreeNode = { name: string; path: string; children: TreeNode[]; file?: DroppedFile; bytes: number; count: number };

/** Build a folder tree from slash-separated paths (folders first, then by name). */
export function buildTree(files: DroppedFile[]): TreeNode {
  const root: TreeNode = { name: '', path: '', children: [], bytes: 0, count: 0 };
  for (const f of files) {
    const parts = f.path.split('/').filter(Boolean);
    let node = root;
    node.bytes += f.size;
    node.count++;
    parts.forEach((part, k) => {
      const path = parts.slice(0, k + 1).join('/');
      let child = node.children.find(c => c.name === part && (k === parts.length - 1) === !!c.file);
      if (!child) {
        child = { name: part, path, children: [], bytes: 0, count: 0, file: k === parts.length - 1 ? f : undefined };
        node.children.push(child);
      }
      child.bytes += f.size;
      child.count++;
      node = child;
    });
  }
  const sort = (n: TreeNode) => {
    n.children.sort((a, b) => Number(!!a.file) - Number(!!b.file) || a.name.localeCompare(b.name));
    n.children.forEach(sort);
  };
  sort(root);
  return root;
}

async function readEntry(entry: any, prefix: string, out: DroppedFile[]): Promise<void> {
  if (out.length >= MAX_FILES || !entry) return;
  if (entry.isFile) {
    const file: File = await new Promise((resolve, reject) => entry.file(resolve, reject));
    out.push({ path: `${prefix}${entry.name}`, size: file.size, file });
    return;
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    for (;;) {
      const batch: any[] = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
      if (!batch.length || out.length >= MAX_FILES) break;
      for (const child of batch) await readEntry(child, `${prefix}${entry.name}/`, out);
    }
  }
}

const bytes = (n: number) => (n >= 1 << 30 ? `${(n / (1 << 30)).toFixed(1)} GB` : n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);

export function DropZone() {
  const [files, setFiles] = useState<DroppedFile[]>([]);
  const [over, setOver] = useState(false);
  const [inspect, setInspect] = useState<Record<string, Inspect>>({});
  const revision = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const tree = useMemo(() => buildTree(files), [files]);

  useEffect(() => {
    if (!files.length) return;
    const rev = String(++revision.current);
    const session = createArtifactParserSession(r => r === rev);
    let alive = true;
    setInspect({});
    (async () => {
      for (const f of files.slice(0, MAX_INSPECT)) {
        if (!alive) break;
        setInspect(old => ({ ...old, [f.path]: { status: 'pending' } }));
        const payload = await f.file.slice(0, HEADER_BYTES).arrayBuffer();
        const result = await session.run<ArtifactInspection>({
          id: `${rev}:${f.path}`, operation: 'inspect-artifact', revisionId: rev, payload,
          limits: { maxArtifactBytes: HEADER_BYTES, timeoutMs: 5000 },
        });
        if (!alive) break;
        setInspect(old => ({
          ...old,
          [f.path]: result.status === 'completed' && result.value ? { status: 'ok', value: result.value } : { status: 'other', reason: result.failure?.message || result.status },
        }));
      }
      session.terminate();
    })().catch(() => session.terminate());
    return () => {
      alive = false;
      session.terminate();
    };
  }, [files]);

  const accept = (list: DroppedFile[]) => list.length && setFiles(list.slice(0, MAX_FILES));
  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const items = Array.from(e.dataTransfer.items || []);
    const entries = items.map(i => (i as any).webkitGetAsEntry?.()).filter(Boolean);
    if (entries.length) {
      const out: DroppedFile[] = [];
      for (const entry of entries) await readEntry(entry, '', out);
      accept(out);
    } else {
      accept(Array.from(e.dataTransfer.files).map(file => ({ path: file.name, size: file.size, file })));
    }
  };
  const fromInput = (list: FileList | null) => {
    accept(Array.from(list || []).map(file => ({ path: (file as any).webkitRelativePath || file.name, size: file.size, file })));
  };

  const recognised = Object.values(inspect).filter(i => i.status === 'ok').length;

  return (
    <div className="cp-dropwrap">
      <div
        className={`cp-drop ${over ? 'over' : ''}`}
        onDragOver={e => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={e => void onDrop(e)}
        data-tip="Drop builds or whole folders · inspected locally in this browser (ELF / PE headers)"
      >
        <svg width="26" height="26" viewBox="0 0 28 28" aria-hidden="true"><rect x="3" y="3" width="22" height="22" rx="5" fill="none" stroke="currentColor" strokeDasharray="3 3" /><path d="M14 8v10M9.5 13.5 14 18l4.5-4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
        <span className="cp-drop-text">
          <b>Drop builds</b>
          <span className="cp-drop-btns">
            <button type="button" onClick={() => inputRef.current?.click()}>Files</button>
            <button type="button" onClick={() => folderRef.current?.click()}>Folder</button>
          </span>
        </span>
        <input ref={inputRef} type="file" multiple hidden onChange={e => fromInput(e.target.files)} />
        <input ref={folderRef} type="file" multiple hidden {...({ webkitdirectory: '', directory: '' } as any)} onChange={e => fromInput(e.target.files)} />
      </div>
      {files.length > 0 && (
        <div className="cp-tree-wrap">
          <div className="cp-tree-head">
            <span className="cp-mono">{files.length}{files.length >= MAX_FILES ? '+' : ''} files · {bytes(tree.bytes)}</span>
            <span className="cp-mono cp-good" data-tip="Files the local parser recognised as ELF or PE">{recognised} bin</span>
            <button type="button" className="cp-iconbtn" aria-label="Clear dropped files" data-tip="Clear" onClick={() => { setFiles([]); setInspect({}); }}>
              <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" /></svg>
            </button>
          </div>
          <ul className="cp-tree" role="tree" aria-label="Dropped files">
            {tree.children.map(n => <TreeItem key={n.path} node={n} depth={0} inspect={inspect} />)}
          </ul>
        </div>
      )}
    </div>
  );
}

function TreeItem({ node, depth, inspect }: { node: TreeNode; depth: number; inspect: Record<string, Inspect> }) {
  const [open, setOpen] = useState(depth < 1);
  if (node.file) {
    const info = inspect[node.file.path];
    const chip = info?.status === 'ok' ? `${info.value.format} · ${info.value.architecture}` : info?.status === 'pending' ? '…' : '';
    return (
      <li role="treeitem" aria-selected={false} className={`cp-leaf ${info?.status === 'ok' ? 'bin' : ''}`} style={{ paddingLeft: 8 + depth * 12 }}
        data-tip={`${node.path} · ${bytes(node.bytes)}${info?.status === 'ok' ? ` · ${info.value.format.toUpperCase()} ${info.value.architecture}` : info?.status === 'other' ? ' · not ELF/PE' : ''}`}>
        <span className="cp-tree-name">{node.name}</span>
        {chip && <span className="cp-chip mini">{chip}</span>}
      </li>
    );
  }
  return (
    <li role="treeitem" aria-expanded={open} aria-selected={false} className="cp-folder">
      <button type="button" style={{ paddingLeft: 4 + depth * 12 }} onClick={() => setOpen(!open)} data-tip={`${node.path} · ${node.count} files · ${bytes(node.bytes)}`}>
        <span className="cp-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="cp-tree-name">{node.name}</span>
        <small className="cp-mono">{node.count}</small>
      </button>
      {open && (
        <ul role="group">
          {node.children.slice(0, 300).map(c => <TreeItem key={c.path} node={c} depth={depth + 1} inspect={inspect} />)}
        </ul>
      )}
    </li>
  );
}
