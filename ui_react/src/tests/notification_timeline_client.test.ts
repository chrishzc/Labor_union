/**
 * File: notification_timeline_client.test.ts
 * Description: 驗證案件 LINE 通知歷程 GET 的路徑、strict decode 與識別防漂移。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { lineNotificationTimelineClient } from '../api/line/notification_timeline_client';
import { transport } from '../api/shared/transport';

const fixture = {
  case_no: 'CASE/1',
  records: [{
    source_event_id: 9,
    event_code: 'service_time_checkpoint',
    recipient_masked: '***1234',
    intent_status: 'cancelled',
  }],
};

describe('lineNotificationTimelineClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('token');
  });

  it('queries and strictly decodes a deidentified case timeline', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue({
      success: true, message: 'ok', data: fixture, error: null,
    });
    await expect(lineNotificationTimelineClient.query('CASE/1')).resolves.toEqual(fixture);
    expect(get).toHaveBeenCalledWith(
      '/api/v1/line/notification-rules/timeline/CASE%2F1',
      expect.objectContaining({ token: 'token' }),
    );
  });

  it('rejects identity drift and extra record fields', async () => {
    vi.spyOn(transport, 'get').mockResolvedValueOnce({
      success: true, message: 'ok', data: { ...fixture, case_no: 'CASE-2' }, error: null,
    });
    await expect(lineNotificationTimelineClient.query('CASE/1')).rejects.toThrow('案件識別不一致');

    vi.mocked(transport.get).mockResolvedValueOnce({
      success: true,
      message: 'ok',
      data: { ...fixture, records: [{ ...fixture.records[0], leaked: true }] },
      error: null,
    });
    await expect(lineNotificationTimelineClient.query('CASE/1')).rejects.toThrow();
  });
});
