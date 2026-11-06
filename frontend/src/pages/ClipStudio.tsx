import { Check, Download, Film, Play, Scissors, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Confirm, Empty, ErrorBox, fmtBytes, fmtDur, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import type { Clip, CropAnalysis, RenderJob, RenderSpec } from "../types";

const PRESETS: [string, string][] = [["pop_yellow", "Viral Pop"], ["neon_green", "Neon Punch"], ["cyber_violet", "Cyber Violet"], ["fire_red", "Fire Red"], ["electric_cyan", "Electric Cyan"], ["golden", "Golden Aura"], ["clean", "Clean Minimal"], ["bold_outline", "Bold Outline"]];
const num = (v: string, d = 0) => (Number.isFinite(parseFloat(v)) ? parseFloat(v) : d);

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block text-xs text-mute">{label}<div className="mt-1">{children}</div></label>;
}

function SpecEditor({ clip, onJob }: { clip: Clip; onJob: (id: string) => void }) {
  const toast = useAppStore((s) => s.toast);
  const edit = useAsync(() => api.getEdit(clip.id), [clip.id]);
  const [spec, setSpec] = useState<RenderSpec | null>(null);
  const [t, setT] = useState(0);
  const [nonce, setNonce] = useState(0);
  const [analysis, setAnalysis] = useState<CropAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [imgErr, setImgErr] = useState(false);
  const timer = useRef<number>(0);

  useEffect(() => { if (edit.data) setSpec(edit.data); }, [edit.data]);
  useEffect(() => { setAnalysis(null); setT(0); }, [clip.id]);

  const change = (patch: Partial<RenderSpec>) => {
    if (!spec) return;
    const next = { ...spec, ...patch };
    setSpec(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      api.putEdit(clip.id, next).then(() => { setNonce((n) => n + 1); setImgErr(false); }).catch((e) => toast("error", errMsg(e)));
    }, 500);
  };
  const cap = (patch: Partial<RenderSpec["captions"]>) => spec && change({ captions: { ...spec.captions, ...patch } });

  if (edit.error) return <ErrorBox message={edit.error} onRetry={edit.reload} />;
  if (!spec) return <Spinner />;

  return (
    <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
      <div>
        <div className="overflow-hidden rounded-lg border border-line bg-black" style={{ aspectRatio: "9 / 16" }}>
          {imgErr ? <div className="grid h-full place-items-center p-3 text-center text-xs text-bad">Pratinjau gagal dibuat</div>
            : <img src={api.previewUrl(clip.id, t, nonce)} alt="Pratinjau crop" className="h-full w-full object-cover" onError={() => setImgErr(true)} />}
        </div>
        <input type="range" className="mt-2 w-full" min={0} max={Math.max(0.1, clip.duration - 0.1)} step={0.1} value={t} onChange={(e) => { setT(num(e.target.value)); setImgErr(false); }} aria-label="Posisi pratinjau" />
        <div className="text-center text-xs text-mute">{fmtDur(t)} / {fmtDur(clip.duration)} · pratinjau memakai crop yang sama dengan render (tanpa subtitle)</div>
      </div>

      <div className="space-y-4 text-sm">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Layout">
            <select className="input" value={spec.layout} onChange={(e) => change({ layout: e.target.value as RenderSpec["layout"] })}>
              <option value="fill">Isi 9:16 (crop)</option><option value="letterbox">Letterbox</option><option value="split">Split (kamera atas + layar bawah)</option></select></Field>
          {spec.layout === "fill" && (
            <Field label="Mode crop">
              <select className="input" value={spec.crop_mode} onChange={(e) => change({ crop_mode: e.target.value as RenderSpec["crop_mode"] })}>
                <option value="face">Ikuti wajah otomatis</option><option value="center">Center crop</option><option value="manual">Manual</option></select></Field>)}
          {spec.layout === "letterbox" && (
            <Field label="Latar"><select className="input" value={spec.background} onChange={(e) => change({ background: e.target.value as RenderSpec["background"] })}>
              <option value="blur">Blur</option><option value="black">Hitam</option></select></Field>)}
          {spec.layout === "split" && <Field label={`Tinggi bagian atas: ${Math.round(spec.split_top_ratio * 100)}%`}>
            <input type="range" min={0.2} max={0.8} step={0.05} value={spec.split_top_ratio} onChange={(e) => change({ split_top_ratio: num(e.target.value, 0.5) })} className="w-full" /></Field>}
        </div>
        {spec.layout === "fill" && spec.crop_mode === "manual" && (
          <Field label={`Posisi horizontal crop: ${Math.round(spec.manual_x * 100)}%`}>
            <input type="range" min={0} max={1} step={0.01} value={spec.manual_x} onChange={(e) => change({ manual_x: num(e.target.value, 0.5) })} className="w-full" /></Field>)}
        {spec.layout === "split" && (
          <div className="grid grid-cols-4 gap-2">
            {(["x", "y", "w", "h"] as const).map((k) => <Field key={k} label={`Area kamera ${k.toUpperCase()} (0–1)`}>
              <input className="input" type="number" min={0} max={1} step={0.05} value={spec.cam_rect[k]} onChange={(e) => change({ cam_rect: { ...spec.cam_rect, [k]: Math.min(1, Math.max(k === "w" || k === "h" ? 0.05 : 0, num(e.target.value))) } })} /></Field>)}
          </div>)}

        {spec.layout === "fill" && spec.crop_mode === "face" && (
          <div className="rounded-lg bg-panel-2 p-3">
            <button className="btn btn-ghost" disabled={analyzing} onClick={() => { setAnalyzing(true); api.analyzeCrop(clip.id).then(setAnalysis).catch((e) => toast("error", errMsg(e))).finally(() => setAnalyzing(false)); }}>
              {analyzing ? "Menganalisis wajah…" : "Analisis wajah & jalur kamera"}</button>
            {analysis && (
              <div className="mt-2 space-y-1 text-xs">
                <div>{analysis.note}</div>
                {analysis.available && <div className="text-mute">Wajah terdeteksi di {analysis.frames_with_face}/{analysis.samples} sampel · maks {analysis.max_faces} wajah · {analysis.static ? "kamera dikunci" : `pergeseran ${((analysis.travel ?? 0) * 100).toFixed(0)}%`}</div>}
                {analysis.track.length > 1 && (
                  <svg viewBox="0 0 100 20" className="h-10 w-full rounded bg-panel" preserveAspectRatio="none">
                    <polyline fill="none" stroke="currentColor" className="text-brand-2" strokeWidth="1.2" vectorEffect="non-scaling-stroke"
                      points={analysis.track.map((p) => `${(p.t / Math.max(clip.duration, 0.1)) * 100},${20 - p.x * 20}`).join(" ")} /></svg>)}
              </div>)}
          </div>)}

        <fieldset className="rounded-lg border border-line p-3">
          <legend className="px-1 text-xs text-mute">Subtitle (dari transkrip)</legend>
          <label className="mb-2 flex items-center gap-2"><input type="checkbox" checked={spec.captions.enabled} onChange={(e) => cap({ enabled: e.target.checked })} />Tampilkan subtitle per kata</label>
          {spec.captions.enabled && (
            <div className="grid gap-3 sm:grid-cols-4">
              <Field label="Preset"><select className="input" value={spec.captions.preset} onChange={(e) => cap({ preset: e.target.value })}>{PRESETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
              <Field label="Kata per baris"><input className="input" type="number" min={1} max={8} value={spec.captions.words_per_line} onChange={(e) => cap({ words_per_line: Math.min(8, Math.max(1, Math.round(num(e.target.value, 3)))) })} /></Field>
              <Field label="Ukuran"><input className="input" type="number" min={24} max={200} value={spec.captions.size} onChange={(e) => cap({ size: Math.min(200, Math.max(24, Math.round(num(e.target.value, 84)))) })} /></Field>
              <Field label={`Posisi vertikal ${Math.round(spec.captions.y * 100)}%`}><input type="range" min={0.1} max={0.95} step={0.01} value={spec.captions.y} onChange={(e) => cap({ y: num(e.target.value, 0.78) })} className="w-full" /></Field>
            </div>)}
          <p className="mt-2 text-xs text-mute">Dibutuhkan transkrip video ini (halaman Transkripsi). Tanpa transkrip, tidak ada subtitle yang dibuat.</p>
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Codec"><select className="input" value={spec.codec} onChange={(e) => change({ codec: e.target.value as RenderSpec["codec"] })}><option value="h264">H.264</option><option value="h265">H.265 (HEVC)</option></select></Field>
          <Field label={`Kualitas CRF ${spec.crf} (kecil = bagus)`}><input type="range" min={14} max={32} value={spec.crf} onChange={(e) => change({ crf: Math.round(num(e.target.value, 20)) })} className="w-full" /></Field>
          <Field label="Teks judul (opsional)"><input className="input" maxLength={120} value={spec.title_overlay ?? ""} onChange={(e) => change({ title_overlay: e.target.value || null })} /></Field>
          <label className="flex items-end gap-2 pb-2 text-xs text-mute"><input type="checkbox" checked={spec.loudnorm} onChange={(e) => change({ loudnorm: e.target.checked })} />Normalisasi volume</label>
        </div>

        <RenderPanel clip={clip} onJob={onJob} flush={async () => { window.clearTimeout(timer.current); await api.putEdit(clip.id, spec); }} />
      </div>
    </div>
  );
}

