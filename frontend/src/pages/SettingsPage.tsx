import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge, ErrorBox, fmtBytes, Meter, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";

export function SettingsPage() {
  const toast = useAppStore((s) => s.toast);
  const res = useAppStore((s) => s.resources);
  const health = useAsync(api.health);
  const gpu = useAsync(() => api.gpu(false));
  const [testing, setTesting] = useState(false);

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
          <h2 className="mb-3 text-sm font-semibold">Batas sumber daya &amp; lokasi</h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-mute">AI worker</dt><dd>{h.limits.ai_workers}</dd>
            <dt className="text-mute">GPU render worker</dt><dd>{h.limits.gpu_render_workers}</dd>
            <dt className="text-mute">CPU utility worker</dt><dd>{h.limits.cpu_workers}</dd>
            <dt className="text-mute">Cadangan VRAM</dt><dd>{h.limits.vram_reserve_mb} MB</dd>
            <dt className="text-mute">Batas unggah</dt><dd>{fmtBytes(h.limits.max_upload_mb * 1024 * 1024)}</dd>
            <dt className="text-mute">Alamat server</dt><dd className="font-mono text-xs">{h.bind}</dd>
            <dt className="text-mute">Penyimpanan</dt><dd className="break-all font-mono text-xs">{h.storage_dir}</dd>
            <dt className="text-mute">Folder model</dt><dd className="break-all font-mono text-xs">{h.models_dir}</dd>
          </dl>
          <p className="mt-2 text-xs text-mute">Diubah lewat file <code>.env</code> (awalan <code>ASF_</code>). Pengelolaan model AI (memuat/melepas dari VRAM) dikerjakan pada Fase 2–3.</p>
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
