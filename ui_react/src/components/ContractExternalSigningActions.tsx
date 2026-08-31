/**
 * File: ContractExternalSigningActions.tsx
 * Description: 呈現外部簽約 successor closed states、完成回報與最終 PDF 確認、Apply、receipt/readback。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  contractExternalSigningClient,
  createExternalSigningCommandIdentity,
  type ContractExternalSigningQuery,
  type ExternalSigningCommandIdentity,
  type ExternalSigningConfirmationMethod,
  type ExternalSigningReceipt,
  type FinalDocumentPreview,
  type FinalDocumentReadback,
  type LegacyRecoveryPreview,
  type LegacyRecoveryPreviewInput,
  type LegacyRecoveryQuery,
  type LegacyRecoveryTarget,
} from '../api/orders/contract_external_signing_client';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';

export interface ContractExternalSigningActionsProps {
  caseNo: string;
  onCommitted?: () => Promise<void> | void;
}

type WorkingOperation = 'query' | 'download' | 'staff_report' | 'client_report' | 'final_preview' | 'final_apply' | 'receipt' | 'readback';

interface RecoveryPreviewState {
  target: LegacyRecoveryTarget;
  request: LegacyRecoveryPreviewInput;
  preview: LegacyRecoveryPreview;
  confirmed: boolean;
}

interface ReceiptExpectation {
  commandType: ExternalSigningReceipt['command_type'];
  sessionId: string;
  matchingSegmentId: number | null;
  resultingStatusVersion: number;
}

export type ContractExternalSigningUiState =
  | { type: 'querying' }
  | { type: 'ready' }
  | { type: 'working'; operation: WorkingOperation }
  | { type: 'preview_ready'; preview: FinalDocumentPreview; confirmed: boolean }
  | { type: 'recovery_preview_ready'; recovery: RecoveryPreviewState }
  | { type: 'receipt_committed'; receipt: ExternalSigningReceipt; message: string }
  | { type: 'outcome_unknown'; identity: ExternalSigningCommandIdentity; expected: ReceiptExpectation; message: string }
  | { type: 'observed'; receipt: ExternalSigningReceipt; readback: FinalDocumentReadback }
  | { type: 'error'; message: string };

const unsafePublicText = /https?:\/\/|[A-Za-z]:\\|\\\\|\/(?:mnt|Volumes|private|var)\/|[0-9a-f]{64}|preview[_ -]?fingerprint|storage[_ -]?locator|raw[_ -]?cursor/i;

function safeErrorMessage(error: unknown): string {
  const fallback = '外部簽約操作失敗，請重新查詢目前狀態。';
  const message = error instanceof Error ? error.message : fallback;
  if (unsafePublicText.test(message)) return fallback;
  if (error instanceof ApiTimeoutError || error instanceof ApiNetworkError) {
    return '連線暫時中斷，結果可能尚未確認，請使用原操作重新確認。';
  }
  if (error instanceof ApiHttpError) {
    if (error.status === 401 || error.status === 403) return '目前帳號無權處理這筆外部簽約。';
    if (error.status === 409) return '簽約資料已變更，請重新查詢後再檢查影響。';
    if (error.retryable || error.status >= 500) return '簽約服務暫時無法使用，請稍後重新查詢。';
    return '這筆操作未通過簽約檢查，請重新查詢目前狀態。';
  }
  return message || fallback;
}

function assertFinalReadbackMatchesCase(caseNo: string, readback: FinalDocumentReadback): void {
  if (readback.case_no !== caseNo.trim()) {
    throw new Error('最終 PDF 的案件識別不一致。');
  }
}

function outcomeCouldBeUnknown(error: unknown): boolean {
  return error instanceof ApiTimeoutError
    || error instanceof ApiNetworkError
    || (error instanceof ApiHttpError && error.retryable);
}

function stateLabel(query: ContractExternalSigningQuery): string {
  switch (query.state) {
    case 'staff_reporting': return '等待月嫂完成回報';
    case 'staff_reports_complete': return '月嫂回報完成，等待客戶回報';
    case 'client_reported_final_pdf_pending': return '最終簽署 PDF 待回收';
    case 'completed': return '契約完成';
    case 'superseded': return '此簽約工作已被新版取代';
  }
}

function currentIdentity(
  identities: Map<string, ExternalSigningCommandIdentity>,
  key: string,
): ExternalSigningCommandIdentity {
  const existing = identities.get(key);
  if (existing) return existing;
  const created = createExternalSigningCommandIdentity(key);
  identities.set(key, created);
  return created;
}

function recoveryTargetKey(target: LegacyRecoveryTarget): string {
  return target.scope === 'staff' ? `staff-${target.matching_segment_id}` : 'client';
}

function hasCompleteLegacyLineage(target: LegacyRecoveryTarget): boolean {
  return target.legacy_document_version_id !== null
    && target.signing_event_id !== null
    && target.command_receipt_id !== null
    && target.legacy_media_sha256 !== null;
}

function assertRecoveryQueryMatchesCurrent(
  current: ContractExternalSigningQuery,
  recovery: LegacyRecoveryQuery,
): void {
  if (
    current.case_no !== recovery.case_no
    || current.session_id !== recovery.session_id
    || current.matching_plan_id !== recovery.matching_plan_id
    || current.commitment_id !== recovery.commitment_id
    || current.state !== recovery.state
    || current.status_version !== recovery.status_version
  ) {
    throw new Error('歷史簽回修復與目前簽約狀態不一致，請重新查詢。');
  }
  const currentStaff = new Map(current.staff_targets.map((target) => [target.matching_segment_id, target]));
  const recoveryStaff = recovery.targets.filter((target) => target.scope === 'staff');
  if (currentStaff.size !== recoveryStaff.length || recoveryStaff.some((target) => {
    const source = currentStaff.get(target.matching_segment_id!);
    return !source
      || source.staff_subject_reference !== target.target_subject_reference
      || source.document_version_id !== target.current_document_version_id
      || source.reported !== target.reported;
  })) {
    throw new Error('歷史簽回修復與目前月嫂簽署對象不一致，請重新查詢。');
  }
  const recoveryClient = recovery.targets.find((target) => target.scope === 'client');
  if (
    !recoveryClient
    || recoveryClient.target_subject_reference !== current.client_target.client_subject_reference
    || recoveryClient.current_document_version_id !== current.client_target.document_version_id
    || recoveryClient.reported !== current.client_target.reported
  ) {
    throw new Error('歷史簽回修復與目前客戶簽署對象不一致，請重新查詢。');
  }
}

function assertRecoveryPreviewMatches(
  recovery: LegacyRecoveryQuery,
  target: LegacyRecoveryTarget,
  preview: LegacyRecoveryPreview,
): void {
  if (
    preview.session_id !== recovery.session_id
    || preview.expected_status_version !== recovery.status_version
    || preview.scope !== target.scope
    || preview.matching_segment_id !== target.matching_segment_id
    || preview.current_document_version_id !== target.current_document_version_id
    || preview.current_document_set_sha256 !== recovery.current_document_set_sha256
    || preview.current_commitment_id !== recovery.commitment_id
    || preview.legacy_media_sha256 !== target.legacy_media_sha256
  ) {
    throw new Error('歷史簽回修復與目前文件證據不一致，請重新查詢。');
  }
}

export function ContractExternalSigningActions({ caseNo, onCommitted }: ContractExternalSigningActionsProps) {
  const identities = useRef(new Map<string, ExternalSigningCommandIdentity>());
  const requestGeneration = useRef(0);
  const [query, setQuery] = useState<ContractExternalSigningQuery | null>(null);
  const [recoveryQuery, setRecoveryQuery] = useState<LegacyRecoveryQuery | null>(null);
  const [uiState, setUiState] = useState<ContractExternalSigningUiState>({ type: 'querying' });
  const [notice, setNotice] = useState<string | null>(null);
  const [staffReasons, setStaffReasons] = useState<Record<number, string>>({});
  const [clientReason, setClientReason] = useState('');
  const [recoveryReasons, setRecoveryReasons] = useState<Record<string, string>>({});
  const [confirmationMethod, setConfirmationMethod] = useState<ExternalSigningConfirmationMethod>('verified_other');
  const [finalFile, setFinalFile] = useState<File | null>(null);

  const loadQuery = useCallback(async (signal?: AbortSignal): Promise<ContractExternalSigningQuery> => {
    const generation = ++requestGeneration.current;
    setUiState({ type: 'querying' });
    const value = await contractExternalSigningClient.query(caseNo, { signal });
    const recovery = value.state === 'superseded'
      ? null
      : await contractExternalSigningClient.queryLegacyRecovery(caseNo, { signal });
    if (recovery) assertRecoveryQueryMatchesCurrent(value, recovery);
    if (generation !== requestGeneration.current) return value;
    setQuery(value);
    setRecoveryQuery(recovery);
    setUiState({ type: 'ready' });
    return value;
  }, [caseNo]);

  useEffect(() => {
    const controller = new AbortController();
    setQuery(null);
    setRecoveryQuery(null);
    setNotice(null);
    setFinalFile(null);
    identities.current.clear();
    void loadQuery(controller.signal).then(async (value) => {
      if (controller.signal.aborted || value.state !== 'completed') return;
      try {
        setUiState({ type: 'working', operation: 'readback' });
        const readback = await contractExternalSigningClient.getFinalDocumentReadback(caseNo, controller.signal);
        assertFinalReadbackMatchesCase(caseNo, readback);
        if (readback.session_id !== value.session_id) {
          throw new Error('最終 PDF 與目前簽約工作不一致。');
        }
        if (!controller.signal.aborted) {
          setNotice(`最終 PDF 第 ${readback.version_number} 版已確認完成，完整性驗證通過。`);
          setUiState({ type: 'ready' });
        }
      } catch (error) {
        if (!controller.signal.aborted) setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }).catch((error) => {
      if (!controller.signal.aborted) setUiState({ type: 'error', message: safeErrorMessage(error) });
    });
    return () => {
      requestGeneration.current += 1;
      controller.abort();
    };
  }, [caseNo, loadQuery]);

  const downloadUnsigned = async (documentVersionId: number, targetLabel: string) => {
    if (!query?.unsigned_document) return;
    setUiState({ type: 'working', operation: 'download' });
    setNotice(null);
    try {
      const artifact = await contractExternalSigningClient.downloadUnsignedPdf(
        caseNo,
        documentVersionId,
      );
      const url = URL.createObjectURL(artifact.blob);
      try {
        const link = document.createElement('a');
        link.href = url;
        link.download = artifact.filename;
        link.click();
      } finally {
        URL.revokeObjectURL(url);
      }
      setNotice(`${targetLabel}未簽契約 PDF「${artifact.filename}」已下載。`);
      setUiState({ type: 'ready' });
    } catch (error) {
      setUiState({ type: 'error', message: safeErrorMessage(error) });
    }
  };

  const runReport = async (
    key: string,
    operation: (identity: ExternalSigningCommandIdentity) => Promise<ExternalSigningReceipt>,
  ) => {
    const identity = currentIdentity(identities.current, key);
    setNotice(null);
    setUiState({ type: 'working', operation: key.startsWith('staff') ? 'staff_report' : 'client_report' });
    try {
      const receipt = await operation(identity);
      const staffSegmentId = key.startsWith('staff-') ? Number(key.slice('staff-'.length)) : null;
      const expectedCommand = staffSegmentId === null ? 'record_client_report' : 'record_staff_report';
      if (
        receipt.receipt_id !== identity.receiptId
        || receipt.session_id !== query!.session_id
        || receipt.command_type !== expectedCommand
        || receipt.matching_segment_id !== staffSegmentId
        || receipt.resulting_status_version !== query!.status_version + 1
      ) {
        throw new Error('完成回報與原操作或目前狀態不一致；不得視為完成。');
      }
      identities.current.delete(key);
      setNotice(receipt.replayed ? '完成回報已安全重播，正在重新查詢。' : '完成回報已記錄，正在重新查詢。');
      await loadQuery();
    } catch (error) {
      if (outcomeCouldBeUnknown(error)) {
        const segmentId = key.startsWith('staff-') ? Number(key.slice('staff-'.length)) : null;
        setUiState({
          type: 'outcome_unknown',
          identity,
          expected: {
            commandType: segmentId === null ? 'record_client_report' : 'record_staff_report',
            sessionId: query!.session_id,
            matchingSegmentId: segmentId,
            resultingStatusVersion: query!.status_version + 1,
          },
          message: '完成回報結果未明；請使用原操作重新確認，不要重送。',
        });
      } else {
        setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }
  };

  const previewLegacyRecovery = async (target: LegacyRecoveryTarget) => {
    if (!recoveryQuery || target.reported || !hasCompleteLegacyLineage(target)) return;
    const key = recoveryTargetKey(target);
    const reason = (recoveryReasons[key] ?? '').trim();
    if (!reason) return;
    const request: LegacyRecoveryPreviewInput = {
      scope: target.scope,
      matching_segment_id: target.matching_segment_id,
      legacy_document_version_id: target.legacy_document_version_id!,
      signing_event_id: target.signing_event_id!,
      command_receipt_id: target.command_receipt_id!,
      confirmation_method: confirmationMethod,
      reason,
    };
    setNotice(null);
    setUiState({ type: 'working', operation: target.scope === 'staff' ? 'staff_report' : 'client_report' });
    try {
      const preview = await contractExternalSigningClient.previewLegacyRecovery(caseNo, request);
      assertRecoveryPreviewMatches(recoveryQuery, target, preview);
      identities.current.delete(`legacy-${key}`);
      setUiState({ type: 'recovery_preview_ready', recovery: { target, request, preview, confirmed: false } });
    } catch (error) {
      setUiState({ type: 'error', message: safeErrorMessage(error) });
    }
  };

  const applyLegacyRecovery = async () => {
    if (!recoveryQuery || uiState.type !== 'recovery_preview_ready') return;
    const { target, request, preview, confirmed } = uiState.recovery;
    if (!confirmed || !preview.can_apply) return;
    const key = `legacy-${recoveryTargetKey(target)}`;
    const identity = currentIdentity(identities.current, key);
    setUiState({ type: 'working', operation: target.scope === 'staff' ? 'staff_report' : 'client_report' });
    try {
      const receipt = await contractExternalSigningClient.applyLegacyRecovery(caseNo, {
        ...request,
        preview_fingerprint: preview.preview_fingerprint,
        expected_status_version: preview.expected_status_version,
      }, identity);
      const expectedCommand = target.scope === 'staff' ? 'record_staff_report' : 'record_client_report';
      if (
        receipt.receipt_id !== identity.receiptId
        || receipt.session_id !== recoveryQuery.session_id
        || receipt.command_type !== expectedCommand
        || receipt.matching_segment_id !== target.matching_segment_id
        || receipt.resulting_status_version !== preview.expected_status_version + 1
      ) {
        throw new Error('歷史簽回修復與原操作證據不一致；不得視為完成。');
      }
      identities.current.delete(key);
      setNotice(receipt.replayed ? '歷史簽回修復已安全重播，正在重新查詢。' : '歷史簽回修復已記錄，正在重新查詢。');
      await loadQuery();
    } catch (error) {
      if (outcomeCouldBeUnknown(error)) {
        setUiState({
          type: 'outcome_unknown',
          identity,
          expected: {
            commandType: target.scope === 'staff' ? 'record_staff_report' : 'record_client_report',
            sessionId: recoveryQuery.session_id,
            matchingSegmentId: target.matching_segment_id,
            resultingStatusVersion: preview.expected_status_version + 1,
          },
          message: '歷史簽回修復結果未明；不得重送，請使用原操作重新確認。',
        });
      } else {
        setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }
  };

  const previewFinalDocument = async () => {
    if (!query || !finalFile) return;
    const identity = currentIdentity(identities.current, 'final-stage');
    setNotice(null);
    setUiState({ type: 'working', operation: 'final_preview' });
    try {
      const staged = await contractExternalSigningClient.stageFinalDocument(caseNo, finalFile, identity);
      const preview = await contractExternalSigningClient.previewFinalDocument(caseNo, {
        staging_id: staged.staging_id,
        expected_status_version: query.status_version,
      });
      identities.current.delete('final-stage');
      identities.current.delete('final-apply');
      setUiState({ type: 'preview_ready', preview, confirmed: false });
    } catch (error) {
      setUiState({ type: 'error', message: safeErrorMessage(error) });
    }
  };

  const observeFinalReceipt = async (receipt: ExternalSigningReceipt) => {
    setUiState({ type: 'receipt_committed', receipt, message: '最終文件已受理；正在確認簽約完成結果。' });
    try {
      const readback = await contractExternalSigningClient.getFinalDocumentReadback(caseNo);
      assertFinalReadbackMatchesCase(caseNo, readback);
      if (receipt.final_document_id !== readback.final_document_id || receipt.session_id !== readback.session_id) {
        throw new Error('最終 PDF 的受理結果與回讀文件不一致。');
      }
      setUiState({ type: 'observed', receipt, readback });
      const refreshed = await loadQuery();
      if (
        refreshed.session_id !== receipt.session_id
        || refreshed.state !== 'completed'
        || refreshed.status_version !== receipt.resulting_status_version
      ) {
        throw new Error('最終 PDF 回讀後的簽約狀態尚未完成；不得重送。');
      }
      setNotice(`契約完成，最終 PDF 第 ${readback.version_number} 版已確認，完整性驗證通過。`);
      await onCommitted?.();
    } catch (error) {
      setUiState({
        type: 'receipt_committed',
        receipt,
        message: `最終文件已受理，但完成結果尚未確認；不要重送。${safeErrorMessage(error)}`,
      });
    }
  };

  const applyFinalDocument = async () => {
    if (!query || uiState.type !== 'preview_ready' || !uiState.confirmed || !uiState.preview.can_apply) return;
    const preview = uiState.preview;
    const identity = currentIdentity(identities.current, 'final-apply');
    setUiState({ type: 'working', operation: 'final_apply' });
    try {
      const receipt = await contractExternalSigningClient.applyFinalDocument(caseNo, {
        staging_id: preview.staging_id,
        expected_staging_version: preview.expected_staging_version,
        preview_token: preview.preview_token,
        expected_status_version: query.status_version,
      }, identity);
      if (
        receipt.receipt_id !== identity.receiptId
        || receipt.session_id !== query.session_id
        || receipt.command_type !== 'apply_final_signed_contract'
        || receipt.matching_segment_id !== null
        || receipt.resulting_status_version !== query.status_version + 1
      ) {
        throw new Error('最終 PDF 受理結果與原操作或目前狀態不一致；不得視為完成。');
      }
      identities.current.delete('final-apply');
      await observeFinalReceipt(receipt);
    } catch (error) {
      if (outcomeCouldBeUnknown(error)) {
        setUiState({
          type: 'outcome_unknown',
          identity,
          expected: {
            commandType: 'apply_final_signed_contract',
            sessionId: query.session_id,
            matchingSegmentId: null,
            resultingStatusVersion: query.status_version + 1,
          },
          message: '最終 PDF 處理結果未明；不得重送，請使用原操作重新確認。',
        });
      } else {
        setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }
  };

  const reconcileUnknown = async () => {
    if (uiState.type !== 'outcome_unknown') return;
    const identity = uiState.identity;
    const expected = uiState.expected;
    setUiState({ type: 'working', operation: 'receipt' });
    try {
      const receipt = await contractExternalSigningClient.getReceipt(caseNo, identity.receiptId);
      if (
        receipt.receipt_id !== identity.receiptId
        || receipt.command_type !== expected.commandType
        || receipt.session_id !== expected.sessionId
        || receipt.matching_segment_id !== expected.matchingSegmentId
        || receipt.resulting_status_version !== expected.resultingStatusVersion
      ) {
        throw new Error('受理結果與原操作識別不一致；不得視為完成。');
      }
      if (receipt.command_type === 'apply_final_signed_contract') {
        identities.current.delete('final-apply');
        await observeFinalReceipt(receipt);
      } else {
        await loadQuery();
      }
    } catch (error) {
      setUiState({
        type: 'outcome_unknown',
        identity,
        expected,
        message: `尚無法確認原操作結果；請稍後使用同一操作重新確認。${safeErrorMessage(error)}`,
      });
    }
  };

  const retryReadback = async () => {
    if (uiState.type !== 'receipt_committed') return;
    const receipt = uiState.receipt;
    setUiState({ type: 'working', operation: 'readback' });
    await observeFinalReceipt(receipt);
  };

  const busy = uiState.type === 'working';
  const pendingRecoveryTargets = recoveryQuery?.targets.filter((target) => !target.reported) ?? [];
  const allRecoveryStaffReported = recoveryQuery?.targets
    .filter((target) => target.scope === 'staff')
    .every((target) => target.reported) ?? false;
  const isRecoveryOwnedTarget = (scope: 'staff' | 'client', segmentId: number | null) =>
    recoveryQuery?.targets.some((target) => (
      target.scope === scope
      && target.matching_segment_id === segmentId
      && !target.reported
      && hasCompleteLegacyLineage(target)
    )) ?? false;

  return (
    <section aria-label="外部平台簽約與最終 PDF" data-control-id="orders.contract-external-signing.actions" style={{ display: 'grid', gap: '14px' }}>
      <header>
        <h3 style={{ margin: 0 }}>📄 外部平台簽約與最終 PDF</h3>
        <p style={{ margin: '6px 0 0', color: '#74593f', fontSize: '0.84rem' }}>
          系統只保存完成回報與受控最終文件；外部平台狀態、LINE 已送達或畫面提示都不等於契約完成。
        </p>
      </header>

      {query && (
        <div role="status" style={{ padding: '10px 12px', border: '1px solid #fed7aa', borderRadius: '10px', background: '#fff8f6' }}>
          <strong>{stateLabel(query)}</strong>
          <details style={{ fontSize: '0.8rem', color: '#74593f', marginTop: '4px' }}>
            <summary>技術詳情與資料來源</summary>
            <div>狀態版本 {query.status_version}</div>
          </details>
        </div>
      )}

      {recoveryQuery && pendingRecoveryTargets.length > 0 && (
        <section aria-label="歷史簽回人工修復" style={{ border: '2px solid #f59e0b', borderRadius: '12px', padding: '14px', display: 'grid', gap: '12px' }}>
          <header>
            <strong>🧾 歷史簽回人工修復</strong>
            <div style={{ fontSize: '0.82rem', color: '#74593f', marginTop: '4px' }}>
              尚有 {pendingRecoveryTargets.length} 個未完成對象。每筆都必須先核對歷史簽回證據並檢查影響；月嫂完成後才可修復客戶。
            </div>
            <details style={{ fontSize: '0.78rem', color: '#74593f' }}>
              <summary>技術詳情與資料來源</summary>
              <div>Session {recoveryQuery.session_id}｜狀態版本 {recoveryQuery.status_version}｜配對方案 {recoveryQuery.matching_plan_id}</div>
            </details>
          </header>

          {pendingRecoveryTargets.map((target) => {
            const key = recoveryTargetKey(target);
            const lineageComplete = hasCompleteLegacyLineage(target);
            const clientBlocked = target.scope === 'client' && (!allRecoveryStaffReported || recoveryQuery.commitment_id === null);
            const activePreview = uiState.type === 'recovery_preview_ready'
              && recoveryTargetKey(uiState.recovery.target) === key
              ? uiState.recovery
              : null;
            return (
              <article key={key} aria-label={`${target.scope === 'staff' ? '月嫂' : '客戶'} ${target.target_subject_reference} 歷史簽回修復`} style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px', display: 'grid', gap: '8px' }}>
                <strong>{target.scope === 'staff' ? '月嫂' : '客戶'} {target.target_subject_reference}</strong>
                <div style={{ fontSize: '0.8rem', color: '#74593f' }}>
                  {lineageComplete ? '歷史簽回證據完整，可檢查修復影響。' : '找不到完整歷史簽回證據，無法檢查修復影響。'}
                </div>
                <details style={{ fontSize: '0.78rem', color: '#74593f' }}>
                  <summary>簽回證據技術詳情</summary>
                  <div>
                    現行文件版本 {target.current_document_version_id}
                    {lineageComplete
                      ? `｜歷史文件 ${target.legacy_document_version_id}／事件 ${target.signing_event_id}／receipt ${target.command_receipt_id}／證據 ${target.legacy_media_sha256!.slice(0, 8)}…`
                      : '｜歷史簽回證據不完整'}
                  </div>
                </details>
                {clientBlocked && <div role="status">需先完成所有月嫂修復，並由系統確認最新簽約狀態。</div>}
                <label style={{ display: 'grid', gap: '4px' }}>
                  修復原因與人工核對依據
                  <input
                    value={recoveryReasons[key] ?? ''}
                    disabled={busy || clientBlocked || !lineageComplete}
                    maxLength={1000}
                    onChange={(event) => {
                      setRecoveryReasons((current) => ({ ...current, [key]: event.target.value }));
                      identities.current.delete(`legacy-${key}`);
                      if (activePreview) setUiState({ type: 'ready' });
                    }}
                  />
                </label>
                <button
                  type="button"
                  disabled={busy || clientBlocked || !lineageComplete || !(recoveryReasons[key] ?? '').trim()}
                  onClick={() => void previewLegacyRecovery(target)}
                >
                  檢查{target.scope === 'staff' ? '月嫂' : '客戶'}歷史簽回修復影響
                </button>
                {activePreview && (
                  <div style={{ padding: '10px', background: '#fffbeb', borderRadius: '8px', display: 'grid', gap: '6px' }}>
                    <div>現行文件與歷史簽回證據已完成一致性檢查。</div>
                    <details style={{ fontSize: '0.78rem', color: '#74593f' }}>
                      <summary>檢查技術詳情</summary>
                      <div>Preview 已綁定現行文件版本 {activePreview.preview.current_document_version_id} 與歷史證據 {activePreview.preview.legacy_media_sha256.slice(0, 8)}…</div>
                    </details>
                    {activePreview.preview.blockers.length > 0 && (
                      <ul>{activePreview.preview.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
                    )}
                    <label>
                      <input
                        type="checkbox"
                        checked={activePreview.confirmed}
                        onChange={(event) => setUiState({
                          type: 'recovery_preview_ready',
                          recovery: { ...activePreview, confirmed: event.target.checked },
                        })}
                      />
                      我已核對案件、對象、現行文件與歷史簽回證據
                    </label>
                    <button
                      type="button"
                      disabled={!activePreview.confirmed || !activePreview.preview.can_apply}
                      onClick={() => void applyLegacyRecovery()}
                    >
                      確認套用此筆歷史簽回修復
                    </button>
                  </div>
                )}
              </article>
            );
          })}
        </section>
      )}

      {query?.unsigned_document && (
        <section aria-label="未簽契約 PDF" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
          <strong>未簽契約 PDF</strong>
          <div style={{ fontSize: '0.82rem', margin: '5px 0' }}>
            {query.unsigned_document.filename}｜{query.unsigned_document.size_bytes.toLocaleString()} bytes
          </div>
          <div style={{ display: 'grid', gap: '6px' }}>
            {query.staff_targets.map((target) => (
              <button
                key={target.matching_segment_id}
                type="button"
                disabled={busy}
                onClick={() => void downloadUnsigned(target.document_version_id, `月嫂 ${target.staff_subject_reference} `)}
              >
                下載月嫂 {target.staff_subject_reference} 未簽契約 PDF
              </button>
            ))}
            <button
              type="button"
              disabled={busy}
              onClick={() => void downloadUnsigned(
                query.client_target.document_version_id,
                `客戶 ${query.client_target.client_subject_reference} `,
              )}
            >
              下載客戶 {query.client_target.client_subject_reference} 未簽契約 PDF
            </button>
          </div>
        </section>
      )}

      {query?.staff_targets.map((target) => (
        <section key={target.matching_segment_id} aria-label={`月嫂 ${target.staff_subject_reference} 外部簽署回報`} style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
          <strong>月嫂 {target.staff_subject_reference}</strong>
          <div style={{ fontSize: '0.82rem', margin: '5px 0' }}>{target.reported ? '完成回報已記錄' : '尚待外部簽署完成回報'}</div>
          {!target.reported && query.state === 'staff_reporting' && !isRecoveryOwnedTarget('staff', target.matching_segment_id) && (
            <>
              <label style={{ display: 'grid', gap: '4px' }}>
                月嫂完成證據
                <input
                  value={staffReasons[target.matching_segment_id] ?? ''}
                  disabled={busy}
                  maxLength={500}
                  onChange={(event) => {
                    setStaffReasons((current) => ({ ...current, [target.matching_segment_id]: event.target.value }));
                    identities.current.delete(`staff-${target.matching_segment_id}`);
                  }}
                />
              </label>
              <button
                type="button"
                disabled={busy || !(staffReasons[target.matching_segment_id] ?? '').trim()}
                onClick={() => void runReport(`staff-${target.matching_segment_id}`, (identity) =>
                  contractExternalSigningClient.recordStaffCompletionReport(caseNo, target.matching_segment_id, {
                    expected_status_version: query.status_version,
                    expected_document_version_id: target.document_version_id,
                    confirmation_method: confirmationMethod,
                    reason: staffReasons[target.matching_segment_id] ?? '',
                  }, identity))}
              >
                記錄月嫂 {target.staff_subject_reference} 完成回報
              </button>
            </>
          )}
        </section>
      ))}

      {query && (
        <label style={{ display: 'grid', gap: '4px', maxWidth: '320px' }}>
          受控人工確認方式
          <select value={confirmationMethod} disabled={busy} onChange={(event) => {
            setConfirmationMethod(event.target.value as ExternalSigningConfirmationMethod);
            identities.current.clear();
            if (uiState.type === 'recovery_preview_ready') setUiState({ type: 'ready' });
          }}>
            <option value="phone">電話確認</option>
            <option value="paper">紙本確認</option>
            <option value="in_person">當面確認</option>
            <option value="verified_other">其他已驗證方式</option>
          </select>
        </label>
      )}

      {query?.state === 'staff_reports_complete' && !query.client_target.reported && query.commitment_id !== null && !isRecoveryOwnedTarget('client', null) && (
        <section aria-label="客戶外部簽署回報" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
          <strong>客戶 {query.client_target.client_subject_reference}</strong>
          <label style={{ display: 'grid', gap: '4px' }}>
            客戶完成證據
            <input value={clientReason} disabled={busy} maxLength={500} onChange={(event) => {
              setClientReason(event.target.value);
              identities.current.delete('client-report');
            }} />
          </label>
          <button
            type="button"
            disabled={busy || !clientReason.trim()}
            onClick={() => void runReport('client-report', (identity) =>
              contractExternalSigningClient.recordClientCompletionReport(caseNo, {
                expected_status_version: query.status_version,
                expected_document_version_id: query.client_target.document_version_id,
                expected_commitment_id: query.commitment_id!,
                confirmation_method: confirmationMethod,
                reason: clientReason,
              }, identity))}
          >
            記錄客戶完成回報
          </button>
        </section>
      )}

      {query?.state === 'client_reported_final_pdf_pending'
        && uiState.type !== 'receipt_committed'
        && !(uiState.type === 'outcome_unknown' && uiState.expected.commandType === 'apply_final_signed_contract') && (
        <section aria-label="最終簽署 PDF 納管" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px', display: 'grid', gap: '8px' }}>
          <strong>最終簽署 PDF 待回收</strong>
          <label style={{ display: 'grid', gap: '4px' }}>
            最終簽署 PDF
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={busy}
              onChange={(event) => {
                setFinalFile(event.target.files?.item(0) ?? null);
                identities.current.delete('final-stage');
                identities.current.delete('final-apply');
                setUiState({ type: 'ready' });
              }}
            />
          </label>
          <button type="button" disabled={busy || !finalFile} onClick={() => void previewFinalDocument()}>
            建立最終 PDF 預覽
          </button>
          {uiState.type === 'preview_ready' && (
            <div style={{ padding: '10px', background: '#f0fdf4', borderRadius: '8px' }}>
              <div>{uiState.preview.filename}｜{uiState.preview.size_bytes.toLocaleString()} bytes</div>
              <div>PDF 類型與完整性已確認。</div>
              {uiState.preview.blockers.length > 0 && (
                <ul>{uiState.preview.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
              )}
              <label>
                <input
                  type="checkbox"
                  checked={uiState.confirmed}
                  onChange={(event) => setUiState({ ...uiState, confirmed: event.target.checked })}
                />
                我已核對案件、檔名、PDF 類型與版本
              </label>
              <button
                type="button"
                disabled={!uiState.confirmed || !uiState.preview.can_apply}
                onClick={() => void applyFinalDocument()}
              >
                確認套用最終簽署 PDF
              </button>
            </div>
          )}
        </section>
      )}

      {uiState.type === 'working' && <div role="status">正在處理外部簽約操作…</div>}
      {uiState.type === 'error' && <div role="alert">{uiState.message}</div>}
      {uiState.type === 'outcome_unknown' && (
        <div role="alert">
          <div>{uiState.message}</div>
          <button type="button" onClick={() => void reconcileUnknown()}>重新確認原操作結果</button>
        </div>
      )}
      {uiState.type === 'receipt_committed' && (
        <div role="status">
          <div>{uiState.message}</div>
          <button type="button" onClick={() => void retryReadback()}>重新確認最終 PDF</button>
        </div>
      )}
      {notice && <div role="status">{notice}</div>}
    </section>
  );
}
