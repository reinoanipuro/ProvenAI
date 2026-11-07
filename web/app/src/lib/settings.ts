import { useSyncExternalStore } from "react";

export interface Settings { apiUrl: string; demo: boolean; theme: "light" | "dark" }
const KEY = "provenai.settings";
// Defaults to the ProvenAI backend in this project; override with VITE_API_URL and VITE_DEMO.
const env = import.meta.env;
export const DEFAULT_SETTINGS: Settings = {
  apiUrl: (env["VITE_API_URL"] as string | undefined) ?? "http://localhost:8000/lovable",
  demo: env["VITE_DEMO"] === "true",
  theme: "light",
};
let cache: Settings | null = null;
const listeners = new Set<() => void>();

export function getSettings(): Settings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  if (!cache) {
    try { cache = { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(KEY) || "{}"), theme: "light" }; } catch { cache = DEFAULT_SETTINGS; }
  }
  return cache ?? DEFAULT_SETTINGS;
}
export function setSettings(patch: Partial<Settings>) {
  cache = { ...getSettings(), ...patch, theme: "light" };
  localStorage.setItem(KEY, JSON.stringify(cache));
  listeners.forEach((l) => l());
}
const subscribe = (l: () => void) => { listeners.add(l); return () => listeners.delete(l); };
export const useSettings = () => useSyncExternalStore(subscribe, getSettings, () => DEFAULT_SETTINGS);
