# Browser rewrite contributor

Status: implementation. Date: 2026-09-10.

## Decision

Complete the existing `rewrite` exchange lane with one opt-in worker per
browser tab. The browser receives a portable proposal, sends it directly to a
user-selected LLM provider using a key held only in worker memory, and returns
candidate C to the coordinator. It never performs compilation, objdiff,
identity writes, or a verified-match claim.

This is intentionally a small contributor control in both dashboard shells,
not another dashboard. It must remain inert when the experimental exchange is
not mounted.

## Non-negotiable boundaries

- The key, lease token, prompt, and candidate response are never persisted in
  browser storage, written to coordinator logs, or sent to a coordinator route
  other than the candidate submission.
- Provider traffic is opt-in only after a visible Start action. Stop terminates
  the worker and clears its transient key; a held lease safely expires.
- A browser sends only `rewrite` claims, maintains one lease at a time, and
  retries an identical submission with its original idempotency key.
- Hidden tabs do not poll or claim new work. They complete an in-flight leased
  attempt (including heartbeats) and then wait until visible again.
- Untrusted payload contents are evidence, not instructions. The browser prompt
  repeats the canonical rewrite trust boundary and readable-C constraints.
- UI labels only report proposals/awaiting verification. It must never call a
  proposal a match, win, or verified result.
- The production CSP permits direct connections only to the explicitly
  supported, documented provider origins. There is no coordinator credential
  proxy and no wildcard `connect-src` relaxation.

## Tasks

1. Correct the published exchange API contract and normalize its exchange
   validation errors, so the browser has one predictable error envelope.
2. Add a pure TypeScript exchange protocol module plus a Vite module worker:
   OpenAI-compatible and Anthropic request adapters, bounded retries, lease
   heartbeat, visibility/stop behavior, and proposal-only submission.
3. Add one shared, accessible `Contribute compute` control to both React
   shells. Persist only provider/model preferences. Package the production
   assets and add focused protocol tests.
4. Add the narrow provider CSP allowlist, then verify the built dashboard and
   Vite surfaces against actual exchange handler paths. No external LLM request
   is made during automated verification.

## Acceptance evidence

- Contract route tests cover mandatory fields and error shape.
- Protocol tests cover a 204 claim, fenced C extraction, stable idempotency
  retry, disabled exchange, lease rejection, and no terminal submission for
  provider failure.
- `npm test` and `npm run build` pass in the dashboard frontend.
- The built worker asset is delivered from `/dashboard/static/react/assets/`.
- Browser checks show disabled state, visible opt-in/stop controls, no secrets
  in storage, and no background polling while hidden.

## Ruling

The implementation supports OpenAI and Anthropic direct browser adapters only.
Adding arbitrary provider URLs would require a wildcard CSP or arbitrary
network egress, neither of which is appropriate for a dashboard that handles
binary-derived source evidence. Supporting another provider is a deliberate
future CSP/API review.
