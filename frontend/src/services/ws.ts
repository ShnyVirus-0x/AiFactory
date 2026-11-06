export type WsMessage = { type: string; data: Record<string, unknown> };

/** WebSocket dengan reconnect eksponensial. Mengembalikan fungsi untuk menutup koneksi. */
export function connectWs(onMessage: (m: WsMessage) => void, onState: (connected: boolean) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    if (closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      attempt = 0;
      onState(true);
    };
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data as string) as WsMessage);
      } catch {
        /* abaikan pesan rusak */
      }
    };
    ws.onclose = () => {
      onState(false);
      if (closed) return;
      attempt += 1;
      timer = setTimeout(open, Math.min(10000, 500 * 2 ** attempt));
    };
    ws.onerror = () => ws?.close();
  };
  open();
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    ws?.close();
  };
}
