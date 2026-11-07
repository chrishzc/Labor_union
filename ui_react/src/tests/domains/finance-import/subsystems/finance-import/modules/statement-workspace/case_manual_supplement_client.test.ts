/** Existing HTTP client carries the user's intent and idempotency key unchanged. */
import { beforeEach, expect, it, vi } from 'vitest';
import { financeAccountingClient } from '../../../../../../../api/finance_import/finance_accounting_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

vi.mock('../../../../../../../api/shared/transport', () => ({ transport: { post: vi.fn() } }));
vi.mock('../../../../../../../api/auth/session_client', () => ({ sessionClient: { getToken: () => 'synthetic-session' } }));

beforeEach(() => vi.clearAllMocks());

it.each([
  ['client_receipt', false], ['client_receipt', true], ['client_refund', false], ['client_refund', true],
] as const)('passes %s overage choice %s to the existing transport with the original key', async (direction, allowOverage) => {
  const rejected = new ApiHttpError(422, 'synthetic_blocker', 'Synthetic rejection');
  vi.mocked(transport.post).mockRejectedValue(rejected);
  const command = { bank: 'sinopac', direction, target_item: 'synthetic-obligation',
    amount_ntd: 1100, transaction_date: '2026-11-06', allow_overage_disposition: allowOverage } as const;
  await expect(financeAccountingClient.manualSupplement('CASE', command, 'original-key')).rejects.toBe(rejected);
  expect(transport.post).toHaveBeenCalledWith('/api/v1/finance-import/cases/CASE/manual-supplement', command,
    expect.objectContaining({ headers: { 'Idempotency-Key': 'original-key' } }));
});
