import { CheckCircle2, CircleHelp, XCircle } from "lucide-react";
import { statusLabel } from "@/lib/presentation";
import { cn } from "@/lib/utils";
import type { Status } from "@/lib/types";

const map = {
  PASS: { icon: CheckCircle2, cls: "bg-pass-soft text-pass border-pass/30" },
  FAIL: { icon: XCircle, cls: "bg-fail-soft text-fail border-fail/30" },
  UNKNOWN: { icon: CircleHelp, cls: "bg-unknown-soft text-unknown border-unknown/40" },
} as const;

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const { icon: Icon, cls } = map[status];
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px] font-semibold uppercase", cls, className)}>
      <span className={cn("h-2 w-2 border border-current", status !== "UNKNOWN" && "bg-current")} aria-hidden />
      {statusLabel[status]}
    </span>
  );
}

export function ReviewBadge({ className }: { className?: string }) {
  return null;
}

export function ConfidenceTag({ c }: { c: "high" | "medium" | "low" | null }) {
  if (!c) return <span className="text-muted-foreground">—</span>;
  const bars = c === "high" ? 3 : c === "medium" ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="flex gap-0.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className={cn("h-2.5 w-1 rounded-sm", i < bars ? "bg-foreground/60" : "bg-border")} />
        ))}
      </span>
      {c}
    </span>
  );
}

export const statusRank: Record<Status, number> = { FAIL: 0, UNKNOWN: 1, PASS: 2 };
export const statusColorVar: Record<Status, string> = { PASS: "var(--pass)", FAIL: "var(--fail)", UNKNOWN: "var(--unknown)" };
