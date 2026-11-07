import { Link } from '@tanstack/react-router';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import type { Result, RuleSet, Status } from '@/lib/types';
import { headerStage } from '@/lib/headerPresentation';

export function CheckerHeader({ loaded = false, checked = false, running = false, results = [], packs = [], visibility = { FAIL: true, UNKNOWN: true, PASS: false }, onToggle, onLoad, onRun, onReview, title }: {
  loaded?: boolean; checked?: boolean; running?: boolean; results?: Result[]; packs?: RuleSet[];
  visibility?: Record<Status, boolean>; onToggle?: (status: Status) => void; onLoad?: () => void; onRun?: () => void; onReview?: () => void; title?: string | undefined;
}) {
  const stage = headerStage(loaded, checked, results);
  const failures = results.filter(result => result.status === 'FAIL').length;
  const authorities = [...new Set(packs.map(pack => pack.id.startsWith('ada') ? 'ADA' : pack.id.startsWith('dnv') ? 'DNV' : pack.authority))].join(' · ');
  const packLabels = authorities.split(' · ').filter(Boolean);
  const compactAuthorities = packLabels.length > 3 ? `${packLabels.slice(-3).join(' · ')} +${packLabels.length - 3}` : authorities;
  const labels = ['LOAD DRAWING', 'RUN CHECK', 'REVIEW NOTES', 'DAILY REPORT'];
  const current = { load: 0, run: 1, review: 2, report: 3 }[stage];
  const action = running ? 'CHECKING…' : stage === 'load' ? 'LOAD DRAWING' : stage === 'run' ? 'RUN CHECK ▸' : stage === 'review' ? `REVIEW ${failures} NONCONFORMITIES ▸` : 'SEND DAILY REPORT ▸';
  const hint = stage === 'load' ? 'Start with the RCRV test drawing' : stage === 'run' ? `${results.length} rules · ${compactAuthorities || 'Loading rule packs'}` : stage === 'review' ? 'N = next note' : 'Summary for your supervisor';
  return <header className="checker-header no-print">
    <section className="header-title" aria-label="Open drawing">
      <span className="header-eyebrow">VESSEL / DRAWING</span>
      <strong>{title ?? (loaded ? 'RCRV · GA 6096-070-001' : 'NO DRAWING LOADED')}</strong>
      <span className="header-revision">{loaded ? 'REV J · DECK 01 · 1/8" = 1\'-0"' : 'REV — · DECK — · SCALE —'}</span>
      <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" className="header-packs" title={authorities}>Checking against: {compactAuthorities || '—'} ▾</Button></DropdownMenuTrigger><DropdownMenuContent align="start">
        {packs.map(pack => <DropdownMenuItem asChild key={pack.id}><Link to="/rules">{pack.name}</Link></DropdownMenuItem>)}
        <DropdownMenuItem asChild><Link to="/rules">Rule library</Link></DropdownMenuItem>
        <DropdownMenuItem asChild><Link to="/" onClick={onLoad}>Load another drawing</Link></DropdownMenuItem>
        <DropdownMenuItem asChild><Link to="/inspections/new">New inspection</Link></DropdownMenuItem>
        <DropdownMenuItem asChild><Link to="/settings">Settings</Link></DropdownMenuItem>
      </DropdownMenuContent></DropdownMenu>
    </section>
    <section className={`header-workflow ${checked ? 'header-checked' : ''}`}>
      <nav className="header-steps" aria-label="Drawing checking workflow">{labels.map((label, i) => {
        const content = <><span className="step-number">{i < current ? '✓' : String(i + 1).padStart(2, '0')}</span><span className="step-label">{label}</span></>;
        const classes = `header-step ${i === current ? 'step-current' : i < current ? 'step-done' : 'step-future'}`;
        return i === 3 ? <Button key={label} variant="ghost" asChild className={classes}><Link to="/report" aria-current={i === current ? 'step' : undefined}>{content}</Link></Button> : <Button key={label} variant="ghost" className={classes} aria-current={i === current ? 'step' : undefined} disabled={running || (i > 0 && !loaded) || (i === 2 && !checked)} onClick={i === 0 ? onLoad : i === 1 ? onRun : onReview}>{content}</Button>;
      })}</nav>
      {checked && <div className="header-counters" aria-label="Show markup">{(['FAIL', 'UNKNOWN', 'PASS'] as const).map(status => <Button variant="ghost" key={status} className="header-counter" data-status={status} aria-pressed={visibility[status]} onClick={() => onToggle?.(status)}><span className="counter-value">{results.filter(result => result.status === status).length}</span><span>{status === 'FAIL' ? 'NONCONFORMITIES' : status === 'UNKNOWN' ? 'NOT VERIFIED' : 'OK'}</span></Button>)}</div>}
    </section>
    <section className="header-action">
      <nav aria-label="Workspace pages"><Button variant="link" asChild><Link to="/rules">RULES</Link></Button><span>·</span><Button variant="link" asChild><Link to="/history">HISTORY</Link></Button><span>·</span><Button variant="link" asChild><Link to="/report">REPORT</Link></Button></nav>
      {stage === 'report' || (stage === 'load' && !onLoad) ? <Button asChild className="header-primary"><Link to={stage === 'report' ? '/report' : '/'}><span key={action} className="primary-label">{action}</span></Link></Button> : <Button className="header-primary" disabled={running} onClick={stage === 'load' ? onLoad : stage === 'run' ? onRun : onReview}><span key={action} className="primary-label">{action}</span></Button>}
      <p>{hint}</p>
    </section>
  </header>;
}
