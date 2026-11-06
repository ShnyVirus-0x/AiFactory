import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge, ErrorBox, fmtBytes, Meter, PageHeader, Spinner } from "../components/ui";
import type { Limits } from "../types";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";

export function SettingsPage() {
  const toast = useAppStore((s) => s.toast);
  const res = useAppStore((s) => s.resources);
  const health = useAsync(api.health);
  const gpu = useAsync(() => api.gpu(false));
  const [testing, setTesting] = useState(false);
  const lim = useAsync(api.limits);
  const [draft, setDraft] = useState<Limits | null>(null);
  const limits = draft ?? lim.data;

  async function saveLimits() {
    if (!draft) return;
    try {
      await api.setLimits(draft);
      toast("success", "Batas sumber daya disimpan");
      setDraft(null);
      void lim.reload();
      void health.reload();
    } catch (e) {
      toast("error", errMsg(e));
    }
  }
  async function unload(key?: string) {
    try {
      if (key) await api.unloadModel(key);
      else await api.unloadAll();
      toast("success", "Model dilepas dari memori");
      void health.reload();
    } catch (e) {
      toast("error", errMsg(e));
    }
  }

  async function retestNvenc() {
    setTesting(true);
    try {
      const g = await api.gpu(true);
      toast(g.nvenc.available ? "success" : "error", g.nvenc.available ? "NVENC berfungsi (uji encode berhasil)" : `NVENC tidak tersedia: ${g.nvenc.reason}`);
      void gpu.reload();
      void health.reload();
    } catch (e) {
      toast("error", errMsg(e));
    } finally {
      setTesting(false);
    }
  }

  if (health.loading) return <Spinner label="Menjalankan diagnostik…" />;
  if (health.error || !health.data) return <ErrorBox message={health.error ?? "Gagal memuat"} onRetry={health.reload} />;
  const h = health.data;
  const g = gpu.data;
  return (
    <>
      <PageHeader title="Pengaturan & Diagnostik" subtitle={`Versi ${h.version} · Python ${h.python} · ${h.platform}`}
        actions={<button className="btn btn-ghost" onClick={() => { void health.reload(); void gpu.reload(); }}><RefreshCw size={16} />Muat ulang</button>} />
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card">
          <h2 className="mb-3 text-sm font-semibold">Pemeriksaan komponen</h2>
          <ul className="space-y-2 text-sm">
            {h.checks.map((c) => (
              <li key={c.key} className="flex items-start gap-2">
                {c.ok ? <CheckCircle2 size={16} className="mt-0.5 text-ok" /> : <XCircle size={16} className={`mt-0.5 ${c.required ? "text-bad" : "text-warn"}`} />}
                <div className="min-w-0 flex-1"><div className="font-medium">{c.label} {c.required && <Badge>wajib</Badge>}</div><div className="break-words text-xs text-mute">{c.detail}</div></div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">GPU &amp; encoder</h2>
            <button className="btn btn-ghost" onClick={() => void retestNvenc()} disabled={testing}>{testing ? "Menguji…" : "Uji ulang NVENC"}</button>
          </div>
          {!g ? <Spinner /> : g.available ? (
            <div className="space-y-3 text-sm">
              {g.gpus.map((x) => (
                <div key={x.index} className="space-y-2">
                  <div className="font-medium">{x.name} <span className="text-xs text-mute">· driver {x.driver_version}{g.cuda_version ? ` · CUDA ${g.cuda_version}` : ""}</span></div>
                  <Meter label="VRAM" value={(x.vram_used_mb / x.vram_total_mb) * 100} detail={`${x.vram_used_mb} / ${x.vram_total_mb} MB (bebas ${x.vram_free_mb} MB)`} />
                  <Meter label="Beban GPU" value={x.utilization_percent} />
                  <div className="text-xs text-mute">Suhu: {x.temperature_c ?? "tidak tersedia"}°C · Daya: {x.power_w !== null ? `${x.power_w} W` : "tidak tersedia"}</div>
                </div>
              ))}
            </div>
          ) : <div className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-xs text-warn"><b>GPU NVIDIA tidak terdeteksi.</b> {g.reason}</div>}
          <div className="mt-3 flex items-center gap-2 text-sm">
            <span className="text-mute">NVENC:</span>
            {h.nvenc.available ? <Badge kind="ok">tersedia (H.264{h.nvenc.hevc ? " + H.265" : ""})</Badge> : <Badge kind="warn">tidak tersedia — render memakai CPU</Badge>}
          </div>
          {!h.nvenc.available && h.nvenc.reason && <p className="mt-1 text-xs text-mute">{h.nvenc.reason}</p>}
        </section>

        <section className="card">
          <h2 className="mb-3 text-sm font-semibold">Sumber daya sistem</h2>
          {res ? (
            <div className="space-y-3">
              <Meter label={`CPU — ${res.cpu.name}`} value={res.cpu.percent} detail={`${res.cpu.cores_physical ?? "?"} core / ${res.cpu.cores_logical ?? "?"} thread`} />
              <Meter label="RAM" value={res.ram.percent} detail={`${fmtBytes(res.ram.used)} / ${fmtBytes(res.ram.total)}`} />
              {res.disk && <Meter label="Penyimpanan (storage/)" value={res.disk.percent} detail={`${fmtBytes(res.disk.free)} tersedia`} warnAt={85} badAt={95} />}
              <div className="text-xs text-mute">{res.os}</div>
            </div>
          ) : <Spinner />}
        </section>

        <section className="card">
          <h2 className="mb-3 text-sm font-semibold">Batas sumber daya</h2>
          {limits ? (
            <div className="space-y-3 text-sm">
              <label className="block text-xs text-mute">Mode pemrosesan AI
                <select className="input mt-1" value={limits.compute_mode} onChange={(e) => setDraft({ ...limits, compute_mode: e.target.value as Limits["compute_mode"] })}>
                  <option value="auto">Otomatis (GPU bila tersedia, jika tidak CPU)</option>
                  <option value="gpu">Paksa GPU (gagal bila CUDA tidak tersedia)</option>
                  <option value="cpu">Paksa CPU</option>
                </select></label>
              {lim.data && <div className="text-xs text-mute">Perangkat efektif saat ini: <b className="text-ink">{lim.data.effective_device}</b>{lim.data.device_reason ? ` — ${lim.data.device_reason}` : ""}</div>}
              <div className="grid grid-cols-2 gap-3">
                {([["ai_workers", "Worker AI", 1, 4], ["gpu_render_workers", "Worker render GPU", 1, 4], ["cpu_workers", "Worker CPU", 1, 16], ["vram_reserve_mb", "Cadangan VRAM (MB)", 0, 24576]] as const).map(([k, label, lo, hi]) => (
                  <label key={k} className="text-xs text-mute">{label}
                    <input className="input mt-1" type="number" min={lo} max={hi} value={limits[k]} onChange={(e) => setDraft({ ...limits, [k]: Number(e.target.value) })} /></label>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <button className="btn btn-primary" disabled={!draft} onClick={() => void saveLimits()}>Simpan</button>
                {draft && <button className="btn btn-ghost" onClick={() => setDraft(null)}>Batal</button>}
                <span className="ml-auto text-xs text-mute">Batas unggah: {fmtBytes(h.limits.max_upload_mb * 1024 * 1024)}</span>
              </div>
            </div>
          ) : <Spinner />}
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-line pt-3 text-sm">
            <dt className="text-mute">Alamat server</dt><dd className="font-mono text-xs">{h.bind}</dd>
            <dt className="text-mute">Penyimpanan</dt><dd className="break-all font-mono text-xs">{h.storage_dir}</dd>
            <dt className="text-mute">Folder model</dt><dd className="break-all font-mono text-xs">{h.models_dir}</dd>
          </dl>
        </section>

        <section className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Model AI di memori &amp; CUDA</h2>
            <button className="btn btn-ghost" disabled={!h.models_loaded.length} onClick={() => void unload()}>Lepas semua</button>
          </div>
          {h.models_loaded.length === 0 ? <p className="text-sm text-mute">Tidak ada model yang sedang dimuat.</p> : (
            <ul className="space-y-2 text-sm">
              {h.models_loaded.map((m) => (
                <li key={m.key} className="flex items-center justify-between rounded-lg bg-panel-2 px-3 py-2">
                  <span>{m.key} <Badge kind={m.device === "cuda" ? "ok" : "mute"}>{m.device}</Badge>{m.device === "cuda" && <span className="ml-2 text-xs text-mute">±{m.est_vram_mb} MB VRAM</span>}</span>
                  <button className="text-xs text-bad hover:underline" onClick={() => void unload(m.key)}>Lepas</button>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 space-y-1 border-t border-line pt-3 text-xs">
            <div className="flex items-center gap-2 text-sm"><span className="text-mute">Kompatibilitas CUDA (faster-whisper):</span>
              {h.cuda.ok ? <Badge kind="ok">kompatibel</Badge> : <Badge kind="warn">belum terbukti</Badge>}</div>
            <div className="text-mute">Dibutuhkan: {h.cuda.required}</div>
            <div className="text-mute">Driver CUDA: {h.cuda.driver_cuda ?? "tidak terdeteksi"} · GPU terlihat oleh CTranslate2: {h.cuda.ctranslate2_cuda_devices ?? "tidak diketahui"}</div>
            {h.cuda.reason && <div className="text-warn">{h.cuda.reason}</div>}
          </div>
        </section>

        <section className="card lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold">Status modul</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {h.capabilities.map((c) => (
              <div key={c.key} className="flex items-center justify-between rounded-lg bg-panel-2 px-3 py-2 text-sm">
                <span>{c.label}</span>
                {c.available ? <Badge kind="ok">tersedia</Badge> : <Badge kind="warn">belum tersedia · Fase {c.phase}</Badge>}
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
