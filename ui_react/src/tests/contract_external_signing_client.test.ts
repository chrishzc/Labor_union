/**
 * File: contract_external_signing_client.test.ts
 * Description: 驗證外部簽約 successor client 的 strict schema、PDF 下載、命令 identity 與安全 readback。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';
import {
  contractExternalSigningClient,
  createExternalSigningCommandIdentity,
} from '../api/orders/contract_external_signing_client';

const sessionId = 'ces_1234567890abcdef1234567890abcdef';
const query = {
  case_no: 'CASE-001',
  session_id: sessionId,
  state: 'staff_reporting' as const,
  status_version: 3,
  matching_plan_id: 17,
  commitment_id: null,
  unsigned_document: {
    document_version_id: 31,
    filename: 'CASE-001-unsigned.pdf',
    mime_type: 'application/pdf' as const,
    size_bytes: 20,
  },
  staff_targets: [{
    matching_segment_id: 41,
    staff_subject_reference: 'STAFF-009',
    document_version_id: 31,
    reported: false,
  }],
  client_target: {
    client_subject_reference: 'CLIENT-001',
    document_version_id: 32,
    reported: false,
  },
};

const reportReceipt = {
  receipt_id: 'cesr_1234567890abcdef1234567890abcdef',
  command_type: 'record_staff_report' as const,
  schema_version: 'contract-external-signing-receipt.v1' as const,
  session_id: sessionId,
  outcome_state: 'recorded' as const,
  resulting_status_version: 4,
  resulting_state: 'staff_reports_complete' as const,
  matching_segment_id: 41,
  final_document_id: null,
  replayed: false,
  applied_at: '2026-08-26T10:00:00Z',
};

const envelope = (data: unknown) => ({ success: true, message: 'ok', data, error: null });

describe('contractExternalSigningClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('session-token');
  });

  it('strictly decodes the privacy-safe query and rejects storage locator drift', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(envelope(query));
    await expect(contractExternalSigningClient.query('CASE-001')).resolves.toEqual(query);
    expect(get).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-001/contract-external-signing',
      expect.objectContaining({ token: 'session-token' }),
    );

    vi.mocked(get).mockResolvedValueOnce(envelope({ ...query, storage_locator: '/mnt/contracts' }));
    await expect(contractExternalSigningClient.query('CASE-001')).rejects.toThrow();
  });

  it('records a staff completion report with expected versions and stable command identity', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue(envelope(reportReceipt));
    const identity = createExternalSigningCommandIdentity('staff-report');
    await expect(contractExternalSigningClient.recordStaffCompletionReport(
      'CASE-001',
      41,
      {
        expected_status_version: 3,
        expected_document_version_id: 31,
        confirmation_method: 'verified_other',
        reason: '已核對外部平台完成證據。',
      },
      identity,
    )).resolves.toEqual(reportReceipt);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-001/contract-external-signing/staff-segments/41/completion-reports',
      expect.objectContaining({ expected_status_version: 3, expected_document_version_id: 31 }),
      expect.objectContaining({
        token: 'session-token',
        headers: {
          'Idempotency-Key': identity.idempotencyKey,
          'X-Correlation-ID': identity.correlationId,
          'X-Receipt-ID': identity.receiptId,
        },
      }),
    );
  });

  it('keeps final Preview fingerprint private and uses an opaque preview token', async () => {
    const preview = {
      preview_token: `cp_${'A'.repeat(43)}`,
      staging_id: 'cfs_1234567890abcdef1234567890abcdef',
      expected_staging_version: 1,
      filename: 'final-signed.pdf',
      mime_type: 'application/pdf' as const,
      size_bytes: 20,
      blockers: [],
      can_apply: true as const,
    };
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope(preview));
    await expect(contractExternalSigningClient.previewFinalDocument('CASE-001', {
      staging_id: preview.staging_id,
      expected_status_version: 3,
    })).resolves.toEqual(preview);

    vi.mocked(post).mockResolvedValueOnce(envelope({ ...preview, preview_fingerprint: 'a'.repeat(64) }));
    await expect(contractExternalSigningClient.previewFinalDocument('CASE-001', {
      staging_id: preview.staging_id,
      expected_status_version: 3,
    })).rejects.toThrow();
  });

  it('uses contract-owned staging and rejects any digest leaking from its response', async () => {
    const staged = {
      staging_id: 'cfs_1234567890abcdef1234567890abcdef',
      filename: 'final-signed.pdf',
      mime_type: 'application/pdf' as const,
      size_bytes: 20,
      expires_at: '2026-08-26T10:30:00Z',
    };
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope(staged));
    const identity = createExternalSigningCommandIdentity('final-stage');
    const file = new File(['%PDF-1.7\n%%EOF'], staged.filename, { type: staged.mime_type });

    await expect(contractExternalSigningClient.stageFinalDocument('CASE-001', file, identity)).resolves.toEqual(staged);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-001/contract-external-signing/final-document/staging',
      expect.any(FormData),
      expect.objectContaining({
        headers: {
          'Idempotency-Key': identity.idempotencyKey,
          'X-Correlation-ID': identity.correlationId,
        },
      }),
    );

    vi.mocked(post).mockResolvedValueOnce(envelope({ ...staged, sha256_digest: 'a'.repeat(64) }));
    await expect(contractExternalSigningClient.stageFinalDocument('CASE-001', file, identity)).rejects.toThrow();
  });

  it('downloads only a current no-store PDF attachment with PDF magic and EOF', async () => {
    const pdf = new Blob(['%PDF-1.7\ncontract\n%%EOF'], { type: 'application/pdf' });
    const fetchStub = vi.fn().mockImplementation((_: string, init: RequestInit) => {
      const requestHeaders = new Headers(init.headers);
      return Promise.resolve(new Response(pdf, {
        status: 200,
        headers: {
          'content-type': 'application/pdf',
          'content-disposition': 'attachment; filename="CASE-001-unsigned.pdf"',
          'cache-control': 'no-store',
          'x-contract-document-version': '31',
          'x-correlation-id': requestHeaders.get('X-Correlation-ID') ?? '',
        },
      }));
    });
    vi.stubGlobal('fetch', fetchStub);

    await expect(contractExternalSigningClient.downloadUnsignedPdf('CASE-001', 31)).resolves.toMatchObject({
      filename: 'CASE-001-unsigned.pdf',
      mimeType: 'application/pdf',
    });
    expect(fetchStub).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-001/contract-external-signing/unsigned-pdf',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer session-token',
          'X-Expected-Document-Version': '31',
          'X-Correlation-ID': expect.stringMatching(/^contract-external-download-[0-9a-f]{32}$/),
        }),
      }),
    );
  });

  it('rejects a PDF response with a missing or mismatched correlation identity', async () => {
    const pdf = new Blob(['%PDF-1.7\ncontract\n%%EOF'], { type: 'application/pdf' });
    for (const responseCorrelation of [null, 'contract-external-download-wrong']) {
      const headers = new Headers({
        'content-type': 'application/pdf',
        'content-disposition': 'attachment; filename="CASE-001-unsigned.pdf"',
        'cache-control': 'no-store',
        'x-contract-document-version': '31',
      });
      if (responseCorrelation) headers.set('x-correlation-id', responseCorrelation);
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(pdf, { status: 200, headers })));

      await expect(contractExternalSigningClient.downloadUnsignedPdf('CASE-001', 31)).rejects.toThrow();
    }
  });

  it('rejects noncanonical Preview tokens in both Preview decode and Apply input', async () => {
    const post = vi.spyOn(transport, 'post');
    const invalidTokens = [
      `cp_${'A'.repeat(42)}`,
      `cp_${'A'.repeat(44)}`,
      `cp_${'A'.repeat(42)}+`,
      `cp_${'A'.repeat(42)}/`,
    ];
    const identity = createExternalSigningCommandIdentity('final-apply');

    for (const previewToken of invalidTokens) {
      post.mockResolvedValueOnce(envelope({
        preview_token: previewToken,
        staging_id: 'cfs_1234567890abcdef1234567890abcdef',
        expected_staging_version: 1,
        filename: 'final-signed.pdf',
        mime_type: 'application/pdf',
        size_bytes: 20,
        blockers: [],
        can_apply: true,
      }));
      await expect(contractExternalSigningClient.previewFinalDocument('CASE-001', {
        staging_id: 'cfs_1234567890abcdef1234567890abcdef',
        expected_status_version: 3,
      })).rejects.toThrow();
      await expect(contractExternalSigningClient.applyFinalDocument('CASE-001', {
        staging_id: 'cfs_1234567890abcdef1234567890abcdef',
        expected_staging_version: 1,
        preview_token: previewToken,
        expected_status_version: 3,
      }, identity)).rejects.toThrow();
    }
  });

  it('rejects impossible command, outcome, and resulting-state receipt unions', async () => {
    const get = vi.spyOn(transport, 'get');
    const impossibleReceipts = [
      { ...reportReceipt, outcome_state: 'completed' },
      {
        ...reportReceipt,
        command_type: 'record_client_report',
        resulting_state: 'staff_reports_complete',
        matching_segment_id: null,
      },
      {
        ...reportReceipt,
        command_type: 'apply_final_signed_contract',
        outcome_state: 'recorded',
        resulting_state: 'completed',
        matching_segment_id: null,
        final_document_id: 'cfd_1234567890abcdef1234567890abcdef',
      },
    ];

    for (const value of impossibleReceipts) {
      get.mockResolvedValueOnce(envelope(value));
      await expect(contractExternalSigningClient.getReceipt('CASE-001', reportReceipt.receipt_id)).rejects.toThrow();
    }
  });

  it('decodes every legitimate receipt command and resulting-state union', async () => {
    const legitimateReceipts = [
      reportReceipt,
      {
        ...reportReceipt,
        command_type: 'record_client_report',
        resulting_state: 'client_reported_final_pdf_pending',
        matching_segment_id: null,
      },
      {
        ...reportReceipt,
        command_type: 'apply_final_signed_contract',
        outcome_state: 'completed',
        resulting_state: 'completed',
        matching_segment_id: null,
        final_document_id: 'cfd_1234567890abcdef1234567890abcdef',
      },
    ];
    const get = vi.spyOn(transport, 'get');

    for (const receipt of legitimateReceipts) {
      get.mockResolvedValueOnce(envelope(receipt));
      await expect(contractExternalSigningClient.getReceipt('CASE-001', reportReceipt.receipt_id)).resolves.toEqual(receipt);
    }
  });

  it('queries a known receipt and final readback without raw cursor or path inputs', async () => {
    const readback = {
      case_no: 'CASE-001',
      session_id: sessionId,
      final_document_id: 'cfd_1234567890abcdef1234567890abcdef',
      controlled_file_id: 'cf_1234567890abcdef1234567890abcdef',
      version_number: 1,
      filename: 'final-signed.pdf',
      mime_type: 'application/pdf' as const,
      size_bytes: 20,
      status: 'completed' as const,
      integrity_verified: true as const,
      applied_at: '2026-08-26T10:00:00Z',
    };
    const get = vi.spyOn(transport, 'get')
      .mockResolvedValueOnce(envelope(reportReceipt))
      .mockResolvedValueOnce(envelope(readback));

    await expect(contractExternalSigningClient.getReceipt('CASE-001', reportReceipt.receipt_id)).resolves.toEqual(reportReceipt);
    await expect(contractExternalSigningClient.getFinalDocumentReadback('CASE-001')).resolves.toEqual(readback);
    expect(get.mock.calls.map(([path]) => path)).toEqual([
      `/api/v1/orders/CASE-001/contract-external-signing/receipts/${reportReceipt.receipt_id}`,
      '/api/v1/orders/CASE-001/contract-external-signing/final-document/readback',
    ]);
  });
});
