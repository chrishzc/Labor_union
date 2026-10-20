import { useUnsavedDraft } from './UnsavedChanges';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
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
  type ExternalSigningReceipt,
  type FinalDocumentPreview,
  type FinalDocumentReadback,
  type SignedDocumentTarget,
  type SignedDocumentPreview,
  type SignedDocumentUpload,
  type PreparedUnsignedDocument,
} from '../api/orders/contract_external_signing_client';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';
import { sessionClient } from '../api/auth/session_client';
import { previewContractFields } from '../api/orders/contract_full_preview_client';
import { OrderContractPreview } from './OrderContractPreview';
import { CandidateInquiryDialog } from './CandidateInquiryDialog';
import {
  orderMutationFlowStore,
  type ExternalSigningHandoffCommand,
  type ExternalSigningHandoffFlowState,
  type ExternalSigningUnsignedPreparationCommand,
  type ExternalSigningUnsignedPreparationFlowState,
} from '../adapters/orders/order_mutation_flow_store';

export interface ContractExternalSigningActionsProps {
  caseNo: string;
  revision?: number;
  onCommitted?: () => Promise<void> | void;
  onOpenFinance?: () => void;
  onOpenServiceDates?: () => void;
  onOpenRecommendation?: () => void;
}

type WorkingOperation = 'query' | 'prepare_client' | 'prepare_staff' | 'download' | 'handoff' | 'final_preview' | 'final_apply' | 'receipt' | 'readback';

interface ContractMetadata { name: string; period: string; staffId?: number }
interface SignedReturnDraft { file: File | null; staged: SignedDocumentPreview | null; checked: boolean }
const signedTargetKey = (target: Pick<SignedDocumentTarget, 'scope' | 'matching_segment_id'>) => target.scope === 'client' ? 'client' : `staff:${target.matching_segment_id}`;
const uploadInput = (row: SignedDocumentUpload): SignedDocumentUpload => ({ scope: row.scope, matching_segment_id: row.matching_segment_id, document_version_id: row.document_version_id, staging_id: row.staging_id, expected_staging_version: row.expected_staging_version });

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
  | { type: 'receipt_committed'; receipt: ExternalSigningReceipt; message: string }
  | { type: 'outcome_unknown'; identity: ExternalSigningCommandIdentity; expected: ReceiptExpectation; message: string }
  | { type: 'observed'; receipt: ExternalSigningReceipt; readback: FinalDocumentReadback }
  | { type: 'error'; message: string };

const unsafePublicText = /https?:\/\/|[A-Za-z]:\\|\\\\|\/(?:mnt|Volumes|private|var)\/|[0-9a-f]{64}|preview[_ -]?fingerprint|storage[_ -]?locator|raw[_ -]?cursor/i;

const CONTRACT_CHECK_REASONS: Record<string, string> = {
  client_finance_bootstrap_required: '本案尚未建立客戶付款條款，請至客戶名冊核對並補齊。',
  payroll_bootstrap_required: '本案尚未建立月嫂薪資資料，請至客戶名冊核對並補齊。',
  payroll_case_policy_bootstrap_required: '本案尚未建立月嫂薪資政策，請至客戶名冊核對並補齊。',
  contract_identity_already_recorded: '本案已有另一份契約的簽約紀錄，本次文件不能覆蓋原契約。',
  contract_completion_already_recorded: '本案已完成簽約，不能重複完成簽約。',
  contract_identity_missing: '本次契約尚未建立可核對的文件紀錄。',
  service_time_terms_incomplete: '本案每日服務時段尚未填寫完整，請先保存服務時段。',
  official_service_dates_incomplete: '本案服務日期與約定服務天數不一致，請先核對服務期間與休假日。',
  client_obligation_history_conflict: '本案已有與本次簽約不相容的客戶款項紀錄，請先核對帳務。',
  final_contract_testing_confirmation_required: '測試占位文件只能搭配「測試案件、跳過文件回收」確認；一般文件需確認真實簽署。',
  final_document_preview_stale: '檢查後的案件、帳務或文件資料已變更，請重新檢查完整文件。',
  final_document_preview_token_invalid: '本次完整文件的驗收結果無效，請重新檢查完整文件。',
  external_signing_status_version_stale: '簽約狀態已在文件檢查後變更，請重新讀取目前狀態。',
  final_signed_contract_already_applied: '本次簽回文件已完成驗收，請重新讀取完成結果。',
  final_signed_contract_documents_incomplete: '仍缺少客戶服務契約或月嫂委任契約，請分別上傳並檢查。',
  final_signed_contract_target_mismatch: '簽回文件的契約對象不一致，請重新選擇對應文件。',
  contract_testing_skip_unavailable: '目前主機不是允許跳過文件回收的本機測試環境。',
  contract_testing_completed_commitment_missing: '本案已完成簽約，但目前方案缺少原服務承諾，無法將測試文件接回原簽約紀錄。',
  signing_staff_occupancy_conflict: '目前推薦月嫂的檔期已衝突，請先更換月嫂或調整服務日期，再送交簽約。',
  signing_service_dates_unavailable: '目前服務日期與推薦區段不一致，請先調整日期或重新推薦月嫂，再送交簽約。',
};

function contractCheckReason(code: string): string {
  return CONTRACT_CHECK_REASONS[code] ?? code;
}

