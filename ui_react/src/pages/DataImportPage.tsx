/**
 * File: DataImportPage.tsx
 * Description: 提供四種工作簿匯入選檔、互斥結果筆數、未匯入明細與錯誤列號案件明細呈現。
 */
import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { ClientBeClassWorkbookPairing } from '../components/ClientBeClassWorkbookPairing';
import { useUnsavedDraft } from '../components/UnsavedChanges';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adaptClientBeClassWorkbookPreview, type ClientBeClassWorkbookPreviewModel } from '../adapters/case_import/client_beclass_workbook_adapter';
import { adaptHcmWorkbookPreview } from '../adapters/case_import/hcm_workbook_adapter';
import { adaptStaffHistoricalWorkbookPreview } from '../adapters/case_import/staff_historical_workbook_adapter';
import { adaptHistoricalOrderWorkbookPreview } from '../adapters/orders/historical_order_workbook_adapter';
import { adaptClientBeClassImportResult, adaptHcmImportResult, adaptHistoricalOrderImportResult, adaptStaffHistoricalImportResult, type WorkbookImportResult } from '../adapters/workbook_import_result_adapter';
import { ClientBeClassWorkbookSnapshot, clientBeClassWorkbookPreviewClient } from '../api/case_import/client_beclass_workbook/client';
import type { ClientBeClassPairing } from '../api/case_import/client_beclass_workbook/schemas';
import { HcmWorkbookSnapshot, hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
import { StaffHistoricalWorkbookSnapshot, staffHistoricalWorkbookPreviewClient } from '../api/case_import/staff_historical_workbook/client';
import { HistoricalOrderWorkbookSnapshot, historicalOrderWorkbookPreviewClient } from '../api/orders/historical_order_workbook/client';
import './DataImportPage.css';

interface WorkbookErrorDetail {
  rowLabel: string;
  caseLabel: string;
  message: string;
}

type CasePreviewState<T> =
  | { kind: 'idle' }
  | { kind: 'reading' }
  | { kind: 'loading' }
  | { kind: 'ready'; preview: T }
  | { kind: 'error'; message: string; details: ReadonlyArray<WorkbookErrorDetail> };

type ApplyState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; result: WorkbookImportResult }
  | { kind: 'error'; message: string; details: ReadonlyArray<WorkbookErrorDetail>; outcomeUnknown: boolean; autoConfirm: boolean };

function isOutcomeUnknown(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'retryable' in error && error.retryable === true;
}

function canConfirmAutomatically(error: unknown): boolean {
  if (!isOutcomeUnknown(error) || typeof error !== 'object' || error === null || !('code' in error)) return false;
  const code = String(error.code);
  if (code.startsWith('historical_order_database_')) return false;
  return code.endsWith('_lock_timeout') || code.endsWith('_apply_timeout') || code.endsWith('_apply_network_error')
    || ('status' in error && (error.status === 502 || error.status === 504));
}

function workbookErrorMessage(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : fallback;
  return typeof error === 'object' && error !== null && 'code' in error ? `${message}（錯誤代碼：${String(error.code)}）` : message;
}

function formatRowFieldLabel(field: string): string {
  const match = /^rows?\[([\d,\s]+)\]$/.exec(field.trim());
  if (!match) return field.trim() || '—';
  const rows = match[1].split(',').map(item => item.trim()).filter(Boolean);
  return rows.length > 0 ? `第 ${rows.join('、')} 列` : field.trim();
}

function extractCaseLabel(message: string): string {
  const cases = Array.from(message.matchAll(/案件\s+([^，）\s]+)/g), item => item[1]).filter(Boolean);
  return cases.length > 0 ? [...new Set(cases)].join('、') : '—';
}

function workbookErrorDetails(error: unknown): ReadonlyArray<WorkbookErrorDetail> {
  if (typeof error !== 'object' || error === null || !('fieldErrors' in error) || !Array.isArray(error.fieldErrors)) {
    return [];
  }
  return error.fieldErrors
    .filter((item): item is { field: string; message: string } =>
      typeof item === 'object' && item !== null && 'field' in item && 'message' in item
      && typeof item.field === 'string' && typeof item.message === 'string')
    .map(item => ({
      rowLabel: formatRowFieldLabel(item.field),
      caseLabel: extractCaseLabel(item.message),
      message: item.message,
    }));
}

