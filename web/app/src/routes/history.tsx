import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageTitle } from "@/components/app/AppShell";
import { api, qk } from "@/lib/api";

export const Route = createFileRoute("/history")({
  head: () => ({ meta: [
    { title: "Earlier checks — ProvenAI" },
    { name: "description", content: "Earlier design checks with their issues and values to check." },
  ] }),
  component: History,
});

function History() {
  const { data, isLoading, error } = useQuery({ queryKey: ["inspections", ...qk.all()], queryFn: api.inspections, refetchInterval: 5000 });
  const checks = [...(data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return <>
    <PageTitle label="Design compliance check" title="Earlier checks" />
    <table className="sheet mt-4 w-full border-collapse text-sm">
      <thead><tr className="sheet-label border-b border-[var(--foreground)] bg-[var(--background)] text-left">
        <th className="px-3 py-2 font-semibold">Document</th><th className="px-3 py-2 font-semibold">Checked</th>
        <th className="px-3 py-2 text-right font-semibold" style={{ color: "var(--fail)" }}>Issues</th>
        <th className="px-3 py-2 text-right font-semibold" style={{ color: "var(--unknown)" }}>To check</th>
        <th className="px-3 py-2 text-right font-semibold" style={{ color: "var(--pass)" }}>OK</th>
        <th className="px-3 py-2 font-semibold">Status</th>
      </tr></thead>
      <tbody>
        {isLoading && <tr><td colSpan={6} className="px-3 py-6 text-center text-[var(--muted-foreground)]">Loading …</td></tr>}
        {error && <tr><td colSpan={6} className="px-3 py-6 text-center">The checker did not answer. Start it with start.ps1.</td></tr>}
        {!isLoading && !error && !checks.length && <tr><td colSpan={6} className="px-3 py-6 text-center text-[var(--muted-foreground)]">No checks yet. <Link to="/" className="underline">Check a document</Link>.</td></tr>}
        {checks.map((check) => {
          const done = check.status === "done";
          return <tr key={check.id} className="border-t border-[var(--border)] hover:bg-[var(--background)]">
            <td className="px-3 py-2"><Link to="/inspections/$id" params={{ id: check.id }} className="font-semibold underline-offset-2 hover:underline">{check.name}</Link></td>
            <td className="sheet-mono px-3 py-2 text-xs">{check.created_at.slice(0, 16).replace("T", " ")}</td>
            <td className="sheet-mono px-3 py-2 text-right">{done ? check.counts.fail : "–"}</td>
            <td className="sheet-mono px-3 py-2 text-right">{done ? check.counts.unknown : "–"}</td>
            <td className="sheet-mono px-3 py-2 text-right">{done ? check.counts.pass : "–"}</td>
            <td className="px-3 py-2 text-xs">{done ? "Done" : check.status === "error" ? "Error" : "Checking …"}</td>
          </tr>;
        })}
      </tbody>
    </table>
  </>;
}
