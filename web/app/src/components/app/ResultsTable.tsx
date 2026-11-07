import { useRef, useState } from "react";
import { Check, CircleHelp, X, ChevronDown, ChevronRight } from "lucide-react";
import type { Result, ShipElement } from "@/lib/api";
import { findingTitle, revisionChange } from "@/lib/presentation";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function ResultsTable({ results, elements, selectedId, onSelect, previous, showChanges, expandPassed = false }: {
  results: Result[]; elements: ShipElement[]; selectedId: string | null; onSelect: (r: Result) => void;
  previous?: Result[] | undefined; showChanges?: boolean; expandPassed?: boolean;
}) {
  const [passedOpen, setPassedOpen] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const groups = [{ status: "FAIL", label: "VIOLATIONS", icon: X, color: "text-fail" }, { status: "UNKNOWN", label: "NEED MORE INFORMATION", icon: CircleHelp, color: "text-unknown" }, { status: "PASS", label: "OK", icon: Check, color: "text-pass" }] as const;
  return <div ref={list} aria-label="Findings" onKeyDown={(e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const buttons = Array.from(list.current?.querySelectorAll<HTMLButtonElement>("button[data-finding]") ?? []);
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = Math.max(0, Math.min(buttons.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)));
    e.preventDefault(); buttons[next]?.focus();
  }}>
    {groups.map((group) => {
      const rows = results.filter((r) => r.status === group.status);
      if (!rows.length) return null;
      const open = group.status !== "PASS" || passedOpen || expandPassed;
      return <section key={group.status}>
        {group.status === "PASS" ? <Button variant="ghost" className="h-8 w-full justify-start rounded-none px-3 text-xs font-normal text-muted-foreground" onClick={() => setPassedOpen((v) => !v)} aria-expanded={open}>{open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}OK ({rows.length}){!open && " — collapsed"}</Button> : <h3 className="flex h-8 items-center px-3 text-xs font-normal text-muted-foreground">{group.label} ({rows.length})</h3>}
        {open && rows.map((r) => <Button key={r.id} data-finding={r.id} aria-pressed={selectedId === r.id} variant="ghost" onClick={() => onSelect(r)} className={cn("finding-row min-h-16 h-auto w-full items-start justify-start gap-2 whitespace-normal rounded-none border-l-[3px] border-l-transparent px-3 py-2 text-left font-normal", selectedId === r.id && "border-l-primary bg-accent hover:bg-accent")}>
          <span className={cn("mt-1 h-2 w-2 shrink-0 border border-current", group.color, r.status !== "UNKNOWN" && "bg-current")} aria-label={group.label} />
          <span className="min-w-0 flex-1"><span className="block text-sm leading-5">{findingTitle(r)}</span><span className="block text-xs leading-5 text-muted-foreground"><span>Cabin {elements.find((el) => el.id === r.element_id)?.space ?? r.element_id}</span> · <span className={r.status === "UNKNOWN" ? "font-sans" : "font-mono"}>{r.status === "UNKNOWN" ? (r.evidence.length > 1 ? "Conflicting measurements" : "Measurement missing") : `${r.measured} ${r.unit}, needs ${r.required} ${r.unit}`}</span>{showChanges && previous && <span className="ml-2 font-sans">{revisionChange(r, previous)}</span>}</span></span>
        </Button>)}
      </section>;
    })}
    {!results.length && <p className="px-3 py-8 text-sm text-muted-foreground">No checks match. Clear the search or status filter.</p>}
  </div>;
}
