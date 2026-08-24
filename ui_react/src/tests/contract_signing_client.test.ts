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

  it('downloads an immutable document only through the versioned authorized route', async () => {
    const fetchStub = vi.fn().mockResolvedValue(new Response(new Blob(['pdf'], { type: 'application/pdf' }), {
      status: 200,
      headers: {
        'content-type': 'application/pdf',
        'content-disposition': 'attachment; filename="signed-contract.pdf"',
      },
    }));
    vi.stubGlobal('fetch', fetchStub);

    await expect(contractSigningClient.downloadDocument('CASE-1', 7)).resolves.toMatchObject({
      filename: 'signed-contract.pdf',
      mimeType: 'application/pdf',
    });
    expect(fetchStub).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/contract-signing/documents/7/download',
      expect.objectContaining({ method: 'GET', headers: { Authorization: 'Bearer token' } }),
    );
  });

  it('preserves the typed server error when an archived document is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { error: { code: 'archive file missing', message: '找不到或無法驗證契約文件。' } },
    }), { status: 404, headers: { 'content-type': 'application/json' } })));

    await expect(contractSigningClient.downloadDocument('CASE-1', 7)).rejects.toMatchObject({
      status: 404,
      raw: { detail: { error: { message: '找不到或無法驗證契約文件。' } } },
    });
  });
});
