---
name: "clarify"
description: "Resolve ambiguous or missing requirements for a personal AI agent before planning or implementation."
argument-hint: "Ambiguous requirements, open questions, decisions needed, or user preferences"
compatibility: "Requires a personal AI agent spec or plan with open questions"
metadata:
  author: "teng-jacker"
  source: "personal-ai-agent/skills/clarify.md"
user-invocable: true
disable-model-invocation: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

You are clarifying requirements for a personal AI agent. Your job is to reduce ambiguity only where it affects correct behavior, safety, privacy, or implementation choices.

Follow this execution flow:

1. Load current context:
   - Specification from `specs/<feature>/spec.md`
   - Plan from `specs/<feature>/plan.md` if present
   - Constitution from `specs/<feature>/constitution.md` if present

2. Identify ambiguity:
   - Missing user goals
   - Undefined agent boundaries
   - Unclear permissions
   - Unknown integrations
   - Conflicting requirements
   - Acceptance criteria that cannot be verified

3. Prioritize questions:
   - Ask only questions that change implementation or acceptance criteria.
   - Group related questions.
   - Mark each question as blocking or non-blocking.
   - Prefer concise questions with concrete options when possible.

4. Apply available answers:
   - If user input answers an open question, update the spec or plan.
   - If repository context answers a question, use that context and cite the file path.
   - If an answer is still unknown but non-blocking, document the assumption.

5. Write updates:
   - Update the source document containing the ambiguity.
   - Add a "Clarifications" section if one does not exist.
   - Record date, question, answer, and affected requirement or task.

6. Output a final summary to the user with:
   - Questions resolved
   - Questions still blocking
   - Assumptions made
   - Suggested next command: `/specify`, `/plan`, or `/tasks`

## Quality Bar

- Clarification does not become brainstorming unless the user asks for brainstorming.
- Each question has a clear reason for existing.
- Assumptions are visible and easy to revise.
- Updated documents remain internally consistent.
