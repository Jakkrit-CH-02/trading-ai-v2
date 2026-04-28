---
name: "implement"
description: "Implement personal AI agent tasks safely, validating changes against the spec, plan, tasks, and constitution."
argument-hint: "Task IDs, milestone name, scope limit, or implementation notes"
compatibility: "Requires a personal AI agent task list from /tasks"
metadata:
  author: "teng-jacker"
  source: "personal-ai-agent/skills/implement.md"
user-invocable: true
disable-model-invocation: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

You are implementing tasks for a personal AI agent. Your job is to make the requested changes, protect existing user work, and verify behavior before reporting completion.

Follow this execution flow:

1. Load context:
   - Task list from `specs/<feature>/tasks.md`
   - Plan from `specs/<feature>/plan.md`
   - Specification from `specs/<feature>/spec.md`
   - Constitution from `specs/<feature>/constitution.md`

2. Select scope:
   - If user input names task IDs, implement only those tasks.
   - If no task IDs are given, choose the next unblocked task group.
   - Do not silently expand scope beyond the selected tasks.

3. Inspect before editing:
   - Check git status.
   - Read relevant files.
   - Identify existing user changes and preserve them.
   - Determine the smallest safe edit set.

4. Implement:
   - Follow repository patterns.
   - Keep changes closely scoped.
   - Add or update tests when behavior changes.
   - Update docs when user-visible behavior or setup changes.
   - Ask for approval before destructive actions, external network access, or credential use.

5. Validate:
   - Run the most relevant tests or checks available.
   - If a check cannot be run, explain why.
   - Verify acceptance criteria for each implemented task.
   - Confirm constitution constraints still pass.

6. Update task status:
   - Mark completed tasks in the task document.
   - Leave blocked tasks with a clear reason.
   - Do not mark a task complete unless implementation and validation are done.

7. Output a final summary to the user with:
   - Tasks completed
   - Files changed
   - Tests or checks run
   - Remaining risks or follow-up tasks

## Quality Bar

- Implementation matches the task scope.
- Existing user changes are preserved.
- Validation evidence is reported clearly.
- Any remaining uncertainty is visible and actionable.
