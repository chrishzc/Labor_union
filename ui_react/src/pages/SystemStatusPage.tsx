/**
 * File: SystemStatusPage.tsx
 * Description: 顯示 ui-react:#system-status 的 server performance snapshot；只提供唯讀查詢與重試。
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

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '無法取得系統效能快照';
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
        setState({ kind: 'error', message: errorMessage(error) });
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
            只顯示本次 server performance snapshot；不以前端預設值推定服務狀態。
          </p>
        </div>
        <button
          type="button"
          className="system-status-reload-button"
          data-control-id="system-status.query.retry"
          onClick={loadSnapshot}
          disabled={state.kind === 'loading'}
        >
          重新載入快照
        </button>
      </header>

      {state.kind === 'loading' && (
        <section
          className="system-status-state"
          data-surface-id="system-status.query.loading"
          role="status"
        >
          正在讀取系統效能快照…
        </section>
      )}

      {state.kind === 'error' && (
        <section
          className="system-status-state system-status-error"
          data-surface-id="system-status.query.error"
          data-testid="system-status.query.error"
          role="alert"
        >
          <strong>系統效能快照無法取得</strong>
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
          aria-label="系統效能快照"
        >
          <dl className="system-status-metrics">
            <div data-testid="system-status.metric.started-at">
              <dt>服務啟動時間</dt>
              <dd>{state.snapshot.started_at}</dd>
            </div>
            <div data-testid="system-status.metric.request-count">
              <dt>請求樣本數</dt>
              <dd>{state.snapshot.request_count}</dd>
            </div>
            <div data-testid="system-status.metric.average-response-time">
              <dt>平均回應時間</dt>
              <dd>{metricValue(state.snapshot.average_response_time_ms, ' ms')}</dd>
            </div>
            <div data-testid="system-status.metric.p50-response-time">
              <dt>p50 回應時間上限</dt>
              <dd>{metricValue(state.snapshot.p50_response_time_upper_bound_ms, ' ms')}</dd>
            </div>
            <div data-testid="system-status.metric.p95-response-time">
              <dt>p95 回應時間上限</dt>
              <dd>{metricValue(state.snapshot.p95_response_time_upper_bound_ms, ' ms')}</dd>
            </div>
            <div data-testid="system-status.metric.maximum-response-time">
              <dt>最大回應時間</dt>
              <dd>{metricValue(state.snapshot.maximum_response_time_ms, ' ms')}</dd>
            </div>
          </dl>
        </section>
      )}
    </div>
  );
};

export default SystemStatusPage;
