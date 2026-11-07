export type Status = "PASS" | "FAIL" | "UNKNOWN";
export type Confidence = "high" | "medium" | "low";
export type Method = "OCR" | "Vector measurement" | "Text" | "3D model" | "Engineer input";
export type ElementType = "cabin" | "door" | "corridor";

export interface Evidence {
  attr?: string | undefined;
  value: number | null;
  unit: string;
  confidence: Confidence;
  quote: string;
  source_file: string;
  page: number | null;
  section: string;
  method: Method;
}
export interface Attr extends Evidence {
  /** Other sources reporting a different value for the same attribute. */
  conflicts?: Evidence[] | undefined;
}
export interface ShipElement {
  id: string;
  type: ElementType;
  name: string;
  space: string;
  deck: string;
  page: number;
  /** PDF points, origin bottom-left: [x0, y0, x1, y1] */
  bbox: [number, number, number, number];
  accessible?: boolean;
  attrs: Record<string, Attr>;
}
export interface AuditEvent { at: string; actor: string; event: string }
export interface Result {
  id: string;
  check_id: string;
  element_id: string;
  status: Status;
  needs_review: boolean;
  reviewed?: boolean | undefined;
  notes?: string[] | undefined;
  rule_set: string;
  clause_ref: string;
  clause_text: string;
  check_name: string;
  condition: string;
  required_inputs: string[];
  measured: number | null;
  required: string;
  unit: string;
  confidence: Confidence | null;
  reason: string;
  recommendation: string;
  missing: string[];
  evidence: Evidence[];
  audit: AuditEvent[];
}
export interface Question {
  attr: string;
  label: string;
  unit: string;
  owner: string;
  resolves_count: number;
  element_ids: string[];
  check_ids: string[];
}
export interface InspectionFile { id: string; name: string; size: number; type: string; pages?: number }
export type InspectionStatus = "queued" | "running" | "done" | "error";
export interface Inspection {
  id: string;
  name: string;
  project: string;
  created_at: string;
  status: InspectionStatus;
  progress: { step: number; label: string };
  rule_set_ids: string[];
  files: InspectionFile[];
  elements: ShipElement[];
  results: Result[];
  questions: Question[];
  previous_revision?: { id: string; label: string };
}
export interface InspectionSummary {
  id: string;
  name: string;
  created_at: string;
  file_count: number;
  status: InspectionStatus;
  changes?: { new_violations: number; fixed: number; previous_label: string } | undefined;
  counts: { pass: number; fail: number; unknown: number; review: number };
}
export interface RuleSet { id: string; name: string; authority: string; description: string }
export interface RuleCondition {
  attr: string;
  label: string;
  op: ">=" | "<=";
  value: number;
  unit: string;
  /** word used in the plain-language reason when violated, e.g. "too narrow" */
  deficit: string;
}
export type TestInput = number | null | "conflict";
export interface RuleTest { name: string; input: TestInput; expected: Status; actual?: Status; passed?: boolean }
export interface Rule {
  id: string;
  rule_set_id: string;
  rule_set: string;
  name: string;
  clause_ref: string;
  clause_text: string;
  applies_to: ElementType;
  accessible_only?: boolean;
  condition: RuleCondition;
  required_inputs: string[];
  tests: RuleTest[];
  recommend_fail: string;
  missing_owner: string;
  status: "approved" | "proposed";
}
export interface Answer { attr: string; element_id: string; value: number }
