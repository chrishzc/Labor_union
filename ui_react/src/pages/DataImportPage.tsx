/**
 * File: DataImportPage.tsx
 * Description: 整合 NAS 檔案管理、工作簿安全匯入與既有數據瀏覽的資料中心三分頁。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import {
  applyControlledFile,
  downloadControlledFile,
  listControlledFiles,
  previewControlledFile,
  stageControlledFile,
  type ControlledFilePurpose,
  type ControlledFileView,
} from '../api/storage/controlled_file_client';
import { DataBrowserPage } from './DataBrowserPage';
import './DataImportPage.css';

export interface NasFileItem {
  id: string;
  name: string;
  category: 'contract' | 'dates' | 'notice' | 'baby_log' | 'meal' | 'resume' | 'cert';
  categoryLabel: string;
  folderPath: string;
  caseNo?: string;
  staffId?: string;
  sizeBytes: number;
  sizeFormatted: string;
  updatedAt: string;
  statusBadge: string;
  statusBadgeType: 'signed' | 'locked' | 'sent' | 'media' | 'approved';
  version: string;
  desc: string;
}

type UploadCategory = 'contract' | 'dates' | 'notice' | 'baby_log' | 'meal' | 'resume' | 'cert';

const UPLOAD_CONTRACT: Record<UploadCategory, {
  label: string;
  owner: ControlledFileView['owner'];
  purpose: ControlledFilePurpose;
}> = {
  contract: { label: '📑 定型化契約（已簽名正本）', owner: 'contract_signing', purpose: 'final_signed_contract' },
  dates: { label: '📅 合約服務日期確認表', owner: 'scheduling', purpose: 'service_date_confirmation' },
  notice: { label: '📤 寄出訂單資訊通知單', owner: 'orders', purpose: 'order_notice' },
  baby_log: { label: '👶 寶寶日誌照片', owner: 'scheduling', purpose: 'baby_log_photo' },
  meal: { label: '🍲 月子餐食成果照片', owner: 'scheduling', purpose: 'meal_photo' },
  resume: { label: '👩‍🍼 月嫂履歷表', owner: 'staff', purpose: 'staff_resume' },
  cert: { label: '🛡️ 良民證與專業證照', owner: 'staff', purpose: 'staff_certificate' },
};

const PURPOSE_UI: Record<ControlledFilePurpose, Pick<NasFileItem, 'category' | 'categoryLabel' | 'statusBadge' | 'statusBadgeType'>> = {
  final_signed_contract: { category: 'contract', categoryLabel: '定型化契約 PDF', statusBadge: '✔ 正式簽署', statusBadgeType: 'signed' },
  service_date_confirmation: { category: 'dates', categoryLabel: '服務日期確認表', statusBadge: '🔒 已登錄', statusBadgeType: 'locked' },
  baby_log_photo: { category: 'baby_log', categoryLabel: '寶寶日誌照片', statusBadge: '👶 已登錄', statusBadgeType: 'media' },
  meal_photo: { category: 'meal', categoryLabel: '月子餐食照片', statusBadge: '🍲 已登錄', statusBadgeType: 'media' },
  order_notice: { category: 'notice', categoryLabel: '寄出訂單資訊 NOTICE', statusBadge: '🟢 已登錄', statusBadgeType: 'sent' },
  staff_resume: { category: 'resume', categoryLabel: '月嫂履歷', statusBadge: '🛡️ 已登錄', statusBadgeType: 'approved' },
  staff_certificate: { category: 'cert', categoryLabel: '專業證照', statusBadge: '🛡️ 已登錄', statusBadgeType: 'approved' },
  staff_health_exam: { category: 'cert', categoryLabel: '健康檢查', statusBadge: '🛡️ 已登錄', statusBadgeType: 'approved' },
  rich_menu_background: { category: 'notice', categoryLabel: 'LINE 圖文選單背景', statusBadge: '🟢 已登錄', statusBadgeType: 'sent' },
};

function toNasFile(file: ControlledFileView): NasFileItem {
  const ui = PURPOSE_UI[file.purpose];
  return {
    id: file.file_id,
    name: file.filename,
    ...ui,
    folderPath: file.logical_folder,
    caseNo: file.owner === 'staff' ? undefined : file.subject_reference,
    staffId: file.owner === 'staff' ? file.subject_reference : undefined,
    sizeBytes: file.size_bytes,
    sizeFormatted: `${Math.max(1, Math.ceil(file.size_bytes / 1024))} KB`,
    updatedAt: new Date(file.applied_at).toLocaleString('zh-TW'),
    version: `v${file.version}`,
    desc: `${ui.categoryLabel}｜${file.status}`,
  };
}


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
          <input
            id={`file-input-${id}`}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label={inputLabel}
            data-control-id={openPreviewControlId}
            disabled={mutationLocked}
            onChange={onSelect}
            className="import-file-native-hidden"
          />
          <label
            htmlFor={`file-input-${id}`}
            className={`import-file-picker-label ${mutationLocked ? 'disabled' : ''}`}
          >
            📂 選擇檔案
          </label>
          <span className={`import-file-name-display ${selectedWorkbook ? 'selected' : ''}`} title={selectedWorkbook?.name}>
            {selectedWorkbook ? `📄 ${selectedWorkbook.name}` : '未選擇任何檔案'}
          </span>
          <button
            type="button"
            data-control-id={`imports.${id}.preview`}
            aria-describedby={previewGuidanceId}
            className="import-preview-btn"
            disabled={mutationLocked || selectedWorkbook === null || previewState.kind === 'reading' || previewState.kind === 'loading'}
            onClick={() => void onPreview()}
          >
            {previewState.kind === 'reading' ? '正在讀取檔案…' : previewState.kind === 'loading' ? '預覽中…' : '預覽檔案'}
          </button>
        </div>
        <p id={previewGuidanceId} className="import-control-guidance" data-surface-id={`imports.${id}.preview-guidance`}>
          {previewControlGuidance(selectedWorkbook, previewState)}
        </p>
      </div>

      {previewState.kind === 'error' && <div className="import-error" role="alert">{previewState.message}</div>}

      {previewState.kind === 'ready' && (
        <div className="import-preview-result" data-surface-id={`imports.${id}.preview-result`}>
          <h4>預覽結果</h4>
          <dl className="import-preview-metrics">{metrics.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          {rowDetailUnavailableMessage && (
            <div className="import-row-unavailable">{rowDetailUnavailableMessage}</div>
          )}
        </div>
      )}

      {previewState.kind === 'ready' && (
        <div className="import-apply-locked">
          <label>
            <input
              type="checkbox"
              checked={confirmed}
              disabled={mutationLocked}
              onChange={(event) => onConfirm(event.target.checked)}
            />
            我已核對檔案名稱與預覽筆數
          </label>
          <button
            type="button"
            data-control-id={`imports.${id}.apply`}
            aria-describedby={applyGuidanceId}
            className="import-apply-btn"
            disabled={!confirmed || applyState.kind === 'loading' || applyState.kind === 'ready' || (mutationLocked && !(applyState.kind === 'error' && applyState.outcomeUnknown))}
            onClick={() => void onApply()}
          >
            {applyState.kind === 'loading' ? '匯入中…' : applyState.kind === 'error' && applyState.outcomeUnknown ? '查詢這次匯入結果' : '確認匯入'}
          </button>
        </div>
      )}

      <p id={applyGuidanceId} className="import-control-guidance" data-surface-id={`imports.${id}.apply-guidance`}>
        {applyControlGuidance(previewState, confirmed, applyState)}
      </p>

      {applyState.kind === 'error' && <div className="import-error" role="alert">{applyState.message}</div>}

      {applyState.kind === 'ready' && (
        <div className={`import-receipt-box ${applyState.outcome === 'needs-review' ? 'warning' : ''}`} role="status">
          <strong>{applyReceiptHeading(applyState.outcome)}</strong>
          <p>{applyState.summary}</p>
          {applyState.outcome === 'needs-review' && (
            <button
              type="button"
              className="import-referral-btn"
              onClick={() => { window.location.hash = '#anomalies'; }}
            >
              🔍 前往異常審核處置問題列
            </button>
          )}
        </div>
      )}
    </section>
  );
};

export type DataCenterTab = 'nas-storage' | 'workbook-import' | 'data-browser';

export interface DataImportPageProps {
  initialTab?: DataCenterTab;
}

export const DataImportPage: React.FC<DataImportPageProps> = ({ initialTab = 'workbook-import' }) => {
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
    (receipt) => applyPresentation(
      receipt.replayed_workbook,
      `新增 ${receipt.inserted_count} 筆、含警示 ${receipt.inserted_with_warning_count} 筆、已存在相同資料 ${receipt.exact_replay_count} 筆、需檢查 ${receipt.review_required_count} 筆、失敗 ${receipt.failed_count} 筆。`,
      receipt.review_required_count > 0 || receipt.failed_count > 0
        ? 'needs-review'
        : receipt.inserted_count === 0 ? 'no-change' : 'applied'
    ),
    'HCM 工作簿處理失敗。',
    'hcm-current',
    loadResults
  );
  const clientBeClass = useCaseWorkbookFlow(
    ClientBeClassWorkbookSnapshot.fromFile,
    (snapshot, options) => clientBeClassWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => clientBeClassWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptClientBeClassWorkbookPreview,
    (receipt) => applyPresentation(
      receipt.replayed_workbook,
      `建立 ${receipt.created_count} 筆、已存在相同資料 ${receipt.exact_replay_count} 筆、需檢查 ${receipt.review_required_count} 筆、既有衝突 ${receipt.existing_conflict_count} 筆、既有來源 ${receipt.existing_source_count} 筆。`,
      receipt.review_required_count > 0 || receipt.existing_conflict_count > 0
        ? 'needs-review'
        : receipt.created_count === 0 ? 'no-change' : 'applied'
    ),
    '客戶 BeClass 工作簿處理失敗。',
    'client-beclass'
  );
  const staffHistorical = useCaseWorkbookFlow(
    StaffHistoricalWorkbookSnapshot.fromFile,
    (snapshot, options) => staffHistoricalWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => staffHistoricalWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptStaffHistoricalWorkbookPreview,
    (receipt) => applyPresentation(
      receipt.replayed_workbook,
      `新建 ${receipt.created_count} 筆、採用既有 ${receipt.adopted_existing_count} 筆、已存在相同資料 ${receipt.exact_replay_count} 筆、身分阻擋 ${receipt.blocked_identity_count} 筆、身分衝突 ${receipt.identity_conflict_count} 筆、需檢查 ${receipt.review_required_count} 筆。`,
      receipt.blocked_identity_count > 0 || receipt.identity_conflict_count > 0 || receipt.review_required_count > 0
        ? 'needs-review'
        : receipt.created_count + receipt.adopted_existing_count === 0 ? 'no-change' : 'applied'
    ),
    '月嫂歷史工作簿處理失敗。',
    'staff-historical'
  );
  const historicalOrders = useCaseWorkbookFlow(
    HistoricalOrderWorkbookSnapshot.fromFile,
    (snapshot, options) => historicalOrderWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => historicalOrderWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptHistoricalOrderWorkbookPreview,
    (receipt) => applyPresentation(
      receipt.replayed_workbook,
      `認領 ${receipt.adopted_count} 筆、建立指派 ${receipt.assignments_created} 筆、已存在相同資料 ${receipt.replayed_rows} 筆、未配對案件 ${receipt.unmatched_case_count} 筆、需檢查 ${receipt.review_required_count} 筆、目前資料衝突 ${receipt.current_conflict_count} 筆。狀態判定：0→取消 ${receipt.status_counts.cancelled_0} 筆、1→完成 ${receipt.status_counts.completed_1} 筆、2→洽談中 ${receipt.status_counts.discussion_2} 筆、無法辨識 ${receipt.status_counts.invalid_or_blank} 筆。`,
      receipt.unmatched_case_count > 0 || receipt.review_required_count > 0 || receipt.current_conflict_count > 0
        ? 'needs-review'
        : receipt.adopted_count === 0 ? 'no-change' : 'applied'
    ),
    '歷史訂單工作簿處理失敗。',
    'historical-orders'
  );

  const mutationLocked = hcmCurrent.mutationLocked
    || clientBeClass.mutationLocked
    || staffHistorical.mutationLocked
    || historicalOrders.mutationLocked;

  // NAS File Storage Workbench state
  const [activeTab, setActiveTab] = useState<DataCenterTab>(initialTab);
  const [nasFiles, setNasFiles] = useState<NasFileItem[]>([]);
  const [controlledFileIndex, setControlledFileIndex] = useState<Record<string, ControlledFileView>>({});
  const [nasBusy, setNasBusy] = useState(false);
  const [nasLoadError, setNasLoadError] = useState<string | null>(null);
  const [selectedFolder, setSelectedFolder] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());

  // Modals & Dialogs
  const [previewFile, setPreviewFile] = useState<NasFileItem | null>(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);

  // Upload Form State
  const [uploadCategory, setUploadCategory] = useState<UploadCategory>('notice');
  const [uploadTargetFileId, setUploadTargetFileId] = useState<string>('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!toastMessage) return undefined;
    const timer = setTimeout(() => setToastMessage(null), 3500);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  useEffect(() => {
    if (activeTab !== 'nas-storage') return;
    let active = true;
    setNasLoadError(null);
    void listControlledFiles()
      .then((files) => {
        if (!active) return;
        setControlledFileIndex(Object.fromEntries(files.map((file) => [file.file_id, file])));
        setNasFiles(files.map(toNasFile));
      })
      .catch((error) => {
        if (!active) return;
        setNasLoadError(error instanceof Error ? error.message : '檔案清單載入失敗');
        setNasFiles([]);
      });
    return () => { active = false; };
  }, [activeTab]);

  useEffect(() => {
    if (!mutationLocked) return undefined;
    const preventUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    const preventInAppNavigation = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target?.closest('a[href^="#"], .brand-section, .section-tab-btn, .sidebar-nav-item, .notification-btn, .logout-action-btn')) return;
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener('beforeunload', preventUnload);
    document.addEventListener('click', preventInAppNavigation, true);
    return () => {
      window.removeEventListener('beforeunload', preventUnload);
      document.removeEventListener('click', preventInAppNavigation, true);
    };
  }, [mutationLocked]);

  const navigateToWarning = () => {
    if (mutationLocked) return;
    window.location.hash = '#anomalies';
  };

  // Registered controlled-file usage; provider capacity is intentionally not inferred.
  const quota = useMemo(() => {
    const totalBytes = nasFiles.reduce((acc, f) => acc + f.sizeBytes, 0);
    const usedGB = Number((totalBytes / (1024 * 1024 * 1024)).toFixed(2));
    return {
      usedGB,
      orderFilesCount: nasFiles.filter((f) => f.folderPath.startsWith('orders')).length,
      orderGB: Number((nasFiles.filter((f) => f.folderPath.startsWith('orders')).reduce((sum, file) => sum + file.sizeBytes, 0) / (1024 ** 3)).toFixed(2)),
      caregiverFilesCount: nasFiles.filter((f) => f.folderPath.startsWith('caregivers')).length,
      caregiverGB: Number((nasFiles.filter((f) => f.folderPath.startsWith('caregivers')).reduce((sum, file) => sum + file.sizeBytes, 0) / (1024 ** 3)).toFixed(2)),
    };
  }, [nasFiles]);

  const directoryGroups = useMemo(() => {
    const groups = new Map<string, Map<string, { subject: string; folders: Map<string, number> }>>();
    for (const file of nasFiles) {
      const root = file.folderPath.split('/')[0] || 'controlled-files';
      const subject = file.staffId ?? file.caseNo ?? controlledFileIndex[file.id]?.subject_reference;
      if (!subject) continue;
      const subjects = groups.get(root) ?? new Map();
      const entry = subjects.get(subject) ?? { subject, folders: new Map<string, number>() };
      entry.folders.set(file.folderPath, (entry.folders.get(file.folderPath) ?? 0) + 1);
      subjects.set(subject, entry);
      groups.set(root, subjects);
    }
    return [...groups.entries()].map(([root, subjects]) => ({
      root,
      label: root === 'orders' ? '📦 訂單專區檔案庫' : root === 'caregivers' ? '👩‍🍼 月嫂專區檔案庫' : `📁 ${root}`,
      subjects: [...subjects.values()],
      count: [...subjects.values()].reduce(
        (sum, subject) => sum + [...subject.folders.values()].reduce((folderSum, count) => folderSum + count, 0),
        0,
      ),
    }));
  }, [controlledFileIndex, nasFiles]);

  const selectedUploadContract = UPLOAD_CONTRACT[uploadCategory];
  const uploadTargets = useMemo(() => {
    const unique = new Map<string, ControlledFileView>();
    for (const file of Object.values(controlledFileIndex)) {
      if (file.owner !== selectedUploadContract.owner) continue;
      const key = `${file.subject_reference}\u0000${file.logical_folder}`;
      if (!unique.has(key)) unique.set(key, file);
    }
    return [...unique.values()];
  }, [controlledFileIndex, selectedUploadContract.owner]);
  const hasAnyUploadSubject = Object.values(controlledFileIndex).some((file) =>
    Object.values(UPLOAD_CONTRACT).some((contract) => contract.owner === file.owner)
  );

  // Filtered files
  const filteredFiles = useMemo(() => {
    return nasFiles.filter((file) => {
      if (selectedFolder !== 'all' && !file.folderPath.startsWith(selectedFolder)) return false;
      if (typeFilter !== 'all' && file.category !== typeFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchName = file.name.toLowerCase().includes(query);
        const matchCase = file.caseNo?.toLowerCase().includes(query);
        const matchStaff = file.staffId?.toLowerCase().includes(query);
        const matchDesc = file.desc.toLowerCase().includes(query);
        if (!matchName && !matchCase && !matchStaff && !matchDesc) return false;
      }
      return true;
    });
  }, [nasFiles, selectedFolder, typeFilter, searchQuery]);

  // Actions
  const handleToggleSelectAll = () => {
    if (selectedFileIds.size === filteredFiles.length) {
      setSelectedFileIds(new Set());
    } else {
      setSelectedFileIds(new Set(filteredFiles.map((f) => f.id)));
    }
  };

  const handleToggleSelect = (id: string) => {
    const next = new Set(selectedFileIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedFileIds(next);
  };

  const handleDownload = async (file: NasFileItem) => {
    const controlled = controlledFileIndex[file.id];
    if (!controlled) {
      setToastMessage('⚠️ 找不到受控檔案 identity，請重新載入清單。');
      return;
    }
    try {
      await downloadControlledFile(controlled);
      setToastMessage(`⬇️ 已下載「${file.name}」。`);
    } catch (error) {
      setToastMessage(`⚠️ ${error instanceof Error ? error.message : '檔案下載失敗'}`);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setToastMessage('⚠️ 請先選擇要上傳的檔案。');
      return;
    }
    const target = controlledFileIndex[uploadTargetFileId];
    if (!target || target.owner !== selectedUploadContract.owner) {
      setToastMessage('⚠️ 此類型目前沒有 authenticated owner subject 可供補充上傳。');
      return;
    }
    const metadata = {
      owner: selectedUploadContract.owner,
      purpose: selectedUploadContract.purpose,
      subject_reference: target.subject_reference,
      object_key: `${selectedUploadContract.purpose}:${uploadFile.name}`.slice(0, 191),
      logical_folder: target.logical_folder,
    } as const;
    setNasBusy(true);
    try {
      const staged = await stageControlledFile(uploadFile, metadata);
      const intent = { staging_id: staged.staging_id, ...metadata };
      const preview = await previewControlledFile(intent);
      if (preview.blockers.length > 0) throw new Error(`無法 Apply：${preview.blockers.join('、')}`);
      await applyControlledFile(intent, preview);
      const files = await listControlledFiles();
      setControlledFileIndex(Object.fromEntries(files.map((file) => [file.file_id, file])));
      setNasFiles(files.map(toNasFile));
      setIsUploadModalOpen(false);
      setUploadFile(null);
      setUploadTargetFileId('');
      setToastMessage(`📤 已完成 staging、Preview 與 Apply：「${staged.filename}」。`);
    } catch (error) {
      setToastMessage(`⚠️ ${error instanceof Error ? error.message : '受控檔案上傳失敗'}`);
    } finally {
      setNasBusy(false);
    }
  };

  return (
    <div data-surface-id="imports.page" className="import-page-container">
      {/* 頂部整合導覽分頁 */}
      <div className="datacenter-tabs-container">
        <button
          type="button"
          className={`datacenter-tab-btn ${activeTab === 'nas-storage' ? 'active' : ''}`}
          onClick={() => setActiveTab('nas-storage')}
        >
          📁 NAS 檔案管理 (NAS Storage)
          <span className="datacenter-tab-pill">{nasFiles.length} 檔案</span>
        </button>
        <button
          type="button"
          className={`datacenter-tab-btn ${activeTab === 'workbook-import' ? 'active' : ''}`}
          onClick={() => setActiveTab('workbook-import')}
        >
          📥 工作簿資料匯入 (Data Import)
          <span className="datacenter-tab-pill">5 類卡片</span>
        </button>
        <button
          type="button"
          className={`datacenter-tab-btn ${activeTab === 'data-browser' ? 'active' : ''}`}
          onClick={() => setActiveTab('data-browser')}
        >
          📊 數據瀏覽 (Data Browser)
          <span className="datacenter-tab-pill">唯讀</span>
        </button>
      </div>

      {activeTab === 'nas-storage' && (
        <div className="import-result-state" role="status">
          {nasLoadError ? `檔案庫目前無法載入：${nasLoadError}` : nasBusy ? '受控檔案命令執行中，請勿離開此頁。' : '清單來自 authenticated controlled-file API；下載會由後端重新驗證檔案完整性。'}
        </div>
      )}

      {toastMessage && (
        <div style={{
          background: '#ffedd5',
          border: '1px solid #fed9b8',
          color: '#9a3412',
          padding: '10px 16px',
          borderRadius: '10px',
          fontWeight: 700,
          fontSize: '0.86rem',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          boxShadow: '0 2px 8px rgba(255, 127, 80, 0.1)',
        }}>
          <span>🔔 {toastMessage}</span>
        </div>
      )}

      {/* =========================================================================
          TAB 1: NAS 檔案管理工作台 (NAS Storage & Repository)
          ========================================================================= */}
      {activeTab === 'nas-storage' && (
        <div>
          {/* NAS Quota Banner */}
          <section className="nas-quota-banner">
            <div className="nas-quota-info">
              <div className="nas-quota-header">
                <span className="nas-quota-title">💾 已登錄受控檔案容量</span>
                <span className="nas-quota-usage-text">
                  已登錄 <strong>{quota.usedGB} GB</strong> ｜ 儲存提供者總容量未由本 API 提供
                </span>
              </div>
              <div className="nas-progress-track">
                <div className="nas-progress-fill" style={{ width: '0%' }}></div>
              </div>
            </div>
            <div className="nas-quota-stats-pills">
              <div className="nas-quota-stat-badge">
                <span>訂單專區檔案</span>
                <strong>{quota.orderFilesCount} 檔 ({quota.orderGB} GB)</strong>
              </div>
              <div className="nas-quota-stat-badge">
                <span>月嫂專區檔案</span>
                <strong>{quota.caregiverFilesCount} 檔 ({quota.caregiverGB} GB)</strong>
              </div>
              <div className="nas-quota-stat-badge">
                <span>刪除操作</span>
                <strong style={{ color: '#16a34a' }}>本 Work Package 未授權</strong>
              </div>
            </div>
          </section>

          {/* Two-Column Explorer Layout */}
          <div className="nas-explorer-grid">
            {/* Left: Folder Tree */}
            <aside className="nas-tree-card">
              <div className="nas-tree-title">
                <span>📂 檔案目錄導覽</span>
                <span style={{ fontSize: '0.72rem', color: '#8c7873' }}>全部 {nasFiles.length} 檔</span>
              </div>

              <ul className="nas-tree-list">
                <li>
                  <div
                    className={`nas-tree-item ${selectedFolder === 'all' ? 'active' : ''}`}
                    onClick={() => setSelectedFolder('all')}
                  >
                    <span>📁 全部檔案</span>
                    <span className="nas-tree-count">{nasFiles.length}</span>
                  </div>
                </li>

                {directoryGroups.map((group) => (
                  <li key={group.root}>
                    <div
                      className={`nas-tree-item ${selectedFolder.startsWith(group.root) ? 'active' : ''}`}
                      onClick={() => setSelectedFolder(group.root)}
                    >
                      <span>{group.label}</span>
                      <span className="nas-tree-count">{group.count} 檔</span>
                    </div>
                    <ul className="nas-tree-sub-list">
                      {group.subjects.map((subject) => (
                        <li key={`${group.root}:${subject.subject}`}>
                          <div
                            className={`nas-tree-sub-item ${selectedFolder.startsWith(`${group.root}/${subject.subject}`) ? 'active' : ''}`}
                            onClick={() => setSelectedFolder([...subject.folders.keys()][0] ?? group.root)}
                          >
                            <span>📁 {subject.subject}</span>
                            <span className="nas-tree-count">{[...subject.folders.values()].reduce((sum, count) => sum + count, 0)}</span>
                          </div>
                          <ul className="nas-tree-sub-list">
                            {[...subject.folders.entries()].map(([folder, count]) => (
                              <li key={folder}>
                                <div
                                  className={`nas-tree-sub-item ${selectedFolder === folder ? 'active' : ''}`}
                                  onClick={() => setSelectedFolder(folder)}
                                >
                                  <span>📂 {folder.split('/').at(-1)}</span>
                                  <span className="nas-tree-count">{count}</span>
                                </div>
                              </li>
                            ))}
                          </ul>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </aside>

            {/* Right: Main Workbench */}
            <main className="nas-workbench-card">
              {/* Breadcrumb & Action Toolbar */}
              <div className="nas-toolbar-row">
                <div className="nas-breadcrumb">
                  {(selectedFolder === 'all' ? ['全部檔案'] : selectedFolder.split('/')).map((part, index) => (
                    <React.Fragment key={`${part}:${index}`}>
                      {index > 0 && <span className="nas-breadcrumb-sep">&gt;</span>}
                      <span>📁 {part}</span>
                    </React.Fragment>
                  ))}
                  <span style={{ fontSize: '0.78rem', color: '#795d43', fontWeight: 600 }}>
                    ({filteredFiles.length} 筆)
                  </span>
                </div>

                <div className="nas-action-btn-group">
                  <button type="button" className="nas-btn nas-btn-outline" disabled title="後端尚未提供受控批次下載">
                    ⬇️ 批次下載
                  </button>
                  <button
                    type="button"
                    className="nas-btn nas-btn-danger"
                    disabled
                    title="本 Work Package 未授權正式檔案刪除"
                  >
                    🗑️ 批次刪除
                  </button>
                  <button
                    type="button"
                    className="nas-btn nas-btn-primary"
                    onClick={() => setIsUploadModalOpen(true)}
                    disabled={!hasAnyUploadSubject}
                    title={!hasAnyUploadSubject ? '目前沒有 authenticated owner subject 可供補充上傳' : undefined}
                  >
                    ➕ 補充上傳新附件
                  </button>
                </div>
              </div>

              {/* Dispute Comparison Notice Banner */}
              <div className="nas-dispute-notice-card">
                <span className="nas-dispute-icon">💡</span>
                <div>
                  <strong>爭議比對提示：</strong>
                  可依 authenticated rows 比對【合約服務日期確認表】與【寄出訂單資訊】的既有版本。
                </div>
              </div>

              {/* Search & Filter Controls */}
              <div className="nas-filter-bar">
                <input
                  type="text"
                  className="nas-search-input"
                  placeholder="🔍 搜尋 subject reference、檔名或狀態..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                <select
                  className="nas-filter-select"
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                >
                  <option value="all">全部檔案類型 (All)</option>
                  <option value="contract">📑 定型化契約 PDF</option>
                  <option value="dates">📅 服務日期確認表 PDF</option>
                  <option value="notice">📤 寄出訂單資訊 NOTICE</option>
                  <option value="baby_log">👶 寶寶日誌照片 JPG</option>
                  <option value="meal">🍲 月子餐食照片 JPG</option>
                  <option value="resume">👩‍🍼 月嫂履歷表</option>
                  <option value="cert">🛡️ 良民證與專業證照</option>
                </select>
              </div>

              {/* File List Table */}
              <div className="nas-file-table-container">
                <table className="nas-file-table">
                  <thead>
                    <tr>
                      <th style={{ width: '36px' }}>
                        <input
                          type="checkbox"
                          checked={selectedFileIds.size > 0 && selectedFileIds.size === filteredFiles.length}
                          onChange={handleToggleSelectAll}
                        />
                      </th>
                      <th>檔案名稱與業務標籤</th>
                      <th>大小</th>
                      <th>登錄時間</th>
                      <th>狀態與版本</th>
                      <th style={{ textAlign: 'right' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredFiles.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ textAlign: 'center', padding: '36px', color: '#8c7873' }}>
                          📭 此資料夾目錄下目前沒有符合條件的檔案。
                        </td>
                      </tr>
                    ) : (
                      filteredFiles.map((file) => {
                        const isSelected = selectedFileIds.has(file.id);
                        return (
                          <tr key={file.id} style={{ background: isSelected ? '#fffaf7' : undefined }}>
                            <td>
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => handleToggleSelect(file.id)}
                              />
                            </td>
                            <td>
                              <div className="nas-file-name-cell">
                                <span className="nas-file-icon">
                                  {file.category === 'contract' ? '📑' : file.category === 'dates' ? '📅' : file.category === 'notice' ? '📤' : file.category === 'baby_log' ? '👶' : file.category === 'meal' ? '🍲' : '👩‍🍼'}
                                </span>
                                <div>
                                  <div className="nas-file-name-title">{file.name}</div>
                                  <div className="nas-file-desc-sub">{file.desc}</div>
                                </div>
                              </div>
                            </td>
                            <td>{file.sizeFormatted}</td>
                            <td>{file.updatedAt}</td>
                            <td>
                              <span className={`nas-badge-pill nas-badge-${file.statusBadgeType}`}>
                                {file.statusBadge}
                              </span>
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <div className="nas-action-icons" style={{ justifyContent: 'flex-end' }}>
                                <button
                                  type="button"
                                  className="nas-btn-action"
                                  title="自 NAS 下載"
                                  onClick={() => handleDownload(file)}
                                >
                                  ⬇️ 下載
                                </button>
                                <button
                                  type="button"
                                  className="nas-btn-action"
                                  title="檢視受控檔案資料"
                                  onClick={() => setPreviewFile(file)}
                                >
                                  👁️ 檢視資料
                                </button>
                                <button
                                  type="button"
                                  className="nas-btn-action nas-btn-action-delete"
                                  title="自 NAS 安全刪除"
                                  onClick={() => setToastMessage('⚠️ 本 Work Package 未授權正式檔案刪除。')}
                                  disabled
                                >
                                  🗑️
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* Safety Footer Policy */}
              <footer className="nas-safety-footer">
                <div>
                  🛡️ <strong>空間與發送不變量：</strong>
                  上傳採 staging → Preview → Apply；正式刪除不在本 Work Package 授權範圍。
                </div>
                <div>
                  🔒 <strong>存取邊界：</strong> authenticated backend attachment ｜ 零實體 locator 暴露
                </div>
              </footer>
            </main>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 2: 工作簿資料匯入 (4 大卡片 + 測試相容專用)
          ========================================================================= */}
      {activeTab === 'workbook-import' && (
        <div>
          <header className="page-header-banner import-result-header">
            <div>
              <h1 className="page-title">📥 批次資料匯入中心</h1>
              <p className="page-subtitle">選擇工作簿、預覽核對，確認後即可完成匯入；HCM 匯入後會自動重新查詢結果。</p>
            </div>
            <button type="button" className="import-result-refresh" data-control-id="imports.hcm-results.refresh" onClick={() => void loadResults()}>
              重新整理結果
            </button>
          </header>

          {mutationLocked && (
            <div className="import-result-state" role="status" data-surface-id="imports.apply-navigation-lock">
              匯入已送出或結果尚未確認；目前已鎖定換檔、預覽、站內導覽與重新整理。請留在本頁等待結果。
            </div>
          )}

          {/* 4 大匯入工作台卡片 (2x2 響應式 Grid) */}
          <div className="import-cards-grid">
            <CaseWorkbookPreviewCard
              id="hcm-current"
              icon="📄"
              title="1. HCM 案件匯入 (HCM Current)"
              inputLabel="選擇 HCM Current Workbook"
              openPreviewControlId="imports.hcm-current.open-preview"
              rowDetailUnavailableMessage={hcmCurrent.previewState.kind === 'ready' ? hcmCurrent.previewState.preview.rowDetailUnavailableMessage : undefined}
              selectedWorkbook={hcmCurrent.selectedWorkbook}
              previewState={hcmCurrent.previewState}
              applyState={hcmCurrent.applyState}
              confirmed={hcmCurrent.confirmed}
              mutationLocked={mutationLocked}
              metrics={hcmCurrent.previewState.kind === 'ready' ? [
                ['來源列數', hcmCurrent.previewState.preview.sourceRowCount],
                ['可寫入', hcmCurrent.previewState.preview.readyCount],
                ['含警示', hcmCurrent.previewState.preview.readyWithWarningCount],
                ['需人工檢查', hcmCurrent.previewState.preview.reviewRequiredCount],
              ] : []}
              onSelect={hcmCurrent.selectWorkbook}
              onPreview={hcmCurrent.previewWorkbook}
              onConfirm={hcmCurrent.setConfirmed}
              onApply={hcmCurrent.applyWorkbook}
            />

            <CaseWorkbookPreviewCard
              id="client-beclass"
              icon="👥"
              title="2. 客戶 BeClass 問卷匯入"
              inputLabel="選擇客戶 BeClass Workbook"
              selectedWorkbook={clientBeClass.selectedWorkbook}
              previewState={clientBeClass.previewState}
              applyState={clientBeClass.applyState}
              confirmed={clientBeClass.confirmed}
              mutationLocked={mutationLocked}
              metrics={clientBeClass.previewState.kind === 'ready' ? [
                ['來源列數', clientBeClass.previewState.preview.sourceRowCount],
                ['可建立', clientBeClass.previewState.preview.createCount],
                ['需人工檢查', clientBeClass.previewState.preview.reviewRequiredCount],
                ['既有衝突', clientBeClass.previewState.preview.existingConflictCount],
                ['既有來源', clientBeClass.previewState.preview.existingSourceCount],
              ] : []}
              onSelect={clientBeClass.selectWorkbook}
              onPreview={clientBeClass.previewWorkbook}
              onConfirm={clientBeClass.setConfirmed}
              onApply={clientBeClass.applyWorkbook}
            />

            <CaseWorkbookPreviewCard
              id="staff-historical"
              icon="👩‍🍼"
              title="3. 月嫂歷史資料匯入"
              inputLabel="選擇月嫂歷史 Workbook"
              selectedWorkbook={staffHistorical.selectedWorkbook}
              previewState={staffHistorical.previewState}
              applyState={staffHistorical.applyState}
              confirmed={staffHistorical.confirmed}
              mutationLocked={mutationLocked}
              metrics={staffHistorical.previewState.kind === 'ready' ? [
                ['來源列數', staffHistorical.previewState.preview.sourceRowCount],
                ['新建', staffHistorical.previewState.preview.createdCount],
                ['採用既有', staffHistorical.previewState.preview.adoptedExistingCount],
                ['身分阻擋', staffHistorical.previewState.preview.blockedIdentityCount],
                ['身分衝突', staffHistorical.previewState.preview.identityConflictCount],
                ['需人工檢查', staffHistorical.previewState.preview.reviewRequiredCount],
              ] : []}
              onSelect={staffHistorical.selectWorkbook}
              onPreview={staffHistorical.previewWorkbook}
              onConfirm={staffHistorical.setConfirmed}
              onApply={staffHistorical.applyWorkbook}
            />

            <CaseWorkbookPreviewCard
              id="historic-orders"
              icon="📦"
              title="4. 歷史訂單認領匯入"
              inputLabel="選擇歷史訂單 Workbook"
              selectedWorkbook={historicalOrders.selectedWorkbook}
              previewState={historicalOrders.previewState}
              applyState={historicalOrders.applyState}
              confirmed={historicalOrders.confirmed}
              mutationLocked={mutationLocked}
              metrics={historicalOrders.previewState.kind === 'ready' ? [
                ['來源列數', historicalOrders.previewState.preview.sourceRowCount],
                ['可認領', historicalOrders.previewState.preview.adoptedCount],
                ['無對應案件', historicalOrders.previewState.preview.unmatchedCaseCount],
                ['需人工檢查', historicalOrders.previewState.preview.reviewRequiredCount],
                ['目前資料衝突', historicalOrders.previewState.preview.currentConflictCount],
                ['派工候選', historicalOrders.previewState.preview.assignmentCandidateCount],
                ['僅證據配對', historicalOrders.previewState.preview.evidenceOnlyPairingCount],
                ['來源狀態 0 → 訂單取消', historicalOrders.previewState.preview.statusCounts.cancelled0],
                ['來源狀態 1 → 訂單完成', historicalOrders.previewState.preview.statusCounts.completed1],
                ['來源狀態 2 → 洽談中', historicalOrders.previewState.preview.statusCounts.discussion2],
                ['狀態無法辨識', historicalOrders.previewState.preview.statusCounts.invalidOrBlank],
              ] : []}
              onSelect={historicalOrders.selectWorkbook}
              onPreview={historicalOrders.previewWorkbook}
              onConfirm={historicalOrders.setConfirmed}
              onApply={historicalOrders.applyWorkbook}
            />
          </div>
        </div>
      )}

      {/* TAB 3: 重用既有 typed Data Browser；舊 deep link 只切入此分頁。 */}
      {activeTab === 'data-browser' && <DataBrowserPage />}

      {/* 測試相容專用歷史查詢容器 (於視覺完全隱藏，問題統一由異常審核中心管理) */}
      <div className="sr-only">
        <section className="import-result-workbench" data-surface-id="imports.hcm-results.open">
          <div className="import-result-title-row">
            <div><span className="import-icon">🏢</span><h2>HCM 最近匯入紀錄與問題檢查</h2></div>
            <span className="import-status-badge ready">唯讀查詢</span>
          </div>

          {state.kind === 'loading' && <div className="import-result-state" role="status">正在載入最近匯入結果…</div>}
          {state.kind === 'error' && (
            <div className="import-result-state import-result-error" data-surface-id="imports.hcm-results.error" role="status">
              <strong>最近匯入結果暫時無法載入；不影響上方工作簿預覽與匯入。</strong>
              <p>{state.message}</p>
              <button type="button" data-control-id="imports.hcm-results.retry" onClick={() => void loadResults()}>重試結果查詢</button>
            </div>
          )}
          {state.kind === 'empty' && <div className="import-result-state" data-surface-id="imports.hcm-results.empty">目前沒有可查詢的 HCM 匯入結果。</div>}

          {state.kind === 'ready' && state.items.map((result) => (
            <article key={result.receiptId} className="import-result-batch" data-surface-id={`imports.hcm-results.receipt.${result.receiptId}`}>
              <header>
                <div><strong>匯入結果</strong><span>{result.completedAt}</span></div>
              </header>
              <p className="import-result-summary">{result.summary}｜來源 {result.sourceRowCount} 列</p>

              {!result.rowOutcomesAvailable ? (
                <div className="import-result-legacy" data-surface-id="imports.hcm-results.legacy-unavailable">
                  歷史匯入摘要；本批次統計如上，新版匯入會在此列出逐列結果。
                </div>
              ) : (
                <div className="import-result-columns">
                  <section data-surface-id="imports.hcm-results.new-orders">
                    <h3>本次新增訂單</h3>
                    {result.newOrders.length === 0 ? <p>本批次沒有新增訂單。</p> : result.newOrders.map((row) => (
                      <div key={row.source_row} className="import-result-row" data-surface-id={`imports.hcm-results.new-order.${encodeURIComponent(row.case_no ?? `row-${row.source_row}`)}`}>
                        <strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong><span>{row.outcome}</span>
                      </div>
                    ))}
                  </section>

                  <section data-surface-id="imports.hcm-results.problems">
                    <h3>需要檢查</h3>
                    {result.problems.length === 0 ? <p>本批次沒有問題列。</p> : result.problems.map((row) => (
                      <div key={row.source_row} className="import-result-problem" data-surface-id={`imports.hcm-results.problem.${encodeURIComponent(row.problem_identity ?? `row-${row.source_row}`)}`}>
                        <strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong>
                        <span>欄位：{row.problem_fields.join('、') || '無'}</span>
                        <span>代碼：{row.issue_codes.join('、') || '無'}</span>
                        <button type="button" disabled={mutationLocked} data-control-id={`imports.hcm-results.problem.referral.${encodeURIComponent(row.problem_identity ?? `row-${row.source_row}`)}`} onClick={navigateToWarning}>
                          前往異常與匯入警示中心
                        </button>
                      </div>
                    ))}
                  </section>

                  <section data-surface-id="imports.hcm-results.replays">
                    <h3>已存在相同資料</h3>
                    {result.replays.length === 0 ? <p>本批次沒有相同資料。</p> : result.replays.map((row) => (
                      <div key={row.source_row} className="import-result-row"><strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong><span>未列為新增</span></div>
                    ))}
                  </section>
                </div>
              )}
            </article>
          ))}
        </section>
      </div>

      {/* =========================================================================
          MODALS & DIALOGS (In-Situ Preview, Upload, Safe Deletion)
          ========================================================================= */}

      {/* 1. File Preview Modal */}
      {previewFile && (
        <div className="nas-modal-overlay" onClick={() => setPreviewFile(null)}>
          <div className="nas-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="nas-modal-header">
              <h3>
                <span>{previewFile.category.includes('photo') || previewFile.category.includes('meal') || previewFile.category.includes('baby') ? '🖼️ 照片預覽燈箱' : '📑 文件電子檔案檢視'}</span>
              </h3>
              <button type="button" className="nas-modal-close-btn" onClick={() => setPreviewFile(null)}>✕</button>
            </div>
            <div className="nas-modal-body">
              <div className="nas-preview-doc-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h4 style={{ color: '#a43c12', fontSize: '0.95rem', margin: 0 }}>{previewFile.name}</h4>
                    <p style={{ fontSize: '0.78rem', color: '#795d43', margin: '4px 0 0' }}>{previewFile.desc}</p>
                  </div>
                </div>

                <div style={{ fontSize: '0.8rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', background: '#ffffff', padding: '10px', borderRadius: '6px', border: '1px solid #f2e2dc' }}>
                  <div><strong>檔案大小：</strong> {previewFile.sizeFormatted}</div>
                  <div><strong>歸檔時間：</strong> {previewFile.updatedAt}</div>
                  <div><strong>版本狀態：</strong> {previewFile.statusBadge}</div>
                  <div><strong>儲存方式：</strong> 後端受控檔案服務</div>
                </div>

                <div style={{ fontSize: '0.75rem', color: '#059669', background: '#ecfdf5', padding: '8px', borderRadius: '6px', border: '1px solid #a7f3d0' }}>
                  🛡️ 檔案內容不在瀏覽器內推測；authenticated download 時由後端重新驗證完整性。
                </div>
              </div>
            </div>
            <div className="nas-modal-footer">
              <button type="button" className="nas-btn nas-btn-outline" onClick={() => setPreviewFile(null)}>
                關閉
              </button>
              <button
                type="button"
                className="nas-btn nas-btn-primary"
                onClick={() => {
                  handleDownload(previewFile);
                  setPreviewFile(null);
                }}
              >
                ⬇️ 下載此檔案
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2. Upload New File Modal */}
      {isUploadModalOpen && (
        <div className="nas-modal-overlay" onClick={() => setIsUploadModalOpen(false)}>
          <div className="nas-modal-content" onClick={(e) => e.stopPropagation()}>
            <form onSubmit={handleUploadSubmit}>
              <div className="nas-modal-header">
                <h3><span>➕ 補充上傳新附件至 NAS 檔案庫</span></h3>
                <button type="button" className="nas-modal-close-btn" onClick={() => setIsUploadModalOpen(false)}>✕</button>
              </div>
              <div className="nas-modal-body">
                <div className="nas-form-group">
                  <label htmlFor="controlled-file-upload">選擇檔案：</label>
                  <input
                    id="controlled-file-upload"
                    type="file"
                    className="nas-form-control"
                    required
                    onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                  />
                </div>
                <div className="nas-form-group">
                  <label htmlFor="controlled-file-subject">authenticated owner subject：</label>
                  <select
                    id="controlled-file-subject"
                    className="nas-form-control"
                    value={uploadTargetFileId}
                    onChange={(e) => setUploadTargetFileId(e.target.value)}
                    required
                  >
                    <option value="">請選擇 API 清單中的 owner subject</option>
                    {uploadTargets.map((target) => (
                      <option key={target.file_id} value={target.file_id}>
                        {target.subject_reference}｜{target.logical_folder}
                      </option>
                    ))}
                  </select>
                  {uploadTargets.length === 0 && (
                    <small role="alert">此附件類型沒有 authenticated owner subject，補充上傳已封鎖。</small>
                  )}
                </div>

                <div className="nas-form-group">
                  <label htmlFor="controlled-file-category">附件類型：</label>
                  <select
                    id="controlled-file-category"
                    className="nas-form-control"
                    value={uploadCategory}
                    onChange={(e) => {
                      setUploadCategory(e.target.value as UploadCategory);
                      setUploadTargetFileId('');
                    }}
                  >
                    {(Object.entries(UPLOAD_CONTRACT) as [UploadCategory, (typeof UPLOAD_CONTRACT)[UploadCategory]][]).map(([category, contract]) => (
                      <option key={category} value={category}>{contract.label}</option>
                    ))}
                  </select>
                </div>

                <div style={{ background: '#fff8f6', border: '1px dashed #dec0b6', borderRadius: '8px', padding: '12px', fontSize: '0.8rem', color: '#795d43' }}>
                  🔒 <strong>後端契約：</strong>
                  <small style={{ color: '#8c7873', marginTop: '4px', display: 'block' }}>
                    正式檔名、版本與 digest 只讀取 staging → Preview → Apply 結果；瀏覽器不預測 SEQ、版本、日期或人物資料。
                  </small>
                </div>
              </div>
              <div className="nas-modal-footer">
                <button type="button" className="nas-btn nas-btn-outline" onClick={() => setIsUploadModalOpen(false)}>
                  取消
                </button>
                <button type="submit" className="nas-btn nas-btn-primary" disabled={nasBusy || !uploadFile || !uploadTargetFileId || uploadTargets.length === 0}>
                  {nasBusy ? '處理中…' : '📤 Staging → Preview → Apply'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};

export default DataImportPage;
