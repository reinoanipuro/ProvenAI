// The result of one check: verdict, summary, the document with every issue marked in red,
// and numbered next steps for the engineer, each with its evidence and regulation page.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api, qk, type Inspection, type InspectionFile, type NextStep, type RegulationSource, type Result, type ShipElement, type Status, type StepKind } from "@/lib/api";
import { PageTitle } from "./AppShell";
import { PdfView, type Mark } from "./PdfView";

const STEPS = ["Queued", "Reading the documents", "Finding design values", "Checking the regulations", "Done"];
const COLOR: Record<Status, string> = { FAIL: "var(--fail)", UNKNOWN: "var(--unknown)", PASS: "var(--pass)" };
const RANK: Record<Status, number> = { FAIL: 0, UNKNOWN: 1, PASS: 2 };
const KIND: Record<StepKind, { label: string; color: string }> = {
  fix: { label: "Fix", color: "var(--fail)" },
  confirm: { label: "Confirm", color: "var(--unknown)" },
  check: { label: "Check", color: "var(--unknown)" },
  measure: { label: "Add value", color: "var(--unknown)" },
  recheck: { label: "Recheck", color: "var(--foreground)" },
  info: { label: "OK", color: "var(--pass)" },
};
const PDF = /\.pdf$/i;
const TEXT = /\.(txt|md|csv|docx)$/i;

/** One design value and every rule checked against it; several rule sets (ADA, PVAG) can check the same value. */
interface Group { id: string; status: Status; element: ShipElement | undefined; main: Result; results: Result[] }

