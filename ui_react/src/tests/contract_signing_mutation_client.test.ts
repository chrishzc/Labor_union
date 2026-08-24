/**
 * File: contract_signing_mutation_client.test.ts
 * Description: 驗證契約寄送與簽回命令使用既有 typed endpoint、multipart 與 command identity。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { contractSigningMutationClient } from '../api/orders/contract_signing_mutation_client';
import { transport } from '../api/shared/transport';

const receipt = {
  document_version_id: 7,
  signing_event_id: 8,
  line_delivery_task_id: 9,
  commitment_id: null,
  contract_identity: null,
};

const command = { idempotencyKey: 'contract-idem', correlationId: 'contract-corr' };

describe('contractSigningMutationClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('token');
    vi.spyOn(transport, 'post').mockResolvedValue({ success: true, message: 'ok', data: receipt, error: null });
  });

  it('sends a staff contract with command identity and the existing endpoint', async () => {
    await expect(contractSigningMutationClient.sendStaff('CASE-1', 3, 'https://contracts.example/download', command)).resolves.toEqual(receipt);
    expect(transport.post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/contract-signing/staff-segments/3/send',
      { download_url: 'https://contracts.example/download' },
      expect.objectContaining({ token: 'token', headers: { 'Idempotency-Key': 'contract-idem', 'X-Correlation-ID': 'contract-corr' } }),
    );
  });

  it('submits a client signed return as multipart and preserves its expected sent version', async () => {
    const file = new File(['signed'], 'signed.pdf', { type: 'application/pdf' });
    await contractSigningMutationClient.uploadClientSignedReturn('CASE-1', file, 7, command);
    const [, body] = vi.mocked(transport.post).mock.calls[0];
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('expected_document_version_id')).toBe('7');
    expect((body as FormData).get('document')).toBeInstanceOf(File);
    expect(vi.mocked(transport.post).mock.calls[0][0]).toBe('/api/v1/orders/CASE-1/contract-signing/client/signed-return');
  });
});
