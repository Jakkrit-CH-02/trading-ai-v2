---
name: "plan"
description: "Create an implementation plan for a personal AI agent from an approved specification and constitution."
argument-hint: "Implementation approach, architecture constraints, milestones, stack choices, or risk notes"
compatibility: "Requires a personal AI agent specification from /specify and recommended constitution from /constitution"
metadata:
  author: "teng-jacker"
  source: "personal-ai-agent/skills/plan.md"
user-invocable: true
disable-model-invocation: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

You are creating or updating the implementation plan for a personal AI agent. The plan translates the approved specification into architecture, milestones, risks, and validation strategy.

Follow this execution flow:

1. Load context:
   - Constitution from `specs/<feature>/constitution.md`
   - Specification from `specs/<feature>/spec.md`
   - Existing README, docs, and relevant app structure

2. Run the constitution check:
   - Verify the plan respects agent principles, privacy rules, permission boundaries, and quality gates.
   - If a principle is violated, document the violation and propose a compliant alternative.
   - Do not continue with an implementation approach that conflicts with non-negotiable principles.

3. Define the technical approach:
   - Components and responsibilities
   - Data flow and state management
   - Tool or API integrations
   - Memory strategy, if any
   - Permission and confirmation model
   - Error handling and fallback behavior

4. Define milestones:
   - Split work into small deliverable phases.
   - Each phase MUST produce a verifiable outcome.
   - Mark dependencies between phases.

5. Define validation:
   - Unit, integration, end-to-end, or manual checks as appropriate.
   - Privacy and safety checks.
   - Regression checks for existing behavior.

6. Identify risks:
   - Technical risks
   - Product risks
   - Privacy or security risks
   - Ambiguous requirements that should return to `/clarify`

7. Write or update the plan document:
   - Use `specs/<feature>/plan.md`.
   - If the feature name is not provided, derive it from the existing spec path, user request, or repository context.
   - Create the `specs/<feature>/` directory when it does not exist.
   - Preserve existing decisions unless the spec or constitution requires changes.

8. Output a final summary to the user with:
   - Plan path
   - Recommended architecture
   - Risks and mitigations
   - Suggested next command: `/tasks`

## Quality Bar

- The plan is concrete enough to generate tasks.
- Technical choices are justified by the specification and repository context.
- Privacy, permissions, and failure behavior are planned before implementation.
- Risks are named directly rather than hidden in vague language.
