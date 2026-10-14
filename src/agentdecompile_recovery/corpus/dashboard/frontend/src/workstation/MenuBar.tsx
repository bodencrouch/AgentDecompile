import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";

export type MenuAction = {
  label: string;
  run: () => void;
  hint?: string;
  shortcut?: string;
  disabled?: boolean;
  selected?: boolean;
};

export type MenuGroup = { label: string; actions: MenuAction[] };

/** A small keyboard- and touch-friendly application menu shared by all workspace actions. */
export function MenuBar({ groups }: { groups: MenuGroup[] }) {
  const root = useRef<HTMLElement>(null);
  const [open, setOpen] = useState("");
  const [anchor, setAnchor] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen("");
    };
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen("");
      root.current?.querySelector<HTMLButtonElement>(`[data-menu-trigger="${CSS.escape(open)}"]`)?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  useEffect(() => {
    if (open) root.current?.querySelector<HTMLButtonElement>(`[data-menu-content="${CSS.escape(open)}"] button:not(:disabled)`)?.focus();
  }, [open]);

  function toggle(label: string, button: HTMLButtonElement) {
    if (open === label) { setOpen(""); return; }
    setAnchor(button.getBoundingClientRect());
    setOpen(label);
  }

  function moveItem(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      const triggers = Array.from(root.current?.querySelectorAll<HTMLButtonElement>(".ws-menu-trigger") || []);
      const current = triggers.findIndex(button => button.dataset.menuTrigger === open);
      const next = triggers[(current + (event.key === "ArrowRight" ? 1 : -1) + triggers.length) % triggers.length];
      if (next) { event.preventDefault(); toggle(next.dataset.menuTrigger || "", next); }
      return;
    }
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key)) return;
    const items = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
    if (!items.length) return;
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
      : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    event.preventDefault();
    items[next]?.focus();
  }

  const style: CSSProperties | undefined = anchor ? {
    left: Math.min(Math.max(8, anchor.left), Math.max(8, window.innerWidth - 320)),
    top: anchor.bottom,
  } : undefined;

  return <nav className="ws-menu-bar" aria-label="Application menu" ref={root}>
    {groups.map(group => <div className="ws-menu-group" key={group.label}>
      <button type="button" className="ws-menu-trigger" data-menu-trigger={group.label}
        aria-expanded={open === group.label} aria-haspopup="menu" aria-controls={`ws-menu-${group.label}`}
        onClick={event => toggle(group.label, event.currentTarget)}
        onKeyDown={event => {
          if (event.key === "ArrowDown" && open !== group.label) {
            event.preventDefault(); toggle(group.label, event.currentTarget);
          }
        }}>{group.label}</button>
      {open === group.label && <div className="ws-menu-popover" id={`ws-menu-${group.label}`} role="menu"
        aria-label={`${group.label} actions`} data-menu-content={group.label} style={style} onKeyDown={moveItem}>
        {group.actions.map(action => <button type="button" role="menuitem" key={action.label}
          disabled={action.disabled} aria-current={action.selected ? "true" : undefined}
          onClick={() => { setOpen(""); action.run(); }}>
          <span className="ws-menu-item-label">{action.label}{action.hint && <small>{action.hint}</small>}</span>
          {action.shortcut && <kbd>{action.shortcut}</kbd>}
        </button>)}
      </div>}
    </div>)}
  </nav>;
}
