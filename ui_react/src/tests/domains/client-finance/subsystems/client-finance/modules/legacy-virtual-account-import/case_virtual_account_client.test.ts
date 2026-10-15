import { afterEach, describe, expect, it, vi } from 'vitest';
import { caseVirtualAccountClient } from '../../../../../../../api/client_finance/case_virtual_account_client';
import { transport } from '../../../../../../../api/shared/transport';

vi.mock('../../../../../../../api/auth/session_client', () => ({ sessionClient: { getToken: () => 'test-session' } }));
const command = { case_no: '114000001', virtual_account: '99781699114999', expected_mapping_ids: [1] };
const receipt = { case_no: command.case_no, before: ['99781699114001'], virtual_account: command.virtual_account };
const envelope = (data: unknown) => ({ success: true, message: '完成', data, error: null });
afterEach(() => vi.restoreAllMocks());

describe('single-case account transport', () => {
  it('sends one direct save with current mapping IDs, without reason or preview', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue(envelope(receipt));
    await caseVirtualAccountClient.apply(command, 'same-key');
    expect(post).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/client-finance/cases/114000001/virtual-account/apply', {
      virtual_account: command.virtual_account, expected_mapping_ids: [1],
    }, { token: 'test-session', headers: { 'Idempotency-Key': 'same-key' } });
  });
  it('rejects another case or a receipt inconsistent with the submitted account', async () => {
    vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope({ ...receipt, case_no: '114000002' }))
      .mockResolvedValueOnce(envelope({ ...receipt, virtual_account: '99781699114002' }));
    await expect(caseVirtualAccountClient.apply(command, 'key')).rejects.toThrow('案件不一致');
    await expect(caseVirtualAccountClient.apply(command, 'key')).rejects.toThrow('收據與送出內容不一致');
  });
});
