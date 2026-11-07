import { createFileRoute } from "@tanstack/react-router";
import { DrawingStart } from "@/components/app/DrawingStart";
export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): { calibrate?: string } => ({ calibrate: String(search["calibrate"] ?? "") }),
  head: () => ({ meta: [
    { title: "Check a ship design — ProvenAI" },
    { name: "description", content: "Check a ship drawing against engineering rules. See door violations on the drawing and what needs more information." },
    { property: "og:title", content: "Check a ship design — ProvenAI" },
    { property: "og:description", content: "Engineering redlines, measured nonconformities and traceable checker notes." },
    { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" },
  ] }), component: DesignCheck,
});

function DesignCheck() { const { calibrate } = Route.useSearch(); return <DrawingStart calibrate={calibrate === "1"}/>; }
