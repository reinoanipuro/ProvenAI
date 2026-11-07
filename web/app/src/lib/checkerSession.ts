import { useSyncExternalStore } from 'react';
import type { Inspection } from './api';

export type CheckedDrawing = { at: string; inspection: Inspection };
let rows: CheckedDrawing[] = [];
const listeners = new Set<() => void>();
const empty: CheckedDrawing[] = [];
export function recordDrawingCheck(inspection: Inspection) {
  rows = [...rows, { at: new Date().toISOString(), inspection: structuredClone(inspection) }];
  listeners.forEach(fn => fn());
}
export function useCheckedDrawings() {
  return useSyncExternalStore(fn => { listeners.add(fn); return () => { listeners.delete(fn); }; }, () => rows, () => empty);
}