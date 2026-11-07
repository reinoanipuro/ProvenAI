import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { PageTitle } from "@/components/app/AppShell";
import { api } from "@/lib/api";
import { DEFAULT_SETTINGS, setSettings, useSettings } from "@/lib/settings";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings — ProvenAI" }, { name: "description", content: "Address of the ProvenAI checker." }] }),
  component: SettingsPage,
});

function SettingsPage() {
  const settings = useSettings();
  const [url, setUrl] = useState(settings.apiUrl);
  const [status, setStatus] = useState("");
  async function save(next: string) {
    setSettings({ apiUrl: next });
    setUrl(next);
    setStatus("Testing …");
    setStatus(await api.health() ? "Saved. The checker answered." : "Saved, but the checker did not answer at this address.");
  }
  return <div className="mx-auto max-w-3xl">
    <PageTitle label="ProvenAI" title="Settings" />
    <section className="sheet mt-4">
      <div className="sheet-heading">Checker address</div>
      <div className="space-y-3 p-4 text-sm">
        <p>The web app sends documents to the ProvenAI checker. It runs on this computer when started with start.ps1.</p>
        <div className="flex flex-wrap gap-2">
          <input aria-label="Checker address" value={url} onChange={(e) => setUrl(e.target.value)} className="sheet-mono min-w-0 flex-1 border border-[var(--foreground)] bg-[var(--card)] px-2 py-1 text-sm" />
          <button type="button" className="sheet-button" data-primary onClick={() => void save(url)}>Save and test</button>
          <button type="button" className="sheet-button" onClick={() => void save(DEFAULT_SETTINGS.apiUrl)}>Default</button>
        </div>
        {status && <p role="status">{status}</p>}
      </div>
    </section>
    <section className="sheet mt-4">
      <div className="sheet-heading">How results are decided</div>
      <table className="w-full border-collapse text-sm"><tbody>
        {[
          ["Reading", "Mistral (ministral-3:8b) via Ollama, on this computer. It only finds values in the text."],
          ["Deciding", "Python compares each value with the limit quoted from the regulation page. No AI decides pass or fail."],
          ["Regulations", "The PDFs in data/regulations, searched locally. Each result names the file and page."],
          ["Summary", "Written by Mistral and kept only if every number in it is in the results."],
        ].map(([label, text]) => <tr key={label} className="border-b border-[var(--border)]"><td className="sheet-label w-32 px-4 py-2 align-top">{label}</td><td className="px-4 py-2">{text}</td></tr>)}
      </tbody></table>
    </section>
  </div>;
}
