import { useEffect } from "react";
import { api } from "../services/api";
import { connectWs } from "../services/ws";
import { useAppStore } from "../stores/useAppStore";
import type { Resources } from "../types";

/** Menghubungkan WebSocket ke store: statistik sistem nyata + sinyal perubahan data. */
export function useLiveEvents(): void {
  useEffect(() => {
    const { setWs, setResources, bump } = useAppStore.getState();
    void api.resources().then(setResources).catch(() => undefined);
    return connectWs(
      (m) => {
        if (m.type === "system.stats") setResources(m.data as unknown as Resources);
        else if (m.type !== "hello") bump();
      },
      (c) => {
        setWs(c);
        if (c) bump(); // sinkronkan ulang setelah (re)connect
      },
    );
  }, []);
}
