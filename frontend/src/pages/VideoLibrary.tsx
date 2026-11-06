import { Film, Pencil, Play, Trash2, UploadCloud, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Confirm, Empty, ErrorBox, fmtBytes, fmtDate, fmtDur, Modal, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg, uploadVideos } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import type { Video } from "../types";

const ACCEPT = ".mp4,.mov,.mkv,.webm,.avi";

function Dropzone({ projectId, disabled, onDone }: { projectId: string; disabled: boolean; onDone: () => void }) {
  const toast = useAppStore((s) => s.toast);
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [pct, setPct] = useState<number | null>(null);

  async function send(files: File[]) {
    if (!files.length || !projectId) return;
    setPct(0);
    try {
      const r = await uploadVideos(projectId, files, setPct);
      if (r.succeeded) toast("success", `${r.succeeded} video berhasil diunggah`);
      for (const it of r.items.filter((i) => !i.ok)) toast("error", `${it.filename}: ${it.error}`);
      onDone();
    } catch (e) {
      toast("error", errMsg(e));
    } finally {
      setPct(null);
      if (input.current) input.current.value = "";
    }
  }
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    if (!disabled && pct === null) void send(Array.from(e.dataTransfer.files));
  };
  return (
    <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}
      className={`mb-5 rounded-xl border-2 border-dashed p-6 text-center transition ${over ? "border-brand bg-brand/10" : "border-line"} ${disabled ? "opacity-50" : ""}`}>
      <UploadCloud className="mx-auto mb-2 text-brand-2" />
      {pct === null ? (
        <>
          <p className="text-sm">Seret &amp; lepas video di sini, atau{" "}
            <button className="text-brand-2 underline disabled:no-underline" disabled={disabled} onClick={() => input.current?.click()}>pilih file</button></p>
          <p className="mt-1 text-xs text-mute">{disabled ? "Pilih atau buat proyek terlebih dahulu." : "MP4, MOV, MKV, WEBM, AVI · bisa banyak file sekaligus · diproses lokal"}</p>
        </>
      ) : (
        <div className="mx-auto max-w-sm">
          <div className="mb-1 text-xs text-mute">{pct < 100 ? `Mengunggah… ${pct.toFixed(0)}%` : "Memvalidasi dan membuat thumbnail…"}</div>
          <div className="h-2 overflow-hidden rounded-full bg-panel-2"><div className="h-full bg-brand transition-all" style={{ width: `${pct}%` }} /></div>
        </div>
      )}
      <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={(e) => void send(Array.from(e.target.files ?? []))} />
    </div>
  );
}

function VideoCard({ v, onPlay, onRename, onDelete }: { v: Video; onPlay: () => void; onRename: () => void; onDelete: () => void }) {
  return (
    <div className="card overflow-hidden p-0">
      <button className="group relative block aspect-video w-full bg-panel-2" onClick={onPlay} aria-label={`Putar ${v.filename}`}>
        {v.has_thumbnail ? <img src={api.thumbUrl(v.id)} alt="" loading="lazy" className="h-full w-full object-cover" /> : <Film className="absolute inset-0 m-auto text-mute" />}
        <span className="absolute inset-0 grid place-items-center bg-black/0 opacity-0 transition group-hover:bg-black/40 group-hover:opacity-100"><Play className="text-white" /></span>
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/70 px-1.5 text-xs tabular-nums">{fmtDur(v.duration)}</span>
      </button>
      <div className="space-y-2 p-3">
        <div className="truncate text-sm font-medium" title={v.filename}>{v.filename}</div>
        <div className="flex flex-wrap gap-1.5">
          <Badge kind="brand">{v.width}×{v.height}</Badge>
          <Badge>{v.fps.toFixed(v.fps % 1 ? 2 : 0)} fps</Badge>
          <Badge>{v.video_codec}</Badge>
          <Badge kind={v.audio_tracks ? "mute" : "warn"}>{v.audio_tracks ? <><Volume2 size={11} />{v.audio_tracks} audio</> : <><VolumeX size={11} />tanpa audio</>}</Badge>
        </div>
        <div className="flex items-center justify-between text-xs text-mute">
          <span>{fmtBytes(v.file_size)} · {fmtDate(v.created_at)}</span>
          <span className="flex gap-1">
            <button className="rounded p-1 hover:bg-panel-2 hover:text-ink" onClick={onRename} aria-label="Ganti nama"><Pencil size={14} /></button>
            <button className="rounded p-1 hover:bg-bad/20 hover:text-bad" onClick={onDelete} aria-label="Hapus"><Trash2 size={14} /></button>
          </span>
        </div>
      </div>
    </div>
  );
}

