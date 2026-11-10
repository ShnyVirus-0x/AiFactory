import { CheckSquare, Play, RotateCcw, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Empty, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import type { RenderJob } from "../types";

const statusLabel: Record<RenderJob["status"], string> = {
  queued: "Menunggu",
  running: "Merender",
  done: "Selesai",
  failed: "Gagal",
  cancelled: "Dibatalkan",
};

function statusKind(status: RenderJob["status"]): "ok" | "warn" | "bad" | "mute" {
  if (status === "done") return "ok";
  if (status === "running" || status === "queued") return "warn";
  if (status === "failed") return "bad";
  return "mute";
}

export function Renderer() {
  const toast = useAppStore((s) => s.toast);
  const projects = useAsync(() => api.projects({ status: "active" }), []);
  const [projectId, setProjectId] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const clips = useAsync(() => projectId ? api.projectClips(projectId) : Promise.resolve([]), [projectId]);
  const jobs = useAsync(api.jobs);
  const activeJobs = jobs.data ?? [];

  useEffect(() => {
    if (!projectId && projects.data?.length) setProjectId(projects.data[0].id);
  }, [projectId, projects.data]);
  useEffect(() => setSelected(new Set()), [projectId]);

  const toggle = (id: string) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const selectAll = () => setSelected(new Set((clips.data ?? []).map((clip) => clip.id)));

  async function renderSelected() {
    if (!projectId || selected.size === 0) return;
    setSubmitting(true);
    try {
      const result = await api.renderProject(projectId, [...selected]);
      const message = `${result.jobs.length} klip masuk antrean${result.skipped.length ? ` · ${result.skipped.length} dilewati karena sudah aktif` : ""}`;
      toast("success", message);
      setSelected(new Set());
      await jobs.reload();
    } catch (e) {
      toast("error", errMsg(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function act(job: RenderJob, action: "cancel" | "retry") {
    try {
      if (action === "cancel") await api.cancelRender(job.id);
      else await api.retryRender(job.id);
      toast("success", action === "cancel" ? "Render dibatalkan" : "Render dimasukkan ulang ke antrean");
      await jobs.reload();
    } catch (e) {
      toast("error", errMsg(e));
    }
  }

  return (
    <>
      <PageHeader title="Batch Renderer" subtitle="Pilih klip dari proyek dan render ke antrean persisten." />

      <section className="card mb-5 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <label className="block min-w-64 text-xs text-mute">Proyek
            <select className="input mt-1" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              {(projects.data ?? []).map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <div className="flex gap-2">
            <button className="btn btn-ghost" onClick={selectAll} disabled={!clips.data?.length}><CheckSquare size={15} />Pilih semua</button>
            <button className="btn btn-primary" onClick={() => void renderSelected()} disabled={submitting || selected.size === 0}>
              <Play size={15} />{submitting ? "Memasukkan…" : `Render ${selected.size} klip`}
            </button>
          </div>
        </div>
        {projects.loading ? <Spinner /> : projects.error ? <ErrorBox message={projects.error} onRetry={projects.reload} /> : !projects.data?.length ? (
          <Empty title="Belum ada proyek aktif" hint="Buat proyek dan tambahkan klip sebelum mulai merender." />
        ) : clips.loading ? <Spinner label="Memuat klip…" /> : clips.error ? <ErrorBox message={clips.error} onRetry={clips.reload} /> : !clips.data?.length ? (
          <Empty title="Belum ada klip di proyek ini" hint="Buat klip dari Perpustakaan Video sebelum merender." />
        ) : (
          <div className="max-h-80 divide-y divide-line overflow-y-auto rounded-lg border border-line">
            {clips.data.map((clip) => (
              <label key={clip.id} className="flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm hover:bg-panel-2">
                <input type="checkbox" checked={selected.has(clip.id)} onChange={() => toggle(clip.id)} aria-label={`Pilih ${clip.title}`} />
                <span className="min-w-0 flex-1 truncate">{clip.title || "Klip tanpa judul"}</span>
                <span className="shrink-0 text-xs text-mute">{clip.duration.toFixed(1)} dtk</span>
                {clip.approved && <Badge kind="ok">disetujui</Badge>}
              </label>
            ))}
          </div>
        )}
      </section>

      <PageHeader title="Antrean render" subtitle="Progres dan status pekerjaan terbaru." actions={<button className="btn btn-ghost" onClick={() => void jobs.reload()}>Muat ulang</button>} />
      {jobs.loading ? <Spinner /> : jobs.error ? <ErrorBox message={jobs.error} onRetry={jobs.reload} /> : activeJobs.length === 0 ? (
        <Empty title="Antrean render masih kosong" hint="Pilih satu atau beberapa klip untuk memulai." />
      ) : (
        <div className="space-y-2">
          {activeJobs.map((job) => (
            <article key={job.id} className="card flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate text-sm font-medium">{job.clip_title || `Klip ${job.clip_id.slice(0, 8)}`}</span>
                  <Badge kind={statusKind(job.status)}>{statusLabel[job.status]}</Badge>
                  {job.encoder && <Badge>{job.encoder}{job.uses_gpu ? " · GPU" : " · CPU"}</Badge>}
                </div>
                {(job.status === "queued" || job.status === "running") && (
                  <div className="mt-2 h-1.5 overflow-hidden rounded bg-panel-2">
                    <div className="h-full bg-brand transition-all" style={{ width: `${Math.max(0, Math.min(100, job.progress * 100))}%` }} />
                  </div>
                )}
                {job.status === "failed" && job.error_message && <p className="mt-1 text-xs text-bad">{job.error_message}</p>}
              </div>
              {job.status === "done" && <Link className="btn btn-ghost" to="/exports">Lihat ekspor</Link>}
              {(job.status === "queued" || job.status === "running") && <button className="btn btn-ghost" onClick={() => void act(job, "cancel")} aria-label="Batalkan render"><XCircle size={15} />Batalkan</button>}
              {job.status === "failed" && <button className="btn btn-ghost" onClick={() => void act(job, "retry")}><RotateCcw size={15} />Coba lagi</button>}
            </article>
          ))}
        </div>
      )}
    </>
  );
}
