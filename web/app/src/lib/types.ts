export type Status = "PASS" | "FAIL" | "UNKNOWN";
export type Confidence = "high" | "medium" | "low";
// The shapes the checker (backend/lovable.py) returns.
export type Method = "Text" | "Engineer input";
export type ElementType = "cabin" | "door" | "corridor";

export interface Evidence {
  attr?: string | undefined;
  value: number | null;
  unit: string;
  /** The value as written in the design, such as "1:12" or "800 mm". */
  value_text?: string | undefined;
  /** Where this value is printed on its PDF page, PDF points from the bottom left. */
  bbox?: [number, number, number, number] | null | undefined;
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
  /** Regulation passages the result is based on: file, page and the quoted text. */
  sources?: RegulationSource[] | undefined;
  audit: AuditEvent[];
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
  /** Python's summary at first, replaced by Mistral's once its numbers are checked. */
  summary?: { text: string; source: "mistral" | "python"; note?: string } | null;
  next_steps?: NextStep[];
  warnings?: string[];
  /** True while Mistral writes the summary and reads regulations after the result is shown. */
  refining?: boolean;
  duration_s?: number;
}
export interface InspectionSummary {
  id: string;
  name: string;
  created_at: string;
  file_count: number;
  status: InspectionStatus;
  counts: { pass: number; fail: number; unknown: number };
}
export interface RegulationSource {
  filename: string;
  page: number | null;
  section: string;
  quote: string;
  /** The quote was confirmed word for word on the regulation page. */
  verified: boolean;
  /** Only the closest passage found, not a confirmed requirement. */
  closest: boolean;
}
export type StepKind = "fix" | "confirm" | "check" | "measure" | "recheck" | "info";
export interface NextStep {
  number: number;
  kind: StepKind;
  title: string;
  detail: string;
  result_ids: string[];
  element_id: string | null;
  source: RegulationSource | null;
}
