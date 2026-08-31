/**
 * File: HistoricalCompletionPanel.tsx
 * Description: 顯示 Step 11 fresh owner roots、active alerts 與 owner referral，不推斷完成狀態。
 */
import { useEffect, useState } from 'react';
import {
  HistoricalCompletionContractError,
  historicalCompletionClient,
  type HistoricalCompletionClient,
} from '../api/orders/historical_completion_client';
import type { HistoricalCompletion } from '../api/orders/historical_completion_schemas';

const OWNER_LABELS: Readonly<Record<string, string>> = {
  orders: '訂單管理',
  scheduling: '排班管理',
  client_finance: '客戶帳務',
  staff_payables: '月嫂薪資',
};

const REFERRAL_LABELS: Readonly<Record<string, string>> = {
  'orders.completion': '訂單完成資料',
  'orders.actual_start': '訂單實際開始資料',
  'scheduling.official_service_facts': '正式排班與服務資料',
  'client_finance.settlement': '客戶帳務結清',
  'staff_payables.payout': '服務人員款項',
};

type QueryState =
  | { kind: 'loading' }
  | { kind: 'ready'; projection: HistoricalCompletion }
  | { kind: 'error'; message: string };

export interface HistoricalCompletionPanelProps {
  caseNo: string;
  client?: HistoricalCompletionClient;
}

export function HistoricalCompletionPanel({
  caseNo,
  client = historicalCompletionClient,
}: HistoricalCompletionPanelProps) {
  const [state, setState] = useState<QueryState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: 'loading' });
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
  return (
    <section
      aria-label="歷史案件完成根事實"
      data-surface-id="order-tracker.historical-completion"
      data-status={projection.step_11_status}
    >
      <p role="status">
        {projection.step_11_completed
          ? 'Step 11 所需的訂單、排班、客戶帳務與服務人員款項皆已確認完成。'
          : projection.state === 'unavailable'
            ? '至少一項必要資料目前無法安全取得；Step 11 保持未完成。'
            : `尚有 ${projection.active_alerts.length} 項必要資料待處理；Step 11 保持未完成。`}
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
      <details>
        <summary>技術詳情與資料來源</summary>
        <p>owner 版本 {projection.owner_versions.length} 項；Staff Payables source vector {projection.owner_source_versions.length} 項。</p>
        {projection.active_alerts.map((alert) => (
          <p key={`${alert.owner}:${alert.field_path}:${alert.code}:technical`}>
            {alert.code}｜{alert.field_path}｜{alert.referral}｜{alert.message}
          </p>
        ))}
        <p>source fingerprint：{projection.source_fingerprint}</p>
        <p>projection fingerprint：{projection.projection_fingerprint}</p>
      </details>
    </section>
  );
}
