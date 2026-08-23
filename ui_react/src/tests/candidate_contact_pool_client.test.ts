/**
 * File: candidate_contact_pool_client.test.ts
 * Description: 驗證候選聯繫池查詢、加入、意願與可靠資訊發送的 closed decode 及認證邊界。
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
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-1' } as never);
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

  it('creates a reliable candidate information task with authenticated actor identity', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue({
      success: true,
      message: 'queued',
      data: { status: 'queued', event_id: 31, line_task_id: 52 },
      error: null,
    });

    await expect(candidateContactPoolClient.sendInformation('CASE-POOL-001', 17, 2)).resolves.toEqual({
      status: 'queued',
      event_id: 31,
      line_task_id: 52,
    });
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-POOL-001/candidate-contact-pool/candidates/17/information',
      expect.objectContaining({
        info_type: 2,
        actor: 'operator-1',
        event_key: expect.stringMatching(/^orders-candidate-info-2-17-/),
      }),
      { token: 'volatile-token' },
    );
  });

  it('adds availability-checked candidates with actor and event identity', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue(successEnvelope({
      pool_id: 9,
      candidate_ids: [17],
      status: 'recorded',
    }));

    await expect(candidateContactPoolClient.addCandidates('CASE-POOL-001', [{
      staff_id: 8892,
      start_date: '2026-09-01',
      end_date: '2026-09-05',
    }])).resolves.toEqual({ pool_id: 9, candidate_ids: [17], status: 'recorded' });
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-POOL-001/candidate-contact-pool/candidates',
      expect.objectContaining({
        candidates: [{ staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' }],
        actor: 'operator-1',
        event_key: expect.stringMatching(/^orders-candidate-pool-add-/),
      }),
      { token: 'volatile-token' },
    );
  });

  it('records manual willingness and rejects an empty unwilling reason before transport', async () => {
    const put = vi.spyOn(transport, 'put').mockResolvedValue(successEnvelope({
      status: 'recorded',
      event_id: 45,
    }));

    await expect(candidateContactPoolClient.recordWillingness(
      'CASE-POOL-001', 17, 'willing', '',
    )).resolves.toEqual({ status: 'recorded', event_id: 45 });
    expect(put).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-POOL-001/candidate-contact-pool/candidates/17/willingness',
      expect.objectContaining({
        willingness: 'willing',
        reason: '人工補登願意',
        actor: 'operator-1',
      }),
      { token: 'volatile-token' },
    );

    await expect(candidateContactPoolClient.recordWillingness(
      'CASE-POOL-001', 17, 'unwilling', ' ',
    )).rejects.toThrow('必須填寫');
    expect(put).toHaveBeenCalledTimes(1);
  });

  it('fails closed before sending when session identity is missing', async () => {
    vi.mocked(sessionClient.getUser).mockReturnValue(null);
    const post = vi.spyOn(transport, 'post');

    await expect(candidateContactPoolClient.sendInformation('CASE-POOL-001', 17, 1)).rejects.toBeInstanceOf(
      ApiHttpError,
    );
    expect(post).not.toHaveBeenCalled();
  });

  it('rejects a queued response without durable line task identity', async () => {
    vi.spyOn(transport, 'post').mockResolvedValue({
      success: true,
      message: 'queued',
      data: { status: 'queued', event_id: 31, line_task_id: null },
      error: null,
    });

    await expect(candidateContactPoolClient.sendInformation('CASE-POOL-001', 17, 1)).rejects.toThrow();
  });
});
