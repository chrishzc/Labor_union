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
  type ContractPreparationQuery,
  type ExternalSigningCommandIdentity,
  type ExternalSigningReceipt,
  type FinalDocumentPreview,
  type FinalDocumentReadback,
  type SignedDocumentTarget,
  type SignedDocumentUpload,
  type SignedArchiveFile,
} from '../api/orders/contract_external_signing_client';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';
import { sessionClient } from '../api/auth/session_client';
import { openContractPrintView, previewContractFields } from '../api/orders/contract_full_preview_client';
import { OrderContractPreview } from './OrderContractPreview';
import { CandidateInquiryDialog } from './CandidateInquiryDialog';
import {
  orderMutationFlowStore,
  type ExternalSigningHandoffCommand,
  type ExternalSigningHandoffFlowState,
} from '../adapters/orders/order_mutation_flow_store';

export interface ContractExternalSigningActionsProps {
  caseNo: string;
  revision?: number;
  onCommitted?: () => Promise<void> | void;
  onOpenFinance?: () => void;
  onOpenServiceDates?: () => void;
  onOpenRecommendation?: () => void;
}

type WorkingOperation = 'query' | 'download' | 'handoff' | 'final_preview' | 'final_apply' | 'receipt' | 'readback';

interface ContractMetadata { name: string; period: string; staffId?: number }
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
  | { type: 'receipt_committed'; receipt: ExternalSigningReceipt; message: string }
  | { type: 'outcome_unknown'; identity: ExternalSigningCommandIdentity; expected: ReceiptExpectation; message: string }
  | { type: 'observed'; receipt: ExternalSigningReceipt; readback: FinalDocumentReadback }
  | { type: 'error'; message: string };

const unsafePublicText = /https?:\/\/|[A-Za-z]:\\|\\\\|\/(?:mnt|Volumes|private|var)\/|[0-9a-f]{64}|preview[_ -]?fingerprint|storage[_ -]?locator|raw[_ -]?cursor/i;