function previewControlGuidance(
  selectedWorkbook: File | null,
  previewState: CasePreviewState<unknown>
): string {
  if (selectedWorkbook === null) return '請先選擇 .xlsx 工作簿。';
  if (previewState.kind === 'reading' || previewState.kind === 'loading') return '正在檢查檔案，請稍候。';
  if (previewState.kind === 'error') return '預覽未通過：請修正檔案或連線問題後重試。';
  if (previewState.kind === 'ready') return '正在處理匯入。';
  return '檔案已選擇，可以匯入。';
}

function applyControlGuidance(
  previewState: CasePreviewState<unknown>,
  applyState: ApplyState
): string {
  if (previewState.kind !== 'ready') return '選擇檔案後即可匯入。';
  if (applyState.kind === 'loading') return '正在匯入：請勿換檔、離頁或重新整理。';
  if (applyState.kind === 'ready') return '本次檔案已處理完成。';
  if (applyState.kind === 'error' && applyState.outcomeUnknown) return '匯入結果尚未確認，可稍後查詢；離開匯入頁後需重新選取原檔案。';
  if (applyState.kind === 'error') return '匯入未完成：請依錯誤訊息修正後重試。';
  return '可以開始匯入；完成後會顯示結果。';
}

interface WorkbookCommandOptions {
  signal?: AbortSignal;
  idempotencyKey: string;
  correlationId: string;
  manualPairings?: readonly ClientBeClassPairing[];
}

const HISTORICAL_ORDERS_IMPORT = 'historical-orders-authoritative-v3';

function commandIdentity(scope: string, sourceContentDigest: string, manual = false): WorkbookCommandOptions {
  const nonce = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return {
    idempotencyKey: `ui-import-${scope}-${scope === HISTORICAL_ORDERS_IMPORT || manual ? nonce : sourceContentDigest}`,
    correlationId: `ui-import-${scope}-${nonce}`,
  };
}

