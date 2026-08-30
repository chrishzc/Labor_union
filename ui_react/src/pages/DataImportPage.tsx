/**
 * File: DataImportPage.tsx
 * Description: 整合工作簿安全匯入與既有數據瀏覽的資料中心分頁。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adaptClientBeClassWorkbookPreview } from '../adapters/case_import/client_beclass_workbook_adapter';
import { adaptHcmWorkbookPreview } from '../adapters/case_import/hcm_workbook_adapter';
import { adaptHcmImportResult, type HcmImportResultViewModel } from '../adapters/case_import/hcm_import_result_adapter';
import { adaptStaffHistoricalWorkbookPreview } from '../adapters/case_import/staff_historical_workbook_adapter';
import { adaptHistoricalOrderWorkbookPreview } from '../adapters/orders/historical_order_workbook_adapter';
import { ClientBeClassWorkbookSnapshot, clientBeClassWorkbookPreviewClient } from '../api/case_import/client_beclass_workbook/client';
import { HcmWorkbookSnapshot, hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
import { hcmImportResultClient } from '../api/case_import/hcm_import_result_client';
import { StaffHistoricalWorkbookSnapshot, staffHistoricalWorkbookPreviewClient } from '../api/case_import/staff_historical_workbook/client';
import { HistoricalOrderWorkbookSnapshot, historicalOrderWorkbookPreviewClient } from '../api/orders/historical_order_workbook/client';
import { DataBrowserPage } from './DataBrowserPage';
import './DataImportPage.css';

type ResultState =
  | { kind: 'loading' }
  | { kind: 'ready'; items: HcmImportResultViewModel[] }
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
  onApplied?: () => void | Promise<void>
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
      await onApplied?.();
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
}

const CaseWorkbookPreviewCard: React.FC<CaseWorkbookPreviewCardProps> = ({
  id, icon, title, inputLabel, openPreviewControlId, rowDetailUnavailableMessage, selectedWorkbook, previewState, applyState, confirmed, mutationLocked, metrics, onSelect, onPreview, onConfirm, onApply,
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
          {applyState.outcome === 'needs-review' && <button type="button" className="import-referral-btn" onClick={() => { window.location.hash = '#anomalies'; }}>🔍 前往異常審核處置問題列</button>}
        </div>
      )}
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

  const loadResults = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setState({ kind: 'loading' });
    try {
      const page = await hcmImportResultClient.query({ limit: 20 }, { signal: controller.signal });
      if (controller.signal.aborted || generation !== generationRef.current) return;
      const items = page.items.map(adaptHcmImportResult);
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
    (receipt) => applyPresentation(receipt.replayed_workbook, `新增 ${receipt.inserted_count} 筆、含警示 ${receipt.inserted_with_warning_count} 筆、已存在相同資料 ${receipt.exact_replay_count} 筆、需檢查 ${receipt.review_required_count} 筆、失敗 ${receipt.failed_count} 筆。`, receipt.review_required_count > 0 || receipt.failed_count > 0 ? 'needs-review' : receipt.inserted_count === 0 ? 'no-change' : 'applied'),
    'HCM 工作簿處理失敗。', 'hcm-current', loadResults
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
    (receipt) => applyPresentation(receipt.replayed_workbook, `認領 ${receipt.adopted_count} 筆、建立指派 ${receipt.assignments_created} 筆、已存在相同資料 ${receipt.replayed_rows} 筆、未配對案件 ${receipt.unmatched_case_count} 筆、需檢查 ${receipt.review_required_count} 筆、目前資料衝突 ${receipt.current_conflict_count} 筆。狀態判定：0→取消 ${receipt.status_counts.cancelled_0} 筆、1→完成 ${receipt.status_counts.completed_1} 筆、2→洽談中 ${receipt.status_counts.discussion_2} 筆、無法辨識 ${receipt.status_counts.invalid_or_blank} 筆。`, receipt.unmatched_case_count > 0 || receipt.review_required_count > 0 || receipt.current_conflict_count > 0 ? 'needs-review' : receipt.adopted_count === 0 ? 'no-change' : 'applied'),
    '歷史訂單工作簿處理失敗。', 'historical-orders'
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

  const navigateToWarning = () => {
    if (mutationLocked) return;
    window.location.hash = '#anomalies';
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
            <CaseWorkbookPreviewCard id="historic-orders" icon="📦" title="4. 歷史訂單認領匯入" inputLabel="選擇歷史訂單 Workbook" selectedWorkbook={historicalOrders.selectedWorkbook} previewState={historicalOrders.previewState} applyState={historicalOrders.applyState} confirmed={historicalOrders.confirmed} mutationLocked={mutationLocked} metrics={historicalOrders.previewState.kind === 'ready' ? [['來源列數', historicalOrders.previewState.preview.sourceRowCount], ['可認領', historicalOrders.previewState.preview.adoptedCount], ['無對應案件', historicalOrders.previewState.preview.unmatchedCaseCount], ['需人工檢查', historicalOrders.previewState.preview.reviewRequiredCount], ['目前資料衝突', historicalOrders.previewState.preview.currentConflictCount], ['派工候選', historicalOrders.previewState.preview.assignmentCandidateCount], ['僅證據配對', historicalOrders.previewState.preview.evidenceOnlyPairingCount], ['來源狀態 0 → 訂單取消', historicalOrders.previewState.preview.statusCounts.cancelled0], ['來源狀態 1 → 訂單完成', historicalOrders.previewState.preview.statusCounts.completed1], ['來源狀態 2 → 洽談中', historicalOrders.previewState.preview.statusCounts.discussion2], ['狀態無法辨識', historicalOrders.previewState.preview.statusCounts.invalidOrBlank]] : []} onSelect={historicalOrders.selectWorkbook} onPreview={historicalOrders.previewWorkbook} onConfirm={historicalOrders.setConfirmed} onApply={historicalOrders.applyWorkbook} />
          </div>
        </div>
      )}

      {activeTab === 'data-browser' && <DataBrowserPage />}

      <div className="sr-only">
        <section className="import-result-workbench" data-surface-id="imports.hcm-results.open">
          <div className="import-result-title-row"><div><span className="import-icon">🏢</span><h2>HCM 最近匯入紀錄與問題檢查</h2></div><span className="import-status-badge ready">唯讀查詢</span></div>
          {state.kind === 'loading' && <div className="import-result-state" role="status">正在載入最近匯入結果…</div>}
          {state.kind === 'error' && <div className="import-result-state import-result-error" data-surface-id="imports.hcm-results.error" role="status"><strong>最近匯入結果暫時無法載入；不影響上方工作簿預覽與匯入。</strong><p>{state.message}</p><button type="button" data-control-id="imports.hcm-results.retry" onClick={() => void loadResults()}>重試結果查詢</button></div>}
          {state.kind === 'empty' && <div className="import-result-state" data-surface-id="imports.hcm-results.empty">目前沒有可查詢的 HCM 匯入結果。</div>}
          {state.kind === 'ready' && state.items.map((result) => (
            <article key={result.receiptId} className="import-result-batch" data-surface-id={`imports.hcm-results.receipt.${result.receiptId}`}>
              <header><div><strong>匯入結果</strong><span>{result.completedAt}</span></div></header>
              <p className="import-result-summary">{result.summary}｜來源 {result.sourceRowCount} 列</p>
              {!result.rowOutcomesAvailable ? <div className="import-result-legacy" data-surface-id="imports.hcm-results.legacy-unavailable">歷史匯入摘要；本批次統計如上，新版匯入會在此列出逐列結果。</div> : (
                <div className="import-result-columns">
                  <section data-surface-id="imports.hcm-results.new-orders"><h3>本次新增訂單</h3>{result.newOrders.length === 0 ? <p>本批次沒有新增訂單。</p> : result.newOrders.map((row) => <div key={row.source_row} className="import-result-row" data-surface-id={`imports.hcm-results.new-order.${encodeURIComponent(row.case_no ?? `row-${row.source_row}`)}`}><strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong><span>{row.outcome}</span></div>)}</section>
                  <section data-surface-id="imports.hcm-results.problems"><h3>需要檢查</h3>{result.problems.length === 0 ? <p>本批次沒有問題列。</p> : result.problems.map((row) => <div key={row.source_row} className="import-result-problem" data-surface-id={`imports.hcm-results.problem.${encodeURIComponent(row.problem_identity ?? `row-${row.source_row}`)}`}><strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong><span>欄位：{row.problem_fields.join('、') || '無'}</span><span>代碼：{row.issue_codes.join('、') || '無'}</span><button type="button" disabled={mutationLocked} data-control-id={`imports.hcm-results.problem.referral.${encodeURIComponent(row.problem_identity ?? `row-${row.source_row}`)}`} onClick={navigateToWarning}>前往異常與匯入警示中心</button></div>)}</section>
                  <section data-surface-id="imports.hcm-results.replays"><h3>已存在相同資料</h3>{result.replays.length === 0 ? <p>本批次沒有相同資料。</p> : result.replays.map((row) => <div key={row.source_row} className="import-result-row"><strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong><span>未列為新增</span></div>)}</section>
                </div>
              )}
            </article>
          ))}
        </section>
      </div>
    </div>
  );
};

export default DataImportPage;
