import { Bookmark, Film, RotateCcw, Scissors } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Empty, ErrorBox, fmtDur, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import type { Clip } from "../types";

const seconds = (value: string, fallback: number) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export function ClipEditor() {
  const toast = useAppStore((s) => s.toast);
  const [params, setParams] = useSearchParams();
  const videoId = params.get("video") ?? "";
  const videos = useAsync(() => api.videos({ sort: "newest" }), []);
  const video = videos.data?.find((item) => item.id === videoId) ?? null;
  const clips = useAsync(() => videoId ? api.clips(videoId) : Promise.resolve([] as Clip[]), [videoId]);
  const [clipId, setClipId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [title, setTitle] = useState("");
  const [playhead, setPlayhead] = useState(0);
  const [saving, setSaving] = useState(false);
  const player = useRef<HTMLVideoElement>(null);
  const clip = clips.data?.find((item) => item.id === clipId) ?? null;
  const startValue = seconds(start, -1);
  const endValue = seconds(end, -1);
  const validRange = Boolean(video && startValue >= 0 && endValue > startValue && endValue <= video.duration && endValue - startValue >= 1 && endValue - startValue <= 900);
  const rangeStart = video ? Math.min(100, Math.max(0, (startValue / video.duration) * 100)) : 0;
  const rangeEnd = video ? Math.min(100, Math.max(0, (endValue / video.duration) * 100)) : 0;
  const playheadPosition = video ? Math.min(100, Math.max(0, (playhead / video.duration) * 100)) : 0;

  useEffect(() => {
    if (!videoId && videos.data?.length) setParams({ video: videos.data[0].id }, { replace: true });
  }, [videoId, videos.data, setParams]);

  useEffect(() => {
    if (clips.data && !clips.data.some((item) => item.id === clipId)) setClipId(clips.data[0]?.id ?? "");
  }, [clips.data, clipId]);

  useEffect(() => {
    if (!clip) return;
    setStart(clip.start_time.toFixed(2));
    setEnd(clip.end_time.toFixed(2));
    setTitle(clip.title);
    setPlayhead(clip.start_time);
    if (player.current) player.current.currentTime = clip.start_time;
  }, [clip?.id]);

  function mark(which: "start" | "end") {
    const time = Math.min(video?.duration ?? 0, Math.max(0, player.current?.currentTime ?? playhead));
    if (which === "start") setStart(time.toFixed(2));
    else setEnd(time.toFixed(2));
  }

  function seek(value: number) {
    const time = Math.min(video?.duration ?? 0, Math.max(0, value));
    setPlayhead(time);
    if (player.current) player.current.currentTime = time;
  }

  async function save() {
    if (!clip || !validRange) return;
    setSaving(true);
    try {
      await api.patchClip(clip.id, { start_time: startValue, end_time: endValue, title: title.trim() });
      toast("success", "Batas klip disimpan");
      await clips.reload();
    } catch (error) {
      toast("error", errMsg(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="Editor Klip" subtitle="Atur titik awal dan akhir klip dengan pemutar dan timeline, lalu simpan sebelum render." />
      {videos.loading ? <Spinner /> : videos.error ? <ErrorBox message={videos.error} onRetry={videos.reload} /> : !videos.data?.length ? (
        <Empty title="Belum ada video" hint="Unggah video terlebih dahulu dari Perpustakaan Video." />
      ) : (
        <div className="space-y-4">
          <label className="block max-w-xl text-xs text-mute">Video sumber
            <select className="input mt-1" value={videoId} onChange={(event) => setParams(event.target.value ? { video: event.target.value } : {})}>
              {videos.data.map((item) => <option key={item.id} value={item.id}>{item.filename} · {fmtDur(item.duration)}</option>)}
            </select>
          </label>

          {clips.loading ? <Spinner label="Memuat klip…" /> : clips.error ? <ErrorBox message={clips.error} onRetry={clips.reload} /> : !clips.data?.length ? (
            <Empty title="Belum ada klip untuk video ini" hint="Buat klip terlebih dahulu di Smart Crop & Render." />
          ) : (
            <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
              <section className="card space-y-3">
                <h2 className="text-sm font-semibold">Daftar klip</h2>
                <div className="max-h-[28rem] space-y-1 overflow-y-auto">
                  {clips.data.map((item) => (
                    <button key={item.id} className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${item.id === clipId ? "bg-brand/15 text-brand-2" : "hover:bg-panel-2"}`} onClick={() => setClipId(item.id)}>
                      <Film size={15} className="shrink-0" />
                      <span className="min-w-0 flex-1 truncate">{item.title || "Klip tanpa judul"}</span>
                      <span className="shrink-0 text-xs text-mute">{fmtDur(item.duration)}</span>
                    </button>
                  ))}
                </div>
              </section>

              {clip && video && (
                <section className="card space-y-4">
                  <video ref={player} className="max-h-[65vh] w-full rounded-lg bg-black" src={api.streamUrl(video.id)} controls preload="metadata"
                    onTimeUpdate={(event) => setPlayhead(event.currentTarget.currentTime)} />
                  <div className="space-y-2">
                    <div className="relative h-8 overflow-hidden rounded-lg bg-panel-2" aria-label="Timeline video">
                      <div className="absolute inset-y-1 rounded bg-brand/40" style={{ left: `${rangeStart}%`, width: `${Math.max(0, rangeEnd - rangeStart)}%` }} />
                      <div className="absolute inset-y-0 w-0.5 bg-warn" style={{ left: `${playheadPosition}%` }} />
                    </div>
                    <input type="range" className="w-full" min={0} max={video.duration} step={0.05} value={playhead} onChange={(event) => seek(Number(event.target.value))} aria-label="Geser posisi timeline" />
                    <div className="flex justify-between text-xs text-mute"><span>0:00</span><span>{fmtDur(playhead)} / {fmtDur(video.duration)}</span><span>{fmtDur(video.duration)}</span></div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    <label className="block text-xs text-mute">Judul klip
                      <input className="input mt-1" maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} />
                    </label>
                    <label className="block text-xs text-mute">Mulai (detik)
                      <span className="mt-1 flex gap-1"><input className="input" type="number" min={0} max={video.duration} step={0.05} value={start} onChange={(event) => setStart(event.target.value)} /><button className="btn btn-ghost shrink-0" title="Tandai awal pada posisi pemutar" onClick={() => mark("start")}><Scissors size={14} />Awal</button></span>
                    </label>
                    <label className="block text-xs text-mute">Selesai (detik)
                      <span className="mt-1 flex gap-1"><input className="input" type="number" min={0} max={video.duration} step={0.05} value={end} onChange={(event) => setEnd(event.target.value)} /><button className="btn btn-ghost shrink-0" title="Tandai akhir pada posisi pemutar" onClick={() => mark("end")}><Scissors size={14} />Akhir</button></span>
                    </label>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
                    <span className={`text-xs ${validRange ? "text-mute" : "text-bad"}`}>{validRange ? `Durasi klip: ${fmtDur(endValue - startValue)}` : "Rentang harus 1–900 detik dan berada di dalam video."}</span>
                    <div className="flex gap-2">
                      <button className="btn btn-ghost" onClick={() => { setStart(clip.start_time.toFixed(2)); setEnd(clip.end_time.toFixed(2)); setTitle(clip.title); }} disabled={saving}><RotateCcw size={14} />Reset</button>
                      <button className="btn btn-primary" onClick={() => void save()} disabled={saving || !validRange}><Bookmark size={14} />{saving ? "Menyimpan…" : "Simpan perubahan"}</button>
                    </div>
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
