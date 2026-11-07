import { useSyncExternalStore } from "react";

/** Where the ProvenAI checker runs. Stored per browser; VITE_API_URL sets the default. */
export interface Settings { apiUrl: string }
const KEY = "provenai.settings";
export const DEFAULT_SETTINGS: Settings = {
  apiUrl: (import.meta.env["VITE_API_URL"] as string | undefined) ?? "http://localhost:8000/lovable",
};
let cache: Settings | null = null;
const listeners = new Set<() => void>();

export function getSettings(): Settings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  if (!cache) {
    try {
      const stored = JSON.parse(localStorage.getItem(KEY) || "{}") as Partial<Settings>;
      cache = { apiUrl: typeof stored.apiUrl === "string" && stored.apiUrl ? stored.apiUrl : DEFAULT_SETTINGS.apiUrl };
    } catch { cache = DEFAULT_SETTINGS; }
  }
  return cache;
}
export function setSettings(patch: Partial<Settings>) {
  cache = { ...getSettings(), ...patch };
  try { localStorage.setItem(KEY, JSON.stringify(cache)); } catch { /* private window: kept for this visit only */ }
  listeners.forEach((listener) => listener());
}
const subscribe = (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); };
export const useSettings = () => useSyncExternalStore(subscribe, getSettings, () => DEFAULT_SETTINGS);
