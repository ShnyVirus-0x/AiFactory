import { Download, Merge, Replace, Scissors, Search, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Confirm, Empty, ErrorBox, fmtDur, Modal, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import type { Segment, TranscriptionJob, WhisperModel } from "../types";

const LANGS: [string, string][] = [["auto", "Deteksi otomatis"], ["id", "Indonesia"], ["en", "Inggris"], ["ms", "Melayu"], ["ja", "Jepang"], ["ko", "Korea"], ["zh", "Mandarin"], ["es", "Spanyol"], ["ar", "Arab"]];

const ts = (s: number) => {
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
};

/* ------------------------------ Model Whisper ------------------------------ */
function ModelsPanel() {
  const toast = useAppStore((s) => s.toast);
  const { data, error, reload } = useAsync(api.whisperModels);
  const [ask, setAsk] = useState<WhisperModel | null>(null);
  useEffect(() => {
    if (!data?.some((m) => m.download?.status === "downloading")) return;
    const t = setInterval(() => void reload(), 1000);
    return () => clearInterval(t);
  }, [data, reload]);
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <Spinner />;
  return (
    <section className="card">
      <h2 className="mb-1 text-sm font-semibold">Model Whisper (lokal)</h2>
      <p className="mb-3 text-xs text-mute">Model diunduh sekali dari huggingface.co setelah Anda setuju, lalu berjalan offline. Ukuran adalah perkiraan.</p>
      <ul className="space-y-2">
        {data.map((m) => {
          const d = m.download;
          return (
            <li key={m.name} className="rounded-lg bg-panel-2 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-medium">{m.name}</span> {m.default && <Badge kind="brand">bawaan</Badge>}
                  <div className="text-xs text-mute">{m.note} · ±{m.approx_size_mb} MB · VRAM ±{m.vram_mb} MB</div>
                </div>
                {m.installed ? <Badge kind="ok">terpasang{m.installed_size_mb ? ` · ${m.installed_size_mb} MB` : ""}</Badge>
                  : d?.status === "downloading" ? <Badge kind="brand">mengunduh…</Badge>
                  : <button className="btn btn-ghost" disabled={!m.enough_disk} onClick={() => setAsk(m)} title={m.enough_disk ? "" : "Ruang disk tidak cukup"}><Download size={14} />Unduh</button>}
              </div>
              {d?.status === "downloading" && (
                <div className="mt-2">
                  <div className="h-1.5 overflow-hidden rounded-full bg-panel"><div className="h-full bg-brand transition-all" style={{ width: `${Math.min(100, (d.downloaded_mb / d.total_mb) * 100)}%` }} /></div>
                  <div className="mt-1 text-xs text-mute">{d.downloaded_mb.toFixed(0)} / ±{d.total_mb.toFixed(0)} MB</div>
                </div>
              )}
              {d?.status === "failed" && <div className="mt-2 text-xs text-bad">Unduhan gagal: {d.error}</div>}
            </li>
          );
        })}
      </ul>
      {ask && (
        <Confirm title={`Unduh model ${ask.name}?`} confirmLabel="Unduh"
          message={`Akan mengunduh ±${ask.approx_size_mb} MB dari huggingface.co (${ask.repo}) ke folder ${ask.path}. Pastikan ruang disk cukup. Unduhan dibatalkan otomatis bila gagal dan tidak menimpa model yang ada.`}
          onCancel={() => setAsk(null)}
          onConfirm={() => { const m = ask; setAsk(null); api.downloadWhisper(m.name).then(() => { toast("info", `Mengunduh ${m.name}…`); void reload(); }).catch((e) => toast("error", errMsg(e))); }} />
      )}
    </section>
  );
}

/* ------------------------------ Baris segmen ------------------------------ */
function SegmentRow({ seg, query, onSeek, onChanged }: { seg: Segment; query: string; onSeek: (t: number) => void; onChanged: () => void }) {
  const toast = useAppStore((s) => s.toast);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(seg.text);
  const [splitting, setSplitting] = useState(false);
  const [del, setDel] = useState(false);
  useEffect(() => setText(seg.text), [seg.text]);
  const run = (p: Promise<unknown>, ok?: string) => p.then(() => { if (ok) toast("success", ok); onChanged(); }).catch((e) => toast("error", errMsg(e)));

  const hl = (s: string) => {
    if (!query.trim()) return s;
    const i = s.toLowerCase().indexOf(query.trim().toLowerCase());
    return i < 0 ? s : <>{s.slice(0, i)}<mark className="rounded bg-warn/30 px-0.5 text-ink">{s.slice(i, i + query.trim().length)}</mark>{s.slice(i + query.trim().length)}</>;
  };

  return (
    <li className="group rounded-lg border border-transparent px-3 py-2 hover:border-line hover:bg-panel-2/50">
      <div className="flex gap-3">
        <button className="w-24 shrink-0 pt-0.5 text-left font-mono text-xs text-brand-2 hover:underline" onClick={() => onSeek(seg.start_time)} title="Putar dari sini">{ts(seg.start_time)}–{ts(seg.end_time)}</button>
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="space-y-2">
              <textarea className="input" rows={2} value={text} autoFocus onChange={(e) => setText(e.target.value)} />
              <div className="flex gap-2">
                <button className="btn btn-primary" disabled={!text.trim()} onClick={() => void run(api.patchSegment(seg.id, { text }).then(() => setEditing(false)), "Segmen disimpan")}>Simpan</button>
                <button className="btn btn-ghost" onClick={() => { setEditing(false); setText(seg.text); }}>Batal</button>
              </div>
            </div>
          ) : splitting ? (
            <div className="text-sm">
              <div className="mb-1 text-xs text-mute">Klik kata terakhir untuk bagian pertama:</div>
              <div className="flex flex-wrap gap-1">
                {seg.words.slice(0, -1).map((w, i) => <button key={i} className="rounded bg-panel-2 px-1.5 py-0.5 hover:bg-brand/30" onClick={() => void run(api.splitSegment(seg.id, i).then(() => setSplitting(false)), "Segmen dipisah")}>{w}</button>)}
                <button className="btn btn-ghost !py-0" onClick={() => setSplitting(false)}><X size={12} /></button>
              </div>
            </div>
          ) : (
            <p className="cursor-text text-sm leading-relaxed" onDoubleClick={() => setEditing(true)} title="Klik dua kali untuk mengedit">
              {hl(seg.text)} {seg.edited && <Badge kind="mute">diedit</Badge>} {seg.words_estimated && <span title="Timing kata diperkirakan karena segmen diedit"><Badge kind="warn">timing perkiraan</Badge></span>}
            </p>
          )}
        </div>
        {!editing && !splitting && (
          <div className="flex shrink-0 gap-0.5 opacity-0 transition group-hover:opacity-100">
            <button className="rounded p-1.5 text-mute hover:bg-panel-2 hover:text-ink" aria-label="Pisah" title="Pisah segmen" disabled={seg.words.length < 2} onClick={() => setSplitting(true)}><Scissors size={14} /></button>
            <button className="rounded p-1.5 text-mute hover:bg-panel-2 hover:text-ink" aria-label="Gabung" title="Gabung dengan berikutnya" onClick={() => void run(api.mergeNext(seg.id), "Digabung")}><Merge size={14} /></button>
            <button className="rounded p-1.5 text-mute hover:bg-bad/20 hover:text-bad" aria-label="Hapus" title="Hapus segmen" onClick={() => setDel(true)}><Trash2 size={14} /></button>
          </div>
        )}
      </div>
      {del && <Confirm title="Hapus segmen?" message={`“${seg.text.slice(0, 120)}” akan dihapus dari transkrip ini.`} onCancel={() => setDel(false)} onConfirm={() => { setDel(false); void run(api.deleteSegment(seg.id), "Segmen dihapus"); }} />}
    </li>
  );
}

