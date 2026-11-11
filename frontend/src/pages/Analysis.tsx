import { ArrowRight, Brain, Check, LoaderCircle, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Empty, ErrorBox, fmtDur, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import type { ClipCandidate } from "../types";

export function Analysis() {
  const toast = useAppStore((s) => s.toast);
  const videos = useAsync(() => api.videos({ sort: "newest" }), []);
  const health = useAsync(api.health, []);
  const [videoId, setVideoId] = useState("");
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState("");
  const [candidates, setCandidates] = useState<ClipCandidate[]>([]);
  const [saved, setSaved] = useState<Set<number>>(new Set());
  const [limit, setLimit] = useState(12);
  const video = videos.data?.find((item) => item.id === videoId);
  const ollama = health.data?.ollama;

  async function analyze() {
    if (!videoId) return;
    setBusy(true);
    setCandidates([]);
    setSaved(new Set());
    try {
      const result = await api.suggestClips(videoId, limit);
      setCandidates(result.candidates);
      setModel(result.model);
      if (!result.candidates.length) toast("info", "Belum ada kandidat yang memenuhi batas waktu. Coba model lain atau cek transkrip.");
    } catch (error) {
      toast("error", errMsg(error));
    } finally {
      setBusy(false);
    }
  }

  async function createClip(candidate: ClipCandidate, index: number) {
    try {
      await api.createClip(videoId, {
        start_time: candidate.start_time,
        end_time: candidate.end_time,
        title: candidate.title,
        hook: candidate.hook,
        score: candidate.score,
        category: candidate.category,
      });
      setSaved((current) => new Set(current).add(index));
      toast("success", "Kandidat disimpan sebagai klip");
    } catch (error) {
      toast("error", errMsg(error));
    }
  }

  return (
    <>
      <PageHeader title="Analisis AI" subtitle="Cari momen menarik dari transkrip dan tinjau kandidat sebelum dijadikan klip." />
      {videos.loading ? <Spinner /> : videos.error ? <ErrorBox message={videos.error} onRetry={videos.reload} /> : !videos.data?.length ? (
        <Empty title="Belum ada video" hint="Unggah video di Perpustakaan Video, lalu buat transkrip." />
      ) : (
        <>
          <section className="card mb-5 space-y-4">
            <div className="flex items-start gap-3">
              <Brain className="mt-0.5 shrink-0 text-brand-2" size={20} />
              <div>
                <h2 className="text-sm font-semibold">Analisis lokal dengan Ollama</h2>
                <p className="mt-1 text-xs leading-relaxed text-mute">
                  Yang dianalisis hanya teks transkrip dan timestamp; file video tidak dikirim ke Ollama. Analisis dapat memerlukan beberapa menit, bergantung pada panjang transkrip dan kecepatan komputer.
                </p>
              </div>
            </div>
            {health.loading ? <Spinner label="Memeriksa Ollama…" /> : health.error ? <ErrorBox message={health.error} onRetry={health.reload} /> : (
              <div className="rounded-lg bg-panel-2 p-3 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span>Status Ollama:</span>
                  {ollama?.running ? <Badge kind={ollama.model_ready ? "ok" : "warn"}>{ollama.model_ready ? "model siap" : "Ollama aktif, model belum diunduh"}</Badge> : <Badge kind="warn">tidak berjalan</Badge>}
                  <span className="font-mono text-mute">{ollama?.wanted_model}</span>
                </div>
                {!ollama?.running || !ollama.model_ready ? (
                  <p className="mt-2 text-mute">
                    Jalankan Ollama di komputer ini, lalu unduh model dengan <code className="rounded bg-panel px-1">ollama pull {ollama?.wanted_model ?? "qwen2.5:7b-instruct"}</code>. Tidak perlu API key; model menggunakan resource komputer.
                  </p>
                ) : <p className="mt-2 text-mute">Transkrip diproses lokal oleh model {ollama.wanted_model}; tidak menggunakan API cloud.</p>}
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px_auto] sm:items-end">
              <label className="block text-xs text-mute">Video dengan transkrip
                <select className="input mt-1" value={videoId} onChange={(event) => { setVideoId(event.target.value); setCandidates([]); setSaved(new Set()); }}>
                  <option value="">Pilih video…</option>
                  {videos.data.map((item) => <option key={item.id} value={item.id}>{item.filename} · {fmtDur(item.duration)}</option>)}
                </select>
              </label>
              <label className="block text-xs text-mute">Maks. kandidat
                <select className="input mt-1" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
                  {[5, 10, 12, 20, 30].map((number) => <option key={number} value={number}>{number}</option>)}
                </select>
              </label>
              <button className="btn btn-primary" disabled={!videoId || busy || !ollama?.model_ready} onClick={() => void analyze()}>
                {busy ? <><LoaderCircle className="animate-spin" size={15} />Menganalisis…</> : <><Sparkles size={15} />Cari kandidat klip</>}
              </button>
            </div>
            {video && !busy && <p className="text-xs text-mute">Video {fmtDur(video.duration)}. Jika belum ada transkrip, buka <Link className="text-brand-2 underline" to={`/transcripts?video=${video.id}`}>halaman Transkripsi</Link> dan transkripsikan terlebih dahulu.</p>}
            {busy && <p className="text-xs text-mute">Model sedang membaca transkrip secara bertahap. Jangan tutup halaman sampai analisis selesai.</p>}
          </section>

          {candidates.length > 0 && (
            <section className="space-y-3">
              <PageHeader title={`${candidates.length} kandidat klip`} subtitle={`Model lokal: ${model}. Periksa konteksnya sebelum render.`} />
              {candidates.map((candidate, index) => (
                <article key={`${candidate.start_time}-${candidate.end_time}-${index}`} className="card space-y-3">
                  <div className="flex flex-wrap items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-medium">{candidate.title}</h3>
                      <div className="mt-1 flex flex-wrap gap-2 text-xs text-mute">
                        <span>{fmtDur(candidate.start_time)}–{fmtDur(candidate.end_time)} · {fmtDur(candidate.end_time - candidate.start_time)}</span>
                        <span>·</span><span>{candidate.category}</span>
                      </div>
                    </div>
                    <Badge kind={candidate.score >= 75 ? "ok" : "brand"}>Skor {candidate.score}/100</Badge>
                  </div>
                  {candidate.hook && <p className="text-sm text-ink">“{candidate.hook}”</p>}
                  {candidate.reason && <p className="text-xs text-mute">{candidate.reason}</p>}
                  <div className="flex flex-wrap gap-2 border-t border-line pt-3">
                    <button className="btn btn-primary" disabled={saved.has(index)} onClick={() => void createClip(candidate, index)}>
                      {saved.has(index) ? <><Check size={14} />Tersimpan</> : <><ArrowRight size={14} />Jadikan klip</>}
                    </button>
                    {saved.has(index) && <Link className="btn btn-ghost" to={`/editor?video=${videoId}`}>Edit klip</Link>}
                  </div>
                </article>
              ))}
            </section>
          )}
        </>
      )}
    </>
  );
}
