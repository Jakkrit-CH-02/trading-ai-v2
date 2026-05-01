/**
 * MSW browser bootstrap. Imported lazily from `main.tsx` only when
 * `VITE_ENABLE_MSW=true` so production bundles don't pull msw.
 */
export async function startMockServiceWorker(): Promise<void> {
  if (typeof window === "undefined") return;
  if (import.meta.env.VITE_ENABLE_MSW !== "true") return;

  const { setupWorker } = await import("msw/browser");
  const { handlers } = await import("../test/msw/handlers");

  const worker = setupWorker(...handlers);
  await worker.start({
    onUnhandledRequest: "bypass",
    serviceWorker: { url: "/mockServiceWorker.js" },
  });
}
