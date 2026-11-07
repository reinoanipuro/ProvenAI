import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { Inspection } from '@/lib/api';
import { useCheckedDrawings } from '@/lib/checkerSession';
import { checkerFix, reportChanges, reportCounts } from '@/lib/presentation';
import { drawingSize, findingOverlay } from '@/lib/drawingOverlays';
import { revisionCloud } from '@/lib/redlineGeometry';
import drawing from '@/assets/rcrv-deck01-cabins.png.asset.json';
import { toast } from 'sonner';

export function DailyReport({ insp, previous, demo = true, printOnly = false }: { insp: Inspection; previous?: Inspection | undefined; demo?: boolean; printOnly?: boolean }) {
  const checks = useCheckedDrawings();
  const [engineer, setEngineer] = useState('');
  const today = new Date().toLocaleDateString('en-GB');
  const todays = checks.filter(row => new Date(row.at).toLocaleDateString('en-GB') === today);
  const counts = reportCounts(insp.results), changes = reportChanges(insp.results, previous?.results);
  const failures = [...insp.results].filter(r => r.status === 'FAIL').sort((a,b) => a.element_id === 'D-01-36-2' ? -1 : b.element_id === 'D-01-36-2' ? 1 : a.element_id.localeCompare(b.element_id));
  const regulations = [ ['ADA', 'ADA'], ['PVAG','PVAG'], ['COLREG','COLREG'], ['Load Line','Load Line'], ['DNV (demo placeholder)','DNV'] ];
  const summary = [`PROJECT ${insp.project} · ${today}`, `ENGINEER ${engineer || '—'} · ${new Set(todays.map(r => r.inspection.id)).size} drawings checked today`, `${counts.nonconform} nonconformities open · ${counts.unverified} need information · ${counts.ok} verified OK`, changes ? `Since ${insp.previous_revision?.label}: ${changes.fixed} fixed, ${changes.new} new (not a daily comparison)` : 'Previous-revision comparison unavailable', `Missing: ${insp.questions.map(q => `${q.label} (${q.resolves_count} checks)`).join('; ')}`].join('\n');
  return <article className={printOnly ? 'daily-report print-only' : 'daily-report'}>
    {!printOnly && <header className="report-toolbar no-print"><strong>REPORT · DAILY CHECKER'S SUMMARY</strong><Button variant="outline" onClick={() => window.print()}>PRINT / PDF</Button><Button variant="outline" onClick={async () => { try { await navigator.clipboard.writeText(summary); toast.success('Five-line summary copied'); } catch { toast.error('Clipboard unavailable'); } }}>COPY SUMMARY</Button></header>}
    <table className="report-title"><tbody><tr><th>PROJECT</th><td>{insp.project}</td><th>DATE</th><td>{new Date().toLocaleDateString('fi-FI')}</td></tr><tr><th>ENGINEER</th><td><Input aria-label="Engineer name" value={engineer} onChange={e => setEngineer(e.target.value)} className="no-print"/><span className="print-only">{engineer || '________________'}</span></td><th>DRAWINGS CHECKED TODAY</th><td>{new Set(todays.map(r => r.inspection.id)).size}</td></tr><tr><th>CHECKS APPLIED</th><td>{counts.checked}</td><th>UNIQUE RULES</th><td>{new Set(insp.results.map(r => r.check_id)).size}</td></tr></tbody></table>
    <div className="report-verdict">{counts.nonconform} NONCONFORMITIES OPEN · {counts.unverified} ITEMS NEED INFORMATION · {counts.ok} VERIFIED OK</div>
    <p className="font-mono text-xs">{changes ? `${changes.fixed} fixed, ${changes.new} new since ${insp.previous_revision?.label} · yesterday comparison not available` : 'YESTERDAY COMPARISON NOT AVAILABLE'}{demo && ' · ILLUSTRATIVE DEMO EVIDENCE'}</p>
    <h2>TODAY'S WORK</h2><table><thead><tr><th>DRAWING / INSPECTION</th><th>REVISION</th><th>TIME</th><th>NONCONFORM / NOT VERIFIED / OK</th></tr></thead><tbody>{todays.map((row,i) => { const c = reportCounts(row.inspection.results); return <tr key={i}><td>{row.inspection.name}</td><td>{row.inspection.id === insp.id ? 'J (test drawing)' : 'See inspection'}</td><td>{new Date(row.at).toLocaleTimeString('en-GB')}</td><td>{c.nonconform} / {c.unverified} / {c.ok}</td></tr>; })}{!todays.length && <tr><td colSpan={4}>No check run in this browser session today. Results below are the selected inspection.</td></tr>}</tbody></table>
    <h2>COMPLIANCE BY REGULATION</h2><table><thead><tr><th>REGULATION</th><th>CHECKED</th><th>OK</th><th>NONCONFORM</th><th>NOT VERIFIED</th><th /></tr></thead><tbody>{regulations.map(([label,prefix]) => { const rows = insp.results.filter(r => r.rule_set.startsWith(prefix ?? '')); const c = reportCounts(rows); return <tr key={label}><td>{label}</td><td>{c.checked}</td><td>{c.ok}</td><td>{c.nonconform}</td><td>{c.unverified}</td><td><div className="report-stack">{(['PASS','FAIL','UNKNOWN'] as const).map(status => <svg key={status} width={Math.round(rows.filter(r=>r.status===status).length / Math.max(1,c.checked)*100)} height="5"><rect width="100%" height="5" fill={`var(--${status==='PASS'?'pass':status==='FAIL'?'fail':'unknown'})`}/></svg>)}</div></td></tr>; })}</tbody></table>
    <h2>OPEN NONCONFORMITIES</h2>{failures.map((r,i) => { const box = findingOverlay(r.id,r.element_id); const b = box ? { x: box.x0*drawingSize.width, y: box.y0*drawingSize.height, w:(box.x1-box.x0)*drawingSize.width, h:(box.y1-box.y0)*drawingSize.height } : null; return <section className="report-finding" key={r.id}><div><strong>{i+1}. {r.element_id} · {r.clause_ref}</strong><p>{r.check_name}: {r.measured} {r.unit} · required {r.required} {r.unit}</p><p>PROPOSED FIX: {checkerFix(r)}</p></div>{b && <svg aria-label={`Redline crop ${i+1}`} viewBox={`${b.x-30} ${b.y-30} ${b.w+60} ${b.h+60}`}><image href={drawing.url} width={drawingSize.width} height={drawingSize.height} opacity=".55"/><path d={revisionCloud(b,12)} fill="var(--redline-fill)" stroke="var(--fail)" strokeWidth="3" vectorEffect="non-scaling-stroke"/></svg>}</section>; })}
    <h2>INFORMATION NEEDED</h2><table><thead><tr><th>INPUT</th><th>ELEMENTS</th><th>CHECKS RESOLVED</th><th>OWNER</th></tr></thead><tbody>{insp.questions.map(q => <tr key={q.attr}><td>{q.label} ({q.unit})</td><td>{q.element_ids.join(', ')}</td><td>{q.resolves_count}</td><td>{q.owner}</td></tr>)}</tbody></table>
    <table className="report-title report-signoff"><tbody><tr><th>CHECKED BY</th><td>ProvenAI · rule version not supplied · {demo ? 'Mistral local fixture (demo)' : 'model unverified'}</td></tr><tr><th>REVIEWED BY</th><td>________________</td></tr><tr><th>APPROVED BY</th><td>________________</td></tr></tbody></table>
  </article>;
}
