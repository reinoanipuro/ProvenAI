import type { Result, Status } from "./api";

export const statusLabel: Record<Status, string> = { PASS: "OK", FAIL: "Violation", UNKNOWN: "Need more information" };

/** Presentation only: explain an existing engine decision without reevaluating it. */
export function drawingCallout(r: Result): string {
  if (r.status === "FAIL" && r.required_inputs[0] === "clear_width_mm" && r.measured !== null) {
    const minimum = Number(r.required.replace(/[^\d.]/g, ""));
    if (Number.isFinite(minimum)) return `Door ${minimum - r.measured} mm too narrow (${r.clause_ref.replace(" 2010", "")}). Fix: widen to ≥ ${minimum} mm.`;
  }
  return r.status === "UNKNOWN" ? `${findingTitle(r)}. Confirm the measurement to finish this check.` : r.reason;
}

export function findingTitle(r: Result): string {
  if (r.status === "UNKNOWN") return `${r.check_name.replace(/Clear /i, "")} ${r.evidence.length > 1 ? "has conflicting sources" : "unknown"}`;
  if (r.status === "PASS") return `${r.check_name} meets the rule`;
  const titles: Record<string, string> = {
    clear_width_mm: "Door too narrow", sill_height_mm: "Door sill too high",
    headroom_mm: "Cabin ceiling too low", floor_area_m2: "Cabin floor area too small",
    turning_diameter_mm: "Turning space too small", handle_height_mm: "Door handle too high",
  };
  return titles[r.required_inputs[0] ?? ""] ?? `${r.check_name} outside the limit`;
}

export function findingNumber(r: Result): string {
  if (r.status === "UNKNOWN") return r.evidence.length > 1 ? "Sources disagree — confirm the measurement" : "Measurement missing from drawing";
  return `${r.measured} ${r.unit} · ${r.status === "FAIL" ? "needs" : "required"} ${r.required.replace(/[≥≤<> =]/g, "")} ${r.unit}`;
}

export function revisionChange(result: Result, previous: Result[]): "New" | "Fixed" | "Unchanged" {
  const old = previous.find((r) => r.id === result.id);
  if (result.status === "FAIL" && old?.status !== "FAIL") return "New";
  if (result.status !== "FAIL" && old?.status === "FAIL") return "Fixed";
  return "Unchanged";
}
/** Terse checker notes format existing decisions, never decide compliance. */
export function checkerMeasurement(r: Result): string {
  if (r.status === "UNKNOWN") return r.evidence.length > 1 ? "CONFLICTING SOURCES" : "MEASUREMENT REQUIRED";
  return `${r.measured} ${r.status === "FAIL" ? ((r.condition.includes("<=") || r.condition.includes("≤")) ? ">" : "<") : " / "} ${r.required.replace(/[≥≤<> =]/g, "")} ${r.unit}`;
}
export function checkerFix(r: Result): string {
  if (r.status === "FAIL" && r.required_inputs[0] === "clear_width_mm" && r.measured !== null) {
    const minimum = Number(r.required.replace(/[^\d.]/g, ""));
    if (Number.isFinite(minimum)) return `Widen ≥ ${minimum - r.measured} mm`;
  }
  if (r.status === "UNKNOWN") return r.evidence.length > 1 ? "Verify current source measurement" : `Provide ${r.check_name.toLowerCase()} (${r.unit})`;
  return r.recommendation;
}

export function verifiedMeasurement(r: Result): string {
  return `${r.measured} ${r.condition.includes('<=') || r.condition.includes('≤') ? '≤' : '≥'} ${r.required.replace(/[≥≤<> =]/g, '')} ${r.unit}`;
}

/** Report aggregation uses existing engine verdicts and explicit revisions only. */
export function reportCounts(results: Result[]) {
  return { checked: results.length, ok: results.filter(r => r.status === 'PASS').length, nonconform: results.filter(r => r.status === 'FAIL').length, unverified: results.filter(r => r.status === 'UNKNOWN').length };
}
export function reportChanges(results: Result[], previous?: Result[]) {
  if (!previous) return null;
  return { fixed: results.filter(r => revisionChange(r, previous) === 'Fixed').length, new: results.filter(r => revisionChange(r, previous) === 'New').length };
}
export function ruleSection(rule: { clause_ref: string; rule_set_id: string }): string {
  if (rule.rule_set_id.startsWith('dnv')) return 'ACCOMMODATION · DEMO PLACEHOLDER';
  const clause = rule.clause_ref.match(/§(\d+)/)?.[1];
  const names: Record<string, string> = { '404': 'DOORS, DOORWAYS AND GATES', '304': 'TURNING SPACE', '309': 'OPERABLE PARTS' };
  return clause ? `${clause} ${names[clause] ?? 'REQUIREMENTS'}` : 'GENERAL REQUIREMENTS';
}
