import { useEffect } from "react";
import { useMarketStreamStore } from "../stores/marketStreamStore";

const WS_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined ?? "http://localhost:8080")
    .replace(/^http/, "ws");

/**
 * Connects the market WebSocket stream for the given symbols.
 * Disconnects cleanly when the component unmounts or symbols change.
 */
export function useMarketStream(symbols: string[]) {
  const connect = useMarketStreamStore((s) => s.connect);
  const disconnect = useMarketStreamStore((s) => s.disconnect);

  useEffect(() => {
    if (symbols.length === 0) return;
    connect(symbols, WS_BASE);
    return () => disconnect();
  }, [symbols.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
}
