/**
 * File: candidate_contact_pool_client.test.ts
 * Description: 驗證候選聯繫池 GET 的 closed decode、identity、空池與 request signal。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { transport } from '../api/shared/transport';

const candidate = {
  id: 17,
  staff_id: 8892,
  service_start_date: '2026-09-01',
  service_end_date: '2026-09-05',
  status: 'active',
  created_at: '2026-08-23T10:00:00',
  staff_name: '測試月嫂',
  willingness: 'willing',
  reason: null,
  information: {
    '1': { status: 'sent', sent_at: '2026-08-23T10:05:00' },
    '2': null,
  },
} as const;

const fixture = {
  pool_id: 9,
  case_no: 'CASE-POOL-001',
  candidates: [candidate],
};

const successEnvelope = (data: unknown) => ({
  success: true,
  message: '成功讀取候選聯繫池',
  data,
  error: null,
});

describe('candidateContactPoolClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('volatile-token');
  });

  it('queries the bounded endpoint and strictly decodes owner facts', async () => {
    const signal = new AbortController().signal;
    const get = vi.spyOn(transport, 'get').mockResolvedValue(successEnvelope(fixture));

    await expect(
      candidateContactPoolClient.query('CASE-POOL-001', { signal }),
    ).resolves.toEqual(fixture);
    expect(get).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-POOL-001/candidate-contact-pool',
      { signal, token: 'volatile-token' },
    );
  });

  it('accepts the server typed empty-pool result', async () => {
    vi.spyOn(transport, 'get').mockResolvedValue(successEnvelope({
      pool_id: null,
      case_no: 'CASE-EMPTY-001',
      candidates: [],
    }));

    await expect(candidateContactPoolClient.query('CASE-EMPTY-001')).resolves.toEqual({
      pool_id: null,
      case_no: 'CASE-EMPTY-001',
      candidates: [],
    });
  });

  it('rejects case identity drift and nested extra fields', async () => {
    vi.spyOn(transport, 'get').mockResolvedValueOnce(successEnvelope({
      ...fixture,
      case_no: 'CASE-OTHER',
    }));
    await expect(candidateContactPoolClient.query('CASE-POOL-001')).rejects.toThrow(
      '案件識別不一致',
    );

    vi.mocked(transport.get).mockResolvedValueOnce(successEnvelope({
      ...fixture,
      candidates: [{ ...candidate, private_phone: '0900000000' }],
    }));
    await expect(candidateContactPoolClient.query('CASE-POOL-001')).rejects.toThrow();
  });

  it('rejects an unsuccessful or empty success envelope as a typed HTTP error', async () => {
    vi.spyOn(transport, 'get').mockResolvedValue({
      success: false,
      message: 'query failed',
      data: null,
      error: 'candidate pool unavailable',
    });

    await expect(candidateContactPoolClient.query('CASE-POOL-001')).rejects.toBeInstanceOf(
      ApiHttpError,
    );
  });
});
