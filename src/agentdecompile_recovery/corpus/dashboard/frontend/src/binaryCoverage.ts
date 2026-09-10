import type { Data } from "./contracts";

export function binaryCoverageLabel(row: Data): string {
  const coverage = row.coverage || {};
  const hash = coverage.exactHashRegistration?.status === "confirmed" ? "hash registered" : "hash unconfirmed";
  const parser = coverage.parser?.status === "supported" ? `${coverage.parser.format} parser` : "parser unsupported";
  const provider = coverage.projectProvider?.status === "available" ? "project bound" : "project not bound";
  const evidence = coverage.evidence?.status === "available" ? "evidence available" : "no evidence";
  const preset = coverage.matchingPreset?.status === "available" ? "preset available" : "no matching preset";
  const proof = coverage.proof?.phase || "awaiting independent comparison";
  return `${hash} · ${parser} · ${provider} · ${evidence} · ${preset} · proof ${proof}`;
}
