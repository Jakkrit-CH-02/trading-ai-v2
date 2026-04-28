---
name: "specify"
description: "Create or update a personal AI agent specification from goals, context, user stories, requirements, constraints, integrations, and acceptance criteria."
argument-hint: "Agent goal, target users, workflows, constraints, integrations, or success criteria"
compatibility: "Requires a personal AI agent workspace with output under specs/<feature>/"
metadata:
  author: "teng-jacker"
  source: "personal-ai-agent/skills/specify.md"
user-invocable: true
disable-model-invocation: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

You are creating or updating the specification for a personal AI agent. The specification defines what the agent is for, how it behaves, what outcomes it supports, and what must be true before planning or implementation begins.

Follow this execution flow:

1. Load upstream context:
   - Constitution from `specs/<feature>/constitution.md` if present.
   - Existing specification from `specs/<feature>/spec.md` if present.
   - README, docs, and relevant repository context.

2. Identify the agent purpose:
   - Primary mission.
   - Target user or owner.
   - Core problems the agent solves.
   - Non-goals.
   - Situations where the agent should refuse, pause, or ask for permission.

3. Capture user stories and workflows:
   - Write stories in the form: "As a [user], I want [capability], so that [outcome]."
   - Prioritize stories as P1, P2, or P3.
   - Include the happy path, edge cases, and recovery behavior.

4. Define functional requirements:
   - Use testable requirement statements.
   - Use MUST for required behavior and SHOULD for preferred behavior.
   - Include inputs, outputs, tools, integrations, state, memory, and permissions.

5. Define non-functional requirements:
   - Privacy and data handling.
   - Reliability and fallback behavior.
   - Latency or responsiveness expectations.
   - Tone, personality, and interaction style.
   - Observability, logs, or audit trail if relevant.

6. Define acceptance criteria:
   - Each P1 story MUST have clear acceptance criteria.
   - Criteria MUST be objectively verifiable.
   - Include examples of successful and unsuccessful behavior.

7. Identify open questions:
   - List only questions that block a correct implementation.
   - Avoid asking questions that can be answered from repository context.
   - Mark each question as blocking or non-blocking.

8. Write or update the specification document:
   - Use `specs/<feature>/spec.md`.
   - If the feature name is not provided, derive a concise kebab-case feature name from the user's request or repository context.
   - Create the `specs/<feature>/` directory when it does not exist.
   - Preserve existing useful content and update it in place.

9. Output a final summary to the user with:
   - Spec path.
   - Main capabilities captured.
   - Blocking questions, if any.
   - Suggested next command: `/plan` if no blocking questions remain.

## Quality Bar

- Requirements are specific, testable, and implementation-neutral.
- The specification describes user-visible behavior before internal design.
- No major behavior depends on unstated assumptions.
- Privacy and permission boundaries are explicit.