const CONTRACT_CHECK_REASONS: Record<string, string> = {
  signing_accepted_plan_required: '請先完成客戶接受目前推薦方案，再記錄送交簽署。',
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
  final_document_preview_stale: '案件、帳務或文件資料已變更，請重新儲存簽署文件。',
  final_document_preview_token_invalid: '本次完整文件的驗收結果無效，請重新儲存簽署文件。',
  external_signing_status_version_stale: '簽約狀態已在文件檢查後變更，請重新讀取目前狀態。',
  final_signed_contract_already_applied: '本次簽回文件已完成驗收，請重新讀取完成結果。',
  final_signed_contract_documents_incomplete: '仍缺少客戶服務契約或月嫂委任契約，請分別上傳並檢查。',
  final_signed_contract_target_mismatch: '簽回文件的契約對象不一致，請重新選擇對應文件。',
  contract_testing_skip_unavailable: '目前主機不是允許跳過文件回收的本機測試環境。',
  contract_testing_completed_commitment_missing: '本案已完成簽約，但目前方案缺少原服務承諾，無法將測試文件接回原簽約紀錄。',
  signing_staff_occupancy_conflict: '目前推薦月嫂的檔期已衝突，正式完成簽約前請更換月嫂或調整服務日期。',
  signing_service_dates_unavailable: '目前服務日期與推薦區段不一致，正式完成簽約前請調整日期或重新推薦月嫂。',
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
    if (error.code === 'contract_unsigned_pdf_missing') return message || '客戶或服務人員的契約 PDF 尚未備妥，請重新查詢簽約狀態。';
    if (error.code === 'final_signed_contract_documents_incomplete') return '仍缺少客戶服務契約或月嫂委任契約，請分別上傳並檢查。';
    if (error.code === 'final_signed_contract_target_mismatch') return '簽回文件的契約對象不一致，請重新選擇對應文件。';
    if (['external_staff_report_document_stale', 'external_client_report_document_stale'].includes(error.code)) return '本案契約版本已更新，請重新讀取並核對新版契約。';
    if (error.code === 'final_document_staging_version_stale') return '上傳文件已變更，請重新選擇這份文件後儲存。';
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

function nextHandoffOperationToken(): number {
  handoffOperationSequence += 1;
  return handoffOperationSequence;
}



function handoffReceiptMatches(
  command: ExternalSigningHandoffCommand,
  receipt: { session_id: string | null; resulting_status_version: number },
): boolean {
  return (command.sessionId === null || receipt.session_id === command.sessionId)
    && (receipt.resulting_status_version === command.expectedStatusVersion
      || receipt.resulting_status_version === command.expectedStatusVersion + 1);
}

export function ContractExternalSigningActions({ caseNo, revision = 0, onCommitted, onOpenFinance, onOpenServiceDates, onOpenRecommendation }: ContractExternalSigningActionsProps) {
  const staffIdentity = useStaffIdentityLabels();
  const observedRevision = useRef(revision);
  const identities = useRef(new Map<string, ExternalSigningCommandIdentity>());
  const requestGeneration = useRef(0);
  const printController = useRef<AbortController | null>(null);
  const activeHandoffOperation = useRef<{ caseNo: string; operationToken: number } | null>(null);
  const [query, setQuery] = useState<ContractExternalSigningQuery | null>(null);
  const [preparation, setPreparation] = useState<ContractPreparationQuery | null>(null);
  const [preparationSegments, setPreparationSegments] = useState<number[]>([]);
  const [uiState, setUiState] = useState<ContractExternalSigningUiState>({ type: 'querying' });
  const [archiveSegments, setArchiveSegments] = useState<{ segment_id: number; staff_id: number }[] | null>(null);
  const [archivedFiles, setArchivedFiles] = useState<SignedArchiveFile[] | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [archiveUnknown, setArchiveUnknown] = useState(false);
  const archiveRequest = useRef<AbortController | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [fileReturns, setFileReturns] = useState<Record<string, File | null>>({});
  const [contractMetadata, setContractMetadata] = useState<Record<string, ContractMetadata>>({});
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [bootstrapReasons, setBootstrapReasons] = useState<string[]>([]);
  const [testingFiles, setTestingFiles] = useState<string[]>([]);
  const [completedReadback, setCompletedReadback] = useState<FinalDocumentReadback | null>(null);
  const [reviewTarget, setReviewTarget] = useState<{ scope: 'client' | 'staff'; segmentId: number | null } | null>(null);
  const handoffFlow = useSyncExternalStore(
    subscribeExternalSigningHandoff,
    () => orderMutationFlowStore.getExternalSigningHandoff(caseNo),
  );
  useEffect(() => {
    const controller = new AbortController();
    archiveRequest.current = controller;
    setArchiveSegments(null);
    setArchivedFiles(null);
    setArchiveError(null);
    setArchiveBusy(false);
    setArchiveUnknown(false);
    return () => controller.abort();
  }, [caseNo]);

  useEffect(() => {
    if (archiveBusy || archiveUnknown) return;
    const controller = new AbortController();
    void contractExternalSigningClient.querySignedArchive(caseNo, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setArchiveSegments(value.staff_segments);
      setArchivedFiles(previous => value.files ?? previous);
    }).catch(error => {
      if (!controller.signal.aborted) setArchiveError(safeErrorMessage(error));
    });
    return () => controller.abort();
  }, [caseNo, revision, archiveBusy, archiveUnknown]);

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
    if (value.state === 'preparing') {
      setPreparation(value);
      if (signal?.aborted || generation !== requestGeneration.current) return null;
      setQuery(null);
      setPreparationSegments(value.staff_segments.map((segment) => segment.segment_id));
      setUiState({ type: 'ready' });
      return null;
    }
    if (generation !== requestGeneration.current) return value;
    setQuery(value);
    setPreparation(null);
    setPreparationSegments([]);
    setUiState({ type: 'ready' });
    return value;
  }, [caseNo]);

  useEffect(() => {
    observedRevision.current = revision;
    printController.current?.abort();
    const controller = new AbortController();
    setQuery(null);
    setPreparation(null);
    setPreparationSegments([]);

    setNotice(null);
    setFileReturns({});
    setTestingFiles([]);
    setCompletedReadback(null);
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
      requestGeneration.current += 1;
      controller.abort();
      printController.current?.abort();
    };
  }, [caseNo, loadQuery]);

  useEffect(() => {
    if (observedRevision.current === revision || archiveBusy || handoffFlow || Object.values(fileReturns).some(Boolean)
      || !['ready', 'error'].includes(uiState.type)) return;
    observedRevision.current = revision;
    setQuery(null); setPreparationSegments([]); setNotice(null);
    identities.current.clear();
    const pending = loadQuery();
    const generation = requestGeneration.current;
    void pending.catch(error => {
      if (generation === requestGeneration.current) setUiState({ type: 'error', message: safeErrorMessage(error) });
    });
  }, [revision, loadQuery, archiveBusy, handoffFlow, fileReturns, uiState.type]);

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
    if (receipt.session_id === null) {
      if (fresh.case_no !== command.caseNo || !fresh.handoff_logged) throw new Error('交接紀錄尚未回讀確認。');
      orderMutationFlowStore.clearExternalSigningHandoff(command.caseNo);
      if (request !== requestGeneration.current) return;
      if (fresh.state === 'preparing') {
        setPreparation(fresh);
        setPreparationSegments(fresh.staff_segments.map(segment => segment.segment_id));
      } else {
        setQuery(fresh);
        setPreparation(null);
        setPreparationSegments([]);
      }
      setUiState({ type: 'ready' });
      setNotice('已記錄送交外部簽署平台。');
      return;
    }
    if (
      fresh.state === 'preparing'
      || fresh.case_no !== command.caseNo
      || fresh.session_id !== receipt.session_id
      || !fresh.handoff_recorded
      || fresh.status_version < receipt.resulting_status_version
    ) {
      throw new Error('交接收據後回讀與原案件、簽約工作或版本不一致；只能重新讀取。');
    }
    orderMutationFlowStore.clearExternalSigningHandoff(command.caseNo);
    if (request !== requestGeneration.current) return;
    setQuery(fresh);
    setUiState({ type: 'ready' });
    setNotice('已記錄送交外部簽署平台。');
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
    return orderMutationFlowStore.getExternalSigningHandoff(command.caseNo) ? undefined : receipt;
  };

  const recordHandoff = async () => {
    if (handoffFlow || busy || finalProtected || (!query && !preparation) || signingBlocked) return;
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor) {
      setUiState({ type: 'error', message: '請先登入後再記錄外部平台交接。' });
      return;
    }
    setUiState({ type: 'working', operation: 'handoff' });
    setNotice(null);
    await submitCurrentHandoff(query, actor);
  };

  const submitCurrentHandoff = (session: ContractExternalSigningQuery | null, actor: string) => submitHandoff({
    caseNo,
    sessionId: session?.session_id ?? null,
    expectedStatusVersion: session?.status_version ?? 0,
    actor,
    identity: createExternalSigningCommandIdentity('handoff'),
  }, false);

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

  const printContract = async (scope: 'client' | 'staff', segmentId: number | null) => {
    printController.current?.abort();
    const controller = new AbortController();
    printController.current = controller;
    const generation = requestGeneration.current;
    setUiState({ type: 'working', operation: 'download' });
    setNotice(null);
    try {
      await openContractPrintView(caseNo, scope, segmentId, controller.signal);
      if (controller.signal.aborted || generation !== requestGeneration.current) return;
      setNotice('已開啟完整契約列印視窗；請選 A4、直向、縮放 100%，關閉頁首及頁尾，可另存為 PDF。');
      setUiState({ type: 'ready' });
    } catch (error) {
      if (controller.signal.aborted || generation !== requestGeneration.current) return;
      setUiState({ type: 'error', message: safeErrorMessage(error) });
    }
  };

  const targetsForSession = (session: ContractExternalSigningQuery): SignedDocumentTarget[] => [
    ...(session.client_target.document_version_id === null ? [] : [{ scope: 'client' as const, matching_segment_id: null, document_version_id: session.client_target.document_version_id }]),
    ...session.staff_targets.map(row => ({ scope: 'staff' as const, matching_segment_id: row.matching_segment_id, document_version_id: row.document_version_id })),
  ];

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
      setTestingFiles([]);
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
      setNotice(readback.filename.startsWith('TEST-ONLY-') ? '測試簽約已完成，已跳過真實簽署文件回收，可接續測試訂金與案件群組流程。' : `契約完成，最終 PDF 第 ${readback.version_number} 版已確認，完整性驗證通過。`);
      await onCommitted?.();
    } catch (error) {
      setUiState({
        type: 'receipt_committed',
        receipt,
        message: `最終文件已受理，但完成結果尚未確認；不要重送。${safeErrorMessage(error)}`,
      });
    }
  };

  const applyTestingFinalDocument = async (preview: FinalDocumentPreview, session: ContractExternalSigningQuery) => {
    const requiredReturnTargets = targetsForSession(session);
    const identity = currentIdentity(identities.current, 'final-apply');
    setUiState({ type: 'working', operation: 'final_apply' });
    try {
      if (!preview.can_apply || preview.session_id !== session.session_id || preview.expected_status_version !== session.status_version || preview.documents.length !== requiredReturnTargets.length
        || preview.documents.some(row => !requiredReturnTargets.some(target => signedTargetKey(target) === signedTargetKey(row) && target.document_version_id === row.document_version_id))) throw new Error('簽約完成檢查未通過，請重新查詢文件。');
      const receipt = await contractExternalSigningClient.applyFinalDocument(caseNo, {
        session_id: preview.session_id,
        documents: preview.documents.map(uploadInput),
        signatures_confirmed: false,
        testing_skip_confirmed: true,
        preview_token: preview.preview_token,
        expected_status_version: preview.expected_status_version,
      }, identity);
      if (
        receipt.receipt_id !== identity.receiptId
        || receipt.session_id !== session.session_id
        || receipt.command_type !== 'apply_final_signed_contract'
        || receipt.matching_segment_id !== null
        || receipt.resulting_status_version !== session.status_version + 1
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
            sessionId: session.session_id,
            matchingSegmentId: null,
            resultingStatusVersion: session.status_version + 1,
          },
          message: '最終 PDF 處理結果未明；不得重送，請使用原操作重新確認。',
        });
      } else {
        setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }
  };

  const prepareTestingSkip = async () => {
    if (!testingSkipAllowed || !handoffRecorded || busy || finalProtected || handoffFlow) return;
    const generation = requestGeneration.current;
    const session = query;
    if (!session?.testing_skip_allowed || generation !== requestGeneration.current) return;
    const requiredReturnTargets = targetsForSession(session);
    setNotice(null);
    setUiState({ type: 'working', operation: 'final_preview' });
    try {
      const preview = await contractExternalSigningClient.prepareTestingSkip(caseNo, {
        session_id: session.session_id, expected_status_version: session.status_version,
      }, currentIdentity(identities.current, 'testing-skip'));
      if (generation !== requestGeneration.current) return;
      if (preview.session_id !== session.session_id || preview.expected_status_version !== session.status_version
        || preview.documents.length !== requiredReturnTargets.length
        || new Set(preview.documents.map(signedTargetKey)).size !== requiredReturnTargets.length
        || preview.documents.some(row => !row.filename.startsWith('TEST-ONLY-') || !requiredReturnTargets.some(target => signedTargetKey(row) === signedTargetKey(target) && row.document_version_id === target.document_version_id))) {
        throw new Error('測試文件與本次契約對象或版本不一致。');
      }
      setTestingFiles(preview.documents.map(row => row.filename));
      identities.current.delete('testing-skip');
      identities.current.delete('final-apply');
      await applyTestingFinalDocument(preview, session);
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

  const busy = uiState.type === 'working' || uiState.type === 'querying';
  const finalProtected = uiState.type === 'outcome_unknown' || uiState.type === 'receipt_committed';
  const signingBlockers = query?.signing_blockers ?? preparation?.signing_blockers ?? [];
  const signingBlocked = signingBlockers.length > 0;
  const metadataLabel = (key: string) => { const meta = contractMetadata[key]; return key === 'client' ? meta?.name : staffIdentity.label(meta?.staffId ?? (Number(query?.staff_targets.find(target => `staff:${target.matching_segment_id}` === key)?.staff_subject_reference) || null), meta?.name); };
  const documentRows = [
    { key: 'client', scope: 'client' as const, segmentId: null, title: '客戶服務契約' },
    ...(query ? query.staff_targets.map(row => ({ key: `staff:${row.matching_segment_id}`, scope: 'staff' as const, segmentId: row.matching_segment_id, title: '月嫂委任契約' }))
      : preparationSegments.map(segmentId => ({ key: `staff:${segmentId}`, scope: 'staff' as const, segmentId, title: '月嫂委任契約' }))),
  ];
  const completedMembers = completedReadback?.documents ?? [];
  const returnTargets = [
    { scope: 'client' as const, matching_segment_id: null },
    ...(archiveSegments ?? []).map(segment => ({ scope: 'staff' as const, matching_segment_id: segment.segment_id })),
  ];
  const saveSignedArchive = async () => {
    if (archiveBusy || archiveSegments === null || archivedFiles !== null) return;
    const client = fileReturns.client;
    if (!client) return;
    const staff = archiveSegments.flatMap(segment => {
      const file = fileReturns['staff:' + segment.segment_id];
      return file ? [{ segmentId: segment.segment_id, file }] : [];
    });
    if (staff.length !== archiveSegments.length) return;
    const identity = currentIdentity(identities.current, 'signed-archive');
    const signal = archiveRequest.current?.signal;
    setArchiveBusy(true);
    setArchiveError(null);
    try {
      const files = await contractExternalSigningClient.archiveSignedFiles(caseNo, client, staff, identity);
      if (signal?.aborted) return;
      setArchivedFiles(files);
      setFileReturns({});
      setArchiveUnknown(false);
    } catch (error) {
      if (signal?.aborted) return;
      setArchiveUnknown(outcomeCouldBeUnknown(error));
      setArchiveError(safeErrorMessage(error));
      return;
    } finally {
      if (!signal?.aborted) setArchiveBusy(false);
    }
    try { await onCommitted?.(); }
    catch (error) { if (!signal?.aborted) setArchiveError(safeErrorMessage(error)); }
  };
  const selectedCount = returnTargets.filter(row => fileReturns[signedTargetKey(row)]).length;
  const testingCompleted = completedReadback?.filename.startsWith('TEST-ONLY-') ?? false;
  const handoffRecorded = query?.handoff_recorded || query?.handoff_logged || preparation?.handoff_logged;
  const phase = archivedFiles !== null || query?.state === 'completed' ? 3 : handoffRecorded ? 2 : 1;
  const testingSkipAllowed = query?.handoff_recorded && query.testing_skip_allowed;
  const returnActionsAvailable = archiveSegments !== null && archivedFiles === null && !completedReadback && query?.state !== 'completed';
  const renderReturn = (target: Pick<SignedDocumentTarget, 'scope' | 'matching_segment_id'>) => {
    const key = signedTargetKey(target), file = fileReturns[key], meta = contractMetadata[key];
    const name = metadataLabel(key) || (target.scope === 'staff' ? staffIdentity.label(archiveSegments?.find(segment => segment.segment_id === target.matching_segment_id)?.staff_id ?? null) : undefined);
    const title = target.scope === 'client' ? '客戶服務契約' : '月嫂委任契約';
    return <article className="contract-return-row" key={key} aria-label={`${title}簽回${name ? ` ${name}` : ''}`}>
      <header><div><strong>{name || title}</strong><p>{meta?.period || '服務期間待核對'}</p></div><span className={`contract-document-status ${file ? 'complete' : ''}`}>{file ? '已選擇' : '待回收'}</span></header>
      <label className="contract-return-file">{target.scope === 'client' ? '客戶服務契約 PDF' : `${name || '月嫂'} 委任契約 PDF`}
        {!file && <input type="file" accept="application/pdf,.pdf" disabled={archiveBusy || archiveUnknown} onChange={event => {
          const file = event.target.files?.item(0) ?? null;
          setFileReturns(previous => ({ ...previous, [key]: file }));
          identities.current.delete('signed-archive');
        }} />}
      </label>
      {file && <div className="contract-return-actions"><strong>{file.name}</strong><button type="button" disabled={archiveBusy || archiveUnknown} onClick={() => {
        setFileReturns(previous => ({ ...previous, [key]: null }));
        identities.current.delete('signed-archive');
      }}>重新選擇檔案</button></div>}
    </article>;
  };
  useUnsavedDraft('紙本契約回傳', { '待確認文件': returnTargets.flatMap(target => { const file = fileReturns[signedTargetKey(target)]; return file ? [file.name] : []; }) }, { baseline: { '待確認文件': [] }, busy: busy || archiveBusy || finalProtected, enabled: !completedReadback && archivedFiles === null });



  return (
    <section aria-label="外部平台簽約與最終 PDF" data-control-id="orders.contract-external-signing.actions" className="contract-signing-workflow">
      <section className="contract-documents-card" aria-label="契約文件">
        <ol className="contract-signing-progress" aria-label="簽約進度">{['列印契約', '送交簽署', '回收簽署文件'].map((label, index) => <li key={label} className={index < phase ? 'complete' : index === phase ? 'current' : ''} aria-current={index === phase ? 'step' : undefined}><span>{index < phase ? '✓' : index + 1}</span>{label}</li>)}</ol>
        <header className="contract-documents-heading"><h3>契約文件</h3></header>
        {metadataError && <p role="alert">{metadataError}</p>}
        {!query && uiState.type === 'ready' && preparationSegments.length === 0 && <p role="status">目前尚未選定可列印契約的月嫂，請先建立推薦方案。</p>}
        <div className="contract-documents-list">{documentRows.map(row => <article className="contract-document-row" key={row.key}>
          <div><strong>{row.title}{metadataLabel(row.key) ? ` · ${metadataLabel(row.key)}` : ''}</strong><p>{contractMetadata[row.key]?.period || '服務期間待核對'}</p></div>
          <div className="contract-document-actions"><button type="button" aria-label={`瀏覽器列印 · ${row.title}${metadataLabel(row.key) ? ` · ${metadataLabel(row.key)}` : ''}`} disabled={busy} onClick={() => void printContract(row.scope, row.segmentId)}>瀏覽器列印</button><button type="button" disabled={busy || finalProtected} onClick={() => setReviewTarget({ scope: row.scope, segmentId: row.segmentId })}>核對資料</button>
          </div>
        </article>)}</div>
      </section>
      <section className="contract-signing-actions-card" aria-label="送交簽署">
        <header className="contract-documents-heading"><h3>送交簽署</h3></header>
        {signingBlocked && <div role="alert" className="contract-manual-notice">
          {signingBlockers.map(code => <p key={code}>{contractCheckReason(code)}</p>)}
          <div className="order-case-action-row">
            {onOpenRecommendation && <button type="button" disabled={busy || finalProtected} onClick={onOpenRecommendation}>更換推薦月嫂</button>}
            {onOpenServiceDates && <button type="button" disabled={busy || finalProtected} onClick={onOpenServiceDates}>調整服務日期</button>}
          </div>
        </div>}
        <div className="contract-platform-action-row"><div><strong>外部平台交接</strong><p>{handoffRecorded
          ? '交接已記錄。'
          : '可記錄已送交外部簽署平台。'}</p></div><div className="contract-signing-action-controls"><span className={`contract-document-status ${handoffRecorded ? 'complete' : ''}`}>{handoffRecorded ? '交接已記錄' : '待記錄'}</span>{!handoffFlow && <button className="formal-recommendation-primary" type="button" disabled={busy || finalProtected || (!query && !preparation) || signingBlocked} onClick={() => void recordHandoff()}>記錄已送交簽署平台</button>}</div></div>
      </section>
      {reviewTarget && <CandidateInquiryDialog title={`核對資料 · ${reviewTarget.scope === 'client' ? '客戶服務契約' : '月嫂委任契約'}`} side onClose={() => setReviewTarget(null)}><div className="contract-review-body"><OrderContractPreview key={`${caseNo}:${reviewTarget.scope}:${reviewTarget.segmentId}`} caseNo={caseNo} revision={revision} initialScope={reviewTarget.scope} targetSegmentId={reviewTarget.segmentId} targetStaffId={contractMetadata[`staff:${reviewTarget.segmentId}`]?.staffId} staffLabels={documentRows.filter(row => row.scope === 'staff').map(row => metadataLabel(row.key) || '月嫂資料待確認')} showScopeControls={false} /></div><footer className="contract-review-footer"><small>完整條文可透過瀏覽器列印查看，並另存為 PDF。</small><button className="formal-recommendation-primary" type="button" disabled={busy} onClick={() => void printContract(reviewTarget.scope, reviewTarget.segmentId)}>瀏覽器列印</button></footer></CandidateInquiryDialog>}

      <section className="contract-return-card" aria-label="回收簽署文件">
        <header className="contract-documents-heading">
          <h3>回收簽署文件</h3>
          {returnActionsAvailable && <span className="contract-document-status">{selectedCount}／{returnTargets.length} 份已選擇</span>}
        </header>
        {returnActionsAvailable ? <>
          <p>客戶服務契約與月嫂委任契約分開上傳。每位月嫂的委任契約各自回收。</p>
          <p>人員確認完約後，選擇並儲存已簽 PDF。</p>
          <section className="contract-return-group"><h4>客戶服務契約</h4>{returnTargets.filter(row => row.scope === 'client').map(renderReturn)}</section>
          <section className="contract-return-group"><h4>月嫂委任契約</h4>{returnTargets.filter(row => row.scope === 'staff').map(renderReturn)}</section>
          {testingSkipAllowed && <details className="contract-signing-test-tools"><summary>測試模式 · 跳過文件回收</summary><div><p>使用 TEST ONLY 占位文件跳過回收。確認後可繼續測試簽約完成與後續收款。</p><button type="button" disabled={busy || finalProtected || !!handoffFlow} onClick={() => void prepareTestingSkip()}>測試用：跳過文件回收</button>{testingFiles.length > 0 && <ul>{testingFiles.map(name => <li key={name}>{name}</li>)}</ul>}</div></details>}
          <div className="contract-final-confirmation">
            {archiveBusy && <p role="status">正在歸檔已簽 PDF…</p>}
            <button className="formal-recommendation-primary" type="button"
              disabled={archiveBusy || returnTargets.some(target => !fileReturns[signedTargetKey(target)])}
              onClick={() => void saveSignedArchive()}>{archiveUnknown ? '重新確認歸檔結果' : '儲存簽署文件'}</button>
          </div>
        </> : archivedFiles !== null || completedReadback ? (
          <section aria-label="契約完成">
            <div className="contract-completed-notice">
              <strong>{testingCompleted ? '測試簽約已完成' : '簽約已完成'}</strong>
              <p>{testingCompleted ? '已保存 TEST ONLY 占位文件。' : '已歸檔工會人員確認的已簽契約。'}</p>
            </div>
            <ul className="contract-signed-list">{archivedFiles !== null
              ? archivedFiles.map(file => <li key={file.file_id}>{file.filename}</li>)
              : completedMembers.length > 0
                ? completedMembers.map(member => <li key={member.controlled_file_id}>{member.filename}</li>)
                : <li>{completedReadback?.filename}</li>}</ul>
            {(onOpenServiceDates || onOpenFinance) && <button className="formal-recommendation-primary" type="button" disabled={busy} onClick={onOpenServiceDates ?? onOpenFinance}>查看服務日期與排班 →</button>}
            <p>訂金已核銷後，建立案件群組並邀請加入。雙方在群組自行協調，由月嫂提交開始日，系統檢查通過即更新正式日期與排班。</p>
          </section>
        ) : !archiveError && <p>正在讀取歸檔資料…</p>}
        {archiveError && <p role="alert">{archiveError}</p>}
      </section>

      {bootstrapReasons.length > 0 && <p role="alert">{bootstrapReasons.join(' ')} <a href={`#clients?case=${encodeURIComponent(caseNo)}&from=workbench`} aria-disabled={busy || finalProtected || undefined} onClick={event => { if (busy || finalProtected) event.preventDefault(); }}>前往客戶名冊補齊資料 →</a></p>}
      {uiState.type === 'error' && <div role="alert"><p>{uiState.message}</p><button type="button" disabled={busy || finalProtected} onClick={() => void loadQuery()}>重新讀取契約狀態</button></div>}
      {busy && <p role="status">{uiState.type === 'working' && uiState.operation === 'handoff' ? '正在記錄送交…' : '正在處理契約資料…'}</p>}

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
