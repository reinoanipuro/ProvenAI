import { createFileRoute } from "@tanstack/react-router";
import { ResultPage } from "@/components/app/Result";

export const Route = createFileRoute("/inspections/$id")({
  head: () => ({ meta: [
    { title: "Check result — ProvenAI" },
    { name: "description", content: "Issues marked in red on the design document, with the regulation page and next steps." },
  ] }),
  component: InspectionPage,
});

function InspectionPage() {
  const { id } = Route.useParams();
  return <ResultPage id={id} />;
}
