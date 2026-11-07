import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export function InspectionStepper({ step }: { step: 1 | 2 | 3 }) {
  return <ol aria-label="Inspection progress" className="flex flex-wrap items-center gap-4 border-b px-8 py-4 text-xs">
    {["Upload design", "Choose rules", "See results"].map((label, i) => <li key={label} aria-current={step === i + 1 ? "step" : undefined} className={cn("flex items-center gap-2", step === i + 1 ? "font-medium text-primary" : "text-muted-foreground")}>
      <span className={cn("grid h-6 w-6 place-items-center rounded-full border font-mono", step > i + 1 && "border-primary/30 text-primary", step === i + 1 && "border-primary bg-primary text-primary-foreground")}>{step > i + 1 ? <Check className="h-3 w-3" /> : i + 1}</span>{label}
      {i < 2 && <span className="ml-4 h-px w-8 bg-border" aria-hidden />}
    </li>)}
  </ol>;
}