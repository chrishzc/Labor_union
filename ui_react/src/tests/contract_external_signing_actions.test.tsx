/**
 * File: contract_external_signing_actions.test.tsx
 * Description: 驗證外部簽約 closed-state UI、最終 PDF 明確確認、receipt reconciliation 與隱私不變量。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiTimeoutError } from '../api/shared/typed_errors';
import { ContractExternalSigningActions } from '../components/ContractExternalSigningActions';
import { contractExternalSigningClient } from '../api/orders/contract_external_signing_client';

vi.mock('../api/orders/contract_external_signing_client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/orders/contract_external_signing_client')>();
  return {
    ...original,
    contractExternalSigningClient: {
      query: vi.fn(),
      downloadUnsignedPdf: vi.fn(),
      recordStaffCompletionReport: vi.fn(),
      recordClientCompletionReport: vi.fn(),
      stageFinalDocument: vi.fn(),
      previewFinalDocument: vi.fn(),
      applyFinalDocument: vi.fn(),
      getReceipt: vi.fn(),
      getFinalDocumentReadback: vi.fn(),
    },
  };
});

const sessionId = 'ces_1234567890abcdef1234567890abcdef';
const query = {
  case_no: 'CASE-001',
  session_id: sessionId,
  state: 'client_reported_final_pdf_pending' as const,
  status_version: 5,
  matching_plan_id: 17,
  commitment_id: 44,
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
    reported: true,
  }],
  client_target: {
    client_subject_reference: 'CLIENT-001',
    document_version_id: 32,
    reported: true,
  },
};

const staged = {
  staging_id: 'cfs_1234567890abcdef1234567890abcdef',
  filename: 'final-signed.pdf',
  mime_type: 'application/pdf' as const,
  size_bytes: 20,
  expires_at: '2026-08-27T10:00:00Z',
};

const preview = {
  preview_token: `cp_${'A'.repeat(43)}`,
  staging_id: staged.staging_id,
  expected_staging_version: 1,
  filename: staged.filename,
  mime_type: 'application/pdf' as const,
  size_bytes: staged.size_bytes,
  blockers: [],
  can_apply: true as const,
};

const receipt = {
  receipt_id: 'cesr_1234567890abcdef1234567890abcdef',
  command_type: 'apply_final_signed_contract' as const,
  schema_version: 'contract-external-signing-receipt.v1' as const,
  session_id: sessionId,
  outcome_state: 'completed' as const,
  resulting_status_version: 6,
  resulting_state: 'completed' as const,
  matching_segment_id: null,
  final_document_id: 'cfd_1234567890abcdef1234567890abcdef',
  replayed: false,
  applied_at: '2026-08-26T10:00:00Z',
};

const readback = {
  case_no: 'CASE-001',
  session_id: sessionId,
  final_document_id: receipt.final_document_id,
  controlled_file_id: 'cf_1234567890abcdef1234567890abcdef',
  version_number: 1,
  filename: 'final-signed.pdf',
  mime_type: 'application/pdf' as const,
  size_bytes: 20,
  status: 'completed' as const,
  integrity_verified: true as const,
  applied_at: '2026-08-26T10:00:00Z',
};

const fileList = (file: File) => ({ 0: file, length: 1, item: (index: number) => index === 0 ? file : null });

describe('ContractExternalSigningActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(query);
    vi.mocked(contractExternalSigningClient.downloadUnsignedPdf).mockResolvedValue({
      blob: new Blob(['%PDF-1.7\n%%EOF'], { type: 'application/pdf' }),
      filename: 'target-unsigned.pdf',
      mimeType: 'application/pdf',
    });
    vi.mocked(contractExternalSigningClient.stageFinalDocument).mockResolvedValue(staged);
    vi.mocked(contractExternalSigningClient.previewFinalDocument).mockResolvedValue(preview);
    vi.mocked(contractExternalSigningClient.applyFinalDocument).mockResolvedValue(receipt);
    vi.mocked(contractExternalSigningClient.getFinalDocumentReadback).mockResolvedValue(readback);
  });

  it('offers explicit unsigned PDF downloads for every staff target and the client target', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({
      ...query,
      staff_targets: [
        query.staff_targets[0],
        {
          matching_segment_id: 42,
          staff_subject_reference: 'STAFF-010',
          document_version_id: 33,
          reported: true,
        },
      ],
    });
    const createObjectURL = vi.fn().mockReturnValue('blob:unsigned-contract');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '下載月嫂 STAFF-009 未簽契約 PDF' }));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith('CASE-001', 31));
    fireEvent.click(screen.getByRole('button', { name: '下載月嫂 STAFF-010 未簽契約 PDF' }));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith('CASE-001', 33));
    fireEvent.click(screen.getByRole('button', { name: '下載客戶 CLIENT-001 未簽契約 PDF' }));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith('CASE-001', 32));

    expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledTimes(3);
    expect(createObjectURL).toHaveBeenCalledTimes(3);
    expect(revokeObjectURL).toHaveBeenCalledTimes(3);
    expect(click).toHaveBeenCalledTimes(3);
    expect(document.body.textContent).not.toMatch(/https?:\/\//i);
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{64}/i);
  });

  it('requires final PDF staging and Preview plus explicit confirmation before Apply/readback', async () => {
    const onCommitted = vi.fn();
    render(<ContractExternalSigningActions caseNo="CASE-001" onCommitted={onCommitted} />);
    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });

    const file = new File(['%PDF-1.7\ncontract\n%%EOF'], 'final-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('最終簽署 PDF'), { target: { files: fileList(file) } });
    fireEvent.click(screen.getByRole('button', { name: '建立最終 PDF 預覽' }));

    await screen.findByText(/完整性已由後端驗證/);
    const apply = screen.getByRole('button', { name: '確認套用最終簽署 PDF' });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByLabelText('我已核對案件、檔名、PDF 類型與版本'));
    expect(apply).toBeEnabled();
    fireEvent.click(apply);

    await screen.findByText(/契約完成，最終 PDF 已完成 readback/);
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledWith(
      'CASE-001',
      expect.objectContaining({
        staging_id: staged.staging_id,
        expected_staging_version: 1,
        preview_token: preview.preview_token,
        expected_status_version: 5,
      }),
      expect.objectContaining({ idempotencyKey: expect.any(String), receiptId: expect.any(String) }),
    );
    expect(onCommitted).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).not.toContain(preview.preview_token);
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{64}/);
    expect(document.body.textContent).not.toContain('/mnt/');
  });

  it('invalidates a final Preview when the selected file changes', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });
    const first = new File(['%PDF-1.7\nfirst\n%%EOF'], 'first.pdf', { type: 'application/pdf' });
    const second = new File(['%PDF-1.7\nsecond\n%%EOF'], 'second.pdf', { type: 'application/pdf' });
    const input = screen.getByLabelText('最終簽署 PDF');
    fireEvent.change(input, { target: { files: fileList(first) } });
    fireEvent.click(screen.getByRole('button', { name: '建立最終 PDF 預覽' }));
    await screen.findByText(/完整性已由後端驗證/);

    fireEvent.change(input, { target: { files: fileList(second) } });
    expect(screen.queryByRole('button', { name: '確認套用最終簽署 PDF' })).not.toBeInTheDocument();
  });

  it('reconciles an outcome-unknown Apply by receipt identity without resubmitting', async () => {
    vi.mocked(contractExternalSigningClient.applyFinalDocument).mockRejectedValueOnce(new ApiTimeoutError(10000));
    vi.mocked(contractExternalSigningClient.getReceipt).mockResolvedValueOnce(receipt);
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });
    const file = new File(['%PDF-1.7\ncontract\n%%EOF'], 'final-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('最終簽署 PDF'), { target: { files: fileList(file) } });
    fireEvent.click(screen.getByRole('button', { name: '建立最終 PDF 預覽' }));
    await screen.findByText(/完整性已由後端驗證/);
    fireEvent.click(screen.getByLabelText('我已核對案件、檔名、PDF 類型與版本'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用最終簽署 PDF' }));

    await screen.findByText(/結果未明/);
    fireEvent.click(screen.getByRole('button', { name: '以原命令查詢 receipt' }));
    await screen.findByText(/契約完成，最終 PDF 已完成 readback/);
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.getReceipt).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.getReceipt).toHaveBeenCalledWith(
      'CASE-001',
      expect.stringMatching(/^cesr_[0-9a-f]{32}$/),
    );
  });

  it('keeps client report unavailable until every staff report is complete', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce({
      ...query,
      state: 'staff_reporting',
      status_version: 2,
      commitment_id: null,
      staff_targets: [{ ...query.staff_targets[0], reported: false }],
      client_target: { ...query.client_target, reported: false },
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByText(/等待月嫂完成回報/);
    expect(screen.getByRole('button', { name: /記錄月嫂.*完成回報/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /記錄客戶完成回報/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('受控 HTTPS 文件下載網址')).not.toBeInTheDocument();
  });
});
