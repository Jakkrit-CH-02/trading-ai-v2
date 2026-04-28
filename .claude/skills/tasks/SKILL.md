---
name: "tasks"
description: "Generate an actionable task list for implementing a personal AI agent from the approved spec and plan."
argument-hint: "Task grouping preferences, milestone scope, priority, or implementation constraints"
compatibility: "Requires an approved personal AI agent spec and implementation plan"
metadata:
  author: "teng-jacker"
  source: "personal-ai-agent/skills/tasks.md"
user-invocable: true
disable-model-invocation: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

You are creating or updating the task list for a personal AI agent. The task list must be executable, ordered, and traceable back to the specification and plan.

Follow this execution flow:

1. Load context:
   - Specification from `specs/<feature>/spec.md`
   - Plan from `specs/<feature>/plan.md`
   - Constitution from `specs/<feature>/constitution.md`

2. Validate readiness:
   - Confirm there are no blocking clarification questions.
   - Confirm the plan has enough architecture detail to produce tasks.
   - If readiness fails, stop and recommend `/clarify` or `/plan`.

3. Generate tasks:
   - Use a checklist format with stable task IDs.
   - Group by milestone or implementation phase.
   - Keep tasks independently verifiable when possible.
   - Include file or module ownership when known.
   - Include tests and documentation tasks where required.

4. Task structure:
   - ID, title, priority, dependencies, and acceptance check.
   - Reference the requirement or user story each task supports.
   - Mark tasks that may run in parallel.
   - Mark tasks requiring user approval, credentials, or external services.

5. Include validation tasks:
   - Functional checks
   - Privacy and permission checks
   - Error and fallback checks
   - Regression checks
   - Documentation review

6. Write or update the tasks document:
   - Use `specs/<feature>/tasks.md`.
   - If the feature name is not provided, derive it from the existing spec or plan path, user request, or repository context.
   - Create the `specs/<feature>/` directory when it does not exist.
   - Preserve completed tasks and update only what changed.

7. Output a final summary to the user with:
   - Tasks path
   - Number of tasks by phase
   - Parallel work opportunities
   - Suggested next command: `/implement`

## Quality Bar

- Tasks are small enough to execute without reinterpreting the plan.
- Every P1 requirement has at least one implementation task and one validation task.
- Dependencies are explicit.
- No task requires hidden context.
