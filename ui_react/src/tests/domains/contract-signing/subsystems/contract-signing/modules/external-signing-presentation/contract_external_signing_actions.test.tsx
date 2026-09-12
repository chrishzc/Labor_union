/**
 * File: contract_external_signing_actions.test.tsx
 * Description: 驗證外部簽約 closed-state UI、最終 PDF 明確確認、receipt reconciliation 與隱私不變量。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHttpError, ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';
import { ContractExternalSigningActions } from '../../../../../../../components/ContractExternalSigningActions';
import { contractExternalSigningClient } from '../../../../../../../api/orders/contract_external_signing_client';
import { contractSigningClient } from '../../../../../../../api/orders/contract_signing_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

vi.mock('../../../../../../../api/orders/contract_external_signing_client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../../../../../../api/orders/contract_external_signing_client')>();
  return {
    ...original,
    contractExternalSigningClient: {
      query: vi.fn(),
      prepareStaffUnsignedPdf: vi.fn(),
      prepareClientUnsignedPdf: vi.fn(),
      getStaffReminderReadiness: vi.fn(),
      enqueueStaffReminder: vi.fn(),
      recordHandoff: vi.fn(),
      queryLegacyRecovery: vi.fn(),
      previewLegacyRecovery: vi.fn(),
      applyLegacyRecovery: vi.fn(),
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

vi.mock('../../../../../../../api/orders/contract_signing_client', () => ({
  contractSigningClient: { query: vi.fn() },
}));

const sessionId = 'ces_1234567890abcdef1234567890abcdef';
const query = {
  case_no: 'CASE-001',
  session_id: sessionId,
  state: 'client_reported_final_pdf_pending' as const,
  status_version: 5,
  handoff_recorded: true,
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

const recoveryQuery = {
  case_no: query.case_no,
  session_id: query.session_id,
  matching_plan_id: query.matching_plan_id,
  current_document_set_sha256: 'a'.repeat(64),
  commitment_id: query.commitment_id,
  state: query.state,
  status_version: query.status_version,
  targets: [
    {
      scope: 'staff' as const,
      matching_segment_id: 41,
      target_subject_reference: 'STAFF-009',
      current_document_version_id: 31,
      reported: true,
      legacy_document_version_id: 21,
      signing_event_id: 51,
      command_receipt_id: 61,
      legacy_media_sha256: 'b'.repeat(64),
    },
    {
      scope: 'client' as const,
      matching_segment_id: null,
      target_subject_reference: 'CLIENT-001',
      current_document_version_id: 32,
      reported: true,
      legacy_document_version_id: 22,
      signing_event_id: 52,
      command_receipt_id: 62,
      legacy_media_sha256: 'c'.repeat(64),
    },
  ],
};

const completedQuery = {
  ...query,
  state: 'completed' as const,
  status_version: 6,
};

const completedRecoveryQuery = {
  ...recoveryQuery,
  state: 'completed' as const,
  status_version: 6,
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

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function supersededQuery(caseNo: string) {
  return {
    ...query,
    case_no: caseNo,
    state: 'superseded' as const,
    unsigned_document: { ...query.unsigned_document!, filename: `${caseNo}-unsigned.pdf` },
  };
}

async function assertLateUnsignedPdfAbortOnRemount(
  buttonName: string,
  oldFilename: string,
) {
  const download = deferred<{ blob: Blob; filename: string; mimeType: 'application/pdf' }>();
  vi.mocked(contractExternalSigningClient.query)
    .mockResolvedValueOnce(supersededQuery('115000291'))
    .mockResolvedValueOnce(supersededQuery('115000292'));
  vi.mocked(contractExternalSigningClient.downloadUnsignedPdf).mockReturnValueOnce(download.promise);
  vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:unsigned'), revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  const { rerender } = render(<ContractExternalSigningActions key="115000291" caseNo="115000291" />);
  fireEvent.click(await screen.findByRole('button', { name: buttonName }));
  await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledTimes(1));
  const signal = vi.mocked(contractExternalSigningClient.downloadUnsignedPdf).mock.calls[0]?.[2];

  rerender(<ContractExternalSigningActions key="115000292" caseNo="115000292" />);
  expect(signal?.aborted).toBe(true);
  await act(async () => {
    download.resolve({ blob: new Blob(['%PDF-1.7\n%%EOF']), filename: oldFilename, mimeType: 'application/pdf' });
    await Promise.resolve();
  });

  expect(click).not.toHaveBeenCalled();
  expect(screen.queryByText(new RegExp(oldFilename.replace('.', '\\.')))).not.toBeInTheDocument();
}

async function assertNewUnsignedPdfSurvivesCaseSwitch(
  buttonName: string,
  oldFilename: string,
  newFilename: string,
) {
  const firstDownload = deferred<{ blob: Blob; filename: string; mimeType: 'application/pdf' }>();
  vi.mocked(contractExternalSigningClient.query)
    .mockResolvedValueOnce(supersededQuery('115000291'))
    .mockResolvedValueOnce(supersededQuery('115000292'));
  vi.mocked(contractExternalSigningClient.downloadUnsignedPdf)
    .mockReturnValueOnce(firstDownload.promise)
    .mockResolvedValueOnce({ blob: new Blob(['%PDF-1.7\n%%EOF']), filename: newFilename, mimeType: 'application/pdf' });
  vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:unsigned'), revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  const { rerender } = render(<ContractExternalSigningActions caseNo="115000291" />);
  fireEvent.click(await screen.findByRole('button', { name: buttonName }));
  await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledTimes(1));
  const firstSignal = vi.mocked(contractExternalSigningClient.downloadUnsignedPdf).mock.calls[0]?.[2];

  rerender(<ContractExternalSigningActions caseNo="115000292" />);
  fireEvent.click(await screen.findByRole('button', { name: buttonName }));
  expect(firstSignal?.aborted).toBe(true);
  expect(await screen.findByText(new RegExp(newFilename.replace('.', '\\.')))).toBeInTheDocument();
  await act(async () => {
    firstDownload.resolve({ blob: new Blob(['%PDF-1.7\n%%EOF']), filename: oldFilename, mimeType: 'application/pdf' });
    await Promise.resolve();
  });

  expect(screen.queryByText(new RegExp(oldFilename.replace('.', '\\.')))).not.toBeInTheDocument();
  expect(click).toHaveBeenCalledTimes(1);
}

function handoffRecoveryQuery(caseNo: string, statusVersion = 0) {
  return {
    ...recoveryQuery,
    case_no: caseNo,
    state: 'staff_reporting' as const,
    status_version: statusVersion,
    commitment_id: null,
    targets: recoveryQuery.targets.map((target) => ({ ...target, reported: false })),
  };
}

describe('ContractExternalSigningActions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    orderMutationFlowStore.clearAll();
    sessionClient.setSession('external-signing-test-token', {
      id: 1,
      username: 'external-signing-tester',
      display_name: '外部簽約測試管理員',
      role: 'operator',
      linked_line_user_id: null,
      capabilities: [],
      is_root: false,
      access_control_version: 1,
    });
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(query);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValue(recoveryQuery);
    vi.mocked(contractExternalSigningClient.recordHandoff).mockResolvedValue({
      session_id: sessionId,
      resulting_status_version: 1,
      replayed: false,
    });
    vi.mocked(contractExternalSigningClient.downloadUnsignedPdf).mockResolvedValue({
      blob: new Blob(['%PDF-1.7\n%%EOF'], { type: 'application/pdf' }),
      filename: 'target-unsigned.pdf',
      mimeType: 'application/pdf',
    });
    vi.mocked(contractExternalSigningClient.prepareStaffUnsignedPdf).mockResolvedValue({
      document_version_id: 31,
      filename: 'CASE-001-unsigned.pdf',
      mime_type: 'application/pdf',
      size_bytes: 20,
      replayed: false,
    });
    vi.mocked(contractExternalSigningClient.getStaffReminderReadiness).mockResolvedValue({
      matching_segment_id: 41,
      document_version_id: 31,
      message: '案件 CASE-001 的契約已放到工會既定的外部簽約平台；請前往該平台完成簽署。',
      blockers: [],
      ready: true,
    });
    vi.mocked(contractExternalSigningClient.enqueueStaffReminder).mockResolvedValue({
      task_id: 91,
      status: 'pending',
      replayed: false,
    });
    vi.mocked(contractExternalSigningClient.stageFinalDocument).mockResolvedValue(staged);
    vi.mocked(contractExternalSigningClient.previewFinalDocument).mockResolvedValue(preview);
    vi.mocked(contractExternalSigningClient.applyFinalDocument).mockImplementation(async (_caseNo, _input, identity) => ({
      ...receipt,
      receipt_id: identity.receiptId,
    }));
    vi.mocked(contractExternalSigningClient.getFinalDocumentReadback).mockResolvedValue(readback);
  });

  afterEach(() => {
    sessionClient.clearSession();
    orderMutationFlowStore.clearAll();
  });

  it('aborts a late unsigned-PDF download when the case is remounted', async () => {
    await assertLateUnsignedPdfAbortOnRemount(
      '下載服務人員契約 PDF（STAFF-009）',
      '115000291-unsigned.pdf',
    );
  });

  it('keeps the new case download when the prior case completes late', async () => {
    await assertNewUnsignedPdfSurvivesCaseSwitch(
      '下載服務人員契約 PDF（STAFF-009）',
      '115000291-unsigned.pdf',
      '115000292-unsigned.pdf',
    );
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
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValue({
      ...recoveryQuery,
      targets: [
        recoveryQuery.targets[0],
        {
          ...recoveryQuery.targets[0],
          matching_segment_id: 42,
          target_subject_reference: 'STAFF-010',
          current_document_version_id: 33,
          signing_event_id: 53,
          command_receipt_id: 63,
        },
        recoveryQuery.targets[1],
      ],
    });
    const createObjectURL = vi.fn().mockReturnValue('blob:unsigned-contract');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '下載服務人員契約 PDF（STAFF-009）' }));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith('CASE-001', 31, expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole('button', { name: '下載服務人員契約 PDF（STAFF-010）' }));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith('CASE-001', 33, expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole('button', { name: '下載客戶契約 PDF' }));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith('CASE-001', 32, expect.any(AbortSignal)));

    expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledTimes(3);
    expect(createObjectURL).toHaveBeenCalledTimes(3);
    expect(revokeObjectURL).toHaveBeenCalledTimes(3);
    expect(click).toHaveBeenCalledTimes(3);
    expect(document.body.textContent).not.toMatch(/https?:\/\//i);
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{64}/i);
  });

  it('offers PDF preparation for an accepted signing session that has no unsigned PDF yet', async () => {
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce({
        ...query,
        unsigned_document: null,
        handoff_recorded: false,
        status_version: 0,
        client_target: { ...query.client_target, document_version_id: null, reported: false },
      })
      .mockResolvedValueOnce(query);

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '準備服務人員契約 PDF（服務區段 41）' }));

    await waitFor(() => expect(contractExternalSigningClient.prepareStaffUnsignedPdf).toHaveBeenCalledWith(
      'CASE-001',
      41,
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    ));
    expect(await screen.findByText('已產生月嫂分段 #41 未簽 PDF。')).toBeInTheDocument();
  });

  it('prepares the first staff PDF before a signing session can be derived', async () => {
    vi.mocked(contractExternalSigningClient.query)
      .mockRejectedValueOnce(new ApiHttpError(409, 'external_signing_session_facts_unavailable', 'facts unavailable'))
      .mockResolvedValueOnce(query);
    vi.mocked(contractSigningClient.query).mockResolvedValueOnce({
      staff_segments: [{ segment_id: 41 }],
    } as Awaited<ReturnType<typeof contractSigningClient.query>>);

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByRole('button', { name: '準備並下載客戶契約 PDF' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '準備服務人員契約 PDF（服務區段 41）' }));

    await waitFor(() => expect(contractExternalSigningClient.prepareStaffUnsignedPdf).toHaveBeenCalledWith(
      'CASE-001',
      41,
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    ));
    expect(await screen.findByText('已產生月嫂分段 #41 未簽 PDF。')).toBeInTheDocument();
  });

  it('keeps the next staff segment available while the full signing session is still incomplete', async () => {
    vi.mocked(contractExternalSigningClient.query)
      .mockRejectedValue(new ApiHttpError(409, 'external_signing_session_facts_unavailable', 'facts unavailable'));
    vi.mocked(contractSigningClient.query)
      .mockResolvedValueOnce({
        case_no: 'CASE-001',
        staff_segments: [{ segment_id: 41 }, { segment_id: 42 }],
        documents: [],
      } as unknown as Awaited<ReturnType<typeof contractSigningClient.query>>)
      .mockResolvedValueOnce({
        case_no: 'CASE-001',
        staff_segments: [{ segment_id: 41 }, { segment_id: 42 }],
        documents: [{ document_version_id: 31, scope: 'staff' }],
      } as unknown as Awaited<ReturnType<typeof contractSigningClient.query>>);

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '準備服務人員契約 PDF（服務區段 41）' }));

    expect(await screen.findByText('已產生月嫂分段 #41 未簽 PDF。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '準備服務人員契約 PDF（服務區段 42）' })).toBeEnabled();
  });

  it('prepares and downloads the exact client PDF when there was no old document', async () => {
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce({
        ...query, unsigned_document: null,
        client_target: { ...query.client_target, document_version_id: null },
      })
      .mockResolvedValueOnce({
        ...query,
        unsigned_document: { document_version_id: 92, filename: 'new-client.pdf', mime_type: 'application/pdf', size_bytes: 20 },
        client_target: { ...query.client_target, document_version_id: 92 },
      });
    vi.mocked(contractExternalSigningClient.prepareClientUnsignedPdf).mockResolvedValue({
      document_version_id: 92, filename: 'new-client.pdf', mime_type: 'application/pdf', size_bytes: 20, replayed: false,
    });
    const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:client'), revokeObjectURL: vi.fn() });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '準備並下載客戶契約 PDF' }));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith(
      'CASE-001', 92, expect.any(AbortSignal),
    ));
    expect(download).toHaveBeenCalled();
  });

  it('explains the missing accepted plan instead of suggesting a version retry', async () => {
    vi.mocked(contractExternalSigningClient.query).mockRejectedValueOnce(new ApiHttpError(409, 'external_signing_accepted_plan_required', 'plan required'));
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('請先完成客戶對推薦方案的確認，再準備契約。');
    expect(screen.getByRole('button', { name: '下載客戶契約 PDF' })).toBeDisabled();
  });

  it('shows the URL-less LINE reminder text and readiness without sending it', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);

    fireEvent.click(await screen.findByRole('button', { name: '檢查月嫂 STAFF-009 LINE 通知準備度' }));

    expect(await screen.findByText(/案件 CASE-001 的契約已放到工會既定的外部簽約平台/)).toBeInTheDocument();
    expect(screen.getByText('通知內容與收件綁定均已就緒；尚未建立或送出通知。')).toBeInTheDocument();
    expect(contractExternalSigningClient.getStaffReminderReadiness).toHaveBeenCalledWith('CASE-001', 41, expect.any(AbortSignal));
  });

  it('creates a pending LINE reminder task only after readiness is explicitly checked', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);

    expect(screen.queryByRole('button', { name: /建立月嫂 STAFF-009 LINE 契約通知工作/ })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: '檢查月嫂 STAFF-009 LINE 通知準備度' }));
    const enqueue = await screen.findByRole('button', { name: '建立月嫂 STAFF-009 LINE 契約通知工作（不立即傳送）' });
    fireEvent.click(enqueue);

    await waitFor(() => expect(contractExternalSigningClient.enqueueStaffReminder).toHaveBeenCalledWith(
      'CASE-001',
      41,
      31,
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    ));
    expect(await screen.findByText('已建立月嫂 STAFF-009 的 LINE 契約通知工作 #91；尚未傳送。')).toBeInTheDocument();
  });

  it('requires final PDF staging and Preview plus explicit confirmation before Apply/readback', async () => {
    const onCommitted = vi.fn();
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce(query)
      .mockResolvedValueOnce(completedQuery);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery)
      .mockResolvedValueOnce(recoveryQuery)
      .mockResolvedValueOnce(completedRecoveryQuery);
    render(<ContractExternalSigningActions caseNo="CASE-001" onCommitted={onCommitted} />);
    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });

    const file = new File(['%PDF-1.7\ncontract\n%%EOF'], 'final-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('最終簽署 PDF'), { target: { files: fileList(file) } });
    fireEvent.click(screen.getByRole('button', { name: '建立最終 PDF 預覽' }));

    await screen.findByText(/PDF 類型與完整性已確認/);
    const apply = screen.getByRole('button', { name: '確認套用最終簽署 PDF' });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/我已核對案件、檔名、PDF 類型、版本/));
    expect(apply).toBeEnabled();
    fireEvent.click(apply);

    await screen.findByText(/契約完成，最終 PDF 第 1 版已確認/);
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
    expect(contractExternalSigningClient.query).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('region', { name: '最終簽署 PDF 納管' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(preview.preview_token);
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{64}/);
    expect(document.body.textContent).not.toContain('/mnt/');
  });

  it('fails closed when the initial completed readback belongs to another case', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(completedQuery);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValueOnce(completedRecoveryQuery);
    vi.mocked(contractExternalSigningClient.getFinalDocumentReadback).mockResolvedValueOnce({
      ...readback,
      case_no: 'OTHER-CASE',
    });

    render(<ContractExternalSigningActions caseNo="CASE-001" />);

    expect(await screen.findByRole('alert')).toHaveTextContent(/案件識別不一致/);
    expect(screen.queryByText(/最終 PDF 第 1 版已確認完成/)).not.toBeInTheDocument();
  });

  it('fails closed when the initial completed readback belongs to another signing session', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(completedQuery);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValueOnce(completedRecoveryQuery);
    vi.mocked(contractExternalSigningClient.getFinalDocumentReadback).mockResolvedValueOnce({
      ...readback,
      session_id: 'ces_abcdefabcdefabcdefabcdefabcdefab',
    });

    render(<ContractExternalSigningActions caseNo="CASE-001" />);

    expect(await screen.findByRole('alert')).toHaveTextContent(/與目前簽約工作不一致/);
    expect(screen.queryByText(/最終 PDF 第 1 版已確認完成/)).not.toBeInTheDocument();
  });

  it('fails closed when the post-Apply readback belongs to another case', async () => {
    vi.mocked(contractExternalSigningClient.getFinalDocumentReadback).mockResolvedValueOnce({
      ...readback,
      case_no: 'OTHER-CASE',
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });
    const file = new File(['%PDF-1.7\ncontract\n%%EOF'], 'final-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('最終簽署 PDF'), { target: { files: fileList(file) } });
    fireEvent.click(screen.getByRole('button', { name: '建立最終 PDF 預覽' }));
    await screen.findByText(/PDF 類型與完整性已確認/);
    fireEvent.click(screen.getByLabelText(/我已核對案件、檔名、PDF 類型、版本/));
    fireEvent.click(screen.getByRole('button', { name: '確認套用最終簽署 PDF' }));

    expect(await screen.findByText(/完成結果尚未確認/)).toBeInTheDocument();
    expect(screen.queryByText(/契約完成，最終 PDF 第 1 版已確認/)).not.toBeInTheDocument();
  });

  it('invalidates a final Preview when the selected file changes', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });
    const first = new File(['%PDF-1.7\nfirst\n%%EOF'], 'first.pdf', { type: 'application/pdf' });
    const second = new File(['%PDF-1.7\nsecond\n%%EOF'], 'second.pdf', { type: 'application/pdf' });
    const input = screen.getByLabelText('最終簽署 PDF');
    fireEvent.change(input, { target: { files: fileList(first) } });
    fireEvent.click(screen.getByRole('button', { name: '建立最終 PDF 預覽' }));
    await screen.findByText(/PDF 類型與完整性已確認/);

    fireEvent.change(input, { target: { files: fileList(second) } });
    expect(screen.queryByRole('button', { name: '確認套用最終簽署 PDF' })).not.toBeInTheDocument();
  });

  it('reconciles an outcome-unknown Apply by receipt identity without resubmitting', async () => {
    vi.mocked(contractExternalSigningClient.applyFinalDocument).mockRejectedValueOnce(new ApiTimeoutError(10000));
    vi.mocked(contractExternalSigningClient.getReceipt).mockImplementationOnce(async (_caseNo, receiptId) => ({ ...receipt, receipt_id: receiptId }));
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce(query)
      .mockResolvedValueOnce(completedQuery);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery)
      .mockResolvedValueOnce(recoveryQuery)
      .mockResolvedValueOnce(completedRecoveryQuery);
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });
    const file = new File(['%PDF-1.7\ncontract\n%%EOF'], 'final-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('最終簽署 PDF'), { target: { files: fileList(file) } });
    fireEvent.click(screen.getByRole('button', { name: '建立最終 PDF 預覽' }));
    await screen.findByText(/PDF 類型與完整性已確認/);
    fireEvent.click(screen.getByLabelText(/我已核對案件、檔名、PDF 類型、版本/));
    fireEvent.click(screen.getByRole('button', { name: '確認套用最終簽署 PDF' }));

    await screen.findByText(/結果未明/);
    fireEvent.click(screen.getByRole('button', { name: '重新確認原操作結果' }));
    await screen.findByText(/契約完成，最終 PDF 第 1 版已確認/);
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.getReceipt).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.getReceipt).toHaveBeenCalledWith(
      'CASE-001',
      expect.stringMatching(/^cesr_[0-9a-f]{32}$/),
    );
  });

  it('keeps an outcome unknown when the queried receipt has an unexpected status version', async () => {
    vi.mocked(contractExternalSigningClient.applyFinalDocument).mockRejectedValueOnce(new ApiTimeoutError(10000));
    vi.mocked(contractExternalSigningClient.getReceipt).mockImplementationOnce(async (_caseNo, receiptId) => ({
      ...receipt,
      receipt_id: receiptId,
      resulting_status_version: 999,
    }));
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });
    const file = new File(['%PDF-1.7\ncontract\n%%EOF'], 'final-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('最終簽署 PDF'), { target: { files: fileList(file) } });
    fireEvent.click(screen.getByRole('button', { name: '建立最終 PDF 預覽' }));
    await screen.findByText(/PDF 類型與完整性已確認/);
    fireEvent.click(screen.getByLabelText(/我已核對案件、檔名、PDF 類型、版本/));
    fireEvent.click(screen.getByRole('button', { name: '確認套用最終簽署 PDF' }));

    await screen.findByText(/結果未明/);
    fireEvent.click(screen.getByRole('button', { name: '重新確認原操作結果' }));

    expect(await screen.findByText(/受理結果與原操作識別不一致/)).toBeInTheDocument();
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.getReceipt).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.getFinalDocumentReadback).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.query).toHaveBeenCalledTimes(1);
  });

  it('records the external-platform handoff before enabling final PDF acceptance', async () => {
    const beforeHandoff = {
      ...query,
      state: 'staff_reporting' as const,
      status_version: 0,
      handoff_recorded: false,
      commitment_id: null,
      staff_targets: [{ ...query.staff_targets[0], reported: false }],
      client_target: { ...query.client_target, reported: false },
    };
    const afterHandoff = { ...beforeHandoff, status_version: 1, handoff_recorded: true };
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce(beforeHandoff)
      .mockResolvedValueOnce(afterHandoff);
    const recoveryBeforeHandoff = {
      ...recoveryQuery,
      state: beforeHandoff.state,
      status_version: beforeHandoff.status_version,
      commitment_id: null,
      targets: recoveryQuery.targets.map((target) => ({ ...target, reported: false })),
    };
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery)
      .mockResolvedValueOnce(recoveryBeforeHandoff)
      .mockResolvedValueOnce({ ...recoveryBeforeHandoff, status_version: 1 });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByText('待送交外部簽署平台')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '最終簽署 PDF 納管' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '確認契約已送交外部簽署平台' }));

    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });
    expect(contractExternalSigningClient.recordHandoff).toHaveBeenCalledWith(
      'CASE-001',
      0,
      expect.objectContaining({ idempotencyKey: expect.any(String), receiptId: expect.any(String) }),
    );
    expect(screen.queryByText(/選用稽核資料/)).not.toBeInTheDocument();
  });

  it('reuses the original handoff identity after an outcome-unknown timeout', async () => {
    const beforeHandoff = handoffRecoveryQuery('CASE-001');
    const afterHandoff = { ...beforeHandoff, status_version: 1, handoff_recorded: true };
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce({
        ...query,
        state: 'staff_reporting',
        status_version: 0,
        handoff_recorded: false,
        commitment_id: null,
        staff_targets: [{ ...query.staff_targets[0], reported: false }],
        client_target: { ...query.client_target, reported: false },
      })
      .mockResolvedValueOnce({
        ...query,
        state: 'staff_reporting',
        status_version: 1,
        handoff_recorded: true,
        commitment_id: null,
        staff_targets: [{ ...query.staff_targets[0], reported: false }],
        client_target: { ...query.client_target, reported: false },
      });
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery)
      .mockResolvedValueOnce(beforeHandoff)
      .mockResolvedValueOnce(afterHandoff);
    vi.mocked(contractExternalSigningClient.recordHandoff)
      .mockRejectedValueOnce(new ApiTimeoutError(10000))
      .mockResolvedValueOnce({ session_id: sessionId, resulting_status_version: 1, replayed: true });

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '確認契約已送交外部簽署平台' }));
    fireEvent.click(await screen.findByRole('button', { name: '以原交接操作重新確認' }));

    await screen.findByRole('region', { name: '最終簽署 PDF 納管' });
    expect(contractExternalSigningClient.recordHandoff).toHaveBeenCalledTimes(2);
    expect(vi.mocked(contractExternalSigningClient.recordHandoff).mock.calls[1]?.[2]).toEqual(
      vi.mocked(contractExternalSigningClient.recordHandoff).mock.calls[0]?.[2],
    );
  });

  it('completes one historical staff recovery and enables the client only after fresh server readback', async () => {
    const staffCurrent = {
      ...query,
      state: 'staff_reporting' as const,
      status_version: 3,
      commitment_id: null,
      staff_targets: [{ ...query.staff_targets[0], reported: false }],
      client_target: { ...query.client_target, reported: false },
    };
    const staffFresh = {
      ...staffCurrent,
      state: 'staff_reports_complete' as const,
      status_version: 4,
      commitment_id: 44,
      staff_targets: [{ ...staffCurrent.staff_targets[0], reported: true }],
    };
    const legacyCurrent = {
      ...recoveryQuery,
      state: 'staff_reporting' as const,
      status_version: 3,
      commitment_id: null,
      targets: recoveryQuery.targets.map((target) => ({ ...target, reported: false })),
    };
    const legacyFresh = {
      ...legacyCurrent,
      state: 'staff_reports_complete' as const,
      status_version: 4,
      commitment_id: 44,
      targets: legacyCurrent.targets.map((target) => target.scope === 'staff' ? { ...target, reported: true } : target),
    };
    const recoveryPreview = {
      preview_fingerprint: 'd'.repeat(64),
      session_id: sessionId,
      expected_status_version: 3,
      scope: 'staff' as const,
      matching_segment_id: 41,
      current_document_version_id: 31,
      current_document_set_sha256: legacyCurrent.current_document_set_sha256,
      current_commitment_id: null,
      legacy_media_sha256: legacyCurrent.targets[0].legacy_media_sha256!,
      blockers: [],
      can_apply: true,
    };
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce(staffCurrent)
      .mockResolvedValueOnce(staffFresh);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery)
      .mockResolvedValueOnce(legacyCurrent)
      .mockResolvedValueOnce(legacyFresh);
    vi.mocked(contractExternalSigningClient.previewLegacyRecovery).mockResolvedValue(recoveryPreview);
    vi.mocked(contractExternalSigningClient.applyLegacyRecovery).mockImplementation(async (_caseNo, _input, identity) => ({
      ...receipt,
      receipt_id: identity.receiptId,
      command_type: 'record_staff_report',
      outcome_state: 'recorded',
      resulting_status_version: 4,
      resulting_state: 'staff_reports_complete',
      matching_segment_id: 41,
      final_document_id: null,
    }));

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const staffRegion = await screen.findByRole('article', { name: '月嫂 STAFF-009 歷史簽回修復' });
    expect(screen.getByRole('button', { name: '檢查客戶歷史簽回修復影響' })).toBeDisabled();
    fireEvent.change(screen.getAllByLabelText('修復原因與人工核對依據')[0], { target: { value: '依受控歷史紙本核對完成' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查月嫂歷史簽回修復影響' }));
    await screen.findByText(/現行文件與歷史簽回證據已完成一致性檢查/);
    fireEvent.click(screen.getByLabelText('我已核對案件、對象、現行文件與歷史簽回證據'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用此筆歷史簽回修復' }));

    await waitFor(() => expect(screen.getByRole('article', { name: '客戶 CLIENT-001 歷史簽回修復' })).toBeInTheDocument());
    const clientReasonInput = screen.getByLabelText('修復原因與人工核對依據');
    expect(clientReasonInput).toBeEnabled();
    fireEvent.change(clientReasonInput, { target: { value: '依受控歷史客戶簽回核對完成' } });
    expect(screen.getByRole('button', { name: '檢查客戶歷史簽回修復影響' })).toBeEnabled();
    expect(staffRegion).not.toBeInTheDocument();
    expect(contractExternalSigningClient.query).toHaveBeenCalledTimes(2);
    expect(contractExternalSigningClient.queryLegacyRecovery).toHaveBeenCalledTimes(2);
    expect(contractExternalSigningClient.applyLegacyRecovery).toHaveBeenCalledTimes(1);
  });

  it('fails closed when historical recovery Apply returns an unexpected next status version', async () => {
    const current = {
      ...query,
      state: 'staff_reporting' as const,
      status_version: 3,
      commitment_id: null,
      staff_targets: [{ ...query.staff_targets[0], reported: false }],
      client_target: { ...query.client_target, reported: false },
    };
    const legacy = {
      ...recoveryQuery,
      state: current.state,
      status_version: current.status_version,
      commitment_id: null,
      targets: recoveryQuery.targets.map((target) => ({ ...target, reported: false })),
    };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(current);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValueOnce(legacy);
    vi.mocked(contractExternalSigningClient.previewLegacyRecovery).mockResolvedValueOnce({
      preview_fingerprint: 'd'.repeat(64),
      session_id: sessionId,
      expected_status_version: 3,
      scope: 'staff',
      matching_segment_id: 41,
      current_document_version_id: 31,
      current_document_set_sha256: legacy.current_document_set_sha256,
      current_commitment_id: null,
      legacy_media_sha256: legacy.targets[0].legacy_media_sha256!,
      blockers: [],
      can_apply: true,
    });
    vi.mocked(contractExternalSigningClient.applyLegacyRecovery).mockImplementation(async (_caseNo, _input, identity) => ({
      ...receipt,
      receipt_id: identity.receiptId,
      command_type: 'record_staff_report',
      outcome_state: 'recorded',
      resulting_status_version: 999,
      resulting_state: 'staff_reports_complete',
      matching_segment_id: 41,
      final_document_id: null,
    }));

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('article', { name: '月嫂 STAFF-009 歷史簽回修復' });
    fireEvent.change(screen.getAllByLabelText('修復原因與人工核對依據')[0], { target: { value: '核對完成' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查月嫂歷史簽回修復影響' }));
    await screen.findByText(/現行文件與歷史簽回證據已完成一致性檢查/);
    fireEvent.click(screen.getByLabelText('我已核對案件、對象、現行文件與歷史簽回證據'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用此筆歷史簽回修復' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/與原操作證據不一致/);
    expect(contractExternalSigningClient.query).toHaveBeenCalledTimes(1);
  });

  it('fails closed when a historical recovery Preview does not match current lineage', async () => {
    const current = {
      ...query,
      state: 'staff_reporting' as const,
      status_version: 3,
      commitment_id: null,
      staff_targets: [{ ...query.staff_targets[0], reported: false }],
      client_target: { ...query.client_target, reported: false },
    };
    const legacy = {
      ...recoveryQuery,
      state: current.state,
      status_version: current.status_version,
      commitment_id: null,
      targets: recoveryQuery.targets.map((target) => ({ ...target, reported: false })),
    };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(current);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValueOnce(legacy);
    vi.mocked(contractExternalSigningClient.previewLegacyRecovery).mockResolvedValueOnce({
      preview_fingerprint: 'd'.repeat(64),
      session_id: sessionId,
      expected_status_version: 3,
      scope: 'staff',
      matching_segment_id: 41,
      current_document_version_id: 999,
      current_document_set_sha256: legacy.current_document_set_sha256,
      current_commitment_id: null,
      legacy_media_sha256: legacy.targets[0].legacy_media_sha256!,
      blockers: [],
      can_apply: true,
    });

    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('article', { name: '月嫂 STAFF-009 歷史簽回修復' });
    fireEvent.change(screen.getAllByLabelText('修復原因與人工核對依據')[0], { target: { value: '核對完成' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查月嫂歷史簽回修復影響' }));

    await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent(/與目前文件證據不一致/);
    expect(contractExternalSigningClient.applyLegacyRecovery).not.toHaveBeenCalled();
  });

  it('fails closed before rendering when current and legacy recovery targets disagree', async () => {
    const current = {
      ...query,
      state: 'staff_reporting' as const,
      status_version: 2,
      commitment_id: null,
      staff_targets: [{ ...query.staff_targets[0], reported: false }],
      client_target: { ...query.client_target, reported: false },
    };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(current);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValueOnce({
      ...recoveryQuery,
      state: current.state,
      status_version: current.status_version,
      commitment_id: null,
      targets: [
        { ...recoveryQuery.targets[0], reported: false, target_subject_reference: 'WRONG-STAFF', current_document_version_id: 999 },
        { ...recoveryQuery.targets[1], reported: false },
      ],
    });

    render(<ContractExternalSigningActions caseNo="CASE-001" />);

    expect(await screen.findByRole('alert')).toHaveTextContent(/月嫂簽署對象不一致/);
    expect(screen.queryByRole('region', { name: '歷史簽回人工修復' })).not.toBeInTheDocument();
  });

  it('keeps individual completion reports out of the primary signing flow', async () => {
    const current = {
      ...query,
      state: 'staff_reporting' as const,
      status_version: 2,
      commitment_id: null,
      staff_targets: [{ ...query.staff_targets[0], reported: false }],
      client_target: { ...query.client_target, reported: false },
    };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(current);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValueOnce({
      ...recoveryQuery,
      state: current.state,
      status_version: current.status_version,
      commitment_id: null,
      targets: [
        { ...recoveryQuery.targets[0], reported: false, legacy_document_version_id: null, signing_event_id: null, command_receipt_id: null, legacy_media_sha256: null },
        { ...recoveryQuery.targets[1], reported: false },
      ],
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await waitFor(() => expect(screen.getByRole('button', { name: '下載客戶契約 PDF' })).toBeEnabled());
    expect(screen.queryByText(/選用稽核資料/)).not.toBeInTheDocument();

    expect(screen.queryByLabelText('月嫂完成證據')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /記錄月嫂.*完成回報/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /記錄客戶完成回報/ })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.recordStaffCompletionReport).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.recordClientCompletionReport).not.toHaveBeenCalled();
  });
});
