import { useEffect, useId, useRef, useState } from "react";
import type * as Monaco from "monaco-editor";

/** React owns every keystroke; Monaco is a disposable view over the saved draft. */
export function ScratchEditor({ value, label, onChange, active = true }: { value: string; label: string; onChange: (value: string) => void; active?: boolean }) {
  const id = useId(), host = useRef<HTMLDivElement>(null);
  const editor = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const latest = useRef(value), change = useRef(onChange), updating = useRef(false);
  const latestActive = useRef(active); latestActive.current = active;
  latest.current = value; change.current = onChange;
  const [loaded, setLoaded] = useState(false), [plain, setPlain] = useState(false), [error, setError] = useState("");
  useEffect(() => {
    if (plain) return;
    let live = true, instance: Monaco.editor.IStandaloneCodeEditor | undefined;
    let model: Monaco.editor.ITextModel | undefined, subscription: Monaco.IDisposable | undefined;
    setLoaded(false); setError("");
    void (async () => {
      const { monaco, ensureMonacoLanguage } = await import("../monaco-runtime");
      await ensureMonacoLanguage("c");
      if (!live || !host.current) return;
      model = monaco.editor.createModel(latest.current, "c");
      instance = monaco.editor.create(host.current, { model, theme: "vs-dark", automaticLayout: latestActive.current,
        ariaLabel: label, minimap: { enabled: false }, fontSize: 13, lineHeight: 21,
        wordWrap: "on", scrollBeyondLastLine: false, smoothScrolling: false,
        cursorSmoothCaretAnimation: "off", stickyScroll: { enabled: false }, tabSize: 4 });
      editor.current = instance;
      subscription = model.onDidChangeContent(() => { if (!updating.current) change.current(model!.getValue()); });
      setLoaded(true);
    })().catch(e => {
      subscription?.dispose(); instance?.dispose(); model?.dispose();
      if (editor.current === instance) editor.current = null;
      if (live) { setLoaded(false); setError(`Syntax editor unavailable; plain editor retains your draft. ${e instanceof Error ? e.message : String(e)}`); }
    });
    return () => { live = false; subscription?.dispose(); instance?.dispose(); model?.dispose(); editor.current = null; };
  }, [plain, label]);
  useEffect(() => {
    if (editor.current && editor.current.getValue() !== value) {
      updating.current = true;
      try { editor.current.setValue(value); } finally { updating.current = false; }
    }
  }, [value]);
  useEffect(() => {
    editor.current?.updateOptions({ automaticLayout: active });
    if (!active || !loaded || plain) return;
    const frame = requestAnimationFrame(() => editor.current?.layout());
    return () => cancelAnimationFrame(frame);
  }, [active, loaded, plain]);
  return <div className="scratch-code-editor">
    <div className="scratch-editor-heading"><label htmlFor={loaded && !plain ? undefined : id}>{label}</label>
      <button type="button" aria-pressed={plain} onClick={() => setPlain(v => !v)}>{plain ? "Syntax editor" : "Plain editor"}</button></div>
    {error && <p role="status">{error}</p>}
    <div className="scratch-monaco" ref={host} hidden={!loaded || plain}/>
    {(!loaded || plain) && <textarea id={id} spellCheck={false} value={value} onChange={e => onChange(e.target.value)}/>}
  </div>;
}
