import { Archive, ArchiveRestore, FolderPlus, Library, Pencil, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge, Confirm, Empty, ErrorBox, fmtDate, Modal, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, errMsg } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import type { Project } from "../types";

function NameDialog({ title, initial, onSave, onClose }: { title: string; initial?: Project; onSave: (name: string, description: string) => Promise<void>; onClose: () => void }) {
  const [name, setName] = useState(initial?.name ?? "");
  const [desc, setDesc] = useState(initial?.description ?? "");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await onSave(name.trim(), desc);
      onClose();
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <input className="input" autoFocus maxLength={200} placeholder="Nama proyek" value={name} onChange={(e) => setName(e.target.value)} />
        <textarea className="input" rows={3} maxLength={2000} placeholder="Deskripsi (opsional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Batal</button>
          <button className="btn btn-primary" disabled={busy || !name.trim()}>Simpan</button>
        </div>
      </form>
    </Modal>
  );
}

export function Projects() {
  const toast = useAppStore((s) => s.toast);
  const [params, setParams] = useSearchParams();
  const [showArchived, setShowArchived] = useState(false);
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useAsync(() => api.projects({ status: showArchived ? "archived" : "active", q: q.trim() }), [showArchived, q]);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);

  useEffect(() => {
    if (params.get("new")) {
      setCreating(true);
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast("success", ok);
      void reload();
    } catch (e) {
      toast("error", errMsg(e));
    }
  };

  return (
    <>
      <PageHeader title="Proyek" subtitle="Kelompokkan video dan klip berdasarkan proyek."
        actions={<button className="btn btn-primary" onClick={() => setCreating(true)}><FolderPlus size={16} />Proyek baru</button>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input className="input max-w-xs" placeholder="Cari proyek…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari proyek" />
        <label className="flex items-center gap-2 text-sm text-mute"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />Tampilkan arsip</label>
      </div>
      {loading ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data || data.length === 0 ? (
        <Empty title={showArchived ? "Tidak ada proyek arsip" : "Belum ada proyek"} hint="Klik “Proyek baru” untuk memulai." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((p) => (
            <div key={p.id} className="card flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-medium" title={p.name}>{p.name}</div>
                  <div className="text-xs text-mute">Diperbarui {fmtDate(p.updated_at)}</div>
                </div>
                {p.status === "archived" && <Badge>arsip</Badge>}
              </div>
              {p.description && <p className="line-clamp-2 text-xs text-mute">{p.description}</p>}
              <div className="flex gap-3 text-xs text-mute"><span>{p.video_count} video</span><span>{p.clip_count} klip</span></div>
              <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
                <Link className="btn btn-ghost" to={`/library?project=${p.id}`}><Library size={14} />Buka</Link>
                <button className="btn btn-ghost" onClick={() => setEditing(p)} aria-label="Ganti nama"><Pencil size={14} /></button>
                <button className="btn btn-ghost" onClick={() => void act(() => api.updateProject(p.id, { status: p.status === "active" ? "archived" : "active" }), p.status === "active" ? "Proyek diarsipkan" : "Proyek dipulihkan")}
                  aria-label={p.status === "active" ? "Arsipkan" : "Pulihkan"}>{p.status === "active" ? <Archive size={14} /> : <ArchiveRestore size={14} />}</button>
                <button className="btn btn-danger" onClick={() => setDeleting(p)} aria-label="Hapus"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {creating && <NameDialog title="Proyek baru" onClose={() => setCreating(false)} onSave={async (n, d) => { await api.createProject(n, d); toast("success", "Proyek dibuat"); void reload(); }} />}
      {editing && <NameDialog title="Ubah proyek" initial={editing} onClose={() => setEditing(null)} onSave={async (n, d) => { await api.updateProject(editing.id, { name: n, description: d }); toast("success", "Proyek diperbarui"); void reload(); }} />}
      {deleting && <Confirm title="Hapus proyek?" message={`“${deleting.name}” beserta ${deleting.video_count} video dan semua klipnya akan dihapus permanen dari penyimpanan lokal.`}
        onCancel={() => setDeleting(null)} onConfirm={() => { const p = deleting; setDeleting(null); void act(() => api.deleteProject(p.id), "Proyek dihapus"); }} />}
    </>
  );
}
