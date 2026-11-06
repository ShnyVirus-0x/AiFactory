import { create } from "zustand";
import type { Resources } from "../types";

export interface Toast {
  id: number;
  kind: "info" | "success" | "error";
  text: string;
}

interface AppState {
  wsConnected: boolean;
  resources: Resources | null;
  /** Naik setiap ada event data dari backend; halaman memuat ulang datanya saat berubah. */
  dataVersion: number;
  toasts: Toast[];
  setWs: (v: boolean) => void;
  setResources: (r: Resources) => void;
  bump: () => void;
  toast: (kind: Toast["kind"], text: string) => void;
  dismiss: (id: number) => void;
}

let seq = 1;

export const useAppStore = create<AppState>((set, get) => ({
  wsConnected: false,
  resources: null,
  dataVersion: 0,
  toasts: [],
  setWs: (wsConnected) => set({ wsConnected }),
  setResources: (resources) => set({ resources }),
  bump: () => set((s) => ({ dataVersion: s.dataVersion + 1 })),
  toast: (kind, text) => {
    const id = seq++;
    set((s) => ({ toasts: [...s.toasts.slice(-3), { id, kind, text }] }));
    setTimeout(() => get().dismiss(id), kind === "error" ? 8000 : 4000);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
