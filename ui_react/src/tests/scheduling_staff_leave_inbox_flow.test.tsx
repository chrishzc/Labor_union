/** The historical leave API remains readable after the standalone work area was retired. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { staffLeaveInboxClient, type LeaveInboxItem } from '../api/scheduling/staff_leave_inbox_client';
import { ApiDecodeError } from '../api/shared/typed_errors';
import { transport } from '../api/shared/transport';

const PENDING_ITEM: LeaveInboxItem = {
  id: 77,
  staff_id: 11,
  staff_name: '去敏月嫂甲',
  leave_start_date: '2026-08-03',
  leave_end_date: '2026-08-03',
  request_reason: '個人事務',
  request_status: 'pending',
  aggregate_version: 4,
};

describe('歷史請假唯讀與舊審核契約', () => {
  beforeEach(() => sessionClient.setSession('synthetic-history-token', {
    id: 1, username: 'fixture', display_name: 'Fixture', role: 'system_admin',
  }));
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('用唯讀請求取回歷史請假與來源版本', async () => {
    const resolved: LeaveInboxItem = { ...PENDING_ITEM, request_status: 'resolved', aggregate_version: 5 };
    const get = vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'ok', data: [resolved], error: null });
    const post = vi.spyOn(transport, 'post');

    await expect(staffLeaveInboxClient.list('resolved')).resolves.toEqual([resolved]);
    expect(get).toHaveBeenCalledExactlyOnceWith('/api/v1/scheduling/staff-leave-requests', expect.objectContaining({
      params: { status: 'resolved', limit: 50 }, token: 'synthetic-history-token',
    }));
    expect(post).not.toHaveBeenCalled();
  });

  it('拒絕 identity、狀態或版本不符合 request 的 review receipt', async () => {
    vi.spyOn(transport, 'post').mockResolvedValue({
      success: true,
      message: 'ok',
      data: { request_id: 78, status: 'accepted_for_processing', version: 4, actor: 'admin' },
      error: null,
    });

    await expect(staffLeaveInboxClient.review(PENDING_ITEM, 'accept', '受理')).rejects.toBeInstanceOf(ApiDecodeError);
  });
});
