import { Hammer } from "lucide-react";
import { Badge, PageHeader } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

/** Halaman untuk modul yang BELUM dibuat. Menyatakan statusnya dengan jelas, tanpa tombol/data palsu. */
export function ComingSoon({ title, capability, description }: { title: string; capability: string; description: string }) {
  const { data } = useAsync(api.health);
  const cap = data?.capabilities.find((c) => c.key === capability);
  return (
    <>
      <PageHeader title={title} subtitle={description} />
      <div className="card flex items-start gap-4">
        <Hammer className="mt-1 text-warn" />
        <div>
          <div className="mb-1 flex items-center gap-2 font-medium">Belum tersedia <Badge kind="warn">Fase {cap?.phase ?? "?"}</Badge></div>
          <p className="text-sm text-mute">
            Modul ini belum dikembangkan, jadi tidak ada fitur atau data simulasi di sini. Status modul dan fase pengerjaannya dicatat di
            <code className="mx-1 rounded bg-panel-2 px-1">DEVELOPMENT_STATUS.md</code>.
          </p>
        </div>
      </div>
    </>
  );
}
