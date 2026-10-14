import { useEffect, useRef, useState } from "react";
import { API, query, request, type Data, type Notify, type Selection } from "../contracts";
import { instructionDiffRows, matchingPhase, matchingProvider, parseMatchPayload } from "../integration/boundaries";
import { DiffEvidence } from "../views/DiffEvidence";
import { InstructionDiff } from "../views/InstructionDiff";
import { candidateHash, loadScratches, presetCompatible, resultBelongs, saveScratch, translationUnit, type Scratch } from "./records";
import "./scratch.css";
import { ScratchEditor } from "./ScratchEditor";

type Props = { selection: Selection; revision: number; catalog: Data[]; notify: Notify; onSelect: (patch: Partial<Selection>) => void; onMatchCandidate?: (params: Data, capturedSelection?: Selection) => void; matchingJobId?: string; createNonce?: number; active?: boolean; onCreatingChange?: (creating: boolean) => void };
const terminal = new Set(["ok", "failed", "cancelled", "interrupted", "blocked"]);
const message = (e: unknown) => e instanceof Error ? e.message : String(e);
const sha = /^[a-f0-9]{64}$/;
function download(s: Scratch, c = false) {
  const url = URL.createObjectURL(new Blob([c ? translationUnit(s) : JSON.stringify(s, null, 2)], { type: c ? "text/x-c" : "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = `${s.title.replace(/[^a-zA-Z0-9_.-]/g, "_") || "scratch"}${c ? ".c" : ".scratch.json"}`;
  a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const blankForm = () => ({ title: "Untitled scratch", platform: "", preset: "", symbol: "", target: "", context: "", source: "", targetRevision: "", bind: false });
export function ScratchWorkspace({ selection, revision, catalog, notify, onSelect, onMatchCandidate, matchingJobId = "", createNonce = 0, active: isActive = true, onCreatingChange }: Props) {
  const [scratches, setScratches] = useState<Scratch[]>([]), [selected, setSelected] = useState("");
  const [ready, setReady] = useState(false), [creating, setCreating] = useState(false), [tab, setTab] = useState("source");
  const [outputTab, setOutputTab] = useState("compilation");
  const [saving, setSaving] = useState("Loading local scratches…"), [error, setError] = useState("");
  const [storageWarnings, setStorageWarnings] = useState<string[]>([]);
  const [library, setLibrary] = useState<Data[]>([]), [providerError, setProviderError] = useState("");
  const [autoTarget, setAutoTarget] = useState("");
  const [autoTargetLoading, setAutoTargetLoading] = useState(false);
  const [attempt, setAttempt] = useState<{ id: string; revision: number; hash: string; previousJob: string } | null>(null);
  const [job, setJob] = useState<Data>({}), [hashing, setHashing] = useState(false);
  const saveSequence = useRef(0), nonce = useRef(createNonce), importSequence = useRef(0);
  const titleInput = useRef<HTMLInputElement>(null);
  const lastNotifiedCreating = useRef(creating);
  const active = scratches.find(s => s.id === selected);
  const current = useRef(active); current.current = active;
  const provider = matchingProvider(catalog);
  const [seed, setSeed] = useState<Selection>({ ...selection }), [form, setForm] = useState(blankForm);
  useEffect(() => {
    if (lastNotifiedCreating.current === creating) return;
    lastNotifiedCreating.current = creating;
    onCreatingChange?.(creating);
  }, [creating, onCreatingChange]);
  useEffect(() => {
    if (creating) titleInput.current?.focus({ preventScroll: true });
  }, [creating, createNonce]);
  const discoveryLocator = creating ? seed.locator : active?.binding?.selection.locator ?? seed.locator;
  const seedBinary = library.find(binary => seed.binaryHash && binary.sha256 === seed.binaryHash)
    || library.find(binary => seed.slug && binary.slug === seed.slug)
    || library.find(binary => seed.program && binary.program === seed.program);
  const seedHash = seed.binaryHash || String(seedBinary?.sha256 || "");
  const seedPlatform = String(seedBinary?.platform || seedBinary?.architecture || seedBinary?.format || "");
  const seedName = String(seedBinary?.name || seedBinary?.program || seed.program || seed.slug || "");
  function presets(hash: string): string[] {
    const matching = library.find(b => b.sha256 === hash)?.coverage?.matchingPreset;
    const ids = Array.isArray(matching?.ids) ? matching.ids.filter((id: unknown): id is string => typeof id === "string") : [];
    return [...new Set<string>([...ids, ...descriptors(hash).map(p => p.id)])];
  }
  function descriptors(hash: string): Data[] {
    const rows = library.find(b => b.sha256 === hash)?.coverage?.matchingPreset?.presets;
    return Array.isArray(rows) ? rows.filter(p => p && typeof p.id === "string" && Array.isArray(p.targets)) : [];
  }
  function targets(preset: Data | undefined): Data[] {
    return (preset?.targets || []).filter((t: Data) => t && typeof t.function === "string"
      && /^[A-Za-z_][A-Za-z0-9_@$?]*$/.test(t.function) && typeof t.targetRevision === "string" && sha.test(t.targetRevision));
  }
  const selectedPreset = descriptors(seedHash).find(p => p.id === form.preset);
  const configuredTargets = targets(selectedPreset);
  const compatiblePresetIds = active?.binding ? presets(active.binding.artifactHash).filter(id => {
    const descriptor = descriptors(active.binding!.artifactHash).find(p => p.id === id);
    return descriptor ? presetCompatible(active, descriptor) : id === active.preset;
  }) : [];
  function choosePreset(id: string) {
    const preset = descriptors(seedHash).find(p => p.id === id);
    const matchingTarget = targets(preset).find(t => t.function === form.symbol || t.symbol === form.symbol);
    setForm(f => ({ ...f, preset: id, platform: typeof preset?.platform === "string" && preset.platform ? preset.platform : f.platform,
      symbol: preset ? matchingTarget?.function || "" : f.symbol,
      targetRevision: matchingTarget?.targetRevision || "" }));
  }
  function begin() {
    importSequence.current++;
    setSeed({ ...selection });
    setCreating(true);
    setError("");
    setAutoTarget("");
    setAutoTargetLoading(false);
    const binary = library.find(row => selection.binaryHash && row.sha256 === selection.binaryHash)
      || library.find(row => selection.slug && row.slug === selection.slug)
      || library.find(row => selection.program && row.program === selection.program);
    const hash = selection.binaryHash || String(binary?.sha256 || "");
    const ids = presets(hash);
    setForm({ ...blankForm(),
      title: selection.addr ? `Function at ${selection.addr}` : (binary?.name || binary?.program || selection.program || selection.slug) ? `${binary?.name || binary?.program || selection.program || selection.slug} scratch` : "Untitled scratch",
      platform: String(binary?.platform || binary?.architecture || binary?.format || ""),
      preset: ids.length === 1 ? ids[0] : "",
      symbol: "",
    });
  }
  useEffect(() => {
    let live = true;
    void loadScratches().then(({ scratches: rows, warnings }) => { if (live) { setScratches(rows); setStorageWarnings(warnings); setSelected(rows[0]?.id || ""); setCreating(!rows.length || createNonce > 0); if (!rows.length || createNonce > 0) begin(); setSaving(warnings.length ? "Storage warnings — review retained records" : "Saved locally"); } })
      .catch(e => { if (live) { setError(message(e)); setSaving("Storage unavailable — download drafts"); setCreating(true); } }).finally(() => { if (live) setReady(true); });
    return () => { live = false; };
  }, []);
  useEffect(() => { if (nonce.current !== createNonce) { nonce.current = createNonce; begin(); } }, [createNonce]);
  useEffect(() => {
    if (!isActive) return;
    let live = true; setLibrary([]); setProviderError("");
    void request(`${API}/binaries?locator=${encodeURIComponent(discoveryLocator)}`).then(data => { if (live) setLibrary(Array.isArray(data.binaries) ? data.binaries : []); })
      .catch(e => { if (live) setProviderError(`Configured preset discovery unavailable: ${message(e)}`); });
    return () => { live = false; };
  }, [discoveryLocator, revision, isActive]);
  useEffect(() => {
    if (!creating || !seed.addr) return;
    let live = true;
    const sequence = ++importSequence.current;
    setAutoTargetLoading(true);
    void request(`${API}/function?${query(seed)}`).then(raw => {
      if (!live || sequence !== importSequence.current) return;
      const data = raw.listing ? { ...raw, ...raw.listing, function: raw.selected } : raw;
      const assembly = data.assembly?.text || data.disassembly?.text;
      if (!assembly) { setAutoTarget("Selected function has no recorded assembly yet; a draft can still be created."); return; }
      const functionName = String(data.name || data.function?.name || "");
      setForm(f => {
        const preset = descriptors(seedHash).find(p => p.id === f.preset);
        const matchingTarget = targets(preset).find(t => t.function === functionName || t.symbol === functionName);
        return { ...f, target: f.target.trim() ? f.target : String(assembly),
          symbol: f.symbol || (preset ? matchingTarget?.function || "" : functionName),
          targetRevision: f.targetRevision || matchingTarget?.targetRevision || "" };
      });
      setAutoTarget(`Loaded assembly from ${functionName || seed.addr}.`);
    }).catch(error => {
      if (live && sequence === importSequence.current) setAutoTarget(`Assembly could not be loaded automatically: ${message(error)}`);
    }).finally(() => { if (live && sequence === importSequence.current) setAutoTargetLoading(false); });
    return () => { live = false; };
  }, [creating, seed.addr, seed.binaryHash, seed.locator, seed.program, seed.slug, seedHash]);
  useEffect(() => {
    if (!creating) return;
    setForm(current => {
      const presetIds = presets(seedHash);
      const preset = !current.preset && presetIds.length === 1 ? descriptors(seedHash).find(row => row.id === presetIds[0]) : undefined;
      const target = targets(preset).find(row => row.function === current.symbol || row.symbol === current.symbol);
      const platform = current.platform || (typeof preset?.platform === "string" ? preset.platform : seedPlatform);
      if (current.preset || (!preset && platform === current.platform)) return current;
      return { ...current, preset: preset?.id || current.preset, platform,
        symbol: current.symbol || target?.function || "", targetRevision: current.targetRevision || target?.targetRevision || "" };
    });
  }, [creating, library, seedHash, seedPlatform]);
  useEffect(() => {
    if (!attempt || !matchingJobId || matchingJobId === attempt.previousJob) return;
    let live = true; let timer = 0;
    const poll = async () => {
      try { const response = await request(`/api/v1/jobs/${encodeURIComponent(matchingJobId)}`); if (!live) return;
        const next = response.job || response; setJob(next); if (!terminal.has(String(next.status))) timer = window.setTimeout(poll, 1000);
      } catch (e) { if (live) setJob({ status: "failed", error: message(e) }); }
    };
    void poll(); return () => { live = false; window.clearTimeout(timer); };
  }, [attempt, matchingJobId]);
  function persist(s: Scratch) {
    const sequence = ++saveSequence.current; setSaving("Saving…");
    void saveScratch(s).then(() => {
      if (sequence === saveSequence.current) { setSaving("Saved locally"); setError(""); }
    }).catch(e => { setSaving("Not saved — download JSON to retain changes"); setError(message(e)); });
  }
  function edit(patch: Partial<Scratch>) {
    if (!active) return; const next = { ...active, ...patch, revision: active.revision + 1 };
    if (patch.preset && !compatiblePresetIds.includes(patch.preset)) { setError("This preset requires a different target. Create a new scratch to bind it explicitly."); return; }
    setScratches(rows => rows.map(s => s.id === next.id ? next : s)); setAttempt(null); setJob({}); persist(next);
  }
  async function importTarget() {
    const sequence = ++importSequence.current;
    try { const raw = await request(`${API}/function?${query(seed)}`); if (sequence !== importSequence.current) return;
      const data = raw.listing ? { ...raw, ...raw.listing, function: raw.selected } : raw;
      const assembly = data.assembly?.text || data.disassembly?.text;
      if (!assembly) throw new Error("No recorded assembly. Paste target assembly to continue.");
      const functionName = String(data.name || data.function?.name || "");
      setForm(f => {
        const preset = descriptors(seedHash).find(p => p.id === f.preset);
        const matchingTarget = targets(preset).find(t => t.function === functionName || t.symbol === functionName);
        return { ...f, target: String(assembly), symbol: preset ? f.symbol || matchingTarget?.function || "" : functionName || f.symbol,
          targetRevision: preset && f.symbol ? f.targetRevision : matchingTarget?.targetRevision || f.targetRevision };
      });
    } catch (e) { if (sequence === importSequence.current) setError(message(e)); }
  }
  function create() {
    if (!form.title.trim()) { setError("Give this scratch a title before creating it."); return; }
    const configuredTarget = configuredTargets.find(t => t.function === form.symbol);
    if (form.bind && selectedPreset && (!configuredTarget || configuredTarget.targetRevision !== form.targetRevision)) {
      setError("Select a valid configured target function from this preset before binding."); return;
    }
    if (form.bind && (!sha.test(seedHash) || !seed.addr || !sha.test(form.targetRevision) || !presets(seedHash).includes(form.preset) || !/^[A-Za-z_][A-Za-z0-9_@$?]*$/.test(form.symbol))) {
      setError("Binding requires a selected binary/function, configured preset, safe function symbol, and preset target-object SHA-256."); return;
    }
    const s: Scratch = { schema: 1, id: crypto.randomUUID(), revision: 0, title: form.title.trim(), platform: form.platform, preset: form.preset, symbol: form.symbol, target: form.target, context: form.context, source: form.source, createdAt: new Date().toISOString(), binding: form.bind ? { selection: { ...seed }, artifactHash: seedHash, targetRevision: form.targetRevision } : null };
    importSequence.current++; setScratches(rows => [...rows, s]); setSelected(s.id); setCreating(false); setTab("source"); setAttempt(null); setJob({}); persist(s);
  }
  const result = parseMatchPayload(job), sameDraft = active && attempt && active.id === attempt.id && active.revision === attempt.revision;
  const validResult = Boolean(active && attempt && resultBelongs(active, attempt, result));
  const attributableError = sameDraft && result.candidateRevision === attempt?.hash
    && result.artifactHash === active?.binding?.artifactHash && result.function === active?.symbol
    && ["failed", "compile-failed", "cancelled"].includes(String(result.phase)) ? result.error : "";
  const jobStarted = Boolean(sameDraft && matchingJobId && matchingJobId !== attempt?.previousJob);
  const busy = hashing || Boolean(jobStarted && !terminal.has(String(job.status)));
  const phase = validResult ? matchingPhase(matchingJobId, job, provider.available) : jobStarted ? (job.status === "failed" ? "failed" : terminal.has(String(job.status)) ? "incomplete" : "compiling") : "draft";
  const receipt = validResult && result.receipt && typeof result.receipt === "object" ? result.receipt : null;
  const aligned: Data[] = Array.isArray(receipt?.alignedDiff) ? receipt.alignedDiff : [];
  const unavailable = !active?.binding ? "Standalone scratch: compilation requires a configured binary target. Local editing and export remain available."
    : !onMatchCandidate || !provider.available ? "Candidate matching action is not registered or cannot be submitted by this shell."
    : !compatiblePresetIds.includes(active.preset) ? "No configured preset compatible with this captured function and target hash is currently advertised. Create a new scratch to choose a different target." : "";
  async function compile() {
    if (!active?.binding || unavailable || busy) return;
    const captured = active; setHashing(true); setError("");
    try {
      if (!captured.source.trim()) throw new Error("Candidate source is required to compile.");
      if (new TextEncoder().encode(translationUnit(captured)).length > 2 * 1024 * 1024) throw new Error("Combined context and source exceeds the compiler's 2 MiB limit.");
      const hash = await candidateHash(captured);
      if (current.current?.id !== captured.id || current.current.revision !== captured.revision) return;
      setJob({}); setAttempt({ id: captured.id, revision: captured.revision, hash, previousJob: matchingJobId });
      onMatchCandidate?.({ artifactHash: captured.binding!.artifactHash, targetRevision: captured.binding!.targetRevision, function: captured.symbol, candidateSource: translationUnit(captured), compilerPreset: captured.preset }, { ...captured.binding!.selection });
      notify("Review captured target, configured preset, and combined context/source to approve compilation.");
    } catch (e) { setError(message(e)); setAttempt(null); } finally { setHashing(false); }
  }
  if (!ready) return <section className="scratch-workspace" aria-label="Scratch workspace"><p role="status">{saving}</p></section>;
  return <section className="scratch-workspace" aria-label="Scratch workspace" data-mobile-tab={tab} data-creating={creating}>
    <header className="scratch-toolbar">
      <label className="scratch-selector"><span>Local scratch</span><select value={selected} onChange={e => { importSequence.current++; setSelected(e.target.value); setCreating(false); setTab("source"); setAttempt(null); setJob({}); }}><option value="">Select scratch</option>{scratches.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}</select></label>
      <div className="scratch-desktop-actions"><button type="button" onClick={begin}>New scratch</button>
        {active && <><button onClick={() => download(active)}>Download JSON</button><button onClick={() => download(active, true)}>Download C</button><button onClick={() => persist(active)}>Save</button></>}</div>
      <details className="scratch-mobile-actions"><summary>Actions</summary><div onClick={event => { if (event.target instanceof Element && event.target.closest("button")) event.currentTarget.parentElement?.removeAttribute("open"); }}>
        <button type="button" onClick={begin}>New scratch</button>
        {active && <><button onClick={() => download(active)}>Download JSON</button><button onClick={() => download(active, true)}>Download C</button><button onClick={() => persist(active)}>Save</button>
          <button disabled={!!unavailable || busy || !active.source.trim()} onClick={() => void compile()}>Compile &amp; compare</button><p>{unavailable || phase}</p></>}
      </div></details>
      <span className="scratch-save-state" role="status">{saving}</span>
    </header>
    {error && <p role="alert">{error} {active && <button onClick={() => download(active)}>Download unsaved scratch</button>}</p>}
    {!error && jobStarted && (attributableError || validResult && result.error || job.error) && <p role="alert">{String(attributableError || validResult && result.error || job.error)}</p>}
    {storageWarnings.length > 0 && <details className="scratch-storage-warnings"><summary role="alert">Storage warnings ({storageWarnings.length}) — healthy drafts remain available</summary><ul>{storageWarnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}
    {creating ? <form className="scratch-create" onSubmit={e => { e.preventDefault(); create(); }}>
      <header className="scratch-create-heading"><div><p className="muted">Local draft · saved in this browser</p><h2>Start a scratch</h2></div><span>Comparison setup is optional</span></header>
      <section className="scratch-start-summary" aria-label="Scratch starting context"><div><small>Starting from</small><strong>{seedName || "No binary selected"}</strong><span>{seed.addr ? `${seed.logicalId || "Selected function"} · ${seed.addr}` : "You can add a binary or function later"}</span></div><p>Write first, or attach a configured compiler target when you are ready to compare.</p></section>
      <label>Scratch title<input ref={titleInput} required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}/></label>
      <label className="scratch-primary-source">Candidate C source<textarea spellCheck={false} placeholder="Start writing C, or create the draft and use the editor." value={form.source} onChange={e => setForm({ ...form, source: e.target.value })}/></label>
      <details className="scratch-target-setup" open={Boolean(seed.addr)}><summary>Set up target comparison <small>Optional · exact build and compiler configuration</small></summary>
        <div className="scratch-fields">
          <label>Platform metadata<input list="scratch-platforms" value={form.platform} placeholder={seedPlatform || "Auto-detected when available"} onChange={e => setForm({ ...form, platform: e.target.value })}/></label>
          <datalist id="scratch-platforms">{[...new Set(library.map(b => b.platform).filter(v => typeof v === "string" && v))].map(p => <option key={p} value={p}/>)}</datalist>
          <label>Compiler preset<select value={form.preset} onChange={e => choosePreset(e.target.value)}><option value="">Choose only if advertised for this binary</option>{presets(seedHash).map(id => <option key={id} value={id}>{descriptors(seedHash).find(p => p.id === id)?.label || id}</option>)}</select></label>
          {selectedPreset ? <label>Configured target function<select value={form.symbol} onChange={e => {
            const target = configuredTargets.find(t => t.function === e.target.value);
            setForm({ ...form, symbol: target?.function || "", targetRevision: target?.targetRevision || "" });
          }}><option value="">Choose a configured function</option>{configuredTargets.map(t => <option key={t.function} value={t.function}>{t.function}{t.symbol && t.symbol !== t.function ? ` → ${t.symbol}` : ""}</option>)}</select></label>
            : <label>Diff label / function symbol<input value={form.symbol} onChange={e => setForm({ ...form, symbol: e.target.value })}/></label>}
        </div>
        <p>Platform is descriptive metadata. A compiler is usable only when a compatible preset is advertised for the exact captured binary. {providerError}</p>
        <label className="scratch-check"><input type="checkbox" checked={form.bind} disabled={!sha.test(seedHash) || !seed.addr} onChange={e => setForm({ ...form, bind: e.target.checked })}/>Bind this selected function to its exact binary target{seed.program ? ` · ${seed.program}` : ""}</label>
        {form.bind && <p>Analysis context: {seed.program || seed.slug} {seed.addr}. Compilation target: {form.symbol || "choose a configured function"}. This binding is what permits exact compiler comparison.</p>}
        {form.bind && (selectedPreset ? <p>Target-object revision: <code>{form.targetRevision || "Choose a configured function"}</code></p>
          : <details><summary>Advanced: legacy target-object revision</summary><label>Target-object SHA-256<input pattern="[a-f0-9]{64}" value={form.targetRevision} onChange={e => setForm({ ...form, targetRevision: e.target.value.trim().toLowerCase() })}/><small>Only use a configured target-object hash. Function-evidence revisions are not target-object hashes.</small></label></details>)}
        {seed.addr && <p className="scratch-auto-target" role="status">{autoTargetLoading ? "Loading selected function assembly…" : autoTarget || (form.target ? "Selected function assembly is ready." : "You can paste assembly if it is not available." )} <button type="button" onClick={() => void importTarget()}>Load again</button></p>}
        <label>Target assembly <small>Reference text; the captured target-object revision is the comparison authority.</small><textarea spellCheck={false} placeholder="Automatically loaded for a selected function, or paste it here." value={form.target} onChange={e => { importSequence.current++; setForm({ ...form, target: e.target.value }); }}/></label>
        <label>Context to prepend (optional)<textarea spellCheck={false} value={form.context} onChange={e => setForm({ ...form, context: e.target.value })}/></label>
      </details>
      <p className="scratch-create-note">A draft can be created without platform, target assembly, or a compiler. Compile &amp; compare appears only after you explicitly bind a compatible configured target.</p>
      <div className="scratch-create-actions"><button type="submit">Create scratch and open editor</button><button type="button" onClick={() => { importSequence.current++; setCreating(false); }}>{active ? "Keep current scratch" : "Return to match review"}</button></div>
    </form> : active ? <>
      <div className="scratch-toolbar scratch-settings-bar"><label>Platform<input value={active.platform} onChange={e => edit({ platform: e.target.value })}/></label>
        <label>Compiler preset<select value={active.preset} onChange={e => edit({ preset: e.target.value })}><option value="">No configured preset</option>{[...new Set([active.preset, ...compatiblePresetIds])].filter(Boolean).map(id => <option key={id} disabled={!compatiblePresetIds.includes(id)}>{id}</option>)}</select></label>
        <button disabled={!!unavailable || busy || !active.source.trim()} onClick={() => void compile()}>Compile &amp; compare</button><span role="status">{hashing ? "Preparing exact revision…" : sameDraft && !jobStarted ? "Awaiting approval / job submission" : phase}</span>
      </div>
      <p className="scratch-status" title={`${unavailable || "Configured preset advertised; the server validates compiler and target availability on submission. Compile success and similarity are not byte proof."} ${providerError}`}>{unavailable || "Configured preset advertised; the server validates compiler and target availability on submission. Compile success and similarity are not byte proof."} {providerError}</p>
      <div className="scratch-mobile-tabs" aria-label="Scratch views">{["source", "context", "options", "target", "output"].map(name => <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name[0].toUpperCase() + name.slice(1)}</button>)}</div>
      <div className="scratch-split"><section className="scratch-pane" aria-label="Candidate editor">
        <div className="scratch-tabs" aria-label="Editor sections">{["source", "context", "options"].map(name => <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name === "source" ? "Candidate C" : name === "context" ? "Context" : "Options"}</button>)}</div>
        {tab === "options" ? <div className="scratch-options"><div className="scratch-mobile-settings">
          <label>Platform<input value={active.platform} onChange={e => edit({ platform: e.target.value })}/></label>
          <label>Compiler preset<select value={active.preset} onChange={e => edit({ preset: e.target.value })}><option value="">No configured preset</option>{[...new Set([active.preset, ...compatiblePresetIds])].filter(Boolean).map(id => <option key={id} disabled={!compatiblePresetIds.includes(id)}>{id}</option>)}</select></label>
          <p>{unavailable || "Configured preset advertised; the server validates availability on submission."} {providerError}</p>
        </div><label>Scratch title<input value={active.title} onChange={e => edit({ title: e.target.value })}/></label><label>Diff label / function symbol<input readOnly={!!active.binding} value={active.symbol} onChange={e => edit({ symbol: e.target.value })}/></label>
          <p>{active.binding ? `Captured analysis context: ${active.binding.selection.program} ${active.binding.selection.addr}. Compilation target: ${active.symbol}` : "Standalone target"}</p>{active.binding && <><code>{active.binding.targetRevision}</code><button onClick={() => onSelect({ ...active.binding!.selection })}>Navigate to captured analysis context</button><p>Assembly is reference text; byte proof compares the configured target object at this SHA-256. Create a new scratch to use another target or symbol.</p></>}
        </div> : <ScratchEditor key={`${active.id}:${tab}`} active={isActive} label={tab === "source" ? "Candidate C source" : "Context prepended to candidate C"} value={tab === "source" ? active.source : active.context} onChange={value => edit(tab === "source" ? { source: value } : { context: value })}/>}
      </section><section className="scratch-pane" aria-label="Target and compile comparison">
        <label className="scratch-editor">Target assembly {active.binding ? "(captured reference)" : "(editable standalone target)"}<textarea readOnly={!!active.binding} spellCheck={false} value={active.target} onChange={e => edit({ target: e.target.value })}/></label>
        <div className="scratch-results"><div className="scratch-tabs" aria-label="Output sections">{["compilation", "objdiff"].map(name => <button key={name} aria-pressed={outputTab === name} onClick={() => setOutputTab(name)}>{name === "compilation" ? "Compilation" : "objdiff"}</button>)}</div>
          <div className="scratch-output">
          {!validResult ? <p role="status">{jobStarted ? attributableError || job.error || "No result validated for this scratch revision yet." : "No current result. Editing a draft invalidates prior results."}</p> : <>
            <p role="status">{phase === "objdiff-verified" ? "Objdiff verified for this exact candidate and captured target." : phase}</p>
            {outputTab === "compilation" ? <InstructionDiff rows={instructionDiffRows({receipt})} verified={phase==='objdiff-verified'} onNavigate={addr=>onSelect({...active.binding?.selection,addr})}/> :
              <DiffEvidence receipts={receipt ? [receipt] : []} mismatches={aligned.filter(row => row.differs).map((row, i) => ({ id: String(i), summary: String(row.diffKind || "Instruction differs"), expected: String(row.target || "—"), actual: String(row.candidate || "—") }))}/>}
          </>}
          </div><section className="scratch-problems" aria-label="Compiler problems"><h3>Problems</h3>
            {(validResult && result.error || attributableError || jobStarted && job.error) ? <p role="alert">{String(validResult ? result.error || job.error : attributableError || job.error)}</p> : <p>No compiler errors recorded for the current revision.</p>}
            {validResult && <pre aria-label="Compiler stages and diagnostics">{JSON.stringify(result.stages || [], null, 2)}</pre>}
          </section>
        </div>
      </section></div>
    </> : <p>Create a local scratch to begin.</p>}
  </section>;
}
