// In-memory RCRV demo fixtures; measurements remain illustrative, not newly extracted from the public image.
import { appliesTo, defaultTests, evaluate, formatCondition, requiredText, runTests, translateClause } from "./rulesEngine";
import type {
  Answer, Attr, AuditEvent, Inspection, InspectionFile, InspectionSummary, Question, Result, Rule, RuleSet, ShipElement,
} from "./types";

const GA = "RCRV-GA-6096-070-001-Rev-J-demo.pdf";
const SPEC = "Outfitting-spec_Accommodation_v3.docx";
const DOORS = "Door-schedule_D-01.xlsx";
const IFC = "RCRV_accommodation-demo.ifc";

export const ruleSets: RuleSet[] = [
  { id: "colreg-annex-i", name: "COLREG – Annex I", authority: "COLREG", description: "Navigation light checks — import an approved pack before use." },
  { id: "load-line-reg-12", name: "Load Line – Reg. 12", authority: "Load Line", description: "Door checks — import an approved pack before use." },
  { id: "dnv-acc", name: "DNV – Accommodation", authority: "DNV (placeholder)", description: "Crew accommodation space, headroom and floor area requirements." },
  { id: "ada-doors", name: "ADA – Doors", authority: "2010 ADA Standards", description: "Doors, doorways and gates on accessible routes (§404)." },
  { id: "pvag-acc", name: "PVAG – Accessibility", authority: "PVAG", description: "Passenger vessel accessibility: turning space and operable parts." },
];

const baseRules: Omit<Rule, "tests">[] = [
  {
    id: "ADA-404.2.3", rule_set_id: "ada-doors", rule_set: "ADA – Doors", name: "Door clear width",
    clause_ref: "ADA 2010 §404.2.3",
    clause_text: "Door openings shall provide a clear width of 32 inches (812.8 mm, rounded to 813 mm) minimum. Clear openings of doorways with swinging doors shall be measured between the face of the door and the stop, with the door open 90 degrees.",
    applies_to: "door",
    condition: { attr: "clear_width_mm", label: "Clear width", op: ">=", value: 813, unit: "mm", deficit: "too narrow" },
    required_inputs: ["clear_width_mm"],
    recommend_fail: "Widen {element} by at least {diff}.",
    missing_owner: "Outfitting / door supplier", status: "approved",
  },
  {
    id: "ADA-404.2.5", rule_set_id: "ada-doors", rule_set: "ADA – Doors", name: "Threshold (sill) height",
    clause_ref: "ADA 2010 §404.2.5",
    clause_text: "Thresholds, if provided at doorways, shall be ½ inch (13 mm) high maximum. Raised thresholds and changes in level at doorways shall comply with 302 and 303.",
    applies_to: "door",
    condition: { attr: "sill_height_mm", label: "Door sill height", op: "<=", value: 13, unit: "mm", deficit: "too high" },
    required_inputs: ["sill_height_mm"],
    recommend_fail: "Lower the sill of {element} by {diff} or provide a compliant bevelled ramp.",
    missing_owner: "Hull outfitting (door supplier datasheet)", status: "approved",
  },
  {
    id: "ADA-304.3.1", rule_set_id: "pvag-acc", rule_set: "PVAG – Accessibility", name: "Turning space (circular)",
    clause_ref: "ADA 2010 §304.3.1 (via PVAG)",
    clause_text: "The turning space shall be a space of 60 inches (1525 mm) diameter minimum. The space shall be permitted to include knee and toe clearance complying with 306.",
    applies_to: "cabin", accessible_only: true,
    condition: { attr: "turning_diameter_mm", label: "Turning circle diameter", op: ">=", value: 1525, unit: "mm", deficit: "too small" },
    required_inputs: ["turning_diameter_mm"],
    recommend_fail: "Rearrange furniture in {element} to free a {diff} larger turning circle.",
    missing_owner: "Interior designer (furnished cabin layout)", status: "approved",
  },
  {
    id: "PVAG-309.3", rule_set_id: "pvag-acc", rule_set: "PVAG – Accessibility", name: "Operable part height",
    clause_ref: "PVAG §309.3 / ADA 308.2.1",
    clause_text: "Operable parts shall be placed within one or more of the reach ranges; where a forward reach is unobstructed, the high forward reach shall be 48 inches (1220 mm) maximum above the finish floor.",
    applies_to: "door", accessible_only: true,
    condition: { attr: "handle_height_mm", label: "Door handle height", op: "<=", value: 1220, unit: "mm", deficit: "above reach range" },
    required_inputs: ["handle_height_mm"],
    recommend_fail: "Lower the handle of {element} by {diff}.",
    missing_owner: "Door supplier", status: "approved",
  },
  {
    id: "DNV-ACC-3.2.1", rule_set_id: "dnv-acc", rule_set: "DNV – Accommodation", name: "Cabin floor area (single berth)",
    clause_ref: "DNV (placeholder) Pt.6 Ch.8 Sec.3 [2.1]",
    clause_text: "The floor area of a single-berth sleeping room shall be not less than 4.5 m², measured excluding sanitary spaces.",
    applies_to: "cabin",
    condition: { attr: "floor_area_m2", label: "Floor area", op: ">=", value: 4.5, unit: "m²", deficit: "too small" },
    required_inputs: ["floor_area_m2"],
    recommend_fail: "Enlarge {element} by {diff} or reclassify the space.",
    missing_owner: "Naval architect (GA)", status: "approved",
  },
  {
    id: "DNV-ACC-3.1.4", rule_set_id: "dnv-acc", rule_set: "DNV – Accommodation", name: "Clear headroom",
    clause_ref: "DNV (placeholder) Pt.6 Ch.8 Sec.3 [1.4]",
    clause_text: "The minimum clear headroom in all accommodation spaces shall be not less than 2000 mm, measured to the underside of the deckhead lining.",
    applies_to: "cabin",
    condition: { attr: "headroom_mm", label: "Clear headroom", op: ">=", value: 2000, unit: "mm", deficit: "too low" },
    required_inputs: ["headroom_mm"],
    recommend_fail: "Raise the deckhead lining in {element} by {diff} or re-route ducting above.",
    missing_owner: "HVAC / outfitting coordination", status: "approved",
  },
];

