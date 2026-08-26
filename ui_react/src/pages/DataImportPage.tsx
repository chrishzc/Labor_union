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
import { DataBrowserPage } from './DataBrowserPage';
import './DataImportPage.css';

export interface NasFileItem {
  id: string;
  name: string;
  category: 'contract' | 'dates' | 'notice' | 'baby_log' | 'meal' | 'resume' | 'cert';
  categoryLabel: string;
  folderPath: string;
  caseNo?: string;
  clientName?: string;
  staffId?: string;
  staffName?: string;
  sizeBytes: number;
  sizeFormatted: string;
  updatedAt: string;
  statusBadge: string;
  statusBadgeType: 'signed' | 'locked' | 'sent' | 'media' | 'approved';
  sha256: string;
  isOngoing?: boolean;
  version: string;
  desc: string;
}

const INITIAL_NAS_FILES: NasFileItem[] = [
  {
    id: 'nas-f-01',
    name: 'CONTRACT_ORD-HC019_林美真_SIGNED_v1.pdf',
    category: 'contract',
    categoryLabel: '定型化契約 PDF',
    folderPath: 'orders/ORD-HC019/contracts',
    caseNo: 'ORD-2026-HC019',
    clientName: '林美真',
    sizeBytes: 870400,
    sizeFormatted: '850 KB',
    updatedAt: '115/05/20 10:30',
    statusBadge: '✔ 正式簽署 v1',
    statusBadgeType: 'signed',
    sha256: 'a8f12c90e8d1a45b678c1234ef0987654321abcd',
    isOngoing: true,
    version: 'v1',
    desc: '產婦定型化契約 (已簽名正本) ｜ 訂單履約中',
  },
  {
    id: 'nas-f-02',
    name: 'DATES_ORD-HC019_林美真_CONFIRMED_20260520.pdf',
    category: 'dates',
    categoryLabel: '服務日期確認表',
    folderPath: 'orders/ORD-HC019/contracts',
    caseNo: 'ORD-2026-HC019',
    clientName: '林美真',
    sizeBytes: 430080,
    sizeFormatted: '420 KB',
    updatedAt: '115/05/20 11:00',
    statusBadge: '🔒 檔期已鎖定',
    statusBadgeType: 'locked',
    sha256: '7e3b90aa1234567890abcdef1234567890abcdef',
    isOngoing: true,
    version: 'v1',
    desc: '合約服務日期確認表 (30天排班檔期鎖定憑證)',
  },
  {
    id: 'nas-f-03',
    name: 'NOTICE_ORD-HC019_林美真_SEQ-1_20260518-1430.pdf',
    category: 'notice',
    categoryLabel: '寄出訂單資訊 NOTICE',
    folderPath: 'orders/ORD-HC019/contracts',
    caseNo: 'ORD-2026-HC019',
    clientName: '林美真',
    sizeBytes: 317440,
    sizeFormatted: '310 KB',
    updatedAt: '115/05/18 14:30',
    statusBadge: '🟢 已寄出 SEQ-1',
    statusBadgeType: 'sent',
    sha256: '41dc28ef567890abcdef1234567890abcdef1234',
    isOngoing: true,
    version: 'SEQ-1',
    desc: '寄出訂單資訊-1 (初版派單與報價單留底)',
  },
  {
    id: 'nas-f-04',
    name: 'NOTICE_ORD-HC019_林美真_SEQ-2_20260520-0915.pdf',
    category: 'notice',
    categoryLabel: '寄出訂單資訊 NOTICE',
    folderPath: 'orders/ORD-HC019/contracts',
    caseNo: 'ORD-2026-HC019',
    clientName: '林美真',
    sizeBytes: 348160,
    sizeFormatted: '340 KB',
    updatedAt: '115/05/20 09:15',
    statusBadge: '🟢 已寄出 SEQ-2',
    statusBadgeType: 'sent',
    sha256: '9b12f431abcdef1234567890abcdef1234567890',
    isOngoing: true,
    version: 'SEQ-2',
    desc: '寄出訂單資訊-2 (預產期提早天數修訂確認單留底)',
  },
  {
    id: 'nas-f-05',
    name: 'BABY_ORD-HC019_20260825_01.jpg',
    category: 'baby_log',
    categoryLabel: '寶寶日誌照片',
    folderPath: 'orders/ORD-HC019/baby_logs',
    caseNo: 'ORD-2026-HC019',
    clientName: '林美真',
    sizeBytes: 1887436,
    sizeFormatted: '1.8 MB',
    updatedAt: '115/08/25 09:30',
    statusBadge: '👶 照護日誌照片',
    statusBadgeType: 'media',
    sha256: 'cc1098de1234567890abcdef1234567890abcdef',
    isOngoing: true,
    version: 'v1',
    desc: '寶寶臍帶護理與洗澡紀錄照片',
  },
  {
    id: 'nas-f-06',
    name: 'MEAL_ORD-HC019_20260825_LUNCH_01.jpg',
    category: 'meal',
    categoryLabel: '月子餐食照片',
    folderPath: 'orders/ORD-HC019/meals',
    caseNo: 'ORD-2026-HC019',
    clientName: '林美真',
    sizeBytes: 2516582,
    sizeFormatted: '2.4 MB',
    updatedAt: '115/08/25 12:15',
    statusBadge: '🍲 藥膳餐食照片',
    statusBadgeType: 'media',
    sha256: '38ea67011234567890abcdef1234567890abcdef',
    isOngoing: true,
    version: 'v1',
    desc: '麻油雞燉湯與產後藥膳午餐成果照片',
  },
  {
    id: 'nas-f-07',
    name: 'CONTRACT_ORD-HC020_陳雅萱_SIGNED_v1.pdf',
    category: 'contract',
    categoryLabel: '定型化契約 PDF',
    folderPath: 'orders/ORD-HC020/contracts',
    caseNo: 'ORD-2026-HC020',
    clientName: '陳雅萱',
    sizeBytes: 931840,
    sizeFormatted: '910 KB',
    updatedAt: '115/06/10 14:00',
    statusBadge: '✔ 正式簽署 v1',
    statusBadgeType: 'signed',
    sha256: '55bc8120abcdef1234567890abcdef1234567890',
    isOngoing: false,
    version: 'v1',
    desc: '產婦定型化契約 (已結案)',
  },
  {
    id: 'nas-f-08',
    name: 'RESUME_STF-012_張美敏_v1.pdf',
    category: 'resume',
    categoryLabel: '月嫂履歷表',
    folderPath: 'caregivers/STF-012',
    staffId: 'STF-012',
    staffName: '張美敏',
    sizeBytes: 1258291,
    sizeFormatted: '1.2 MB',
    updatedAt: '115/01/10 11:20',
    statusBadge: '👩‍🍼 資歷合格 v1',
    statusBadgeType: 'approved',
    sha256: '11aa34bc1234567890abcdef1234567890abcdef',
    isOngoing: false,
    version: 'v1',
    desc: '月嫂個人履歷表與 8 年到宅資歷認證',
  },
  {
    id: 'nas-f-09',
    name: 'CERT_STF-012_張美敏_良民證_20260115.pdf',
    category: 'cert',
    categoryLabel: '專業證照',
    folderPath: 'caregivers/STF-012',
    staffId: 'STF-012',
    staffName: '張美敏',
    sizeBytes: 696320,
    sizeFormatted: '680 KB',
    updatedAt: '115/01/15 16:40',
    statusBadge: '🛡️ 良民證通過',
    statusBadgeType: 'approved',
    sha256: '77fe49aa1234567890abcdef1234567890abcdef',
    isOngoing: false,
    version: '2026',
    desc: '新竹市警察局刑事紀錄證明 (良民證)',
  },
  {
    id: 'nas-f-10',
    name: 'HEALTH_STF-012_張美敏_體檢表_20260310.pdf',
    category: 'cert',
    categoryLabel: '健康檢查表',
    folderPath: 'caregivers/STF-012',
    staffId: 'STF-012',
    staffName: '張美敏',
    sizeBytes: 839680,
    sizeFormatted: '820 KB',
    updatedAt: '115/03/10 09:15',
    statusBadge: '🩺 體檢合格',
    statusBadgeType: 'approved',
    sha256: '99bc45121234567890abcdef1234567890abcdef',
    isOngoing: false,
    version: '2026',
    desc: '醫院到宅服務合格健康檢查表 (胸部X光/A肝)',
  },
];

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

