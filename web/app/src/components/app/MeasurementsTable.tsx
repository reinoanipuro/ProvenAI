import type { ShipElement } from "@/lib/types";
import { ConfidenceTag } from "./Status";

export function MeasurementsTable({ elements }: { elements: ShipElement[] }) {
  const rows = elements.flatMap((el) => Object.entries(el.attrs).flatMap(([k, a]) => [{ el, k, a, conflict: false }, ...(a.conflicts ?? []).map((c) => ({ el, k, a: c, conflict: true }))]));
  return (
    <div className="overflow-hidden rounded-md border bg-card">
      <table className="w-full text-sm">
        <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
          <tr>{["Element", "Attribute", "Value", "Method", "Source", "Location", "Quote"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map(({ el, k, a, conflict }, i) => (
            <tr key={i} className="border-t align-top">
              <td className="px-3 py-2 font-mono text-xs">{el.id}</td>
              <td className="px-3 py-2 font-mono text-xs">{k}</td>
              <td className="px-3 py-2 text-right font-mono text-xs tnum">{a.value} {a.unit}</td>
              <td className="px-3 py-2 text-xs">{a.method}</td>
              <td className="max-w-[180px] truncate px-3 py-2 font-mono text-xs" title={a.source_file}>{a.source_file}</td>
              <td className="px-3 py-2 text-xs">{a.page ? `p.${a.page} · ` : ""}{a.section}</td>
              <td className="max-w-[240px] px-3 py-2 font-mono text-xs text-muted-foreground">“{a.quote}”</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
