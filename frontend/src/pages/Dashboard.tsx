import { Activity, Clapperboard, Cpu, FolderKanban, HardDrive, MemoryStick, MonitorPlay, Plus, Thermometer, Upload, Video, XCircle } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Empty, ErrorBox, fmtBytes, fmtDate, Meter, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { useAppStore } from "../stores/useAppStore";

function Stat({ icon: Icon, label, value, tone }: { icon: typeof Video; label: string; value: number; tone?: "bad" | "ok" | "warn" }) {
  const color = tone === "bad" && value > 0 ? "text-bad" : tone === "ok" ? "text-ok" : tone === "warn" && value > 0 ? "text-warn" : "text-brand-2";
  return (
    <div className="card flex items-center gap-3">
      <Icon className={color} size={22} />
      <div>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        <div className="text-xs text-mute">{label}</div>
      </div>
    </div>
  );
}

function Hardware() {
  const r = useAppStore((s) => s.resources);
  if (!r) return <Spinner label="Membaca sensor perangkat keras…" />;
  const g = r.gpu.gpus[0];
  return (
    <div className="space-y-3">
      {r.gpu.available && g ? (
        <>
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 font-medium"><MonitorPlay size={16} className="text-brand-2" />{g.name}</span>
            <span className="flex items-center gap-2 text-xs text-mute">
              {g.temperature_c !== null && <span className="flex items-center gap-1"><Thermometer size={12} />{g.temperature_c.toFixed(0)}°C</span>}
              {r.gpu.cuda_version && <Badge kind="brand">CUDA {r.gpu.cuda_version}</Badge>}
            </span>
          </div>
          <Meter label="Penggunaan GPU" value={g.utilization_percent} />
          <Meter label="VRAM" value={(g.vram_used_mb / g.vram_total_mb) * 100} detail={`${(g.vram_used_mb / 1024).toFixed(1)} / ${(g.vram_total_mb / 1024).toFixed(1)} GB`} />
        </>
      ) : (
        <div className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-xs text-warn">
          <b>GPU NVIDIA tidak terdeteksi.</b> {r.gpu.reason} Rendering akan memakai CPU.
        </div>
      )}
      <Meter label={`CPU — ${r.cpu.name}`} value={r.cpu.percent} detail={`${r.cpu.cores_logical ?? "?"} thread`} />
      <Meter label="RAM" value={r.ram.percent} detail={`${fmtBytes(r.ram.used)} / ${fmtBytes(r.ram.total)}`} />
      {r.disk && <Meter label="Penyimpanan" value={r.disk.percent} detail={`${fmtBytes(r.disk.free)} tersedia`} warnAt={85} badAt={95} />}
    </div>
  );
}

export function Dashboard() {
  const nav = useNavigate();
  const { data, error, loading, reload } = useAsync(api.dashboard);
  const health = useAsync(api.health);
  if (loading) return <Spinner />;
  if (error || !data) return <ErrorBox message={error ?? "Gagal memuat dashboard"} onRetry={reload} />;
  const t = data.totals;
  return (
    <>
      <PageHeader title="Dashboard" subtitle="Ringkasan proyek, antrean, dan kondisi perangkat keras Anda (data nyata)."
        actions={<>
          <button className="btn btn-ghost" onClick={() => nav("/library?upload=1")}><Upload size={16} />Unggah cepat</button>
          <button className="btn btn-primary" onClick={() => nav("/projects?new=1")}><Plus size={16} />Proyek baru</button>
        </>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat icon={FolderKanban} label="Total proyek" value={t.projects} />
        <Stat icon={Video} label="Video diunggah" value={t.videos} />
        <Stat icon={Clapperboard} label="Klip dihasilkan" value={t.clips} />
        <Stat icon={MonitorPlay} label="Render berhasil" value={t.renders_done} tone="ok" />
        <Stat icon={XCircle} label="Render gagal" value={t.renders_failed} tone="bad" />
        <Stat icon={Activity} label="Sedang diproses" value={t.jobs_running} tone="warn" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card lg:col-span-1">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Cpu size={16} />Perangkat keras</h2>
          <Hardware />
        </section>
        <section className="card lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold">Proyek terbaru</h2>
          {data.recent_projects.length === 0 ? (
            <Empty title="Belum ada proyek" hint="Buat proyek pertama Anda, lalu unggah video dari komputer." />
          ) : (
            <ul className="divide-y divide-line">
              {data.recent_projects.map((p) => (
                <li key={p.id}>
                  <Link to={`/library?project=${p.id}`} className="flex items-center justify-between py-2 text-sm hover:text-brand-2">
                    <span>{p.name}</span>
                    <span className="flex items-center gap-3 text-xs text-mute">{p.video_count} video · {fmtDate(p.updated_at)}{p.status === "archived" && <Badge>arsip</Badge>}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card">
          <h2 className="mb-3 text-sm font-semibold">Antrean pemrosesan <span className="ml-1 text-xs font-normal text-mute">({t.jobs_queued} menunggu)</span></h2>
          {data.queue.length === 0 ? <p className="text-sm text-mute">Antrean kosong. Pilih klip di Batch Renderer untuk memulai.</p> : (
            <ul className="space-y-2 text-sm">{data.queue.map((j) => <li key={j.id}><Meter label={`${j.id.slice(0, 8)} · ${j.status}`} value={j.progress * 100} /></li>)}</ul>
          )}
        </section>
        <section className="card">
          <h2 className="mb-3 text-sm font-semibold">Aktivitas terbaru</h2>
          {data.activity.length === 0 ? <p className="text-sm text-mute">Belum ada aktivitas.</p> : (
            <ul className="space-y-2 text-sm">{data.activity.map((a) => <li key={a.id} className="flex justify-between gap-3"><span>{a.message}</span><span className="shrink-0 text-xs text-mute">{fmtDate(a.created_at)}</span></li>)}</ul>
          )}
        </section>
        <section className="card">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold"><HardDrive size={16} />Kesehatan sistem {health.data && <Badge kind={health.data.status === "ok" ? "ok" : "warn"}>{health.data.status === "ok" ? "baik" : "perlu perhatian"}</Badge>}</h2>
          {health.data ? (
            <ul className="space-y-1.5 text-xs">
              {health.data.checks.map((c) => (
                <li key={c.key} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${c.ok ? "bg-ok" : c.required ? "bg-bad" : "bg-warn"}`} />{c.label}</span>
                  <span className="max-w-[55%] truncate text-mute" title={c.detail}>{c.detail}</span>
                </li>
              ))}
            </ul>
          ) : <Spinner />}
          <Link to="/settings" className="mt-3 flex items-center gap-1 text-xs text-brand-2 hover:underline"><MemoryStick size={12} />Diagnostik lengkap</Link>
        </section>
      </div>
    </>
  );
}
