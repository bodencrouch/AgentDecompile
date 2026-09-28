import { useEffect, useRef, useState } from "react";
import { type Data, type SurfaceProps } from "./contracts";
import { ErrorLine, RecordView } from "./ui";
import { useTool } from "./CodeBrowser";
import {
  ensureWorkspaceState,
  patchWorkspaceState,
  workspaceKey,
} from "./workspaceState";

function storageErrors(pieces: Data[], registers: Data[]) {
  if (!pieces.length) return ["Add at least one storage piece."];
  const available = new Map(
    registers.map((register) => [String(register.name), Number(register.size)]),
  );
  return pieces.flatMap((piece, index) => {
    const errors: string[] = [];
    const label = `Piece ${index + 1}`;
    if (!Number.isInteger(piece.size) || piece.size <= 0)
      errors.push(`${label}: bytes must be a positive integer.`);
    if (piece.register !== undefined) {
      const width = available.get(String(piece.register));
      if (width === undefined)
        errors.push(`${label}: select a register advertised by the server.`);
      else if (Number.isInteger(piece.size) && piece.size > width)
        errors.push(`${label}: ${piece.register} is only ${width} bytes wide.`);
    } else if (!Number.isInteger(piece.stackOffset)) {
      errors.push(`${label}: stack offset must be an integer.`);
    }
    return errors;
  });
}

