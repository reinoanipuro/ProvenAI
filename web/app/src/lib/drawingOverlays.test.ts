import { describe, expect, it } from "vitest";
import { drawingSize, findingOverlay, normalizedPoint } from "./drawingOverlays";
import { DEMO_ID, getInspection } from "./mockData";

describe("RCRV drawing mappings", () => {
  it("places the 01-36-2 entrance at the requested normalized door bounds", () => {
    expect(findingOverlay("ADA-404.2.3:D-01-36-2")).toEqual({ x0: 0.16, x1: 0.22, y0: 0.78, y1: 0.90 });
  });
  it("renames the second violation to the 01-31-2 cabin and maps its door", async () => {
    const demo = await getInspection(DEMO_ID);
    expect(demo.elements.find((e) => e.id === "D-01-31-2")?.space).toBe("01-31-2");
    expect(demo.results.find((r) => r.id === "ADA-404.2.3:D-01-31-2")?.status).toBe("FAIL");
    expect(demo.elements.some((e) => e.id === "D-01-36-1")).toBe(false);
    expect(findingOverlay("ADA-404.2.3:D-01-31-2")).toEqual({ x0: 0.33, x1: 0.38, y0: 0.78, y1: 0.90 });
  });
  it("maps unknown 01-36-2 items to the supplied cabin bounds", () => {
    expect(findingOverlay("DNV-ACC-3.1.4:CAB-01-36-2")).toEqual({ x0: 0.13, x1: 0.28, y0: 0.48, y1: 0.98 });
  });
  it("maps unknown 01-26-2 items to the supplied cabin bounds", () => {
    expect(findingOverlay("ADA-304.3.1:CAB-01-26-2")).toEqual({ x0: 0.46, x1: 0.64, y0: 0.48, y1: 0.98 });
  });
  it("maps every unknown reference finding without changing its verdict", async () => {
    const demo = await getInspection(DEMO_ID);
    const unknown = demo.results.filter((r) => r.status === "UNKNOWN");
    expect(unknown).toHaveLength(5);
    for (const result of unknown) expect(findingOverlay(result.id)).not.toBeNull();
  });
  it("reports calibration coordinates in image space and ignores outside clicks", () => {
    expect(normalizedPoint(drawingSize.width * 0.2, drawingSize.height * 0.84, drawingSize.width, drawingSize.height)).toEqual({ x: 0.2, y: 0.84 });
    expect(normalizedPoint(-1, 10, drawingSize.width, drawingSize.height)).toBeNull();
  });
});