let rules: Rule[] = baseRules.map((r) => ({ ...r, tests: defaultTests(r) })).map((r) => ({ ...r, tests: runTests(r) }));

const a = (value: number, unit: string, confidence: Attr["confidence"], quote: string, source_file: string, page: number | null, section: string, method: Attr["method"], conflicts?: Attr["conflicts"]): Attr =>
  ({ value, unit, confidence, quote, source_file, page, section, method, conflicts });

function demoElements(): ShipElement[] {
  return [
    {
      id: "CAB-01-31-2", type: "cabin", name: "Cabin 01-31-2", space: "01-31-2", deck: "Deck 1", page: 10, bbox: [380, 470, 560, 640],
      attrs: {
        floor_area_m2: a(6.8, "m²", "high", "Polyline area 6.80 m² (net, excl. WC 01-31-2W)", GA, 10, "Frame 36–41, PS", "Vector measurement"),
        headroom_mm: a(2100, "mm", "high", "CLR. HEADROOM 2100", GA, 10, "Section B-B detail 4", "OCR"),
      },
    },
    {
      id: "CAB-01-36-2", type: "cabin", name: "Cabin 01-36-2", space: "01-36-2", deck: "Deck 1", page: 10, bbox: [560, 470, 740, 640],
      attrs: {
        floor_area_m2: a(6.4, "m²", "high", "Polyline area 6.42 m² (net)", GA, 10, "Frame 41–46, PS", "Vector measurement"),
        headroom_mm: a(2100, "mm", "medium", "CLR. HEADROOM 2100 (typ.)", GA, 10, "Section B-B detail 4", "OCR", [
          a(1950, "mm", "high", "Cabin 01-36-2: deckhead lowered to 1950 mm clear due to ventilation duct Ø250", SPEC, 14, "§4.3.2 Deckheads", "Text"),
        ]),
      },
    },
    {
      id: "CAB-01-26-2", type: "cabin", name: "Cabin 01-26-2 (accessible)", space: "01-26-2", deck: "Deck 1", page: 10, bbox: [740, 470, 960, 640], accessible: true,
      attrs: {
        floor_area_m2: a(9.2, "m²", "high", "Polyline area 9.18 m² (net, excl. accessible WC)", GA, 10, "Frame 46–52, PS", "Vector measurement"),
        headroom_mm: a(2150, "mm", "high", "IfcSpace 01-26-2 Height = 2150", IFC, null, "IfcSpace GUID 2O2Fr$t4X7Zf8NOew3FLKr", "3D model"),
      },
    },
    {
      id: "D-01-31-2", type: "door", name: "Door D-01-31-2", space: "01-31-2", deck: "Deck 1", page: 10, bbox: [445, 455, 495, 485],
      attrs: { clear_width_mm: a(790, "mm", "low", "D-01-31-2 CLR 790 (smudged scan)", GA, 10, "Frame 38, corridor side", "Vector measurement") },
    },
    {
      id: "D-01-36-2", type: "door", name: "Door D-01-36-2", space: "01-36-2", deck: "Deck 1", page: 10, bbox: [625, 455, 675, 485],
      attrs: { clear_width_mm: a(700, "mm", "high", "Door clear opening 700 between stop and leaf face", GA, 10, "Door tag at frame 43", "OCR") },
    },
    {
      id: "D-01-26-2", type: "door", name: "Door D-01-26-2", space: "01-26-2", deck: "Deck 1", page: 10, bbox: [815, 455, 885, 485], accessible: true,
      attrs: {
        clear_width_mm: a(815, "mm", "high", "Row 14: D-01-26-2 | A-60 | clear opening 815 mm", DOORS, 1, "Sheet 'Deck 1', row 14", "Text"),
        handle_height_mm: a(950, "mm", "high", "Lever handle centreline 950 mm AFF", SPEC, 9, "§3.6 Door hardware", "Text"),
      },
    },
  ];
}

