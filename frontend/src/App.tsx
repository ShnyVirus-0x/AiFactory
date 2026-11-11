import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { ComingSoon } from "./pages/ComingSoon";
import { ClipStudio } from "./pages/ClipStudio";
import { ClipEditor } from "./pages/ClipEditor";
import { Analysis } from "./pages/Analysis";
import { Dashboard } from "./pages/Dashboard";
import { Projects } from "./pages/Projects";
import { SettingsPage } from "./pages/SettingsPage";
import { Transcription } from "./pages/Transcription";
import { VideoLibrary } from "./pages/VideoLibrary";
import { Renderer } from "./pages/Renderer";
import { Exports } from "./pages/Exports";

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
        <Route path="analysis" element={<Analysis />} />
        <Route path="editor" element={<ClipEditor />} />
        {soon("subtitles", "Studio Subtitle", "subtitle_studio", "Subtitle per kata dengan highlight, preset, dan renderer ASS.")}
        <Route path="crop" element={<ClipStudio />} />
        <Route path="split" element={<Navigate to="/crop" replace />} />
        {soon("templates", "Template", "templates", "Simpan dan terapkan template pengeditan ke banyak klip.")}
        {soon("thumbnails", "Studio Thumbnail", "thumbnails", "Pembuatan thumbnail lokal dengan pemilihan frame berbasis wajah.")}
        <Route path="renderer" element={<Renderer />} />
        <Route path="exports" element={<Exports />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
