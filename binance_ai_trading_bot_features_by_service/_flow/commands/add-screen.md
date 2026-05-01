---
description: Scaffold a new frontend screen mapped to a requirement file
argument-hint: <screen_slug> <requirement_filename>
---

# Add a new frontend screen

Add a new screen `$1` to the frontend, implementing the requirement from `trading_bot_requirements_v2/frontend/$2`.

Read first:
- `CLAUDE.md` (root)
- `apps/frontend/CLAUDE.md`
- `trading_bot_requirements_v2/frontend/$2`
- `apps/frontend/src/App.tsx` and `apps/frontend/src/lib/api.ts`
- An existing page under `apps/frontend/src/pages/` if one exists (use as reference for layout + hooks)

Create:
1. `apps/frontend/src/pages/$1/`
   - `${PascalCase($1)}Page.tsx` — top-level page component, default export
   - `components/` — page-specific components (only if needed)
   - `hooks/use${PascalCase($1)}.ts` — TanStack Query hooks
   - `index.ts` — re-export the page

2. `apps/frontend/src/api/$1.ts` (only if requirement lists API endpoints not already covered)
   - Zod schema per response
   - One async function per endpoint

3. Add route to `apps/frontend/src/routes.tsx` and a sidebar link in `apps/frontend/src/components/layout/Sidebar.tsx`

Constraints:
- Styling: `sx` prop only — no `styled`, no `style={{}}`, no Tailwind
- Server state via TanStack Query, never copied into Zustand
- Zod-validate every API response (use `.parse()` not `as Type`)
- Forms: `react-hook-form` + zod resolver

After scaffolding:
- Run `pnpm typecheck`
- Run `pnpm lint`
- Show me the diff summary, not the full file contents

Do NOT modify backend routes, theme, or other pages.
