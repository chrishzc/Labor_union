import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffPerformanceClient } from '../../../../../../../api/reports/staff_performance_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { transport } from '../../../../../../../api/shared/transport';
import { performanceFixture } from './staff_performance_fixture';

const filters = { year: 2026, period: 'month' as const, month: 11 };
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
  vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'Success', error: null, data: performanceFixture(filters) });
});

describe('staff performance strict transport', () => {
  it('sends authenticated bounded period parameters and decodes the report', async () => {
    const report = await staffPerformanceClient.query(filters);
    expect(report.totals.total_amount_ntd).toBe(99000);
    expect(transport.get).toHaveBeenCalledWith('/api/v1/operations-reports/staff-performance', expect.objectContaining({ params: filters, token: 'synthetic-session', cache: 'no-store' }));
  });
  it('rejects wrong versions and a mismatched request period', async () => {
    vi.mocked(transport.get).mockResolvedValueOnce({ success: true, message: 'Success', data: { ...performanceFixture(filters), schema_version: 'old' } });
    await expect(staffPerformanceClient.query(filters)).rejects.toThrow('格式');
    vi.mocked(transport.get).mockResolvedValueOnce({ success: true, message: 'Success', data: { ...performanceFixture(filters), selected_staff_id: 9 } });
    await expect(staffPerformanceClient.query(filters)).rejects.toThrow('篩選不一致');
  });
  it('requires a session and refuses invalid export content', async () => {
    vi.mocked(sessionClient.getToken).mockReturnValueOnce(null);
    await expect(staffPerformanceClient.query(filters)).rejects.toThrow('請先登入');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('not an xlsx', { headers: { 'Content-Type': 'text/html' } }));
    await expect(staffPerformanceClient.download(filters, 'service_hours')).rejects.toThrow('格式');
  });
});
