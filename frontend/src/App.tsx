import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { ComingSoon } from "./pages/ComingSoon";
import { ClipStudio } from "./pages/ClipStudio";
import { Dashboard } from "./pages/Dashboard";
import { Projects } from "./pages/Projects";
import { SettingsPage } from "./pages/SettingsPage";
import { Transcription } from "./pages/Transcription";
import { VideoLibrary } from "./pages/VideoLibrary";

const soon = (path: string, title: string, capability: string, description: string) => (
  <Route key={path} path={path} element={<ComingSoon title={title} capability={capability} description={description} />} />
);

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="projects" element={<Projects />} />
        <Route path="library" element={<VideoLibrary />} />
        <Route path="transcripts" element={<Transcription />} />
        <Route path="settings" element={<SettingsPage />} />
        {soon("analysis", "Analisis AI", "clip_detection", "Transkripsi (Whisper) dan deteksi klip viral dengan Qwen lokal.")}
        {soon("editor", "Editor Klip", "clip_editor", "Pratinjau, potong, bagi, gabung, timeline, dan undo/redo.")}
        {soon("subtitles", "Studio Subtitle", "subtitle_studio", "Subtitle per kata dengan highlight, preset, dan renderer ASS.")}
        <Route path="crop" element={<ClipStudio />} />
        <Route path="split" element={<Navigate to="/crop" replace />} />
        {soon("templates", "Template", "templates", "Simpan dan terapkan template pengeditan ke banyak klip.")}
        {soon("thumbnails", "Studio Thumbnail", "thumbnails", "Pembuatan thumbnail lokal dengan pemilihan frame berbasis wajah.")}
        {soon("renderer", "Batch Renderer", "batch_renderer", "Antrean persisten, rendering NVENC, jeda/lanjut/ulang.")}
        {soon("exports", "Export Center", "export_center", "Pratinjau, unduh, dan kelola hasil render.")}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
