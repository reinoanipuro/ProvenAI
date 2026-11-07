import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { CheckCircle2, Plus, Upload, ShieldCheck, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { PageHeader } from "@/components/app/AppShell";
import { StatusBadge } from "@/components/app/Status";
import { api, parseRulePack, qk, type Rule } from "@/lib/api";
import { formatCondition } from "@/lib/rulesEngine";
import { ruleSection } from "@/lib/presentation";
import { DEMO_ID } from "@/lib/api";
import { useCheckedDrawings } from "@/lib/checkerSession";
import { useSettings } from "@/lib/settings";

export const Route = createFileRoute("/rules")({
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Rule library — ProvenAI" },
      { name: "description", content: "Deterministic compliance rules translated from regulation text, each with edge-case self-tests." },
      { property: "og:title", content: "Rule library — ProvenAI" },
      { property: "og:description", content: "Regulation clauses translated into tested, human-approved checks." },
    ],
  }),
  component: Rules,
});

function TestsTable({ rule }: { rule: Rule }) {
  return (
    <table className="w-full text-xs">
      <thead className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
        <tr><th className="py-1.5">Test</th><th>Input</th><th>Expected</th><th>Actual</th><th /></tr>
      </thead>
      <tbody>
        {rule.tests.map((t) => (
          <tr key={t.name} className="border-t">
            <td className="py-1.5">{t.name}</td>
            <td className="font-mono">{t.input === null ? "missing" : t.input === "conflict" ? "2 sources disagree" : `${t.input} ${rule.condition.unit}`}</td>
            <td><StatusBadge status={t.expected} /></td>
            <td>{t.actual && <StatusBadge status={t.actual} />}</td>
            <td>{t.passed ? <CheckCircle2 className="h-4 w-4 text-pass" aria-label="passed" /> : <XCircle className="h-4 w-4 text-fail" aria-label="failed" />}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RuleBody({ rule }: { rule: Rule }) {
  return (
    <div className="space-y-5 text-sm">
      <section>
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Clause · {rule.clause_ref}</h3>
        <blockquote className="border-l-2 border-primary/50 pl-3 italic text-muted-foreground">“{rule.clause_text}”</blockquote>
      </section>
      <section>
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Deterministic check</h3>
        <code className="block rounded bg-muted px-2.5 py-1.5 font-mono">{formatCondition(rule)}</code>
        <p className="mt-1 text-xs text-muted-foreground">Applies to: {rule.applies_to}{rule.accessible_only ? " (accessible only)" : ""} · Inputs: <span className="font-mono">{rule.required_inputs.join(", ")}</span> · Missing or conflicting input ⇒ UNKNOWN</p>
      </section>
      <section>
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Edge-case self-tests</h3>
        <TestsTable rule={rule} />
      </section>
    </div>
  );
}

function AddRule({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const { data: sets } = useQuery({ queryKey: ["rulesets", ...qk.all()], queryFn: api.ruleSets });
  const [form, setForm] = useState({ text: "", clause_ref: "", rule_set_id: "ada-doors", applies_to: "door" as Rule["applies_to"], name: "" });
  const propose = useMutation({ mutationFn: () => api.proposeRule(form) });
  const approve = useMutation({
    mutationFn: (r: Rule) => api.approveRule(r),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rules"] }); toast.success("Rule approved and added to the library"); propose.reset(); onOpenChange(false); },
  });
  const res = propose.data;
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) propose.reset(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add rule from regulation text</DialogTitle>
          <DialogDescription>No code needed. The proposed check and its self-tests must be approved by an engineer before use.</DialogDescription>
        </DialogHeader>
        {!res?.ok ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Input placeholder="Clause reference, e.g. ADA 2010 §404.2.4.1" value={form.clause_ref} onChange={(e) => setForm({ ...form, clause_ref: e.target.value })} />
              <Input placeholder="Check name, e.g. Maneuvering clearance" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <select className="h-9 rounded-md border bg-background px-2 text-sm" value={form.rule_set_id} onChange={(e) => setForm({ ...form, rule_set_id: e.target.value })} aria-label="Rules">
                {sets?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              <select className="h-9 rounded-md border bg-background px-2 text-sm" value={form.applies_to} onChange={(e) => setForm({ ...form, applies_to: e.target.value as Rule["applies_to"] })} aria-label="Applies to">
                <option value="door">Door</option><option value="cabin">Cabin</option><option value="corridor">Corridor</option>
              </select>
            </div>
            <Textarea rows={5} placeholder="Paste the verbatim clause, e.g. “Corridors on accessible routes shall have a clear width of at least 915 mm.”" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
            {res && !res.ok && <p className="rounded border border-unknown/40 bg-unknown-soft px-3 py-2 text-sm text-unknown">{res.error}</p>}
            <div className="flex justify-end"><Button disabled={!form.text.trim() || !form.clause_ref.trim() || propose.isPending} onClick={() => propose.mutate()}>{propose.isPending ? "Translating…" : "Propose check"}</Button></div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm"><span className="rounded bg-muted px-2 py-1 text-xs font-medium text-muted-foreground">Proposed — awaiting approval</span>
              <span className="text-muted-foreground">{res.rule.tests.filter((t) => t.passed).length}/{res.rule.tests.length} self-tests passed</span></div>
            <RuleBody rule={res.rule} />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { propose.reset(); toast("Proposal rejected — nothing was added"); }}><XCircle className="h-4 w-4" />Reject</Button>
              <Button onClick={() => approve.mutate(res.rule)} disabled={approve.isPending || res.rule.tests.some((t) => !t.passed)}><ShieldCheck className="h-4 w-4" />Approve rule</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Rules() {
  useSettings();
  const { data } = useQuery({ queryKey: ["rules", ...qk.all()], queryFn: api.rules });
  const { data: packs } = useQuery({ queryKey: ["rulesets", ...qk.all()], queryFn: api.ruleSets });
  const [open, setOpen] = useState<Rule | null>(null);
  const checks = useCheckedDrawings();
  const latestId = checks.at(-1)?.inspection.id ?? DEMO_ID;
  const { data: latest } = useQuery({ queryKey:['inspection',latestId,...qk.all()], queryFn:()=>api.inspection(latestId) });
  const [adding, setAdding] = useState(false);
  const [imported, setImported] = useState<Rule[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const [importBusy, setImportBusy] = useState(false);
  const approvePack = async () => {
    setImportBusy(true);
    try { for (const rule of imported) await api.approveRule(rule); await qc.invalidateQueries({ queryKey: ["rules"] }); setImported([]); toast.success("Rules approved"); }
    catch (e) { toast.error((e as Error).message); }
    finally { setImportBusy(false); }
  };
  return (
    <div className="checker-document-page">
      <PageHeader title="Rules"
        actions={<><Button variant="outline" onClick={() => input.current?.click()}>Import rules</Button><Button onClick={() => setAdding(true)}>Add rule</Button></>} />
      <input ref={input} type="file" accept=".json,application/json" hidden onChange={async (e) => { const file = e.target.files?.[0]; e.target.value = ""; if (!file) return; try { setImported(parseRulePack(JSON.parse(await file.text()))); } catch (err) { toast.error((err as Error).message); } }} />
      <div className="rules-workspace">
        <nav className="rules-tree" aria-label="Regulation contents">{[...(packs ?? [])].sort((a,b)=>['ada-doors','pvag-acc','colreg-annex-i','load-line-reg-12','dnv-acc'].indexOf(a.id)-['ada-doors','pvag-acc','colreg-annex-i','load-line-reg-12','dnv-acc'].indexOf(b.id)).map(pack=>{
          const rules=(data??[]).filter(r=>r.rule_set_id===pack.id), tests=rules.flatMap(r=>r.tests);
          const sections=[...new Set(rules.map(ruleSection))];
          return <details key={pack.id}><summary><strong>{pack.id==='ada-doors'?'ADA 2010 STANDARDS':pack.name.toUpperCase()}</strong> · {rules.length} rules · {tests.filter(t=>t.passed).length}/{tests.length} self-tests pass<span className="tree-source">SOURCE {pack.authority} · EDITION {pack.id==='ada-doors'?'2010':'not supplied'} · {pack.id.startsWith('dnv')?'DEMO PLACEHOLDER · not yet loaded':rules.length?'EXCERPTS · full text not loaded':'NOT YET LOADED'}</span></summary>{sections.map(section=><details className="rule-section" key={section}><summary>{section} · {rules.filter(r=>ruleSection(r)===section).length} rules</summary>{rules.filter(r=>ruleSection(r)===section).map(r=><Button key={r.id} className="rule-tree-leaf" variant="ghost" aria-pressed={open?.id===r.id} onClick={()=>setOpen(r)}>{r.clause_ref} · {r.name} · {formatCondition(r)} · {r.tests.filter(t=>t.passed).length}/{r.tests.length} tests · {r.status}</Button>)}</details>)}{!rules.length&&<p className="p-2 text-xs">Not yet loaded. Import an approved regulation excerpt.</p>}</details>;
        })}</nav>
        <section className="rule-detail"><header className="properties-heading">RULE PROPERTIES</header>{open ? <div className="p-4"><h2 className="mb-3 font-mono text-sm">{open.id} · {open.name}</h2><RuleBody rule={open}/><h3 className="notes-ruled-heading mt-4">APPLIED IN LATEST CHECK · {latest?.name}</h3><table className="w-full text-xs"><thead><tr><th>ELEMENT</th><th>MEASURED</th><th>RESULT</th><th>PAGE / SOURCE</th></tr></thead><tbody>{latest?.results.filter(r=>r.check_id===open.id).map(r=><tr key={r.id}><td>{r.element_id}</td><td>{r.measured??'—'} {r.unit}</td><td><StatusBadge status={r.status}/></td><td>{r.evidence.map(e=>`${e.source_file}${e.page?` p.${e.page}`:''}`).join('; ')||'Evidence missing'}</td></tr>)}</tbody></table><p className="mt-3 text-xs text-muted-foreground">Clause page reference not supplied in this rule pack.</p></div> : <p className="p-4 text-sm">Select a rule.</p>}</section>
      </div>
      <Dialog open={!!imported.length} onOpenChange={(o) => { if (!o) setImported([]); }}><DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto"><DialogHeader><DialogTitle>Review imported rules</DialogTitle><DialogDescription>Rules stay locked until all tests pass and an engineer approves them.</DialogDescription></DialogHeader>{imported.map((r) => <section key={r.id} className="border-t py-2"><h2 className="mb-4 text-xl font-medium">{r.name}</h2><RuleBody rule={r} /></section>)}<Button variant="outline" disabled={importBusy || imported.some((r) => r.tests.some((t) => !t.passed))} onClick={approvePack}><ShieldCheck className="h-4 w-4" />Approve rules</Button></DialogContent></Dialog>
      <AddRule open={adding} onOpenChange={setAdding} />
    </div>
  );
}
