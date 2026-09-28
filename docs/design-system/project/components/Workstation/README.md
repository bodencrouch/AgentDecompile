# Workstation

The whole shell composed from the system: header with the one workflow control, session tabs, workspace tabs, navigator with the single Functions list, the listing, the evidence rail, the activity dock and the status line.

**Use it** as the reference composition for both surfaces (static 8080 workbench and the optional full workspace). They may differ in richness but not in regions, selection or semantics.

**Consumer provides** the active project and related-build scope, the selected logical entity and concrete build/address, the function working set, evidence for the selection, and live activity.

- Regions follow the Layout section: navigator `navigator-w`, evidence `evidence-w`, dock `dock-h`, 1px `splitter-rule` between them.
- Listing and Decompile own the center. There is exactly one Functions surface.
- Below 700px only one primary pane shows at a time; a rail bar switches Navigate, Analyze, Inspect and Activity.
- The preview uses generic sample data; never ship product or binary names in defaults.
