import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { useAppStore } from "../stores/useAppStore";

export const fmtBytes = (n: number): string => {
  if (n < 1024) return `${n} B`;
  const u = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${u[i]}`;
};

export const fmtDur = (s: number): string => {
  const t = Math.round(s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
};

export const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-mute">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </div>
  );
}

export function Badge({ kind = "mute", children }: { kind?: "ok" | "warn" | "bad" | "brand" | "mute"; children: ReactNode }) {
  const cls = { ok: "bg-ok/15 text-ok", warn: "bg-warn/15 text-warn", bad: "bg-bad/15 text-bad", brand: "bg-brand/20 text-brand-2", mute: "bg-panel-2 text-mute" }[kind];
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
}

export function Meter({ value, label, detail, warnAt = 75, badAt = 90 }: { value: number | null; label: string; detail?: string; warnAt?: number; badAt?: number }) {
  const v = value === null ? 0 : Math.max(0, Math.min(100, value));
  const color = value === null ? "bg-line" : v >= badAt ? "bg-bad" : v >= warnAt ? "bg-warn" : "bg-brand";
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-mute">{label}</span>
        <span className="font-medium tabular-nums">{value === null ? "tidak tersedia" : `${v.toFixed(0)}%`}{detail ? <span className="ml-2 text-mute">{detail}</span> : null}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-panel-2" role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

export function Spinner({ label = "Memuat…" }: { label?: string }) {
  return <div className="flex items-center gap-2 py-6 text-sm text-mute"><span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />{label}</div>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-bad/40 bg-bad/10 p-3 text-sm text-bad" role="alert">
      <span className="flex items-center gap-2"><AlertTriangle size={16} />{message}</span>
      {onRetry && <button className="btn btn-ghost" onClick={onRetry}>Coba lagi</button>}
    </div>
  );
}

export function Empty({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line py-10 text-center text-mute">
      {icon}
      <div className="text-sm font-medium text-ink">{title}</div>
      {hint && <div className="max-w-md text-xs">{hint}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()} role="dialog" aria-modal="true" aria-label={title}>
      <div className={`card max-h-[90vh] w-full overflow-auto ${wide ? "max-w-4xl" : "max-w-md"}`}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">{title}</h2>
          <button className="text-mute hover:text-ink" onClick={onClose} aria-label="Tutup"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Confirm({ title, message, confirmLabel = "Hapus", onConfirm, onCancel }: { title: string; message: string; confirmLabel?: string; onConfirm: () => void; onCancel: () => void }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="mb-4 text-sm text-mute">{message}</p>
      <div className="flex justify-end gap-2">
        <button className="btn btn-ghost" onClick={onCancel}>Batal</button>
        <button className="btn btn-danger" onClick={onConfirm} autoFocus>{confirmLabel}</button>
      </div>
    </Modal>
  );
}

export function Toasts() {
  const toasts = useAppStore((s) => s.toasts);
  const dismiss = useAppStore((s) => s.dismiss);
  return (
    <div className="fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2" aria-live="polite">
      {toasts.map((t) => {
        const Icon = t.kind === "success" ? CheckCircle2 : t.kind === "error" ? AlertTriangle : Info;
        const color = t.kind === "success" ? "border-ok/40 text-ok" : t.kind === "error" ? "border-bad/40 text-bad" : "border-brand/40 text-brand-2";
        return (
          <div key={t.id} className={`card flex items-start gap-2 border ${color} text-sm`}>
            <Icon size={16} className="mt-0.5 shrink-0" />
            <span className="flex-1 text-ink">{t.text}</span>
            <button onClick={() => dismiss(t.id)} aria-label="Tutup"><X size={14} /></button>
          </div>
        );
      })}
    </div>
  );
}