function useCaseWorkbookFlow<TSnapshot, TRaw, TModel extends { previewFingerprint: string; sourceContentDigest: string; manualRows?: readonly unknown[] }, TReceipt>(
  fromFile: (file: File) => Promise<TSnapshot>,
  preview: (snapshot: TSnapshot, options: { signal?: AbortSignal }) => Promise<TRaw>,
  apply: (snapshot: TSnapshot, previewFingerprint: string, options: WorkbookCommandOptions) => Promise<TReceipt>,
  adapt: (raw: TRaw) => TModel,
  summarize: (receipt: TReceipt) => WorkbookImportResult,
  fallbackError: string,
  scope: string
) {
  const [selectedWorkbook, setSelectedWorkbook] = useState<File | null>(null);
  const [previewState, setPreviewState] = useState<CasePreviewState<TModel>>({ kind: 'idle' });
  const [applyState, setApplyState] = useState<ApplyState>({ kind: 'idle' });
  const snapshotRef = useRef<TSnapshot | null>(null);
  const checkedRef = useRef<TModel | null>(null);
  const commandRef = useRef<WorkbookCommandOptions | null>(null);
  const generationRef = useRef(0);
  const confirmationAttemptsRef = useRef(0);
  const applyInFlightRef = useRef(false);
  const previewAbortRef = useRef<AbortController | null>(null);
  const historicalOrders = scope === HISTORICAL_ORDERS_IMPORT;
  const mutationLocked = previewState.kind === 'reading' || previewState.kind === 'loading' || applyState.kind === 'loading' || (!historicalOrders && applyState.kind === 'error' && applyState.outcomeUnknown);

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
    snapshotRef.current = null;
    checkedRef.current = null;
    commandRef.current = null;
    confirmationAttemptsRef.current = 0;
  };

  const clearWorkbook = () => {
    if (mutationLocked) return;
    previewAbortRef.current?.abort();
    previewAbortRef.current = null;
    generationRef.current += 1;
    setSelectedWorkbook(null);
    setPreviewState({ kind: 'idle' });
    setApplyState({ kind: 'idle' });
    snapshotRef.current = null;
    checkedRef.current = null;
    commandRef.current = null;
    confirmationAttemptsRef.current = 0;
  };

  const previewWorkbook = async () => {
    if (mutationLocked) return;
    if (selectedWorkbook === null) {
      setPreviewState({ kind: 'error', message: '請先選擇 .xlsx 檔案。', details: [] });
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
      checkedRef.current = adapted;
      const recheckingConflict = applyState.kind === 'ready' && applyState.result.requiresRepreview;
      commandRef.current = commandIdentity(scope, adapted.sourceContentDigest, Boolean(adapted.manualRows?.length || recheckingConflict));
      setApplyState({ kind: 'idle' });
      confirmationAttemptsRef.current = 0;
      if (!adapted.manualRows?.length) await applyWorkbook();
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current) return;
      setPreviewState({
        kind: 'error',
        message: workbookErrorMessage(error, fallbackError),
        details: workbookErrorDetails(error),
      });
    } finally {
      if (previewAbortRef.current === controller) previewAbortRef.current = null;
    }
  };

  const applyWorkbook = useCallback(async (manualPairings?: readonly ClientBeClassPairing[]) => {
    const snapshot = snapshotRef.current;
    const command = commandRef.current;
    const checked = checkedRef.current;
    if (applyInFlightRef.current || snapshot === null || command === null || checked === null) return;
    if (manualPairings) {
      if (command.manualPairings) return;
      command.manualPairings = manualPairings;
    }
    if (checked.manualRows?.length && !command.manualPairings?.length) return;
    applyInFlightRef.current = true;
    const generation = generationRef.current;
    setApplyState({ kind: 'loading' });
    try {
      const receipt = await apply(snapshot, checked.previewFingerprint, command);
      const presentation = summarize(receipt);
      if (generation !== generationRef.current) return;
      setApplyState({ kind: 'ready', result: presentation });
    } catch (error) {
      if (generation !== generationRef.current) return;
      setApplyState({
        kind: 'error',
        message: workbookErrorMessage(error, '工作簿套用失敗。'),
        details: workbookErrorDetails(error),
        outcomeUnknown: isOutcomeUnknown(error),
        autoConfirm: !historicalOrders && canConfirmAutomatically(error) && confirmationAttemptsRef.current < 6,
      });
    } finally {
      applyInFlightRef.current = false;
    }
  }, [apply, historicalOrders, summarize]);

  useEffect(() => {
    if (applyState.kind !== 'error' || !applyState.autoConfirm) return undefined;
    const timer = window.setTimeout(() => {
      confirmationAttemptsRef.current += 1;
      void applyWorkbook();
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [applyState, applyWorkbook]);
  useUnsavedDraft(({ 'hcm-current': 'HCM 案件匯入', 'client-beclass': '客戶 BeClass 匯入', 'staff-historical': '月嫂歷史匯入', 'historical-orders-authoritative-v3': '歷史訂單匯入' } as Record<string, string>)[scope] ?? '工作簿匯入', { '待匯入檔案': selectedWorkbook?.name ?? '' }, { baseline: { '待匯入檔案': '' }, enabled: applyState.kind === 'idle' && previewState.kind === 'idle' });


  return { selectedWorkbook, previewState, applyState, mutationLocked, selectWorkbook, clearWorkbook, previewWorkbook, applyWorkbook };
}

const WorkbookErrorAlert: React.FC<{ message: string; details: ReadonlyArray<WorkbookErrorDetail> }> = ({ message, details }) => (
  <div className="import-error" role="alert">
    {details.length === 0 ? message : <>
      <span>{message}</span>
      <div className="import-details-scroll">
        <table className="import-error-details-table" aria-label="衝突與錯誤明細">
          <thead>
            <tr>
              <th scope="col">Excel 列號</th>
              <th scope="col">案件明細</th>
              <th scope="col">衝突／錯誤說明</th>
            </tr>
          </thead>
          <tbody>
            {details.map((detail, index) => (
              <tr key={`${detail.rowLabel}-${detail.caseLabel}-${index}`}>
                <td>{detail.rowLabel}</td>
                <td>{detail.caseLabel}</td>
                <td>{detail.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>}
  </div>
);

interface CaseWorkbookPreviewCardProps {
  id: string;
  title: string;
  inputLabel: string;
  openPreviewControlId?: string;
  selectedWorkbook: File | null;
  previewState: CasePreviewState<{ sourceContentDigest: string; previewFingerprint: string; sourceRowCount: number }>;
  applyState: ApplyState;
  mutationLocked: boolean;
  onSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onClear: () => void;
  onPreview: () => Promise<void>;
  onApply: (pairings?: readonly ClientBeClassPairing[]) => Promise<void>;
  beclassPreview?: ClientBeClassWorkbookPreviewModel;
}

const CaseWorkbookPreviewCard: React.FC<CaseWorkbookPreviewCardProps> = ({
  id, title, inputLabel, openPreviewControlId, selectedWorkbook, previewState, applyState, mutationLocked, onSelect, onClear, onPreview, onApply, beclassPreview,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const historicalOrders = id === 'historic-orders';
  const ready = previewState.kind === 'ready';
  const done = applyState.kind === 'ready';
  const loading = applyState.kind === 'loading';
  const waiting = loading || (applyState.kind === 'error' && applyState.autoConfirm);
  const unknown = applyState.kind === 'error' && applyState.outcomeUnknown;
  const result = done ? applyState.result : null;
  const manual = Boolean(beclassPreview?.manualRows.length);
  const status = waiting ? '匯入處理中' : unknown ? '結果待確認' : done ? '已完成' : ready ? '待確認' : '待選檔';
  const previewGuidanceId = `imports-${id}-preview-guidance`;
  const applyGuidanceId = `imports-${id}-apply-guidance`;
  const metrics: Array<[string, number | null, string]> = [
    ['來源筆數', result?.sourceCount ?? (ready ? previewState.preview.sourceRowCount : null), 'source'],
    ['成功匯入', result?.importedCount ?? null, 'success'],
    [historicalOrders ? '資料已一致' : '重複略過', result?.duplicateCount ?? null, 'skipped'],
    ['未匯入', result?.notImportedCount ?? null, 'not-imported'],
  ];
  if (historicalOrders) metrics.push(['檔外取消', result?.absentOrderCancellationCount ?? null, 'absent-cancelled']);
  return (
    <section className="import-workbench-card" data-surface-id={`imports.${id}.workbench`} aria-labelledby={`imports-${id}-title`}>
      <header className="import-card-header">
        <h2 id={`imports-${id}-title`}>{title}</h2>
        <span className={`import-status-pill ${done ? 'ready' : ready ? 'idle' : 'locked'}`}>{status}</span>
      </header>
      <div className="import-simple-file-section">
        <div className="import-simple-file-text"><span>來源檔案</span><strong>{selectedWorkbook?.name ?? '未選擇任何檔案'}</strong></div>
        <input ref={fileInputRef} id={`file-input-${id}`} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label={inputLabel} data-control-id={openPreviewControlId} disabled={mutationLocked} onChange={onSelect} className="import-file-native-hidden" />
        <button type="button" className="import-simple-secondary" disabled={mutationLocked} onClick={() => fileInputRef.current?.click()}>{selectedWorkbook ? '更換檔案' : '選擇檔案'}</button>
        {(!ready || (!historicalOrders && applyState.kind === 'error' && !unknown)) && <button type="button" data-control-id={`imports.${id}.preview`} aria-describedby={!ready ? previewGuidanceId : undefined} className="import-preview-btn" disabled={mutationLocked || selectedWorkbook === null || previewState.kind === 'reading' || previewState.kind === 'loading'} onClick={() => void onPreview()}>
          {previewState.kind === 'reading' ? '正在讀取檔案…' : previewState.kind === 'loading' ? '處理中…' : ready ? (manual ? '重新預覽' : '重新匯入') : '匯入'}
        </button>}
        {selectedWorkbook && !done && !mutationLocked && <button type="button" className="import-simple-clear" onClick={() => { if (fileInputRef.current) fileInputRef.current.value = ''; onClear(); }}>取消選取檔案</button>}
      </div>
      {!ready && <p id={previewGuidanceId} className="import-control-guidance">{previewControlGuidance(selectedWorkbook, previewState)}</p>}
      {previewState.kind === 'error' && <WorkbookErrorAlert message={previewState.message} details={previewState.details} />}
      {ready && !loading && !unknown && <section data-surface-id={`imports.${id}.${done ? 'result' : 'preview-result'}`} className="import-simple-result" aria-label={done ? '匯入結果' : '預覽結果'} aria-live="polite">
        <header className="import-simple-result-heading"><h3>{done ? '匯入結果' : '預覽結果'}</h3><span>{result?.replayedWorkbook ? '已處理過，以下為原處理結果' : done && result?.importedCount === null ? '舊紀錄未提供完整筆數' : done ? '本次處理筆數' : '匯入後顯示實際結果'}</span></header>
        {(!manual || done) && <dl className="import-simple-metrics">{metrics.map(([label, value, className]) => <div key={label} className={className}><dt>{label}</dt><dd><span>{value ?? '—'}</span>{value !== null && <small>筆</small>}</dd></div>)}</dl>}
        {beclassPreview && manual && applyState.kind === 'idle' &&
          <ClientBeClassWorkbookPairing key={beclassPreview.previewFingerprint} preview={beclassPreview} onConfirm={pairings => void onApply(pairings)} />}
        {!!result?.manualBindings?.length && <details className="import-not-imported-details beclass-binding-results" open>
          <summary>人工綁定明細（{result.manualBindings.length} 筆）</summary>
          <div className="import-details-scroll"><table>
            <thead><tr><th scope="col">Excel 列號</th><th scope="col">BeClass 查詢序號</th><th scope="col">綁定 HCM 案號</th></tr></thead>
            <tbody>{result.manualBindings.map(binding => <tr key={`${binding.source_row}:${binding.case_no}`}>
              <td>{binding.source_row}</td><td>{binding.query_no}</td><td>{binding.case_no}</td>
            </tr>)}</tbody>
          </table></div>
        </details>}
        {result?.payrollIssues && result.payrollIssues.length > 0 && <section className="import-not-imported-details" aria-label="月嫂應付待核對">
          <h4>月嫂應付待核對</h4>
          <div className="import-details-scroll"><table>
            <thead><tr><th scope="col">Excel 列號</th><th scope="col">案件編號</th><th scope="col">略過原因</th></tr></thead>
            <tbody>{result.payrollIssues.map(row => <tr key={row.sourceRow}>
              <td>{row.sourceRow}</td><td>{row.identifier ?? '—'}</td><td>{row.reasons.join('；')}</td>
            </tr>)}</tbody>
          </table></div>
        </section>}
        {result && result.notImportedCount !== 0 && <section className="import-not-imported-details" aria-label="未匯入明細">
          <h4>未匯入明細</h4>
          {result.notImportedRows === null ? <p>這份匯入收據未保存逐筆明細，無法從收據確認未匯入的是哪些資料。</p> : <div className="import-details-scroll"><table>
            <thead><tr><th scope="col">{id === 'hcm-current' ? '來源資料序號' : 'Excel 列號'}</th><th scope="col">案件／查詢編號</th><th scope="col">問題欄位</th><th scope="col">未匯入原因</th></tr></thead>
            <tbody>{result.notImportedRows.map(row => <tr key={row.sourceRow}><td>{row.sourceRow}</td><td>{row.identifier || '未提供（依來源位置定位）'}</td><td>{row.fields.join('、') || '—'}</td><td>{row.reasons.join('；') || '資料未通過匯入檢查'}</td></tr>)}</tbody>
          </table></div>}
        </section>}
      </section>}
      {waiting && <p className="import-simple-busy" role="status">正在等待匯入結果，資料多或連線慢時可能較久。可切換頁面，離開後會停止自動查詢。返回時請選原檔案查詢結果，請勿重複上傳或重新整理。</p>}
      {ready && !waiting && (!manual || done || unknown) && <footer className="import-simple-actions">
        {done ? <><p role="status">本次檔案已處理完成。</p>{result?.requiresRepreview &&
          <button type="button" className="import-simple-secondary" onClick={() => void onPreview()}>重新預覽</button>}
          <button type="button" className="import-apply-btn" onClick={() => historicalOrders ? void onPreview() : fileInputRef.current?.click()}>{historicalOrders ? '重新匯入' : '匯入下一份檔案'}</button></> : <>
          <div><p id={applyGuidanceId} className="import-control-guidance">{historicalOrders && unknown ? '匯入結果尚未確認。' : applyControlGuidance(previewState, applyState)}</p></div>
          <button type="button" data-control-id={`imports.${id}.apply`} aria-describedby={applyGuidanceId} className="import-apply-btn" disabled={loading || (mutationLocked && !unknown)} onClick={() => void (historicalOrders ? onPreview() : onApply())}>{unknown ? (historicalOrders ? '重新匯入' : '查詢這次匯入結果') : '重試匯入'}</button>
        </>}
      </footer>}
      {!ready && <p className="import-control-guidance">選擇檔案後即可匯入。</p>}
      {applyState.kind === 'error' && !applyState.outcomeUnknown && <WorkbookErrorAlert message={applyState.message} details={applyState.details} />}
      {unknown && !waiting && <p className="import-result-state" role="status">{applyState.kind === 'error' && applyState.message} {historicalOrders ? '請查看訂單狀態與變更紀錄。重新匯入會再次檢查整份檔案。' : '匯入結果尚未確認，請稍後查詢。離開後請用原檔查詢。'}</p>}
    </section>
  );
};

type WorkbookImportKind = 'hcm-current' | 'client-beclass' | 'staff-historical' | 'historic-orders';
const WORKBOOK_IMPORT_OPTIONS: ReadonlyArray<{ kind: WorkbookImportKind; label: string }> = [
  { kind: 'hcm-current', label: 'HCM 案件' },
  { kind: 'client-beclass', label: '客戶 BeClass' },
  { kind: 'staff-historical', label: '月嫂歷史資料' },
  { kind: 'historic-orders', label: '歷史訂單' },
];

export const DataImportPage: React.FC = () => {
  const [activeImportKind, setActiveImportKind] = useState<WorkbookImportKind>('hcm-current');
  const hcmCurrent = useCaseWorkbookFlow(HcmWorkbookSnapshot.fromFile,
    (snapshot, options) => hcmWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => hcmWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptHcmWorkbookPreview, adaptHcmImportResult, 'HCM 工作簿處理失敗。', 'hcm-current');
  const clientBeClass = useCaseWorkbookFlow(ClientBeClassWorkbookSnapshot.fromFile,
    (snapshot, options) => clientBeClassWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => clientBeClassWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptClientBeClassWorkbookPreview, adaptClientBeClassImportResult, '客戶 BeClass 工作簿處理失敗。', 'client-beclass');
  const staffHistorical = useCaseWorkbookFlow(StaffHistoricalWorkbookSnapshot.fromFile,
    (snapshot, options) => staffHistoricalWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => staffHistoricalWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptStaffHistoricalWorkbookPreview, adaptStaffHistoricalImportResult, '月嫂歷史工作簿處理失敗。', 'staff-historical');
  const historicalOrders = useCaseWorkbookFlow(HistoricalOrderWorkbookSnapshot.fromFile,
    (snapshot, options) => historicalOrderWorkbookPreviewClient.preview(snapshot, options),
    (snapshot, fingerprint, options) => historicalOrderWorkbookPreviewClient.apply(snapshot, fingerprint, options),
    adaptHistoricalOrderWorkbookPreview, adaptHistoricalOrderImportResult, '歷史訂單工作簿處理失敗。', HISTORICAL_ORDERS_IMPORT);
  const mutationLocked = hcmCurrent.mutationLocked || clientBeClass.mutationLocked || staffHistorical.mutationLocked || historicalOrders.mutationLocked;
  const cards = {
    'hcm-current': { flow: hcmCurrent, title: 'HCM 案件匯入', inputLabel: '選擇 HCM Current Workbook' },
    'client-beclass': { flow: clientBeClass, title: '客戶 BeClass 匯入', inputLabel: '選擇客戶 BeClass Workbook' },
    'staff-historical': { flow: staffHistorical, title: '月嫂歷史資料匯入', inputLabel: '選擇月嫂歷史 Workbook' },
    'historic-orders': { flow: historicalOrders, title: '歷史訂單匯入', inputLabel: '選擇歷史訂單 Workbook' },
  };
  const { flow, title, inputLabel } = cards[activeImportKind];
  return <div data-surface-id="imports.page">
  <ManagementPageHeader title="批次資料匯入" description="選擇檔案後按「匯入」。" />
  <div className="import-page-container import-simple-page">
    <nav className="import-kind-selector" aria-label="選擇匯入類型"><div>{WORKBOOK_IMPORT_OPTIONS.map(option => <button type="button" key={option.kind} className={activeImportKind === option.kind ? 'active' : ''} aria-pressed={activeImportKind === option.kind} onClick={() => setActiveImportKind(option.kind)}>{option.label}</button>)}</div></nav>
    <CaseWorkbookPreviewCard key={activeImportKind} id={activeImportKind} title={title} inputLabel={inputLabel} openPreviewControlId={activeImportKind === 'hcm-current' ? 'imports.hcm-current.open-preview' : undefined}
      beclassPreview={activeImportKind === 'client-beclass' && clientBeClass.previewState.kind === 'ready' ? clientBeClass.previewState.preview : undefined}
      selectedWorkbook={flow.selectedWorkbook} previewState={flow.previewState} applyState={flow.applyState} mutationLocked={mutationLocked}
      onSelect={flow.selectWorkbook} onClear={flow.clearWorkbook} onPreview={flow.previewWorkbook} onApply={flow.applyWorkbook} />
  </div></div>;
};
export default DataImportPage;
