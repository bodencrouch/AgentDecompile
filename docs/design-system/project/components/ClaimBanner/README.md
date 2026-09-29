# ClaimBanner

The claim-status line and worked-example panel that every design diagram carries.

**Consumer provides** the status sentence and, for a worked example, its title and Observe / Contain / Recover / Future proof lines.

- Status lines use `status-claim` amber: "DESIGN ONLY", "NOT RUN", "FUTURE / NOT RUN". They say what the diagram does not claim, in words; amber is never the only carrier.
- The worked panel: `pane`, `line-node`, `radius-contract`, bold title, plain lines, and a closing status line.

**Linking:** none (print diagram). Its nodes keep their pipeline-model ids (`cap-banner`, `challenge-late-worker`, `worked-interruption`, `cap-demo`): where the app renders the same node (Explain, go to `~challenge-late-worker`), that rendering links it to `?node=` with that id, and in docs the name links to the outline anchor (`execution-contracts.outline.md#…`). The print canvas itself carries no links and no live data. "NOT RUN" and "FUTURE / NOT RUN" are never replaced by a link to a result that does not exist.

**Accessibility**

- The status line is text, not a live region. The worked panel is a `section` named by its title.
