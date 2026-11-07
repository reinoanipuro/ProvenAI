import { createFileRoute } from "@tanstack/react-router";
import { SimpleHome } from "@/components/app/SimpleHome";
export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "Check a ship design — ProvenAI" },
    { name: "description", content: "Check a ship drawing against engineering rules. See door violations on the drawing and what needs more information." },
    { property: "og:title", content: "Check a ship design — ProvenAI" },
    { property: "og:description", content: "Engineering redlines, measured nonconformities and traceable checker notes." },
    { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" },
  ] }), component: DesignCheck,
});

function DesignCheck() { return <SimpleHome/>; }
