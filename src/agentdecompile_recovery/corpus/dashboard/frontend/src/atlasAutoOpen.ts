/** Binary identity for one-shot function auto-open (slug|program|locator). */
export function binaryIdentityKey(parts: {
  slug?: string;
  program?: string;
  locator?: string;
}): string {
  const slug = String(parts.slug || "");
  const program = String(parts.program || "");
  const locator = String(parts.locator || "");
  if (!slug && !program && !locator) return "";
  return `${slug}|${program}|${locator}`;
}

/** Whether AtlasAnalysis should auto-select the top ranked row once. */
export function shouldAutoOpenFunction(args: {
  browseOnly: boolean;
  addr: string;
  rowCount: number;
  binaryKey: string;
  openedForKey: string | null;
}): boolean {
  if (args.browseOnly) return false;
  if (args.addr) return false;
  if (args.rowCount <= 0) return false;
  if (!args.binaryKey) return false;
  if (args.openedForKey === args.binaryKey) return false;
  return true;
}
