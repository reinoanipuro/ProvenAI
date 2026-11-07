import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Result, ShipElement } from "@/lib/api";
import { checkerMeasurement } from "@/lib/presentation";
export function EvidenceChain({ result: r, element, onClose, onReviewed, onNote }: {
  result: Result; element?: ShipElement | undefined; onClose: () => void; onReviewed: () => void; onNote: (n: string) => void;
}) {
  const [noteOpen, setNoteOpen] = useState(false), [note, setNote] = useState("");
  return <section className="properties-panel" aria-label="Finding properties">
    <header className="properties-heading"><span>PROPERTIES · {r.element_id} · {element?.space}</span><Button variant="ghost" onClick={onClose} aria-label="Close properties">×</Button></header>
    <div className="properties-body"><dl className="properties-grid">
      <dt>RULE</dt><dd>{r.rule_set} · {r.clause_ref}</dd>
      <dt>CLAUSE TEXT</dt><dd><blockquote>“{r.clause_text}”</blockquote><span className="font-mono text-xs">{r.clause_ref}</span></dd>
      <dt>CHECK</dt><dd className="font-mono">{r.check_name.toUpperCase()} · {r.condition} {r.unit}</dd>
      <dt>MEASURED</dt><dd className="font-mono">{checkerMeasurement(r)}</dd>
      <dt>SOURCE</dt><dd>{r.evidence.length ? r.evidence.map((e,i) => <details key={i}><summary>{e.source_file}{e.page ? ` · p.${e.page}` : ''}</summary><p>“{e.quote}”</p><p>{e.section}</p></details>) : "No source measurement"}</dd>
      <dt>METHOD</dt><dd>{r.evidence.map(e => e.method).join(' / ') || 'Not available'}</dd>
      <dt>CONFIDENCE</dt><dd>{r.confidence ?? 'Not available'}{r.evidence.length > 1 && ' · Conflicting sources, verify current measurement'}</dd>
      <dt>RESULT</dt><dd>{r.status} · {r.reason}</dd>
      <dt>FIX</dt><dd>{r.recommendation}</dd>
    </dl><details className="border-t pt-2"><summary>Audit trail · {r.audit.length} events</summary>{r.audit.map((a,i) => <p key={i} className="text-xs"><span className="font-mono">{new Date(a.at).toISOString().slice(0,19).replace('T',' ')}</span> · {a.actor} · {a.event}</p>)}</details>
    {r.notes?.map((n,i) => <p className="border-t py-1" key={i}>{n}</p>)}
    {noteOpen && <div className="flex gap-2 py-2"><Textarea aria-label="Review note" value={note} onChange={e => setNote(e.target.value)} rows={2} autoFocus/><Button variant="outline" disabled={!note.trim()} onClick={() => { onNote(note.trim()); setNote(''); setNoteOpen(false); }}>Save note</Button></div>}
    </div><footer className="flex shrink-0 justify-end gap-2 border-t"><Button variant="ghost" disabled={r.reviewed} onClick={onReviewed}>{r.reviewed ? 'Reviewed' : 'Mark reviewed'}</Button><Button variant="ghost" onClick={() => setNoteOpen(v => !v)}>Add note</Button></footer>
  </section>;
}
