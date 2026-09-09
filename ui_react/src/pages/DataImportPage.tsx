/**
 * File: DataImportPage.tsx
 * Description: 整合工作簿安全匯入與既有數據瀏覽的資料中心分頁。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adaptClientBeClassWorkbookPreview } from '../adapters/case_import/client_beclass_workbook_adapter';
import { adaptHcmWorkbookPreview } from '../adapters/case_import/hcm_workbook_adapter';
import { adaptStaffHistoricalWorkbookPreview } from '../adapters/case_import/staff_historical_workbook_adapter';
import { adaptHistoricalOrderWorkbookPreview } from '../adapters/orders/historical_order_workbook_adapter';
import { ClientBeClassWorkbookSnapshot, clientBeClassWorkbookPreviewClient } from '../api/case_import/client_beclass_workbook/client';
import { HcmWorkbookSnapshot, hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import type { ImportWarningTaskView } from '../api/anomalies/anomaly_query_schemas';
import { hcmResubmissionClient } from '../api/case_import/hcm_resubmission_client';
import type { HcmResubmissionPreview } from '../api/case_import/hcm_workbook_schemas';
import { StaffHistoricalWorkbookSnapshot, staffHistoricalWorkbookPreviewClient } from '../api/case_import/staff_historical_workbook/client';
import { HistoricalOrderWorkbookSnapshot, historicalOrderWorkbookPreviewClient } from '../api/orders/historical_order_workbook/client';
import { HistoricalOrderReviewRemediationWorkbench } from '../components/HistoricalOrderReviewRemediationWorkbench';
import { DataBrowserPage } from './DataBrowserPage';
import './DataImportPage.css';

type ResultState =
  | { kind: 'loading' }
  | { kind: 'ready'; items: ImportWarningTaskView[] }
  | { kind: 'empty' }
  | { kind: 'error'; message: string };

type CasePreviewState<T> =
  | { kind: 'idle' }
  | { kind: 'reading' }
  | { kind: 'loading' }
  | { kind: 'ready'; preview: T }
  | { kind: 'error'; message: string };

type ApplyState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; summary: string; outcome: ApplyOutcome }
  | { kind: 'error'; message: string; outcomeUnknown: boolean };

type ApplyOutcome = 'applied' | 'no-change' | 'needs-review' | 'replayed';

interface ApplyPresentation {
  summary: string;
  outcome: ApplyOutcome;
}

function isOutcomeUnknown(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'retryable' in error && error.retryable === true;
}

function applyReceiptHeading(outcome: ApplyOutcome): string {
  if (outcome === 'replayed') return '這份工作簿已處理過，未重複匯入';
  if (outcome === 'needs-review') return '匯入完成，有資料需要檢查';
  if (outcome === 'no-change') return '匯入完成，未新增資料';
  return '匯入完成';
}

function applyPresentation(replayedWorkbook: boolean, summary: string, outcome: ApplyOutcome): ApplyPresentation {
  return replayedWorkbook
    ? { summary: `以下為上次處理結果：${summary}`, outcome: 'replayed' }
    : { summary, outcome };
}

function previewControlGuidance(
  selectedWorkbook: File | null,
  previewState: CasePreviewState<unknown>
): string {
  if (selectedWorkbook === null) return '請先選擇 .xlsx 工作簿。';
  if (previewState.kind === 'reading' || previewState.kind === 'loading') return '正在預覽檔案，請稍候。';
  if (previewState.kind === 'error') return '預覽未通過：請修正檔案或連線問題後重試。';
  if (previewState.kind === 'ready') return '預覽完成：請核對檔案名稱與筆數。';
  return '檔案已選擇，可以預覽。';
}

function applyControlGuidance(
  previewState: CasePreviewState<unknown>,
  confirmed: boolean,
  applyState: ApplyState
): string {
  if (previewState.kind !== 'ready') return '預覽成功後才能確認匯入。';
  if (applyState.kind === 'loading') return '正在匯入：請勿換檔、離頁或重新整理。';
  if (applyState.kind === 'ready') return '匯入已完成，結果顯示於下方。';
  if (applyState.kind === 'error' && applyState.outcomeUnknown) return '匯入結果尚未確認：請保留本頁，並使用原內容查詢最終結果。';
  if (applyState.kind === 'error') return '匯入未完成：請依錯誤訊息修正後重試。';
  if (!confirmed) return '請先勾選已核對檔案名稱與預覽筆數。';
  return '可以開始匯入；完成後會顯示結果。';
}

interface WorkbookCommandOptions {
  signal?: AbortSignal;
  idempotencyKey: string;
  correlationId: string;
}

function commandIdentity(scope: string, sourceContentDigest: string): { idempotencyKey: string; correlationId: string } {
  const nonce = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return {
    idempotencyKey: `ui-import-${scope}-${sourceContentDigest}`,
    correlationId: `ui-import-${scope}-${nonce}`,
  };
}

function useCaseWorkbookFlow<TSnapshot, TRaw, TModel extends { previewFingerprint: string; sourceContentDigest: string }, TReceipt>(
  fromFile: (file: File) => Promise<TSnapshot>,
  preview: (snapshot: TSnapshot, options: { signal?: AbortSignal }) => Promise<TRaw>,
  apply: (snapshot: TSnapshot, previewFingerprint: string, options: WorkbookCommandOptions) => Promise<TReceipt>,
  adapt: (raw: TRaw) => TModel,
  summarize: (receipt: TReceipt) => ApplyPresentation,
  fallbackError: string,
  scope: string,
  onApplied?: (receipt: TReceipt) => void | Promise<void>
) {
  const [selectedWorkbook, setSelectedWorkbook] = useState<File | null>(null);
  const [previewState, setPreviewState] = useState<CasePreviewState<TModel>>({ kind: 'idle' });
  const [applyState, setApplyState] = useState<ApplyState>({ kind: 'idle' });
  const [confirmed, setConfirmed] = useState(false);
  const snapshotRef = useRef<TSnapshot | null>(null);
  const commandRef = useRef<{ idempotencyKey: string; correlationId: string } | null>(null);
  const generationRef = useRef(0);
  const previewAbortRef = useRef<AbortController | null>(null);
  const mutationLocked = applyState.kind === 'loading' || (applyState.kind === 'error' && applyState.outcomeUnknown);

  useEffect(() => () => {
    previewAbortRef.current?.abort();
    generationRef.current += 1;
  }, []);

  const selectWorkbook = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (mutationLocked) return;
    previewAbortRef.current?.abort();
    generationRef.current += 1;
    setSelectedWorkbook(event.target.files?.[0] ?? null);
    setPreviewState({ kind: 'idle' });
    setApplyState({ kind: 'idle' });
    setConfirmed(false);
    snapshotRef.current = null;
    commandRef.current = null;
  };

  const previewWorkbook = async () => {
    if (mutationLocked) return;
    if (selectedWorkbook === null) {
      setPreviewState({ kind: 'error', message: '請先選擇 .xlsx 檔案。' });
      return;
    }
    previewAbortRef.current?.abort();
    const controller = new AbortController();
    previewAbortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setPreviewState({ kind: 'reading' });
    try {
      const snapshot = await fromFile(selectedWorkbook);
      if (controller.signal.aborted || generation !== generationRef.current) return;
      setPreviewState({ kind: 'loading' });
      const raw = await preview(snapshot, { signal: controller.signal });
      if (controller.signal.aborted || generation !== generationRef.current) return;
      const adapted = adapt(raw);
      setPreviewState({ kind: 'ready', preview: adapted });
      snapshotRef.current = snapshot;
      commandRef.current = commandIdentity(scope, adapted.sourceContentDigest);
      setApplyState({ kind: 'idle' });
      setConfirmed(false);
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current) return;
      setPreviewState({ kind: 'error', message: error instanceof Error ? error.message : fallbackError });
    } finally {
      if (previewAbortRef.current === controller) previewAbortRef.current = null;
    }
  };

  const applyWorkbook = async () => {
    const snapshot = snapshotRef.current;
    const command = commandRef.current;
    if (!confirmed || snapshot === null || command === null || previewState.kind !== 'ready') return;
    setApplyState({ kind: 'loading' });
    try {
      const receipt = await apply(snapshot, previewState.preview.previewFingerprint, command);
      const presentation = summarize(receipt);
      setApplyState({ kind: 'ready', ...presentation });
      await onApplied?.(receipt);
    } catch (error) {
      setApplyState({
        kind: 'error',
        message: error instanceof Error ? error.message : '工作簿套用失敗。',
        outcomeUnknown: isOutcomeUnknown(error),
      });
    }
  };

  return { selectedWorkbook, previewState, applyState, confirmed, mutationLocked, setConfirmed, selectWorkbook, previewWorkbook, applyWorkbook };
}

interface CaseWorkbookPreviewCardProps {
  id: string;
  icon: string;
  title: string;
  inputLabel: string;
  openPreviewControlId?: string;
  rowDetailUnavailableMessage?: string;
  selectedWorkbook: File | null;
  previewState: CasePreviewState<{ sourceContentDigest: string; previewFingerprint: string }>;
  applyState: ApplyState;
  confirmed: boolean;
  mutationLocked: boolean;
  metrics: Array<[string, number]>;
  onSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onPreview: () => Promise<void>;
  onConfirm: (confirmed: boolean) => void;
  onApply: () => Promise<void>;
  reviewAction?: React.ReactNode;
}

const CaseWorkbookPreviewCard: React.FC<CaseWorkbookPreviewCardProps> = ({
  id, icon, title, inputLabel, openPreviewControlId, rowDetailUnavailableMessage, selectedWorkbook, previewState, applyState, confirmed, mutationLocked, metrics, onSelect, onPreview, onConfirm, onApply, reviewAction,
}) => {
  const previewGuidanceId = `imports-${id}-preview-guidance`;
  const applyGuidanceId = `imports-${id}-apply-guidance`;
  return (
    <section className="import-workbench-card" data-surface-id={`imports.${id}.workbench`}>
      <div className="import-card-header">
        <div className="import-icon-title-group">
          <div className="import-icon-badge">{icon}</div>
          <div className="import-card-title-group">
            <h2>{title}</h2>
            <p>上傳檔案 • 預覽核對 • 確認匯入</p>
          </div>
        </div>
        <span className={`import-status-pill ${applyState.kind === 'ready' ? 'ready' : previewState.kind === 'ready' ? 'idle' : 'locked'}`}>
          {applyState.kind === 'ready' ? '✅ 匯入完成' : previewState.kind === 'ready' ? '🔍 預覽就緒' : '待選檔'}
        </span>
      </div>
      <p className="import-description">先預覽完整工作簿，這一步不會匯入資料；核對檔案與筆數後再確認匯入。</p>
      <div className="import-file-upload-box">
        <div className="import-file-selector-row">
          <input id={`file-input-${id}`} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label={inputLabel} data-control-id={openPreviewControlId} disabled={mutationLocked} onChange={onSelect} className="import-file-native-hidden" />
          <label htmlFor={`file-input-${id}`} className={`import-file-picker-label ${mutationLocked ? 'disabled' : ''}`}>📂 選擇檔案</label>
          <span className={`import-file-name-display ${selectedWorkbook ? 'selected' : ''}`} title={selectedWorkbook?.name}>{selectedWorkbook ? `📄 ${selectedWorkbook.name}` : '未選擇任何檔案'}</span>
          <button type="button" data-control-id={`imports.${id}.preview`} aria-describedby={previewGuidanceId} className="import-preview-btn" disabled={mutationLocked || selectedWorkbook === null || previewState.kind === 'reading' || previewState.kind === 'loading'} onClick={() => void onPreview()}>
            {previewState.kind === 'reading' ? '正在讀取檔案…' : previewState.kind === 'loading' ? '預覽中…' : '預覽檔案'}
          </button>
        </div>
        <p id={previewGuidanceId} className="import-control-guidance" data-surface-id={`imports.${id}.preview-guidance`}>{previewControlGuidance(selectedWorkbook, previewState)}</p>
      </div>
      {previewState.kind === 'error' && <div className="import-error" role="alert">{previewState.message}</div>}
      {previewState.kind === 'ready' && (
        <div className="import-preview-result" data-surface-id={`imports.${id}.preview-result`}>
          <h4>預覽結果</h4>
          <dl className="import-preview-metrics">{metrics.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          {rowDetailUnavailableMessage && <div className="import-row-unavailable">{rowDetailUnavailableMessage}</div>}
        </div>
      )}
      {previewState.kind === 'ready' && (
        <div className="import-apply-locked">
          <label><input type="checkbox" checked={confirmed} disabled={mutationLocked} onChange={(event) => onConfirm(event.target.checked)} />我已核對檔案名稱與預覽筆數</label>
          <button type="button" data-control-id={`imports.${id}.apply`} aria-describedby={applyGuidanceId} className="import-apply-btn" disabled={!confirmed || applyState.kind === 'loading' || applyState.kind === 'ready' || (mutationLocked && !(applyState.kind === 'error' && applyState.outcomeUnknown))} onClick={() => void onApply()}>
            {applyState.kind === 'loading' ? '匯入中…' : applyState.kind === 'error' && applyState.outcomeUnknown ? '查詢這次匯入結果' : '確認匯入'}
          </button>
        </div>
      )}
      <p id={applyGuidanceId} className="import-control-guidance" data-surface-id={`imports.${id}.apply-guidance`}>{applyControlGuidance(previewState, confirmed, applyState)}</p>
      {applyState.kind === 'error' && <div className="import-error" role="alert">{applyState.message}</div>}
      {applyState.kind === 'ready' && (
        <div className={`import-receipt-box ${applyState.outcome === 'needs-review' ? 'warning' : ''}`} role="status">
          <strong>{applyReceiptHeading(applyState.outcome)}</strong><p>{applyState.summary}</p>
          {applyState.outcome === 'needs-review' && (reviewAction ?? <button type="button" className="import-referral-btn" onClick={() => { window.location.hash = '#anomalies'; }}>🔍 前往異常審核處置問題列</button>)}
        </div>
      )}
    </section>
  );
};

interface HcmCorrectionSelection {
  task: ImportWarningTaskView;
  reviewIdentity: string;
}

const HcmControlledCorrection: React.FC<{
  selection: HcmCorrectionSelection;
  onCancel: () => void;
  onApplied: () => void;
}> = ({ selection, onCancel, onApplied }) => {
  const [snapshot, setSnapshot] = useState<HcmWorkbookSnapshot | null>(null);
  const [preview, setPreview] = useState<HcmResubmissionPreview | null>(null);
  const [reason, setReason] = useState('修正 HCM 匯入異常');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const selectFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setPreview(null);
    setMessage(null);
    if (!file) { setSnapshot(null); return; }
    try { setSnapshot(await HcmWorkbookSnapshot.fromFile(file)); }
    catch (error) { setSnapshot(null); setMessage(error instanceof Error ? error.message : '無法讀取修正版。'); }
  };

  const previewCorrection = async () => {
    if (!snapshot || busy) return;
    setBusy(true); setMessage(null);
    try { setPreview(await hcmResubmissionClient.preview(snapshot, selection.reviewIdentity)); }
    catch (error) { setMessage(error instanceof Error ? error.message : '修正預覽失敗。'); }
    finally { setBusy(false); }
  };

  const applyCorrection = async () => {
    if (!snapshot || !preview || !reason.trim() || busy) return;
    setBusy(true); setMessage(null);
    try {
      await hcmResubmissionClient.apply(snapshot, preview, reason.trim());
      onApplied();
    } catch (error) { setMessage(error instanceof Error ? error.message : '修正套用失敗。'); }
    finally { setBusy(false); }
  };

  return (
    <section className="import-workbench-card" data-surface-id="imports.hcm-correction.workbench">
      <div className="import-card-header"><div className="import-card-title-group"><h2>修正案件 {selection.task.subject}</h2><p>{selection.task.display_message}</p></div></div>
      <p className="import-description">請選擇包含本案件的完整 HCM 修正版。系統會先預覽，且只會更新這項異常對應的欄位。</p>
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label="選擇 HCM 修正版" disabled={busy} onChange={(event) => void selectFile(event)} />
      <button type="button" className="import-preview-btn" disabled={!snapshot || busy} onClick={() => void previewCorrection()}>{busy && !preview ? '預覽中…' : '預覽修正'}</button>
      {preview && <div className="import-preview-result" role="status"><strong>只會修正：{preview.source_field}</strong><p>案件 {preview.case_no}；套用前仍會重新確認資料版本。</p></div>}
      {preview && <label>修正原因<input value={reason} maxLength={500} disabled={busy} onChange={(event) => setReason(event.target.value)} /></label>}
      {preview && <button type="button" className="import-apply-btn" disabled={busy || !reason.trim()} onClick={() => void applyCorrection()}>{busy ? '套用中…' : '確認套用修正'}</button>}
      <button type="button" disabled={busy} onClick={onCancel}>取消</button>
      {message && <div className="import-error" role="alert">{message}</div>}
    </section>
  );
};

export type DataCenterTab = 'workbook-import' | 'data-browser';

export interface DataImportPageProps {
  initialTab?: DataCenterTab;
}

export const DataImportPage: React.FC<DataImportPageProps> = ({ initialTab = 'workbook-import' }) => {
  const [activeTab, setActiveTab] = useState<DataCenterTab>(initialTab);
  const [state, setState] = useState<ResultState>({ kind: 'loading' });
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const [historicalReviewIdentities, setHistoricalReviewIdentities] = useState<string[]>([]);
  const [selectedHistoricalReviewIdentity, setSelectedHistoricalReviewIdentity] = useState<string | null>(null);
  const [hcmCorrection, setHcmCorrection] = useState<HcmCorrectionSelection | null>(null);
  const [referralError, setReferralError] = useState<string | null>(null);

  const loadResults = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setState({ kind: 'loading' });
    try {
      const tasks = await anomalyQueryClient.queryImportWarningTasks({ activeOnly: true, limit: 200 }, { signal: controller.signal });
      if (controller.signal.aborted || generation !== generationRef.current) return;
      const seenCases = new Set<string>();
      const items = tasks.filter((task) => {
        if (task.owning_lane !== 'hcm' || seenCases.has(task.subject)) return false;
        seenCases.add(task.subject);
        return true;
      });
      setState(items.length ? { kind: 'ready', items } : { kind: 'empty' });
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current) return;
      setState({ kind: 'error', message: error instanceof Error ? error.message : 'HCM 匯入結果載入失敗。' });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => { if (!cancelled) void loadResults(); });
    return () => {
      cancelled = true;
      abortRef.current?.abort();
      generationRef.current += 1;
    };
  }, [loadResults]);

  const hcmCurrent = useCaseWorkbookFlow(
    HcmWorkbookSnapshot.fromFile,
    (snapshot, options) => hcmWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => hcmWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptHcmWorkbookPreview,
    (receipt) => applyPresentation(receipt.replayed_workbook, `新增 ${receipt.inserted_count} 筆、含警示 ${receipt.inserted_with_warning_count} 筆、既有案件跳過 ${receipt.skipped_existing_count} 筆、需檢查 ${receipt.review_required_count} 筆、失敗 ${receipt.failed_count} 筆。`, receipt.review_required_count > 0 || receipt.failed_count > 0 ? 'needs-review' : receipt.inserted_count === 0 ? 'no-change' : 'applied'),
    'HCM 工作簿處理失敗。', 'hcm-current', () => loadResults()
  );
  const clientBeClass = useCaseWorkbookFlow(
    ClientBeClassWorkbookSnapshot.fromFile,
    (snapshot, options) => clientBeClassWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => clientBeClassWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptClientBeClassWorkbookPreview,
    (receipt) => applyPresentation(receipt.replayed_workbook, `建立 ${receipt.created_count} 筆、已存在相同資料 ${receipt.exact_replay_count} 筆、需檢查 ${receipt.review_required_count} 筆、既有衝突 ${receipt.existing_conflict_count} 筆、既有來源 ${receipt.existing_source_count} 筆。`, receipt.review_required_count > 0 || receipt.existing_conflict_count > 0 ? 'needs-review' : receipt.created_count === 0 ? 'no-change' : 'applied'),
    '客戶 BeClass 工作簿處理失敗。', 'client-beclass'
  );
  const staffHistorical = useCaseWorkbookFlow(
    StaffHistoricalWorkbookSnapshot.fromFile,
    (snapshot, options) => staffHistoricalWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => staffHistoricalWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptStaffHistoricalWorkbookPreview,
    (receipt) => applyPresentation(receipt.replayed_workbook, `新建 ${receipt.created_count} 筆、採用既有 ${receipt.adopted_existing_count} 筆、已存在相同資料 ${receipt.exact_replay_count} 筆、身分阻擋 ${receipt.blocked_identity_count} 筆、身分衝突 ${receipt.identity_conflict_count} 筆、需檢查 ${receipt.review_required_count} 筆。`, receipt.blocked_identity_count > 0 || receipt.identity_conflict_count > 0 || receipt.review_required_count > 0 ? 'needs-review' : receipt.created_count + receipt.adopted_existing_count === 0 ? 'no-change' : 'applied'),
    '月嫂歷史工作簿處理失敗。', 'staff-historical'
  );
  const historicalOrders = useCaseWorkbookFlow(
    HistoricalOrderWorkbookSnapshot.fromFile,
    (snapshot, options) => historicalOrderWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => historicalOrderWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptHistoricalOrderWorkbookPreview,
    (receipt) => applyPresentation(receipt.replayed_workbook, `不採用 ${receipt.result_counts.not_adopted} 筆、配對中未付訂金 ${receipt.result_counts.matching_pending_deposit} 筆、已付訂金未服務 ${receipt.result_counts.historical_unserved} 筆、歷史服務中 ${receipt.result_counts.historical_in_service} 筆、歷史服務完成 ${receipt.result_counts.historical_service_completed} 筆、工作簿未列入而取消 ${receipt.absent_order_cancellation_count} 筆。`, receipt.review_required_count > 0 || receipt.current_conflict_count > 0 ? 'needs-review' : receipt.adopted_count + receipt.absent_order_cancellation_count === 0 ? 'no-change' : 'applied'),
    '歷史訂單工作簿處理失敗。', 'historical-orders-authoritative-v3', (receipt) => {
      setHistoricalReviewIdentities(receipt.review_references);
      setSelectedHistoricalReviewIdentity(null);
    }
  );

  const historicalReviewAction = historicalReviewIdentities.length === 0 ? undefined : (
    <div className="import-referral-group" aria-label="歷史訂單待確認處理入口">
      <p>這次匯入有 {historicalReviewIdentities.length} 筆資料需要確認，請直接處理：</p>
      {historicalReviewIdentities.map((reviewIdentity, index) => (
        <button
          key={reviewIdentity}
          type="button"
          className="import-referral-btn"
          onClick={() => setSelectedHistoricalReviewIdentity(reviewIdentity)}
        >
          🛠️ 處理歷史訂單待確認 {index + 1}
        </button>
      ))}
    </div>
  );

  const mutationLocked = hcmCurrent.mutationLocked || clientBeClass.mutationLocked || staffHistorical.mutationLocked || historicalOrders.mutationLocked;

  useEffect(() => {
    if (!mutationLocked) return undefined;
    const preventUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const preventInAppNavigation = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target?.closest('a[href^="#"], .brand-section, .section-tab-btn, .sidebar-nav-item, .notification-btn, .logout-action-btn')) return;
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener('beforeunload', preventUnload);
    document.addEventListener('click', preventInAppNavigation, true);
    return () => { window.removeEventListener('beforeunload', preventUnload); document.removeEventListener('click', preventInAppNavigation, true); };
  }, [mutationLocked]);

  const handleHcmProblem = async (task: ImportWarningTaskView) => {
    if (mutationLocked) return;
    setReferralError(null);
    if (!['HCM-FIELD-001', 'HCM-FIELD-002'].includes(task.logical_code)) {
      window.location.hash = '#anomalies';
      return;
    }
    try {
      const referral = await anomalyQueryClient.queryImportWarningReferral({ occurrenceIdentity: task.occurrence_identity, expectedVersion: task.tracking_version });
      if (referral.target_command !== 'preview_hcm_resubmission') throw new Error('此異常目前不能直接修正。');
      setHcmCorrection({ task, reviewIdentity: referral.review_identity });
    } catch (error) {
      setReferralError(error instanceof Error ? error.message : '無法開啟 HCM 修正。');
    }
  };

  const hcmActionLabel = (task: ImportWarningTaskView): string => {
    if (['HCM-FIELD-001', 'HCM-FIELD-002'].includes(task.logical_code)) return '提交受控修正';
    if (task.logical_code.startsWith('HCM-LINK-')) return '確認客戶身分';
    return '檢查系統設定／重新檢查';
  };

  const selectTab = (tab: DataCenterTab) => {
    setActiveTab(tab);
    window.location.hash = tab === 'data-browser' ? '#data-browser' : '#data-import';
  };

  return (
    <div data-surface-id="imports.page" className="import-page-container">
      <div className="datacenter-tabs-container">
        <button type="button" className={`datacenter-tab-btn ${activeTab === 'workbook-import' ? 'active' : ''}`} onClick={() => selectTab('workbook-import')}>📥 工作簿資料匯入 (Data Import)<span className="datacenter-tab-pill">4 類卡片</span></button>
        <button type="button" className={`datacenter-tab-btn ${activeTab === 'data-browser' ? 'active' : ''}`} onClick={() => selectTab('data-browser')}>📊 數據瀏覽 (Data Browser)<span className="datacenter-tab-pill">唯讀</span></button>
      </div>

      {activeTab === 'workbook-import' && (
        <div>
          <header className="page-header-banner import-result-header">
            <div><h1 className="page-title">📥 批次資料匯入中心</h1><p className="page-subtitle">選擇工作簿、預覽核對，確認後即可完成匯入；HCM 匯入後會自動重新查詢結果。</p></div>
            <button type="button" className="import-result-refresh" data-control-id="imports.hcm-results.refresh" onClick={() => void loadResults()}>重新整理結果</button>
          </header>
          {mutationLocked && <div className="import-result-state" role="status" data-surface-id="imports.apply-navigation-lock">匯入已送出或結果尚未確認；目前已鎖定換檔、預覽、站內導覽與重新整理。請留在本頁等待結果。</div>}
          <div className="import-cards-grid">
            <CaseWorkbookPreviewCard id="hcm-current" icon="📄" title="1. HCM 案件匯入 (HCM Current)" inputLabel="選擇 HCM Current Workbook" openPreviewControlId="imports.hcm-current.open-preview" rowDetailUnavailableMessage={hcmCurrent.previewState.kind === 'ready' ? hcmCurrent.previewState.preview.rowDetailUnavailableMessage : undefined} selectedWorkbook={hcmCurrent.selectedWorkbook} previewState={hcmCurrent.previewState} applyState={hcmCurrent.applyState} confirmed={hcmCurrent.confirmed} mutationLocked={mutationLocked} metrics={hcmCurrent.previewState.kind === 'ready' ? [['來源列數', hcmCurrent.previewState.preview.sourceRowCount], ['可寫入', hcmCurrent.previewState.preview.readyCount], ['含警示', hcmCurrent.previewState.preview.readyWithWarningCount], ['需人工檢查', hcmCurrent.previewState.preview.reviewRequiredCount]] : []} onSelect={hcmCurrent.selectWorkbook} onPreview={hcmCurrent.previewWorkbook} onConfirm={hcmCurrent.setConfirmed} onApply={hcmCurrent.applyWorkbook} />
            <CaseWorkbookPreviewCard id="client-beclass" icon="👥" title="2. 客戶 BeClass 問卷匯入" inputLabel="選擇客戶 BeClass Workbook" selectedWorkbook={clientBeClass.selectedWorkbook} previewState={clientBeClass.previewState} applyState={clientBeClass.applyState} confirmed={clientBeClass.confirmed} mutationLocked={mutationLocked} metrics={clientBeClass.previewState.kind === 'ready' ? [['來源列數', clientBeClass.previewState.preview.sourceRowCount], ['可建立', clientBeClass.previewState.preview.createCount], ['需人工檢查', clientBeClass.previewState.preview.reviewRequiredCount], ['既有衝突', clientBeClass.previewState.preview.existingConflictCount], ['既有來源', clientBeClass.previewState.preview.existingSourceCount]] : []} onSelect={clientBeClass.selectWorkbook} onPreview={clientBeClass.previewWorkbook} onConfirm={clientBeClass.setConfirmed} onApply={clientBeClass.applyWorkbook} />
            <CaseWorkbookPreviewCard id="staff-historical" icon="👩‍🍼" title="3. 月嫂歷史資料匯入" inputLabel="選擇月嫂歷史 Workbook" selectedWorkbook={staffHistorical.selectedWorkbook} previewState={staffHistorical.previewState} applyState={staffHistorical.applyState} confirmed={staffHistorical.confirmed} mutationLocked={mutationLocked} metrics={staffHistorical.previewState.kind === 'ready' ? [['來源列數', staffHistorical.previewState.preview.sourceRowCount], ['新建', staffHistorical.previewState.preview.createdCount], ['採用既有', staffHistorical.previewState.preview.adoptedExistingCount], ['身分阻擋', staffHistorical.previewState.preview.blockedIdentityCount], ['身分衝突', staffHistorical.previewState.preview.identityConflictCount], ['需人工檢查', staffHistorical.previewState.preview.reviewRequiredCount]] : []} onSelect={staffHistorical.selectWorkbook} onPreview={staffHistorical.previewWorkbook} onConfirm={staffHistorical.setConfirmed} onApply={staffHistorical.applyWorkbook} />
            <CaseWorkbookPreviewCard id="historic-orders" icon="📦" title="4. 歷史訂單認領匯入" inputLabel="選擇歷史訂單 Workbook" selectedWorkbook={historicalOrders.selectedWorkbook} previewState={historicalOrders.previewState} applyState={historicalOrders.applyState} confirmed={historicalOrders.confirmed} mutationLocked={mutationLocked} metrics={historicalOrders.previewState.kind === 'ready' ? [['來源列數', historicalOrders.previewState.preview.sourceRowCount], ['工作簿未列入將取消', historicalOrders.previewState.preview.absentOrderCancellationCount], ['不採用', historicalOrders.previewState.preview.resultCounts.notAdopted], ['配對中未付訂金', historicalOrders.previewState.preview.resultCounts.matchingPendingDeposit], ['已付訂金未服務', historicalOrders.previewState.preview.resultCounts.historicalUnserved], ['歷史服務中', historicalOrders.previewState.preview.resultCounts.historicalInService], ['歷史服務完成', historicalOrders.previewState.preview.resultCounts.historicalServiceCompleted], ['目前資料衝突', historicalOrders.previewState.preview.currentConflictCount]] : []} onSelect={historicalOrders.selectWorkbook} onPreview={historicalOrders.previewWorkbook} onConfirm={historicalOrders.setConfirmed} onApply={historicalOrders.applyWorkbook} reviewAction={historicalReviewAction} />
          </div>
          {selectedHistoricalReviewIdentity && <section className="import-workbench-card" aria-label="歷史訂單欄位衝突更正">
            <HistoricalOrderReviewRemediationWorkbench
              reviewIdentity={selectedHistoricalReviewIdentity}
              onResolved={() => {
                setHistoricalReviewIdentities((current) => current.filter((item) => item !== selectedHistoricalReviewIdentity));
                setSelectedHistoricalReviewIdentity(null);
              }}
            />
          </section>}
        </div>
      )}

      {activeTab === 'data-browser' && <DataBrowserPage />}

      {activeTab === 'workbook-import' && (
      <div>
        <section className="import-result-workbench" data-surface-id="imports.hcm-results.open">
          <div className="import-result-title-row"><div><span className="import-icon">🏢</span><h2>HCM 目前待處理異常</h2></div><span className="import-status-badge ready">每案僅顯示最新一筆</span></div>
          {state.kind === 'loading' && <div className="import-result-state" role="status">正在載入待處理異常…</div>}
          {state.kind === 'error' && <div className="import-result-state import-result-error" data-surface-id="imports.hcm-results.error" role="status"><strong>待處理異常暫時無法載入；不影響上方工作簿預覽與匯入。</strong><p>{state.message}</p><button type="button" data-control-id="imports.hcm-results.retry" onClick={() => void loadResults()}>重試查詢</button></div>}
          {state.kind === 'empty' && <div className="import-result-state" data-surface-id="imports.hcm-results.empty">目前沒有待處理的 HCM 異常。</div>}
          {referralError && <div className="import-result-state import-result-error" role="alert">{referralError}</div>}
          {state.kind === 'ready' && state.items.map((task) => (
            <article key={task.occurrence_identity} className="import-result-problem" data-surface-id={`imports.hcm-results.problem.${encodeURIComponent(task.occurrence_identity)}`}>
              <strong>案件 {task.subject}</strong>
              <span>{task.display_message}</span>
              <button type="button" disabled={mutationLocked} data-control-id={`imports.hcm-results.problem.referral.${encodeURIComponent(task.occurrence_identity)}`} onClick={() => void handleHcmProblem(task)}>{hcmActionLabel(task)}</button>
            </article>
          ))}
        </section>
        {hcmCorrection && <HcmControlledCorrection selection={hcmCorrection} onCancel={() => setHcmCorrection(null)} onApplied={() => {
          setState((current) => {
            if (current.kind !== 'ready') return current;
            const items = current.items.filter((item) => item.subject !== hcmCorrection.task.subject);
            return items.length ? { kind: 'ready', items } : { kind: 'empty' };
          });
          setHcmCorrection(null);
        }} />}
      </div>
      )}
    </div>
  );
};

export default DataImportPage;