function groupResults(insp: Inspection): Group[] {
  const elements = new Map(insp.elements.map((e) => [e.id, e]));
  const groups = new Map<string, Result[]>();
  for (const r of insp.results) {
    const key = `${r.element_id}|${r.required_inputs.join(",")}`;
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  return [...groups.entries()].map(([id, results]) => {
    const sorted = [...results].sort((a, b) => RANK[a.status] - RANK[b.status]);
    const main = sorted[0]!;
    return { id, status: main.status, element: elements.get(main.element_id), main, results: sorted };
  }).sort((a, b) => RANK[a.status] - RANK[b.status] || (a.element?.name ?? "").localeCompare(b.element?.name ?? ""));
}

const norm = (text: string) => text.toLowerCase().replace(/\s+/g, "");
const fileOf = (g: Group) => g.main.evidence[0]?.source_file ?? "";

export function ResultPage({ id }: { id: string }) {
  const { data: insp, error } = useQuery({
    queryKey: ["inspection", id, ...qk.all()],
    queryFn: () => api.inspection(id),
    refetchInterval: (q) => (q.state.data && (q.state.data.status === "error" || (q.state.data.status === "done" && !q.state.data.refining)) ? false : 1500),
  });
  return <>
    <Link to="/" className="sheet-noprint text-sm hover:underline">← Check another document</Link>
    {error ? <Notice title="The result could not be loaded.">The checker did not answer. Make sure it is running (start.ps1) and reload this page.</Notice>
      : !insp ? <p className="sheet-label mt-6">Loading …</p>
      : insp.status === "error" ? <Notice title="The check stopped with an error.">{insp.progress.label}</Notice>
      : insp.status !== "done" ? <Progress insp={insp} />
      : <Report insp={insp} />}
  </>;
}

function Progress({ insp }: { insp: Inspection }) {
  return <section className="sheet mt-4">
    <div className="sheet-heading"><span>Checking · {insp.name}</span><span className="sheet-spinner" aria-hidden /></div>
    <ol className="p-4 text-sm">
      {STEPS.slice(1).map((label, index) => {
        const step = index + 1, done = insp.progress.step > step, current = insp.progress.step === step;
        return <li key={label} className={`flex items-center gap-3 py-1.5 ${done || current ? "" : "text-[var(--muted-foreground)]"}`}>
          <span className="sheet-step-number">{done ? "✓" : step}</span>
          <span className={current ? "font-semibold" : ""}>{current ? insp.progress.label : label}</span>
        </li>;
      })}
    </ol>
    <p className="border-t border-[var(--border)] px-4 py-2 text-xs text-[var(--muted-foreground)]">The result is shown as soon as Python has checked the values. The AI summary follows a moment later. This page updates by itself.</p>
  </section>;
}

function Report({ insp }: { insp: Inspection }) {
  const groups = useMemo(() => groupResults(insp), [insp]);
  const byResult = useMemo(() => new Map(groups.flatMap((g) => g.results.map((r) => [r.id, g] as const))), [groups]);
  const steps = insp.next_steps ?? [];
  const fails = groups.filter((g) => g.status === "FAIL"), unknown = groups.filter((g) => g.status === "UNKNOWN"), passes = groups.filter((g) => g.status === "PASS");
  const files = insp.files.filter((f) => PDF.test(f.name) || TEXT.test(f.name));
  const [selected, setSelected] = useState<string | null>(null);
  const [openStep, setOpenStep] = useState<number | null>(null);
  const [showOk, setShowOk] = useState(false);
  const [fileId, setFileId] = useState<string | null>(null);
  const current = groups.find((g) => g.id === selected) ?? null;
  const file = files.find((f) => f.id === fileId) ?? files.find((f) => fails.some((g) => fileOf(g) === f.name)) ?? files[0];

  function select(group: Group | null) {
    setSelected(group?.id ?? null);
    const target = group && files.find((f) => f.name === fileOf(group));
    if (target) setFileId(target.id);
  }
  function toggleStep(step: NextStep) {
    const opening = openStep !== step.number;
    setOpenStep(opening ? step.number : null);
    select(opening ? byResult.get(step.result_ids[0] ?? "") ?? null : null);
  }
  function selectFromDocument(group: Group) {
    select(group);
    const step = steps.find((s) => s.result_ids.some((rid) => group.results.some((r) => r.id === rid)));
    setOpenStep(step?.number ?? null);
    if (!step) document.getElementById("passed-list")?.setAttribute("open", "");
  }
  const marked = groups.filter((g) => g.status !== "PASS" || showOk || g.id === selected);

  const verdict = fails.length ? { label: "Not compliant", text: `${fails.length} issue${fails.length > 1 ? "s" : ""} found`, color: "var(--fail)" }
    : !groups.length ? { label: "Nothing checked", text: "No design values with a matching rule were found", color: "var(--unknown)" }
    : unknown.length ? { label: "No issues found · review needed", text: `${unknown.length} value${unknown.length > 1 ? "s" : ""} could not be checked automatically`, color: "var(--unknown)" }
    : { label: "Compliant", text: "Every value that was found meets the regulations", color: "var(--pass)" };

  return <>
    <div className="mt-3"><PageTitle label="Check result" title={insp.name}>
      <table className="sheet-mono border-collapse text-xs"><tbody>
        <tr><td className="pr-3 text-[var(--muted-foreground)]">FILES</td><td>{insp.files.map((f) => f.name).join(", ")}</td></tr>
        {insp.duration_s != null && <tr><td className="pr-3 text-[var(--muted-foreground)]">CHECKED IN</td><td>{insp.duration_s} s</td></tr>}
        <tr><td className="pr-3 text-[var(--muted-foreground)]">DECIDED BY</td><td>Python rules · regulation quotes</td></tr>
      </tbody></table>
    </PageTitle></div>

    <section className="sheet mt-4 flex flex-wrap items-center justify-between gap-3 px-4 py-3" style={{ borderLeft: `8px solid ${verdict.color}` }}>
      <div><p className="sheet-title text-[22px]" style={{ color: verdict.color }}>{verdict.label}</p><p className="text-sm">{verdict.text}.</p></div>
      <div className="sheet-mono flex gap-4 text-sm">
        <span style={{ color: COLOR.FAIL }}>{fails.length} ISSUES</span><span style={{ color: COLOR.UNKNOWN }}>{unknown.length} TO CHECK</span><span style={{ color: COLOR.PASS }}>{passes.length} OK</span>
      </div>
      <button type="button" className="sheet-button sheet-noprint" onClick={() => window.print()}>Print report</button>
    </section>

    <Summary insp={insp} />

    <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <section className="sheet flex h-[78vh] min-h-[440px] flex-col overflow-hidden">
        <div className="flex items-stretch justify-between border-b border-[var(--foreground)] bg-[var(--background)]">
          <div role="tablist" className="flex min-w-0 overflow-x-auto">
            {files.map((f) => <button key={f.id} role="tab" aria-selected={f.id === file?.id} className="sheet-tab" onClick={() => setFileId(f.id)}>
              {f.name}{(() => { const n = fails.filter((g) => fileOf(g) === f.name).length; return n ? <span className="ml-1 text-[var(--fail)]">· {n}</span> : null; })()}
            </button>)}
            {!files.length && <span className="sheet-heading border-0">Document</span>}
          </div>
          <label className="sheet-noprint flex shrink-0 items-center gap-1 px-3 text-xs"><input type="checkbox" checked={showOk} onChange={(e) => setShowOk(e.target.checked)} />Show OK</label>
        </div>
        <p className="border-b border-[var(--border)] px-3 py-1.5 text-xs">
          <span style={{ color: COLOR.FAIL }}>■ issue</span> &nbsp; <span style={{ color: COLOR.UNKNOWN }}>■ to check</span>{showOk && <> &nbsp; <span style={{ color: COLOR.PASS }}>■ OK</span></>} &nbsp;· Click a mark to see why.
        </p>
        {!file ? <p className="p-4 text-sm">No file to show.</p>
          : TEXT.test(file.name) ? <TextDocument insp={insp} file={file} groups={marked} selected={selected} onSelect={selectFromDocument} />
          : <PdfDocument insp={insp} file={file} groups={marked} selected={selected} onSelect={selectFromDocument} />}
      </section>

      <div className="flex flex-col gap-4 lg:max-h-[78vh] lg:overflow-y-auto">
        <section className="sheet">
          <div className="sheet-heading"><span>What to do now</span><span className="sheet-mono font-normal">{steps.length} step{steps.length === 1 ? "" : "s"}</span></div>
          <ol>{steps.map((step) => <StepItem key={step.number} step={step} open={openStep === step.number} onToggle={() => toggleStep(step)}
            groups={[...new Set(step.result_ids.map((rid) => byResult.get(rid)).filter((g): g is Group => !!g))]} onShow={select} />)}</ol>
          {insp.refining && <p className="flex items-center gap-2 border-t border-[var(--border)] px-3 py-2 text-xs text-[var(--muted-foreground)]"><span className="sheet-spinner" />{insp.progress.label}. The steps update when it finishes.</p>}
        </section>
        <details id="passed-list" className="sheet" open={!!current && current.status === "PASS"}>
          <summary className="sheet-heading cursor-pointer"><span style={{ color: COLOR.PASS }}>Meets the regulations</span><span className="sheet-mono font-normal">{passes.length}</span></summary>
          {!passes.length ? <p className="p-3 text-sm text-[var(--muted-foreground)]">Nothing passed.</p> : <ul>{passes.map((g) => <li key={g.id} className="sheet-step" data-open={selected === g.id || undefined} style={{ ["--step-color" as string]: COLOR.PASS }}>
            <button type="button" onClick={() => select(selected === g.id ? null : g)}><span style={{ color: COLOR.PASS }}>✓</span><span className="min-w-0"><span className="block font-semibold">{g.element?.name ?? g.main.element_id}</span><span className="block text-sm">{shortName(g.main)} · <span className="sheet-mono">{measuredText(g)} (required {g.main.required} {g.main.unit})</span></span></span></button>
            {selected === g.id && <div className="px-3 pb-3"><Evidence group={g} onShow={select} /></div>}
          </li>)}</ul>}
        </details>
      </div>
    </div>
  </>;
}

function Summary({ insp }: { insp: Inspection }) {
  const summary = insp.summary;
  const ai = summary?.source === "mistral";
  return <section className="sheet mt-4">
    <div className="sheet-heading">
      <span>{ai ? "AI summary" : "Summary"}</span>
      <span className="flex items-center gap-2 text-xs font-normal normal-case tracking-normal">
        {ai ? "Written by Mistral (local) · every number checked by Python" : insp.refining ? <><span className="sheet-spinner" />Mistral is writing the AI summary …</> : "Written by Python from the results"}
      </span>
    </div>
    <p className="px-4 py-3 text-[15px] leading-relaxed">{summary?.text ?? "No summary."}</p>
    {summary?.note && <p className="border-t border-[var(--border)] px-4 py-2 text-xs text-[var(--muted-foreground)]">{summary.note}</p>}
  </section>;
}

function StepItem({ step, open, onToggle, groups, onShow }: { step: NextStep; open: boolean; onToggle: () => void; groups: Group[]; onShow: (g: Group) => void }) {
  const kind = KIND[step.kind];
  return <li className="sheet-step" data-open={open || undefined} style={{ ["--step-color" as string]: kind.color }}>
    <button type="button" onClick={onToggle} aria-expanded={open}>
      <span className="sheet-step-number">{step.number}</span>
      <span className="min-w-0 flex-1"><span className="sheet-tag" style={{ color: kind.color }}>{kind.label}</span><span className="mt-1 block font-semibold">{step.title}</span></span>
    </button>
    {open && <div className="space-y-3 px-3 pb-4 pl-[44px] text-sm">
      <p>{step.detail}</p>
      {groups.map((g) => <Evidence key={g.id} group={g} onShow={onShow} />)}
      {!groups.length && step.source?.filename && step.source.page != null && <RegulationPage source={step.source} />}
    </div>}
  </li>;
}

function Evidence({ group, onShow }: { group: Group; onShow: (g: Group) => void }) {
  const r = group.main, doc = r.evidence[0];
  return <div className="space-y-2">
    <table className="w-full border-collapse text-sm"><tbody>
      <Row label="Element">{group.element?.name ?? r.element_id}</Row>
      <Row label="Check">{shortName(r)}</Row>
      <Row label="Design"><span className="sheet-mono font-semibold" style={{ color: COLOR[group.status] }}>{measuredText(group)}</span></Row>
      {r.required && <Row label="Required"><span className="sheet-mono">{r.required} {r.unit}</span></Row>}
      {r.reason && <Row label="Python">{r.reason}</Row>}
    </tbody></table>
    {doc?.quote && <p><span className="sheet-label">In your document</span><br /><span className="sheet-mono text-[13px]">“{doc.quote}”</span> <span className="text-xs text-[var(--muted-foreground)]">{doc.source_file}{doc.page ? `, page ${doc.page}` : ""}</span>
      {" "}<button type="button" className="sheet-noprint text-xs underline" onClick={() => onShow(group)}>Show in the document</button></p>}
    <div><span className="sheet-label">Regulation</span>
      <ul className="mt-1 space-y-2">{group.results.map((rule) => <li key={rule.id}>
        <span className="font-semibold" style={{ color: COLOR[rule.status] }}>{rule.status === "FAIL" ? "Not met" : rule.status === "PASS" ? "Met" : "Not checked"}</span>
        {" · "}{rule.clause_ref.split(" · ")[0]}
        {(rule.sources ?? []).slice(0, rule.sources?.[0]?.closest ? 2 : 1).map((source, index) => source.filename && source.page != null ? <RegulationPage key={index} source={source} /> : null)}
      </li>)}</ul>
    </div>
  </div>;
}

function RegulationPage({ source }: { source: RegulationSource }) {
  const [shown, setShown] = useState(false);
  const url = source.page != null ? api.regulationPageUrl(source.filename, source.page, source.verified ? source.quote : "") : null;
  return <div className="mt-1 border border-[var(--border)] bg-[var(--card)]">
    <div className="flex flex-wrap items-center justify-between gap-2 px-2 py-1.5">
      <span className="text-xs"><span className="sheet-mono">{source.filename}</span> · <strong>page {source.page}</strong>{source.section ? ` · ${source.section}` : ""}
        <br /><span className="text-[var(--muted-foreground)]">{source.closest ? "Closest passage found: not a confirmed requirement" : source.verified ? "Quote confirmed word for word on this page" : "Quote not confirmed in the index"}</span></span>
      {url && <button type="button" className="sheet-button sheet-noprint h-7 px-2 text-[11px]" onClick={() => setShown(!shown)}>{shown ? "Hide page" : `Show page ${source.page}`}</button>}
    </div>
    {source.quote && <blockquote className="sheet-quote mx-2 mb-2 text-xs">{source.quote.length > 400 ? `${source.quote.slice(0, 400)} …` : source.quote}</blockquote>}
    {shown && url && <div className="border-t border-[var(--border)]">
      <a href={url} target="_blank" rel="noreferrer" title="Open the full page"><img src={url} alt={`${source.filename} page ${source.page}, the quote is highlighted`} className="block w-full" loading="lazy" /></a>
    </div>}
  </div>;
}

function PdfDocument({ insp, file, groups, selected, onSelect }: { insp: Inspection; file: InspectionFile; groups: Group[]; selected: string | null; onSelect: (g: Group) => void }) {
  // Marks only for values found in this file, at a known place.
  const placed = (e: ShipElement | undefined): e is ShipElement => !!e && e.bbox.some((v) => v !== 0) && Object.values(e.attrs).some((a) => a.source_file === file.name);
  const marks: Mark[] = groups.flatMap((g) => placed(g.element) ? [{ id: g.id, status: g.status, page: g.element.page, bbox: g.element.bbox }] : []);
  const missing = groups.filter((g) => g.status === "FAIL" && fileOf(g) === file.name && !placed(g.element)).length;
  return <>
    {missing > 0 && <p className="border-b border-[var(--border)] px-3 py-1 text-xs text-[var(--fail)]">{missing} issue{missing > 1 ? "s" : ""} could not be placed on the page; see the steps.</p>}
    <PdfView key={file.id} url={api.fileUrl(insp.id, file.id)} marks={marks} selected={selected} onSelect={(id) => { const g = groups.find((x) => x.id === id); if (g) onSelect(g); }} />
  </>;
}

function TextDocument({ insp, file, groups, selected, onSelect }: { insp: Inspection; file: InspectionFile; groups: Group[]; selected: string | null; onSelect: (g: Group) => void }) {
  const { data, error } = useQuery({ queryKey: ["file-text", insp.id, file.id, ...qk.all()], queryFn: () => api.fileText(insp.id, file.id) });
  const selectedLine = useRef<HTMLSpanElement>(null);
  useEffect(() => { selectedLine.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }, [selected, data]);
  // The value line of each finding: the last part of its quote, as the source line joins the label line with " | ".
  const mine = groups.filter((g) => fileOf(g) === file.name).map((g) => ({ g, parts: (g.main.evidence[0]?.quote ?? "").split(" | ").map(norm).filter((p) => p.length > 2) }));
  const findFor = (line: string) => {
    const n = norm(line);
    if (n.length < 3) return undefined;
    return mine.find(({ parts }) => parts.length && n.includes(parts[parts.length - 1]!))?.g ?? mine.find(({ parts }) => parts.slice(0, -1).some((p) => p === n))?.g;
  };
  if (error) return <p className="p-4 text-sm">The text of this file could not be loaded.</p>;
  if (!data) return <p className="sheet-label p-4">Loading …</p>;
  return <div className="min-h-0 flex-1 overflow-y-auto bg-[var(--card)] p-3">
    {data.pages.map((page, index) => <div key={index}>
      {page.text.split("\n").map((line, lineIndex) => {
        const g = findFor(line), isSelected = !!g && g.id === selected;
        return <span key={lineIndex} ref={isSelected ? selectedLine : undefined} className="sheet-doc-line" data-status={g?.status} data-selected={isSelected || undefined}
          onClick={g ? () => onSelect(g) : undefined} title={g ? `${g.main.check_name}: ${g.status === "FAIL" ? "not met" : g.status === "PASS" ? "met" : "to check"}` : undefined}>{line || " "}</span>;
      })}
    </div>)}
  </div>;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <tr className="border-b border-[var(--border)]"><td className="sheet-label w-24 py-1 pr-2 align-top">{label}</td><td className="py-1">{children}</td></tr>;
}

function shortName(r: Result) { return r.check_name.replace(/ on passenger vessels$/, ""); }
function measuredText(g: Group) {
  const r = g.main, attr = g.element?.attrs[r.required_inputs[0] ?? ""];
  if (attr?.value_text) return attr.value_text;
  return r.measured != null ? `${r.measured} ${r.unit}` : "not stated";
}

function Notice({ title, children }: { title: string; children: ReactNode }) {
  return <section className="sheet mt-4" style={{ borderLeft: "8px solid var(--fail)" }}><div className="sheet-heading">{title}</div><p className="p-4">{children}</p></section>;
}