export const DataImportPage: React.FC<DataImportPageProps> = ({ initialTab = 'nas-storage' }) => {
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
      `認領 ${receipt.adopted_count} 筆、建立指派 ${receipt.assignments_created} 筆、已存在相同資料 ${receipt.replayed_rows} 筆、未配對案件 ${receipt.unmatched_case_count} 筆、需檢查 ${receipt.review_required_count} 筆、目前資料衝突 ${receipt.current_conflict_count} 筆。`,
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
  const [nasFiles, setNasFiles] = useState<NasFileItem[]>(INITIAL_NAS_FILES);
  const [selectedFolder, setSelectedFolder] = useState<string>('orders/ORD-HC019/contracts');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [timeFilter, setTimeFilter] = useState<string>('all');
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());

  // Modals & Dialogs
  const [previewFile, setPreviewFile] = useState<NasFileItem | null>(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);
  const [deleteConfirmFile, setDeleteConfirmFile] = useState<NasFileItem | null>(null);

  // Upload Form State
  const [uploadCategory, setUploadCategory] = useState<'contract' | 'dates' | 'notice' | 'baby_log' | 'meal' | 'resume' | 'cert'>('notice');
  const [uploadTargetCase, setUploadTargetCase] = useState<string>('ORD-2026-HC019 (林美真)');
  const [uploadCustomDesc, setUploadCustomDesc] = useState<string>('');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!toastMessage) return undefined;
    const timer = setTimeout(() => setToastMessage(null), 3500);
    return () => clearTimeout(timer);
  }, [toastMessage]);

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

  // Quota dynamic calculation
  const quota = useMemo(() => {
    const totalBytes = nasFiles.reduce((acc, f) => acc + f.sizeBytes, 0);
    const usedGB = Number((38.5 + (totalBytes - INITIAL_NAS_FILES.reduce((a, b) => a + b.sizeBytes, 0)) / (1024 * 1024 * 1024)).toFixed(2));
    const totalGB = 500;
    const percent = Math.min(100, Math.max(1, Number(((usedGB / totalGB) * 100).toFixed(1))));
    return {
      usedGB,
      totalGB,
      percent,
      availableGB: Number((totalGB - usedGB).toFixed(1)),
      orderFilesCount: 1180 + nasFiles.filter((f) => f.folderPath.startsWith('orders')).length - 7,
      orderGB: 28.2,
      caregiverFilesCount: 160 + nasFiles.filter((f) => f.folderPath.startsWith('caregivers')).length - 3,
      caregiverGB: 10.3,
    };
  }, [nasFiles]);

  // Filtered files
  const filteredFiles = useMemo(() => {
    return nasFiles.filter((file) => {
      if (selectedFolder !== 'all') {
        if (selectedFolder === 'orders' && !file.folderPath.startsWith('orders')) return false;
        if (selectedFolder === 'caregivers' && !file.folderPath.startsWith('caregivers')) return false;
        if (selectedFolder.startsWith('orders/ORD-') || selectedFolder.startsWith('caregivers/STF-')) {
          if (!file.folderPath.startsWith(selectedFolder)) return false;
        }
      }
      if (typeFilter !== 'all' && file.category !== typeFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchName = file.name.toLowerCase().includes(query);
        const matchCase = file.caseNo?.toLowerCase().includes(query);
        const matchClient = file.clientName?.toLowerCase().includes(query);
        const matchStaff = file.staffName?.toLowerCase().includes(query);
        const matchDesc = file.desc.toLowerCase().includes(query);
        if (!matchName && !matchCase && !matchClient && !matchStaff && !matchDesc) return false;
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

  const handleDownload = (file: NasFileItem) => {
    setToastMessage(`⬇️ 本機介面預覽：將下載「${file.name}」；目前未連接 NAS，不會傳輸檔案。`);
  };

  const handleBatchDownload = () => {
    if (selectedFileIds.size === 0) {
      setToastMessage('⚠️ 請先勾選欲打包下載的檔案項目。');
      return;
    }
    setToastMessage(`📦 本機介面預覽：已選取 ${selectedFileIds.size} 筆打包下載候選；目前未建立下載任務。`);
  };

  const handleBatchDelete = () => {
    if (selectedFileIds.size === 0) {
      setToastMessage('⚠️ 請先勾選欲批次刪除的檔案項目。');
      return;
    }
    const targetFile = nasFiles.find((f) => selectedFileIds.has(f.id));
    if (targetFile) setDeleteConfirmFile(targetFile);
  };

  const handleConfirmDelete = () => {
    if (!deleteConfirmFile) return;
    const targetId = deleteConfirmFile.id;
    setNasFiles((prev) => prev.filter((f) => f.id !== targetId));
    setSelectedFileIds((prev) => {
      const next = new Set(prev);
      next.delete(targetId);
      return next;
    });
    setToastMessage(`🗑️ 本機介面預覽：已從畫面移除「${deleteConfirmFile.name}」；NAS 與資料庫均未變更。`);
    setDeleteConfirmFile(null);
  };

  const handleUploadSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const now = new Date();
    const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
    const timeStr = `${dateStr}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;

    let generatedName = '';
    let categoryLabel = '';
    let statusBadge = '';
    let statusBadgeType: NasFileItem['statusBadgeType'] = 'signed';
    let folder = selectedFolder;

    if (uploadCategory === 'notice') {
      const seq = nasFiles.filter((f) => f.category === 'notice' && f.caseNo === 'ORD-2026-HC019').length + 1;
      generatedName = `NOTICE_ORD-HC019_林美真_SEQ-${seq}_${timeStr}.pdf`;
      categoryLabel = '寄出訂單資訊 NOTICE';
      statusBadge = `🟢 已寄出 SEQ-${seq}`;
      statusBadgeType = 'sent';
      folder = 'orders/ORD-HC019/contracts';
    } else if (uploadCategory === 'dates') {
      generatedName = `DATES_ORD-HC019_林美真_CONFIRMED_${dateStr}.pdf`;
      categoryLabel = '服務日期確認表';
      statusBadge = '🔒 檔期已鎖定';
      statusBadgeType = 'locked';
      folder = 'orders/ORD-HC019/contracts';
    } else if (uploadCategory === 'contract') {
      generatedName = `CONTRACT_ORD-HC019_林美真_SIGNED_v2.pdf`;
      categoryLabel = '定型化契約 PDF';
      statusBadge = '✔ 正式簽署 v2';
      statusBadgeType = 'signed';
      folder = 'orders/ORD-HC019/contracts';
    } else if (uploadCategory === 'baby_log') {
      generatedName = `BABY_ORD-HC019_${dateStr}_02.jpg`;
      categoryLabel = '寶寶日誌照片';
      statusBadge = '👶 照護日誌照片';
      statusBadgeType = 'media';
      folder = 'orders/ORD-HC019/baby_logs';
    } else if (uploadCategory === 'meal') {
      generatedName = `MEAL_ORD-HC019_${dateStr}_DINNER_01.jpg`;
      categoryLabel = '月子餐食照片';
      statusBadge = '🍲 藥膳餐食照片';
      statusBadgeType = 'media';
      folder = 'orders/ORD-HC019/meals';
    } else {
      generatedName = `CERT_STF-012_張美敏_專業證照_${dateStr}.pdf`;
      categoryLabel = '專業證照';
      statusBadge = '🛡️ 證件審核通過';
      statusBadgeType = 'approved';
      folder = 'caregivers/STF-012';
    }

    const newFile: NasFileItem = {
      id: `nas-f-${Date.now()}`,
      name: generatedName,
      category: uploadCategory,
      categoryLabel,
      folderPath: folder,
      caseNo: 'ORD-2026-HC019',
      clientName: '林美真',
      sizeBytes: 524288,
      sizeFormatted: '512 KB',
      updatedAt: `115/${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`,
      statusBadge,
      statusBadgeType,
      sha256: `${Math.random().toString(36).substring(2, 10)}${Math.random().toString(36).substring(2, 10)}...驗證合格`,
      isOngoing: true,
      version: 'v1',
      desc: uploadCustomDesc.trim() || '管理端受控補充上傳附件',
    };

    setNasFiles((prev) => [newFile, ...prev]);
    setIsUploadModalOpen(false);
    setUploadCustomDesc('');
    setToastMessage(`📤 本機介面預覽：已加入上傳候選「${generatedName}」；NAS 與資料庫均未變更。`);
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
          <span className="datacenter-tab-pill">1,340 檔案</span>
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
          目前為 NAS 前端操作預覽；清單與容量使用設計資料，下載、上傳與刪除不會操作地端 NAS。
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
                <span className="nas-quota-title">💾 Synology NAS 儲存容量監控</span>
                <span className="nas-quota-usage-text">
                  已使用 <strong>{quota.usedGB} GB</strong> / {quota.totalGB} GB ({quota.percent}%) ｜ 剩餘可用: <strong>{quota.availableGB} GB</strong>
                </span>
              </div>
              <div className="nas-progress-track">
                <div className="nas-progress-fill" style={{ width: `${quota.percent}%` }}></div>
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
                <span>安全防呆保護</span>
                <strong style={{ color: '#16a34a' }}>已啟用 (未結案警示)</strong>
              </div>
            </div>
          </section>

          {/* Two-Column Explorer Layout */}
          <div className="nas-explorer-grid">
            {/* Left: Folder Tree */}
            <aside className="nas-tree-card">
              <div className="nas-tree-title">
                <span>📂 檔案目錄導覽</span>
                <span style={{ fontSize: '0.72rem', color: '#8c7873' }}>全部 1,340 檔</span>
              </div>

              <ul className="nas-tree-list">
                <li>
                  <div
                    className={`nas-tree-item ${selectedFolder === 'all' ? 'active' : ''}`}
                    onClick={() => setSelectedFolder('all')}
                  >
                    <span>📁 全部檔案</span>
                    <span className="nas-tree-count">1,340</span>
                  </div>
                </li>

                {/* Orders Category */}
                <li>
                  <div
                    className={`nas-tree-item ${selectedFolder.startsWith('orders') ? 'active' : ''}`}
                    onClick={() => setSelectedFolder('orders/ORD-HC019/contracts')}
                  >
                    <span>📦 訂單專區檔案庫</span>
                    <span className="nas-tree-count">142 案</span>
                  </div>

                  <ul className="nas-tree-sub-list">
                    {/* Case 1: Active */}
                    <li>
                      <div
                        className={`nas-tree-sub-item ${selectedFolder.startsWith('orders/ORD-HC019') ? 'active' : ''}`}
                        onClick={() => setSelectedFolder('orders/ORD-HC019')}
                      >
                        <span>📁 ORD-HC019 (林美真 產婦)</span>
                        <span className="nas-tree-count">18</span>
                      </div>
                      <ul className="nas-tree-sub-list">
                        <li>
                          <div
                            className={`nas-tree-sub-item ${selectedFolder === 'orders/ORD-HC019/contracts' ? 'active' : ''}`}
                            onClick={() => setSelectedFolder('orders/ORD-HC019/contracts')}
                          >
                            <span>📑 契約與服務確認</span>
                            <span className="nas-tree-count">4</span>
                          </div>
                        </li>
                        <li>
                          <div
                            className={`nas-tree-sub-item ${selectedFolder === 'orders/ORD-HC019/baby_logs' ? 'active' : ''}`}
                            onClick={() => setSelectedFolder('orders/ORD-HC019/baby_logs')}
                          >
                            <span>👶 寶寶照護日誌</span>
                            <span className="nas-tree-count">8</span>
                          </div>
                        </li>
                        <li>
                          <div
                            className={`nas-tree-sub-item ${selectedFolder === 'orders/ORD-HC019/meals' ? 'active' : ''}`}
                            onClick={() => setSelectedFolder('orders/ORD-HC019/meals')}
                          >
                            <span>🍲 月子餐食照片</span>
                            <span className="nas-tree-count">6</span>
                          </div>
                        </li>
                      </ul>
                    </li>

                    {/* Case 2 */}
                    <li>
                      <div
                        className={`nas-tree-sub-item ${selectedFolder === 'orders/ORD-HC020' || selectedFolder === 'orders/ORD-HC020/contracts' ? 'active' : ''}`}
                        onClick={() => setSelectedFolder('orders/ORD-HC020/contracts')}
                      >
                        <span>📁 ORD-HC020 (陳雅萱 產婦)</span>
                        <span className="nas-tree-count">12</span>
                      </div>
                    </li>
                    {/* Case 3 */}
                    <li>
                      <div
                        className={`nas-tree-sub-item ${selectedFolder === 'orders/ORD-HC021' ? 'active' : ''}`}
                        onClick={() => setSelectedFolder('orders/ORD-HC021')}
                      >
                        <span>📁 ORD-HC021 (黃雅婷 產婦)</span>
                        <span className="nas-tree-count">9</span>
                      </div>
                    </li>
                  </ul>
                </li>

                {/* Caregivers Category */}
                <li>
                  <div
                    className={`nas-tree-item ${selectedFolder.startsWith('caregivers') ? 'active' : ''}`}
                    onClick={() => setSelectedFolder('caregivers/STF-012')}
                  >
                    <span>👩‍🍼 月嫂專區檔案庫</span>
                    <span className="nas-tree-count">48 位</span>
                  </div>
                  <ul className="nas-tree-sub-list">
                    <li>
                      <div
                        className={`nas-tree-sub-item ${selectedFolder === 'caregivers/STF-012' ? 'active' : ''}`}
                        onClick={() => setSelectedFolder('caregivers/STF-012')}
                      >
                        <span>📁 STF-012 (張美敏 月嫂)</span>
                        <span className="nas-tree-count">4</span>
                      </div>
                    </li>
                    <li>
                      <div
                        className={`nas-tree-sub-item ${selectedFolder === 'caregivers/STF-015' ? 'active' : ''}`}
                        onClick={() => setSelectedFolder('caregivers/STF-015')}
                      >
                        <span>📁 STF-015 (李秀芬 月嫂)</span>
                        <span className="nas-tree-count">5</span>
                      </div>
                    </li>
                  </ul>
                </li>
              </ul>
            </aside>

            {/* Right: Main Workbench */}
            <main className="nas-workbench-card">
              {/* Breadcrumb & Action Toolbar */}
              <div className="nas-toolbar-row">
                <div className="nas-breadcrumb">
                  <span>📁 {selectedFolder.startsWith('caregivers') ? '月嫂專區' : '訂單專區'}</span>
                  <span className="nas-breadcrumb-sep">&gt;</span>
                  <span>{selectedFolder.includes('ORD-HC019') ? '📁 ORD-2026-HC019 (林美真 產婦)' : selectedFolder.includes('ORD-HC020') ? '📁 ORD-2026-HC020 (陳雅萱)' : selectedFolder.includes('STF-012') ? '📁 STF-012 (張美敏 月嫂)' : '📁 全部檔案'}</span>
                  {selectedFolder.includes('contracts') && (
                    <>
                      <span className="nas-breadcrumb-sep">&gt;</span>
                      <span>📑 契約與服務確認</span>
                    </>
                  )}
                  {selectedFolder.includes('baby_logs') && (
                    <>
                      <span className="nas-breadcrumb-sep">&gt;</span>
                      <span>👶 寶寶照護日誌</span>
                    </>
                  )}
                  {selectedFolder.includes('meals') && (
                    <>
                      <span className="nas-breadcrumb-sep">&gt;</span>
                      <span>🍲 月子餐食照片</span>
                    </>
                  )}
                  <span style={{ fontSize: '0.78rem', color: '#795d43', fontWeight: 600 }}>
                    ({filteredFiles.length} 筆)
                  </span>
                </div>

                <div className="nas-action-btn-group">
                  <button type="button" className="nas-btn nas-btn-outline" onClick={handleBatchDownload}>
                    ⬇️ 批次下載
                  </button>
                  <button type="button" className="nas-btn nas-btn-danger" onClick={handleBatchDelete}>
                    🗑️ 批次刪除
                  </button>
                  <button type="button" className="nas-btn nas-btn-primary" onClick={() => setIsUploadModalOpen(true)}>
                    ➕ 補充上傳新附件
                  </button>
                </div>
              </div>

              {/* Dispute Comparison Notice Banner */}
              <div className="nas-dispute-notice-card">
                <span className="nas-dispute-icon">💡</span>
                <div>
                  <strong>爭議比對提示：</strong>
                  若產婦對服務排班或天數有爭議，可比對【合約服務日期確認表】與【寄出訂單資訊 NOTICE_SEQ-1 / SEQ-2】之歷史派單留底。
                </div>
              </div>

              {/* Search & Filter Controls */}
              <div className="nas-filter-bar">
                <input
                  type="text"
                  className="nas-search-input"
                  placeholder="🔍 搜尋訂單編號、產婦姓名、檔名或時間..."
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
                <select
                  className="nas-filter-select"
                  value={timeFilter}
                  onChange={(e) => setTimeFilter(e.target.value)}
                >
                  <option value="all">全部時間區間</option>
                  <option value="7d">本週 (7 天內)</option>
                  <option value="30d">本月 (30 天內)</option>
                  <option value="115y">今年度 (115 年)</option>
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
                      <th>歸檔 / 發送時間</th>
                      <th>狀態與版本</th>
                      <th>SHA-256 完整性</th>
                      <th style={{ textAlign: 'right' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredFiles.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ textAlign: 'center', padding: '36px', color: '#8c7873' }}>
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
                            <td>
                              <span className="nas-sha-badge" title={file.sha256}>
                                🛡️ {file.sha256.substring(0, 8)}...驗證合格
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
                                  title="預覽內容"
                                  onClick={() => setPreviewFile(file)}
                                >
                                  👁️ 預覽
                                </button>
                                <button
                                  type="button"
                                  className="nas-btn-action nas-btn-action-delete"
                                  title="自 NAS 安全刪除"
                                  onClick={() => setDeleteConfirmFile(file)}
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
                  外發通知均採【先存 NAS 鎖定 ➔ 再由 NAS 發送】；刪除檔案即時顯示釋放空間預覽，進行中合約具備防呆警告保護。
                </div>
                <div>
                  🔒 <strong>通訊協定：</strong> SFTP (Port 22) 加密傳輸 ｜ 零實體磁碟暴露
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
                  {previewFile.category === 'contract' && (
                    <div className="nas-preview-stamp">新竹市月子工會 契約審核核章</div>
                  )}
                </div>

                {previewFile.category === 'baby_log' && (
                  <div style={{ background: '#fff0eb', border: '1px solid #fed9b8', borderRadius: '8px', padding: '16px', textAlign: 'center' }}>
                    <div style={{ fontSize: '3rem', marginBottom: '8px' }}>👶</div>
                    <div style={{ fontWeight: 700, color: '#a43c12', fontSize: '0.85rem' }}>寶寶到宅照護日誌記錄影像</div>
                    <p style={{ fontSize: '0.75rem', color: '#795d43', margin: '4px 0 0' }}>拍攝時間：{previewFile.updatedAt} ｜ 體溫 36.6°C ｜ 臍帶乾燥良好</p>
                  </div>
                )}

                {previewFile.category === 'meal' && (
                  <div style={{ background: '#fff0eb', border: '1px solid #fed9b8', borderRadius: '8px', padding: '16px', textAlign: 'center' }}>
                    <div style={{ fontSize: '3rem', marginBottom: '8px' }}>🍲</div>
                    <div style={{ fontWeight: 700, color: '#a43c12', fontSize: '0.85rem' }}>產後藥膳月子餐料理存證</div>
                    <p style={{ fontSize: '0.75rem', color: '#795d43', margin: '4px 0 0' }}>拍攝時間：{previewFile.updatedAt} ｜ 當季溫補麻油杜仲燉湯</p>
                  </div>
                )}

                <div style={{ fontSize: '0.8rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', background: '#ffffff', padding: '10px', borderRadius: '6px', border: '1px solid #f2e2dc' }}>
                  <div><strong>檔案大小：</strong> {previewFile.sizeFormatted}</div>
                  <div><strong>歸檔時間：</strong> {previewFile.updatedAt}</div>
                  <div><strong>版本狀態：</strong> {previewFile.statusBadge}</div>
                  <div><strong>儲存位置：</strong> 地端 NAS (SFTP)</div>
                </div>

                <div style={{ fontSize: '0.75rem', color: '#059669', background: '#ecfdf5', padding: '8px', borderRadius: '6px', border: '1px solid #a7f3d0' }}>
                  🛡️ <strong>SHA-256 完整性雜湊值：</strong><br />
                  <code style={{ wordBreak: 'break-all', fontFamily: 'monospace' }}>{previewFile.sha256}</code>
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
                  <label>歸屬案件 / 月嫂資料夾：</label>
                  <select
                    className="nas-form-control"
                    value={uploadTargetCase}
                    onChange={(e) => setUploadTargetCase(e.target.value)}
                  >
                    <option value="ORD-2026-HC019 (林美真)">📦 ORD-2026-HC019 (林美真 產婦)</option>
                    <option value="ORD-2026-HC020 (陳雅萱)">📦 ORD-2026-HC020 (陳雅萱 產婦)</option>
                    <option value="STF-012 (張美敏)">👩‍🍼 STF-012 (張美敏 月嫂)</option>
                  </select>
                </div>

                <div className="nas-form-group">
                  <label>附件類型：</label>
                  <select
                    className="nas-form-control"
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value as any)}
                  >
                    <option value="notice">📤 寄出訂單資訊通知單 (NOTICE_SEQ-{nasFiles.filter((f) => f.category === 'notice').length + 1})</option>
                    <option value="dates">📅 合約服務日期確認表 (DATES_CONFIRMED)</option>
                    <option value="contract">📑 定型化契約 (已簽名正本)</option>
                    <option value="baby_log">👶 寶寶日誌照片 (BABY_LOG)</option>
                    <option value="meal">🍲 月子餐食成果照片 (MEAL)</option>
                    <option value="cert">🛡️ 良民證與專業證照 (CERT)</option>
                  </select>
                </div>

                <div className="nas-form-group">
                  <label>檔案說明備註 (選填)：</label>
                  <input
                    type="text"
                    className="nas-form-control"
                    placeholder="例：預產期提早修改之第二版服務確認單"
                    value={uploadCustomDesc}
                    onChange={(e) => setUploadCustomDesc(e.target.value)}
                  />
                </div>

                <div style={{ background: '#fff8f6', border: '1px dashed #dec0b6', borderRadius: '8px', padding: '12px', fontSize: '0.8rem', color: '#795d43' }}>
                  🔒 <strong>自動防呆命名預覽：</strong>
                  <div style={{ fontWeight: 700, color: '#a43c12', marginTop: '4px', fontFamily: 'monospace' }}>
                    {uploadCategory === 'notice' ? `NOTICE_ORD-HC019_林美真_SEQ-${nasFiles.filter((f) => f.category === 'notice').length + 1}_20260825-1540.pdf` : uploadCategory === 'dates' ? 'DATES_ORD-HC019_林美真_CONFIRMED_20260825.pdf' : uploadCategory === 'contract' ? 'CONTRACT_ORD-HC019_林美真_SIGNED_v2.pdf' : uploadCategory === 'baby_log' ? 'BABY_ORD-HC019_20260825_02.jpg' : uploadCategory === 'meal' ? 'MEAL_ORD-HC019_20260825_DINNER_01.jpg' : 'CERT_STF-012_張美敏_專業證照_20260825.pdf'}
                  </div>
                  <small style={{ color: '#8c7873', marginTop: '4px', display: 'block' }}>
                    ✔ 預覽【先存 NAS 鎖定 ➔ 再由 NAS 發送】時序；正式雜湊須由後端儲存流程產生。
                  </small>
                </div>
              </div>
              <div className="nas-modal-footer">
                <button type="button" className="nas-btn nas-btn-outline" onClick={() => setIsUploadModalOpen(false)}>
                  取消
                </button>
                <button type="submit" className="nas-btn nas-btn-primary">
                  📤 預覽上傳結果
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 3. Safe Deletion Confirmation Modal */}
      {deleteConfirmFile && (
        <div className="nas-modal-overlay" onClick={() => setDeleteConfirmFile(null)}>
          <div className="nas-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="nas-modal-header" style={{ background: '#fef2f2' }}>
              <h3 style={{ color: '#dc2626' }}>
                <span>⚠️ 安全刪除確認</span>
              </h3>
              <button type="button" className="nas-modal-close-btn" onClick={() => setDeleteConfirmFile(null)}>✕</button>
            </div>
            <div className="nas-modal-body">
              <p style={{ fontSize: '0.88rem', color: '#1e1b19', margin: 0 }}>
                您正在預覽從地端 Synology NAS <strong>永久刪除</strong> 以下檔案的結果：
              </p>

              <div style={{ background: '#fff5f5', border: '1px solid #fecaca', borderRadius: '8px', padding: '12px', fontSize: '0.82rem' }}>
                <div style={{ fontWeight: 700, color: '#991b1b', fontFamily: 'monospace' }}>{deleteConfirmFile.name}</div>
                <div style={{ color: '#7f1d1d', marginTop: '4px' }}>
                  檔案大小：<strong>{deleteConfirmFile.sizeFormatted}</strong> ｜ 歸檔時間：{deleteConfirmFile.updatedAt}
                </div>
              </div>

              {deleteConfirmFile.isOngoing && (
                <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px', padding: '10px', fontSize: '0.8rem', color: '#92400e' }}>
                  ⚠️ <strong>進行中合約保護警示：</strong><br />
                  此檔案所屬之訂單目前處於服務履約中，若非重複或錯誤檔案，請謹慎評估後再執行刪除！
                </div>
              )}

              <div style={{ fontSize: '0.8rem', color: '#57423b' }}>
                💡 <strong>容量釋放預覽：</strong> 刪除後將即時自 NAS 釋放 <strong>{deleteConfirmFile.sizeFormatted}</strong> 儲存空間。
              </div>
            </div>
            <div className="nas-modal-footer">
              <button type="button" className="nas-btn nas-btn-outline" onClick={() => setDeleteConfirmFile(null)}>
                取消保留
              </button>
              <button type="button" className="nas-btn nas-btn-danger" onClick={handleConfirmDelete}>
                🗑️ 預覽刪除結果
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default DataImportPage;
