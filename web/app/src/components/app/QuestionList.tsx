import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Answer, Question, ShipElement } from "@/lib/types";

export function QuestionList({ questions, elements, onRecheck, busy }: {
  questions: Question[]; elements: ShipElement[]; onRecheck: (a: Answer[]) => void; busy: boolean;
}) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const pending = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  useEffect(() => () => { pending.current.forEach(clearTimeout); }, []);
  const submit = (q: Question, id: string, raw: string) => {
    const key = `${q.attr}:${id}`;
    const old = pending.current.get(key); if (old) clearTimeout(old);
    if (!raw.trim() || !Number.isFinite(Number(raw)) || Number(raw) < 0) return;
    pending.current.set(key, setTimeout(() => { onRecheck([{ attr: q.attr, element_id: id, value: Number(raw) }]); pending.current.delete(key); }, 650));
  };
  if (!questions.length)
    return <div className="border-b py-2 text-sm">ALL MEASUREMENTS AVAILABLE</div>;
  const sorted = [...questions].sort((a, b) => b.resolves_count - a.resolves_count);
  return (
    <ol className="space-y-0">
      {sorted.map((q, i) => {
        const answers: Answer[] = q.element_ids
          .map((id) => ({ attr: q.attr, element_id: id, value: parseFloat(vals[`${q.attr}:${id}`] ?? "") }))
          .filter((a) => Number.isFinite(a.value));
        return (
          <li key={q.attr} className="border-b py-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex gap-2">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded bg-unknown-soft font-mono text-xs font-semibold text-unknown">{i + 1}</span>
                <div>
                  <div className="font-medium">{q.label}</div>
                  <div className="text-xs text-muted-foreground">Resolves <b className="font-mono text-foreground">{q.resolves_count}</b> check{q.resolves_count > 1 ? "s" : ""} · Ask: {q.owner}</div>
                </div>
              </div>
              <Button size="sm" variant="outline" disabled={!answers.length || busy} onClick={() => onRecheck(answers)}>
                Re-check{answers.length ? ` (${answers.length})` : ""}
              </Button>
            </div>
            <div className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
              {q.element_ids.map((id) => {
                const el = elements.find((e) => e.id === id);
                return (
                  <label key={id} className="flex items-center gap-2 border-b px-2 py-1">
                    <span className="min-w-0 flex-1 truncate font-mono text-xs" title={el?.name}>{id}</span>
                    <Input type="number" inputMode="decimal" className="h-7 w-20 text-right font-mono text-xs" placeholder="—"
                      value={vals[`${q.attr}:${id}`] ?? ""} min={0} onChange={(e) => { const raw = e.target.value; setVals((v) => ({ ...v, [`${q.attr}:${id}`]: raw })); submit(q, id, raw); }} aria-label={`${q.label} for ${id}`} />
                    <span className="w-6 text-xs text-muted-foreground">{q.unit}</span>
                  </label>
                );
              })}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
