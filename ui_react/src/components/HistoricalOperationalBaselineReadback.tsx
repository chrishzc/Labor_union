/**
 * File: HistoricalOperationalBaselineReadback.tsx
 * Description: 顯示 Orders-owned Historical Operational Baseline Query，不提供 mutation。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  historicalOperationalBaselineClient,
  mapHistoricalOperationalBaselineUnavailable,
  type HistoricalOperationalBaselineClient,
  type HistoricalOperationalBaselineUnavailableError,
} from '../api/orders/historical_operational_baseline_client';
import type { HistoricalOperationalBaseline } from '../api/orders/historical_operational_baseline_schemas';

type QueryState =
  | { kind: 'loading' }
  | { kind: 'ready'; baseline: HistoricalOperationalBaseline }
  | { kind: 'unavailable'; error: HistoricalOperationalBaselineUnavailableError };

export interface HistoricalOperationalBaselineReadbackProps {
  caseNo: string;
  client?: HistoricalOperationalBaselineClient;
}

function stepStateLabel(state: string): string {
  if (state === 'historical_baseline_completed') return '歷史資料已確認';
  if (state === 'in_progress') return '目前進行中';
  return '狀態待確認';
}

function unavailableMessage(error: HistoricalOperationalBaselineUnavailableError): string {
  if (error.status === 401) return '請先登入再讀取歷史案件作業基準。';
  if (error.status === 403) return '目前帳號無權讀取這筆歷史案件作業基準。';
  return error.retryable
    ? '歷史案件作業基準暫時無法讀取，請稍後重試。'
    : '歷史案件作業基準目前無法使用。';
}

export function HistoricalOperationalBaselineReadback({
  caseNo,
  client = historicalOperationalBaselineClient,
}: HistoricalOperationalBaselineReadbackProps) {
  const [state, setState] = useState<QueryState>({ kind: 'loading' });
  const requestSequence = useRef(0);

  const query = useCallback(() => {
    const sequence = ++requestSequence.current;
    const controller = new AbortController();
    setState({ kind: 'loading' });
    void client.queryByCase(caseNo, { signal: controller.signal })
      .then((baseline) => {
        if (sequence === requestSequence.current) setState({ kind: 'ready', baseline });
      })
      .catch((caught: unknown) => {
        if (sequence !== requestSequence.current) return;
        const error = mapHistoricalOperationalBaselineUnavailable(caught);
        if (error.code === 'historical_operational_baseline_aborted') return;
        setState({ kind: 'unavailable', error });
      });
    return controller;
  }, [caseNo, client]);

  useEffect(() => {
    const controller = query();
    return () => {
      requestSequence.current += 1;
      controller.abort();
    };
  }, [query]);

  if (state.kind === 'loading') {
    return <section aria-label="歷史案件作業基準" className="anomalies-recovery-card recovery">
      <div className="anomalies-loading" role="status">正在讀取案件最新的歷史作業基準…</div>
    </section>;
  }

  if (state.kind === 'unavailable') {
    return <section aria-label="歷史案件作業基準" className="anomalies-recovery-card recovery">
      <div className="anomalies-detail-error" role="alert">
        {unavailableMessage(state.error)}
      </div>
      <button className="anomalies-retry-btn" type="button" onClick={() => query()}>
        重新讀取
      </button>
    </section>;
  }

  const { baseline } = state;
  const current = baseline.current_baseline;

  return <section
    aria-label="歷史案件作業基準"
    className="anomalies-recovery-card recovery"
    data-surface-id="orders.historical-operational-baseline"
    data-baseline-step={current?.selected_step ?? 'unset'}
  >
    <h3>歷史案件作業基準</h3>
    <div className="anomaly-recovery-metadata-row">
      <span>案件</span>
      <code>{baseline.case_no}</code>
    </div>
    <div className="anomaly-recovery-metadata-row">
      <span>目前作業基準</span>
      <span>{current === null ? '尚未設定' : `作業步驟 ${current.selected_step}`}</span>
    </div>
    <details className="anomaly-recovery-technical-details">
      <summary>技術詳情與資料來源</summary>
      <div>Orders identity：<code>{baseline.order_identity}</code></div>
      <div>Orders version：<code>{baseline.current_orders_version}</code></div>
      <div>歷史來源：<code>{baseline.historical_provenance.source_event_identity}</code>（v{baseline.historical_provenance.source_version}）</div>
    </details>
    {current === null ? <div className="anomalies-detail-empty">尚未設定歷史案件作業基準。</div> : <div>
      <h4>作業步驟投影</h4>
      <ul aria-label="歷史案件作業步驟">
        {current.step_projection.map((step) => <li key={step.step}>作業步驟 {step.step}：{stepStateLabel(step.state)}</li>)}
      </ul>
    </div>}
  </section>;
}

export default HistoricalOperationalBaselineReadback;
