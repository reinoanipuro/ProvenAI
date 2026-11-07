import { describe, expect, it } from "vitest";
import { parseRulePack } from "./api";
import { approveRule, getInspection, listRules, submitAnswers, DEMO_ID } from "./mockData";
import { drawingCallout, revisionChange } from "./presentation";

describe("clarity flows", () => {
  it("the demo contains 2 violations, 5 unknown checks and 7 OK checks", async () => {
    const demo = await getInspection(DEMO_ID);
    expect(demo.results.filter((r) => r.status === "FAIL")).toHaveLength(2);
    expect(demo.results.filter((r) => r.status === "UNKNOWN")).toHaveLength(5);
    expect(demo.results.filter((r) => r.status === "PASS")).toHaveLength(7);
  });
  it("the 700 mm demo door needs 113 mm more to meet the 813 mm minimum", async () => {
    const demo = await getInspection(DEMO_ID);
    const door = demo.results.find((r) => r.element_id === "D-01-36-2" && r.check_id === "ADA-404.2.3");
    if (!door) throw new Error("Missing demo door");
    expect(door.measured).toBe(700);
    expect(door.required).toBe("≥ 813");
    expect(door.status).toBe("FAIL");
    expect(drawingCallout(door)).toContain("113 mm");
  });
  it("imports stay proposed even when JSON claims approval", async () => {
    const rule = (await listRules())[0];
    if (!rule) throw new Error("Missing demo rule");
    expect(parseRulePack([rule])[0]?.status).toBe("proposed");
  });
  it("a failing rule cannot be approved", async () => {
    const rule = (await listRules())[0];
    if (!rule) throw new Error("Missing demo rule");
    const broken = { ...rule, tests: [{ name: "Invalid boundary", input: 813, expected: "FAIL" as const }] };
    await expect(approveRule(broken)).rejects.toThrow("Rule locked");
  });
  it("a supplied sill height resolves its unknown check", async () => {
    await getInspection(DEMO_ID);
    const updated = await submitAnswers(DEMO_ID, [{ attr: "sill_height_mm", element_id: "D-01-31-2", value: 10 }]);
    expect(updated.results.find((r) => r.check_id === "ADA-404.2.5" && r.element_id === "D-01-31-2")?.status).toBe("PASS");
    expect(updated.questions.find((q) => q.attr === "sill_height_mm")?.element_ids).not.toContain("D-01-31-2");
  });
  it("a violation resolved since the previous revision is Fixed", async () => {
    const current = await getInspection("rv60-rev-c"), previous = await getInspection("rv60-rev-b");
    const door = current.results.find((r) => r.check_id === "ADA-404.2.3" && r.element_id === "D-01-26-2");
    if (!door) throw new Error("Missing door result");
    expect(revisionChange(door, previous.results)).toBe("Fixed");
  });
});