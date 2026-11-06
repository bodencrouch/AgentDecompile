# /ralphy-validate (Validate against acceptance criteria)

Follow [AGENTS](../../AGENTS.md) and [STRATEGY](../../STRATEGY.md). Current recovery
forbids filesystem tests/builds and uses existing 8080; generic development steps
below do not override those restrictions or permit publication.


You are an AI coding assistant validating an OpenSpec change against its acceptance criteria.

## Goal
Confirm the implementation satisfies the requirements/scenarios in:
- `openspec/changes/<change-name>/specs/**`
using the verification permitted by the current mission.

## Steps
1. Identify the active change folder under `openspec/changes/`.
2. Extract acceptance criteria from the spec scenarios and `tasks.md` test plan notes.
3. Outside the restricted recovery mission, run the authorized project test command (prefer package scripts), for example:
   - `npm test`
   - `pnpm test`
   - `bun test`
4. If tests fail:
   - Diagnose the failure
   - Fix code/tests
   - Re-run tests
5. Report results:
   - Which requirements are proven (by which tests/commands)
   - Any gaps (missing tests or unclear acceptance criteria)
