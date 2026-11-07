import { describe, expect, it } from 'vitest';
import { headerStage, nextNonconformity } from './headerPresentation';
import type { Result } from './types';
const finding = (id: string, status: Result['status'], reviewed = false) => ({ id, status, reviewed }) as Result;
describe('context-aware header action', () => {
  it('loads before a drawing is open', () => expect(headerStage(false, false, [])).toBe('load'));
  it('runs after loading and before checking', () => expect(headerStage(true, false, [])).toBe('run'));
  it('reviews nonconformities after checking', () => expect(headerStage(true, true, [finding('1', 'FAIL')])).toBe('review'));
  it('offers daily report only once every nonconformity is reviewed', () => {
    expect(headerStage(true, true, [finding('1', 'FAIL', true), finding('2', 'FAIL')])).toBe('review');
    expect(headerStage(true, true, [finding('1', 'FAIL', true), finding('2', 'FAIL', true), finding('3', 'UNKNOWN')])).toBe('report');
  });
  it('selects note one then the next unreviewed nonconformity', () => {
    const results = [finding('1', 'FAIL'), finding('2', 'FAIL'), finding('3', 'UNKNOWN')];
    expect(nextNonconformity(results, null)?.id).toBe('1');
    expect(nextNonconformity(results, '1')?.id).toBe('2');
    expect(nextNonconformity(results, '2')?.id).toBe('1');
    expect(nextNonconformity([finding('1', 'FAIL', true), finding('2', 'FAIL')], '1')?.id).toBe('2');
  });
});
