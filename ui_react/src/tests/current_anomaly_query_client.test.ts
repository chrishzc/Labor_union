import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';
import { queryCurrentAnomalies } from '../api/anomalies/current_anomaly_query_client';

describe('current anomaly query client', () => {
  beforeEach(() => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-session');
  });

  it('uses only the closed current filters and decodes cursor pages', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue({
      success: true,
      message: 'ok',
      data: {
        items: [{
          issue_key: `ci_${'a'.repeat(64)}`,
          definition_code: 'LINE-006',
          owner_domain: 'line',
          severity: 'warning',
          blocking: false,
          episode_started_at: '2026-08-30T01:00:00Z',
          last_verified_at: '2026-08-30T01:01:00Z',
        }],
        next_cursor: 'signed-cursor',
      },
    });

    const page = await queryCurrentAnomalies({ ownerDomain: 'line', blocking: false, limit: 50 });

    expect(page.items[0].issue_key).toMatch(/^ci_/);
    expect(page.next_cursor).toBe('signed-cursor');
    expect(get).toHaveBeenCalledWith('/api/v1/anomalies', expect.objectContaining({
      params: {
        definition_code: undefined,
        owner_domain: 'line',
        blocking: false,
        limit: 50,
        cursor: undefined,
      },
    }));
  });

  it('rejects offset-style pagination', async () => {
    await expect(queryCurrentAnomalies({ limit: 101 })).rejects.toThrow('目前異常查詢參數無效');
  });
});
