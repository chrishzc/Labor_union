/**
 * File: HistoricalCompletionPanel.tsx
 * Description: 顯示 Step 11 fresh owner roots、active alerts 與 owner referral，不推斷完成狀態。
 */
import { useEffect, useState } from 'react';
import {
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
          message: error instanceof Error
            ? error.message
            : '歷史案件完成狀態目前無法載入。',
        });
      });
    return () => controller.abort();
  }, [caseNo, client]);

  if (state.kind === 'loading') {
    return <p role="status">正在回讀所有 owner 的 Step 11 根事實…</p>;
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
          ? 'Step 11 已由 Orders、Scheduling、Client Finance 與 Staff Payables 根事實共同確認完成。'
          : projection.state === 'unavailable'
            ? '至少一個 owner readback 無法安全取得；Step 11 與歷史警示保持未完成。'
            : `尚有 ${projection.active_alerts.length} 項 owner 根事實待處理；Step 11 保持未完成。`}
      </p>
      {projection.active_alerts.length > 0 && (
        <ul aria-label="待處理 owner 根事實">
          {projection.active_alerts.map((alert) => (
            <li key={`${alert.owner}:${alert.field_path}:${alert.code}`}>
              <strong>{OWNER_LABELS[alert.owner]}</strong>：{alert.message}
              <span>（處理入口：{alert.referral}）</span>
            </li>
          ))}
        </ul>
      )}
      <p>
        owner 版本 {projection.owner_versions.length} 項；Staff Payables source vector {projection.owner_source_versions.length} 項。
      </p>
    </section>
  );
}
