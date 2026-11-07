import { createFileRoute } from "@tanstack/react-router";
import { SimpleResult } from "@/components/app/SimpleResult";
export const Route = createFileRoute("/inspections/$id")({
  validateSearch: (search: Record<string, unknown>): { calibrate?: string } => ({ calibrate: String(search["calibrate"] ?? "") }),
  head: () => ({
    meta: [
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { title: "Inspection result — ProvenAI" },
      { name: "description", content: "Ship drawing violations, required measurements and clear explanations for every check." },
      { property: "og:title", content: "Inspection result — ProvenAI" },
      { property: "og:description", content: "See doors that are too narrow on the drawing, with the rule and the fix." },
    ],
  }),
  component: InspectionPage,
});

function InspectionPage() { const { id } = Route.useParams(); return <SimpleResult id={id}/>; }
