/** Client-side project locator key aligned with server session dedupe. */
export function canonicalProjectLocator(value: unknown): string {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const source = text.replaceAll("\\", "/");
  const parts: string[] = [];
  for (const part of source.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") parts.pop();
    else parts.push(part);
  }
  const rooted = source.startsWith("/") ? "/" : "";
  const joined = rooted + parts.join("/");
  return joined.replace(/\/+$/, "") || joined;
}

export function projectLocatorsMatch(left: unknown, right: unknown): boolean {
  const a = canonicalProjectLocator(left);
  const b = canonicalProjectLocator(right);
  return Boolean(a && b && a === b);
}

export type ProjectLocatorValidation =
  | { ok: true; locator: string }
  | { ok: false; code: "empty-locator" | "unsafe-path"; message: string };

/** Validate a display locator without resolving it against the host filesystem. */
export function validateProjectLocator(value: unknown): ProjectLocatorValidation {
  const raw = String(value ?? "").trim();
  if (!raw) return { ok: false, code: "empty-locator", message: "A project locator is required" };
  const source = raw.replaceAll("\\", "/");
  if (source.split("/").includes("..") || source.includes("\0")) {
    return { ok: false, code: "unsafe-path", message: "Project locator must not contain traversal segments" };
  }
  return { ok: true, locator: canonicalProjectLocator(raw) };
}
