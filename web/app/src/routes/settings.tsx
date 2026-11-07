import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { PageHeader } from "@/components/app/AppShell";
import { api } from "@/lib/api";
import { setSettings, useSettings } from "@/lib/settings";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Settings — ProvenAI" },
      { name: "description", content: "Configure the on-premise API connection and demo data mode." },
      { property: "og:title", content: "Settings — ProvenAI" },
      { property: "og:description", content: "API connection, demo mode and deployment information." },
    ],
  }),
  component: SettingsPage,
});

function SettingsPage() {
  const s = useSettings();
  const [url, setUrl] = useState(s.apiUrl);
  return <div className="checker-document-page">
    <PageHeader title="Settings" />
    <div className="document-settings">
      <section className="settings-rule"><label htmlFor="api">API BASE URL</label><div className="flex min-w-0 gap-2"><Input id="api" value={url} onChange={e => setUrl(e.target.value)} className="font-mono min-w-0"/><Button variant="outline" onClick={async () => { setSettings({apiUrl:url}); const h=await api.health(); toast[h.ok || s.demo ? 'success' : 'warning'](s.demo ? 'Saved. Demo data active' : h.ok ? 'API connected' : 'Saved. API unreachable'); }}>Save & test</Button></div></section>
      <section className="settings-rule"><label>DEMO DATA</label><Switch checked={s.demo} onCheckedChange={demo => setSettings({demo})} aria-label="Use demo data"/></section>
      <section className="settings-rule"><label>DEPLOYMENT</label><dl className="properties-grid"><dt>MODEL</dt><dd>Mistral via Ollama. Local deployment configuration.</dd><dt>CHECK ENGINE</dt><dd>Versioned deterministic rules. Missing or conflicting evidence is UNKNOWN.</dd><dt>FALLBACK</dt><dd>Demo data when API is unreachable.</dd></dl></section>
    </div>
  </div>;
}
