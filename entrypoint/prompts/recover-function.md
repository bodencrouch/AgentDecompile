Read `entrypoint/AGENT_BOOTSTRAP.md` and `entrypoint/RECOVERY_LOOP.md` section 6.

Recover `<function name or address>` on build `<build id>` through the existing catalog.

Target: readable C, named per the project conventions, that compiles under the identified
toolchain and passes objdiff with zero differences against the original bytes.

Order of attempts: verified sibling source via identity, re-proven here; compiler and
profile variation; mechanical transforms and known idioms; structural correction from the
diff shape; only then a bounded model-assisted rewrite as a challenger lane. Compile after
every change and keep the exact compiler output and objdiff mismatch class for each attempt.

If zero differences is not reached, stop at the budget and deliver:

- the best compiling candidate labeled readable/compiling, or the attempt receipts if
  nothing compiled, and
- a clearly labeled `.S` floor that preserves the machine code and calling boundary and
  stays replaceable by C.

Do not infer C++ from a C-level match. Never count the floor as recovered source.
