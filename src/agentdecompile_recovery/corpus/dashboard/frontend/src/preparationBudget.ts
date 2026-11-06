export function preparationBudgetText(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "Action admissions: unknown";
  const budget = value as Record<string, unknown>;
  const count = (n: unknown): n is number => typeof n === "number" && Number.isSafeInteger(n) && n >= 0;
  const used = count(budget.consumed) ? String(budget.consumed) : "unknown";
  const limit = budget.maxActionAdmissions === null ? "unlimited" : count(budget.maxActionAdmissions) ? String(budget.maxActionAdmissions) : "unknown";
  const revision = count(budget.allocationRevision) ? String(budget.allocationRevision) : "unknown";
  const prior = budget.priorUsageUnknown === true ? " · earlier spending unknown; shown usage is a lower bound" : "";
  const exhausted = count(budget.consumed) && count(budget.maxActionAdmissions) && budget.consumed >= budget.maxActionAdmissions ? " · allowance exhausted" : "";
  return `Action admissions: ${used} used / ${limit} allowance · allocation revision ${revision}${exhausted}${prior}`;
}

export function preparationProviderBudgetText(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "MCP tool calls: unknown";
  const budget = value as Record<string, unknown>;
  if (budget.schema !== 1 || budget.accountingScope !== "mcp-tool-dispatches-since-allocation") return "MCP tool calls: unknown";
  const count = (n: unknown): n is number => typeof n === "number" && Number.isSafeInteger(n) && n >= 0;
  const used = count(budget.consumed) ? String(budget.consumed) : "unknown";
  const limit = budget.maxMcpToolCalls === null ? "unlimited" : count(budget.maxMcpToolCalls) ? String(budget.maxMcpToolCalls) : "unknown";
  const revision = count(budget.allocationRevision) ? String(budget.allocationRevision) : "unknown";
  const prior = budget.priorUsageUnknown === true ? " · earlier spending unknown; shown usage is a lower bound" : "";
  const exhausted = count(budget.consumed) && count(budget.maxMcpToolCalls) && budget.consumed >= budget.maxMcpToolCalls ? " · allowance exhausted" : "";
  return `MCP tool calls: ${used} used / ${limit} allowance · allocation revision ${revision}${exhausted}${prior}`;
}
