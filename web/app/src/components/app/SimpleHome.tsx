// The start page: drop a 2D picture of a design or a design document. It is checked, and the result page
// marks every issue in red on it, with an AI summary and step-by-step next steps.
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { api, DEMO_ID, qk } from "@/lib/api";
import { setSettings, useSettings } from "@/lib/settings";

const ACCEPTED = /\.(pdf|docx|txt|md|csv|png|jpe?g|webp|bmp)$/i;

export function SimpleHome() {
  const settings = useSettings(), navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false), [sending, setSending] = useState(false), [error, setError] = useState("");
  const health = useQuery({ queryKey: ["health", ...qk.all()], queryFn: api.health, refetchInterval: 5000 });
  const connected = settings.demo || health.data?.ok === true;

  async function send(list: FileList | null) {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    const wrong = files.filter((file) => !ACCEPTED.test(file.name));
    if (wrong.length) { setError(`${wrong.map((f) => f.name).join(", ")}: drop a picture (PNG, JPG), a PDF, a Word file (.docx) or a text file.`); return; }
    if (settings.demo) { setError("Demo mode is on, so your file is not checked. Turn demo mode off above to check your own design."); return; }
    setSending(true); setError("");
    try {
      const name = files.length === 1 ? files[0]!.name.replace(/\.[^.]+$/, "") : `${files.length} documents`;
      const { id } = await api.checkDocuments(name, files);
      await navigate({ to: "/inspections/$id", params: { id } });
    } catch {
      setError("The checker did not answer, so nothing was checked. Start it with start.ps1 (see above) and try again.");
    } finally { setSending(false); }
  }

  return <div className="min-h-screen">
    <SimpleTopBar />
    <main className="mx-auto w-full max-w-4xl px-4 py-8">
      <div className="sheet-rule py-3">
        <p className="sheet-label">Design compliance check</p>
        <h1 className="sheet-title">Check a ship design</h1>
      </div>
      <p className="mt-3 max-w-2xl text-[15px]">
        Drop a 2D picture of the design or a document with the design values. The values are checked against the regulations in the project,
        every issue is marked in red, and you get a summary and the steps to take next.
      </p>

      <ConnectionStatus connected={connected} checking={health.isLoading} demo={settings.demo} />

      <input hidden ref={input} type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp,.bmp" onChange={(e) => { void send(e.target.files); e.target.value = ""; }} />
      <button type="button" disabled={sending} data-over={over || undefined}
        className="sheet-drop mt-5 flex w-full flex-col items-center justify-center gap-2 px-6 py-14 text-center disabled:cursor-wait"
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); void send(e.dataTransfer.files); }}>
        <span className="sheet-title text-[20px]">{sending ? "Sending …" : "Drop the design here"}</span>
        <span className="text-sm">or click to choose files</span>
        <span className="sheet-mono mt-2 text-xs text-[var(--muted-foreground)]">PICTURE PNG · JPG &nbsp;|&nbsp; DOCUMENT PDF · DOCX · TXT</span>
      </button>
      {error && <p role="alert" className="mt-3 border border-[var(--fail)] bg-[var(--card)] px-4 py-3 text-sm text-[var(--fail)]">{error}</p>}

      <table className="mt-8 w-full border-collapse border border-[var(--foreground)] bg-[var(--card)] text-sm">
        <tbody>
          {[
            ["01", "READ", "Text is read from the document, and from pictures with local OCR. Mistral (local) finds the design values."],
            ["02", "CHECK", "Python compares every value with the limit quoted from the regulation page. No AI decides pass or fail."],
            ["03", "ACT", "Issues are marked in red where they are on your design, with the regulation page and the next steps."],
          ].map(([n, title, text]) => <tr key={n} className="border-b border-[var(--border)]">
            <td className="sheet-mono w-12 border-r border-[var(--border)] px-3 py-2 align-top">{n}</td>
            <td className="w-24 border-r border-[var(--border)] px-3 py-2 align-top font-semibold [font-family:var(--font-label)]">{title}</td>
            <td className="px-3 py-2">{text}</td>
          </tr>)}
        </tbody>
      </table>
      {settings.demo && <p className="mt-6 text-sm"><Link className="underline" to="/inspections/$id" params={{ id: DEMO_ID }}>Open the example drawing</Link></p>}
    </main>
  </div>;
}

function ConnectionStatus({ connected, checking, demo }: { connected: boolean; checking: boolean; demo: boolean }) {
  if (demo) return <p className="mt-4 border border-[var(--unknown)] bg-[var(--card)] px-4 py-3 text-sm">
    <strong>Demo mode:</strong> shows example data only.{" "}
    <button type="button" className="underline" onClick={() => setSettings({ demo: false })}>Turn demo mode off</button> to check your own design.
  </p>;
  if (checking) return <p className="sheet-label mt-4">Looking for the checker …</p>;
  return connected
    ? <p className="mt-4 flex items-center gap-2 text-sm"><span className="inline-block h-2.5 w-2.5 bg-[var(--pass)]" />Checker is running (Mistral and the regulation index are local).</p>
    : <div className="mt-4 border border-[var(--fail)] bg-[var(--card)] px-4 py-3 text-sm">
        <p className="flex items-center gap-2 font-semibold"><span className="inline-block h-2.5 w-2.5 bg-[var(--fail)]" />The checker is not running.</p>
        <p className="mt-1">Start it in PowerShell, in the project folder:</p>
        <code className="sheet-mono mt-1 block bg-[var(--muted)] px-2 py-1 text-xs">powershell -ExecutionPolicy Bypass -File start.ps1</code>
        <p className="mt-1 text-[var(--muted-foreground)]">This page notices by itself when it runs. Address: <Link className="underline" to="/settings">Settings</Link></p>
      </div>;
}

export function SimpleTopBar() {
  return <header className="sheet-noprint border-b border-[var(--foreground)] bg-[var(--card)]">
    <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2">
      <Link to="/" className="flex items-center gap-2"><img src="/logo.png" alt="" className="h-7 w-7" /><span className="sheet-title text-[17px]">ProvenAI</span></Link>
      <nav className="flex gap-5 text-[13px] uppercase tracking-wide [font-family:var(--font-label)]">
        <Link to="/" className="hover:underline">New check</Link>
        <Link to="/history" className="hover:underline">Earlier checks</Link>
        <Link to="/settings" className="hover:underline">Settings</Link>
      </nav>
    </div>
  </header>;
}
