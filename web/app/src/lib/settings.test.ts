import { describe, expect, it } from "vitest";
import { getSettings, setSettings } from "./settings";

describe("light-only drawing workspace", () => {
  it("keeps the theme light when a stored dark preference is requested", () => {
    setSettings({ theme: "dark" });
    expect(getSettings().theme).toBe("light");
  });
});