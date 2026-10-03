import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";
import { preparationResponse } from "./preparationResponse";
import { preparationBudgetText, preparationProviderBudgetText } from "./preparationBudget";
import { PreparationProgress } from "./PreparationActivity";

const source = readFileSync(new URL("../../static/workbench-app.js", import.meta.url), "utf8");
const start = source.indexOf("  function preparationBudgetText(");
const end = source.indexOf("  function PreparationObservation(", start);
const staticResponse = runInNewContext(source.slice(source.indexOf("  function preparationResponse("), start) + "; preparationResponse;");
const staticProviderBudget = runInNewContext(source.slice(start, end) + "; preparationProviderBudgetText;");
const staticBudget = runInNewContext(source.slice(start, end) + "; preparationBudgetText;");

describe.each([["React", preparationBudgetText], ["static", staticBudget]])("%s action allowance", (_, display) => {
  it("distinguishes zero and unlimited from missing evidence", () => {
    expect(display({consumed: 0, maxActionAdmissions: 0, allocationRevision: 0})).toContain("0 used / 0 allowance");
    expect(display({consumed: 0, maxActionAdmissions: 0})).toContain("allowance exhausted");
    expect(display({consumed: 4, maxActionAdmissions: null})).toContain("4 used / unlimited");
    expect(display({})).toContain("unknown used / unknown allowance");
    expect(display(null)).toBe("Action admissions: unknown");
  });
  it("does not coerce malformed spending into a successful allowance", () => {
    for (const value of [-1, 1.5, NaN, Infinity, "3", true]) {
      expect(display({consumed: value, maxActionAdmissions: value, allocationRevision: value})).toBe("Action admissions: unknown used / unknown allowance · allocation revision unknown");
    }
  });
  it("preserves uncertainty and shows revision and exhaustion", () => {
    const text = display({consumed: 5, maxActionAdmissions: 4, allocationRevision: 2, priorUsageUnknown: true});
    expect(text).toContain("allocation revision 2");
    expect(text).toContain("allowance exhausted");
    expect(text).toContain("earlier spending unknown; shown usage is a lower bound");
  });
});

it("keeps stale time and allowance visible in compact React mode", () => {
  const html = renderToStaticMarkup(createElement(PreparationProgress, {
    run: {id: "run-a", status: "completed", updatedAt: 100, objectiveBudget: {consumed: 2, maxActionAdmissions: 5, allocationRevision: 1}},
    selection: {slug: "", program: "", addr: "", logicalId: "", locator: ""}, notify: () => {}, compact: true, lastConnectedAt: 105000, now: 125000,
  }));
  expect(html).toContain("current state unknown");
  expect(html).toContain("Last change");
  expect(html).toContain("Last received");
  expect(html).toContain("2 used / 5 allowance");
});

it("static poll preserves records after HTTP and malformed response failures and serializes pending reads", async () => {
  const pollStart = source.indexOf("    const loadPreparations = useCallback(async function () {");
  const pollEnd = source.indexOf("    const loadFuncs", pollStart);
  const pollSource = source.slice(pollStart, pollEnd).replace("const loadPreparations =", "globalThis.load =");
  let runs: unknown = [{id: "previous"}];
  let feed = {receivedAt: 42, error: ""};
  let response: any = {ok: false, status: 503};
  let calls = 0;
  let resolve: ((value: any) => void) | undefined;
  const context: any = {API: {preparations: "/read"}, useCallback: (fn: any) => fn,
    preparationResponse: staticResponse, preparationInFlight: {current: false}, preparationSequence: {current: 0}, AbortSignal,
    fetch: async () => { calls++; return response; },
    setPreparationRuns: (value: any) => {runs = value;},
    setPreparationFeed: (value: any) => {feed = typeof value === "function" ? value(feed) : value;},
  };
  runInNewContext(pollSource, context);
  await context.load();
  expect(runs).toEqual([{id: "previous"}]); expect(feed.receivedAt).toBe(42); expect(feed.error).toContain("503");
  for (const bad of [{}, {ok: false, runs: []}, {runs: [{stages: {}}]}, {runs: [{updatedAt: 1e20}]}]) {
    response = {ok: true, json: async () => bad};
    await context.load(); expect(runs).toEqual([{id: "previous"}]); expect(feed.error).toContain("Invalid");
  }
  response = new Promise(r => {resolve = r;});
  const pending = context.load(); const before = calls;
  await context.load(); expect(calls).toBe(before);
  resolve!({ok: true, json: async () => ({runs: [{id: "new"}]})});
  await pending; expect(runs).toEqual([{id: "new"}]); expect(feed.error).toBe(""); expect(feed.receivedAt).toBeGreaterThan(42);
});

describe.each([["React", preparationResponse], ["static", staticResponse]])("%s response admission", (_, parse) => {
  it("rejects error envelopes and fields that would crash the retained view", () => {
    for (const bad of [null, {ok: false, runs: []}, {runs: [null]}, {runs: [{stages: {}}]}, {runs: [{updatedAt: 1e20}]}, {runs: [{updatedAt: "bad"}]}, {runs: [{reason: {}}]}, {runs: [{events: [{message: {}}]}]}, {runs: [{programs: [4]}]}, {runs: [{retryDecisions: {a: {reason: {}}}}]}, {runs: [{currentJob: {params: {programPath: {}}}}]}, {runs: [{stages: [{workProgress: {total: 1, completed: 1, currentTarget: {}}}]}]}, {runs: [{stages: [{receipt: {}}]}]}]) expect(() => parse(bad)).toThrow();
  });
  it("accepts empty success and sparse durable records without inventing defaults", () => {
    expect(parse({runs: []})).toEqual([]);
    expect(parse({runs: [{id: "old", updatedAt: 0, stages: [], objectiveBudget: null}]})).toEqual([{id: "old", updatedAt: 0, stages: [], objectiveBudget: null}]);
  });
});

