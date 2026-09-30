import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  API,
  request,
  type Data,
  type Notify,
  type Selection,
} from "./contracts";
import { DialogFrame } from "./Actions";
type Mode = "open" | "create" | "copy" | "connection" | "import" | null;
type FileItem = { file: File; path: string };
const post = (url: string, body: Data) =>
  request(url, { method: "POST", body: JSON.stringify(body) });
function programName(item: any): string {
  return typeof item === "string"
    ? item
    : item?.name || item?.path || item?.program || "";
}
async function droppedFiles(event: DragEvent): Promise<FileItem[]> {
  const entries = Array.from(event.dataTransfer.items)
    .map((item) => (item as any).webkitGetAsEntry?.())
    .filter(Boolean);
  async function walk(entry: any, prefix = ""): Promise<FileItem[]> {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) =>
        entry.file(resolve, reject),
      );
      return [{ file, path: prefix + file.name }];
    }
    if (!entry.isDirectory) return [];
    const reader = entry.createReader();
    const children: any[] = [];
    for (;;) {
      const next = await new Promise<any[]>((resolve, reject) =>
        reader.readEntries(resolve, reject),
      );
      if (!next.length) break;
      children.push(...next);
    }
    return (
      await Promise.all(
        children.map((child) => walk(child, prefix + entry.name + "/")),
      )
    ).flat();
  }
  return entries.length
    ? (await Promise.all(entries.map((entry) => walk(entry)))).flat()
    : Array.from(event.dataTransfer.files).map((file) => ({
        file,
        path: file.webkitRelativePath || file.name,
      }));
}
export function ProjectDialog({
  mode,
  selection,
  onClose,
  onSelect,
  notify,
  onRefresh,
}: {
  mode: Mode;
  selection: Selection;
  onClose: () => void;
  onSelect: (patch: Partial<Selection>) => void;
  notify: Notify;
  onRefresh: () => void;
}) {
  const [locator, setLocator] = useState(""),
    [name, setName] = useState(""),
    [destination, setDestination] = useState("");
  const [kind, setKind] = useState("ghidra-project"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [inspection, setInspection] = useState<Data | null>(null),
    [result, setResult] = useState<Data | null>(null),
    [files, setFiles] = useState<FileItem[]>([]),
    [outcomes, setOutcomes] = useState<Data[]>([]);
  const [browse, setBrowse] = useState<Data | null>(null);
  const folder = useRef<HTMLInputElement>(null);
  const uploadedPaths = useRef(new Map<string, string>());
  const projectRef = useRef({
    locator: selection.locator,
    slug: selection.slug,
  });
  useEffect(() => {
    setLocator("");
    setName("");
    setDestination("");
    setError("");
    setResult(null);
    setInspection(null);
    setFiles([]);
    setOutcomes([]);
    setBrowse(null);
    projectRef.current = { locator: selection.locator, slug: selection.slug };
  }, [mode]);
  useEffect(() => {
    folder.current?.setAttribute("webkitdirectory", "");
  }, [mode]);
  if (!mode) return null;
  const titles = {
    open: "Open project",
    create: "Create project",
    copy: "Copy project",
    connection: "Save connection",
    import: "Import binaries or project",
  };
  async function inspect(value = locator) {
    const data = await request(
      `${API}/inspect?locator=${encodeURIComponent(value.trim())}`,
    );
    setInspection(data);
    return data;
  }
  async function open(value: string, inspected?: Data) {
    const data = inspected || (await inspect(value));
    const selected = {
      locator: data.locator || value,
      slug: data.slug || "",
      program: data.program_paths?.[programName(data.programs?.[0])] || programName(data.programs?.[0]),
    };
    projectRef.current = { locator: selected.locator, slug: selected.slug };
    onSelect(selected);
    onRefresh();
    return data;
  }
  async function ensureProject() {
    if (projectRef.current.locator) return projectRef.current;
    const created = await post(`${API}/projects`, {
      name:
        name.trim() ||
        files[0]?.file.name.replace(/\.[^.]+$/, "") ||
        "Imported binaries",
    });
    projectRef.current = {
      locator: created.locator || created.gpr,
      slug: created.slug || "",
    };
    onSelect(projectRef.current);
    await open(projectRef.current.locator, created);
    return projectRef.current;
  }
  async function uploadMemberBinary(file: File) {
    const body = new FormData();
    body.append("file", file, file.name);
    body.append("role", "member");
    // source_path is the immutable staged upload. binary.locator can name
    // another project and binary.repo a virtual Ghidra-only row; neither is a
    // readable file for import-binary. Registration may fail (HTTP 400) while
    // staging succeeded, so read the body instead of throwing on status.
    const response = await fetch(`${API}/binaries`, { method: "POST", body });
    const uploaded = await response.json().catch(() => ({}));
    const path: string | undefined = uploaded?.source_path;
    if (!path) throw new Error(uploaded?.error || "Upload returned no server path.");
    return path;
  }
  async function queueImportBatch(
    project: { locator: string; slug: string },
    targets: { path: string; name: string }[],
  ) {
    if (!targets.length) return null;
    const result = await request("/api/v1/batches", {
      method: "POST",
      body: JSON.stringify({
        key: crypto.randomUUID(),
        action: "mcp.import-binary",
        params: { analyzeAfterImport: false },
        confirm: true,
        targets: targets.map((target) => ({
          locator: project.locator,
          params: {
            file_path: target.path,
            programName: target.name,
            analyzeAfterImport: false,
          },
        })),
      }),
    });
    window.dispatchEvent(new Event("library-import-submitted"));
    return result;
  }
  async function receiveFiles(items: FileItem[]) {
    uploadedPaths.current.clear();
    setResult(null);
    setFiles(items);
    setOutcomes([]);
    setError("");
  }
  async function runImport(): Promise<{ message: string; details?: Data }> {
    if (!files.length) {
      if (!locator.trim())
        throw new Error("Choose files or enter a server path.");
      const project = await ensureProject();
      const path = locator.trim();
      const batch = await queueImportBatch(project, [
        { path, name: path.split(/[/\\]/).pop() || "binary" },
      ]);
      return {
        message: "Queued 1 binary import. Track progress in Activity and Imports.",
        details: { batchId: batch?.batch?.id, target: project.locator },
      };
    }
    const paths = files.map((item) => item.path);
    const isProject = paths.some((path) =>
      /\.gpr$|\.rep(?:\/|$)|(?:^|\/)~index.dat$|(?:^|\/)users$/i.test(path),
    );
    if (isProject) {
      const gpr = paths.find((path) => /\.gpr$/i.test(path));
      if (
        gpr &&
        !paths.some((path) => path.startsWith(gpr.replace(/\.gpr$/i, ".rep/")))
      )
        throw new Error(
          "Choose the project folder containing both the .gpr file and its .rep directory. A .gpr file alone does not contain the program databases.",
        );
      const body = new FormData();
      files.forEach((item) => body.append("file", item.file, item.file.name));
      body.append("paths", JSON.stringify(paths));
      const stage = await request(`${API}/stage-drop`, {
        method: "POST",
        body,
      });
      const resolved = await post(`${API}/resolve-drop`, {
        name: gpr || paths[0].split("/")[0],
        relativePaths: paths,
        staging_id: stage.staging_id,
      });
      if (!resolved.locator)
        throw new Error(
          resolved.candidates?.length
            ? "Several projects were found. Open the project you want using its server path."
            : "The staged files did not resolve to a project.",
        );
      const selected = {
        locator: resolved.locator,
        slug: resolved.slug || "",
        program: programName(resolved.programs?.[0]) || "",
      };
      await open(resolved.locator, resolved);
      void request(API + "/prepare", {
        method: "POST",
        body: JSON.stringify({ locator: selected.locator }),
      });
      return {
        message:
          "Staged project registered. Preparation will continue in the background.",
        details: { locator: selected.locator },
      };
    }
    const project = await ensureProject();
    const targets: { path: string; name: string }[] = [];
    const failed: Data[] = [];
    await Promise.all(
      files.map(async (item) => {
        try {
          const stored = uploadedPaths.current.get(item.path);
          const path = stored ?? (await uploadMemberBinary(item.file));
          if (!stored) uploadedPaths.current.set(item.path, path);
          targets.push({ path, name: item.file.name });
        } catch (e) {
          failed.push({
            name: item.file.name,
            status: "Failed",
            error: e instanceof Error ? e.message : String(e),
            path: item.path,
          });
        }
      }),
    );
    if (failed.length) setOutcomes(failed);
    if (!targets.length)
      throw new Error(
        failed[0]?.error || "No binaries could be uploaded for import.",
      );
    const batch = await queueImportBatch(project, targets);
    if (failed.length) {
      setFiles(
        files.filter((item) => failed.some((row) => row.path === item.path)),
      );
    }
    return {
      message: `Queued ${targets.length} binary import${targets.length === 1 ? "" : "s"}${failed.length ? `; ${failed.length} upload${failed.length === 1 ? "" : "s"} failed` : ""}. Track progress in Activity and Imports.`,
      details: { batchId: batch?.batch?.id, target: project.locator },
    };
  }
  async function submit() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (mode === "import") {
        const summary = await runImport();
        notify(summary.message, "info", summary.details);
        onRefresh();
        onClose();
      } else if (mode === "open") {
        if (!locator.trim()) throw new Error("Enter a project path or URL.");
        await open(
          locator.trim(),
          inspection?.locator === locator.trim() ? inspection : undefined,
        );
        notify("Opened project.");
        onClose();
      } else if (mode === "create") {
        if (!name.trim()) throw new Error("Enter a project name.");
        const data = await post(`${API}/projects`, {
          name: name.trim(),
          destination: destination.trim(),
        });
        await open(data.locator || data.gpr, data);
        notify("Created project.");
        onClose();
      } else {
        if (!name.trim()) throw new Error("Enter a name.");
        if (mode === "connection" && !locator.trim())
          throw new Error("Enter a ghidra:// or HTTP URL.");
        const data = await post(`${API}/save-as`, {
          locator: selection.locator,
          target: mode === "connection" ? "shared-project" : kind,
          name: name.trim(),
          dest: destination.trim(),
          url: locator.trim(),
        });
        setResult(data);
        onRefresh();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function browsePath(path: string) {
    setBusy(true);
    setError("");
    try {
      setBrowse(
        await request(`${API}/browse?path=${encodeURIComponent(path)}`),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const resultLocator =
    result?.http_locator ||
    result?.locator ||
    result?.local_checkout ||
    result?.gpr;
  return (
    <DialogFrame title={titles[mode]} onClose={onClose} busy={busy}>
      <div className="ad-dialog-body">
        {(mode === "create" ||
          mode === "copy" ||
          mode === "connection" ||
          (mode === "import" && !selection.locator)) && (
          <label className="ad-field">
            Project name
            <input
              value={name}
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
        )}
        {(mode === "open" || mode === "connection" || mode === "import") && (
          <label className="ad-field">
            {mode === "connection"
              ? "Server URL"
              : "Server path or project URL"}
            <input
              value={locator}
              disabled={busy}
              onChange={(e) => {
                setLocator(e.target.value);
                setInspection(null);
              }}
              placeholder={
                mode === "connection"
                  ? "ghidra://host/repository"
                  : "/path/to/project.gpr"
              }
            />
            <small>Paths refer to the machine running AgentDecompile.</small>
          </label>
        )}
        {mode === "open" && (
          <div className="ad-dialog-actions">
            <button
              disabled={busy || !locator.trim()}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await inspect();
                } catch (e) {
                  setError(String((e as Error).message));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Inspect path
            </button>
            <button disabled={busy} onClick={() => browsePath(locator)}>
              Browse server
            </button>
          </div>
        )}
        {browse && (
          <section className="ad-file-browser">
            <p>{browse.path || browse.root}</p>
            {browse.parent && (
              <button onClick={() => browsePath(browse.parent)}>
                Parent folder
              </button>
            )}
            {(browse.entries || []).map((entry: Data) => (
              <div key={entry.path}>
                <button
                  onClick={() => {
                    setLocator(entry.path);
                    setInspection(null);
                  }}
                >
                  {entry.name}
                </button>
                {(entry.is_dir ||
                  ["directory", "dir", "project-dir", "shared-fs"].includes(
                    entry.kind,
                  )) && (
                  <button onClick={() => browsePath(entry.path)}>
                    Browse folder
                  </button>
                )}
              </div>
            ))}
          </section>
        )}
        {inspection && (
          <section>
            <h3>Project details</h3>
            <dl>
              <dt>Kind</dt>
              <dd>{inspection.kind}</dd>
              <dt>Programs</dt>
              <dd>{inspection.programs?.length ?? 0}</dd>
              <dt>Location</dt>
              <dd>{inspection.locator}</dd>
            </dl>
            {inspection.origin?.note && <p>{inspection.origin.note}</p>}
          </section>
        )}
        {mode === "create" && (
          <label className="ad-field">
            Destination folder
            <input
              value={destination}
              disabled={busy}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Workspace ghidra-projects folder"
            />
            <small>
              Leave blank to use the current workspace’s ghidra-projects folder.
            </small>
          </label>
        )}
        {mode === "copy" && (
          <>
            <label className="ad-field">
              Copy format
              <select
                value={kind}
                disabled={busy}
                onChange={(e) => setKind(e.target.value)}
              >
                <option value="ghidra-project">Local Ghidra project</option>
                <option value="shared-fs">
                  Ghidra server filesystem layout
                </option>
              </select>
            </label>
            <label className="ad-field">
              Destination folder
              <input
                value={destination}
                disabled={busy}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="Use workspace default"
              />
            </label>
            <p>
              Program databases are copied when available. The result states
              what was written.
            </p>
          </>
        )}
        {mode === "connection" && (
          <p>
            This saves a reopenable connection. It does not copy program
            databases or publish a repository.
          </p>
        )}
        {mode === "import" && (
          <>
            <div
              className="ad-drop"
              onDragOver={(e) => e.preventDefault()}
              onDrop={async (e) => {
                e.preventDefault();
                if (busy) return;
                try {
                  await receiveFiles(await droppedFiles(e));
                } catch (error) {
                  setError(String(error));
                }
              }}
            >
              Drop binaries or a complete Ghidra project folder here.
              <label>
                Choose files
                <input
                  type="file"
                  multiple
                  disabled={busy}
                  onChange={(e) =>
                    receiveFiles(
                      Array.from(e.target.files || []).map((file) => ({
                        file,
                        path: file.webkitRelativePath || file.name,
                      })),
                    )
                  }
                />
              </label>
              <label>
                Choose folder
                <input
                  ref={folder}
                  type="file"
                  multiple
                  disabled={busy}
                  onChange={(e) =>
                    receiveFiles(
                      Array.from(e.target.files || []).map((file) => ({
                        file,
                        path: file.webkitRelativePath || file.name,
                      })),
                    )
                  }
                />
              </label>
            </div>
            {files.length > 0 && <p>{files.length} files selected</p>}
            <p>
              Imports reuse this project. A blank session creates one project
              for all files. Ghidra import runs as a background job; the dialog
              closes as soon as the upload and queue step finishes.
            </p>
          </>
        )}
        {outcomes.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Result</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.map((row, i) => (
                <tr key={i}>
                  <td>{row.name}</td>
                  <td>{row.status}</td>
                  <td>{row.error || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {result && (
          <section role="status">
            <h3>Result</h3>
            <p>
              {result.message ||
                result.origin?.note ||
                result.note ||
                "Saved project metadata. Inspect the saved location for database details."}
            </p>
            {resultLocator && <p>{resultLocator}</p>}
            {resultLocator && (
              <button
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await open(resultLocator);
                    onClose();
                  } catch (e) {
                    setError(String((e as Error).message));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Open saved project
              </button>
            )}
          </section>
        )}
        {error && (
          <p className="ad-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <footer>
        <button onClick={onClose} disabled={busy}>
          {result ? "Close" : "Cancel"}
        </button>
        {(!result || (mode === "import" && files.length > 0)) && (
          <button disabled={busy} onClick={submit}>
            {busy
              ? mode === "import"
                ? "Uploading…"
                : "Working…"
              : result && files.length
                ? "Retry failed files"
                : mode === "open"
                  ? "Open project"
                  : mode === "create"
                    ? "Create project"
                    : mode === "copy"
                      ? "Copy project"
                      : mode === "connection"
                        ? "Save connection"
                        : "Import"}
          </button>
        )}
      </footer>
    </DialogFrame>
  );
}
