# Frontend (React + Vite + TS + MUI)

> Read with root `/CLAUDE.md`. This file = frontend-only rules.

## Tech

- React 18, Vite 5, TypeScript `strict: true`
- MUI v5 — styling via `sx` prop **only**. No `styled()`, `css` prop, `makeStyles`, Tailwind, or inline `style={{}}` (except dynamic transforms).
- TanStack Query v5 (server state) + Zustand (ephemeral client state)
- React Router v6
- `axios` — single configured instance in `src/lib/api.ts` (auth header, base URL, error normalization)
- WebSocket: native `WebSocket` wrapped in a hook (`useMarketStream`)
- Forms: `react-hook-form` + `zod`. Schemas mirror Go DTO field names exactly.
- Charts: `lightweight-charts` (candles), `recharts` (everything else)

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
    ├── theme.ts
    ├── lib/
    │   ├── api.ts              # axios + interceptors
    │   ├── queryClient.ts
    │   ├── ws.ts
    │   └── format.ts           # money, %, time
    ├── pages/                  # one folder per requirement screen
    │   ├── dashboard/
    │   ├── market-watch/
    │   ├── bot-control/
    │   ├── trade-logs/
    │   ├── risk-monitor/
    │   ├── backtesting/
    │   ├── ai-training/
    │   ├── paper-trading/
    │   ├── settings/
    │   └── alerts/
    ├── components/             # cross-page reusable
    │   ├── layout/             # AppShell, Sidebar, TopBar
    │   ├── charts/
    │   ├── tables/
    │   └── forms/
    ├── stores/                 # Zustand
    ├── api/                    # one file per backend domain
    │   ├── bot.ts
    │   ├── strategies.ts
    │   ├── trades.ts
    │   ├── backtest.ts
    │   └── ai.ts
    ├── types/
    └── test/
        ├── setup.ts
        └── msw/
```

**Mapping rule:** each `trading_bot_requirements_v2/frontend/NN_*.md` → one folder in `pages/`. Do not split or merge.

## Component rules

- One default export per file. File name = component name in PascalCase.
- Props interface declared above the component, named `<ComponentName>Props`
- No `React.FC`. Use `function ComponentName(props: ComponentNameProps) { ... }`
- Hooks live in `hooks/` next to their page. Cross-page hooks → `src/hooks/`.
- Co-locate small components under the page folder. Promote to `src/components/` when used by 2+ pages.

## Styling rules (`sx` only)

```tsx
// GOOD
<Box sx={{ display: "flex", gap: 2, p: 2, bgcolor: "background.paper" }}>
  <Typography sx={{ color: "text.secondary" }}>Equity</Typography>
</Box>

// BAD
<Box style={{ display: "flex" }}>...</Box>
const Wrapper = styled(Box)`display: flex;`;
<div className="flex gap-2">...</div>
```

- Use theme tokens: `p: 2` not `p: "16px"`; `bgcolor: "background.paper"` not `#1e1e1e`
- Responsive: `sx={{ width: { xs: "100%", md: 320 } }}`
- Long `sx`: extract `const styles = { root: { ... } } as const` at top of file, then `sx={styles.root}`

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
const { data } = useQuery({
  queryKey: ["bot", "status"],
  queryFn: getBotStatus,
  refetchInterval: 2000,
});
```

- All responses parsed through `zod`. Never `as Type`.
- Mutations: `useMutation` with explicit `onSuccess` invalidating relevant `queryKey`
- Errors: rely on global `QueryClient` `defaultOptions.queries.onError` → toast. No try/catch in components.

## WebSocket pattern

- One connection per market stream, multiplexed by symbol/timeframe via subscribe messages
- Lifecycle owned by Zustand store (`marketStreamStore`)
- Reconnect with exponential backoff, max 30s
- All incoming messages parsed through `zod` before dispatch

## State boundaries

- **Server state** → TanStack Query, never copy into Zustand
- **Client state** (UI toggles, selected symbol, drawer open) → Zustand
- **Form state** → `react-hook-form`, never lift into Zustand

## Live trading confirmation

Bot control page must implement 2-step confirmation before switching to live:
1. Modal showing strategy, symbol, max position, max daily loss
2. Type `BTCUSDT` into a confirmation field
3. Submit calls `POST /api/bot/start` with `{ mode: "live", confirmed: true }`

If `confirmed` is missing, backend rejects. Do not bypass on frontend.

## Testing

- `vitest` + `@testing-library/react`
- One test file per page, focusing on user flow
- Mock backend with `msw` (`src/test/msw/`)
- Run: `pnpm test` (watch) / `pnpm test:ci` (single)
- Required for: bot control (live confirmation), risk monitor (threshold display), backtest result (numbers parse)

## Build & run

```bash
pnpm install
pnpm dev          # localhost:5173
pnpm build
pnpm typecheck
pnpm lint
```

## Don'ts

- No direct `fetch` — always go through `api`
- No business logic in components — extract to `hooks/` or `api/`
- No `any` (CI fails on it). Use `unknown` + zod parse.
- No global CSS beyond MUI theme reset
- No image/icon as components — use `@mui/icons-material` or remote URLs
