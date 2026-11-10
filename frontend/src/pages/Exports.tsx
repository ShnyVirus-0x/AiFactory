import { Download, Film } from "lucide-react";
import { Link } from "react-router-dom";
import { Empty, ErrorBox, fmtBytes, fmtDate, fmtDur, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

export function Exports() {
  const { data, error, loading, reload } = useAsync(api.exports);
  return (
    <>
      <PageHeader title="Export Center" subtitle="Pratinjau dan unduh video hasil render." actions={<button className="btn btn-ghost" onClick={() => void reload()}>Muat ulang</button>} />
      {loading ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.length ? (
        <Empty icon={<Film size={24} />} title="Belum ada hasil ekspor" hint="Render klip dari Batch Renderer; hasil yang selesai akan muncul di sini." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((job) => (
            <article key={job.id} className="card">
              <video className="mb-3 aspect-[9/16] max-h-[28rem] w-full rounded-lg bg-black object-contain" controls preload="metadata" src={job.download_url ?? undefined}>
                Browser Anda tidak mendukung pratinjau video.
              </video>
              <div className="mb-3 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-medium">{job.clip_title || `Klip ${job.clip_id.slice(0, 8)}`}</h2>
                  <p className="mt-1 text-xs text-mute">{job.output_info ? `${job.output_info.width}×${job.output_info.height} · ${fmtDur(job.output_info.duration)} · ${fmtBytes(job.output_info.size)}` : "Render selesai"}</p>
                  <p className="mt-1 text-xs text-mute">{fmtDate(job.updated_at)}</p>
                </div>
                <a className="btn btn-primary shrink-0" href={job.download_url ?? undefined} download aria-label={`Unduh ${job.clip_title || "hasil render"}`}>
                  <Download size={15} />Unduh
                </a>
              </div>
            </article>
          ))}
        </div>
      )}
      <p className="mt-4 text-xs text-mute"><Link className="text-brand-2 hover:underline" to="/renderer">Kembali ke antrean render</Link></p>
    </>
  );
}
