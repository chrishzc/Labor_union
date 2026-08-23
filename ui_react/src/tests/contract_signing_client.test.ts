/**
 * File: contract_signing_client.test.ts
 * Description: 驗證契約簽署 GET 的路徑、strict decode 與案件識別防漂移。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import { transport } from '../api/shared/transport';

const fixture = {
  case_no: 'CASE-1',
  staff_segments: [{ segment_id: 7, staff_id: 9, sent: true, signed_received: true }],
  commitment_id: 3,
  client_document_sent: true,
  client_signed_received: false,
  contract_identity: null,
  documents: [],
};

describe('contractSigningClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('token');
  });

  it('queries and strictly decodes the case signing status', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue({
      success: true, message: 'ok', data: fixture, error: null,
    });
    await expect(contractSigningClient.query('CASE-1')).resolves.toEqual(fixture);
    expect(get).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/contract-signing',
      expect.objectContaining({ token: 'token' }),
    );
  });

  it('rejects identity drift and extra response fields', async () => {
    vi.spyOn(transport, 'get').mockResolvedValueOnce({
      success: true, message: 'ok', data: { ...fixture, case_no: 'CASE-2' }, error: null,
    });
    await expect(contractSigningClient.query('CASE-1')).rejects.toThrow('案件識別不一致');

    vi.mocked(transport.get).mockResolvedValueOnce({
      success: true, message: 'ok', data: { ...fixture, leaked: true }, error: null,
    });
    await expect(contractSigningClient.query('CASE-1')).rejects.toThrow();
  });
});