function RenderPanel({ clip, flush, onJob }: { clip: Clip; flush: () => Promise<void>; onJob: (id: string) => void }) {
  const toast = useAppStore((s) => s.toast);
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<RenderJob | null>(null);
  useEffect(() => { setJobId(""); setJob(null); }, [clip.id]);
  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    const tick = async () => {
      try { const j = await api.renderJob(jobId); if (!stop) { setJob(j); if (j.status === "queued" || j.status === "running") setTimeout(tick, 800); else onJob(j.id); } } catch (e) { if (!stop) toast("error", errMsg(e)); }
    };
    void tick();
    return () => { stop = true; };
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps
  const busy = job?.status === "queued" || job?.status === "running";
  return (
    <div className="rounded-lg bg-panel-2 p-3">
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-primary" disabled={busy} onClick={() => { flush().then(() => api.renderClip(clip.id)).then((r) => setJobId(r.id)).catch((e) => toast("error", errMsg(e))); }}><Play size={14} />{busy ? "Merender…" : "Render klip"}</button>
        {busy && job && <button className="btn btn-ghost" onClick={() => void api.cancelRender(job.id)}>Batal</button>}
        {job?.encoder && <Badge kind={job.uses_gpu ? "ok" : "mute"}>{job.encoder} · {job.uses_gpu ? "GPU (NVENC)" : "CPU"}</Badge>}
        {job && <Badge kind={job.status === "done" ? "ok" : job.status === "failed" ? "bad" : "brand"}>{job.status}</Badge>}
      </div>
      {busy && job && <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-panel"><div className="h-full bg-brand transition-all" style={{ width: `${job.progress * 100}%` }} /></div>}
      {job?.error_message && <div className="mt-2 text-xs text-bad">{job.error_message}</div>}
      {job?.status === "done" && job.output_info && (
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
          <a className="btn btn-primary" href={job.download_url ?? "#"} download><Download size={14} />Unduh MP4</a>
          <span className="text-mute">Diverifikasi FFprobe: {job.output_info.width}×{job.output_info.height} · {job.output_info.fps} fps · {job.output_info.video_codec} · {job.output_info.has_audio ? "ada audio" : "tanpa audio"} · {fmtDur(job.output_info.duration)} · {fmtBytes(job.output_info.size)}</span>
          {job.output_info.crop_note && <span className="text-mute">{job.output_info.crop_note}</span>}
        </div>)}
    </div>
  );
}

export function ClipStudio() {
  const toast = useAppStore((s) => s.toast);
  const [params, setParams] = useSearchParams();
  const videoId = params.get("video") ?? "";
  const videos = useAsync(() => api.videos({ sort: "newest" }));
  const video = videos.data?.find((v) => v.id === videoId) ?? null;
  const clips = useAsync(() => (videoId ? api.clips(videoId) : Promise.resolve([] as Clip[])), [videoId]);
  const [sel, setSel] = useState("");
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("10");
  const [title, setTitle] = useState("");
  const [del, setDel] = useState<Clip | null>(null);
  const player = useRef<HTMLVideoElement>(null);
  const clip = clips.data?.find((c) => c.id === sel) ?? null;
  useEffect(() => { if (clips.data && !clips.data.some((c) => c.id === sel)) setSel(clips.data[0]?.id ?? ""); }, [clips.data, sel]);

  const mark = (which: "start" | "end") => { const t = (player.current?.currentTime ?? 0).toFixed(1); (which === "start" ? setStart : setEnd)(t); };
  const create = () => api.createClip(videoId, { start_time: num(start), end_time: num(end), title }).then((c) => { toast("success", "Klip dibuat"); setSel(c.id); setTitle(""); void clips.reload(); }).catch((e) => toast("error", errMsg(e)));

  return (
    <>
      <PageHeader title="Smart Crop & Render" subtitle="Buat klip dari video, atur crop (ikuti wajah otomatis), subtitle, lalu render MP4 9:16. Encoder yang dipakai (GPU/CPU) ditampilkan apa adanya." />
      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <div className="space-y-4">
          <section className="card space-y-3">
            <select className="input" value={videoId} onChange={(e) => setParams(e.target.value ? { video: e.target.value } : {})} aria-label="Video">
              <option value="">Pilih video…</option>{videos.data?.map((v) => <option key={v.id} value={v.id}>{v.filename} ({fmtDur(v.duration)})</option>)}</select>
            {video ? (
              <>
                <video ref={player} className="w-full rounded-lg bg-black" src={api.streamUrl(video.id)} controls preload="metadata" />
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Mulai (detik)"><div className="flex gap-1"><input className="input" value={start} onChange={(e) => setStart(e.target.value)} /><button className="btn btn-ghost" title="Ambil dari posisi video" onClick={() => mark("start")}>◂</button></div></Field>
                  <Field label="Selesai (detik)"><div className="flex gap-1"><input className="input" value={end} onChange={(e) => setEnd(e.target.value)} /><button className="btn btn-ghost" title="Ambil dari posisi video" onClick={() => mark("end")}>◂</button></div></Field>
                </div>
                <input className="input" placeholder="Judul klip (opsional)" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
                <button className="btn btn-primary w-full" onClick={() => void create()}><Scissors size={14} />Buat klip</button>
              </>
            ) : <Empty icon={<Film />} title="Pilih video" />}
          </section>
          {videoId && (
            <section className="card">
              <h2 className="mb-2 text-sm font-semibold">Klip ({clips.data?.length ?? 0})</h2>
              {clips.loading ? <Spinner /> : !clips.data?.length ? <p className="text-sm text-mute">Belum ada klip.</p> : (
                <ul className="space-y-1">
                  {clips.data.map((c) => (
                    <li key={c.id} className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${c.id === sel ? "bg-brand/15" : "hover:bg-panel-2"}`}>
                      <button className="min-w-0 flex-1 text-left" onClick={() => setSel(c.id)}><div className="truncate">{c.title}</div><div className="text-xs text-mute">{fmtDur(c.start_time)}–{fmtDur(c.end_time)} · {c.duration.toFixed(1)} dtk</div></button>
                      <button className={`rounded p-1 ${c.approved ? "text-ok" : "text-mute hover:text-ink"}`} title="Setujui untuk render" onClick={() => void api.patchClip(c.id, { approved: !c.approved }).then(() => clips.reload())}><Check size={15} /></button>
                      <button className="rounded p-1 text-mute hover:text-bad" aria-label="Hapus" onClick={() => setDel(c)}><Trash2 size={15} /></button>
                    </li>))}
                </ul>)}
            </section>)}
        </div>
        <section className="card min-h-[400px]">
          {clips.error ? <ErrorBox message={clips.error} onRetry={clips.reload} /> : clip ? <SpecEditor clip={clip} onJob={() => undefined} /> : <Empty title="Pilih atau buat klip" hint="Atur rentang waktu di panel kiri, lalu klik “Buat klip”." />}
        </section>
      </div>
      {del && <Confirm title="Hapus klip?" message={`“${del.title}” dan pengaturannya akan dihapus. Video sumber tidak terpengaruh.`} onCancel={() => setDel(null)} onConfirm={() => { const c = del; setDel(null); void api.deleteClip(c.id).then(() => clips.reload()).catch((e) => toast("error", errMsg(e))); }} />}
    </>
  );
}
