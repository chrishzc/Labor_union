/**
 * File: HistoricalCompletionPanel.tsx
 * Description: 顯示 Step 11 fresh owner roots、active alerts 與 owner referral，不推斷完成狀態。
 */
import { useEffect, useState } from 'react';
import { useUnsavedDraft } from './UnsavedChanges';
import { ApiHttpError } from '../api/shared/typed_errors';
import {
  HistoricalCompletionContractError,
  historicalCompletionClient,
  type HistoricalCompletionClient,
} from '../api/orders/historical_completion_client';
import type { HistoricalCompletion } from '../api/orders/historical_completion_schemas';
import type {
  HistoricalCompletionPreview,
  HistoricalCompletionReceipt,
} from '../api/orders/historical_completion_schemas';

const OWNER_LABELS: Readonly<Record<string, string>> = {
  orders: '訂單管理',
  scheduling: '排班管理',
  client_finance: '客戶帳務',
  staff_payables: '月嫂薪資',
};

const REFERRAL_LABELS: Readonly<Record<string, string>> = {
  'orders.completion': '訂單完成資料',
  'orders.actual_start': '訂單實際開始資料',
  'scheduling.official_service_facts': '排班與服務資料',
  'client_finance.settlement': '客戶帳務結清',
  'staff_payables.payout': '服務人員款項',
};

type QueryState =
  | { kind: 'loading' }
  | { kind: 'ready'; projection: HistoricalCompletion }
  | { kind: 'error'; message: string };

type CompletionActionState =
  | { kind: 'idle' }
  | { kind: 'previewing' }
  | { kind: 'applying'; preview: HistoricalCompletionPreview }
  | { kind: 'success'; receipt: HistoricalCompletionReceipt }
  | { kind: 'outcome_unknown'; message: string }
  | { kind: 'error'; message: string };


export interface HistoricalCompletionPanelProps {
  caseNo: string;
  client?: HistoricalCompletionClient;
  onCompleted?: () => void;
}

export function HistoricalCompletionPanel({
  caseNo,
  client = historicalCompletionClient,
  onCompleted,
}: HistoricalCompletionPanelProps) {
  const [state, setState] = useState<QueryState>({ kind: 'loading' });
  const [reason, setReason] = useState('');
  const [action, setAction] = useState<CompletionActionState>({ kind: 'idle' });
  useUnsavedDraft('歷史案件帳務完成', { '完成原因': reason }, { baseline: { '完成原因': '' }, busy: ['previewing', 'applying', 'outcome_unknown'].includes(action.kind), save: () => loadPreview(), discard: () => setReason('') });

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: 'loading' });
    setAction({ kind: 'idle' });
    void client.query(caseNo, { signal: controller.signal })
      .then((projection) => setState({ kind: 'ready', projection }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          kind: 'error',
          message: error instanceof HistoricalCompletionContractError
            ? error.message
            : '歷史案件完成狀態目前無法載入。',
        });
      });
    return () => controller.abort();
  }, [caseNo, client]);

  if (state.kind === 'loading') {
    return <p role="status">正在確認歷史案件的完成資料…</p>;
  }
  if (state.kind === 'error') {
    return <p role="alert">{state.message}</p>;
  }

  const { projection } = state;
  const loadPreview = async () => {
    setAction({ kind: 'previewing' });
    try {
      const preview = await client.preview(caseNo);
      await applyCompletion(preview);
    } catch (error: unknown) {
      setAction({
        kind: 'error',
        message: error instanceof HistoricalCompletionContractError
          ? error.message
          : '帳務完成預覽目前無法建立，請重新確認帳務狀態。',
      });
    }
  };
  const applyCompletion = async (preview: HistoricalCompletionPreview) => {
    setAction({ kind: 'applying', preview });
    try {
      const receipt = await client.apply(preview, reason.trim());
      setReason('');
      setAction({ kind: 'success', receipt });
    } catch (error: unknown) {
      const rejected = (error instanceof ApiHttpError && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429) || (error instanceof HistoricalCompletionContractError && error.code === 'historical_completion_unauthenticated');
      setAction(rejected
        ? { kind: 'error', message: error.message }
        : { kind: 'outcome_unknown', message: '帳務完成結果尚未確認；請重新查詢目前資料，勿重複送出。' });
      return;
    }
    onCompleted?.();
  };
  return (
    <section
      aria-label="歷史案件完成根事實"
      data-surface-id="order-tracker.historical-completion"
      data-status={projection.step_11_status}
    >
      <p role="status">
        {projection.step_11_completed
          ? '訂單、服務資料、客戶帳務與月嫂款項皆已確認完成。'
          : projection.state === 'unavailable'
            ? '至少一項必要資料目前無法取得，暫時無法確認帳務完成。'
            : `尚有 ${projection.active_alerts.length} 項必要資料待處理，暫時無法確認帳務完成。`}
      </p>
      {projection.active_alerts.length > 0 && (
        <ul aria-label="待處理項目">
          {projection.active_alerts.map((alert) => (
            <li key={`${alert.owner}:${alert.field_path}:${alert.code}`}>
              <strong>{OWNER_LABELS[alert.owner]}</strong>：尚有資料待完成
              <span>（前往：{REFERRAL_LABELS[alert.referral]}）</span>
            </li>
          ))}
        </ul>
      )}
      {projection.step_11_completed && action.kind === 'idle' && (<><label>完成原因（選填）<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label>
        <button type="button" onClick={() => void loadPreview()}>
          儲存帳務完成
        </button></>
      )}
      {action.kind === 'previewing' && <p role="status">正在檢核帳務完成資料…</p>}
      {action.kind === 'applying' && <p role="status">正在推進至帳務完成…</p>}
      {action.kind === 'success' && (
        <p role="status">已推進至{action.receipt.after_status}（訂單版本 {action.receipt.resulting_order_version}）。</p>
      )}
      {action.kind === 'outcome_unknown' && <p role="alert">{action.message}<button type="button" onClick={() => {
        void client.query(caseNo).then(projection => setState({ kind: 'ready', projection })).catch(() => setAction({ kind: 'outcome_unknown', message: '帳務完成結果查詢失敗；請再次重新查詢。' }));
      }}>重新查詢帳務完成結果</button></p>}
      {action.kind === 'error' && (
        <p role="alert">
          {action.message}
          <button type="button" onClick={() => setAction({ kind: 'idle' })}>重新操作</button>
        </p>
      )}

    </section>
  );
}