/* ------------------------------ Halaman ------------------------------ */
export function Transcription() {
  const toast = useAppStore((s) => s.toast);
  const [params, setParams] = useSearchParams();
  const videoId = params.get("video") ?? "";
  const videos = useAsync(() => api.videos({ sort: "newest" }));
  const models = useAsync(api.whisperModels);
  const video = videos.data?.find((v) => v.id === videoId) ?? null;
  const jobs = useAsync(() => (videoId ? api.asrJobs(videoId) : Promise.resolve([] as TranscriptionJob[])), [videoId]);
  const trs = useAsync(() => (videoId ? api.transcripts(videoId) : Promise.resolve([])), [videoId]);
  const [trId, setTrId] = useState("");
  const [q, setQ] = useState("");
  const [lang, setLang] = useState("auto");
  const [model, setModel] = useState("");
  const [track, setTrack] = useState(0);
  const [busy, setBusy] = useState(false);
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [delTr, setDelTr] = useState(false);
  const player = useRef<HTMLVideoElement>(null);

  const installed = models.data?.filter((m) => m.installed) ?? [];
  useEffect(() => { if (!model && installed.length) setModel((installed.find((m) => m.default) ?? installed[0]).name); }, [installed, model]);
  useEffect(() => { if (trs.data?.length && !trs.data.some((t) => t.id === trId)) setTrId(trs.data[0].id); if (trs.data && !trs.data.length) setTrId(""); }, [trs.data, trId]);

  const tr = useAsync(() => (trId ? api.transcript(trId, q) : Promise.resolve(null)), [trId, q]);
  const active = jobs.data?.find((j) => j.status === "queued" || j.status === "running");

  const start = async () => {
    setBusy(true);
    try {
      await api.transcribe(videoId, { language: lang, model, audio_track: track });
      toast("info", "Transkripsi dimulai");
      void jobs.reload();
    } catch (e) { toast("error", errMsg(e)); } finally { setBusy(false); }
  };
  const seek = (t: number) => { if (player.current) { player.current.currentTime = t; void player.current.play().catch(() => undefined); } };

  return (
    <>
      <PageHeader title="Transkripsi" subtitle="faster-whisper berjalan lokal. Timestamp per kata, editor, pencarian, dan ekspor SRT/VTT/TXT." />
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <section className="card space-y-3">
            <h2 className="text-sm font-semibold">Transkripsi baru</h2>
            <select className="input" value={videoId} onChange={(e) => setParams(e.target.value ? { video: e.target.value } : {})} aria-label="Video">
              <option value="">Pilih video…</option>
              {videos.data?.map((v) => <option key={v.id} value={v.id}>{v.filename} ({fmtDur(v.duration)})</option>)}
            </select>
            {video && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-xs text-mute">Bahasa
                    <select className="input mt-1" value={lang} onChange={(e) => setLang(e.target.value)}>{LANGS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
                  <label className="text-xs text-mute">Trek audio
                    <select className="input mt-1" value={track} onChange={(e) => setTrack(Number(e.target.value))} disabled={video.audio_tracks < 1}>
                      {Array.from({ length: Math.max(1, video.audio_tracks) }, (_, i) => <option key={i} value={i}>Trek {i + 1}</option>)}</select></label>
                </div>
                <label className="block text-xs text-mute">Model
                  <select className="input mt-1" value={model} onChange={(e) => setModel(e.target.value)} disabled={!installed.length}>
                    {installed.length ? installed.map((m) => <option key={m.name} value={m.name}>{m.name}</option>) : <option>Belum ada model terpasang</option>}</select></label>
                {video.audio_tracks < 1 && <div className="text-xs text-warn">Video ini tidak punya trek audio.</div>}
                <button className="btn btn-primary w-full" disabled={busy || !!active || !model || !installed.length || video.audio_tracks < 1} onClick={() => void start()}>
                  {active ? "Sedang berjalan…" : "Mulai transkripsi"}</button>
              </>
            )}
            {jobs.data && jobs.data.length > 0 && (
              <ul className="space-y-2 border-t border-line pt-3 text-xs">
                {jobs.data.slice(0, 4).map((j) => (
                  <li key={j.id}>
                    <div className="flex items-center justify-between">
                      <span>{j.model} · {j.device || "—"}</span>
                      <span className="flex items-center gap-2">
                        <Badge kind={j.status === "done" ? "ok" : j.status === "failed" ? "bad" : j.status === "cancelled" ? "mute" : "brand"}>{j.status}</Badge>
                        {(j.status === "running" || j.status === "queued") && <button className="text-bad hover:underline" onClick={() => void api.cancelAsr(j.id).then(() => jobs.reload())}>batal</button>}
                      </span>
                    </div>
                    {j.status === "running" && <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-panel-2"><div className="h-full bg-brand transition-all" style={{ width: `${j.progress * 100}%` }} /></div>}
                    {j.error_message && <div className="mt-1 text-bad">{j.error_message}</div>}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <ModelsPanel />
        </div>

        <section className="card min-h-[420px]">
          {!videoId ? <Empty title="Pilih video" hint="Pilih video di panel kiri untuk melihat atau membuat transkrip." />
            : trs.loading ? <Spinner /> : !trs.data?.length ? <Empty title="Belum ada transkrip" hint={installed.length ? "Klik “Mulai transkripsi”." : "Unduh salah satu model Whisper terlebih dahulu (panel kiri bawah)."} />
            : (
              <>
                {video && <video ref={player} className="mb-3 max-h-60 w-full rounded-lg bg-black" src={api.streamUrl(video.id)} controls preload="metadata" />}
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <select className="input w-auto" value={trId} onChange={(e) => setTrId(e.target.value)} aria-label="Versi transkrip">
                    {trs.data.map((t) => <option key={t.id} value={t.id}>{new Date(t.created_at).toLocaleString("id-ID")} · {t.model} · {t.language}</option>)}
                  </select>
                  <div className="relative min-w-40 flex-1"><Search size={14} className="absolute left-2.5 top-3 text-mute" /><input className="input" style={{ paddingLeft: 34 }} placeholder="Cari di transkrip…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
                  <button className="btn btn-ghost" onClick={() => setReplaceOpen(true)}><Replace size={14} />Cari &amp; ganti</button>
                  {(["srt", "vtt", "txt"] as const).map((f) => <a key={f} className="btn btn-ghost" href={api.exportUrl(trId, f)} download>{f.toUpperCase()}</a>)}
                  <button className="btn btn-danger" onClick={() => setDelTr(true)} aria-label="Hapus transkrip"><Trash2 size={14} /></button>
                </div>
                {tr.loading ? <Spinner /> : tr.error ? <ErrorBox message={tr.error} onRetry={tr.reload} /> : tr.data && (
                  <>
                    <div className="mb-2 flex flex-wrap gap-2 text-xs text-mute">
                      <Badge kind="brand">{tr.data.language}{tr.data.language_probability ? ` · ${(tr.data.language_probability * 100).toFixed(0)}%` : ""}</Badge>
                      <span>{tr.data.segment_count} segmen · {fmtDur(tr.data.duration)} · {tr.data.model}</span>
                      {q && <span>{tr.data.total_matches} cocok</span>}
                      <span className="ml-auto">Klik dua kali pada teks untuk mengedit</span>
                    </div>
                    <ul className="max-h-[560px] space-y-0.5 overflow-y-auto">
                      {tr.data.segments.map((s) => <SegmentRow key={s.id} seg={s} query={q} onSeek={seek} onChanged={() => { void tr.reload(); void trs.reload(); }} />)}
                      {!tr.data.segments.length && <Empty title="Tidak ada hasil" />}
                    </ul>
                  </>
                )}
              </>
            )}
        </section>
      </div>
      {replaceOpen && trId && <ReplaceDialog id={trId} onClose={() => setReplaceOpen(false)} onDone={() => { void tr.reload(); }} />}
      {delTr && <Confirm title="Hapus transkrip ini?" message="Seluruh segmen dan hasil editan pada versi transkrip ini akan dihapus. Versi lain tidak terpengaruh." onCancel={() => setDelTr(false)}
        onConfirm={() => { setDelTr(false); void api.deleteTranscript(trId).then(() => { toast("success", "Transkrip dihapus"); void trs.reload(); }).catch((e) => toast("error", errMsg(e))); }} />}
    </>
  );
}

function ReplaceDialog({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: () => void }) {
  const toast = useAppStore((s) => s.toast);
  const [find, setFind] = useState("");
  const [repl, setRepl] = useState("");
  const [cs, setCs] = useState(false);
  const [ww, setWw] = useState(false);
  return (
    <Modal title="Cari & ganti (koreksi transkrip)" onClose={onClose}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); api.replaceAll(id, { find, replace: repl, case_sensitive: cs, whole_word: ww }).then((r) => { toast("success", `${r.replaced} penggantian`); onDone(); onClose(); }).catch((er) => toast("error", errMsg(er))); }}>
        <input className="input" autoFocus placeholder="Cari" value={find} onChange={(e) => setFind(e.target.value)} />
        <input className="input" placeholder="Ganti dengan" value={repl} onChange={(e) => setRepl(e.target.value)} />
        <label className="flex items-center gap-2 text-sm text-mute"><input type="checkbox" checked={cs} onChange={(e) => setCs(e.target.checked)} />Sensitif huruf besar/kecil</label>
        <label className="flex items-center gap-2 text-sm text-mute"><input type="checkbox" checked={ww} onChange={(e) => setWw(e.target.checked)} />Hanya kata utuh</label>
        <div className="flex justify-end gap-2"><button type="button" className="btn btn-ghost" onClick={onClose}>Batal</button><button className="btn btn-primary" disabled={!find}>Ganti semua</button></div>
      </form>
    </Modal>
  );
}