const demoFiles: InspectionFile[] = [
  { id: "f1", name: GA, size: 18_420_112, type: "application/pdf", pages: 24 },
  { id: "f2", name: SPEC, size: 1_204_880, type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  { id: "f3", name: DOORS, size: 88_310, type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  { id: "f4", name: IFC, size: 42_903_551, type: "application/x-step" },
];

interface Stored extends Inspection { _started: number; _reviews: Record<string, { reviewed?: boolean; notes: string[]; extra: AuditEvent[] }> }
const store = new Map<string, Stored>();

const STEP_MS = 1400;
const steps = ["Queued", "Ingesting documents", "Extracting evidence", "Evaluating rules", "Done"];

function addSec(iso: string, s: number) { return new Date(new Date(iso).getTime() + s * 1000).toISOString(); }

function evaluateAll(insp: Stored) {
  const active = rules.filter((r) => r.status === "approved" && insp.rule_set_ids.includes(r.rule_set_id));
  const results: Result[] = [];
  const t0 = insp.created_at;
  for (const r of active) for (const el of insp.elements) {
    if (!appliesTo(r, el)) continue;
    const ev = evaluate(r, el.attrs[r.condition.attr], el.name);
    const id = `${r.id}:${el.id}`;
    const rv = insp._reviews[id] ?? { notes: [], extra: [] };
    const audit: AuditEvent[] = [
      { at: addSec(t0, 2), actor: "ingest", event: `Ingested ${insp.files.length} files; ${GA} p.10 rasterised and vectorised` },
      ...ev.evidence.map((e, i) => ({
        at: addSec(t0, 9 + i * 2),
        actor: e.method === "Engineer input" ? "engineer" : "extractor · mistral-small (Ollama, local)",
        event: `Extracted ${r.condition.attr} = ${e.value} ${e.unit} from ${e.source_file}${e.page ? ` p.${e.page}` : ""} (${e.method}, ${e.confidence} confidence)`,
      })),
      ...(ev.missing.length ? [{ at: addSec(t0, 12), actor: "extractor · mistral-small (Ollama, local)", event: `No evidence found for ${r.condition.attr} in ${insp.files.length} files` }] : []),
      { at: addSec(t0, 15), actor: "rules-engine v1.4.2", event: `Evaluated ${formatCondition(r)} → ${ev.status}` },
      ...(ev.needs_review ? [{ at: addSec(t0, 15), actor: "rules-engine v1.4.2", event: "Flagged for human review (low confidence or conflicting sources)" }] : []),
      ...rv.extra,
    ];
    results.push({
      id, check_id: r.id, element_id: el.id, status: ev.status, needs_review: ev.needs_review && !rv.reviewed, reviewed: rv.reviewed, notes: rv.notes,
      rule_set: r.rule_set, clause_ref: r.clause_ref, clause_text: r.clause_text, check_name: r.name,
      condition: formatCondition(r), required_inputs: r.required_inputs, measured: ev.measured, required: requiredText(r), unit: r.condition.unit,
      confidence: ev.confidence, reason: ev.reason, recommendation: ev.recommendation, missing: ev.missing, evidence: ev.evidence, audit,
    });
  }
  const qmap = new Map<string, Question>();
  for (const res of results) for (const m of res.missing.length ? res.missing : res.status === "UNKNOWN" ? res.required_inputs : []) {
    const rule = rules.find((r) => r.id === res.check_id);
    if (!rule) continue;
    const q = qmap.get(m) ?? { attr: m, label: rule.condition.label, unit: rule.condition.unit, owner: rule.missing_owner, resolves_count: 0, element_ids: [], check_ids: [] };
    q.resolves_count++; if (!q.element_ids.includes(res.element_id)) q.element_ids.push(res.element_id); q.check_ids.push(res.id);
    qmap.set(m, q);
  }
  insp.results = results;
  insp.questions = [...qmap.values()].sort((x, y) => y.resolves_count - x.resolves_count);
}

function refresh(insp: Stored) {
  if (insp.status === "done") return;
  const step = Math.min(4, Math.floor((Date.now() - insp._started) / STEP_MS));
  insp.progress = { step, label: steps[step] ?? "" };
  insp.status = step >= 4 ? "done" : step === 0 ? "queued" : "running";
  if (insp.status === "done") evaluateAll(insp);
}

function seed() {
  if (store.size) return;
  const mk = (id: string, name: string, daysAgo: number, mut?: (els: ShipElement[]) => void) => {
    const els = demoElements(); mut?.(els);
    const s: Stored = {
      id, name, project: "RCRV Research Vessel · Deck 01", created_at: new Date(Date.now() - daysAgo * 864e5).toISOString(),
      status: "done", progress: { step: 4, label: "Done" }, rule_set_ids: ruleSets.map((r) => r.id), files: demoFiles, elements: els,
      results: [], questions: [], _started: 0, _reviews: {},
    };
    evaluateAll(s); store.set(id, s);
  };
  mk("rv60-rev-b", "GA Deck 1 accommodation — rev B", 21, (els) => {
    els.forEach((e) => { if (e.attrs["headroom_mm"]) delete e.attrs["headroom_mm"].conflicts; });
    const door = els.find((e) => e.id === "D-01-26-2");
    if (door?.attrs["clear_width_mm"]) door.attrs["clear_width_mm"].value = 760;
  });
  mk("rv60-rev-c", "GA Deck 1 accommodation — rev C", 9, (els) => { els.forEach((e) => { if (e.attrs["headroom_mm"]) delete e.attrs["headroom_mm"].conflicts; }); });
  mk(DEMO_ID, "RCRV Deck 01 cabins — rev J", 0.2);
  const c = store.get("rv60-rev-c"), d = store.get(DEMO_ID);
  if (c) c.previous_revision = { id: "rv60-rev-b", label: "rev B" };
  if (d) d.previous_revision = { id: "rv60-rev-c", label: "rev C" };
}
export const DEMO_ID = "rv60-rev-d";

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const strip = ({ _started, _reviews, ...rest }: Stored): Inspection => clone(rest);
const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms));