function safeErrorMessage(error: unknown): string {
  const fallback = '外部簽約操作失敗，請重新查詢目前狀態。';
  const message = error instanceof Error ? error.message : fallback;
  if (error instanceof ApiHttpError) {
    const reason = CONTRACT_CHECK_REASONS[error.code] ?? CONTRACT_CHECK_REASONS[message];
    if (reason) return reason;
  }
  if (unsafePublicText.test(message)) return fallback;
  if (error instanceof ApiTimeoutError || error instanceof ApiNetworkError) {
    return '連線暫時中斷，結果可能尚未確認，請使用原操作重新確認。';
  }
  if (error instanceof ApiHttpError) {
    if (error.status === 401 || error.status === 403) return '目前帳號無權處理這筆外部簽約。';
    if (error.code === 'external_signing_accepted_plan_required') return '目前尚無可投影契約的有效配對方案。';
    if (error.code === 'external_signing_session_facts_unavailable') return '外部簽約工作尚未建立；請先完成服務人員媒合與服務區段。';
    if (error.code === 'contract_pdf_external_reference_unresolved') return '契約模板缺少舊版引用內容，尚不能產生可簽署 PDF；請先補齊模板。';
    if (error.code === 'contract_pdf_required_mapping_missing') return '契約必要資料尚未齊全，請先在契約欄位預覽核對案件資料與收款設定。';
    if (error.code === 'contract_unsigned_pdf_missing') return message || '客戶或服務人員的未簽契約 PDF 尚未備妥，請先下載兩方契約後再確認送交。';
    if (error.code === 'contract_line_recipient_unbound' || error.code === 'contract_line_recipient_subject_mismatch') {
      return message || '客戶或服務人員的 LINE 身分尚未完成正確綁定，無法建立簽約提醒。';
    }
    if (error.code === 'final_signed_contract_documents_incomplete') return '仍缺少客戶服務契約或月嫂委任契約，請分別上傳並檢查。';
    if (error.code === 'final_signed_contract_target_mismatch') return '簽回文件的契約對象不一致，請重新選擇對應文件。';
    if (['external_staff_report_document_stale', 'external_client_report_document_stale'].includes(error.code)) return '本案契約版本已更新，請重新讀取並核對新版契約。';
    if (error.code === 'final_document_staging_version_stale') return '上傳文件已變更，請重新檢查這一份文件。';
    if (error.code === 'external_signing_handoff_already_recorded') return '此案件已記錄送交外部簽署平台，請重新讀取目前狀態。';
    if (error.code === 'external_signing_session_completed') return '此案件已完成簽約，無需再次送交外部簽署平台。';
    if (error.code === 'external_signing_session_superseded') return '此簽約工作已被新的配對方案取代，請重新讀取目前契約。';
    if (error.retryable || error.status >= 500) return '簽約服務暫時無法使用，請稍後重新查詢。';
    return `簽約檢查未通過：${message || error.code}`;
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
  if (!query.handoff_recorded) return '待送交';
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
    && (receipt.resulting_status_version === command.expectedStatusVersion
      || receipt.resulting_status_version === command.expectedStatusVersion + 1);
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
    && fresh.staff_targets.some((target) => target.matching_segment_id === command.segmentId);
}

export function ContractExternalSigningActions({ caseNo, revision = 0, onCommitted, onOpenFinance, onOpenServiceDates, onOpenRecommendation }: ContractExternalSigningActionsProps) {
  const staffIdentity = useStaffIdentityLabels();
  const observedRevision = useRef(revision);
  const identities = useRef(new Map<string, ExternalSigningCommandIdentity>());
  const requestGeneration = useRef(0);
  const unsignedDownloadController = useRef<AbortController | null>(null);
  const activeHandoffOperation = useRef<{ caseNo: string; operationToken: number } | null>(null);
  const activeUnsignedPreparationOperation = useRef<{ caseNo: string; operationToken: number } | null>(null);
  const activeReminderOperation = useRef<ExternalSigningHandoffCommand | null>(null);
  const [query, setQuery] = useState<ContractExternalSigningQuery | null>(null);
  const [preparationSegments, setPreparationSegments] = useState<number[]>([]);
  const [uiState, setUiState] = useState<ContractExternalSigningUiState>({ type: 'querying' });
  const [notice, setNotice] = useState<string | null>(null);
  const [fileReturns, setFileReturns] = useState<Record<string, SignedReturnDraft>>({});
  const [contractMetadata, setContractMetadata] = useState<Record<string, ContractMetadata>>({});
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [bootstrapReasons, setBootstrapReasons] = useState<string[]>([]);
  const [returnReadError, setReturnReadError] = useState<string | null>(null);
  const [completedReadback, setCompletedReadback] = useState<FinalDocumentReadback | null>(null);
  const [reviewTarget, setReviewTarget] = useState<{ scope: 'client' | 'staff'; segmentId: number | null } | null>(null);
  const [handoffConfirmationOpen, setHandoffConfirmationOpen] = useState(false);
  const [reminderConfirmationOpen, setReminderConfirmationOpen] = useState(false);
  const [preparationStaffDocuments, setPreparationStaffDocuments] = useState<Record<number, number>>({});
  const [preparationClientDocument, setPreparationClientDocument] = useState<number | null>(null);
  const handoffFlow = useSyncExternalStore(
    subscribeExternalSigningHandoff,
    () => orderMutationFlowStore.getExternalSigningHandoff(caseNo),
  );
  const unsignedPreparationFlow = useSyncExternalStore(
    subscribeExternalSigningHandoff,
    () => orderMutationFlowStore.getExternalSigningUnsignedPreparation(caseNo),
  );
  const reminderFlow = useSyncExternalStore(
    subscribeExternalSigningHandoff,
    () => orderMutationFlowStore.getExternalSigningReminder(caseNo),
  );

  useEffect(() => {
    if (reminderFlow?.status !== 'received' || !query) return;
    const receipt = reminderFlow.receipt;
    if (receipt?.session_id === query.session_id) {
      setQuery(current => current && current.session_id === receipt.session_id ? { ...current, signing_reminder: receipt } : current);
    }
    orderMutationFlowStore.clearExternalSigningReminder(caseNo);
  }, [reminderFlow, query?.session_id, caseNo]);

  const loadQuery = useCallback(async (signal?: AbortSignal): Promise<ContractExternalSigningQuery | null> => {
    const generation = ++requestGeneration.current;
    setUiState({ type: 'querying' });
    const value = await contractExternalSigningClient.query(caseNo, { signal });
    const segments = value.state === 'preparing' ? value.staff_segments.map(row => row.segment_id) : value.staff_targets.map(row => row.matching_segment_id);
    const metadataSignal = signal ?? new AbortController().signal;
    const metadataResults = await Promise.allSettled([
      previewContractFields(caseNo, 'client', null, metadataSignal),
      ...segments.map(segmentId => previewContractFields(caseNo, 'staff', segmentId, metadataSignal)),
    ]);
    if (signal?.aborted || generation !== requestGeneration.current) return null;
    const metadata: Record<string, ContractMetadata> = {};
    metadataResults.forEach((result, index) => {
      if (result.status !== 'fulfilled') return;
      const fields = result.value.field_values;
      const field = (key: string) => { const value = fields[key]; return typeof value === 'string' || typeof value === 'number' ? String(value) : Array.isArray(value) ? value.join('、') : ''; };
      const scope = index === 0 ? 'client' : 'staff';
      const start = field(scope === 'client' ? 'B24' : 'B7'), end = field(scope === 'client' ? 'D24' : 'D7'), days = field(scope === 'client' ? 'F24' : 'G7');
      metadata[index === 0 ? 'client' : `staff:${segments[index - 1]}`] = { name: field(scope === 'client' ? 'B8' : 'C4'), staffId: index === 0 ? undefined : value.state === 'preparing' ? value.staff_segments[index - 1]?.staff_id : Number(value.staff_targets[index - 1]?.staff_subject_reference), period: start && end ? `${start} ～ ${end}${days ? ` · ${days} 日` : ''}` : '服務期間待核對' };
    });
    setContractMetadata(metadata);
    setMetadataError(metadataResults.some(result => result.status === 'rejected') ? '部分契約資料暫時無法取得，可開啟「核對資料」查看原因。' : null);
    setBootstrapReasons([...new Set(metadataResults.flatMap(result => {
      if (result.status !== 'rejected' || !(result.reason instanceof ApiHttpError)) return [];
      const code = [result.reason.code, result.reason.message].find(value => ['client_finance_bootstrap_required', 'payroll_bootstrap_required', 'payroll_case_policy_bootstrap_required'].includes(value));
      return code ? [contractCheckReason(code)] : [];
    }))]);
    if (value.state !== 'preparing' && value.handoff_recorded && value.state !== 'completed' && value.state !== 'superseded') {
      try {
        const returns = await contractExternalSigningClient.getSignedDocumentReturns(caseNo, signal);
        if (returns.session_id !== value.session_id || returns.status_version !== value.status_version) throw new Error('簽回文件與本次簽約工作不一致，請重新讀取。');
        if (signal?.aborted || generation !== requestGeneration.current) return null;
        const targets: SignedDocumentTarget[] = [
          ...(value.client_target.document_version_id === null ? [] : [{ scope: 'client' as const, matching_segment_id: null, document_version_id: value.client_target.document_version_id }]),
          ...value.staff_targets.map(row => ({ scope: 'staff' as const, matching_segment_id: row.matching_segment_id, document_version_id: row.document_version_id })),
        ];
        for (const row of returns.documents) {
          if (!targets.some(target => signedTargetKey(target) === signedTargetKey(row) && target.document_version_id === row.document_version_id)) throw new Error('簽回文件的契約對象或版本不一致。');
        }
        setFileReturns(previous => Object.fromEntries(targets.map(target => {
          const key = signedTargetKey(target), staged = returns.documents.find(row => signedTargetKey(row) === key) ?? null, old = previous[key];
          return [key, old?.file ? old : { file: null, staged, checked: !!old?.checked && old.staged?.staging_id === staged?.staging_id && old.staged?.expected_staging_version === staged?.expected_staging_version }];
        })));
        setReturnReadError(null);
      } catch (error) { if (!signal?.aborted && generation === requestGeneration.current) setReturnReadError(safeErrorMessage(error)); }
    }

    if (value.state === 'preparing') {
      if (signal?.aborted || generation !== requestGeneration.current) return null;
      setQuery(null);
      setPreparationSegments(value.staff_segments.map((segment) => segment.segment_id));
      setPreparationStaffDocuments(Object.fromEntries(value.staff_segments.flatMap(segment => { const stored = value.documents.filter(row => row.scope === 'staff_segment' && row.role === 'template_generated' && row.mime_type === 'application/pdf' && row.target_key === `staff-segment:${segment.segment_id}`).sort((left, right) => right.document_version_id - left.document_version_id)[0]; return stored ? [[segment.segment_id, stored.document_version_id]] : []; })));
      setPreparationClientDocument(value.documents.filter(row => row.scope === 'client_contract' && row.role === 'template_generated' && row.mime_type === 'application/pdf').sort((left, right) => right.document_version_id - left.document_version_id)[0]?.document_version_id ?? null);
      setUiState({ type: 'ready' });
      return null;
    }
    if (generation !== requestGeneration.current) return value;
    setQuery(value);
    setPreparationSegments([]);
    setUiState({ type: 'ready' });
    return value;
  }, [caseNo]);

  useEffect(() => {
    observedRevision.current = revision;
    unsignedDownloadController.current?.abort();
    const controller = new AbortController();
    setQuery(null);
    setPreparationSegments([]);
    setNotice(null);
    setReminderConfirmationOpen(false);
    setFileReturns({});
    setContractMetadata({}); setMetadataError(null); setBootstrapReasons([]); setReturnReadError(null); setCompletedReadback(null); setReviewTarget(null); setHandoffConfirmationOpen(false); setPreparationClientDocument(null); setPreparationStaffDocuments({});
    identities.current.clear();
    void loadQuery(controller.signal).then(async (value) => {
      if (controller.signal.aborted || value === null || value.state !== 'completed') return;
      try {
        setUiState({ type: 'working', operation: 'readback' });
        const readback = await contractExternalSigningClient.getFinalDocumentReadback(caseNo, controller.signal);
        assertFinalReadbackMatchesCase(caseNo, readback);
        if (readback.session_id !== value.session_id) {
          throw new Error('最終 PDF 與目前簽約工作不一致。');
        }
        if (!controller.signal.aborted) {
          setCompletedReadback(readback);
          setNotice(`最終 PDF 第 ${readback.version_number} 版已確認完成，完整性驗證通過。`);
          setUiState({ type: 'ready' });
        }
      } catch (error) {
        if (!controller.signal.aborted) setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }).catch((error) => {
      if (controller.signal.aborted) return;
      if (!controller.signal.aborted) setUiState({ type: 'error', message: safeErrorMessage(error) });
    });
    return () => {
      const activeReminder = activeReminderOperation.current;
      const savedReminder = activeReminder && orderMutationFlowStore.getExternalSigningReminder(activeReminder.caseNo);
      if (activeReminder && savedReminder?.command.identity.idempotencyKey === activeReminder.identity.idempotencyKey && savedReminder.status === 'applying') {
        orderMutationFlowStore.setExternalSigningReminder(activeReminder.caseNo, { ...savedReminder, status: 'outcome_unknown', error: '簽署提醒在畫面離開時尚未確認；請重新確認原提醒結果。' });
      }
      activeReminderOperation.current = null;
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
    };
  }, [caseNo, loadQuery]);

  useEffect(() => {
    if (observedRevision.current === revision || handoffFlow || unsignedPreparationFlow || reminderFlow?.status === 'applying' || reminderFlow?.status === 'outcome_unknown' || Object.values(fileReturns).some(row => row.file)
      || !['ready', 'error'].includes(uiState.type)) return;
    observedRevision.current = revision;
    setQuery(null); setPreparationSegments([]); setNotice(null);
    identities.current.clear();
    const pending = loadQuery();
    const generation = requestGeneration.current;
    void pending.catch(error => {
      if (generation === requestGeneration.current) setUiState({ type: 'error', message: safeErrorMessage(error) });
    });
  }, [revision, loadQuery, handoffFlow, unsignedPreparationFlow, reminderFlow, fileReturns, uiState.type]);

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
    const fresh = await contractExternalSigningClient.query(command.caseNo);
    if (!ownsUnsignedPreparationOperation(command.caseNo, state.operationToken)) return;
    if (fresh.state === 'preparing') {
      const targetObserved = command.kind === 'staff'
        ? command.segmentId !== null
          && fresh.staff_segments.some((segment) => segment.segment_id === command.segmentId)
        : true;
      const documentObserved = fresh.documents.some((document) => (
        document.document_version_id === receipt.document_version_id
        && document.scope === (command.kind === 'client' ? 'client_contract' : 'staff_segment')
        && document.role === 'template_generated'
        && document.mime_type === 'application/pdf'
        && document.target_key === (command.kind === 'client' ? 'client-contract' : `staff-segment:${command.segmentId}`)
      ));
      if (fresh.case_no !== command.caseNo || command.sessionId !== null || !targetObserved || !documentObserved) {
        throw new Error('未簽契約收據尚未出現在正式契約狀態；只能重新讀取。');
      }
      orderMutationFlowStore.clearExternalSigningUnsignedPreparation(command.caseNo);
      if (request !== requestGeneration.current) return;
      setQuery(null);
      setPreparationSegments(fresh.staff_segments.map((segment) => segment.segment_id));
      if (command.kind === 'client') setPreparationClientDocument(receipt.document_version_id);
      else if (command.segmentId !== null) setPreparationStaffDocuments(previous => ({ ...previous, [command.segmentId!]: receipt.document_version_id }));
      setUiState({ type: 'ready' });
      setNotice(command.kind === 'client'
        ? `${receipt.replayed ? '已重新確認' : '已產生'}客戶未簽契約 PDF。`
        : `${receipt.replayed ? '已重新確認' : '已產生'}月嫂分段 #${command.segmentId} 未簽 PDF。`);
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
      if (downloadAfterObserved && request === requestGeneration.current) {
        await downloadUnsigned(
          receipt.document_version_id,
          command.kind === 'client' ? '客戶' : `月嫂分段 #${command.segmentId}`,
        );
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

  const prepareUnsigned = async (
    kind: 'client' | 'staff',
    segmentId: number | null,
    downloadAfterObserved = kind === 'client',
  ) => {
    if (unsignedPreparationFlow) return;
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor) {
      setUiState({ type: 'error', message: '請先登入後再準備未簽契約。' });
      return;
    }
    const command: ExternalSigningUnsignedPreparationCommand = {
      kind,
      caseNo,
      sessionId: query?.handoff_recorded ? query.session_id : null,
      segmentId,
      actor,
      identity: createExternalSigningCommandIdentity(kind === 'client' ? 'prepare-client' : `prepare-${segmentId}`),
    };
    setUiState({ type: 'working', operation: kind === 'client' ? 'prepare_client' : 'prepare_staff' });
    setNotice(null);
    await submitUnsignedPreparation(command, false, downloadAfterObserved);
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
      fresh.state === 'preparing'
      || fresh.case_no !== command.caseNo
      || fresh.session_id !== command.sessionId
      || !fresh.handoff_recorded
      || fresh.status_version < receipt.resulting_status_version
      || JSON.stringify(fresh.manual_notification_targets ?? []) !== JSON.stringify(receipt.manual_notification_targets ?? [])
    ) {
      throw new Error('交接收據後回讀與原案件、簽約工作或版本不一致；只能重新讀取。');
    }
    orderMutationFlowStore.clearExternalSigningHandoff(command.caseNo);
    if (request !== requestGeneration.current) return;
    setQuery(fresh);
    setUiState({ type: 'ready' });
    setNotice(receipt.handoff_included_reminders
      ? '已重新確認既有交接與通知紀錄；未建立新的提醒工作。'
      : '已記錄送交外部簽署平台，尚未發送簽署提醒。');
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
    if (!query || handoffFlow || (query.signing_blockers?.length ?? 0) > 0) return;
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

  const submitReminders = async (command: ExternalSigningHandoffCommand) => {
    const actor = sessionClient.getUser()?.username.trim();
    if (!actor || actor !== command.actor) {
      setNotice('請由原帳號重新確認簽署提醒結果。');
      return;
    }
    const generation = requestGeneration.current;
    activeReminderOperation.current = command;
    orderMutationFlowStore.setExternalSigningReminder(command.caseNo, { status: 'applying', command, receipt: null, error: null });
    try {
      const receipt = await contractExternalSigningClient.sendSigningReminders(command.caseNo, {
        session_id: command.sessionId, expected_status_version: command.expectedStatusVersion,
      }, command.identity);
      if (orderMutationFlowStore.getExternalSigningReminder(command.caseNo)?.command.identity.idempotencyKey !== command.identity.idempotencyKey) return;
      if (receipt.receipt_id !== command.identity.receiptId || receipt.session_id !== command.sessionId || receipt.status_version !== command.expectedStatusVersion) {
        throw new ApiHttpError(409, 'SIGNING_REMINDER_RECEIPT_MISMATCH', '簽署提醒結果與原操作不一致。');
      }
      orderMutationFlowStore.setExternalSigningReminder(command.caseNo, { status: 'received', command, receipt, error: null });
      if (generation === requestGeneration.current) setNotice(receipt.replayed ? '已確認原簽署提醒結果，未重複建立提醒。' : '簽署提醒處理已記錄；未綁定 LINE 的對象請人工通知。');
    } catch (error) {
      if (orderMutationFlowStore.getExternalSigningReminder(command.caseNo)?.command.identity.idempotencyKey !== command.identity.idempotencyKey) return;
      const unknown = outcomeCouldBeUnknown(error) || (error instanceof ApiHttpError && error.code === 'SIGNING_REMINDER_RECEIPT_MISMATCH');
      orderMutationFlowStore.setExternalSigningReminder(command.caseNo, { status: unknown ? 'outcome_unknown' : 'failed', command, receipt: null,
        error: unknown ? '簽署提醒結果尚未確認，請重新確認原提醒結果。' : safeErrorMessage(error) });
    } finally {
      if (activeReminderOperation.current?.identity.idempotencyKey === command.identity.idempotencyKey) activeReminderOperation.current = null;
    }
  };

  const sendReminders = async () => {
    if (!query?.handoff_recorded || busy || finalProtected || query.state === 'completed' || query.state === 'superseded' || reminderFlow?.status === 'outcome_unknown') return;
    const currentFlow = orderMutationFlowStore.getExternalSigningReminder(caseNo);
    if (currentFlow?.status === 'applying' || currentFlow?.status === 'outcome_unknown') return;
    const actor = sessionClient.getUser()?.username.trim();
    if (!actor) { setNotice('請先登入後再發送簽署提醒。'); return; }
    setReminderConfirmationOpen(false);
    await submitReminders({ caseNo, sessionId: query.session_id, expectedStatusVersion: query.status_version, actor, identity: createExternalSigningCommandIdentity('signing-reminders') });
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

  const requiredReturnTargets: SignedDocumentTarget[] = query ? [
    ...(query.client_target.document_version_id === null ? [] : [{ scope: 'client' as const, matching_segment_id: null, document_version_id: query.client_target.document_version_id }]),
    ...query.staff_targets.map(row => ({ scope: 'staff' as const, matching_segment_id: row.matching_segment_id, document_version_id: row.document_version_id })),
  ] : [];

  const previewFinalDocument = async (target: SignedDocumentTarget) => {
    if (!query || !query.handoff_recorded || returnReadError) return;
    const key = signedTargetKey(target), draft = fileReturns[key];
    if (!draft || (!draft.file && !draft.staged)) return;
    const sessionId = query.session_id, version = query.status_version, generation = requestGeneration.current;
    let checkingCompletion = false;
    setNotice(null); setUiState({ type: 'working', operation: 'final_preview' });
    try {
      const staged = draft.file ? await contractExternalSigningClient.stageFinalDocument(caseNo, draft.file, currentIdentity(identities.current, `final-stage-${key.replace(':', '-')}`), target, { session_id: sessionId, expected_status_version: version }) : draft.staged!;
      if (signedTargetKey(staged) !== key || staged.document_version_id !== target.document_version_id) throw new Error('上傳結果與所選契約對象或版本不一致。');
      const preview = await contractExternalSigningClient.previewSignedDocument(caseNo, { ...uploadInput(staged), session_id: sessionId, expected_status_version: version });
      if (generation !== requestGeneration.current) return;
      if (signedTargetKey(preview) !== key || preview.document_version_id !== target.document_version_id || preview.staging_id !== staged.staging_id) throw new Error('文件檢查結果與本次上傳不一致。');
      const next = { ...fileReturns, [key]: { file: null, staged: preview, checked: preview.can_apply } };
      setFileReturns(next); identities.current.delete(`final-stage-${key.replace(':', '-')}`); identities.current.delete('final-apply');
      if (requiredReturnTargets.every(row => next[signedTargetKey(row)]?.checked)) {
        checkingCompletion = true;
        const collection = await contractExternalSigningClient.previewFinalDocument(caseNo, { session_id: sessionId, expected_status_version: version, documents: requiredReturnTargets.map(row => uploadInput(next[signedTargetKey(row)]!.staged!)) });
        if (generation !== requestGeneration.current) return;
        if (collection.session_id !== sessionId || collection.expected_status_version !== version || collection.documents.length !== requiredReturnTargets.length || collection.documents.some(row => !requiredReturnTargets.some(target => signedTargetKey(target) === signedTargetKey(row) && target.document_version_id === row.document_version_id))) throw new Error('完整文件驗收預覽與本次契約對象不一致。');
        setUiState({ type: 'preview_ready', preview: collection, confirmed: false });
      } else setUiState({ type: 'ready' });
    } catch (error) { if (generation === requestGeneration.current) setUiState({ type: 'error', message: checkingCompletion
      ? `文件檢查已通過，但簽約完成檢查未通過：${safeErrorMessage(error)}`
      : safeErrorMessage(error) }); }
  };

  const observeFinalReceipt = async (receipt: ExternalSigningReceipt) => {
    setUiState({ type: 'receipt_committed', receipt, message: '最終文件已受理；正在確認簽約完成結果。' });
    try {
      const readback = await contractExternalSigningClient.getFinalDocumentReadback(caseNo);
      assertFinalReadbackMatchesCase(caseNo, readback);
      if (receipt.final_document_id !== readback.final_document_id || receipt.session_id !== readback.session_id) {
        throw new Error('最終 PDF 的受理結果與回讀文件不一致。');
      }
      if (readback.documents.length > 0 && query && readback.documents.length !== query.staff_targets.length + 1) throw new Error('完成結果仍缺少客戶或月嫂簽署文件；不得視為全部完成。');
      setCompletedReadback(readback);
      setFileReturns({});
      setUiState({ type: 'observed', receipt, readback });
      const refreshed = await loadQuery();
      if (
        refreshed === null
        || refreshed.session_id !== receipt.session_id
        || refreshed.state !== 'completed'
        || refreshed.status_version !== receipt.resulting_status_version
      ) {
        throw new Error('最終 PDF 回讀後的簽約狀態尚未完成；不得重送。');
      }
      setNotice(readback.filename.startsWith('TEST-ONLY-') ? '測試簽約已完成，已跳過真實簽署文件回收，可接續確認服務日期與排班。' : `契約完成，最終 PDF 第 ${readback.version_number} 版已確認，完整性驗證通過。`);
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
        session_id: preview.session_id,
        documents: preview.documents.map(uploadInput),
        ...(preview.documents.every(row => row.filename.startsWith('TEST-ONLY-'))
          ? { signatures_confirmed: false as const, testing_skip_confirmed: true as const }
          : { signatures_confirmed: true as const }),
        preview_token: preview.preview_token,
        expected_status_version: preview.expected_status_version,
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

  const prepareTestingSkip = async () => {
    if (!query?.testing_skip_allowed || !query.handoff_recorded || busy || finalProtected) return;
    const generation = requestGeneration.current;
    setNotice(null);
    setUiState({ type: 'working', operation: 'final_preview' });
    try {
      const preview = await contractExternalSigningClient.prepareTestingSkip(caseNo, {
        session_id: query.session_id, expected_status_version: query.status_version,
      }, currentIdentity(identities.current, 'testing-skip'));
      if (generation !== requestGeneration.current) return;
      if (preview.session_id !== query.session_id || preview.expected_status_version !== query.status_version
        || preview.documents.length !== requiredReturnTargets.length
        || new Set(preview.documents.map(signedTargetKey)).size !== requiredReturnTargets.length
        || preview.documents.some(row => !row.filename.startsWith('TEST-ONLY-') || !requiredReturnTargets.some(target => signedTargetKey(row) === signedTargetKey(target) && row.document_version_id === target.document_version_id))) {
        throw new Error('測試文件與本次契約對象或版本不一致。');
      }
      setFileReturns(Object.fromEntries(preview.documents.map(row => [signedTargetKey(row), { file: null, staged: row, checked: row.can_apply }])));
      setReturnReadError(null);
      identities.current.delete('testing-skip');
      identities.current.delete('final-apply');
      setUiState({ type: 'preview_ready', preview, confirmed: false });
    } catch (error) {
      if (generation === requestGeneration.current) setUiState({ type: 'error', message: safeErrorMessage(error) });
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

  const downloadSigned = async (fileId: string) => {
    const generation = requestGeneration.current;
    setUiState({ type: 'working', operation: 'download' });
    try {
      const artifact = await contractExternalSigningClient.downloadSignedPdf(caseNo, fileId);
      if (generation !== requestGeneration.current) return;
      const url = URL.createObjectURL(artifact.blob);
      try { const link = document.createElement('a'); link.href = url; link.download = artifact.filename; link.click(); }
      finally { URL.revokeObjectURL(url); }
      setUiState({ type: 'ready' });
    } catch (error) { if (generation === requestGeneration.current) setUiState({ type: 'error', message: safeErrorMessage(error) }); }
  };

  const busy = uiState.type === 'working' || uiState.type === 'querying' || reminderFlow?.status === 'applying';
  const finalProtected = uiState.type === 'outcome_unknown' || uiState.type === 'receipt_committed';
  const signingBlocked = (query?.signing_blockers?.length ?? 0) > 0;
  const unsignedDocumentId = (scope: 'client' | 'staff', segmentId: number | null) => query ? query.unsigned_documents?.find(row => row.scope === scope && row.matching_segment_id === segmentId)?.document_version_id ?? (query.unsigned_document && query.unsigned_document.document_version_id === (scope === 'client' ? query.client_target.document_version_id : query.staff_targets.find(row => row.matching_segment_id === segmentId)?.document_version_id) ? query.unsigned_document.document_version_id : null) : scope === 'client' ? preparationClientDocument : preparationStaffDocuments[segmentId!] ?? null;
  const documentsReady = query !== null && unsignedDocumentId('client', null) !== null && query.staff_targets.every(row => unsignedDocumentId('staff', row.matching_segment_id) !== null);
  const metadataLabel = (key: string) => { const meta = contractMetadata[key]; return key === 'client' ? meta?.name : staffIdentity.label(meta?.staffId ?? (Number(query?.staff_targets.find(target => `staff:${target.matching_segment_id}` === key)?.staff_subject_reference) || null), meta?.name); };
  const documentRows = [
    { key: 'client', scope: 'client' as const, segmentId: null, title: '客戶服務契約', documentId: unsignedDocumentId('client', null) },
    ...(query ? query.staff_targets.map(row => ({ key: `staff:${row.matching_segment_id}`, scope: 'staff' as const, segmentId: row.matching_segment_id, title: '月嫂委任契約', documentId: unsignedDocumentId('staff', row.matching_segment_id) }))
      : preparationSegments.map(segmentId => ({ key: `staff:${segmentId}`, scope: 'staff' as const, segmentId, title: '月嫂委任契約', documentId: unsignedDocumentId('staff', segmentId) }))),
  ];
  const phase = query?.state === 'completed' ? 3 : query?.handoff_recorded ? 2 : documentsReady ? 1 : 0;
  const completedMembers = completedReadback?.documents ?? [];
  const checkedCount = requiredReturnTargets.filter(row => fileReturns[signedTargetKey(row)]?.checked).length;
  const testingPreview = uiState.type === 'preview_ready' && uiState.preview.documents.every(row => row.filename.startsWith('TEST-ONLY-'));
  const testingCompleted = completedReadback?.filename.startsWith('TEST-ONLY-') ?? false;
  const reminderReceipt = query?.signing_reminder;
  const reminderManualTargets = reminderReceipt?.manual_notification_targets ?? (query?.handoff_included_reminders ? query.manual_notification_targets ?? [] : []);
  const reminderTargets = query ? [
    { scope: 'client' as const, subject: query.client_target.client_subject_reference, name: contractMetadata.client?.name || '客戶' },
    ...query.staff_targets.map(target => ({ scope: 'staff' as const, subject: target.staff_subject_reference, name: metadataLabel(`staff:${target.matching_segment_id}`) || '月嫂' })),
  ] : [];
  const allReminderTargetsManual = reminderTargets.length > 0 && reminderTargets.every(target => reminderManualTargets.some(manual => manual.scope === target.scope && manual.subject_reference === target.subject));
  const renderReturn = (target: SignedDocumentTarget) => {
    const key = signedTargetKey(target), draft = fileReturns[key], meta = contractMetadata[key];
    const name = metadataLabel(key);
    const title = target.scope === 'client' ? '客戶服務契約' : '月嫂委任契約';
    return <article className="contract-return-row" key={key} aria-label={`${title}簽回${name ? ` ${name}` : ''}`}>
      <header><div><strong>{name || title}</strong><p>{meta?.period || '服務期間待核對'}</p></div><span className={`contract-document-status ${draft?.checked ? 'complete' : ''}`}>{draft?.checked ? '檢查通過' : draft?.file || draft?.staged ? '待檢查' : '待回收'}</span></header>
      <label className="contract-return-file">{target.scope === 'client' ? '客戶服務契約 PDF' : `${name || '月嫂'} 委任契約 PDF`}
        {!draft?.file && !draft?.staged && <input type="file" accept="application/pdf,.pdf" disabled={busy || finalProtected || !!returnReadError} onChange={event => {
          const file = event.target.files?.item(0) ?? null;
          setFileReturns(previous => ({ ...previous, [key]: { file, staged: null, checked: false } }));
          identities.current.delete(`final-stage-${key.replace(':', '-')}`); identities.current.delete('final-apply'); setUiState({ type: 'ready' });
        }} />}
      </label>
      {(draft?.file || draft?.staged) && <div className="contract-return-actions"><strong>{draft.file?.name || draft.staged?.filename}</strong><button type="button" disabled={busy || finalProtected} onClick={() => { setFileReturns(previous => ({ ...previous, [key]: { file: null, staged: null, checked: false } })); identities.current.delete(`final-stage-${key.replace(':', '-')}`); identities.current.delete('final-apply'); setUiState({ type: 'ready' }); }}>重新選擇檔案</button></div>}
      {draft?.checked ? <><p className="contract-return-checked">PDF 類型與完整性已確認；簽署內容仍需由人員核對。</p><button type="button" disabled={busy || finalProtected || !!returnReadError} onClick={() => void previewFinalDocument(target)}>重新檢查</button></> : <button type="button" disabled={busy || finalProtected || !!returnReadError || (!draft?.file && !draft?.staged)} onClick={() => void previewFinalDocument(target)}>檢查簽署文件</button>}
      {draft?.staged && draft.staged.blockers.length > 0 && <ul role="alert">{draft.staged.blockers.map(blocker => <li key={blocker}>{contractCheckReason(blocker)}</li>)}</ul>}
    </article>;
  };
  useUnsavedDraft('紙本契約回傳', { '待確認文件': Object.values(fileReturns).map(draft => draft.file?.name ?? draft.staged?.filename ?? '').filter(Boolean) }, { baseline: { '待確認文件': [] }, busy: busy || finalProtected, enabled: !completedReadback });



  return (
    <section aria-label="外部平台簽約與最終 PDF" data-control-id="orders.contract-external-signing.actions" className="contract-signing-workflow">
      <section className="contract-documents-card" aria-label="契約文件">
        <ol className="contract-signing-progress" aria-label="簽約進度">{['下載契約', '送交簽署', '回收簽署文件'].map((label, index) => <li key={label} className={index < phase ? 'complete' : index === phase ? 'current' : ''} aria-current={index === phase ? 'step' : undefined}><span>{index < phase ? '✓' : index + 1}</span>{label}</li>)}</ol>
        <header className="contract-documents-heading"><h3>契約文件</h3>{query && documentsReady && <span className="contract-document-status complete" aria-label={stateLabel(query)}>{documentRows.length} 份已備妥</span>}</header>
        {metadataError && <p role="alert">{metadataError}</p>}
        {!query && uiState.type === 'ready' && preparationSegments.length === 0 && <p role="status">目前尚未選定可下載契約的月嫂，請先建立推薦方案。</p>}
        <div className="contract-documents-list">{documentRows.map(row => <article className="contract-document-row" key={row.key}>
          <div><strong>{row.title}{metadataLabel(row.key) ? ` · ${metadataLabel(row.key)}` : ''}</strong><p>{contractMetadata[row.key]?.period || '服務期間待核對'}</p></div>
          {row.documentId !== null && <span className="contract-document-status complete">已備妥</span>}
          <div className="contract-document-actions"><button type="button" disabled={busy || finalProtected} onClick={() => setReviewTarget({ scope: row.scope, segmentId: row.segmentId })}>核對資料</button>
            {row.scope === 'client' && row.documentId !== null && <button type="button" disabled={busy || finalProtected || !!unsignedPreparationFlow || !!fileReturns.client?.file || !!fileReturns.client?.staged} onClick={() => void prepareUnsigned('client', null, true)}>重新產生客戶契約</button>}
            <button type="button" aria-label={`下載 PDF · ${row.title}${metadataLabel(row.key) ? ` · ${metadataLabel(row.key)}` : ''}`} disabled={busy || finalProtected || !!unsignedPreparationFlow || (!query && preparationSegments.length === 0)} onClick={() => {
              if (row.documentId !== null) void downloadUnsigned(row.documentId, row.scope === 'client' ? '客戶' : '月嫂');
              else void prepareUnsigned(row.scope, row.segmentId, true);
            }}>下載 PDF</button></div>
        </article>)}</div>
      </section>
      <section className="contract-signing-actions-card" aria-label="送交簽署與提醒">
        <header className="contract-documents-heading"><h3>送交簽署與提醒</h3></header>
        {signingBlocked && <div role="alert" className="contract-manual-notice">
          {query?.signing_blockers?.map(code => <p key={code}>{contractCheckReason(code)}</p>)}
          <div className="order-case-action-row">
            {onOpenRecommendation && <button type="button" disabled={busy || finalProtected} onClick={onOpenRecommendation}>更換推薦月嫂</button>}
            {onOpenServiceDates && <button type="button" disabled={busy || finalProtected} onClick={onOpenServiceDates}>調整服務日期</button>}
          </div>
        </div>}
        <div className="contract-platform-action-row"><div><strong>外部平台交接</strong><p>確認契約已送交外部簽署平台，只保存交接紀錄。</p></div><div className="contract-signing-action-controls"><span className={`contract-document-status ${query?.handoff_recorded ? 'complete' : ''}`}>{query?.handoff_recorded ? '交接已記錄' : '待記錄'}</span>{!handoffFlow && <button className="formal-recommendation-primary" type="button" disabled={busy || finalProtected || !query || signingBlocked} onClick={() => setHandoffConfirmationOpen(true)}>記錄已送交簽署平台</button>}</div></div>
        <div className="contract-platform-action-row"><div><strong>簽署提醒</strong><p>需要時另行發送 LINE 提醒，不影響簽署文件回收。</p><small>通知對象：本案客戶及所有月嫂</small></div><div className="contract-signing-action-controls"><span className={`contract-document-status ${reminderReceipt && !allReminderTargetsManual ? 'complete' : ''}`}>{reminderFlow?.status === 'outcome_unknown' ? '結果待確認' : reminderReceipt ? allReminderTargetsManual ? '需人工通知' : '提醒工作已建立' : query?.handoff_included_reminders ? '已有交接通知紀錄' : '尚未發送'}</span><button type="button" disabled={busy || finalProtected || signingBlocked || !query?.handoff_recorded || query.state === 'completed' || query.state === 'superseded' || reminderFlow?.status === 'outcome_unknown'} onClick={() => setReminderConfirmationOpen(true)}>發送簽署提醒</button></div></div>
        <p className="contract-signing-action-hint">{query?.handoff_recorded ? '交接已記錄。簽署提醒需另按「發送簽署提醒」，不會自動發送。' : '先記錄外部平台交接，再發送簽署提醒。'}</p>
        {reminderManualTargets.length > 0 && <div className="contract-manual-notice" aria-label="需人工通知的簽約對象"><strong>需人工通知簽約</strong><p>{reminderManualTargets.map(target => reminderTargets.find(row => row.scope === target.scope && row.subject === target.subject_reference)?.name || (target.scope === 'client' ? '客戶' : '月嫂')).join('、')}在這次通知紀錄中尚未綁定 LINE，請人工通知前往外部平台簽署。</p></div>}
        {reminderFlow?.status === 'outcome_unknown' && <div role="alert"><p>{reminderFlow.error}</p><button type="button" disabled={busy} onClick={() => void submitReminders(reminderFlow.command)}>重新確認原提醒結果</button></div>}
        {reminderFlow?.status === 'failed' && <div role="alert"><p>{reminderFlow.error}</p><button type="button" disabled={busy || finalProtected} onClick={() => void loadQuery()}>重新讀取契約狀態</button></div>}
      </section>
      {handoffConfirmationOpen && <CandidateInquiryDialog title="確認已送交簽署平台" busy={busy} onClose={() => setHandoffConfirmationOpen(false)}><div className="contract-signing-confirm-body"><p>請確認已將客戶及所有月嫂的契約送交外部簽署平台。</p><small>此操作只記錄交接，不會發送 LINE 簽署提醒。</small></div><footer className="contract-signing-confirm-footer"><button type="button" disabled={busy} onClick={() => setHandoffConfirmationOpen(false)}>返回</button><button className="btn-primary-action" type="button" disabled={busy} onClick={() => { setHandoffConfirmationOpen(false); void recordHandoff(); }}>確認已送交</button></footer></CandidateInquiryDialog>}
      {reminderConfirmationOpen && <CandidateInquiryDialog title="確認發送簽署提醒" busy={busy} onClose={() => setReminderConfirmationOpen(false)}><div className="contract-signing-confirm-body"><p>將一次通知本案客戶與所有月嫂：</p><ul>{reminderTargets.map((target, index) => <li key={`${target.scope}:${index}`}>{target.name} · {target.scope === 'client' ? '客戶' : '月嫂'}</li>)}</ul><small>未綁定 LINE 的對象會列出人工通知提示。</small></div><footer className="contract-signing-confirm-footer"><button type="button" disabled={busy} onClick={() => setReminderConfirmationOpen(false)}>取消</button><button className="btn-primary-action" type="button" disabled={busy || !query?.handoff_recorded || query.state === 'completed' || query.state === 'superseded' || reminderFlow?.status === 'outcome_unknown'} onClick={() => void sendReminders()}>確認發送提醒</button></footer></CandidateInquiryDialog>}
      {reviewTarget && <CandidateInquiryDialog title={`核對資料 · ${reviewTarget.scope === 'client' ? '客戶服務契約' : '月嫂委任契約'}`} side onClose={() => setReviewTarget(null)}><div className="contract-review-body"><OrderContractPreview key={`${caseNo}:${reviewTarget.scope}:${reviewTarget.segmentId}`} caseNo={caseNo} revision={revision} initialScope={reviewTarget.scope} targetSegmentId={reviewTarget.segmentId} targetStaffId={contractMetadata[`staff:${reviewTarget.segmentId}`]?.staffId} staffLabels={documentRows.filter(row => row.scope === 'staff').map(row => metadataLabel(row.key) || '月嫂資料待確認')} showScopeControls={false} /></div><footer className="contract-review-footer"><small>完整條文請核對下載的 PDF。</small><button className="formal-recommendation-primary" type="button" disabled={busy} onClick={() => { const row = documentRows.find(row => row.scope === reviewTarget.scope && row.segmentId === reviewTarget.segmentId); if (row?.documentId != null) void downloadUnsigned(row.documentId, row.scope === 'client' ? '客戶' : '月嫂'); else void prepareUnsigned(reviewTarget.scope, reviewTarget.segmentId, true); }}>下載 PDF</button></footer></CandidateInquiryDialog>}

      {query?.handoff_recorded && query.state !== 'completed' && query.state !== 'superseded' && <section className="contract-return-card" aria-label="回收簽署文件">
        <header className="contract-documents-heading"><h3>回收簽署文件</h3><span className="contract-document-status">{checkedCount}／{requiredReturnTargets.length} 份已檢查</span></header>
        <p>客戶服務契約與月嫂委任契約分開上傳。每位月嫂的委任契約各自回收。</p>
        <p>檢查時先暫存至受控檔案庫；確認完成後正式保存，可在本案查看文件。</p>
        {returnReadError && <div role="alert"><p>簽回文件暫時無法讀取：{returnReadError}</p><button type="button" disabled={busy || finalProtected} onClick={() => void loadQuery()}>重新讀取簽回文件</button></div>}
        <section className="contract-return-group"><h4>客戶服務契約</h4>{requiredReturnTargets.filter(row => row.scope === 'client').map(renderReturn)}</section>
        <section className="contract-return-group"><h4>月嫂委任契約</h4>{requiredReturnTargets.filter(row => row.scope === 'staff').map(renderReturn)}</section>
        {query.testing_skip_allowed && <details className="contract-signing-test-tools"><summary>測試模式 · 跳過文件回收</summary><div><p>使用 TEST ONLY 占位文件跳過回收。確認後可繼續測試簽約完成與後續收款。</p><button type="button" disabled={busy || finalProtected || testingPreview} onClick={() => void prepareTestingSkip()}>測試用：跳過文件回收</button></div></details>}
        <div className="contract-final-confirmation"><p>{testingPreview ? '測試占位文件已備妥，請確認後繼續測試。' : uiState.type === 'preview_ready' && uiState.preview.can_apply ? '各份文件均已回收並通過檢查，請核對簽署內容。' : '客戶服務契約及所有月嫂委任契約均回收並通過檢查後，才能確認完成。'}</p>
          {uiState.type === 'preview_ready' && uiState.preview.blockers.length > 0 && <ul role="alert">{uiState.preview.blockers.map(blocker => <li key={blocker}>{contractCheckReason(blocker)}</li>)}</ul>}
          <label><input type="checkbox" checked={uiState.type === 'preview_ready' && uiState.confirmed} disabled={busy || finalProtected || uiState.type !== 'preview_ready' || !uiState.preview.can_apply} onChange={event => { if (uiState.type === 'preview_ready') setUiState({ ...uiState, confirmed: event.target.checked }); }} />{testingPreview ? '我確認本案為測試案件，跳過真實簽署文件回收，並繼續測試後續收款。' : '我已核對本案與文件版本，確認客戶服務契約及所有月嫂委任契約的簽署均完整。'}</label>
          <button className="formal-recommendation-primary" type="button" disabled={busy || finalProtected || uiState.type !== 'preview_ready' || !uiState.confirmed || !uiState.preview.can_apply} onClick={() => void applyFinalDocument()}>{testingPreview ? '確認跳過並完成測試簽約' : '確認完成簽署'}</button>
        </div>
      </section>}
      {query?.state === 'completed' && <section className="contract-return-card" aria-label="契約完成"><div className="contract-completed-notice"><strong>{testingCompleted ? '測試簽約已完成' : '所有月嫂簽約完成、客戶簽約完成'}</strong><p>{testingCompleted ? '已手動跳過真實簽署文件回收，保存 TEST ONLY 占位文件，可接續確認服務日期與排班。' : completedMembers.length > 0 ? '客戶服務契約與所有月嫂委任契約已分別回收，並確認簽署完整。' : '既有簽署文件已驗收完成。'}</p></div>{completedReadback ? <div className="contract-signed-list">{(completedMembers.length > 0 ? completedMembers.map(member => ({ fileId: member.controlled_file_id, filename: member.filename })) : [{ fileId: completedReadback.controlled_file_id, filename: completedReadback.filename }]).map(row => <div key={row.fileId}><span>{row.filename}</span><button type="button" disabled={busy} onClick={() => void downloadSigned(row.fileId)}>{testingCompleted ? '查看測試文件' : '查看已簽文件'}</button></div>)}</div> : <p>正在讀取已簽文件…</p>}{(onOpenServiceDates || onOpenFinance) && <button className="formal-recommendation-primary" type="button" disabled={busy} onClick={onOpenServiceDates ?? onOpenFinance}>前往確認服務日期與排班 →</button>}<p>接續核對服務日期、雙方確認與訂金鎖狀態；條件齊備後自動排班。</p></section>}

      {bootstrapReasons.length > 0 && <p role="alert">{bootstrapReasons.join(' ')} <a href={`#clients?case=${encodeURIComponent(caseNo)}&from=workbench`} aria-disabled={busy || finalProtected || undefined} onClick={event => { if (busy || finalProtected) event.preventDefault(); }}>前往客戶名冊補齊資料 →</a></p>}
      {uiState.type === 'error' && <div role="alert"><p>{uiState.message}</p><button type="button" disabled={busy || finalProtected} onClick={() => void loadQuery()}>重新讀取契約狀態</button></div>}
      {busy && <p role="status">正在處理契約資料…</p>}

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