export function VideoLibrary() {
  const toast = useAppStore((s) => s.toast);
  const [params, setParams] = useSearchParams();
  const projectId = params.get("project") ?? "";
  const projects = useAsync(() => api.projects({ status: "active" }));
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("newest");
  const [minHeight, setMinHeight] = useState("");
  const [audio, setAudio] = useState("");
  const videos = useAsync(
    () => api.videos({ project_id: projectId || undefined, q: q.trim(), sort, min_height: minHeight ? Number(minHeight) : undefined, has_audio: audio === "" ? undefined : audio === "1" }),
    [projectId, q, sort, minHeight, audio],
  );
  const [playing, setPlaying] = useState<Video | null>(null);
  const [renaming, setRenaming] = useState<Video | null>(null);
  const [newName, setNewName] = useState("");
  const [deleting, setDeleting] = useState<Video | null>(null);

  // pilih proyek pertama otomatis agar unggah cepat langsung bisa dipakai
  useEffect(() => {
    if (!projectId && projects.data && projects.data.length === 1) setParams({ project: projects.data[0].id }, { replace: true });
  }, [projectId, projects.data, setParams]);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast("success", ok);
      void videos.reload();
    } catch (e) {
      toast("error", errMsg(e));
    }
  };

  return (
    <>
      <PageHeader title="Perpustakaan Video" subtitle="Unggah dan kelola video sumber. Semua file tetap di komputer Anda." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select className="input max-w-xs" value={projectId} onChange={(e) => setParams(e.target.value ? { project: e.target.value } : {})} aria-label="Proyek">
          <option value="">Semua proyek</option>
          {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input className="input max-w-xs" placeholder="Cari nama file…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari" />
        <select className="input w-auto" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Urutkan">
          <option value="newest">Terbaru</option><option value="oldest">Terlama</option><option value="name">Nama</option><option value="duration">Durasi</option><option value="size">Ukuran</option>
        </select>
        <select className="input w-auto" value={minHeight} onChange={(e) => setMinHeight(e.target.value)} aria-label="Resolusi minimal">
          <option value="">Semua resolusi</option><option value="720">≥ 720p</option><option value="1080">≥ 1080p</option><option value="2160">≥ 4K</option>
        </select>
        <select className="input w-auto" value={audio} onChange={(e) => setAudio(e.target.value)} aria-label="Audio">
          <option value="">Audio: semua</option><option value="1">Ada audio</option><option value="0">Tanpa audio</option>
        </select>
      </div>
      <Dropzone projectId={projectId} disabled={!projectId} onDone={() => void videos.reload()} />
      {videos.loading ? <Spinner /> : videos.error ? <ErrorBox message={videos.error} onRetry={videos.reload} /> : !videos.data || videos.data.length === 0 ? (
        <Empty icon={<Film />} title="Tidak ada video" hint={q || minHeight || audio ? "Ubah pencarian atau filter." : "Unggah video pertama Anda dengan area di atas."} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {videos.data.map((v) => <VideoCard key={v.id} v={v} onPlay={() => setPlaying(v)} onRename={() => { setRenaming(v); setNewName(v.filename); }} onDelete={() => setDeleting(v)} />)}
        </div>
      )}
      {playing && <Modal title={playing.filename} wide onClose={() => setPlaying(null)}><video className="w-full rounded-lg bg-black" src={api.streamUrl(playing.id)} controls autoPlay /></Modal>}
      {renaming && (
        <Modal title="Ganti nama video" onClose={() => setRenaming(null)}>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); const v = renaming; setRenaming(null); void act(() => api.renameVideo(v.id, newName), "Nama diperbarui"); }}>
            <input className="input" autoFocus maxLength={200} value={newName} onChange={(e) => setNewName(e.target.value)} />
            <div className="flex justify-end gap-2"><button type="button" className="btn btn-ghost" onClick={() => setRenaming(null)}>Batal</button><button className="btn btn-primary" disabled={!newName.trim()}>Simpan</button></div>
          </form>
        </Modal>
      )}
      {deleting && <Confirm title="Hapus video?" message={`“${deleting.filename}” dan thumbnail-nya akan dihapus permanen dari penyimpanan lokal.`} onCancel={() => setDeleting(null)}
        onConfirm={() => { const v = deleting; setDeleting(null); void act(() => api.deleteVideo(v.id), "Video dihapus"); }} />}
    </>
  );
}
