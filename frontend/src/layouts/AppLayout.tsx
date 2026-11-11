import { BarChart3, Boxes, Brain, Captions, Clapperboard, FileText, Crop, Download, FolderKanban, Image, LayoutDashboard, Library, Menu, Settings, Wifi, WifiOff, X } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useState } from "react";
import { Badge, Toasts } from "../components/ui";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { useAppStore } from "../stores/useAppStore";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, phase: 1 },
  { to: "/projects", label: "Proyek", icon: FolderKanban, phase: 1 },
  { to: "/library", label: "Perpustakaan Video", icon: Library, phase: 1 },
  { to: "/transcripts", label: "Transkripsi", icon: FileText, phase: 2 },
  { to: "/analysis", label: "Analisis AI", icon: Brain, phase: 3 },
  { to: "/editor", label: "Editor Klip", icon: Clapperboard, phase: 4 },
  { to: "/subtitles", label: "Studio Subtitle", icon: Captions, phase: 5 },
  { to: "/crop", label: "Smart Crop & Render", icon: Crop, phase: 4 },
  { to: "/templates", label: "Template", icon: Boxes, phase: 5 },
  { to: "/thumbnails", label: "Studio Thumbnail", icon: Image, phase: 7 },
  { to: "/renderer", label: "Batch Renderer", icon: BarChart3, phase: 6, ready: true },
  { to: "/exports", label: "Export Center", icon: Download, phase: 6, ready: true },
  { to: "/settings", label: "Pengaturan", icon: Settings, phase: 1 },
];

export function AppLayout() {
  useLiveEvents();
  const ws = useAppStore((s) => s.wsConnected);
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="flex min-h-screen md:h-full">
      {mobileOpen && <button className="fixed inset-0 z-20 bg-black/60 md:hidden" onClick={() => setMobileOpen(false)} aria-label="Tutup menu" />}
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-60 shrink-0 flex-col border-r border-line bg-panel transition-transform md:static md:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center justify-between gap-2 px-4 py-4">
          <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white">▶</div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">AI Shorts Factory</div>
            <div className="text-[11px] text-mute">Studio lokal · 100% offline</div>
          </div>
          </div>
          <button className="rounded p-1 text-mute hover:bg-panel-2 md:hidden" onClick={() => setMobileOpen(false)} aria-label="Tutup menu"><X size={18} /></button>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {NAV.map(({ to, label, icon: Icon, phase, ready }) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${isActive ? "bg-brand/15 text-brand-2" : "text-mute hover:bg-panel-2 hover:text-ink"}`}>
              <Icon size={17} />
              <span className="flex-1">{label}</span>
              {phase > 4 && !ready && <span className="rounded bg-panel-2 px-1.5 text-[10px] text-mute" title={`Tersedia pada Fase ${phase}`}>F{phase}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-line p-3 text-xs">
          <Badge kind={ws ? "ok" : "bad"}>{ws ? <Wifi size={12} /> : <WifiOff size={12} />}{ws ? "Terhubung (live)" : "Terputus — mencoba lagi"}</Badge>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-line bg-panel px-4 py-3 md:hidden">
          <button className="rounded p-1 text-mute hover:bg-panel-2" onClick={() => setMobileOpen(true)} aria-label="Buka menu"><Menu size={20} /></button>
          <span className="text-sm font-semibold">AI Shorts Factory</span>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl p-4 sm:p-6"><Outlet /></div>
        </main>
      </div>
      <Toasts />
    </div>
  );
}
