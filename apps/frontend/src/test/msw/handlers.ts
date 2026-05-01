import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("*/api/health", () =>
    HttpResponse.json({ status: "ok", service: "frontend-mock" }),
  ),
  // TODO: remove once backend ships /api/dashboard/summary
  http.get("*/api/dashboard/summary", () =>
    HttpResponse.json({
      data: {
        bot_state: "idle",
        equity: null,
        pnl_today: null,
        open_positions: [],
      },
      error: null,
    }),
  ),
];
