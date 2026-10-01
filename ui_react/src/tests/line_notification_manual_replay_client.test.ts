import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { lineNotificationManualReplayClient, lineNotificationWarningSkipClient } from '../api/line/notification_manual_replay_client';
import { transport } from '../api/shared/transport';

describe('lineNotificationManualReplayClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('fresh-admin-session');
  });

  it('calls the owner Preview and Apply endpoints with the bound source identity', async () => {
    const post = vi.spyOn(transport, 'post')
      .mockResolvedValueOnce({
        success: true,
        message: 'ok',
        data: {
          source_event_id: 132,
          event_code: 'runtime.alert.review_required',
          historical_silent: false,
          matching_rule_count: 1,
          will_create_new_immutable_source: true,
        },
        error: null,
      })
      .mockResolvedValueOnce({
        success: true,
        message: 'ok',
        data: { source_event_id: 132, replayed_source_event_id: 201 },
        error: null,
      });

    await lineNotificationManualReplayClient.preview(132);
    await lineNotificationManualReplayClient.apply(132, {
      reason: '人工確認後重送',
      idempotency_key: 'manual-replay-idem-1',
      correlation_id: 'manual-replay-corr-1',
    });

    expect(post).toHaveBeenNthCalledWith(
      1,
      '/api/v1/line/notification-rules/sources/132/manual-replay/preview',
      undefined,
      expect.objectContaining({ token: 'fresh-admin-session' }),
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/api/v1/line/notification-rules/sources/132/manual-replay',
      expect.objectContaining({ reason: '人工確認後重送' }),
      expect.objectContaining({ token: 'fresh-admin-session' }),
    );
  });

  it('rejects invalid source identities and mismatched receipts', async () => {
    await expect(lineNotificationManualReplayClient.preview(0)).rejects.toThrow('來源識別值無效');
    vi.spyOn(transport, 'post').mockResolvedValue({
      success: true,
      message: 'ok',
      data: { source_event_id: 133, replayed_source_event_id: 201 },
      error: null,
    });
    await expect(lineNotificationManualReplayClient.apply(132, {
      reason: '人工確認後重送',
      idempotency_key: 'manual-replay-idem-2',
      correlation_id: 'manual-replay-corr-2',
    })).rejects.toThrow('來源不一致');
  });

  it('binds warning skip to the preview snapshot and rejects a receipt for another issue', async () => {
    const key = 'ci_' + 'a'.repeat(64);
    const expected = { issue_key: key, case_no: 'SYNTH-1', notification_reason: 'recipient_unavailable',
      owner_snapshot_token: 'b'.repeat(64), preview_fingerprint: 'c'.repeat(64) };
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce({ success: true, message: 'ok', data: expected, error: null })
      .mockResolvedValueOnce({ success: true, message: 'ok', data: { issue_key: 'ci_' + 'd'.repeat(64), replayed: false }, error: null });
    const preview = await lineNotificationWarningSkipClient.preview(key);
    await expect(lineNotificationWarningSkipClient.apply(preview, 'skip-1')).rejects.toThrow('收據不一致');
    expect(post).toHaveBeenLastCalledWith(`/api/v1/line/notification-rules/failures/${key}/skip/apply`, {
      owner_snapshot_token: expected.owner_snapshot_token, preview_fingerprint: expected.preview_fingerprint, idempotency_key: 'skip-1',
    }, expect.objectContaining({ token: 'fresh-admin-session' }));
  });
});
