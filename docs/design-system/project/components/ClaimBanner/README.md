# ClaimBanner

The claim-status line and worked-example panel that every design diagram carries.

**Consumer provides** the status sentence and, for a worked example, its title and Observe / Contain / Recover / Future proof lines.

- Status lines use `status-claim` amber: "DESIGN ONLY", "NOT RUN", "FUTURE / NOT RUN". They say what the diagram does not claim, in words; amber is never the only carrier.
- The worked panel: `pane`, `line-node`, `radius-contract`, bold title, plain lines, and a closing status line.

**Linking**

- **Publishes:** nothing. Diagram-only.
- **Follows:** nothing; the content is `pipeline-model.json`.
- **Targets rendered:** in app renderings the worked panel's title links to its pipeline node (`?node=challenge-late-worker`, `worked-interruption`, `cap-demo`) and the banner to `?node=cap-banner`; contract words it names (fence, quarantine) link to `?node=fence` and `?node=quarantine`. In docs the same names link to the outline anchors (`execution-contracts.outline.md#challenge-late-worker`).
- **Absent copy:** the banner itself is the absent copy for unrun checks: "NOT RUN" and "FUTURE / NOT RUN" are never replaced by a link to a result that does not exist.

**Accessibility**

- The status line is text, not a live region. The worked panel is a `section` named by its title.
