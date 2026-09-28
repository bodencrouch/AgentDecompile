# Preparation freshness and admission display — 2026-09-27

This is partial L0.2–L0.5 implementation under the September 22 capability roadmap.
Both static and React preparation views now display action-admission spending, finite
or explicitly unlimited allowance, allocation revision and prior-spending uncertainty.
Missing/malformed values remain unknown. Reserved attempts include rejected or uncertain
dispatches; this allowance is separate from wall-clock policy and recovery acceptance.

Static preparation polling rejects HTTP failures, application-error envelopes and
malformed render-critical records before replacing the last valid snapshot. One request
is outstanding at a time, with a ten-second timeout. It retains observation time and
explicit stale/current-state-unknown feedback. React uses the same response rules,
updates its freshness clock during stalled requests, and retains timestamps in compact
mode. Current-job parameters, work-progress children and stage text fields are checked
before rendering. No mutation or recovery admission was added to feed hydration.

## Evidence

- Twelve focused checks passed in an isolated `/dev/shm/ad-live-projection` stage.
  They execute both static and React budget/response functions, render compact React
  output, and drive static polling through HTTP/application/malformed failures,
  concurrent calls and successful reconnect while checking retained state.
- TypeScript checking passed after correcting test selection typing and one validator
  annotation. Static JavaScript syntax and scoped diff checks passed.
- The final production Vite build passed. It retains existing warnings about chunks
  larger than 500 kB; no performance/browser claim follows from that build.
- Independent review requested changes for error envelopes, malformed nested records
  and misleading accounting wording. All reported cases were corrected and the final
  bounded source review approved.

Deliverable: `/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-live-projection/`.
It contains copied source, `sha256.json`, tests/typecheck/build logs, the review, toolchain
versions and `frontend-assets.tar.gz`. Asset archive SHA-256:
`5e7bbdfac4620fd3666abc11268c5d3f8ef6528d1f05690b3f7f090882311f0d`.

The isolated retained toolchain used React/React DOM 19.2.8, TypeScript 5.9.3,
Vite 6.4.3 and Vitest 3.2.7. The current package manifest asks for Vitest 5; these
checks used the explicitly recorded retained runner, not a fresh lockfile installation.
That initial runner limitation was subsequently closed by the locked verification below.

## Locked dependency verification

A fresh isolated `npm ci --no-audit --no-fund` succeeded using the current manifest
and lockfile, including Vitest 5.0.1. Eighteen checks passed across
`preparationBudget.test.tsx`, `preparationProgress.test.ts` and
`activityDisplay.test.ts`; TypeScript and a fresh Vite production build exited zero.
Source behavior did not change between the reviewed slice and this rerun.

The locked deliverable is
`/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-live-projection-locked/`.
It preserves installation/test/typecheck/build logs, manifest/lockfile, per-file React
asset hashes and a fresh archive. Archive SHA-256:
`035de3286664ee2d55f0e858bfeda94081d3c876a3ad2607e679b3d2998c5dcd`.
These are the assets handed to the next isolated Python-wheel package stage; installed
wheel inclusion requires that stage's separate verification. No serving files changed.

## Remaining scope

No serving assets were replaced and no service was started. This is a prepared asset
bundle, not a new Python wheel or live browser receipt. L0.1 and L0.6 remain open.
Target-switch/browser interaction, actual receipt links and accepted-claim projection,
budget mutation controls, full semantic parity and the remaining M0 mechanisms are
not closed by these tests. The full goal and 110-item acceptance register remain active.
