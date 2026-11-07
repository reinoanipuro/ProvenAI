import { createFileRoute } from "@tanstack/react-router";
import { Home } from "@/components/app/Home";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "Check a ship design — ProvenAI" },
    { name: "description", content: "Check a ship design document against the regulations. Issues are marked in red, with next steps." },
  ] }),
  component: Home,
});
