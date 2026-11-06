import "./evidence-surface-toggle.css";

/** Segmented Source | Assembly | Both control for Atlas function evidence. */
export type EvidenceSurface = "source" | "assembly" | "compare";

const OPTIONS: { value: EvidenceSurface; label: string }[] = [
  { value: "source", label: "Source" },
  { value: "assembly", label: "Asm" },
  { value: "compare", label: "Both" },
];

export function EvidenceSurfaceToggle(props: {
  value: string;
  onChange: (value: EvidenceSurface) => void;
  "aria-label"?: string;
}) {
  const current = (OPTIONS.some((o) => o.value === props.value)
    ? props.value
    : "source") as EvidenceSurface;
  return (
    <div
      className="evidence-surface-toggle"
      role="group"
      aria-label={props["aria-label"] || "Editor evidence surface"}
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={current === option.value}
          onClick={() => props.onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
