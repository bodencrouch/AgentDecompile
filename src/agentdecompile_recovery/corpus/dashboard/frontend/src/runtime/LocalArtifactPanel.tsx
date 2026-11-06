import { useEffect, useMemo, useState } from "react";
import type { ArtifactRecord, EvidenceRecord } from "../analysis/contracts";
import type { Data, Notify } from "../contracts";
import { LocalProjectRuntime } from "./localProject";
import "./local-artifact.css";

export type RecordedArtifactMatch =
  | { state: "unseen" }
  | { state: "unique"; binary: Data }
  | { state: "ambiguous"; binaries: Data[] };

export function matchRecordedArtifact(artifact: ArtifactRecord, binaries: Data[]): RecordedArtifactMatch {
  const matches = binaries.filter((binary) =>
    binary.kind === "binary" && typeof binary.sha256 === "string" && binary.sha256.toLowerCase() === artifact.hash.toLowerCase(),
  );
  if (matches.length === 1) return { state: "unique", binary: matches[0] };
  if (matches.length > 1) return { state: "ambiguous", binaries: matches };
  return { state: "unseen" };
}

type Props = {
  projectId?: string;
  binaries?: Data[];
  notify: Notify;
  onOpenRecorded?: (binary: Data) => void;
};

export function LocalArtifactPanel({ projectId = "local:workbench", binaries = [], notify, onOpenRecorded }: Props) {
  const runtime = useMemo(() => new LocalProjectRuntime(projectId), [projectId]);
  const [status, setStatus] = useState("Restoring local artifact state…");
  const [artifacts, setArtifacts] = useState(runtime.current().artifacts);
  const [evidence, setEvidence] = useState(runtime.current().evidence);
  const [capabilities, setCapabilities] = useState(runtime.current().capabilities);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    void runtime.restore().then((model) => {
      if (!live) return;
      setArtifacts(model?.artifacts || runtime.current().artifacts);
      setEvidence(model?.evidence || runtime.current().evidence);
      setCapabilities(model?.capabilities || runtime.current().capabilities);
      setStatus(model ? "Local artifact snapshot restored." : "No local artifact snapshot for this workspace.");
    }).catch((error) => {
      if (live) setStatus(error instanceof Error ? error.message : "Local artifact storage is unavailable.");
    });
    return () => { live = false; };
  }, [runtime]);

  async function ingest(files: File[]) {
    if (!files.length || busy) return;
    setBusy(true);
    try {
      let completed = 0;
      const failures: string[] = [];
      for (const file of files) {
        setStatus(`Inspecting ${file.name} locally (${completed + 1} of ${files.length})…`);
        const result = await runtime.ingest({ name: file.name, bytes: await file.arrayBuffer(), sourceKind: "regular" });
        if (result.status !== "completed" || !result.value) {
          failures.push(`${file.name}: ${result.failure?.message || result.status}`);
          continue;
        }
        completed += 1;
        setArtifacts(result.value.artifacts);
        setEvidence(result.value.evidence);
        setCapabilities(result.value.capabilities);
      }
      const message = `${completed} of ${files.length} artifacts persisted locally by content hash.${failures.length ? ` ${failures.length} could not be ingested.` : ""}`;
      setStatus(message);
      notify(message, failures.length ? "warning" : "info", failures.length ? { failures } : {});
    } catch (error) {
      const message = error instanceof Error ? error.message : "Local artifact ingest failed.";
      setStatus(message);
      notify(message, "error");
    } finally {
      setBusy(false);
    }
  }

  return <section className="local-artifact-panel" aria-label="Local artifact runtime">
    <header><h2>Local artifact runtime</h2><span role="status">{busy ? "Working" : "Local-first"}</span></header>
    <p>ELF and PE files are hashed, inspected, and stored in this browser before any optional provider is used.</p>
    <label className="local-artifact-picker">Choose artifact
      <input type="file" multiple accept=".elf,.so,.exe,.dll,application/x-elf,application/vnd.microsoft.portable-executable" disabled={busy} onChange={(event) => void ingest(Array.from(event.currentTarget.files || []))} />
    </label>
    <p className="local-artifact-status" role="status">{status}</p>
    <dl><div><dt>Stored artifacts</dt><dd>{artifacts.length}</dd></div><div><dt>Capabilities</dt><dd>{capabilities.map((capability) => `${capability.label}: ${capability.status}`).join(" · ") || "None"}</dd></div></dl>
    {artifacts.length ? <ul>{artifacts.map((artifact) => {
      const match = matchRecordedArtifact(artifact, binaries);
      const parserEvidence = evidence.find((item: EvidenceRecord) => item.source.artifactHash === artifact.hash);
      return <li key={artifact.hash}>
        <div><code>{artifact.hash.slice(0, 12)}</code> {artifact.name} · {artifact.format} · {artifact.architecture}</div>
        <small>{parserEvidence?.summary}</small>
        {match.state === "unique" ? <button onClick={() => onOpenRecorded?.(match.binary)}>Open recorded evidence</button> :
          <small>{match.state === "ambiguous" ? `${match.binaries.length} recorded binaries share this hash; choose one in the explorer.` : "No recorded corpus binding for this exact hash."}</small>}
      </li>;
    })}</ul> : null}
  </section>;
}
