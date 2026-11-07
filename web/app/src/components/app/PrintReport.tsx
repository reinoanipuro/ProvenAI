import { StatusBadge } from "./Status";
import type { Inspection } from "@/lib/types";

export function PrintReport({ insp }: { insp: Inspection }) {
  const n = (s: string) => insp.results.filter((r) => r.status === s).length;
  return (
    <div className="print-only">
      <h1 style={{ fontSize: "16pt", fontWeight: 600 }}>ProvenAI compliance report — {insp.name}</h1>
      <p>{insp.project} · generated {new Date().toISOString().slice(0, 16).replace("T", " ")} UTC · {insp.results.length} checks: {n("PASS")} OK, {n("FAIL")} violations, {n("UNKNOWN")} cannot check</p>
      <p style={{ fontSize: "9pt", marginTop: 4 }}>AI extracted evidence only; all decisions were made by deterministic rules. UNKNOWN means evidence was missing or contradictory.</p>
      {insp.results.map((r) => (
        <section key={r.id} style={{ breakInside: "avoid", borderTop: "1px solid #999", padding: "8px 0" }}>
          <StatusBadge status={r.status} /> <b>{r.check_name}</b> — {r.element_id} · {r.clause_ref}
          <div style={{ fontStyle: "italic" }}>“{r.clause_text}”</div>
          <div style={{ fontFamily: "monospace" }}>{r.condition} — {r.reason}</div>
          {r.evidence.map((e, i) => <div key={i} style={{ fontSize: "9pt" }}>Evidence: {e.value} {e.unit} · “{e.quote}” · {e.source_file}{e.page ? ` p.${e.page}` : ""}, {e.section} · {e.method}, {e.confidence}</div>)}
          <div>Action: {r.recommendation}</div>
        </section>
      ))}
    </div>
  );
}
