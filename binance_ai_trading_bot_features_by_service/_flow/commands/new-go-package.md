---
description: Scaffold a new internal Go package mapped to a requirement file
argument-hint: <package_name> <requirement_filename>
---

# New Go internal package

Scaffold `apps/backend/internal/$1/` to implement requirement `trading_bot_requirements_v2/backend-go/$2`.

Read first:
- `CLAUDE.md` (root)
- `apps/backend/CLAUDE.md`
- `trading_bot_requirements_v2/backend-go/$2`
- An existing simple package as style reference: `apps/backend/internal/user/` (handler/service/repository/router pattern)

Create:
1. `apps/backend/internal/$1/types.go`
   - Public types only (structs, sentinel errors)
   - No methods yet

2. `apps/backend/internal/$1/$1.go`
   - The main type (e.g., `type Service struct{...}` or `type Engine struct{...}`)
   - Constructor `New(...)` taking deps explicitly
   - Public methods stubbed with `// TODO: implement` and `panic("not implemented")`

3. `apps/backend/internal/$1/$1_test.go`
   - Table-driven tests for the public methods listed in the requirement's "API / Events Needed"
   - Tests should fail (as expected) — they describe desired behavior

After scaffolding (run from `apps/backend/`):
- Run `go build ./internal/$1` (must compile)
- Run `go test ./internal/$1` (tests should fail with "not implemented")
- Show me the failing test output so I can review the test design before you implement

Do NOT implement the methods yet. Wait for me to confirm the test design.
Do NOT modify other packages.
Do NOT add the new package to `cmd/` mains yet — that's a wiring step in a separate prompt.
