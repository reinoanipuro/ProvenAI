import { describe, it, expect } from 'vitest';
import { reportCounts, reportChanges } from './presentation';
import { getInspection, DEMO_ID } from './mockData';

describe('daily report uses actual check evidence', () => {
  it('reports 2 nonconformities, 5 not verified and 7 OK from the demo verdicts', async () => {
    const insp = await getInspection(DEMO_ID);
    expect(reportCounts(insp.results)).toEqual({ checked: 14, nonconform: 2, unverified: 5, ok: 7 });
  });
  it('does not claim a daily change without an explicit previous revision', async () => {
    const insp = await getInspection(DEMO_ID);
    expect(reportChanges(insp.results)).toBeNull();
    expect(reportChanges(insp.results, insp.results)).toEqual({ fixed: 0, new: 0 });
  });
});