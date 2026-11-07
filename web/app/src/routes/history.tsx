import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/app/AppShell";
import { api, DEMO_ID, qk } from "@/lib/api";
import { useSettings } from "@/lib/settings";

export const Route = createFileRoute("/history")({
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Inspection history — ProvenAI" },
      { name: "description", content: "Past compliance inspections of ship design documents with PASS, FAIL and UNKNOWN counts." },
      { property: "og:title", content: "Inspection history — ProvenAI" },
      { property: "og:description", content: "Past compliance inspections of ship design documents." },
    ],
  }),
  component: History,
});

function History() {
  useSettings();
  const nav = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["inspections", ...qk.all()], queryFn: api.inspections, refetchInterval: 3000 });
  return (
    <div className="checker-document-page">
      <PageHeader title="History"
        actions={<>
          <Button variant="outline" onClick={() => nav({ to: "/inspections/$id", params: { id: DEMO_ID } })}>Load demo inspection</Button>
          <Button size="lg" asChild><Link to="/inspections/new">New inspection</Link></Button>
        </>} />
      <div className="p-8">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th><th className="px-4 py-2 font-medium">Date</th><th className="px-4 py-2 text-right font-medium">Files</th>
                <th className="px-4 py-2 text-right font-medium text-pass"><span className="inline-flex items-center gap-1">OK</span></th><th className="px-4 py-2 text-right font-medium text-fail"><span className="inline-flex items-center gap-1">Violation</span></th>
                <th className="px-4 py-2 text-right font-medium text-unknown"><span className="inline-flex items-center gap-1">Not verified</span></th><th className="px-4 py-2 font-medium">Change vs. previous revision</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && <tr><td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">Loading inspections…</td></tr>}
              {data?.map((i) => (
                <tr key={i.id} className="cursor-pointer border-t hover:bg-muted/50" onClick={() => nav({ to: "/inspections/$id", params: { id: i.id } })}>
                  <td className="px-4 py-2.5 font-medium"><Link to="/inspections/$id" params={{ id: i.id }} className="focus-visible:outline-2 focus-visible:outline-ring">{i.name}</Link><div className="font-mono text-[11px] text-muted-foreground">{i.id}</div></td>
                  <td className="px-4 py-2.5 font-mono text-xs tnum">{new Date(i.created_at).toISOString().slice(0, 16).replace("T", " ")}</td>
                  <td className="px-4 py-2.5 text-right font-mono tnum">{i.file_count}</td>
                  <td className="px-4 py-2.5 text-right font-mono tnum">{i.status === "done" ? i.counts.pass : "–"}</td>
                  <td className="px-4 py-2.5 text-right font-mono tnum">{i.status === "done" ? i.counts.fail : "–"}</td>
                  <td className="px-4 py-2.5 text-right font-mono tnum">{i.status === "done" ? i.counts.unknown : "–"}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{i.changes ? `+${i.changes.new_violations} new violation${i.changes.new_violations === 1 ? "" : "s"}, ${i.changes.fixed} fixed` : "First revision"}</td>
                  <td className="px-4 py-2.5 text-xs">
                    <span className={i.status === "done" ? "text-muted-foreground" : "font-medium text-primary"}>{i.status === "done" ? "Complete" : i.status === "error" ? "Error" : "Running…"}</span>
                  </td>
                </tr>
              ))}
              {!isLoading && !data?.length && <tr><td colSpan={8} className="p-8 text-center text-muted-foreground">Load the demo inspection or start a new inspection to see results.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