const providerBudget = (fields: Record<string, unknown> = {}) => ({
  schema: 1, objectiveId: "objective-a", consumed: 2, maxMcpToolCalls: 5, remaining: 3,
  allocationRevision: 7, priorUsageUnknown: false,
  accountingScope: "mcp-tool-dispatches-since-allocation", ...fields,
});

describe.each([["React", preparationProviderBudgetText], ["static", staticProviderBudget]])("%s MCP allowance", (_, display) => {
  it("shows its own allocation, unlimited and exhausted zero without using admission fields", () => {
    expect(display(providerBudget())).toBe("MCP tool calls: 2 used / 5 allowance · allocation revision 7");
    expect(display(providerBudget({maxMcpToolCalls: null, remaining: null}))).toContain("2 used / unlimited allowance");
    expect(display(providerBudget({consumed: 0, maxMcpToolCalls: 0, remaining: 0}))).toContain("0 used / 0 allowance · allocation revision 7 · allowance exhausted");
    expect(display(providerBudget({consumed: 8}))).toContain("allowance exhausted");
  });
  it("leaves legacy, absent and unsupported accounting evidence unknown", () => {
    for (const value of [undefined, null, [], true, "2", {}, {consumed: 0, maxMcpToolCalls: null}, providerBudget({schema: 2}), providerBudget({accountingScope: {}})]) {
      expect(display(value)).toBe("MCP tool calls: unknown");
    }
  });
  it("does not coerce malformed or unsafe counts", () => {
    for (const value of [undefined, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, "3", true, {}, []]) {
      expect(display(providerBudget({consumed: value, maxMcpToolCalls: value, allocationRevision: value}))).toBe("MCP tool calls: unknown used / unknown allowance · allocation revision unknown");
    }
    expect(display(providerBudget({consumed: Number.MAX_SAFE_INTEGER}))).toContain(String(Number.MAX_SAFE_INTEGER));
  });
  it("retains the lower-bound caveat", () => {
    expect(display(providerBudget({priorUsageUnknown: true}))).toContain("earlier spending unknown; shown usage is a lower bound");
  });
});

const htmSource = readFileSync(new URL("../../static/htm.js", import.meta.url), "utf8");
const htmContext: any = {};
runInNewContext(htmSource, htmContext);
const staticObservation = runInNewContext(source.slice(start, source.indexOf("  function selectPreparationRun(", end)) + "; PreparationObservation;", {html: htmContext.htm.bind(createElement)});
const selection = {slug: "", program: "", addr: "", logicalId: "", locator: ""};
const renderBudget = (surface: string, run: any, feed = {receivedAt: 105000, error: ""}, now = 106000) => renderToStaticMarkup(
  surface === "static" ? createElement(staticObservation, {run, feed, now}) : createElement(PreparationProgress, {
    run, selection, notify: () => {}, compact: surface === "compact React", lastConnectedAt: feed.receivedAt, error: feed.error, now,
  }),
);

describe.each(["React", "compact React", "static"])("%s MCP observation", surface => {
  it("shows independent counts and explains their scope", () => {
    const html = renderBudget(surface, {status: "completed", updatedAt: 100, providerBudget: providerBudget(), objectiveBudget: {consumed: 9, maxActionAdmissions: 10, allocationRevision: 3}});
    expect(html).toContain("MCP tool calls: 2 used / 5 allowance · allocation revision 7");
    expect(html).toContain("Action admissions: 9 used / 10 allowance · allocation revision 3");
    expect(html).toContain("prerequisite, retry and check-in tools/call attempts");
    expect(html).toContain("tokens, money or provider-internal work");
    expect(html).not.toContain("current usage unknown");
  });
  it("renders unknown and malformed budgets without object interpolation", () => {
    for (const budget of [undefined, null, {}, providerBudget({consumed: {}, maxMcpToolCalls: {}, allocationRevision: {}, accountingScope: {}})]) {
      const html = renderBudget(surface, {status: "completed", providerBudget: budget, objectiveBudget: {accountingScope: {}}});
      expect(html).toContain("MCP tool calls: unknown");
    }
  });
  it.each(["disconnected", "resync"])("retains timestamps and caveats for a recently received %s workflow", status => {
    const html = renderBudget(surface, {status, updatedAt: 100, providerBudget: providerBudget({priorUsageUnknown: true})});
    expect(html).toContain("current usage unknown");
    expect(html).toContain("last received observation");
    expect(html).toContain("2 used / 5 allowance");
    expect(html).toContain("shown usage is a lower bound");
    expect(html).toContain("Last received");
    expect(html).toContain("1970-01-01T00:01:40.000Z");
    expect(html).not.toContain(">Connected<");
    expect(html).not.toContain("Preparation feed connected");
  });
  it.each([{receivedAt: 105000, error: "offline"}, {receivedAt: 90000, error: ""}])("retains stale counts when the feed fails or ages", feed => {
    const html = renderBudget(surface, {status: "completed", updatedAt: 100, providerBudget: providerBudget()}, feed);
    expect(html).toContain("current usage unknown");
    expect(html).toContain("2 used / 5 allowance");
    expect(html).toContain("Last received");
  });
});
