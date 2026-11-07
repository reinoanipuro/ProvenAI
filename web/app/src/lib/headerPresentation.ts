import type { Result } from './types';

export function headerStage(loaded: boolean, checked: boolean, results: Result[]) {
  if (!loaded) return 'load';
  if (!checked) return 'run';
  const failures = results.filter(result => result.status === 'FAIL');
  return failures.every(result => result.reviewed) ? 'report' : 'review';
}

export function nextNonconformity(results: Result[], selectedId: string | null) {
  const failures = results.filter(result => result.status === 'FAIL' && !result.reviewed);
  const current = failures.findIndex(result => result.id === selectedId);
  return failures[(current + 1) % failures.length] ?? null;
}
