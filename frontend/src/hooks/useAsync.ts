import { useCallback, useEffect, useRef, useState } from "react";
import { errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";

/** Memuat data, memuat ulang saat deps atau event data backend berubah. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const version = useAppStore((s) => s.dataVersion);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const seq = useRef(0);

  const reload = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const d = await fnRef.current();
      if (mine === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (mine === seq.current) setError(errMsg(e));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void reload(), [reload, version, ...deps]);
  return { data, error, loading, reload };
}
