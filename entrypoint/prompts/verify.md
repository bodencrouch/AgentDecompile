Read `entrypoint/AGENT_BOOTSTRAP.md` section 8 and `entrypoint/COORDINATOR.md` section 3.

Re-check the claim `<claim>` about `<function, match or export>`.

Run the validation gate by hand: list the checks the claim kind requires, run each one you
can through the existing catalog, and record PASS, FAIL or UNKNOWN with the exact
conditions of any proof (toolchain, flags, objdiff settings, tool versions, inputs by hash).

Then state the highest claim tier the evidence supports. If it is lower than the claim as
currently recorded, say so, name the receipt that would raise it, and do not edit the
record to match the stronger wording. UNKNOWN never rounds up to PASS.
