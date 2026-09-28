# Target-local recovery selection — 2026-09-27

This follows the [source-freshness increment](2026-09-26-recovered-source-freshness.md)
and remains partial acceptance work under the active session goal.

Bulk recovery previously gathered source-current logical IDs across all binaries and
used them to suppress sibling work. Its active queue now uses exact target binary ID
and address observations. A donor is still useful reuse evidence, but a shared logical
ID alone cannot stand in for a recipient observation. Legacy helper APIs remain for
compatibility; the active queue no longer uses the cross-binary helper for suppression.

A second existing-file bypass is closed: address-named readable C is checked against
the target-local recorded source digest before it enters already-successful counts.
The actual local file must match; another valid DB file elsewhere does not authenticate
a different local body. Unverified existing C stays eligible under the queue policy.
This is source validation, not a new semantic or whole-image acceptance claim.

Tests exercise current donor versus a different recipient, independent recipient
observations, changed recipient bytes without invalidating the donor, malformed/legacy
records, and a copied body under a recipient-address filename. The combined suite
passed 87 tests in 1.01 seconds against staged source. Tests run actual imported modules
with private SQLite/source fixtures; no bulk compiler or Ghidra workload was launched.
An initial canonical-path pytest invocation failed during test discovery by scanning
an inaccessible parent path; the isolated staged invocation completed successfully.

The source digest still does not bind current original-image bytes or establish
independent semantic identity, ABI equivalence, toolchain closure or linked contribution.
Those remain required work. Existing retry/tried-work policy is not changed by this fix.
No live corpus was modified and no 8080 service was started.

The same 87 tests passed in 0.61 seconds against the installed wheel. PEP 517 build and
isolated install succeeded; the changed module matches canonical source and wheel.
No fresh frontend build or live activation is claimed. This development package
preserves existing working-tree context.

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-target-local/agentdecompile-2.0.1.dev0+autonomy20260927.1-py3-none-any.whl)

SHA-256: `0a516da70e1c11f0a587c71a28d260227de2492ce9663b0e3e8deffd9a7a0354`.

[Package evidence](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-target-local/build-evidence.json).