export async function health() { await delay(30); return { ok: true, version: "demo" }; }
export async function listRuleSets() { await delay(); return clone(ruleSets); }
export async function listRules() { await delay(); return clone(rules); }

export async function listInspections(): Promise<InspectionSummary[]> {
  seed(); await delay();
  return [...store.values()].map((s) => { refresh(s); return s; })
    .sort((x, y) => y.created_at.localeCompare(x.created_at))
    .map((s) => ({
      id: s.id, name: s.name, created_at: s.created_at, file_count: s.files.length, status: s.status,
      changes: s.previous_revision ? {
        previous_label: s.previous_revision.label,
        new_violations: s.results.filter((r) => r.status === "FAIL" && store.get(s.previous_revision?.id ?? "")?.results.find((old) => old.id === r.id)?.status !== "FAIL").length,
        fixed: s.results.filter((r) => r.status !== "FAIL" && store.get(s.previous_revision?.id ?? "")?.results.find((old) => old.id === r.id)?.status === "FAIL").length,
      } : undefined,
      counts: {
        pass: s.results.filter((r) => r.status === "PASS").length,
        fail: s.results.filter((r) => r.status === "FAIL").length,
        unknown: s.results.filter((r) => r.status === "UNKNOWN").length,
        review: s.results.filter((r) => r.needs_review).length,
      },
    }));
}

