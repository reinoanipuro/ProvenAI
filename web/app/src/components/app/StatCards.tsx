import type { Result } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function StatCards({ results, updated = 0, activeStatus, onStatus }: { results: Result[]; source?: string; updated?: number; activeStatus?: string; onStatus?: (status: string) => void }) {
  const counts = [{ status: "FAIL", label: "violations", color: "text-fail" }, { status: "UNKNOWN", label: "need more information", color: "text-unknown" }, { status: "PASS", label: "OK", color: "text-pass" }];
  return <section key={updated} aria-label="Inspection verdict" aria-live="polite" className={cn("flex flex-wrap items-center gap-1", updated > 0 && "verdict-updated")}>
    {counts.map((c, i) => <span key={c.status} className="inline-flex items-center gap-1">{i > 0 && <span aria-hidden className="text-xl text-muted-foreground">·</span>}<Button variant="ghost" aria-pressed={activeStatus === c.status} onClick={() => onStatus?.(c.status)} className={cn("h-auto whitespace-normal px-2 py-1 text-left text-xl font-medium", c.color, activeStatus === c.status && "bg-accent")}>
      {results.filter((r) => r.status === c.status).length} {c.label}
    </Button></span>)}
  </section>;
}