function StorageEditor({
  pieces,
  registers,
  label,
  onChange,
}: {
  pieces: Data[];
  registers: Data[];
  label: string;
  onChange: (next: Data[] | ((rows: Data[]) => Data[])) => void;
}) {
  const update = (index: number, piece: Data) =>
    onChange((rows) => rows.map((row, rowIndex) => (rowIndex === index ? piece : row)));
  return (
    <>
      <table>
        <thead>
          <tr>
            <th>Location</th>
            <th>Register or stack offset</th>
            <th>Bytes</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {pieces.map((piece, index) => (
            <tr key={index}>
              <td>
                <select
                  aria-label={`${label} location ${index + 1}`}
                  value={piece.register !== undefined ? "register" : "stack"}
                  onChange={(event) =>
                    update(index, {
                      size: piece.size,
                      ...(event.target.value === "register"
                        ? { register: registers[0]?.name || "" }
                        : { stackOffset: 0 }),
                    })
                  }
                >
                  <option value="register">Register</option>
                  <option value="stack">Stack</option>
                </select>
              </td>
              <td>
                {piece.register !== undefined ? (
                  <select
                    aria-label={`${label} register ${index + 1}`}
                    value={piece.register}
                    onChange={(event) =>
                      update(index, { ...piece, register: event.target.value })
                    }
                  >
                    {!registers.some((register) => register.name === piece.register) && (
                      <option value={piece.register || ""}>
                        {piece.register || "Select a register"}
                      </option>
                    )}
                    {registers.map((register) => (
                      <option key={register.name} value={register.name}>
                        {register.name} ({register.size} bytes)
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    aria-label={`${label} stack offset ${index + 1}`}
                    type="number"
                    step="1"
                    value={piece.stackOffset ?? ""}
                    onChange={(event) =>
                      update(index, {
                        ...piece,
                        stackOffset:
                          event.target.value === "" ? "" : Number(event.target.value),
                      })
                    }
                  />
                )}
              </td>
              <td>
                <input
                  aria-label={`${label} bytes ${index + 1}`}
                  type="number"
                  min="1"
                  step="1"
                  value={piece.size ?? ""}
                  onChange={(event) =>
                    update(index, {
                      ...piece,
                      size: event.target.value === "" ? "" : Number(event.target.value),
                    })
                  }
                />
              </td>
              <td>
                <button type="button" onClick={() => onChange((rows) => rows.filter((_, i) => i !== index))}>
                  Remove piece
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={() =>
          onChange((rows) => [
            ...rows,
            registers.length
              ? { register: registers[0].name, size: 1 }
              : { register: "", size: 1 },
          ])
        }
      >
        Add storage piece
      </button>
    </>
  );
}

const actionStorage = (pieces: Data[]) =>
  pieces.map(({ register, stackOffset, size }) =>
    register !== undefined ? { register, size } : { stackOffset, size },
  );

export function FunctionEditor({
  props,
  address,
}: {
  props: SurfaceProps;
  address: string;
}) {
  const [open, setOpen] = useState(false),
    [draft, setDraft] = useState<Data>({}),
    [storage, setStorage] = useState<Data[]>([]),
    [returnType, setReturnType] = useState(""),
    [parameterDraft, setParameterDraft] = useState<Data | null>(null);
  const selected = {
    ...props,
    selection: { ...props.selection, addr: address },
  };
  const info = useTool(
    "manage-function",
    { mode: "info", functionIdentifier: address },
    selected,
    open && Boolean(address),
  );
  const storageKey = workspaceKey(
    "function",
    props.selection.locator,
    props.selection.program,
    address,
  );
  const [baseline, setBaseline] = useState<{
    target: string;
    data: Data;
  } | null>(null);
  const targetKey = storageKey;
  const [pending, setPending] = useState<Data | null>(null);
  const [dirty, setDirty] = useState(false);
  const restoredDraftRef = useRef(false);
  const value = baseline?.target === targetKey ? baseline.data : {};
  function adopt(data: Data) {
    setBaseline({ target: targetKey, data });
    setDraft({ ...data });
    setStorage((data.returnStorage || []).map((row: Data) => ({ ...row })));
    setReturnType(data.returnType || "");
    setParameterDraft(null);
    setDirty(false);
    setPending(null);
  }
  useEffect(() => {
    setBaseline(null);
    setPending(null);
    setDraft({});
    setStorage([]);
    setReturnType("");
    setParameterDraft(null);
    setDirty(false);
    restoredDraftRef.current = false;
  }, [targetKey]);
  useEffect(() => {
    if (!open || !address) return;
    let alive = true;
    void ensureWorkspaceState().then((state) => {
      const saved = state.drafts?.[storageKey];
      if (!alive || !saved || typeof saved !== "object" || !saved.draft) return;
      setDraft(saved.draft as Data);
      setStorage((saved.storage as Data[]) || []);
      setReturnType(String(saved.returnType || ""));
      setParameterDraft((saved.parameterDraft as Data) || null);
      setDirty(true);
      restoredDraftRef.current = true;
    });
    return () => {
      alive = false;
    };
  }, [storageKey, open, address]);
  useEffect(() => {
    if (!dirty || !open) return;
    const timer = setTimeout(() => {
      patchWorkspaceState("drafts", storageKey, {
        draft,
        storage,
        returnType,
        parameterDraft,
        updatedAt: Date.now(),
      });
    }, 150);
    return () => clearTimeout(timer);
  }, [storageKey, draft, storage, returnType, parameterDraft, dirty, open]);
  useEffect(() => {
    if (
      info.status !== "loaded" ||
      info.target !== address ||
      info.context !== props.selection.locator + "|" + props.selection.program
    )
      return;
    const incoming = info.data.properties || info.data;
    if (restoredDraftRef.current && !baseline) {
      setBaseline({ target: targetKey, data: incoming });
      restoredDraftRef.current = false;
      return;
    }
    if (dirty && baseline?.target === targetKey) {
      if (JSON.stringify(incoming) !== JSON.stringify(baseline.data))
        setPending(incoming);
    } else adopt(incoming);
  }, [info.data, info.status, targetKey]);
  const edit = (key: string, next: any) => {
    setDirty(true);
    setDraft((d) => ({ ...d, [key]: next }));
  };
  const changeStorage = (next: Data[] | ((rows: Data[]) => Data[])) => {
    setDirty(true);
    setStorage(next);
  };
  const changeReturnType = (next: string) => {
    setDirty(true);
    setReturnType(next);
  };
  const changeParameterStorage = (
    next: Data[] | ((rows: Data[]) => Data[]),
  ) => {
    setDirty(true);
    setParameterDraft((current) =>
      current
        ? {
            ...current,
            storage:
              typeof next === "function" ? next(current.storage || []) : next,
          }
        : current,
    );
  };
  const registers = (value.availableRegisters || []) as Data[];
  const returnErrors = storageErrors(storage, registers);
  const parameterErrors = parameterDraft
    ? storageErrors(parameterDraft.storage || [], registers)
    : [];
  const save = () => {
    const changed = Object.fromEntries(
      ["namespace", "inline", "noReturn", "varArgs", "callFixup", "thunkTarget"]
        .filter((k) => draft[k] !== value[k])
        .map((k) => [k, draft[k]]),
    );
    props.onAction(
      "mcp.manage-function",
      { mode: "set_properties", ...changed },
      [{ ...props.selection, addr: address }],
    );
  };
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Edit function signature and storage</summary>
      <p>
        Target function: <code>{address}</code>. Changes remain analysis
        evidence.
      </p>
      <ErrorLine error={info.error} />
      {dirty && baseline?.target === targetKey && (
        <p role="status">
          Unsaved function edits are preserved.
          {pending
            ? " The recorded function changed after this draft was opened. Review the new values before submitting."
            : ""}{" "}
          <button type="button" onClick={() => adopt(pending || baseline.data)}>
            Discard draft and load {pending ? "updated" : "recorded"} values
          </button>
        </p>
      )}
      {pending && (
        <details>
          <summary>Updated recorded values</summary>
          <RecordView value={pending} />
        </details>
      )}
      {baseline?.target === targetKey ? (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
          >
            <label>
              Namespace{" "}
              <input
                value={draft.namespace || ""}
                onChange={(e) => edit("namespace", e.target.value)}
              />
            </label>
            <label>
              Call fixup{" "}
              <select
                value={draft.callFixup || ""}
                onChange={(e) => edit("callFixup", e.target.value)}
              >
                <option value="">None</option>
                {(value.availableCallFixups || []).map((s: string) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              Thunk target{" "}
              <input
                value={draft.thunkTarget || ""}
                onChange={(e) => edit("thunkTarget", e.target.value)}
                placeholder="Function entry address, or empty"
              />
            </label>
            {["inline", "noReturn", "varArgs"].map((k) => (
              <label key={k}>
                <input
                  type="checkbox"
                  checked={Boolean(draft[k])}
                  onChange={(e) => edit(k, e.target.checked)}
                />
                {k === "noReturn"
                  ? "Does not return"
                  : k === "varArgs"
                    ? "Variable arguments"
                    : "Inline"}
              </label>
            ))}
            <button>Review property changes</button>
          </form>
          <div className="cb-toolbar">
            <label>
              Calling convention{" "}
              <select
                aria-label="Calling convention"
                value={draft.callingConvention || ""}
                onChange={(e) => edit("callingConvention", e.target.value)}
              >
                {!(value.availableCallingConventions || []).includes(
                  value.callingConvention,
                ) && (
                  <option value={value.callingConvention || ""}>
                    {value.callingConvention || "Unspecified"}
                  </option>
                )}
                {(value.availableCallingConventions || []).map((s: string) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <button
              disabled={
                !(value.availableCallingConventions || []).includes(
                  draft.callingConvention,
                )
              }
              onClick={() =>
                props.onAction(
                  "mcp.manage-function",
                  {
                    mode: "set_calling_convention",
                    callingConvention: draft.callingConvention,
                  },
                  [{ ...props.selection, addr: address }],
                )
              }
            >
              Review convention change
            </button>
          </div>
          <h4>Return storage</h4>
          <p>
            Storage follows the selected language. Piece order determines the
            composite value; size is in bytes.
          </p>
          <label>
            Return type{" "}
            <input
              aria-label="Stored return type"
              value={returnType}
              onChange={(e) => changeReturnType(e.target.value)}
            />
          </label>
          <StorageEditor pieces={storage} registers={registers} label="Return storage" onChange={changeStorage} />
          {returnErrors.map((error) => <p role="alert" key={error}>{error}</p>)}
          <button
            disabled={Boolean(returnErrors.length) || !returnType.trim()}
            onClick={() =>
              props.onAction(
                "mcp.manage-function",
                {
                  mode: "set_storage",
                  customStorage: true,
                  returnType,
                  returnStorage: actionStorage(storage),
                },
                [{ ...props.selection, addr: address }],
              )
            }
          >
            Review return storage
          </button>
          <h4>Parameter storage</h4>
          <table>
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Type</th>
                <th>Storage</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(value.parameters || []).map((p: Data) => (
                <tr key={p.ordinal}>
                  <td>{p.name}</td>
                  <td>{p.dataType}</td>
                  <td>
                    {(p.storage || [])
                      .map(
                        (s: Data) =>
                          `${s.register || "stack " + s.stackOffset}:${s.size}`,
                      )
                      .join(", ")}
                  </td>
                  <td>
                    <button
                      type="button"
                      onClick={() => {
                        setDirty(true);
                        setParameterDraft({
                          ordinal: p.ordinal,
                          name: p.name,
                          dataType: p.dataType,
                          storage: (p.storage || []).map((piece: Data) => ({ ...piece })),
                        });
                      }}
                    >
                      Edit parameter storage
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {parameterDraft && (
            <section aria-label={`Edit storage for parameter ${parameterDraft.name}`}>
              <h5>
                Edit {parameterDraft.name} (ordinal {parameterDraft.ordinal})
              </h5>
              <p>
                Type: <code>{parameterDraft.dataType}</code>. Piece order determines
                the composite value; size is in bytes.
              </p>
              <StorageEditor
                pieces={parameterDraft.storage || []}
                registers={registers}
                label={`${parameterDraft.name} storage`}
                onChange={changeParameterStorage}
              />
              {parameterErrors.map((error) => <p role="alert" key={error}>{error}</p>)}
              <button
                type="button"
                disabled={Boolean(parameterErrors.length)}
                onClick={() =>
                  props.onAction(
                    "mcp.manage-function",
                    {
                      mode: "set_storage",
                      customStorage: true,
                      parameterStorage: [{
                        ordinal: parameterDraft.ordinal,
                        dataType: parameterDraft.dataType,
                        storage: actionStorage(parameterDraft.storage || []),
                      }],
                    },
                    [{ ...props.selection, addr: address }],
                  )
                }
              >
                Review parameter storage
              </button>{" "}
              <button type="button" onClick={() => setParameterDraft(null)}>
                Close parameter editor
              </button>
            </section>
          )}
        </>
      ) : (
        <p>{info.status || "Open to read the current function properties."}</p>
      )}
    </details>
  );
}
