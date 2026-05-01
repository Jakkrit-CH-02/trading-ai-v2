# Frontend (React + Vite + TS + MUI)

> Read together with the root `/CLAUDE.md`. This file covers frontend-only rules.

## Tech

- React 18, Vite 5, TypeScript with `"strict": true`
- MUI v5 — styling via the `sx` prop **only**. No `styled()`, no `css` prop, no `makeStyles`, no Tailwind, no inline `style={{}}` except for dynamic transforms.
- TanStack Query v5 for server state. Zustand for ephemeral client state.
- React Router v6.
- `axios` with a single configured instance in `src/lib/api.ts` (auth header, base URL, error normalization).
- WebSocket via native `WebSocket` wrapped in a tiny hook (`useMarketStream`).
- Form: `react-hook-form` + `zod` schemas. Schemas are shared with backend contracts (mirror Go DTO field names exactly).
- Charts: `lightweight-charts` for candles, `recharts` for everything else.

## Folder layout

```
apps/frontend/
├── CLAUDE.md
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── public/
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── routes.tsx
    ├── theme.ts                    # MUI theme — palette, typography, breakpoints
    ├── lib/
    │   ├── api.ts                  # axios instance + interceptors
    │   ├── queryClient.ts          # TanStack Query setup
    │   ├── ws.ts                   # WebSocket helper
    │   └── format.ts               # money, %, time formatters
    ├── pages/                      # one folder per requirement screen
    │   ├── dashboard/
    │   │   ├── DashboardPage.tsx
    │   │   ├── components/
    │   │   └── hooks/
    │   ├── market-watch/
    │   ├── bot-control/
    │   ├── trade-logs/
    │   ├── risk-monitor/
    │   ├── backtesting/
    │   ├── ai-training/
    │   ├── paper-trading/
    │   ├── settings/
    │   └── alerts/
    ├── components/                 # cross-page reusable
    │   ├── layout/                 # AppShell, Sidebar, TopBar
    │   ├── charts/
    │   ├── tables/
    │   └── forms/
    ├── stores/                     # Zustand
    │   ├── botRuntimeStore.ts
    │   └── uiStore.ts
    ├── api/                        # one file per backend domain
    │   ├── bot.ts                  # GET/POST /api/bot/*
    │   ├── strategies.ts
    │   ├── trades.ts
    │   ├── backtest.ts
    │   └── ai.ts
    ├── types/                      # shared TS types (mirror backend DTOs)
    └── test/
        ├── setup.ts                # vitest setup
        └── msw/                    # mock backend handlers
```

**Mapping rule:** each file in `../trading_bot_requirements_v2/frontend/NN_*.md` maps to exactly one folder in `pages/`. Do not split a requirement across pages or merge two requirements into one page.

## Component rules

- One default export per file. File name = component name in PascalCase.
- Props interface declared above the component, named `<ComponentName>Props`.
- No `React.FC`. Use `function ComponentName(props: ComponentNameProps) { ... }`.
- Hooks live in `hooks/` next to their page. Cross-page hooks live in `src/hooks/`.
- Co-locate small components under the page folder. Promote to `src/components/` only when used by 2+ pages.

## Styling rules (`sx` only)

```tsx
// GOOD
<Box sx={{ display: "flex", gap: 2, p: 2, bgcolor: "background.paper" }}>
  <Typography sx={{ color: "text.secondary" }}>Equity</Typography>
</Box>

// BAD — do not do any of these
<Box style={{ display: "flex" }}>...</Box>
const Wrapper = styled(Box)`display: flex;`;
<div className="flex gap-2">...</div>
```

- Use theme tokens: `p: 2` not `p: "16px"`; `bgcolor: "background.paper"` not `bgcolor: "#1e1e1e"`.
- Responsive values: `sx={{ width: { xs: "100%", md: 320 } }}`.
- Long `sx` objects: extract into a `const styles = { root: { ... } } as const` at the top of the file, then `sx={styles.root}`.

## API call pattern

```ts
// src/api/bot.ts
import { api } from "@/lib/api";
import { z } from "zod";

export const BotStatusSchema = z.object({
  mode: z.enum(["backtest", "paper", "live"]),
  state: z.enum(["idle", "running", "paused", "halted"]),
  symbol: z.string(),
  startedAt: z.number().int().nullable(),
});
export type BotStatus = z.infer<typeof BotStatusSchema>;

export async function getBotStatus(): Promise<BotStatus> {
  const { data } = await api.get("/api/bot/status");
  return BotStatusSchema.parse(data);
}
```

```ts
// in a page
const { data, isLoading } = useQuery({
  queryKey: ["bot", "status"],
  queryFn: getBotStatus,
  refetchInterval: 2000,
});
```

- All responses parsed through `zod`. Never `as Type`.
- Mutations: `useMutation` with explicit `onSuccess` invalidating the relevant `queryKey`.
- Errors: rely on a global `QueryClient` `defaultOptions.queries.onError` that pushes to a toast. Do not write try/catch in components.

## WebSocket pattern

- One connection per market stream, multiplexed by symbol/timeframe through subscribe messages
- Connection lifecycle owned by a Zustand store (`marketStreamStore`)
- Reconnect with exponential backoff, max 30s
- All incoming messages parsed through `zod` before dispatch

## State boundaries

- **Server state** (anything from backend) — TanStack Query, never copy into Zustand
- **Client state** (UI toggles, selected symbol, drawer open) — Zustand
- **Form state** — `react-hook-form`, never lift into Zustand

## Live trading confirmation

The bot control page must implement a 2-step confirmation before switching to live mode:
1. Modal showing the strategy, symbol, max position, max daily loss
2. Type the symbol (`BTCUSDT`) into a confirmation field
3. Submit calls `POST /api/bot/start` with `{ mode: "live", confirmed: true }`

If `confirmed` is missing, backend rejects the request — do not bypass on the frontend.

## Testing

- `vitest` + `@testing-library/react`
- One test file per page focusing on user flow, not implementation details
- Mock backend with `msw` (handlers in `src/test/msw/`)
- Run: `pnpm test` (watch) / `pnpm test:ci` (single)
- Required for: bot control (live confirmation), risk monitor (threshold display), backtest result (numbers parse correctly)

## Build & run

```bash
pnpm install
pnpm dev          # localhost:5173
pnpm build
pnpm typecheck
pnpm lint
```

## Don'ts (frontend-specific)

- No direct `fetch` — always go through `api`
- No business logic in components — extract to `hooks/` or `api/`
- No `any` (CI fails on it). Use `unknown` + zod parse.
- No global CSS file beyond MUI theme reset
- No image/icon assets imported as components — use `@mui/icons-material` or remote URLs
