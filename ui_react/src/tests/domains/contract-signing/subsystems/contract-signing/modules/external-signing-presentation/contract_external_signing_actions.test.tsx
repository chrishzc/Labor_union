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
      prepareStaffUnsignedPdf: vi.fn(),
      prepareClientUnsignedPdf: vi.fn(),
      recordHandoff: vi.fn(),
      sendSigningReminders: vi.fn(),
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
    expect(contractExternalSigningClient.sendSigningReminders).not.toHaveBeenCalled();
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

  it('blocks handoff and reminders on an occupancy conflict before submission', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...query,
      signing_blockers: ['signing_staff_occupancy_conflict'] });
    const replacement = vi.fn(), dates = vi.fn();
    render(<ContractExternalSigningActions caseNo="CASE-001" onOpenRecommendation={replacement} onOpenServiceDates={dates} />);
    expect(await screen.findByText('目前推薦月嫂的檔期已衝突，正式完成簽約前請更換月嫂或調整服務日期。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '發送簽署提醒' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '更換推薦月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '調整服務日期' }));
    expect(replacement).toHaveBeenCalledOnce();
    expect(dates).toHaveBeenCalledOnce();
    expect(contractExternalSigningClient.recordHandoff).not.toHaveBeenCalled();
  });
  it('records an unbound handoff before PDFs are ready without automatically requesting reminders', async () => {
    const before = { ...query, state: 'staff_reporting' as const, status_version: 0, handoff_recorded: false, commitment_id: null, unsigned_document: null, unsigned_documents: [] };
    const after = { ...before, status_version: 1, handoff_recorded: true, handoff_included_reminders: false };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(before).mockResolvedValue(after);
    vi.mocked(contractExternalSigningClient.recordHandoff).mockResolvedValue({ session_id: sessionId, resulting_status_version: 1, replayed: false, handoff_included_reminders: false });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const record = await screen.findByRole('button', { name: '記錄已送交簽署平台' });
    await waitFor(() => expect(record).toBeEnabled());
    const reminder = screen.getByRole('button', { name: '發送簽署提醒' });
    const reason = '尚未記錄外部平台交接，暫時無法發送簽署提醒。請先點選上方「記錄已送交簽署平台」。';
    expect(reminder).toBeDisabled();
    expect(screen.getByText(reason)).toBeVisible();
    expect(reminder).toHaveAccessibleDescription(reason);
    fireEvent.click(record);
    expect(await screen.findByText('交接已記錄')).toBeVisible();
    await waitFor(() => expect(reminder).toBeEnabled());
    expect(screen.queryByText(reason)).not.toBeInTheDocument();
    expect(reminder).not.toHaveAccessibleDescription();
    expect(screen.getByText('尚未發送')).toBeVisible();
    expect(contractExternalSigningClient.sendSigningReminders).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.queryLegacyRecovery).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', { name: '歷史簽回人工修復' })).not.toBeInTheDocument();
  });

  it.each(['signing_staff_occupancy_conflict', 'signing_service_dates_unavailable', 'signing_accepted_plan_required'])(
    'shows %s before a PDF-less handoff can be submitted', async blocker => {
      vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...preparing, signing_blockers: [blocker] });
      render(<ContractExternalSigningActions caseNo="CASE-001" />);
      await waitFor(() => expect(screen.getByRole('alert')).toBeVisible());
      expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '發送簽署提醒' })).toBeDisabled();
      expect(contractExternalSigningClient.recordHandoff).not.toHaveBeenCalled();
    },
  );

  it('records a handoff directly while the case has no signing session or PDFs', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(preparing)
      .mockResolvedValue({ ...preparing, handoff_logged: true });
    vi.mocked(contractExternalSigningClient.recordHandoff).mockResolvedValue({ session_id: null, resulting_status_version: 0, replayed: false, handoff_included_reminders: false });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await waitFor(() => expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '記錄已送交簽署平台' }));
    expect(await screen.findByText('交接已記錄')).toBeVisible();
    expect(contractExternalSigningClient.recordHandoff).toHaveBeenCalledWith('CASE-001', 0, expect.any(Object));
    await waitFor(() => expect(screen.getByRole('button', { name: '發送簽署提醒' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '發送簽署提醒' }));
    expect(await screen.findByText('提醒工作已建立')).toBeVisible();
    expect(contractExternalSigningClient.sendSigningReminders).toHaveBeenCalledWith('CASE-001', { session_id: null, expected_status_version: 0 }, expect.any(Object));
  });

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
    vi.mocked(contractExternalSigningClient.getSignedDocumentReturns).mockImplementation(async caseNo => { const current = await vi.mocked(contractExternalSigningClient.query).mock.results.at(-1)!.value; if (current.state === 'preparing') throw new Error('no session'); return { case_no: caseNo, session_id: current.session_id, status_version: current.status_version, documents: [] }; });
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
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery).mockResolvedValue(recoveryQuery);
    vi.mocked(contractExternalSigningClient.recordHandoff).mockResolvedValue({
      session_id: sessionId,
      resulting_status_version: 1,
      replayed: false,
    });
    vi.mocked(contractExternalSigningClient.sendSigningReminders).mockImplementation(async (_caseNo, input, identity) => ({ receipt_id: identity.receiptId, session_id: input.session_id, status_version: input.expected_status_version, manual_notification_targets: [], replayed: false }));
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

  it('offers browser printing for every staff and client target without standalone PDF download buttons', async () => {
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

  it('preserves regeneration and uses browser printing for subsequent client output', async () => {
    const unsigned = { ...query, state: 'staff_reporting' as const, client_target: { ...query.client_target, reported: false } };
    const regenerated = { ...unsigned, client_target: { ...unsigned.client_target, document_version_id: 92 },
      unsigned_documents: unsigned.unsigned_documents.map(row => row.scope === 'client' ? { ...row, document_version_id: 92, filename: 'new-client.pdf' } : row) };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(unsigned).mockResolvedValue(regenerated);
    vi.mocked(contractExternalSigningClient.prepareClientUnsignedPdf).mockResolvedValue({ document_version_id: 92, filename: 'new-client.pdf', mime_type: 'application/pdf', size_bytes: 20, replayed: false });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:new-client'), revokeObjectURL: vi.fn() });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '重新產生客戶契約' }));
    await waitFor(() => expect(contractExternalSigningClient.prepareClientUnsignedPdf).toHaveBeenCalledWith('CASE-001', expect.objectContaining({ idempotencyKey: expect.any(String) })));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith('CASE-001', 92, expect.any(AbortSignal)));
    await waitFor(() => expect(screen.getByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' }));
    await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('CASE-001', 'client', null, expect.any(AbortSignal)));
    expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledTimes(1);
  });

  it('retains the regenerated client PDF while signing facts are still preparing', async () => {
    const document = { document_version_id: 32, scope: 'client_contract' as const, role: 'template_generated' as const, target_key: 'client-contract', mime_type: 'application/pdf' };
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce({ ...preparing, documents: [document] })
      .mockResolvedValue({ ...preparing, documents: [{ ...document, document_version_id: 92 }] });
    vi.mocked(contractExternalSigningClient.prepareClientUnsignedPdf).mockResolvedValue({ document_version_id: 92, filename: 'new-client.pdf', mime_type: 'application/pdf', size_bytes: 20, replayed: false });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:new-client'), revokeObjectURL: vi.fn() });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '重新產生客戶契約' }));
    await waitFor(() => expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledWith('CASE-001', 92, expect.any(AbortSignal)));
    await waitFor(() => expect(screen.getByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '瀏覽器列印 · 客戶服務契約 · 測試客戶' }));
    await waitFor(() => expect(openContractPrintView).toHaveBeenCalledWith('CASE-001', 'client', null, expect.any(AbortSignal)));
    expect(contractExternalSigningClient.downloadUnsignedPdf).toHaveBeenCalledTimes(1);
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

  it('records another handoff for a completed contract without changing its version or sending reminders', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(completedQuery);
    vi.mocked(contractExternalSigningClient.recordHandoff).mockResolvedValue({
      session_id: sessionId, resulting_status_version: completedQuery.status_version, replayed: false,
      handoff_included_reminders: false,
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await confirmHandoff();
    expect(await screen.findByText('已記錄送交外部簽署平台，尚未發送簽署提醒。')).toBeInTheDocument();
    expect(contractExternalSigningClient.recordHandoff).toHaveBeenCalledWith('CASE-001', 6, expect.any(Object));
    expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeEnabled();
    expect(contractExternalSigningClient.sendSigningReminders).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.applyFinalDocument).not.toHaveBeenCalled();
  });







  it('refreshes the current contract segment when the recommendation changes in the same case', async () => {
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce(preparing)
      .mockResolvedValueOnce({ ...preparing, staff_segments: [{ segment_id: 42, staff_id: 10 }] });
    const { rerender } = render(<ContractExternalSigningActions caseNo="CASE-001" revision={0} />);
    await screen.findByRole('button', { name: '瀏覽器列印 · 月嫂委任契約 · 未設定 月嫂41' });
    rerender(<ContractExternalSigningActions caseNo="CASE-001" revision={1} />);
    expect(await screen.findByRole('button', { name: '瀏覽器列印 · 月嫂委任契約 · 未設定 月嫂42' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '瀏覽器列印 · 月嫂委任契約 · 未設定 月嫂41' })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.prepareStaffUnsignedPdf).not.toHaveBeenCalled();
  });

  it('defers automatic facts refresh while an unsigned-PDF command still needs reconciliation', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(query);
    vi.mocked(contractExternalSigningClient.prepareClientUnsignedPdf).mockRejectedValueOnce(new ApiTimeoutError(10000));
    const { rerender } = render(<ContractExternalSigningActions caseNo="CASE-001" revision={0} />);
    fireEvent.click(await screen.findByRole('button', { name: '重新產生客戶契約' }));
    await waitFor(() => expect(orderMutationFlowStore.getExternalSigningUnsignedPreparation('CASE-001')?.status).toBe('outcome_unknown'));
    const original = orderMutationFlowStore.getExternalSigningUnsignedPreparation('CASE-001')!.command;
    rerender(<ContractExternalSigningActions caseNo="CASE-001" revision={1} />);
    await act(async () => { await Promise.resolve(); });
    expect(orderMutationFlowStore.getExternalSigningUnsignedPreparation('CASE-001')!.command).toEqual(original);
    expect(contractExternalSigningClient.query).toHaveBeenCalledTimes(1);
  });

  it('explains the missing current plan without requiring customer acceptance', async () => {
    vi.mocked(contractExternalSigningClient.query).mockRejectedValueOnce(new ApiHttpError(409, 'external_signing_accepted_plan_required', 'plan required'));
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('目前尚無可投影契約的有效配對方案。');
    expect(screen.getByRole('button', { name: /瀏覽器列印 · 客戶服務契約/ })).toBeEnabled();
  });

  it.each([
    { label: 'another target', target_key: 'staff-segment:42' },
    { label: 'an XLSX source', mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
    { label: 'a signed original', role: 'signed_return' as const },
    { label: 'another document version', document_version_id: 93 },
  ])('keeps the received PDF receipt pending when preparation readback contains $label', async (mismatch) => {
    const { label: _label, ...fields } = mismatch;
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce({ ...preparing, documents: [{ document_version_id: 32, scope: 'client_contract', role: 'template_generated', target_key: 'client-contract', mime_type: 'application/pdf' }] })
      .mockResolvedValueOnce({
        ...preparing,
        documents: [{
          document_version_id: 92, scope: 'client_contract', role: 'template_generated',
          target_key: 'client-contract', mime_type: 'application/pdf', ...fields,
        }],
      });
    vi.mocked(contractExternalSigningClient.prepareClientUnsignedPdf).mockResolvedValue({
      document_version_id: 92, filename: 'new-client.pdf', mime_type: 'application/pdf', size_bytes: 20, replayed: false,
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const downloadButton = await screen.findByRole('button', { name: '重新產生客戶契約' });
    await act(async () => { fireEvent.click(downloadButton); });
    await waitFor(() => expect(orderMutationFlowStore.getExternalSigningUnsignedPreparation('CASE-001')?.status).toBe('observation_failed'));
    expect(contractExternalSigningClient.downloadUnsignedPdf).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.prepareClientUnsignedPdf).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: '重新讀取未簽契約準備狀態' })).toBeEnabled();
  });

  it('hides testing skip unless the backend grants the local testing capability', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '回收簽署文件' });
    expect(screen.queryByRole('button', { name: '測試用：跳過文件回收' })).not.toBeInTheDocument();
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
    expect(screen.getAllByText('已選擇')).toHaveLength(2);
    expect(await screen.findByRole('alert')).toHaveTextContent(reason);
    expect(screen.getAllByText('已選擇')).toHaveLength(2);
    expect(onCommitted).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledWith('CASE-001', expect.objectContaining({ testing_skip_confirmed: true, signatures_confirmed: false }), expect.any(Object));
  });

  it('explains a completion rejection when directly saving existing test documents and keeps both selected', async () => {
    const documents = signedPreviews.map(row => ({ ...row, filename: `TEST-ONLY-${row.scope}.pdf` }));
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...query, testing_skip_allowed: true });
    vi.mocked(contractExternalSigningClient.getSignedDocumentReturns).mockResolvedValue({
      case_no: 'CASE-001', session_id: sessionId, status_version: 5, documents,
    });
    const rejection = new ApiHttpError(422, 'contract_external_signing_input_invalid', 'contract_identity_already_recorded');
    vi.mocked(contractExternalSigningClient.prepareTestingSkip).mockRejectedValue(rejection);
    vi.mocked(contractExternalSigningClient.previewSignedDocument).mockImplementation(async (_caseNo, input) => documents.find(row => row.scope === input.scope)!);
    vi.mocked(contractExternalSigningClient.previewFinalDocument).mockRejectedValue(rejection);
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const skip = await screen.findByRole('button', { name: '測試用：跳過文件回收' });
    await act(async () => { fireEvent.click(skip); });
    fireEvent.click(screen.getByRole('button', { name: '儲存簽署文件' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('本案已有另一份契約的簽約紀錄，本次文件不能覆蓋原契約。');
    expect(screen.getAllByText('已選擇')).toHaveLength(2);
    expect(contractExternalSigningClient.stageFinalDocument).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.applyFinalDocument).not.toHaveBeenCalled();
  });

  it('stages and checks all selected files in one save click before Apply/readback', async () => {
    const onCommitted = vi.fn();
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce(query)
      .mockResolvedValueOnce(completedQuery);
    vi.mocked(contractExternalSigningClient.queryLegacyRecovery)
      .mockResolvedValueOnce(recoveryQuery)
      .mockResolvedValueOnce(completedRecoveryQuery);
    render(<ContractExternalSigningActions caseNo="CASE-001" onCommitted={onCommitted} />);
    await screen.findByRole('region', { name: '回收簽署文件' });

    const rows = screen.getAllByRole('article').filter(row => row.getAttribute('aria-label')?.includes('簽回'));
    for (const row of rows) {
      const input = row.querySelector<HTMLInputElement>('input[type=file]')!;
      fireEvent.change(input, { target: { files: fileList(new File(['%PDF-1.7\ncontract\n%%EOF'], 'signed.pdf', { type: 'application/pdf' })) } });
    }
    expect(contractExternalSigningClient.stageFinalDocument).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '檢查簽署文件' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新檢查' })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.previewSignedDocument).not.toHaveBeenCalled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存簽署文件' }));

    await screen.findByText(/契約完成，最終 PDF 第 1 版已確認/);
    expect(contractExternalSigningClient.applyFinalDocument).toHaveBeenCalledWith(
      'CASE-001',
      expect.objectContaining({
        session_id: sessionId,
        documents: preview.documents.map(row => ({ scope: row.scope, matching_segment_id: row.matching_segment_id, document_version_id: row.document_version_id, staging_id: row.staging_id, expected_staging_version: row.expected_staging_version })),
        signatures_confirmed: true,
        preview_token: preview.preview_token,
        expected_status_version: 5,
      }),
      expect.objectContaining({ idempotencyKey: expect.any(String), receiptId: expect.any(String) }),
    );
    expect(onCommitted).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.query).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('region', { name: '回收簽署文件' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(preview.preview_token);
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{64}/);
    expect(document.body.textContent).not.toContain('/mnt/');
  });

  it('reads completed separate files without reopening historical signing recovery', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValueOnce(completedQuery);
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByRole('region', { name: '契約完成' })).toBeInTheDocument();
    expect(screen.getByText(/雙方在群組自行協調，由月嫂提交開始日/)).toBeInTheDocument();
    expect(screen.queryByText(/雙方確認與訂金鎖狀態/)).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '查看已簽文件' })).toHaveLength(2);
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

  it('fails closed when the post-Apply readback belongs to another case', async () => {
    vi.mocked(contractExternalSigningClient.getFinalDocumentReadback).mockResolvedValueOnce({
      ...readback,
      case_no: 'OTHER-CASE',
    });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '回收簽署文件' });
    await prepareSignedReturns();
    await waitFor(() => expect(screen.getByRole('button', { name: '儲存簽署文件' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '儲存簽署文件' }));

    expect(await screen.findByText(/完成結果尚未確認/)).toBeInTheDocument();
    expect(screen.queryByText(/契約完成，最終 PDF 第 1 版已確認/)).not.toBeInTheDocument();
  });

  it('invalidates the collection Preview when one selected file changes', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '回收簽署文件' });
    await prepareSignedReturns();
    const client = screen.getByRole('article', { name: '客戶服務契約簽回 測試客戶' });
    fireEvent.click(within(client).getByRole('button', { name: '重新選擇檔案' }));
    expect(screen.getByRole('button', { name: '儲存簽署文件' })).toBeDisabled();
    expect(screen.queryByRole('checkbox', { name: /我已核對本案與文件版本/ })).not.toBeInTheDocument();
    expect(screen.getByRole('article', { name: '月嫂委任契約簽回 未設定 月嫂41' })).toHaveTextContent('已選擇');
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
    await screen.findByRole('region', { name: '回收簽署文件' });
    await prepareSignedReturns();
    await waitFor(() => expect(screen.getByRole('button', { name: '儲存簽署文件' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '儲存簽署文件' }));

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
    await screen.findByRole('region', { name: '回收簽署文件' });
    await prepareSignedReturns();
    await waitFor(() => expect(screen.getByRole('button', { name: '儲存簽署文件' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '儲存簽署文件' }));

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
    expect(await screen.findByLabelText('待送交')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '回收簽署文件' })).not.toBeInTheDocument();

    await confirmHandoff();

    await screen.findByRole('region', { name: '回收簽署文件' });
    expect(contractExternalSigningClient.recordHandoff).toHaveBeenCalledWith(
      'CASE-001',
      0,
      expect.objectContaining({ idempotencyKey: expect.any(String), receiptId: expect.any(String) }),
    );
    expect(screen.getByText('已記錄送交外部簽署平台，尚未發送簽署提醒。')).toBeInTheDocument();
    expect(screen.queryByText(/選用稽核資料/)).not.toBeInTheDocument();
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
    expect(screen.queryByRole('region', { name: '回收簽署文件' })).not.toBeInTheDocument();
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

    await screen.findByRole('region', { name: '回收簽署文件' });
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
    await screen.findByRole('region', { name: '回收簽署文件' });
    expect(screen.queryByRole('region', { name: '歷史簽回人工修復' })).not.toBeInTheDocument();
    expect(contractExternalSigningClient.queryLegacyRecovery).not.toHaveBeenCalled();
  });

  it.each(['preparing', 'completed', 'superseded'] as const)('keeps the original reminder business gate while %s', async state => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue(state === 'preparing' ? preparing : state === 'superseded' ? supersededQuery('CASE-001') : completedQuery);
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await waitFor(() => expect(screen.getByRole('button', { name: '記錄已送交簽署平台' })).toBeEnabled());
    expect(screen.getByRole('button', { name: '發送簽署提醒' })).toBeDisabled();
    expect(contractExternalSigningClient.sendSigningReminders).not.toHaveBeenCalled();
  });

  it('confirms one reminder for the client and every staff target independently of file collection', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...query, staff_targets: [...query.staff_targets, { matching_segment_id: 42, staff_subject_reference: 'STAFF-010', document_version_id: 33, reported: false }] });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    const send = await screen.findByRole('button', { name: '發送簽署提醒' });
    fireEvent.click(send);
    expect(screen.queryByRole('dialog', { name: '確認發送簽署提醒' })).not.toBeInTheDocument();
    expect(await screen.findByText('提醒工作已建立')).toBeVisible();
    expect(contractExternalSigningClient.sendSigningReminders).toHaveBeenCalledTimes(1);
    expect(contractExternalSigningClient.sendSigningReminders).toHaveBeenCalledWith('CASE-001', { session_id: sessionId, expected_status_version: 5 }, expect.any(Object));
    expect(contractExternalSigningClient.recordHandoff).not.toHaveBeenCalled();
    expect(contractExternalSigningClient.applyFinalDocument).not.toHaveBeenCalled();
    expect(screen.getByText('0／3 份已選擇')).toBeVisible();
  });

  it('shows a persisted reminder and manual notification targets after reloading', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({ ...query, signing_reminder: { receipt_id: receipt.receipt_id, session_id: sessionId, status_version: 5, replayed: false, manual_notification_targets: [{ scope: 'client', subject_reference: 'CLIENT-001' }] } });
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    expect(await screen.findByText('提醒工作已建立')).toBeVisible();
    expect(screen.getByLabelText('需人工通知的簽約對象')).toHaveTextContent('測試客戶');
    expect(contractExternalSigningClient.sendSigningReminders).not.toHaveBeenCalled();
  });

  it('keeps the original reminder identity across a timeout and component remount', async () => {
    vi.mocked(contractExternalSigningClient.sendSigningReminders).mockRejectedValueOnce(new ApiTimeoutError(10000)).mockImplementation(async (_caseNo, input, identity) => ({ receipt_id: identity.receiptId, session_id: input.session_id, status_version: input.expected_status_version, replayed: true, manual_notification_targets: [] }));
    const first = render(<ContractExternalSigningActions caseNo="CASE-001" />);
    fireEvent.click(await screen.findByRole('button', { name: '發送簽署提醒' }));
    expect(await screen.findByRole('button', { name: '重新確認原提醒結果' })).toBeEnabled();
    const identity = vi.mocked(contractExternalSigningClient.sendSigningReminders).mock.calls[0]![2];
    first.unmount();
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '回收簽署文件' });
    expect(screen.getByRole('button', { name: '發送簽署提醒' })).toBeDisabled();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重新確認原提醒結果' })); });
    expect(await screen.findByText('提醒工作已建立')).toBeVisible();
    expect(vi.mocked(contractExternalSigningClient.sendSigningReminders).mock.calls[1]![2]).toEqual(identity);
  });

  it('preserves selected files when a reminder is sent', async () => {
    render(<ContractExternalSigningActions caseNo="CASE-001" />);
    await screen.findByRole('region', { name: '回收簽署文件' });
    await prepareSignedReturns();
    fireEvent.click(screen.getByRole('button', { name: '發送簽署提醒' }));
    expect(await screen.findByText('提醒工作已建立')).toBeVisible();
    expect(screen.getByRole('button', { name: '儲存簽署文件' })).toBeEnabled();
    expect(contractExternalSigningClient.applyFinalDocument).not.toHaveBeenCalled();
  });
});
