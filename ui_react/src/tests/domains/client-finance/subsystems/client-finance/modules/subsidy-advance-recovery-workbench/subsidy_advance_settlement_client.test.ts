/** All bounded pages or no result; reject wrong-owner previews and receipts. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { subsidyAdvanceSettlementClient as client } from '../../../../../../../api/client_finance/subsidy_advance_settlement_client';
import { transport } from '../../../../../../../api/shared/transport';
import { sessionClient } from '../../../../../../../api/auth/session_client';

vi.mock('../../../../../../../api/shared/transport', () => ({ transport: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../../../../../../../api/auth/session_client', () => ({ sessionClient: { getToken: vi.fn(() => 'test-session') } }));
const row = { advance_id: 10, case_no: 'TEST-001', client_name: '測試客戶', advanced_on: '2026-03-15', advance_amount_ntd: 12000, government_received_ntd: 12000, received_on: '2026-04-01', recovered_amount_ntd: 0, status: 'ready', review_reason: null };
const envelope = (data: unknown) => ({ success: true, message: 'ok', data, error: null });

beforeEach(() => { vi.mocked(transport.get).mockReset(); vi.mocked(transport.post).mockReset(); vi.mocked(sessionClient.getToken).mockReturnValue('test-session'); });

describe('advance settlement strict client', () => {
  it('loads every page and does not expose partial results when a later page fails', async () => {
    vi.mocked(transport.get).mockResolvedValueOnce(envelope({ rows: [row], next_cursor: 10 })).mockResolvedValueOnce(envelope({ rows: [{ ...row, advance_id: 11 }], next_cursor: null }));
    expect(await client.queryAll('TEST')).toHaveLength(2);
    expect(transport.get).toHaveBeenLastCalledWith(expect.stringContaining('after_id=10'), expect.objectContaining({ token: 'test-session' }));
    vi.mocked(transport.get).mockResolvedValueOnce(envelope({ rows: [row], next_cursor: 10 })).mockRejectedValueOnce(new Error('later page failed'));
    await expect(client.queryAll()).rejects.toThrow('later page failed');
  });

  it('rejects repeated cursor/items and a preview for a different advance', async () => {
    vi.mocked(transport.get).mockResolvedValue(envelope({ rows: [row], next_cursor: 10 }));
    await expect(client.queryAll()).rejects.toThrow();
    vi.mocked(transport.post).mockResolvedValue(envelope({ row: { ...row, advance_id: 11 }, account_version: 1, batch_version: 2, preview_fingerprint: 'a'.repeat(64) }));
    await expect(client.preview(10)).rejects.toThrow('銷帳預覽與所選墊款不一致。');
  });

  it('rejects unauthenticated access before requesting financial data', async () => {
    vi.mocked(sessionClient.getToken).mockReturnValue(null);
    await expect(client.queryAll()).rejects.toThrow('請先登入。');
    expect(transport.get).not.toHaveBeenCalled();
  });
});
