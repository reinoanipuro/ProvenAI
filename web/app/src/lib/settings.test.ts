import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, getSettings, setSettings } from "./settings";

describe("settings", () => {
  it("uses the local checker by default", () => {
    expect(DEFAULT_SETTINGS.apiUrl).toBe("http://localhost:8000/lovable");
  });

  it("remembers a changed checker address", () => {
    setSettings({ apiUrl: "http://localhost:8010/lovable" });
    expect(getSettings().apiUrl).toBe("http://localhost:8010/lovable");
    expect(JSON.parse(localStorage.getItem("provenai.settings") ?? "{}").apiUrl).toBe("http://localhost:8010/lovable");
  });
});
