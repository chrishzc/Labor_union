import { useUnsavedDraft } from '../components/UnsavedChanges';
/** 四種工作簿匯入共用選檔、確認與互斥的結果筆數呈現。 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adaptClientBeClassWorkbookPreview } from '../adapters/case_import/client_beclass_workbook_adapter';
import { adaptHcmWorkbookPreview } from '../adapters/case_import/hcm_workbook_adapter';
import { adaptStaffHistoricalWorkbookPreview } from '../adapters/case_import/staff_historical_workbook_adapter';
import { adaptHistoricalOrderWorkbookPreview } from '../adapters/orders/historical_order_workbook_adapter';
import { adaptClientBeClassImportResult, adaptHcmImportResult, adaptHistoricalOrderImportResult, adaptStaffHistoricalImportResult, type WorkbookImportResult } from '../adapters/workbook_import_result_adapter';
import { ClientBeClassWorkbookSnapshot, clientBeClassWorkbookPreviewClient } from '../api/case_import/client_beclass_workbook/client';
import { HcmWorkbookSnapshot, hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
import { StaffHistoricalWorkbookSnapshot, staffHistoricalWorkbookPreviewClient } from '../api/case_import/staff_historical_workbook/client';
import { HistoricalOrderWorkbookSnapshot, historicalOrderWorkbookPreviewClient } from '../api/orders/historical_order_workbook/client';
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
  | { kind: 'ready'; result: WorkbookImportResult }
  | { kind: 'error'; message: string; outcomeUnknown: boolean; autoConfirm: boolean };

function isOutcomeUnknown(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'retryable' in error && error.retryable === true;
}

function canConfirmAutomatically(error: unknown): boolean {
  if (!isOutcomeUnknown(error) || typeof error !== 'object' || error === null || !('code' in error)) return false;
  const code = String(error.code);
  return code.endsWith('_lock_timeout') || code.endsWith('_apply_timeout') || code.endsWith('_apply_network_error')
    || ('status' in error && (error.status === 502 || error.status === 504));
}

function workbookErrorMessage(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : fallback;
  return typeof error === 'object' && error !== null && 'code' in error ? `${message}（錯誤代碼：${String(error.code)}）` : message;
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
  if (applyState.kind === 'ready') return '本次檔案已處理完成。';
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
  summarize: (receipt: TReceipt) => WorkbookImportResult,
  fallbackError: string,
  scope: string
) {
  const [selectedWorkbook, setSelectedWorkbook] = useState<File | null>(null);
  const [previewState, setPreviewState] = useState<CasePreviewState<TModel>>({ kind: 'idle' });
  const [applyState, setApplyState] = useState<ApplyState>({ kind: 'idle' });
  const [confirmed, setConfirmed] = useState(false);
  const [waitingStopped, setWaitingStopped] = useState(false);
  const waitingStoppedRef = useRef(false);
  const snapshotRef = useRef<TSnapshot | null>(null);
  const commandRef = useRef<{ idempotencyKey: string; correlationId: string } | null>(null);
  const generationRef = useRef(0);
  const confirmationAttemptsRef = useRef(0);
  const applyInFlightRef = useRef(false);
  const previewAbortRef = useRef<AbortController | null>(null);
  const mutationLocked = applyState.kind === 'loading' || (applyState.kind === 'error' && applyState.outcomeUnknown);
  const navigationLocked = mutationLocked && !waitingStopped;

  useEffect(() => () => {
    previewAbortRef.current?.abort();
    generationRef.current += 1;
  }, []);

  const selectWorkbook = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (mutationLocked) return;
    waitingStoppedRef.current = false;
    setWaitingStopped(false);
    previewAbortRef.current?.abort();
    generationRef.current += 1;
    setSelectedWorkbook(event.target.files?.[0] ?? null);
    setPreviewState({ kind: 'idle' });
    setApplyState({ kind: 'idle' });
    setConfirmed(false);
    snapshotRef.current = null;
    commandRef.current = null;
    confirmationAttemptsRef.current = 0;
  };

  const clearWorkbook = () => {
    if (mutationLocked) return;
    waitingStoppedRef.current = false;
    setWaitingStopped(false);
    previewAbortRef.current?.abort();
    previewAbortRef.current = null;
    generationRef.current += 1;
    setSelectedWorkbook(null);
    setPreviewState({ kind: 'idle' });
    setApplyState({ kind: 'idle' });
    setConfirmed(false);
    snapshotRef.current = null;
    commandRef.current = null;
    confirmationAttemptsRef.current = 0;
  };

  const previewWorkbook = async () => {
    if (mutationLocked) return;
    if (selectedWorkbook === null) {
      setPreviewState({ kind: 'error', message: '請先選擇 .xlsx 檔案。' });
      return;
    }
    waitingStoppedRef.current = false;
    setWaitingStopped(false);
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
      confirmationAttemptsRef.current = 0;
      setConfirmed(false);
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current) return;
      setPreviewState({ kind: 'error', message: workbookErrorMessage(error, fallbackError) });
    } finally {
      if (previewAbortRef.current === controller) previewAbortRef.current = null;
    }
  };

  const applyWorkbook = useCallback(async () => {
    const snapshot = snapshotRef.current;
    const command = commandRef.current;
    if (applyInFlightRef.current || !confirmed || snapshot === null || command === null || previewState.kind !== 'ready') return;
    waitingStoppedRef.current = false;
    setWaitingStopped(false);
    applyInFlightRef.current = true;
    const generation = generationRef.current;
    setApplyState({ kind: 'loading' });
    try {
      const receipt = await apply(snapshot, previewState.preview.previewFingerprint, command);
      const presentation = summarize(receipt);
      if (generation !== generationRef.current) return;
      setApplyState({ kind: 'ready', result: presentation });
    } catch (error) {
      if (generation !== generationRef.current) return;
      setApplyState({
        kind: 'error',
        message: workbookErrorMessage(error, '工作簿套用失敗。'),
        outcomeUnknown: isOutcomeUnknown(error),
        autoConfirm: !waitingStoppedRef.current && canConfirmAutomatically(error) && confirmationAttemptsRef.current < 6,
      });
    } finally {
      applyInFlightRef.current = false;
    }
  }, [confirmed, previewState, apply, summarize]);

  useEffect(() => {
    if (waitingStopped || applyState.kind !== 'error' || !applyState.autoConfirm) return undefined;
    const timer = window.setTimeout(() => {
      if (waitingStoppedRef.current) return;
      confirmationAttemptsRef.current += 1;
      void applyWorkbook();
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [applyState, applyWorkbook, waitingStopped]);
  const stopWaiting = () => {
    waitingStoppedRef.current = true;
    setWaitingStopped(true);
  };
  useUnsavedDraft(({ 'hcm-current': 'HCM 案件匯入', 'client-beclass': '客戶 BeClass 匯入', 'staff-historical': '月嫂歷史匯入', 'historical-orders-authoritative-v3': '歷史訂單匯入' } as Record<string, string>)[scope] ?? '工作簿匯入', { '待匯入檔案': selectedWorkbook?.name ?? '' }, { baseline: { '待匯入檔案': '' }, enabled: applyState.kind !== 'ready' && !waitingStopped, busy: navigationLocked });


  return { selectedWorkbook, previewState, applyState, confirmed, mutationLocked, navigationLocked, waitingStopped, stopWaiting, setConfirmed, selectWorkbook, clearWorkbook, previewWorkbook, applyWorkbook };
}

interface CaseWorkbookPreviewCardProps {
  id: string;
  title: string;
  inputLabel: string;
  openPreviewControlId?: string;
  selectedWorkbook: File | null;
  previewState: CasePreviewState<{ sourceContentDigest: string; previewFingerprint: string; sourceRowCount: number }>;
  applyState: ApplyState;
  confirmed: boolean;
  mutationLocked: boolean;
  waitingStopped: boolean;
  onStopWaiting: () => void;
  onSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onClear: () => void;
  onPreview: () => Promise<void>;
  onConfirm: (confirmed: boolean) => void;
  onApply: () => Promise<void>;
}

const CaseWorkbookPreviewCard: React.FC<CaseWorkbookPreviewCardProps> = ({
  id, title, inputLabel, openPreviewControlId, selectedWorkbook, previewState, applyState, confirmed, mutationLocked, waitingStopped, onStopWaiting, onSelect, onClear, onPreview, onConfirm, onApply,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const ready = previewState.kind === 'ready';
  const done = applyState.kind === 'ready';
  const loading = applyState.kind === 'loading';
  const waiting = !waitingStopped && (loading || (applyState.kind === 'error' && applyState.autoConfirm));
  const unknown = (applyState.kind === 'error' && applyState.outcomeUnknown) || (waitingStopped && loading);
  const result = done ? applyState.result : null;
  const status = waiting ? '匯入處理中' : unknown ? '結果待確認' : done ? '已完成' : ready ? '待確認' : '待選檔';
  const previewGuidanceId = `imports-${id}-preview-guidance`;
  const applyGuidanceId = `imports-${id}-apply-guidance`;
  const metrics: Array<[string, number | null, string]> = [
    ['來源筆數', result?.sourceCount ?? (ready ? previewState.preview.sourceRowCount : null), 'source'],
    ['成功匯入', result?.importedCount ?? null, 'success'],
    ['重複略過', result?.duplicateCount ?? null, 'skipped'],
    ['未匯入', result?.notImportedCount ?? null, 'not-imported'],
  ];
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
        {(!ready || (applyState.kind === 'error' && !unknown)) && <button type="button" data-control-id={`imports.${id}.preview`} aria-describedby={!ready ? previewGuidanceId : undefined} className="import-preview-btn" disabled={mutationLocked || selectedWorkbook === null || previewState.kind === 'reading' || previewState.kind === 'loading'} onClick={() => void onPreview()}>
          {previewState.kind === 'reading' ? '正在讀取檔案…' : previewState.kind === 'loading' ? '預覽中…' : ready ? '重新預覽' : '預覽檔案'}
        </button>}
        {selectedWorkbook && !done && !mutationLocked && <button type="button" className="import-simple-clear" onClick={() => { if (fileInputRef.current) fileInputRef.current.value = ''; onClear(); }}>取消選取檔案</button>}
      </div>
      {!ready && <p id={previewGuidanceId} className="import-control-guidance">{previewControlGuidance(selectedWorkbook, previewState)}</p>}
      {previewState.kind === 'error' && <div className="import-error" role="alert">{previewState.message}</div>}
      {ready && !loading && !unknown && <section data-surface-id={`imports.${id}.${done ? 'result' : 'preview-result'}`} className="import-simple-result" aria-label={done ? '匯入結果' : '預覽結果'} aria-live="polite">
        <header className="import-simple-result-heading"><h3>{done ? '匯入結果' : '預覽結果'}</h3><span>{result?.replayedWorkbook ? '已處理過，以下為原處理結果' : done && result?.importedCount === null ? '舊紀錄未提供完整筆數' : done ? '本次處理筆數' : '匯入後顯示實際結果'}</span></header>
        <dl className="import-simple-metrics">{metrics.map(([label, value, className]) => <div key={label} className={className}><dt>{label}</dt><dd><span>{value ?? '—'}</span>{value !== null && <small>筆</small>}</dd></div>)}</dl>
        {result && result.notImportedCount !== 0 && <section className="import-not-imported-details" aria-label="未匯入明細">
          <h4>未匯入明細</h4>
          {result.notImportedRows === null ? <p>這份匯入收據未保存逐筆明細，無法從收據確認未匯入的是哪些資料。</p> : <div className="import-details-scroll"><table>
            <thead><tr><th scope="col">{id === 'hcm-current' ? '來源資料序號' : 'Excel 列號'}</th><th scope="col">案件／查詢編號</th><th scope="col">問題欄位</th><th scope="col">未匯入原因</th></tr></thead>
            <tbody>{result.notImportedRows.map(row => <tr key={row.sourceRow}><td>{row.sourceRow}</td><td>{row.identifier || '未提供（依來源位置定位）'}</td><td>{row.fields.join('、') || '—'}</td><td>{row.reasons.join('；') || '資料未通過匯入檢查'}</td></tr>)}</tbody>
          </table></div>}
        </section>}
      </section>}
      {waiting && <p className="import-simple-busy" role="status">正在等待匯入結果，資料量較多或連線較慢時可能需要較長時間。請稍候，保持此頁開啟，勿重新整理或重複上傳。</p>}
      {mutationLocked && !waitingStopped && <div className="import-simple-actions"><p>可停止等待並切換頁面。已送出的匯入不會因此取消，也不會撤銷已寫入的資料。離頁後需重新選取原檔案確認結果。</p><button type="button" className="import-simple-secondary" onClick={onStopWaiting}>停止等待</button></div>}
      {ready && !waiting && <footer className="import-simple-actions">
        {done ? <><p role="status">本次檔案已處理完成。</p><button type="button" className="import-apply-btn" onClick={() => fileInputRef.current?.click()}>匯入下一份檔案</button></> : <>
          <div><label><input type="checkbox" checked={confirmed} disabled={mutationLocked} onChange={event => onConfirm(event.target.checked)} />我已核對檔案名稱與預覽筆數</label><p id={applyGuidanceId} className="import-control-guidance">{waitingStopped && unknown ? '可切換頁面；保留本頁時仍可接收原請求結果，或在原請求結束後查詢。' : applyControlGuidance(previewState, confirmed, applyState)}</p></div>
          <button type="button" data-control-id={`imports.${id}.apply`} aria-describedby={applyGuidanceId} className="import-apply-btn" disabled={!confirmed || loading || (mutationLocked && !unknown)} onClick={() => void onApply()}>{unknown ? '查詢這次匯入結果' : '確認匯入'}</button>
        </>}
      </footer>}
      {!ready && <p className="import-control-guidance">預覽成功後才能確認匯入。</p>}
      {applyState.kind === 'error' && !applyState.outcomeUnknown && <div className="import-error" role="alert">{applyState.message}</div>}
      {unknown && !waiting && <p className="import-result-state" role="status">{waitingStopped ? '已停止等待與後續自動查詢，可以切換至其他頁面。後端處理結果仍待確認，這不代表匯入已取消。' : '等待時間較長，目前尚未取得最終結果，這不代表匯入失敗。請保留本頁，稍後點選「查詢這次匯入結果」。'}{waitingStopped && loading && '原請求仍在等待回應，暫不重複送出查詢。'}</p>}
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
    adaptHistoricalOrderWorkbookPreview, adaptHistoricalOrderImportResult, '歷史訂單工作簿處理失敗。', 'historical-orders-authoritative-v3');
  const mutationLocked = hcmCurrent.mutationLocked || clientBeClass.mutationLocked || staffHistorical.mutationLocked || historicalOrders.mutationLocked;
  const navigationLocked = hcmCurrent.navigationLocked || clientBeClass.navigationLocked || staffHistorical.navigationLocked || historicalOrders.navigationLocked;
  useEffect(() => {
    if (!navigationLocked) return undefined;
    const preventUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const preventInAppNavigation = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target?.closest('a[href^="#"], .brand-section, .section-tab-btn, .sidebar-nav-item, .notification-btn, .logout-action-btn')) return;
      event.preventDefault(); event.stopPropagation();
    };
    window.addEventListener('beforeunload', preventUnload);
    document.addEventListener('click', preventInAppNavigation, true);
    return () => { window.removeEventListener('beforeunload', preventUnload); document.removeEventListener('click', preventInAppNavigation, true); };
  }, [navigationLocked]);
  const cards = {
    'hcm-current': { flow: hcmCurrent, title: 'HCM 案件匯入', inputLabel: '選擇 HCM Current Workbook' },
    'client-beclass': { flow: clientBeClass, title: '客戶 BeClass 匯入', inputLabel: '選擇客戶 BeClass Workbook' },
    'staff-historical': { flow: staffHistorical, title: '月嫂歷史資料匯入', inputLabel: '選擇月嫂歷史 Workbook' },
    'historic-orders': { flow: historicalOrders, title: '歷史訂單匯入', inputLabel: '選擇歷史訂單 Workbook' },
  };
  const { flow, title, inputLabel } = cards[activeImportKind];
  return <div data-surface-id="imports.page" className="import-page-container import-simple-page">
    <header className="import-simple-page-heading"><h1>批次資料匯入</h1><p>選擇檔案，預覽核對後確認匯入。</p></header>
    {navigationLocked && <p className="import-result-state" role="status" data-surface-id="imports.apply-navigation-lock">匯入已送出或結果尚未確認；請等待結果，或點選「停止等待」後切換至其他頁面。</p>}
    <nav className="import-kind-selector" aria-label="選擇匯入類型"><div>{WORKBOOK_IMPORT_OPTIONS.map(option => <button type="button" key={option.kind} className={activeImportKind === option.kind ? 'active' : ''} aria-pressed={activeImportKind === option.kind} disabled={mutationLocked} onClick={() => setActiveImportKind(option.kind)}>{option.label}</button>)}</div></nav>
    <CaseWorkbookPreviewCard key={activeImportKind} id={activeImportKind} title={title} inputLabel={inputLabel} openPreviewControlId={activeImportKind === 'hcm-current' ? 'imports.hcm-current.open-preview' : undefined}
      selectedWorkbook={flow.selectedWorkbook} previewState={flow.previewState} applyState={flow.applyState} confirmed={flow.confirmed} mutationLocked={mutationLocked}
      waitingStopped={flow.waitingStopped} onStopWaiting={flow.stopWaiting}
      onSelect={flow.selectWorkbook} onClear={flow.clearWorkbook} onPreview={flow.previewWorkbook} onConfirm={flow.setConfirmed} onApply={flow.applyWorkbook} />
  </div>;
};
export default DataImportPage;
