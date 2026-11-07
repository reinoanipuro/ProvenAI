import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Play, Upload, X } from "lucide-react";
import { fileIcon, fmtSize } from "@/lib/files";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { InspectionStepper } from "@/components/app/InspectionStepper";
import { PageHeader } from "@/components/app/AppShell";
import { api, qk } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/inspections/new")({
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "New inspection — ProvenAI" },
      { name: "description", content: "Upload drawings, specs and models and choose rules to check against." },
      { property: "og:title", content: "New inspection — ProvenAI" },
      { property: "og:description", content: "Upload design documents and run a compliance check." },
    ],
  }),
  component: NewInspection,
});

function NewInspection() {
  const nav = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [sel, setSel] = useState<string[]>([]);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { data: sets } = useQuery({ queryKey: ["rulesets", ...qk.all()], queryFn: api.ruleSets });
  useEffect(() => { if (sets && !sel.length) setSel(sets.map((s) => s.id)); }, [sets]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = useMutation({
    mutationFn: () => api.createInspection(name, files, sel),
    onSuccess: ({ id }) => nav({ to: "/inspections/$id", params: { id } }),
  });
  const add = (fl: FileList | null) => {
    const uploaded = Array.from(fl ?? []);
    setFiles((f) => [...f, ...uploaded]);
  };

  return (
    <div>
      <InspectionStepper step={files.length ? 2 : 1} />
      <PageHeader title="New inspection" sub="Any file type: PDF drawings, scans, 3D/BIM exports, spreadsheets, JSON, text specifications." />
      <div className="grid grid-cols-[1fr_360px] gap-8 p-8">
        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground" htmlFor="iname">Inspection name</label>
            <Input id="iname" value={name} onChange={(e) => setName(e.target.value)} placeholder="GA Deck 1 accommodation — rev E" className="mt-1" />
          </div>
          <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }} onClick={() => input.current?.click()}
            className={cn("grid cursor-pointer place-items-center rounded-md border-2 border-dashed bg-card px-6 py-12 text-center transition-colors hover:border-primary/60", over && "border-primary bg-accent")}>
            <Upload className="h-6 w-6 text-muted-foreground" />
            <p className="mt-2 text-sm font-medium">Drop files here or click to browse</p>
            <p className="text-xs text-muted-foreground">Files stay on your network — processed by the on-premise service.</p>
            <input ref={input} type="file" multiple hidden onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          </div>
          {!!files.length && (
            <ul className="divide-y rounded-md border bg-card">
              {files.map((f, i) => {
                const I = fileIcon(f.name);
                return (
                  <li key={i} className="flex items-center gap-3 px-3 py-2 text-sm">
                    <I className="h-4 w-4 text-muted-foreground" />
                    <span className="flex-1 truncate font-mono text-xs">{f.name}</span>
                    <span className="font-mono text-xs text-muted-foreground tnum">{fmtSize(f.size)}</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`}><X className="h-3.5 w-3.5" /></Button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <aside className="space-y-4">
          <div className="rounded-md border bg-card">
            <div className="border-b px-4 py-2.5 text-sm font-medium">Choose rules</div>
            <ul className="divide-y">
              {sets?.map((s) => (
                <li key={s.id}>
                  <label className="flex cursor-pointer gap-3 px-4 py-3">
                    <Checkbox checked={sel.includes(s.id)} onCheckedChange={(c) => setSel((v) => (c ? [...v, s.id] : v.filter((x) => x !== s.id)))} className="mt-0.5" />
                    <span><span className="block text-sm font-medium">{s.name}</span><span className="block text-xs text-muted-foreground">{s.description}</span></span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
          <Button size="lg" className="w-full" disabled={!files.length || !sel.length || run.isPending} onClick={() => run.mutate()}>
            <Play className="h-4 w-4" />{run.isPending ? "Uploading…" : "Run check"}
          </Button>
          {!files.length && <p className="text-center text-xs text-muted-foreground">Add at least one file to start.</p>}
        </aside>
      </div>
    </div>
  );
}
