import overlays from "@/data/overlays.json";

export type NormalizedBox = { x0: number; x1: number; y0: number; y1: number };
export const drawingSize = overlays.image;

/** Geometry only: maps existing findings without making compliance decisions. */
export function findingOverlay(resultId: string, elementId?: string): NormalizedBox | null {
  const mappings: Record<string, string> = overlays.findings;
  const boxes: Record<string, NormalizedBox> = overlays.boxes;
  const key = mappings[resultId];
  if (key) return boxes[key] ?? null;
  // Reuse calibrated element geometry for other checks on that same element.
  const related = elementId ? Object.keys(mappings).find(id => id.endsWith(`:${elementId}`)) : undefined;
  return related ? boxes[mappings[related] ?? ''] ?? null : null;
}

export function normalizedPoint(x: number, y: number, width: number, height: number) {
  if (width <= 0 || height <= 0 || x < 0 || y < 0 || x > width || y > height) return null;
  return { x: x / width, y: y / height };
}