export async function getInspection(id: string): Promise<Inspection> {
  seed(); await delay(60);
  const s = store.get(id); if (!s) throw new Error(`Inspection ${id} not found`);
  refresh(s); return strip(s);
}

export async function createInspection(name: string, files: File[], ruleSetIds: string[]) {
  seed(); await delay(300);
  const id = `insp-${Date.now().toString(36)}`;
  const uploaded: InspectionFile[] = files.map((f, i) => ({ id: `u${i}`, name: f.name, size: f.size, type: f.type || "application/octet-stream" }));
  // Demo: uploaded files are analysed against the reference vessel model so the full flow is visible.
  const s: Stored = {
    id, name: name || "Untitled inspection", project: "RCRV Research Vessel · Deck 01", created_at: new Date().toISOString(),
    status: "queued", progress: { step: 0, label: "Queued" }, rule_set_ids: ruleSetIds,
    files: [...uploaded, ...demoFiles], elements: demoElements(), results: [], questions: [], _started: Date.now(), _reviews: {},
  };
  store.set(id, s); return { id };
}

export async function submitAnswers(id: string, answers: Answer[]) {
  await delay(250);
  const s = store.get(id); if (!s) throw new Error("not found");
  for (const ans of answers) {
    const el = s.elements.find((e) => e.id === ans.element_id); if (!el) continue;
    const rule = rules.find((r) => r.condition.attr === ans.attr);
    el.attrs[ans.attr] = {
      value: ans.value, unit: rule?.condition.unit ?? "", confidence: "high", quote: `Entered by engineer: ${ans.value} ${rule?.condition.unit ?? ""}`,
      source_file: "Manual entry", page: null, section: "Missing information form", method: "Engineer input",
    };
  }
  evaluateAll(s); return strip(s);
}

function rv(s: Stored, rid: string) { return (s._reviews[rid] ??= { notes: [], extra: [] }); }
export async function markReviewed(id: string, rid: string) {
  const s = store.get(id); if (!s) throw new Error("Inspection not found"); const r = rv(s, rid);
  r.reviewed = true; r.extra.push({ at: new Date().toISOString(), actor: "engineer", event: "Marked as reviewed" });
  evaluateAll(s); return strip(s);
}
export async function addNote(id: string, rid: string, note: string) {
  const s = store.get(id); if (!s) throw new Error("Inspection not found"); const r = rv(s, rid);
  r.notes.push(note); r.extra.push({ at: new Date().toISOString(), actor: "engineer", event: `Note: ${note}` });
  evaluateAll(s); return strip(s);
}

export async function proposeRule(input: { text: string; clause_ref: string; rule_set_id: string; applies_to: Rule["applies_to"]; name: string }) {
  await delay(500);
  const cond = translateClause(input.text);
  if (!cond) return { ok: false as const, error: "No measurable threshold with a comparison (minimum / maximum) was found in the text. Nothing was proposed." };
  const rs = ruleSets.find((r) => r.id === input.rule_set_id);
  if (!rs) return { ok: false as const, error: "Choose a rule pack before proposing a check." };
  const draft: Rule = {
    id: `${(rs.authority.split(" ")[0] ?? "RULE").toUpperCase()}-${input.clause_ref.replace(/[^\w.]+/g, "").slice(-12) || Date.now().toString(36)}`,
    rule_set_id: rs.id, rule_set: rs.name, name: input.name || cond.label, clause_ref: input.clause_ref, clause_text: input.text.trim(),
    applies_to: input.applies_to, condition: cond, required_inputs: [cond.attr], tests: defaultTests({ condition: cond }),
    recommend_fail: "Modify {element} by {diff} to comply.", missing_owner: "Responsible discipline", status: "proposed",
  };
  draft.tests = runTests(draft);
  return { ok: true as const, rule: draft };
}
export async function approveRule(rule: Rule) {
  await delay(200);
  const tested = { ...rule, tests: runTests(rule) };
  if (!tested.tests.length || tested.tests.some((t) => !t.passed)) throw new Error("Rule locked: every self-test must pass before approval.");
  rules = [...rules.filter((r) => r.id !== rule.id), { ...tested, status: "approved" }];
  return clone(rule);
}
