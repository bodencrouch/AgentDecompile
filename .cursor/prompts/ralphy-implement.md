# /ralphy-implement (Implement OpenSpec tasks)

Follow [AGENTS](../../AGENTS.md) and [STRATEGY](../../STRATEGY.md). Current recovery
forbids filesystem tests/builds and uses existing 8080; generic development steps
below do not override those restrictions or permit publication.


You are an AI coding assistant implementing an existing OpenSpec change.

## Goal
Implement tasks from `openspec/changes/<change-name>/tasks.md` until acceptance criteria are met with authorized verification.

## Operating mode (Ralph loop compatible)
If you are being run in an iterative loop, you may see the same prompt repeatedly. You MUST:
- Use authorized verification failures as feedback
- Keep making progress on the next incomplete task
- Only claim completion when verification passes

## Steps
1. Identify the active change folder under `openspec/changes/` (ask the user if multiple exist).
2. Read:
   - `openspec/changes/<change-name>/proposal.md`
   - `openspec/changes/<change-name>/tasks.md`
   - Relevant spec deltas in `openspec/changes/<change-name>/specs/`
   - Current specs in `openspec/specs/` as the baseline
3. Implement tasks in order. For each task:
   - Make the smallest correct change
   - Identify the verification required by acceptance criteria
   - Run only authorized checks and fix failures
   - Mark the task as complete in `tasks.md` ONLY when verified

## Completion promise (for Ralph loop runners)
Only output this exact text when ALL tasks are complete AND required authorized verification passes:

<promise>TASK_COMPLETE</promise>
