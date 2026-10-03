# Scope note: feel.md is now the static-surface canon

Date: 2026-09-28

Per [`README.md`](../README.md)'s own maintenance rule ("Do not rewrite `feel.md`
to match a later CSS pass. New feel work gets a new dated note."), this is that
new dated note, not an edit to `feel.md` itself.

## What changed

[`feel.md`](./feel.md)'s IDE-plus-flight-deck canon — command palette, action
strip, jobs dock, honest dual bars, Cmd+K, "a finished job is not a match" — was
written before the two frontends diverged. It describes "the workbench" and
`/dashboard` generically, with no distinction between surfaces.

That distinction now exists. Per
[`../../FRONTEND_INTENT.md`](../../FRONTEND_INTENT.md) §2 (2026-09-28 note): the
static 8080 surface follows the Ghidra reversing guide's CodeBrowser arrangement;
the Vite surface is a different, real-time all-in-one workstation built from a
separate browser-RE reference set (FRONTEND_INTENT §7). The two share one backend
with field parity, but they are not one interaction canon anymore.

## Scope of feel.md going forward

`feel.md` still governs the static 8080 surface. Every rule in it — flat power
over menus, honest and calm status, no fabricated progress, Phase A shipped /
Phase B gated — continues to apply there without change.

`feel.md` does not yet describe the Vite AIO workstation's real-time feel. That
companion document does not exist yet. Do not assume `feel.md` already covers it,
and do not extend `feel.md` itself to cover it — start a new file when that work
begins, per the same maintenance rule this note follows.

## Related work

The static-surface implementation spec that follows this scope split is
[`../../dashboard-design/2026-09-28-static-codebrowser-guide-redesign.md`](../../dashboard-design/2026-09-28-static-codebrowser-guide-redesign.md).
Its slice 0 (a gated, reversible layout change behind a "Use classic layout" View
command) follows the same Phase A/Phase B caution this folder's prototypes already
established — see that doc's "Why this is Phase B now" note for the specific
trigger.
