// All API calls. Live mode talks to the on-premise REST API; demo mode (or any network error) uses src/lib/mockData.ts.
import { toast } from "sonner";
import { runTests } from "./rulesEngine";
import * as mock from "./mockData";
import { getSettings } from "./settings";
import type { Answer, Inspection, InspectionSummary, Rule, RuleSet } from "./types";
export * from "./types";
export { DEMO_ID } from "./mockData";

let lastWarn = 0;
const base = () => getSettings().apiUrl.replace(/\/$/, "");
export const isDemo = () => getSettings().demo;

async function call<T>(live: (b: string) => Promise<T>, demo: () => Promise<T>): Promise<T> {
  if (isDemo()) return demo();
  try {
    return await live(base());
  } catch (e) {
    if (Date.now() - lastWarn > 15000) {
      lastWarn = Date.now();
      toast.warning("API unreachable — showing demo data", { description: `${base()}: ${(e as Error).message}` });
    }
    return demo();
  }
}
async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json() as Promise<T>;
}
const post = <T,>(url: string, body: unknown) =>
  j<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  /** Not wrapped: the status indicator needs the real outcome. */
  async health(): Promise<{ ok: boolean; mode: "demo" | "live" }> {
    if (isDemo()) return { ok: true, mode: "demo" };
    try { await j(`${base()}/health`); return { ok: true, mode: "live" }; } catch { return { ok: false, mode: "live" }; }
  },
  ruleSets: () => call<RuleSet[]>((b) => j(`${b}/rulesets`), mock.listRuleSets),
  rules: () => call<Rule[]>((b) => j(`${b}/rules`), mock.listRules),
  proposeRule: (input: Parameters<typeof mock.proposeRule>[0]) =>
    call((b) => post<Awaited<ReturnType<typeof mock.proposeRule>>>(`${b}/rules`, input), () => mock.proposeRule(input)),
  approveRule: (rule: Rule) => call((b) => post<Rule>(`${b}/rules/${encodeURIComponent(rule.id)}/approve`, rule), () => mock.approveRule(rule)),
  inspections: () => call<InspectionSummary[]>((b) => j(`${b}/inspections`), mock.listInspections),
  inspection: (id: string) => call<Inspection>((b) => j(`${b}/inspections/${id}`), () => mock.getInspection(id)),
  createInspection: (name: string, files: File[], ruleSetIds: string[]) =>
    call<{ id: string }>(
      (b) => {
        const fd = new FormData();
        fd.append("name", name);
        files.forEach((f) => fd.append("files", f));
        ruleSetIds.forEach((r) => fd.append("ruleset_ids", r));
        return j(`${b}/inspections`, { method: "POST", body: fd });
      },
      () => mock.createInspection(name, files, ruleSetIds),
    ),
  submitAnswers: (id: string, answers: Answer[]) =>
    call<Inspection>((b) => post(`${b}/inspections/${id}/answers`, { answers }), () => mock.submitAnswers(id, answers)),
  markReviewed: (id: string, rid: string) =>
    call<Inspection>((b) => post(`${b}/inspections/${id}/results/${encodeURIComponent(rid)}/review`, {}), () => mock.markReviewed(id, rid)),
  addNote: (id: string, rid: string, note: string) =>
    call<Inspection>((b) => post(`${b}/inspections/${id}/results/${encodeURIComponent(rid)}/notes`, { note }), () => mock.addNote(id, rid, note)),
  /** URL of an original file for the drawing viewer; null in demo mode. */
  fileUrl: (id: string, fileId: string) => (isDemo() ? null : `${base()}/inspections/${id}/files/${fileId}`),
};

export const qk = {
  all: () => [getSettings().demo, getSettings().apiUrl] as const,
};

/** Import full Rule objects as proposals; imported approval claims are never trusted. */
export function parseRulePack(input: unknown): Rule[] {
  const rows = Array.isArray(input) ? input : input && typeof input === "object" && "rules" in input ? input.rules : null;
  if (!Array.isArray(rows) || !rows.length) throw new Error("Choose a JSON array of rules or an object with a rules array.");
  const ids = new Set<string>();
  return rows.map((row: unknown) => {
    if (!row || typeof row !== "object") throw new Error("Every rule must be an object.");
    const r = row as Rule;
    const strings = [r.id, r.rule_set_id, r.rule_set, r.name, r.clause_ref, r.clause_text, r.recommend_fail, r.missing_owner];
    if (strings.some((v) => typeof v !== "string" || !v.trim()) || !["door", "cabin", "corridor"].includes(r.applies_to) || !r.condition || ![">=", "<="].includes(r.condition.op) || !Number.isFinite(r.condition.value) || [r.condition.attr, r.condition.label, r.condition.unit, r.condition.deficit].some((v) => typeof v !== "string" || !v) || !Array.isArray(r.required_inputs) || !r.required_inputs.every((v) => typeof v === "string") || !r.required_inputs.includes(r.condition.attr) || !Array.isArray(r.tests) || !r.tests.length || r.tests.some((t) => !t || typeof t.name !== "string" || !["PASS", "FAIL", "UNKNOWN"].includes(t.expected) || !(t.input === null || t.input === "conflict" || typeof t.input === "number" && Number.isFinite(t.input)))) throw new Error("A rule is incomplete. Include its title, clause, condition, inputs and self-tests.");
    if (ids.has(r.id)) throw new Error("Each imported rule needs a unique ID.");
    ids.add(r.id);
    const draft: Rule = { ...r, status: "proposed" };
    return { ...draft, tests: runTests(draft) };
  });
}
