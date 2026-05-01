---
description: Start a new vertical slice with explicit scope and acceptance criteria
argument-hint: <slice_title>
---

# Start vertical slice

I am starting work on slice: **$1**

Before you write any code, do the following in this exact order:

1. **Echo back the slice name** so I know we're aligned.

2. **Ask me to provide:**
   - The 3-5 acceptance criteria for this slice (must be checkable, not vague)
   - The list of files that may be touched (paths only)
   - The list of files that are out of scope (you'll refuse to modify them)

3. **Wait for my answer.** Do not proceed.

4. After I answer, **summarize the slice in 5 lines max**:
   - Goal
   - Files in scope
   - Files out of scope
   - Acceptance criteria
   - Any open question

5. Wait for me to say "ok go".

6. Then implement, test, and report — but **only** within the agreed scope.

Constraints across all slices:
- Read the relevant `CLAUDE.md` files (root `CLAUDE.md` + service `apps/<service>/CLAUDE.md`) before writing code
- Read the matching requirement file in `trading_bot_requirements_v2/{frontend,backend-go,ai-python}/` if applicable
- Never modify a file outside the in-scope list without asking first
- Run tests after the change and report the result honestly

If at any point the slice grows beyond 1 commit's worth of work, stop and propose splitting.
