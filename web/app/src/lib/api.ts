// Calls to the ProvenAI checker (backend/lovable.py). There is no demo data: when the checker
// cannot be reached a call fails, so a result on screen always comes from the engineer's own files.
import { getSettings } from "./settings";
import type { Inspection, InspectionSummary } from "./types";
export * from "./types";

const base = () => getSettings().apiUrl.replace(/\/$/, "");

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export const api = {
  async health(): Promise<boolean> {
    try { await json(`${base()}/health`); return true; } catch { return false; }
  },
  inspections: () => json<InspectionSummary[]>(`${base()}/inspections`),
  inspection: (id: string) => json<Inspection>(`${base()}/inspections/${encodeURIComponent(id)}`),
  /** Send design documents to be checked; returns the new inspection's id. */
  checkDocuments(name: string, files: File[]): Promise<{ id: string }> {
    const form = new FormData();
    form.append("name", name);
    files.forEach((file) => form.append("files", file));
    return json<{ id: string }>(`${base()}/inspections`, { method: "POST", body: form });
  },
  /** URL of an uploaded file, for the PDF viewer. */
  fileUrl: (id: string, fileId: string) => `${base()}/inspections/${encodeURIComponent(id)}/files/${fileId}`,
  /** The text of an uploaded text or Word file, to show it with the issues marked. */
  fileText: (id: string, fileId: string) =>
    json<{ pages: { page: number | null; text: string }[] }>(`${base()}/inspections/${encodeURIComponent(id)}/files/${fileId}/text`),
  /** The regulation page as an image, with the quote highlighted. */
  regulationPageUrl: (filename: string, page: number, quote: string) =>
    `${base().replace(/\/lovable$/, "")}/source/page?filename=${encodeURIComponent(filename)}&page=${page}&quote=${encodeURIComponent(quote.slice(0, 1500))}`,
};

/** Part of every query key, so changing the checker address refetches everything. */
export const qk = { all: () => [getSettings().apiUrl] as const };
