// The start page: drop a design document. It is checked, and the result page marks every
// issue in red on it, with a summary and step-by-step next steps.
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { api, qk } from "@/lib/api";
import { PageTitle } from "./AppShell";

const ACCEPTED = /\.(pdf|docx|txt|md|csv)$/i;

export function Home() {
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false), [sending, setSending] = useState(false), [error, setError] = useState("");
  const health = useQuery({ queryKey: ["health", ...qk.all()], queryFn: api.health, refetchInterval: 5000 });

  async function send(list: FileList | null) {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    const wrong = files.filter((file) => !ACCEPTED.test(file.name));
    if (wrong.length) { setError(`${wrong.map((f) => f.name).join(", ")}: drop a text document, a PDF with text, Word (.docx), TXT, MD or CSV.`); return; }
    setSending(true); setError("");
    try {
      const name = files.length === 1 ? files[0]!.name.replace(/\.[^.]+$/, "") : `${files.length} documents`;
      const { id } = await api.checkDocuments(name, files);
      await navigate({ to: "/inspections/$id", params: { id } });
    } catch {
      setError("The checker did not answer, so nothing was checked. Start it with start.ps1 (see above) and try again.");
    } finally { setSending(false); }
  }

  return <div className="mx-auto max-w-4xl">
    <PageTitle label="Design compliance check" title="Check a ship design" />
    <p className="mt-3 max-w-2xl text-[15px]">
      Drop a design document with the design values. Each value is checked against the regulations in the project,
      every issue is marked in red on the document, and you get a summary and the steps to take next.
    </p>

    <Connection running={health.data} />

    <input hidden ref={input} type="file" multiple accept=".pdf,.docx,.txt,.md,.csv" onChange={(e) => { void send(e.target.files); e.target.value = ""; }} />
    <button type="button" disabled={sending} data-over={over || undefined}
      className="sheet-drop mt-5 flex w-full flex-col items-center justify-center gap-2 px-6 py-14 text-center disabled:cursor-wait"
      onClick={() => input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); void send(e.dataTransfer.files); }}>
      <span className="sheet-title text-[20px]">{sending ? "Sending …" : "Drop the design document here"}</span>
      <span className="text-sm">or click to choose files</span>
      <span className="sheet-mono mt-2 text-xs text-[var(--muted-foreground)]">PDF WITH TEXT · DOCX · TXT · MD · CSV</span>
    </button>
    {error && <p role="alert" className="mt-3 border border-[var(--fail)] bg-[var(--card)] px-4 py-3 text-sm text-[var(--fail)]">{error}</p>}

    <table className="mt-8 w-full border-collapse border border-[var(--foreground)] bg-[var(--card)] text-sm">
      <tbody>
        {[
          ["01", "READ", "Mistral (local) finds the design values in the document's text."],
          ["02", "CHECK", "Python compares every value with the limit quoted from the regulation page. No AI decides pass or fail."],
          ["03", "ACT", "Issues are marked in red on your document, with the regulation page and the next steps."],
        ].map(([n, title, text]) => <tr key={n} className="border-b border-[var(--border)]">
          <td className="sheet-mono w-12 border-r border-[var(--border)] px-3 py-2 align-top">{n}</td>
          <td className="w-24 border-r border-[var(--border)] px-3 py-2 align-top font-semibold [font-family:var(--font-label)]">{title}</td>
          <td className="px-3 py-2">{text}</td>
        </tr>)}
      </tbody>
    </table>
  </div>;
}

function Connection({ running }: { running: boolean | undefined }) {
  if (running === undefined) return <p className="sheet-label mt-4">Looking for the checker …</p>;
  return running
    ? <p className="mt-4 flex items-center gap-2 text-sm"><span className="inline-block h-2.5 w-2.5 bg-[var(--pass)]" />Checker is running (Mistral and the regulation index are local).</p>
    : <div className="mt-4 border border-[var(--fail)] bg-[var(--card)] px-4 py-3 text-sm">
        <p className="flex items-center gap-2 font-semibold"><span className="inline-block h-2.5 w-2.5 bg-[var(--fail)]" />The checker is not running.</p>
        <p className="mt-1">Start it in PowerShell, in the project folder:</p>
        <code className="sheet-mono mt-1 block bg-[var(--muted)] px-2 py-1 text-xs">powershell -ExecutionPolicy Bypass -File start.ps1</code>
        <p className="mt-1 text-[var(--muted-foreground)]">This page notices by itself when it runs. Address: <Link className="underline" to="/settings">Settings</Link></p>
      </div>;
}
