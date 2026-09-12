/**
 * File: ContractExternalSigningActions.tsx
 * Description: 呈現外部簽約 successor closed states、完成回報與最終 PDF 確認、Apply、receipt/readback。
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
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
  type PreparedUnsignedDocument,
  type StaffReminderReadiness,
} from '../api/orders/contract_external_signing_client';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import { sessionClient } from '../api/auth/session_client';
import {
  orderMutationFlowStore,
  type ExternalSigningHandoffCommand,
  type ExternalSigningHandoffFlowState,
  type ExternalSigningUnsignedPreparationCommand,
  type ExternalSigningUnsignedPreparationFlowState,
} from '../adapters/orders/order_mutation_flow_store';

export interface ContractExternalSigningActionsProps {
  caseNo: string;
  onCommitted?: () => Promise<void> | void;
}

type WorkingOperation = 'query' | 'prepare_client' | 'prepare_staff' | 'download' | 'handoff' | 'reminder_check' | 'reminder_enqueue' | 'staff_report' | 'client_report' | 'final_preview' | 'final_apply' | 'receipt' | 'readback';

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
    if (error.code === 'external_signing_accepted_plan_required') return '請先完成客戶對推薦方案的確認，再準備契約。';
    if (error.code === 'external_signing_session_facts_unavailable') return '簽約資料尚未備妥，請先確認推薦方案與契約文件。';
    if (error.code === 'contract_pdf_external_reference_unresolved') return '契約模板缺少舊版引用內容，尚不能產生可簽署 PDF；請先補齊模板。';
    if (error.code === 'contract_pdf_required_mapping_missing') return '契約必要資料尚未齊全，請先在契約欄位預覽核對案件資料與收款設定。';
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
  if (!query.handoff_recorded) return '待送交外部簽署平台';
  switch (query.state) {
    case 'staff_reporting': return '已送交外部平台，等待最終簽署 PDF';
    case 'staff_reports_complete': return '已送交外部平台，等待最終簽署 PDF';
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

const subscribeExternalSigningHandoff = (listener: () => void) => orderMutationFlowStore.subscribe(listener);
let handoffOperationSequence = 0;
let unsignedPreparationOperationSequence = 0;

function nextHandoffOperationToken(): number {
  handoffOperationSequence += 1;
  return handoffOperationSequence;
}

function nextUnsignedPreparationOperationToken(): number {
  unsignedPreparationOperationSequence += 1;
  return unsignedPreparationOperationSequence;
}

function handoffReceiptMatches(
  command: ExternalSigningHandoffCommand,
  receipt: { session_id: string; resulting_status_version: number },
): boolean {
  return receipt.session_id === command.sessionId
    && receipt.resulting_status_version === command.expectedStatusVersion + 1;
}

function unsignedPreparationReadbackMatches(
  command: ExternalSigningUnsignedPreparationCommand,
  receipt: PreparedUnsignedDocument,
  fresh: ContractExternalSigningQuery,
): boolean {
  if (
    fresh.case_no !== command.caseNo
    || (command.sessionId !== null && fresh.session_id !== command.sessionId)
  ) return false;
  if (command.kind === 'client') {
    return fresh.client_target.document_version_id === receipt.document_version_id;
  }
  return command.segmentId !== null
    && fresh.staff_targets.some((target) => (
      target.matching_segment_id === command.segmentId
      && target.document_version_id === receipt.document_version_id
    ));
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
  const unsignedDownloadController = useRef<AbortController | null>(null);
  const reminderReadinessController = useRef<AbortController | null>(null);
  const activeHandoffOperation = useRef<{ caseNo: string; operationToken: number } | null>(null);
  const activeUnsignedPreparationOperation = useRef<{ caseNo: string; operationToken: number } | null>(null);
  const [query, setQuery] = useState<ContractExternalSigningQuery | null>(null);
  const [preparationSegments, setPreparationSegments] = useState<number[]>([]);
  const [recoveryQuery, setRecoveryQuery] = useState<LegacyRecoveryQuery | null>(null);
  const [uiState, setUiState] = useState<ContractExternalSigningUiState>({ type: 'querying' });
  const [notice, setNotice] = useState<string | null>(null);
  const [recoveryReasons, setRecoveryReasons] = useState<Record<string, string>>({});
  const [confirmationMethod] = useState<ExternalSigningConfirmationMethod>('verified_other');
  const [finalFile, setFinalFile] = useState<File | null>(null);
  const [reminderReadiness, setReminderReadiness] = useState<Record<number, StaffReminderReadiness>>({});
  const handoffFlow = useSyncExternalStore(
    subscribeExternalSigningHandoff,
    () => orderMutationFlowStore.getExternalSigningHandoff(caseNo),
  );
  const unsignedPreparationFlow = useSyncExternalStore(
    subscribeExternalSigningHandoff,
    () => orderMutationFlowStore.getExternalSigningUnsignedPreparation(caseNo),
  );

  const loadQuery = useCallback(async (signal?: AbortSignal): Promise<ContractExternalSigningQuery> => {
    const generation = ++requestGeneration.current;
    setUiState({ type: 'querying' });
    const value = await contractExternalSigningClient.query(caseNo, { signal });
    const recovery = value.state === 'superseded' || value.client_target.document_version_id === null
      ? null
      : await contractExternalSigningClient.queryLegacyRecovery(caseNo, { signal }).catch((error) => {
          if (error instanceof ApiHttpError && (error.status === 401 || error.status === 403)) throw error;
          if (!signal?.aborted && generation === requestGeneration.current) setNotice('歷史簽回資料暫時無法查詢；目前契約操作仍可使用。');
          return null;
        });
    if (recovery) assertRecoveryQueryMatchesCurrent(value, recovery);
    if (generation !== requestGeneration.current) return value;
    setQuery(value);
    setRecoveryQuery(recovery);
    setUiState({ type: 'ready' });
    return value;
  }, [caseNo]);

  useEffect(() => {
    unsignedDownloadController.current?.abort();
    reminderReadinessController.current?.abort();
    const controller = new AbortController();
    setQuery(null);
    setPreparationSegments([]);
    setRecoveryQuery(null);
    setNotice(null);
    setFinalFile(null);
    setReminderReadiness({});
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
    }).catch(async (error) => {
      if (controller.signal.aborted) return;
      if (error instanceof ApiHttpError && error.code === 'external_signing_session_facts_unavailable') {
        try {
          const legacy = await contractSigningClient.query(caseNo, { signal: controller.signal });
          if (!controller.signal.aborted && legacy.staff_segments.length > 0) {
            setPreparationSegments(legacy.staff_segments.map((segment) => segment.segment_id));
            setUiState({ type: 'ready' });
            return;
          }
        } catch {
          // Preserve the canonical successor error below.
        }
      }
      if (!controller.signal.aborted) setUiState({ type: 'error', message: safeErrorMessage(error) });
    });
    return () => {
      const activeHandoff = activeHandoffOperation.current;
      const savedHandoff = activeHandoff && orderMutationFlowStore.getExternalSigningHandoff(activeHandoff.caseNo);
      if (activeHandoff && savedHandoff?.operationToken === activeHandoff.operationToken) {
        if (savedHandoff.status === 'applying') {
          orderMutationFlowStore.setExternalSigningHandoff(activeHandoff.caseNo, {
            ...savedHandoff,
            status: 'outcome_unknown',
            error: '外部平台交接請求在畫面離開時仍未確認；請以原操作重新確認。',
          });
        } else if (savedHandoff.status === 'observing') {
          orderMutationFlowStore.setExternalSigningHandoff(activeHandoff.caseNo, {
            ...savedHandoff,
            status: 'observation_failed',
            error: '外部平台交接收據已收到，但畫面離開前尚未完成狀態讀取；只能重新讀取。',
          });
        }
      }
      activeHandoffOperation.current = null;
      const activePreparation = activeUnsignedPreparationOperation.current;
      const savedPreparation = activePreparation && orderMutationFlowStore.getExternalSigningUnsignedPreparation(activePreparation.caseNo);
      if (activePreparation && savedPreparation?.operationToken === activePreparation.operationToken) {
        if (savedPreparation.status === 'applying') {
          orderMutationFlowStore.setExternalSigningUnsignedPreparation(activePreparation.caseNo, {
            ...savedPreparation,
            status: 'outcome_unknown',
            error: '未簽契約準備請求在畫面離開時仍未確認；請以原操作重新確認。',
          });
        } else if (savedPreparation.status === 'observing') {
          orderMutationFlowStore.setExternalSigningUnsignedPreparation(activePreparation.caseNo, {
            ...savedPreparation,
            status: 'observation_failed',
            error: '未簽契約準備收據已收到，但畫面離開前尚未完成狀態讀取；只能重新讀取。',
          });
        }
      }
      activeUnsignedPreparationOperation.current = null;
      requestGeneration.current += 1;
      controller.abort();
      unsignedDownloadController.current?.abort();
      reminderReadinessController.current?.abort();
    };
  }, [caseNo, loadQuery]);

  const ownsHandoffOperation = (caseNumber: string, operationToken: number): boolean => {
    const active = activeHandoffOperation.current;
    return active?.caseNo === caseNumber
      && active.operationToken === operationToken
      && orderMutationFlowStore.getExternalSigningHandoff(caseNumber)?.operationToken === operationToken;
  };

  const releaseHandoffOperation = (operationToken: number) => {
    if (activeHandoffOperation.current?.operationToken === operationToken) {
      activeHandoffOperation.current = null;
    }
  };

  const ownsUnsignedPreparationOperation = (caseNumber: string, operationToken: number): boolean => {
    const active = activeUnsignedPreparationOperation.current;
    return active?.caseNo === caseNumber
      && active.operationToken === operationToken
      && orderMutationFlowStore.getExternalSigningUnsignedPreparation(caseNumber)?.operationToken === operationToken;
  };

  const releaseUnsignedPreparationOperation = (operationToken: number) => {
    if (activeUnsignedPreparationOperation.current?.operationToken === operationToken) {
      activeUnsignedPreparationOperation.current = null;
    }
  };

  const observeUnsignedPreparation = async (
    state: ExternalSigningUnsignedPreparationFlowState,
    request: number,
  ) => {
    if (state.receipt === null) throw new Error('未簽契約準備尚未收到收據，不能只讀取狀態。');
    const { command, receipt } = state;
    if (!ownsUnsignedPreparationOperation(command.caseNo, state.operationToken)) return;
    orderMutationFlowStore.setExternalSigningUnsignedPreparation(command.caseNo, { ...state, status: 'observing', error: null });
    let fresh: ContractExternalSigningQuery;
    try {
      fresh = await contractExternalSigningClient.query(command.caseNo);
    } catch (error) {
      if (!(command.kind === 'staff'
        && error instanceof ApiHttpError
        && error.code === 'external_signing_session_facts_unavailable')) throw error;
      const legacy = await contractSigningClient.query(command.caseNo);
      if (!ownsUnsignedPreparationOperation(command.caseNo, state.operationToken)) return;
      const segmentObserved = command.segmentId !== null
        && legacy.staff_segments.some((segment) => segment.segment_id === command.segmentId);
      const documentObserved = legacy.documents.some((document) => (
        document.document_version_id === receipt.document_version_id
        && document.scope === 'staff'
      ));
      if (!segmentObserved || !documentObserved) {
        throw new Error('月嫂未簽契約收據尚未出現在正式契約狀態；只能重新讀取。');
      }
      orderMutationFlowStore.clearExternalSigningUnsignedPreparation(command.caseNo);
      if (request !== requestGeneration.current) return;
      setQuery(null);
      setPreparationSegments(legacy.staff_segments.map((segment) => segment.segment_id));
      setUiState({ type: 'ready' });
      setNotice(`${receipt.replayed ? '已重新確認' : '已產生'}月嫂分段 #${command.segmentId} 未簽 PDF。`);
      return;
    }
    if (!ownsUnsignedPreparationOperation(command.caseNo, state.operationToken)) return;
    if (!unsignedPreparationReadbackMatches(command, receipt, fresh)) {
      throw new Error('未簽契約準備收據與原案件、簽約工作或服務區段不一致；只能重新讀取。');
    }
    orderMutationFlowStore.clearExternalSigningUnsignedPreparation(command.caseNo);
    if (request !== requestGeneration.current) return;
    setQuery(fresh);
    setPreparationSegments([]);
    setUiState({ type: 'ready' });
    setNotice(command.kind === 'client'
      ? `客戶未簽契約 PDF「${receipt.filename}」已準備完成。`
      : `${receipt.replayed ? '已重新確認' : '已產生'}月嫂分段 #${command.segmentId} 未簽 PDF。`);
  };

  const submitUnsignedPreparation = async (
    command: ExternalSigningUnsignedPreparationCommand,
    recovery: boolean,
    downloadAfterObserved: boolean,
  ) => {
    const request = requestGeneration.current;
    const operationToken = nextUnsignedPreparationOperationToken();
    activeUnsignedPreparationOperation.current = { caseNo: command.caseNo, operationToken };
    orderMutationFlowStore.setExternalSigningUnsignedPreparation(command.caseNo, {
      status: 'applying', operationToken, command, receipt: null, error: null,
    });
    let receipt: PreparedUnsignedDocument;
    try {
      receipt = command.kind === 'client'
        ? await contractExternalSigningClient.prepareClientUnsignedPdf(command.caseNo, command.identity)
        : await contractExternalSigningClient.prepareStaffUnsignedPdf(command.caseNo, command.segmentId!, command.identity);
    } catch (error) {
      if (!ownsUnsignedPreparationOperation(command.caseNo, operationToken)) return;
      if (!recovery && error instanceof ApiHttpError && !error.retryable) {
        orderMutationFlowStore.clearExternalSigningUnsignedPreparation(command.caseNo);
        if (request === requestGeneration.current) setUiState({ type: 'error', message: safeErrorMessage(error) });
      } else {
        const message = recovery
          ? '原未簽契約準備結果仍未確認；請恢復原帳號權限後以原操作重新確認。'
          : '未簽契約準備結果尚未確認；請以原操作重新確認。';
        orderMutationFlowStore.setExternalSigningUnsignedPreparation(command.caseNo, {
          status: 'outcome_unknown', operationToken, command, receipt: null, error: message,
        });
        if (request === requestGeneration.current) setUiState({ type: 'error', message });
      }
      releaseUnsignedPreparationOperation(operationToken);
      return;
    }
    if (!ownsUnsignedPreparationOperation(command.caseNo, operationToken)) return;
    const received: ExternalSigningUnsignedPreparationFlowState = {
      status: 'observation_failed', operationToken, command, receipt, error: null,
    };
    orderMutationFlowStore.setExternalSigningUnsignedPreparation(command.caseNo, received);
    try {
      await observeUnsignedPreparation(received, request);
      if (downloadAfterObserved && command.kind === 'client' && request === requestGeneration.current) {
        await downloadUnsigned(receipt.document_version_id, '客戶');
      }
    } catch (error) {
      if (!ownsUnsignedPreparationOperation(command.caseNo, operationToken)) return;
      const message = safeErrorMessage(error);
      const saved = orderMutationFlowStore.getExternalSigningUnsignedPreparation(command.caseNo);
      if (saved?.receipt) orderMutationFlowStore.setExternalSigningUnsignedPreparation(command.caseNo, {
        ...saved, status: 'observation_failed', error: message,
      });
      if (request === requestGeneration.current) setUiState({ type: 'error', message });
    }
    releaseUnsignedPreparationOperation(operationToken);
  };

  const prepareUnsigned = async (kind: 'client' | 'staff', segmentId: number | null) => {
    if (unsignedPreparationFlow || (!query && kind === 'client')) return;
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor) {
      setUiState({ type: 'error', message: '請先登入後再準備未簽契約。' });
      return;
    }
    const command: ExternalSigningUnsignedPreparationCommand = {
      kind, caseNo, sessionId: query?.session_id ?? null, segmentId, actor,
      identity: createExternalSigningCommandIdentity(kind === 'client' ? 'prepare-client' : `prepare-${segmentId}`),
    };
    setUiState({ type: 'working', operation: kind === 'client' ? 'prepare_client' : 'prepare_staff' });
    setNotice(null);
    await submitUnsignedPreparation(command, false, kind === 'client');
  };

  const retryUnsignedPreparationOriginal = async () => {
    if (unsignedPreparationFlow?.status !== 'outcome_unknown') return;
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor || actor !== unsignedPreparationFlow.command.actor) {
      setUiState({ type: 'error', message: '原未簽契約準備必須由原帳號重新確認；未確認結果會保留。' });
      return;
    }
    setUiState({ type: 'working', operation: unsignedPreparationFlow.command.kind === 'client' ? 'prepare_client' : 'prepare_staff' });
    setNotice(null);
    await submitUnsignedPreparation(unsignedPreparationFlow.command, true, false);
  };

  const retryUnsignedPreparationReadback = async () => {
    if (unsignedPreparationFlow?.status !== 'observation_failed' || unsignedPreparationFlow.receipt === null) return;
    const request = requestGeneration.current;
    const operationToken = nextUnsignedPreparationOperationToken();
    const state: ExternalSigningUnsignedPreparationFlowState = {
      ...unsignedPreparationFlow, status: 'observing', operationToken, error: null,
    };
    activeUnsignedPreparationOperation.current = { caseNo, operationToken };
    orderMutationFlowStore.setExternalSigningUnsignedPreparation(caseNo, state);
    setUiState({ type: 'working', operation: 'readback' });
    setNotice(null);
    try {
      await observeUnsignedPreparation(state, request);
    } catch (error) {
      if (!ownsUnsignedPreparationOperation(caseNo, operationToken)) return;
      const message = safeErrorMessage(error);
      const saved = orderMutationFlowStore.getExternalSigningUnsignedPreparation(caseNo);
      if (saved?.receipt) orderMutationFlowStore.setExternalSigningUnsignedPreparation(caseNo, {
        ...saved, status: 'observation_failed', error: message,
      });
      if (request === requestGeneration.current) setUiState({ type: 'error', message });
    }
    releaseUnsignedPreparationOperation(operationToken);
  };

  const observeHandoff = async (state: ExternalSigningHandoffFlowState, request: number) => {
    if (state.receipt === null) throw new Error('外部平台交接尚未收到收據，不能只讀取狀態。');
    const { command, receipt } = state;
    if (!handoffReceiptMatches(command, receipt)) {
      throw new Error('外部平台交接收據與原案件、簽約工作或版本不一致；不能視為完成。');
    }
    if (!ownsHandoffOperation(command.caseNo, state.operationToken)) return;
    orderMutationFlowStore.setExternalSigningHandoff(command.caseNo, { ...state, status: 'observing', error: null });
    const fresh = await contractExternalSigningClient.query(command.caseNo);
    if (!ownsHandoffOperation(command.caseNo, state.operationToken)) return;
    if (
      fresh.case_no !== command.caseNo
      || fresh.session_id !== command.sessionId
      || !fresh.handoff_recorded
      || fresh.status_version < receipt.resulting_status_version
    ) {
      throw new Error('交接收據後回讀與原案件、簽約工作或版本不一致；只能重新讀取。');
    }
    orderMutationFlowStore.clearExternalSigningHandoff(command.caseNo);
    if (request !== requestGeneration.current) return;
    setQuery(fresh);
    setUiState({ type: 'ready' });
    setNotice(receipt.replayed ? '已重新確認外部平台交接。' : '已記錄送交外部簽署平台。');
  };

  const submitHandoff = async (command: ExternalSigningHandoffCommand, recovery: boolean) => {
    const request = requestGeneration.current;
    const operationToken = nextHandoffOperationToken();
    activeHandoffOperation.current = { caseNo: command.caseNo, operationToken };
    orderMutationFlowStore.setExternalSigningHandoff(command.caseNo, { status: 'applying', operationToken, command, receipt: null, error: null });
    let receipt: ExternalSigningHandoffFlowState['receipt'];
    try {
      receipt = await contractExternalSigningClient.recordHandoff(
        command.caseNo,
        command.expectedStatusVersion,
        command.identity,
      );
    } catch (error) {
      if (!ownsHandoffOperation(command.caseNo, operationToken)) return;
      if (!recovery && error instanceof ApiHttpError && !error.retryable) {
        orderMutationFlowStore.clearExternalSigningHandoff(command.caseNo);
        if (request === requestGeneration.current) setUiState({ type: 'error', message: safeErrorMessage(error) });
      } else {
        const message = recovery
          ? '原外部平台交接結果仍未確認；請恢復原帳號權限後以原操作重新確認。'
          : '外部平台交接結果尚未確認；請以原操作重新確認。';
        orderMutationFlowStore.setExternalSigningHandoff(command.caseNo, {
          status: 'outcome_unknown',
          operationToken,
          command,
          receipt: null,
          error: message,
        });
        if (request === requestGeneration.current) setUiState({ type: 'error', message });
      }
      releaseHandoffOperation(operationToken);
      return;
    }
    if (!ownsHandoffOperation(command.caseNo, operationToken)) return;
    const received: ExternalSigningHandoffFlowState = {
      status: 'observation_failed',
      operationToken,
      command,
      receipt,
      error: handoffReceiptMatches(command, receipt)
        ? null
        : '外部平台交接收據與原案件、簽約工作或版本不一致；只能重新讀取。',
    };
    orderMutationFlowStore.setExternalSigningHandoff(command.caseNo, received);
    if (!handoffReceiptMatches(command, receipt)) {
      if (request === requestGeneration.current) setUiState({ type: 'error', message: received.error! });
      releaseHandoffOperation(operationToken);
      return;
    }
    try {
      await observeHandoff(received, request);
    } catch (error) {
      if (!ownsHandoffOperation(command.caseNo, operationToken)) return;
      const message = safeErrorMessage(error);
      const saved = orderMutationFlowStore.getExternalSigningHandoff(command.caseNo);
      if (saved?.receipt) orderMutationFlowStore.setExternalSigningHandoff(command.caseNo, { ...saved, status: 'observation_failed', error: message });
      if (request === requestGeneration.current) setUiState({ type: 'error', message });
    }
    releaseHandoffOperation(operationToken);
  };

  const recordHandoff = async () => {
    if (!query || query.handoff_recorded || handoffFlow) return;
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor) {
      setUiState({ type: 'error', message: '請先登入後再記錄外部平台交接。' });
      return;
    }
    const command: ExternalSigningHandoffCommand = {
      caseNo,
      sessionId: query.session_id,
      expectedStatusVersion: query.status_version,
      actor,
      identity: createExternalSigningCommandIdentity('handoff'),
    };
    setUiState({ type: 'working', operation: 'handoff' });
    setNotice(null);
    await submitHandoff(command, false);
  };

  const retryHandoffOriginal = async () => {
    if (handoffFlow?.status !== 'outcome_unknown') return;
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor || actor !== handoffFlow.command.actor) {
      setUiState({ type: 'error', message: '原外部平台交接必須由原帳號重新確認；未確認結果會保留。' });
      return;
    }
    setUiState({ type: 'working', operation: 'handoff' });
    setNotice(null);
    await submitHandoff(handoffFlow.command, true);
  };

  const retryHandoffReadback = async () => {
    if (handoffFlow?.status !== 'observation_failed' || handoffFlow.receipt === null) return;
    const request = requestGeneration.current;
    const operationToken = nextHandoffOperationToken();
    const state: ExternalSigningHandoffFlowState = { ...handoffFlow, status: 'observing', operationToken, error: null };
    activeHandoffOperation.current = { caseNo: caseNo, operationToken };
    orderMutationFlowStore.setExternalSigningHandoff(caseNo, state);
    setUiState({ type: 'working', operation: 'readback' });
    setNotice(null);
    try {
      await observeHandoff(state, request);
    } catch (error) {
      if (!ownsHandoffOperation(caseNo, operationToken)) return;
      const message = safeErrorMessage(error);
      const saved = orderMutationFlowStore.getExternalSigningHandoff(caseNo);
      if (saved?.receipt) orderMutationFlowStore.setExternalSigningHandoff(caseNo, { ...saved, status: 'observation_failed', error: message });
      if (request === requestGeneration.current) setUiState({ type: 'error', message });
    }
    releaseHandoffOperation(operationToken);
  };

  const checkReminderReadiness = async (segmentId: number) => {
    reminderReadinessController.current?.abort();
    const controller = new AbortController();
    reminderReadinessController.current = controller;
    const generation = requestGeneration.current;
    setUiState({ type: 'working', operation: 'reminder_check' });
    setNotice(null);
    try {
      const readiness = await contractExternalSigningClient.getStaffReminderReadiness(caseNo, segmentId, controller.signal);
      if (controller.signal.aborted || generation !== requestGeneration.current) return;
      setReminderReadiness((current) => ({ ...current, [segmentId]: readiness }));
      setUiState({ type: 'ready' });
    } catch (error) {
      if (controller.signal.aborted || generation !== requestGeneration.current) return;
      setUiState({ type: 'error', message: safeErrorMessage(error) });
    }
  };

  const enqueueReminder = async (
    segmentId: number,
    staffSubjectReference: string,
    documentVersionId: number,
  ) => {
    const readiness = reminderReadiness[segmentId];
    if (!readiness?.ready || readiness.document_version_id !== documentVersionId) return;
    const identity = currentIdentity(identities.current, `reminder-${segmentId}`);
    setUiState({ type: 'working', operation: 'reminder_enqueue' });
    setNotice(null);
    try {
      const task = await contractExternalSigningClient.enqueueStaffReminder(
        caseNo, segmentId, documentVersionId, identity,
      );
      identities.current.delete(`reminder-${segmentId}`);
      setNotice(task.replayed
        ? `月嫂 ${staffSubjectReference} 的 LINE 契約通知工作已存在（工作 #${task.task_id}）。`
        : `已建立月嫂 ${staffSubjectReference} 的 LINE 契約通知工作 #${task.task_id}；尚未傳送。`);
      setUiState({ type: 'ready' });
    } catch (error) {
      setUiState({ type: 'error', message: safeErrorMessage(error) });
    }
  };

  const downloadUnsigned = async (documentVersionId: number, targetLabel: string) => {
    unsignedDownloadController.current?.abort();
    const controller = new AbortController();
    unsignedDownloadController.current = controller;
    const generation = requestGeneration.current;
    setUiState({ type: 'working', operation: 'download' });
    setNotice(null);
    try {
      const artifact = await contractExternalSigningClient.downloadUnsignedPdf(
        caseNo,
        documentVersionId,
        controller.signal,
      );
      if (controller.signal.aborted || generation !== requestGeneration.current) return;
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
      if (controller.signal.aborted || generation !== requestGeneration.current) return;
      setUiState({ type: 'error', message: safeErrorMessage(error) });
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


  return (
    <section aria-label="外部平台簽約與最終 PDF" data-control-id="orders.contract-external-signing.actions" style={{ display: 'grid', gap: '14px' }}>
      <header>
        <h3 style={{ margin: 0 }}>契約下載與簽回</h3>
        <p style={{ margin: '6px 0 0', color: '#74593f', fontSize: '0.84rem' }}>
          送交外部平台後，請於雙方完成簽署時上傳最終 PDF；最終 PDF 驗收才會完成契約並開始定金核銷。
        </p>
      </header>

      {query && (
        <div role="status" style={{ padding: '10px 12px', border: '1px solid #fed7aa', borderRadius: '10px', background: '#fff8f6' }}>
          <strong>{stateLabel(query)}</strong>
        </div>
      )}

      <div className="order-case-document-grid" aria-label="下載兩種契約">
        <article><h3>客戶契約 PDF</h3><p>下載未簽署版本，供客戶確認與簽署。</p>
          <button type="button" disabled={busy || !query?.unsigned_document || query.client_target.document_version_id === null} onClick={() => {
            if (query?.unsigned_document && query.client_target.document_version_id !== null) void downloadUnsigned(query.client_target.document_version_id, `客戶 ${query.client_target.client_subject_reference} `);
          }}>下載客戶契約 PDF</button>
          {query?.state !== 'completed' && <button type="button" disabled={busy || !!unsignedPreparationFlow || !query} onClick={() => void prepareUnsigned('client', null)}>準備並下載客戶契約 PDF</button>}
          {!query && preparationSegments.length > 0 && <p>請先準備服務人員契約，再準備客戶契約。</p>}
          {(!query?.unsigned_document || query.client_target.document_version_id === null) && <p>尚無可下載文件時，請先準備契約；需已確認推薦方案，不會發送訊息。</p>}
        </article>
        <article><h3>服務人員契約 PDF</h3><p>每位月嫂的契約分別下載。</p>
          {query?.unsigned_document && query.staff_targets.length > 0 ? query.staff_targets.map((target) => <button key={target.matching_segment_id} type="button" disabled={busy} onClick={() => void downloadUnsigned(target.document_version_id, `月嫂 ${target.staff_subject_reference} `)}>下載服務人員契約 PDF（{target.staff_subject_reference}）</button>) : <><button type="button" disabled>下載服務人員契約 PDF</button><p>{!query ? '尚未取得可下載文件的確認結果。' : '尚無可下載文件。'}若下方有「準備服務人員契約」，請先完成文件準備。</p></>}
        </article>
      </div>

      {((query && !query.unsigned_document && query.staff_targets.length > 0)
        || (!query && preparationSegments.length > 0)) && (
        <section aria-label="準備月嫂未簽契約 PDF" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px', display: 'grid', gap: '8px' }}>
          <strong>準備服務人員契約</strong>
          <div style={{ fontSize: '0.82rem', color: '#74593f' }}>
            核對案件與服務安排後產生未簽署的契約；此操作不會寄送訊息。
          </div>
          {(query
            ? query.staff_targets.map((target) => target.matching_segment_id)
            : preparationSegments).map((segmentId) => (
            <button
              key={segmentId}
              type="button"
              disabled={busy || !!unsignedPreparationFlow}
              onClick={() => void prepareUnsigned('staff', segmentId)}
            >
              準備服務人員契約 PDF（服務區段 {segmentId}）
            </button>
          ))}
        </section>
      )}

      {recoveryQuery && pendingRecoveryTargets.length > 0 && (
        <section aria-label="歷史簽回人工修復" style={{ border: '2px solid #f59e0b', borderRadius: '12px', padding: '14px', display: 'grid', gap: '12px' }}>
          <header>
            <strong>🧾 歷史簽回人工修復</strong>
            <div style={{ fontSize: '0.82rem', color: '#74593f', marginTop: '4px' }}>
              尚有 {pendingRecoveryTargets.length} 個未完成對象。每筆都必須先核對歷史簽回證據並檢查影響；月嫂完成後才可修復客戶。
            </div>
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
              <div key={target.matching_segment_id} style={{ display: 'grid', gap: '4px' }}>
                <button type="button" disabled={busy} onClick={() => void checkReminderReadiness(target.matching_segment_id)}>
                  檢查月嫂 {target.staff_subject_reference} LINE 通知準備度
                </button>
                {reminderReadiness[target.matching_segment_id] && (
                  <div role="status" style={{ fontSize: '0.82rem' }}>
                    <div>{reminderReadiness[target.matching_segment_id].message}</div>
                    <div>{reminderReadiness[target.matching_segment_id].ready
                      ? '通知內容與收件綁定均已就緒；尚未建立或送出通知。'
                      : `尚不可建立通知：${reminderReadiness[target.matching_segment_id].blockers.join('、')}`}</div>
                  </div>
                )}
                {reminderReadiness[target.matching_segment_id]?.ready && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void enqueueReminder(
                      target.matching_segment_id,
                      target.staff_subject_reference,
                      target.document_version_id,
                    )}
                  >
                    建立月嫂 {target.staff_subject_reference} LINE 契約通知工作（不立即傳送）
                  </button>
                )}
              </div>
            ))}
          </div>
          {!query.handoff_recorded && !handoffFlow && (
            <button type="button" disabled={busy} onClick={() => void recordHandoff()}>
              確認契約已送交外部簽署平台
            </button>
          )}
        </section>
      )}


      {query?.handoff_recorded
        && query.state !== 'completed'
        && query.state !== 'superseded'
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
                我已核對案件、檔名、PDF 類型、版本，且此 PDF 包含客戶與所有月嫂的完整簽署
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
      {handoffFlow?.status === 'outcome_unknown' && (
        <div role="alert">
          <div>{handoffFlow.error ?? '外部平台交接結果尚未確認。'}</div>
          <button type="button" onClick={() => void retryHandoffOriginal()}>以原交接操作重新確認</button>
        </div>
      )}
      {handoffFlow?.status === 'observation_failed' && handoffFlow.receipt !== null && (
        <div role="status">
          <div>{handoffFlow.error ?? '交接收據已收到，但目前狀態尚未讀取成功。'}</div>
          <button type="button" onClick={() => void retryHandoffReadback()}>重新讀取交接狀態</button>
        </div>
      )}
      {unsignedPreparationFlow?.status === 'outcome_unknown' && (
        <div role="alert">
          <div>{unsignedPreparationFlow.error ?? '未簽契約準備結果尚未確認。'}</div>
          <button type="button" onClick={() => void retryUnsignedPreparationOriginal()}>以原未簽契約準備操作重新確認</button>
        </div>
      )}
      {unsignedPreparationFlow?.status === 'observation_failed' && unsignedPreparationFlow.receipt !== null && (
        <div role="status">
          <div>{unsignedPreparationFlow.error ?? '未簽契約準備收據已收到，但目前狀態尚未讀取成功。'}</div>
          <button type="button" onClick={() => void retryUnsignedPreparationReadback()}>重新讀取未簽契約準備狀態</button>
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
