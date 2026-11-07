import { describe, expect, it } from "vitest";
import { evaluate, translateClause } from "./rulesEngine";
import { listRules } from "./mockData";
import type { Attr } from "./types";

const ev = (value: number, extra: Partial<Attr> = {}): Attr => ({ value, unit: "mm", confidence: "high", quote: "q", source_file: "f", page: 1, section: "s", method: "Text", ...extra });

describe("rules engine", async () => {
  const rules = await listRules();
  const width = rules.find((r) => r.id === "ADA-404.2.3");
  if (!width) throw new Error("ADA door rule is missing");
  it("door 813 mm against ≥ 813 passes at the exact boundary", () => expect(evaluate(width, ev(813), "d").status).toBe("PASS"));
  it("door 700 mm fails ADA 404.2.3, 113 mm below the limit", () => {
    const r = evaluate(width, ev(700), "d");
    expect(r.status).toBe("FAIL"); expect(r.reason).toContain("113 mm less than the required 813 mm");
  });
  it("812 mm fails the 813 mm ADA limit", () => expect(evaluate(width, ev(812), "d").status).toBe("FAIL"));
  it("missing evidence is UNKNOWN, never guessed", () => expect(evaluate(width, undefined, "d").status).toBe("UNKNOWN"));
  it("contradictory sources are UNKNOWN and flagged for review", () => {
    const r = evaluate(width, ev(900, { conflicts: [ev(800)] }), "d");
    expect(r.status).toBe("UNKNOWN"); expect(r.needs_review).toBe(true);
  });
  it("low-confidence evidence is decided but flagged for review", () => {
    const r = evaluate(width, ev(790, { confidence: "low" }), "d");
    expect(r.status).toBe("FAIL"); expect(r.needs_review).toBe(true);
  });
  it("all built-in rules pass their self-tests", () => rules.forEach((r) => expect(r.tests.every((t) => t.passed)).toBe(true)));
  it("clause without a threshold is not translated", () => expect(translateClause("Doors shall be easy to open.")).toBeNull());
  it("translates a minimum width clause", () => expect(translateClause("clear width of at least 915 mm")).toMatchObject({ op: ">=", value: 915, attr: "clear_width_mm" }));
});
