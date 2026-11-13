/**
 * File: contract_external_signing_actions.test.tsx
 * Description: 驗證外部簽約 closed-state UI、單擊儲存最終 PDF、receipt reconciliation 與隱私不變量。
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHttpError, ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';
import { ContractExternalSigningActions } from '../../../../../../../components/ContractExternalSigningActions';
import { contractExternalSigningClient, type ContractPreparationQuery } from '../../../../../../../api/orders/contract_external_signing_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { openContractPrintView, previewContractFields } from '../../../../../../../api/orders/contract_full_preview_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

vi.mock('../../../../../../../api/orders/contract_external_signing_client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../../../../../../api/orders/contract_external_signing_client')>();
  return {
    ...original,
    contractExternalSigningClient: {
      query: vi.fn(),
      querySignedArchive: vi.fn(),
      archiveSignedFiles: vi.fn(),
      prepareStaffUnsignedPdf: vi.fn(),
      prepareClientUnsignedPdf: vi.fn(),
      recordHandoff: vi.fn(),
      queryLegacyRecovery: vi.fn(),
      previewLegacyRecovery: vi.fn(),
      applyLegacyRecovery: vi.fn(),
      downloadUnsignedPdf: vi.fn(),
      recordStaffCompletionReport: vi.fn(),
      recordClientCompletionReport: vi.fn(),
      stageFinalDocument: vi.fn(),
      previewSignedDocument: vi.fn(),
      getSignedDocumentReturns: vi.fn(),
      downloadSignedPdf: vi.fn(),
      previewFinalDocument: vi.fn(),
      prepareTestingSkip: vi.fn(),
      applyFinalDocument: vi.fn(),
      getReceipt: vi.fn(),
      getFinalDocumentReadback: vi.fn(),
    },
  };
});

vi.mock('../../../../../../../api/orders/contract_full_preview_client', () => ({ previewContractFields: vi.fn(), openContractPrintView: vi.fn() }));

vi.mock('../../../../../../../api/orders/contract_signing_client', () => ({
  contractSigningClient: { query: vi.fn() },
}));

const sessionId = 'ces_1234567890abcdef1234567890abcdef';
const preparing: ContractPreparationQuery = {
  case_no: 'CASE-001', state: 'preparing',
  staff_segments: [{ segment_id: 41, staff_id: 9 }], documents: [],
};
const query = {
  case_no: 'CASE-001',
  session_id: sessionId,
  state: 'client_reported_final_pdf_pending' as const,
  status_version: 5,
  handoff_recorded: true,
  matching_plan_id: 17,
  commitment_id: 44,
  unsigned_documents: [{ scope: 'client' as const, matching_segment_id: null, document_version_id: 32, filename: 'client.pdf', mime_type: 'application/pdf' as const, size_bytes: 20 }, { scope: 'staff' as const, matching_segment_id: 41, document_version_id: 31, filename: 'staff.pdf', mime_type: 'application/pdf' as const, size_bytes: 20 }],
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
  scope: 'client' as const, matching_segment_id: null, document_version_id: 32, expected_staging_version: 1,
  staging_id: 'cfs_1234567890abcdef1234567890abcdef',
  filename: 'final-signed.pdf',
  mime_type: 'application/pdf' as const,
  size_bytes: 20,
  expires_at: '2026-08-27T10:00:00Z',
};

const signedPreviews = [
  { ...staged, blockers: [], can_apply: true },
  { ...staged, scope: 'staff' as const, matching_segment_id: 41, document_version_id: 31, staging_id: 'cfs_abcdefabcdefabcdefabcdefabcdefab', blockers: [], can_apply: true },
];
const preview = {
  preview_token: `cp_${'A'.repeat(43)}`,
  session_id: sessionId, expected_status_version: 5,
  documents: signedPreviews.map(({ expires_at: _expiresAt, ...row }) => row),
  blockers: [], can_apply: true as const,
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
  documents: signedPreviews.map(row => ({ scope: row.scope, matching_segment_id: row.matching_segment_id, document_version_id: row.document_version_id, controlled_file_id: row.scope === 'client' ? 'cf_1234567890abcdef1234567890abcdef' : 'cf_abcdefabcdefabcdefabcdefabcdefab', version_number: 1, filename: row.filename, mime_type: row.mime_type, size_bytes: row.size_bytes })),
  applied_at: '2026-08-26T10:00:00Z',
};

async function prepareSignedReturns() {
  const rows = screen.getAllByRole('article').filter(row => row.getAttribute('aria-label')?.includes('簽回'));
  for (const row of rows) {
    const input = row.querySelector<HTMLInputElement>('input[type=file]')!;
    fireEvent.change(input, { target: { files: fileList(new File(['%PDF-1.7\ncontract\n%%EOF'], 'signed.pdf', { type: 'application/pdf' })) } });
    expect(within(row).getByText('已選擇')).toBeInTheDocument();
  }
  await waitFor(() => expect(screen.getByRole('button', { name: '儲存簽署文件' })).toBeEnabled());
}

async function confirmHandoff() {
  const start = await screen.findByRole('button', { name: '記錄已送交簽署平台' });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
}

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

async function assertPrintCancellation(caseRemount: boolean) {
  const pending = deferred<void>();
  vi.mocked(contractExternalSigningClient.query)
    .mockResolvedValueOnce(supersededQuery('115000291'))
    .mockResolvedValueOnce(supersededQuery('115000292'));
  vi.mocked(openContractPrintView).mockReturnValueOnce(pending.promise).mockResolvedValueOnce();
  const { rerender } = render(<ContractExternalSigningActions key={caseRemount ? '115000291' : 'same'} caseNo="115000291" />);
  fireEvent.click(await screen.findByRole('button', { name: /瀏覽器列印 · 月嫂委任契約/ }));
  await waitFor(() => expect(openContractPrintView).toHaveBeenCalledTimes(1));
  const oldSignal = vi.mocked(openContractPrintView).mock.calls[0]![3];
  rerender(<ContractExternalSigningActions key={caseRemount ? '115000292' : 'same'} caseNo="115000292" />);
  await waitFor(() => expect(oldSignal.aborted).toBe(true));
  if (!caseRemount) {
    fireEvent.click(await screen.findByRole('button', { name: /瀏覽器列印 · 月嫂委任契約/ }));
    await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('115000292', 'staff', 41, expect.any(AbortSignal)));
  }
  await act(async () => { pending.resolve(); await Promise.resolve(); });
  if (caseRemount) expect(screen.queryByText(/已開啟完整契約列印視窗/)).not.toBeInTheDocument();
  else expect(screen.getAllByText(/已開啟完整契約列印視窗/)).toHaveLength(1);
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
  it.each(['client', 'staff'] as const)('prints the %s contract without preparing PDFs or sending signing commands', async (scope) => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(preparing);
    vi.mocked(openContractPrintView).mockResolvedValue();
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const title = scope === 'client' ? '客戶服務契約' : '月嫂委任契約';
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(`瀏覽器列印 · ${title}`) }));
    await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('CASE-001', scope, scope === 'client' ? null : 41, expect.any(AbortSignal)));
    expect(await screen.findByText(/已開啟完整契約列印視窗/)).toBeInTheDocument();
    expect(contractExternalSigningClient.prepareClientUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.prepareStaffUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.recordHandoff).not.toHaveBeenCalled();
  });

  it.each(['client', 'staff'] as const)('uses browser printing in the %s contract review dialog without a PDF download button', async (scope) => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const documents = await screen.findByRole('region', { name: '契約文件' });
    await waitFor(() => expect(within(documents).getAllByRole('button', { name: '核對資料' })[0]).toBeEnabled());
    fireEvent.click(within(documents).getAllByRole('button', { name: '核對資料' })[scope === 'client' ? 0 : 1]);
    const dialog = await screen.findByRole('dialog', { name: new RegExp(`核對資料 · ${scope === 'client' ? '客戶服務契約' : '月嫂委任契約'}`) });
    expect(within(dialog).queryByRole('button', { name: /下載 PDF/ })).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '瀏覽器列印' }));
    await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('CASE-001', scope, scope === 'client' ? null : 41, expect.any(AbortSignal)));
    expect(contractExternalSigningClient.downloadUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.prepareClientUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.prepareStaffUnsignedPdf).not.toHaveBeenCalled();
  });

  it('blocks handoff on an occupancy conflict before submission', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...query,
      signing_blockers: ['signing_staff_occupancy_conflict'] });
    const replacement = vi.fn(), dates = vi.fn();
    render(<ContractExternalSigningActions caseNo="CASE-001" onOpenRecommendation={replacement} onOpenServiceDates={dates} />);
    expect(await screen.findByText('目前推薦月嫂的檔期已衝突，正式完成簽約前請更換月嫂或調整服務日期。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '發送簽署提醒' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '更換推薦月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '調整服務日期' }));
    expect(replacement).toHaveBeenCalledOnce();
    expect(dates).toHaveBeenCalledOnce();
    expect(contractExternalSigningClient.recordHandoff).not.toHaveBeenCalled();
  });
  it('confirms an unbound handoff before PDFs are ready even when readback includes historical notification targets', async () => {
    const before = { ...query, state: 'staff_reporting' as const, status_version: 0, handoff_recorded: false, commitment_id: null, unsigned_document: null, unsigned_documents: [] };
    const after = { ...before, status_version: 1, handoff_recorded: true, handoff_included_reminders: false,
      manual_notification_targets: [{ scope: 'client' as const, subject_reference: 'CLIENT-001' }] };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(before).mockResolvedValue(after);
    vi.mocked(contractExternalSigningClient.recordHandoff).mockResolvedValue({ session_id: sessionId, resulting_status_version: 1, replayed: false, handoff_included_reminders: false });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const record = await screen.findByRole('button', { name: '記錄已送交簽署平台' });
    await waitFor(() => expect(record).toBeEnabled());
    expect(screen.queryByRole('button', { name: '發送簽署提醒' })).not.toBeInTheDocument();
    fireEvent.click(record);
    expect(await screen.findByText('已記錄送交外部簽署平台。')).toBeVisible();
    expect(screen.getByText('交接已記錄')).toBeVisible();
    expect(screen.queryByRole('button', { name: '發送簽署提醒' })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.queryLegacyRecovery).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', { name: '歷史簽回人工修復' })).not.toBeInTheDocument();
  });

  it.each(['signing_staff_occupancy_conflict', 'signing_service_dates_unavailable', 'signing_accepted_plan_required'])(
    'shows %s before a PDF-less handoff can be submitted', async blocker => {
      vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...preparing, signing_blockers: [blocker] });
      render(<ContractExternalSigningActions caseNo="CASE-001" />);
      await waitFor(() => expect(screen.getByRole('alert')).toBeVisible());
      expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeDisabled();
      expect(screen.queryByRole('button', { name: '發送簽署提醒' })).not.toBeInTheDocument();
      expect(contractExternalSigningClient.recordHandoff).not.toHaveBeenCalled();
    },
  );

  it('shows a typed command rejection without claiming that versions changed', async () => {
    const before = {
      ...query, state: 'staff_reporting' as const, status_version: 0,
      handoff_recorded: false, commitment_id: null,
      staff_targets: query.staff_targets.map((target) => ({ ...target, reported: false })),
      client_target: { ...query.client_target, reported: false },
    };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(before);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValue(handoffRecoveryQuery('CASE-001'));
    vi.mocked(contractExternalSigningClient.recordHandoff).mockRejectedValue(new ApiHttpError(
      409, 'contract_unsigned_pdf_missing', '月嫂 STAFF-009 未簽契約 PDF 尚未備妥。',
    ));
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await confirmHandoff();
    expect(await screen.findByText('月嫂 STAFF-009 未簽契約 PDF 尚未備妥。')).toBeInTheDocument();
    expect(screen.queryByText('簽約資料已變更，請重新查詢後再檢查影響。')).not.toBeInTheDocument();
  });

  it('reads back a real session that becomes ready after a preparation-mode handoff click', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(preparing)
      .mockResolvedValue({ ...query, state: 'staff_reporting', status_version: 1, handoff_recorded: true });
    vi.mocked(contractExternalSigningClient.recordHandoff).mockResolvedValue({ session_id: sessionId,
      resulting_status_version: 1, replayed: false, handoff_included_reminders: false });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await waitFor(() => expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '記錄已送交簽署平台' }));
    expect(await screen.findByText('交接已記錄')).toBeVisible();
    expect(screen.queryByText('以原交接操作重新確認')).not.toBeInTheDocument();
  });

  it.each([
    ['client_finance_bootstrap_required', '客戶付款條款'],
    ['payroll_bootstrap_required', '月嫂薪資資料'],
    ['payroll_case_policy_bootstrap_required', '月嫂薪資政策'],
  ])('shows the specific %s reason and links to the existing registry without embedding repair controls', async (code, missing) => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(preparing);
    vi.mocked(previewContractFields).mockRejectedValue(new ApiHttpError(409, code, code));
    render(<ContractExternalSigningActions caseNo={query.case_no} />);
    expect(await screen.findByText(`本案尚未建立${missing}，請至客戶名冊核對並補齊。`, { exact: false })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往客戶名冊補齊資料 →' })).toHaveAttribute('href', '#clients?case=CASE-001&from=workbench');
    expect(screen.queryByRole('button', { name: '預覽帳務與排班資料' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '補齊簽約所需帳務資料' })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.query).toHaveBeenCalledTimes(1);
  });

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(openContractPrintView).mockResolvedValue();
    vi.mocked(previewContractFields).mockImplementation(async (caseNo, scope, segmentId) => ({ case_no: caseNo, scope, assignment_id: null, template_key: scope === 'client' ? 'contract_client_copy' : 'contract_staff_service', template_version: 'a'.repeat(64), owner_fingerprints: {}, field_labels: {}, field_keys: {}, field_values: scope === 'client' ? { B8: '測試客戶', B24: '2026-11-01', D24: '2026-11-10', F24: 10 } as Record<string, string | number> : { C4: `月嫂${segmentId}`, B7: '2026-11-01', D7: '2026-11-10', G7: 10 } as Record<string, string | number>, field_states: {}, warnings: [], blockers: [], preview_fingerprint: 'b'.repeat(64), ready_to_print: true }));
    vi.mocked(contractExternalSigningClient.previewSignedDocument).mockImplementation(async (_caseNo, input) => ({ ...staged, ...input, blockers: [], can_apply: true }));

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
    vi.mocked(contractExternalSigningClient.querySignedArchive).mockResolvedValue({ staff_segments: [{ segment_id: 41, staff_id: 9 }], files: null });
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
    vi.mocked(contractExternalSigningClient.stageFinalDocument).mockImplementation(async (_caseNo, _file, _identity, target) => ({ ...staged, ...target, staging_id: target.scope === 'client' ? staged.staging_id : 'cfs_abcdefabcdefabcdefabcdefabcdefab' }));
    vi.mocked(contractExternalSigningClient.previewFinalDocument).mockResolvedValue(preview);
    vi.mocked(contractExternalSigningClient.applyFinalDocument).mockImplementation(async (_caseNo, _input, identity) => ({
      ...receipt,
      receipt_id: identity.receiptId,
    }));
    vi.mocked(contractExternalSigningClient.getFinalDocumentReadback).mockResolvedValue(readback);
  });

  afterEach(() => {
    sessionClient.clearSession();
    act(() => { orderMutationFlowStore.clearAll(); });
  });

  it('aborts a pending print when the case is remounted', async () => {
    await assertPrintCancellation(true);
  });

  it('keeps the new case print notice when the prior case completes late', async () => {
    await assertPrintCancellation(false);
  });

  it('offers browser printing as the output for every staff and client target', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...query,
      staff_targets: [...query.staff_targets, { ...query.staff_targets[0], matching_segment_id: 42, staff_subject_reference: 'STAFF-010', document_version_id: 33 }],
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    for (const [label, scope, segment] of [
      ['月嫂委任契約 · 未設定 月嫂41', 'staff', 41],
      ['月嫂委任契約 · 未設定 月嫂42', 'staff', 42],
      ['客戶服務契約 · 測試客戶', 'client', null],
    ] as const) {
      const button = await screen.findByRole('button', { name: `瀏覽器列印 · ${label}` });
      await waitFor(() => expect(button).toBeEnabled());
      fireEvent.click(button);
      await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('CASE-001', scope, segment, expect.any(AbortSignal)));
    }
    expect(openContractPrintView).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole('button', { name: /下載 PDF/ })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.downloadUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.prepareClientUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.prepareStaffUnsignedPdf).not.toHaveBeenCalled();
  });



  it('prints current staff data even when the signing session has no stored unsigned PDF', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...query, unsigned_document: null, unsigned_documents: [] });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: /瀏覽器列印 · 月嫂委任契約/ }));
    await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('CASE-001', 'staff', 41, expect.any(AbortSignal)));
    expect(contractExternalSigningClient.prepareStaffUnsignedPdf).not.toHaveBeenCalled();
  });



  it('explains absent staff targets while keeping the client print available', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce({ ...preparing, staff_segments: [] });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByText('目前尚未選定可列印契約的月嫂，請先建立推薦方案。')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /瀏覽器列印 · 客戶服務契約/ })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /下載 PDF/ })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.prepareClientUnsignedPdf).not.toHaveBeenCalled();
  });


  it('keeps every staff print available before the signing session is complete', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...preparing,
      staff_segments: [{ segment_id: 41, staff_id: 9 }, { segment_id: 42, staff_id: 10 }],
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '瀏覽器列印 · 月嫂委任契約 · 未設定 月嫂41' }));
    await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('CASE-001', 'staff', 41, expect.any(AbortSignal)));
    expect(screen.getByRole('button', { name: '瀏覽器列印 · 月嫂委任契約 · 未設定 月嫂42' })).toBeEnabled();
  });

  it('shows browser printing and no regeneration or direct PDF download action', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const print = await screen.findByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' });
    expect(screen.queryByRole('button', { name: /重新產生|下載 PDF/ })).not.toBeInTheDocument();
    fireEvent.click(print);
    await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('CASE-001', 'client', null, expect.any(AbortSignal)));
    expect(contractExternalSigningClient.prepareClientUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.downloadUnsignedPdf).not.toHaveBeenCalled();
  });

  it('allows repeated browser printing for a client contract already reported signed', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const button = await screen.findByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' });
    for (let count = 1; count <= 2; count += 1) {
      await waitFor(() => expect(button).toBeEnabled());
      fireEvent.click(button);
      await waitFor(() => expect(openContractPrintView).toHaveBeenCalledTimes(count));
    }
    expect(contractExternalSigningClient.prepareClientUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.downloadUnsignedPdf).not.toHaveBeenCalled();
  });

  it('records another handoff for a completed contract without changing its version', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(completedQuery);
    vi.mocked(contractExternalSigningClient.recordHandoff).mockResolvedValue({
      session_id: sessionId, resulting_status_version: completedQuery.status_version, replayed: false,
      handoff_included_reminders: false,
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await confirmHandoff();
    expect(await screen.findByText('已記錄送交外部簽署平台。')).toBeInTheDocument();
    expect(screen.queryByText(/尚未發送簽署提醒/)).not.toBeInTheDocument();
    expect(contractExternalSigningClient.recordHandoff).toHaveBeenCalledWith('CASE-001', 6, expect.any(Object));
    expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeEnabled();
    expect(contractExternalSigningClient.applyFinalDocument).not.toHaveBeenCalled();
  });







  it('refreshes the current contract segment when the recommendation changes in the same case', async () => {
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce(preparing)
      .mockResolvedValueOnce({ ...preparing, staff_segments: [{ segment_id: 42, staff_id: 10 }] });
    vi.mocked(contractExternalSigningClient.querySignedArchive)
      .mockResolvedValueOnce({ staff_segments: [{ segment_id: 41, staff_id: 9 }], files: null })
      .mockResolvedValue({ staff_segments: [{ segment_id: 42, staff_id: 10 }], files: null });
    const { rerender } = render(<ContractExternalSigningActions caseNo="CASE-001" revision={0} />);
    await screen.findByRole('button', { name: '瀏覽器列印 · 月嫂委任契約 · 未設定 月嫂41' });
    expect(await screen.findByLabelText(/月嫂41 委任契約 PDF/)).toBeEnabled();
    rerender(<ContractExternalSigningActions caseNo="CASE-001" revision={1} />);
    expect(await screen.findByRole('button', { name: '瀏覽器列印 · 月嫂委任契約 · 未設定 月嫂42' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '瀏覽器列印 · 月嫂委任契約 · 未設定 月嫂41' })).not.toBeInTheDocument();
    expect(await screen.findByLabelText(/月嫂42 委任契約 PDF/)).toBeEnabled();
    expect(screen.queryByLabelText(/月嫂41 委任契約 PDF/)).not.toBeInTheDocument();
    expect(contractExternalSigningClient.prepareStaffUnsignedPdf).not.toHaveBeenCalled();
  });

  it('explains the missing current plan without requiring customer acceptance', async () => {
    vi.mocked(contractExternalSigningClient.query).mockRejectedValueOnce(new ApiHttpError(409, 'external_signing_accepted_plan_required', 'plan required'));
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('目前尚無可投影契約的有效配對方案。');
    expect(screen.getByRole('button', { name: /瀏覽器列印 · 客戶服務契約/ })).toBeEnabled();
  });

  it('hides testing skip unless the backend grants the local testing capability', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByLabelText('客戶服務契約 PDF')).toBeEnabled();
    expect(screen.queryByText('測試模式 · 跳過文件回收')).not.toBeInTheDocument();
  });

  it('skips collection with test placeholders and explicit test confirmation, then reads back test completion', async () => {
    const testingQuery = { ...query, testing_skip_allowed: true };
    const testDocuments = preview.documents.map(row => ({ ...row, filename: `TEST-ONLY-${row.scope}.pdf` }));
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(testingQuery).mockResolvedValue({ ...completedQuery, testing_skip_allowed: true });
    vi.mocked(contractExternalSigningClient.prepareTestingSkip).mockResolvedValue({ ...preview, documents: testDocuments });
    vi.mocked(contractExternalSigningClient.getFinalDocumentReadback).mockResolvedValue({ ...readback, filename: 'TEST-ONLY-client.pdf', documents: readback.documents.map(row => ({ ...row, filename: `TEST-ONLY-${row.scope}.pdf` })) });
    const onCommitted = vi.fn();
    render(<ContractExternalSigningActions caseNo="CASE-001" onCommitted={onCommitted} />);
    await screen.findByText('測試模式 · 跳過文件回收');
    fireEvent.click(screen.getByText('測試模式 · 跳過文件回收'));
    const skip = await screen.findByRole('button', { name: '測試用：跳過文件回收' });
    await act(async () => { fireEvent.click(skip); });
    await waitFor(() => expect(onCommitted).toHaveBeenCalledTimes(1));
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledWith('CASE-001', expect.objectContaining({ signatures_confirmed: false, testing_skip_confirmed: true }), expect.any(Object));
    expect(contractExternalSigningClient.stageFinalDocument).not.toHaveBeenCalled();
    expect(await screen.findByText('測試簽約已完成')).toBeVisible();
    expect(screen.queryByText('客戶服務契約與所有月嫂委任契約已分別回收，並確認簽署完整。')).not.toBeInTheDocument();
  });

  it.each([
    [422, 'contract_external_signing_input_invalid', 'contract_identity_already_recorded', '本案已有另一份契約的簽約紀錄，本次文件不能覆蓋原契約。'],
    [409, 'official_service_dates_incomplete', 'official_service_dates_incomplete', '本案服務日期與約定服務天數不一致，請先核對服務期間與休假日。'],
    [422, 'contract_external_signing_input_invalid', '每日服務時段尚未保存。', '每日服務時段尚未保存。'],
  ] as const)('keeps selected test files and shows the actual completion rejection for %s %s %s', async (status, code, message, reason) => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...query, testing_skip_allowed: true });
    vi.mocked(contractExternalSigningClient.prepareTestingSkip).mockResolvedValue({
      ...preview, documents: preview.documents.map(row => ({ ...row, filename: `TEST-ONLY-${row.scope}.pdf` })),
    });
    vi.mocked(contractExternalSigningClient.applyFinalDocument).mockRejectedValue(new ApiHttpError(status, code, message));
    const onCommitted = vi.fn();
    render(<ContractExternalSigningActions caseNo="CASE-001" onCommitted={onCommitted} />);
    const skip = await screen.findByRole('button', { name: '測試用：跳過文件回收' });
    await act(async () => { fireEvent.click(skip); });
    expect(await screen.findByRole('alert')).toHaveTextContent(reason);
    expect(screen.getByText('TEST-ONLY-client.pdf')).toBeInTheDocument();
    expect(screen.getByText('TEST-ONLY-staff.pdf')).toBeInTheDocument();
    expect(screen.getByLabelText('客戶服務契約 PDF')).toBeEnabled();
    expect(onCommitted).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledWith('CASE-001', expect.objectContaining({ testing_skip_confirmed: true, signatures_confirmed: false }), expect.any(Object));
  });

  it('opens direct upload without reading unfinished legacy staged documents', async () => {
    vi.mocked(contractExternalSigningClient.getSignedDocumentReturns).mockRejectedValue(new Error('old version mismatch'));
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByLabelText('客戶服務契約 PDF')).toBeEnabled();
    await screen.findByRole('button', { name: /瀏覽器列印 · 月嫂委任契約/ });
    expect(contractExternalSigningClient.getSignedDocumentReturns).not.toHaveBeenCalled();
    expect(screen.queryByText(/old version mismatch/)).not.toBeInTheDocument();
  });

  it('archives directly with no session, handoff, unsigned version, or ready scheduling', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({
      ...preparing, signing_blockers: ['signing_accepted_plan_required', 'signing_staff_occupancy_conflict'],
    });
    vi.mocked(contractExternalSigningClient.archiveSignedFiles).mockResolvedValue([
      { target: 'client', filename: 'customer.pdf', file_id: 'cf_' + 'a'.repeat(32) },
      { target: 'staff:41', filename: 'staff.pdf', file_id: 'cf_' + 'b'.repeat(32) },
    ]);
    const onCommitted = vi.fn();
    render(<ContractExternalSigningActions caseNo="CASE-001" onCommitted={onCommitted} />);
    await screen.findByLabelText('客戶服務契約 PDF');
    expect(screen.getByRole('button', { name: '儲存簽署文件' })).toBeDisabled();
    await prepareSignedReturns();
    fireEvent.click(screen.getByRole('button', { name: '儲存簽署文件' }));
    expect(await screen.findByText('簽約已完成')).toBeVisible();
    expect(screen.getByText('customer.pdf')).toBeVisible();
    expect(onCommitted).toHaveBeenCalledOnce();
    expect(contractExternalSigningClient.archiveSignedFiles).toHaveBeenCalledWith('CASE-001', expect.any(File),
      [{ segmentId: 41, file: expect.any(File) }], expect.any(Object));
    expect(contractExternalSigningClient.recordHandoff).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.prepareClientUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.prepareStaffUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.previewFinalDocument).not.toHaveBeenCalled();
  });

  it('retains the files and reuses the same archive command after a timeout', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(preparing);
    vi.mocked(contractExternalSigningClient.querySignedArchive).mockResolvedValue({ staff_segments: [], files: null });
    vi.mocked(contractExternalSigningClient.archiveSignedFiles)
      .mockRejectedValueOnce(new ApiTimeoutError(10000))
      .mockResolvedValue([{ target: 'client', filename: 'customer.pdf', file_id: 'cf_' + 'a'.repeat(32) }]);
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByLabelText('客戶服務契約 PDF');
    await prepareSignedReturns();
    fireEvent.click(screen.getByRole('button', { name: '儲存簽署文件' }));
    fireEvent.click(await screen.findByRole('button', { name: '重新確認歸檔結果' }));
    expect(await screen.findByText('簽約已完成')).toBeVisible();
    const calls = vi.mocked(contractExternalSigningClient.archiveSignedFiles).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[1]).toEqual(calls[0]);
  });

  it('reads completed separate files without reopening historical signing recovery', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(completedQuery);
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const returns = screen.getByRole('region', { name: '回收簽署文件' });
    expect(await within(returns).findByRole('region', { name: '契約完成' })).toBeVisible();
    expect(screen.getByText(/雙方在群組自行協調，由月嫂提交開始日/)).toBeInTheDocument();
    expect(screen.queryByText(/雙方確認與訂金鎖狀態/)).not.toBeInTheDocument();
    expect(within(returns).getAllByRole('listitem')).toHaveLength(2);
    expect(within(returns).queryByRole('button', { name: '查看已簽文件' })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.queryLegacyRecovery).not.toHaveBeenCalled();
    expect(screen.queryByText(/歷史簽回資料暫時無法查詢/)).not.toBeInTheDocument();
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

  it('does not treat a preparation projection as confirmation of a received handoff receipt', async () => {
    const beforeHandoff = {
      ...query, state: 'staff_reporting' as const, status_version: 0,
      handoff_recorded: false, commitment_id: null,
      staff_targets: query.staff_targets.map((target) => ({ ...target, reported: false })),
      client_target: { ...query.client_target, reported: false },
    };
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce(beforeHandoff).mockResolvedValueOnce(preparing);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValueOnce(handoffRecoveryQuery('CASE-001'));
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await confirmHandoff();
    await waitFor(() => expect(orderMutationFlowStore.getExternalSigningHandoff('CASE-001')?.status).toBe('observation_failed'));
    const returns = screen.getByRole('region', { name: '回收簽署文件' });
    expect(returns).toBeVisible();
    expect(await within(returns).findByRole('button', { name: '儲存簽署文件' })).toBeDisabled();
    expect(contractExternalSigningClient.recordHandoff).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: '重新讀取交接狀態' })).toBeEnabled();
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
    await confirmHandoff();
    fireEvent.click(await screen.findByRole('button', { name: '以原交接操作重新確認' }));

    expect(await screen.findByLabelText('客戶服務契約 PDF')).toBeEnabled();
    expect(contractExternalSigningClient.recordHandoff).toHaveBeenCalledTimes(2);
    expect(vi.mocked(contractExternalSigningClient.recordHandoff).mock.calls[1]?.[2]).toEqual(
      vi.mocked(contractExternalSigningClient.recordHandoff).mock.calls[0]?.[2],
    );
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
    await waitFor(() => expect(screen.getByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' })).toBeEnabled());
    expect(screen.queryByText(/選用稽核資料/)).not.toBeInTheDocument();

    expect(screen.queryByLabelText('月嫂完成證據')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /記錄月嫂.*完成回報/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /記錄客戶完成回報/ })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.recordStaffCompletionReport).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.recordClientCompletionReport).not.toHaveBeenCalled();
  });

  it('removes historical repairs and never requests their query even when old evidence exists', async () => {
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValue({ ...recoveryQuery, targets: recoveryQuery.targets.map(target => ({ ...target, reported: false })) });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByLabelText('客戶服務契約 PDF')).toBeEnabled();
    expect(screen.queryByRole('region', { name: '歷史簽回人工修復' })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.queryLegacyRecovery).not.toHaveBeenCalled();
  });

  it('keeps every current signing return and hides historic reminder status', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({
      ...query,
      staff_targets: [...query.staff_targets, { matching_segment_id: 42, staff_subject_reference: 'STAFF-010', document_version_id: 33, reported: false }],
      signing_reminder: { receipt_id: receipt.receipt_id, session_id: sessionId, status_version: 5, replayed: false,
        manual_notification_targets: [{ scope: 'client', subject_reference: 'CLIENT-001' }] },
    });
    vi.mocked(contractExternalSigningClient.querySignedArchive).mockResolvedValue({
      staff_segments: [{ segment_id: 41, staff_id: 9 }, { segment_id: 42, staff_id: 10 }], files: null,
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByText('0／3 份已選擇')).toBeVisible();
    expect(screen.queryByRole('button', { name: '發送簽署提醒' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新確認原提醒結果' })).not.toBeInTheDocument();
    expect(screen.queryByText('提醒工作已建立')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('需人工通知的簽約對象')).not.toBeInTheDocument();
    expect(contractExternalSigningClient.applyFinalDocument).not.toHaveBeenCalled();
  });
});
