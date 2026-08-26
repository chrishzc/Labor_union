/**
 * File: SystemStatusPage.tsx
 * Description: 顯示系統本次啟動後的唯讀回應狀態摘要，並提供去敏錯誤與重試指引。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './SystemStatusPage.css';
import {
  fetchPerformanceSnapshot,
  type PerformanceSnapshot,
} from '../api/system/system_status_client';

export const SYSTEM_STATUS_ENTRY_IDENTITY = 'ui-react:#system-status';

type QueryState =
  | { kind: 'loading' }
  | { kind: 'success'; snapshot: PerformanceSnapshot }
  | { kind: 'error'; message: string };

const SYSTEM_STATUS_UNAVAILABLE_MESSAGE =
  '請確認系統服務已啟動後再試；此畫面未取得資料，不代表服務一定中斷。';

function systemStatusErrorMessage(error: unknown): string {
  return (error as { code?: unknown })?.code === 'SYSTEM_STATUS_UNAUTHENTICATED'
    ? '請先完成管理員登入後再查詢系統狀態。'
    : SYSTEM_STATUS_UNAVAILABLE_MESSAGE;
}

function metricValue(value: number | null, suffix = ''): string {
  return value === null ? '未提供' : `${value}${suffix}`;
}

export const SystemStatusPage: React.FC = () => {
  const [state, setState] = useState<QueryState>({ kind: 'loading' });
  const requestSequence = useRef(0);

  const loadSnapshot = useCallback(() => {
    const sequence = ++requestSequence.current;
    setState({ kind: 'loading' });

    void fetchPerformanceSnapshot()
      .then((snapshot) => {
        if (sequence !== requestSequence.current) return;
        setState({ kind: 'success', snapshot });
      })
      .catch((error: unknown) => {
        if (sequence !== requestSequence.current) return;
        setState({ kind: 'error', message: systemStatusErrorMessage(error) });
      });
  }, []);

  useEffect(() => {
    loadSnapshot();
    return () => {
      requestSequence.current += 1;
    };
  }, [loadSnapshot]);

  return (
    <div
      className="system-status-page"
      data-surface-id="system-status.page"
      data-testid="system-status.page"
      data-entry-identity={SYSTEM_STATUS_ENTRY_IDENTITY}
    >
      <header className="page-header-banner system-status-page-header">
        <div>
          <h1 className="page-title">🩺 系統狀態</h1>
          <p className="page-subtitle">
            顯示本次服務啟動後的回應速度摘要；服務重新啟動後會重新計算。
          </p>
        </div>
        <button
          type="button"
          className="system-status-reload-button"
          data-control-id="system-status.query.retry"
          onClick={loadSnapshot}
          disabled={state.kind === 'loading'}
        >
          更新系統狀態
        </button>
      </header>

      {state.kind === 'loading' && (
        <section
          className="system-status-state"
          data-surface-id="system-status.query.loading"
          role="status"
        >
          正在讀取系統狀態…
        </section>
      )}

      {state.kind === 'error' && (
        <section
          className="system-status-state system-status-error"
          data-surface-id="system-status.query.error"
          data-testid="system-status.query.error"
          role="alert"
        >
          <strong>目前無法取得系統狀態</strong>
          <span>{state.message}</span>
          <button
            type="button"
            data-control-id="system-status.query.retry"
            onClick={loadSnapshot}
          >
            重試查詢
          </button>
        </section>
      )}

      {state.kind === 'success' && (
        <section
          className="system-status-snapshot"
          data-surface-id="system-status.query.success"
          data-testid="system-status.query.success"
          aria-label="系統狀態摘要"
        >
          <dl className="system-status-metrics">
            <div data-testid="system-status.metric.started-at">
              <dt>服務啟動時間</dt>
              <dd>{state.snapshot.started_at}</dd>
            </div>
            <div data-testid="system-status.metric.request-count">
              <dt>本次啟動後測量次數</dt>
              <dd>{state.snapshot.request_count}</dd>
            </div>
            <div data-testid="system-status.metric.average-response-time">
              <dt>平均回應時間</dt>
              <dd>{metricValue(state.snapshot.average_response_time_ms, ' 毫秒')}</dd>
            </div>
            <div data-testid="system-status.metric.p50-response-time">
              <dt>一半請求的回應時間不超過</dt>
              <dd>{metricValue(state.snapshot.p50_response_time_upper_bound_ms, ' 毫秒')}</dd>
            </div>
            <div data-testid="system-status.metric.p95-response-time">
              <dt>大多數請求的回應時間不超過</dt>
              <dd>{metricValue(state.snapshot.p95_response_time_upper_bound_ms, ' 毫秒')}</dd>
            </div>
            <div data-testid="system-status.metric.maximum-response-time">
              <dt>最慢回應時間</dt>
              <dd>{metricValue(state.snapshot.maximum_response_time_ms, ' 毫秒')}</dd>
            </div>
          </dl>
        </section>
      )}
    </div>
  );
};

export default SystemStatusPage;
