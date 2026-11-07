// Deterministic rule evaluation. The AI never decides PASS/FAIL — only this code does.
import type { Attr, Confidence, Evidence, Rule, RuleTest, ShipElement, Status, TestInput } from "./types";

export interface Evaluation {
  status: Status;
  needs_review: boolean;
  measured: number | null;
  confidence: Confidence | null;
  reason: string;
  recommendation: string;
  missing: string[];
  evidence: Evidence[];
}

export const opSymbol = (op: ">=" | "<=") => (op === ">=" ? "≥" : "≤");
export const formatCondition = (r: Pick<Rule, "condition">) =>
  `${r.condition.attr} ${opSymbol(r.condition.op)} ${r.condition.value}`;
export const requiredText = (r: Pick<Rule, "condition">) =>
  `${opSymbol(r.condition.op)} ${r.condition.value}`;

const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0$/, ""));

export function evaluate(rule: Rule, attr: Attr | undefined, elementName: string): Evaluation {
  const c = rule.condition;
  if (!attr || attr.value === null || attr.value === undefined) {
    return {
      status: "UNKNOWN",
      needs_review: false,
      measured: null,
      confidence: null,
      reason: `No ${c.label.toLowerCase()} measurement was found in the source documents.`,
      recommendation: `Provide ${c.label.toLowerCase()} for ${elementName}.`,
      missing: [c.attr],
      evidence: [],
    };
  }
  const evidence: Evidence[] = [{ ...attr, attr: c.attr, conflicts: undefined } as Evidence];
  const conflicting = (attr.conflicts ?? []).filter((e) => e.value !== attr.value);
  if (conflicting.length) {
    const all = [attr, ...conflicting];
    evidence.push(...conflicting.map((e) => ({ ...e, attr: c.attr })));
    return {
      status: "UNKNOWN",
      needs_review: true,
      measured: null,
      confidence: attr.confidence,
      reason: `Sources disagree: ${all.map((e) => `${fmt(e.value as number)} ${e.unit} (${e.source_file})`).join(" vs ")}. The tool does not pick one.`,
      recommendation: `Confirm the correct ${c.label.toLowerCase()} with ${rule.missing_owner} and supersede the outdated document, then re-check.`,
      missing: [c.attr],
      evidence,
    };
  }
  const v = attr.value;
  const ok = c.op === ">=" ? v >= c.value : v <= c.value;
  const diff = Math.abs(v - c.value);
  const sym = ok ? (v === c.value ? "=" : c.op === ">=" ? ">" : "<") : c.op === ">=" ? "<" : ">";
  const lowConf = attr.confidence === "low";
  const reason = ok
    ? `${fmt(v)} ${c.unit} ${v === c.value ? "meets" : c.op === ">=" ? "is above" : "is below"} the required ${fmt(c.value)} ${c.unit} limit${v === c.value ? " exactly" : ` by ${fmt(diff)} ${c.unit}`}.`
    : `${fmt(v)} ${c.unit} is ${fmt(diff)} ${c.unit} ${c.op === ">=" ? "less" : "more"} than the required ${fmt(c.value)} ${c.unit}.`;
  return {
    status: ok ? "PASS" : "FAIL",
    needs_review: lowConf,
    measured: v,
    confidence: attr.confidence,
    reason,
    recommendation: ok
      ? "No action required."
      : rule.recommend_fail.replace("{element}", elementName).replace("{diff}", `${fmt(diff)} ${c.unit}`),
    missing: [],
    evidence,
  };
}

export const appliesTo = (rule: Rule, el: ShipElement) =>
  rule.applies_to === el.type && (!rule.accessible_only || !!el.accessible);

const testAttr = (rule: Rule, input: TestInput): Attr | undefined => {
  if (input === null) return undefined;
  const base: Attr = {
    value: input === "conflict" ? rule.condition.value : input,
    unit: rule.condition.unit, confidence: "high", quote: "test", source_file: "test", page: 1, section: "test", method: "Text",
  };
  if (input === "conflict") base.conflicts = [{ ...base, value: rule.condition.value - 1, source_file: "test-b" }];
  return base;
};

export function defaultTests(rule: Pick<Rule, "condition">): RuleTest[] {
  const { value, op } = rule.condition;
  const step = Number.isInteger(value) ? 1 : 0.1;
  const below = +(value - step).toFixed(2), above = +(value + step).toFixed(2);
  return [
    { name: "Exact boundary", input: value, expected: "PASS" },
    { name: "Just below limit", input: below, expected: op === ">=" ? "FAIL" : "PASS" },
    { name: "Just above limit", input: above, expected: op === ">=" ? "PASS" : "FAIL" },
    { name: "Missing evidence", input: null, expected: "UNKNOWN" },
    { name: "Contradictory sources", input: "conflict", expected: "UNKNOWN" },
  ];
}

export function runTests(rule: Rule): RuleTest[] {
  return rule.tests.map((t) => {
    const actual = evaluate(rule, testAttr(rule, t.input), "test element").status;
    return { ...t, actual, passed: actual === t.expected };
  });
}

/** Translate pasted regulation text into a proposed deterministic check. Returns null when no measurable threshold is found — never guesses. */
export function translateClause(text: string): Omit<Rule["condition"], never> | null {
  const t = text.toLowerCase();
  const num = t.match(/(\d+(?:[.,]\d+)?)\s*(mm|m²|m2|m|n|kg)\b/);
  if (!num) return null;
  let op: ">=" | "<=" | null = null;
  if (/(at least|minimum|not less than|no less than|≥|shall be min)/.test(t)) op = ">=";
  else if (/(maximum|not exceed|not more than|no more than|at most|≤)/.test(t)) op = "<=";
  if (!op) return null;
  const value = parseFloat((num[1] ?? "0").replace(",", "."));
  const raw = num[2] ?? "";
  const unit = raw === "m2" ? "m²" : raw === "n" ? "N" : raw;
  const map: [RegExp, string, string][] = [
    [/(threshold|sill)/, "sill_height", "Sill height"],
    [/(turning|diameter)/, "turning_diameter", "Turning diameter"],
    [/headroom/, "headroom", "Clear headroom"],
    [/(width|clear opening)/, "clear_width", "Clear width"],
    [/area/, "floor_area", "Floor area"],
    [/(handle|hardware)/, "handle_height", "Handle height"],
    [/force/, "opening_force", "Opening force"],
    [/height/, "height", "Height"],
  ];
  const hit: [RegExp, string, string] = map.find(([re]) => re.test(t)) ?? [/./, "value", "Value"];
  const suffix = unit === "m²" ? "m2" : unit.toLowerCase();
  return {
    attr: `${hit[1]}_${suffix}`,
    label: hit[2],
    op,
    value,
    unit,
    deficit: op === ">=" ? "below minimum" : "above maximum",
  };
}
