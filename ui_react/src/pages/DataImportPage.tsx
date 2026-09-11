/**
 * File: DataImportPage.tsx
 * Description: 整合工作簿安全匯入與既有數據瀏覽的資料中心分頁。
 */
import React, { useEffect, useRef, useState } from 'react';
import { adaptClientBeClassWorkbookPreview } from '../adapters/case_import/client_beclass_workbook_adapter';
import { adaptHcmWorkbookPreview } from '../adapters/case_import/hcm_workbook_adapter';
import { adaptStaffHistoricalWorkbookPreview } from '../adapters/case_import/staff_historical_workbook_adapter';
import { adaptHistoricalOrderWorkbookPreview } from '../adapters/orders/historical_order_workbook_adapter';
import { ClientBeClassWorkbookSnapshot, clientBeClassWorkbookPreviewClient } from '../api/case_import/client_beclass_workbook/client';
import { HcmWorkbookSnapshot, hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
import type { HcmWorkbookRowOutcome } from '../api/case_import/hcm_workbook_schemas';
import { StaffHistoricalWorkbookSnapshot, staffHistoricalWorkbookPreviewClient } from '../api/case_import/staff_historical_workbook/client';
import { HistoricalOrderWorkbookSnapshot, historicalOrderWorkbookPreviewClient } from '../api/orders/historical_order_workbook/client';
import { HistoricalOrderReviewRemediationWorkbench } from '../components/HistoricalOrderReviewRemediationWorkbench';
import { HcmControlledCorrectionWorkbench } from '../components/HcmControlledCorrectionWorkbench';
import { DataBrowserPage } from './DataBrowserPage';
import './DataImportPage.css';

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

interface HcmReviewGuidance {
  message: string;
  nextStep: string;
}

interface SourceWorkbookIssue {
  source_row: number;
  fields: string[];
  issue_codes: string[];
  case_no?: string | null;
  query_no?: string | null;
}

function sourceIssueDescription(issue: SourceWorkbookIssue): string {
  const fieldDescriptions = issue.fields.map((field) => {
    const fieldCodes = issue.issue_codes.filter((code) => code.endsWith(`:${field}`));
    if (fieldCodes.some((code) => code.includes('_missing:'))) return `${field}（不可空白）`;
    if (fieldCodes.some((code) => code.includes('_invalid:'))) return `${field}（格式或內容不符合規則）`;
    return field;
  });
  if (issue.issue_codes.includes('client_beclass_source_payload_conflict')) {
    return `需核對欄位：${fieldDescriptions.join('、')}（同一查詢序號的來源內容與既有資料不同）。`;
  }
  if (issue.issue_codes.some((code) => code.includes('client_case_binding') || code.includes('client_beclass_binding'))) {
    return `需核對欄位：${fieldDescriptions.join('、')}（無法唯一對應既有客戶與案件）。`;
  }
  if (issue.issue_codes.includes('historical_status_invalid')) {
    return `需修改欄位：${fieldDescriptions.join('、')}（只接受 0、1、2）。`;
  }
  if (issue.issue_codes.some((code) => code.includes('staff_not_found'))) {
    return `需核對欄位：${fieldDescriptions.join('、')}（找不到可唯一對應的月嫂）。`;
  }
  if (issue.issue_codes.some((code) => code.includes('staff_ambiguous'))) {
    return `需核對欄位：${fieldDescriptions.join('、')}（同名月嫂不唯一）。`;
  }
  if (issue.issue_codes.some((code) => code.endsWith('_date_range_invalid'))) {
    return `需修改欄位：${fieldDescriptions.join('、')}（開始日期不可晚於結束日期）。`;
  }
  return `需修改或核對欄位：${fieldDescriptions.join('、')}。`;
}

const SourceWorkbookIssueList: React.FC<{ title: string; issues: SourceWorkbookIssue[] }> = ({ title, issues }) => {
  if (issues.length === 0) return null;
  return (
    <div className="import-source-issue-list" aria-label={title}>
      <strong>{title}</strong>
      <p>請依下列位置修改原始工作簿，再重新預覽：</p>
      {issues.map((issue) => (
        <div className="import-result-problem" key={`${issue.source_row}-${issue.case_no ?? issue.query_no ?? 'row'}`}>
          <strong>{issue.case_no ? `案件 ${issue.case_no}` : issue.query_no ? `查詢序號 ${issue.query_no}` : `工作簿第 ${issue.source_row} 列`}</strong>
          {(issue.case_no || issue.query_no) && <span>工作簿第 {issue.source_row} 列</span>}
          <span>{sourceIssueDescription(issue)}</span>
        </div>
      ))}
    </div>
  );
};

function hcmReviewGuidance(row: HcmWorkbookRowOutcome): HcmReviewGuidance {
  const fieldIssues = row.issue_codes.filter((code) => code.startsWith('hcm_field_missing:') || code.startsWith('hcm_field_invalid:'));
  if (fieldIssues.length > 0) {
    const descriptions = fieldIssues.map((code) => {
      const [kind, field = '來源資料'] = code.split(':', 2);
      return `${field}（${kind === 'hcm_field_missing' ? '不可空白' : '格式或內容不符合規則'}）`;
    });
    return {
      message: `需修改欄位：${descriptions.join('、')}。`,
      nextStep: '請修正原始工作簿後重新預覽。',
    };
  }

  if (row.issue_codes.some((code) => code.startsWith('hcm_identity:'))) {
    return {
      message: '需核對欄位：查詢序號(案件編號)、姓名、IP位址。系統無法唯一確認這筆資料與既有客戶的身分關聯。',
      nextStep: '請確認這三個欄位屬於同一人，必要時修正原始工作簿後重新預覽。',
    };
  }

  if (row.issue_codes.some((code) => code === 'hcm_case_import:case_import_bootstrap_blocked')) {
    return {
      message: '需核對欄位：服務時間、預計服務日期、希望服務天數、服務方式。這些資料目前無法組成可建立的訂單。',
      nextStep: '請修正原始工作簿後重新預覽。',
    };
  }

  if (row.issue_codes.some((code) => code.startsWith('hcm_case_import:'))) {
    return {
      message: '此案件的既有資料或匯入狀態有衝突；一般 HCM 匯入不會覆寫既有案件與訂單資料。',
      nextStep: '請先核對查詢序號(案件編號)；若要更正既有案件，請使用專用更正流程。',
    };
  }

  const fields = row.problem_fields.filter((field) => field !== 'case_import' && field !== 'hcm_identity');
  return {
    message: fields.length > 0
      ? `需修改欄位：${fields.join('、')}。`
      : `來源第 ${row.source_row} 筆資料需要人工檢查。`,
    nextStep: '請修正原始工作簿後重新預覽。',
  };
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
  previewDetail?: React.ReactNode;
}

const CaseWorkbookPreviewCard: React.FC<CaseWorkbookPreviewCardProps> = ({
  id, icon, title, inputLabel, openPreviewControlId, rowDetailUnavailableMessage, selectedWorkbook, previewState, applyState, confirmed, mutationLocked, metrics, onSelect, onPreview, onConfirm, onApply, reviewAction, previewDetail,
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
          {previewDetail}
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
  caseNo: string;
  displayMessage: string;
  reviewIdentity: string;
}

export type DataCenterTab = 'workbook-import' | 'data-browser';
type WorkbookImportKind = 'hcm-current' | 'client-beclass' | 'staff-historical' | 'historic-orders';

const WORKBOOK_IMPORT_OPTIONS: ReadonlyArray<{ kind: WorkbookImportKind; label: string; shortLabel: string }> = [
  { kind: 'hcm-current', label: 'HCM 案件', shortLabel: 'HCM' },
  { kind: 'client-beclass', label: '客戶 BeClass', shortLabel: '客戶' },
  { kind: 'staff-historical', label: '月嫂歷史資料', shortLabel: '月嫂' },
  { kind: 'historic-orders', label: '歷史訂單認領', shortLabel: '歷史訂單' },
];

export interface DataImportPageProps {
  initialTab?: DataCenterTab;
}

export const DataImportPage: React.FC<DataImportPageProps> = ({ initialTab = 'workbook-import' }) => {
  const [activeTab, setActiveTab] = useState<DataCenterTab>(initialTab);
  const [activeImportKind, setActiveImportKind] = useState<WorkbookImportKind>('hcm-current');
  const [historicalReviewIdentities, setHistoricalReviewIdentities] = useState<string[]>([]);
  const [selectedHistoricalReviewIdentity, setSelectedHistoricalReviewIdentity] = useState<string | null>(null);
  const [hcmReviewRows, setHcmReviewRows] = useState<HcmWorkbookRowOutcome[]>([]);
  const [hcmCorrection, setHcmCorrection] = useState<HcmCorrectionSelection | null>(null);

  const hcmCurrent = useCaseWorkbookFlow(
    HcmWorkbookSnapshot.fromFile,
    (snapshot, options) => hcmWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => hcmWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptHcmWorkbookPreview,
    (receipt) => applyPresentation(receipt.replayed_workbook, `新增 ${receipt.inserted_count} 筆、含警示 ${receipt.inserted_with_warning_count} 筆、既有案件跳過 ${receipt.skipped_existing_count} 筆（不覆寫既有案件與訂單資料）、需檢查 ${receipt.review_required_count} 筆、失敗 ${receipt.failed_count} 筆。`, receipt.inserted_with_warning_count > 0 || receipt.review_required_count > 0 || receipt.failed_count > 0 ? 'needs-review' : receipt.inserted_count === 0 ? 'no-change' : 'applied'),
    'HCM 工作簿處理失敗。', 'hcm-current', (receipt) => {
      setHcmReviewRows(receipt.row_outcomes.filter((row) => row.problem_identity !== null || row.outcome === 'review_required' || row.outcome === 'failed'));
      setHcmCorrection(null);
    }
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

  const hcmReviewAction = (
    <div className="import-referral-group" aria-label="本次 HCM 待檢查資料">
      {hcmReviewRows.length === 0 ? (
        <p>這次收據沒有提供問題列明細；請修正原始工作簿後重新預覽，畫面不會轉往其他頁面。</p>
      ) : hcmReviewRows.map((row) => {
        const fieldIssueCodes = row.issue_codes.filter((code) => code.startsWith('hcm_field_missing:') || code.startsWith('hcm_field_invalid:'));
        const canCorrect = row.case_no !== null && row.problem_identity !== null && new Set(fieldIssueCodes.map((code) => code.split(':', 2)[1])).size === 1;
        const guidance = hcmReviewGuidance(row);
        return (
          <div key={`${row.source_row}-${row.problem_identity ?? row.outcome}`} className="import-result-problem">
            <strong>{row.case_no ? `案件 ${row.case_no}` : `來源第 ${row.source_row} 列`}</strong>
            {row.case_no && <span>工作簿來源第 {row.source_row} 筆</span>}
            <span>{row.outcome === 'failed' ? `匯入失敗。${guidance.message}` : guidance.message}</span>
            {canCorrect ? (
              <button type="button" className="import-referral-btn" onClick={() => setHcmCorrection({ caseNo: row.case_no as string, displayMessage: guidance.message, reviewIdentity: row.problem_identity as string })}>🛠️ 在本頁提交修正</button>
            ) : (
              <span>{guidance.nextStep}</span>
            )}
          </div>
        );
      })}
    </div>
  );

  const clientBeClassRowIssues = clientBeClass.previewState.kind === 'ready' ? clientBeClass.previewState.preview.rowIssues : [];
  const historicalOrderRowIssues = historicalOrders.previewState.kind === 'ready' ? historicalOrders.previewState.preview.rowIssues : [];
  const clientBeClassPreviewIssues = (
    <SourceWorkbookIssueList title="客戶 BeClass 原始資料問題" issues={clientBeClassRowIssues} />
  );
  const historicalOrderPreviewIssues = (
    <SourceWorkbookIssueList title="歷史狀態原始資料問題" issues={historicalOrderRowIssues} />
  );
  const historicalOrderReviewActions = historicalReviewAction ?? (
    historicalOrderRowIssues.length > 0
      ? <p>問題列已列在上方；請修正原始工作簿後重新預覽。</p>
      : undefined
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

  const selectTab = (tab: DataCenterTab) => {
    setActiveTab(tab);
    window.location.hash = tab === 'data-browser' ? '#data-browser' : '#data-import';
  };

  return (
    <div data-surface-id="imports.page" className="import-page-container">
      <div className="datacenter-tabs-container">
        <button type="button" className={`datacenter-tab-btn ${activeTab === 'workbook-import' ? 'active' : ''}`} onClick={() => selectTab('workbook-import')}>📥 工作簿資料匯入 (Data Import)<span className="datacenter-tab-pill">4 種類型</span></button>
        <button type="button" className={`datacenter-tab-btn ${activeTab === 'data-browser' ? 'active' : ''}`} onClick={() => selectTab('data-browser')}>📊 數據瀏覽 (Data Browser)<span className="datacenter-tab-pill">唯讀</span></button>
      </div>

      {activeTab === 'workbook-import' && (
        <div>
          <header className="page-header-banner import-result-header">
            <div><h1 className="page-title">📥 批次資料匯入中心</h1><p className="page-subtitle">選擇工作簿、預覽核對，確認後即可完成匯入；本次需要檢查的 HCM 資料會留在匯入卡片內。</p></div>
          </header>
          {mutationLocked && <div className="import-result-state" role="status" data-surface-id="imports.apply-navigation-lock">匯入已送出或結果尚未確認；目前已鎖定換檔、預覽、站內導覽與重新整理。請留在本頁等待結果。</div>}
          <nav className="import-kind-selector" aria-label="選擇匯入類型">
            <span>匯入類型</span>
            <div>
              {WORKBOOK_IMPORT_OPTIONS.map((option) => (
                <button
                  key={option.kind}
                  type="button"
                  className={activeImportKind === option.kind ? 'active' : ''}
                  aria-pressed={activeImportKind === option.kind}
                  disabled={mutationLocked}
                  onClick={() => setActiveImportKind(option.kind)}
                  title={option.label}
                >
                  {option.shortLabel}
                </button>
              ))}
            </div>
          </nav>
          <div className="import-cards-grid">
            {activeImportKind === 'hcm-current' && <CaseWorkbookPreviewCard id="hcm-current" icon="📄" title="HCM 案件匯入 (HCM Current)" inputLabel="選擇 HCM Current Workbook" openPreviewControlId="imports.hcm-current.open-preview" rowDetailUnavailableMessage={hcmCurrent.previewState.kind === 'ready' ? hcmCurrent.previewState.preview.rowDetailUnavailableMessage : undefined} selectedWorkbook={hcmCurrent.selectedWorkbook} previewState={hcmCurrent.previewState} applyState={hcmCurrent.applyState} confirmed={hcmCurrent.confirmed} mutationLocked={mutationLocked} metrics={hcmCurrent.previewState.kind === 'ready' ? [['來源列數', hcmCurrent.previewState.preview.sourceRowCount], ['可寫入', hcmCurrent.previewState.preview.readyCount], ['含警示', hcmCurrent.previewState.preview.readyWithWarningCount], ['需人工檢查', hcmCurrent.previewState.preview.reviewRequiredCount]] : []} onSelect={hcmCurrent.selectWorkbook} onPreview={hcmCurrent.previewWorkbook} onConfirm={hcmCurrent.setConfirmed} onApply={hcmCurrent.applyWorkbook} reviewAction={hcmReviewAction} />}
            {activeImportKind === 'client-beclass' && <CaseWorkbookPreviewCard id="client-beclass" icon="👥" title="客戶 BeClass 問卷匯入" inputLabel="選擇客戶 BeClass Workbook" selectedWorkbook={clientBeClass.selectedWorkbook} previewState={clientBeClass.previewState} applyState={clientBeClass.applyState} confirmed={clientBeClass.confirmed} mutationLocked={mutationLocked} metrics={clientBeClass.previewState.kind === 'ready' ? [['來源列數', clientBeClass.previewState.preview.sourceRowCount], ['可建立', clientBeClass.previewState.preview.createCount], ['需人工檢查', clientBeClass.previewState.preview.reviewRequiredCount], ['既有衝突', clientBeClass.previewState.preview.existingConflictCount], ['既有來源', clientBeClass.previewState.preview.existingSourceCount]] : []} onSelect={clientBeClass.selectWorkbook} onPreview={clientBeClass.previewWorkbook} onConfirm={clientBeClass.setConfirmed} onApply={clientBeClass.applyWorkbook} previewDetail={clientBeClassPreviewIssues} reviewAction={<p>{clientBeClassRowIssues.length > 0 ? '問題列已列在上方；請修正原始工作簿後重新預覽。' : '請回原始工作簿核對問題資料後重新預覽。'}</p>} />}
            {activeImportKind === 'staff-historical' && <CaseWorkbookPreviewCard id="staff-historical" icon="👩‍🍼" title="月嫂歷史資料匯入" inputLabel="選擇月嫂歷史 Workbook" selectedWorkbook={staffHistorical.selectedWorkbook} previewState={staffHistorical.previewState} applyState={staffHistorical.applyState} confirmed={staffHistorical.confirmed} mutationLocked={mutationLocked} metrics={staffHistorical.previewState.kind === 'ready' ? [['來源列數', staffHistorical.previewState.preview.sourceRowCount], ['新建', staffHistorical.previewState.preview.createdCount], ['採用既有', staffHistorical.previewState.preview.adoptedExistingCount], ['身分阻擋', staffHistorical.previewState.preview.blockedIdentityCount], ['身分衝突', staffHistorical.previewState.preview.identityConflictCount], ['需人工檢查', staffHistorical.previewState.preview.reviewRequiredCount]] : []} onSelect={staffHistorical.selectWorkbook} onPreview={staffHistorical.previewWorkbook} onConfirm={staffHistorical.setConfirmed} onApply={staffHistorical.applyWorkbook} />}
            {activeImportKind === 'historic-orders' && <CaseWorkbookPreviewCard id="historic-orders" icon="📦" title="歷史訂單認領匯入" inputLabel="選擇歷史訂單 Workbook" selectedWorkbook={historicalOrders.selectedWorkbook} previewState={historicalOrders.previewState} applyState={historicalOrders.applyState} confirmed={historicalOrders.confirmed} mutationLocked={mutationLocked} metrics={historicalOrders.previewState.kind === 'ready' ? [['來源列數', historicalOrders.previewState.preview.sourceRowCount], ['工作簿未列入將取消', historicalOrders.previewState.preview.absentOrderCancellationCount], ['不採用', historicalOrders.previewState.preview.resultCounts.notAdopted], ['配對中未付訂金', historicalOrders.previewState.preview.resultCounts.matchingPendingDeposit], ['已付訂金未服務', historicalOrders.previewState.preview.resultCounts.historicalUnserved], ['歷史服務中', historicalOrders.previewState.preview.resultCounts.historicalInService], ['歷史服務完成', historicalOrders.previewState.preview.resultCounts.historicalServiceCompleted], ['目前資料衝突', historicalOrders.previewState.preview.currentConflictCount]] : []} onSelect={historicalOrders.selectWorkbook} onPreview={historicalOrders.previewWorkbook} onConfirm={historicalOrders.setConfirmed} onApply={historicalOrders.applyWorkbook} previewDetail={historicalOrderPreviewIssues} reviewAction={historicalOrderReviewActions} />}
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
          {hcmCorrection && <HcmControlledCorrectionWorkbench {...hcmCorrection} onCancel={() => setHcmCorrection(null)} onApplied={() => {
            setHcmReviewRows((current) => current.filter((row) => row.problem_identity !== hcmCorrection.reviewIdentity));
            setHcmCorrection(null);
          }} />}
        </div>
      )}

      {activeTab === 'data-browser' && <DataBrowserPage />}

    </div>
  );
};

export default DataImportPage;
