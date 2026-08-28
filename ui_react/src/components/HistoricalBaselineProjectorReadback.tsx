/**
 * File: HistoricalBaselineProjectorReadback.tsx
 * Description: 顯示 server-owned HPROJ delivery、active membership 與修復轉介，不提供 mutation。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  historicalBaselineProjectorClient,
  mapHistoricalBaselineProjectorUnavailable,
  type HistoricalBaselineProjectorClient,
  type HistoricalBaselineProjectorUnavailableError,
} from '../api/anomalies/historical_baseline_projector_client';
import type { HistoricalBaselineProjectorReadModel } from '../api/anomalies/historical_baseline_projector_schemas';

type QueryState =
  | { kind: 'loading' }
  | { kind: 'ready'; projection: HistoricalBaselineProjectorReadModel }
  | { kind: 'unavailable'; error: HistoricalBaselineProjectorUnavailableError };

export interface HistoricalBaselineProjectorReadbackProps {
  caseNo: string;
  client?: HistoricalBaselineProjectorClient;
}

const reconciliationLabels = {
  processed: '回讀已精確確認',
  not_ready: 'projector 尚未完成',
  outcome_unknown: '提交後結果尚未確認',
} as const;

export function HistoricalBaselineProjectorReadback({
  caseNo,
  client = historicalBaselineProjectorClient,
}: HistoricalBaselineProjectorReadbackProps) {
  const [state, setState] = useState<QueryState>({ kind: 'loading' });
  const requestSequence = useRef(0);

  const query = useCallback(() => {
    const sequence = ++requestSequence.current;
    const controller = new AbortController();
    setState({ kind: 'loading' });
    void client.queryByCase(caseNo, { signal: controller.signal })
      .then((projection) => {
        if (sequence === requestSequence.current) setState({ kind: 'ready', projection });
      })
      .catch((caught: unknown) => {
        if (sequence !== requestSequence.current) return;
        const error = mapHistoricalBaselineProjectorUnavailable(caught);
        if (error.code === 'historical_baseline_projection_aborted') return;
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
    return <section aria-label="歷史基線投影回讀" className="anomalies-recovery-card recovery">
      <div className="anomalies-loading" role="status">正在讀取案件最新的歷史基線投影…</div>
    </section>;
  }

  if (state.kind === 'unavailable') {
    return <section aria-label="歷史基線投影回讀" className="anomalies-recovery-card recovery">
      <div className="anomalies-detail-error" role="alert">
        歷史基線投影回讀目前無法使用（{state.error.code}）。
      </div>
      <button className="anomalies-retry-btn" type="button" onClick={() => query()}>
        重新讀取
      </button>
    </section>;
  }

  const { projection } = state;
  const activeCount = projection.receipt?.active_membership_set_count ?? null;
  const alertDisplay = projection.current_alert?.display ?? null;

  return <section
    aria-label="歷史基線投影回讀"
    className="anomalies-recovery-card recovery"
    data-surface-id="anomalies.historical-baseline-projector"
    data-delivery-status={projection.delivery.status}
    data-reconciliation-status={projection.reconciliation.status}
  >
    <h3>歷史基線投影回讀</h3>
    <div className="anomaly-recovery-metadata-row">
      <span>Server delivery 狀態</span>
      <code>{projection.delivery.status}</code>
    </div>
    <div className="anomaly-recovery-metadata-row">
      <span>投影回讀狀態</span>
      <span>{reconciliationLabels[projection.reconciliation.status]}（<code>{projection.reconciliation.status}</code>）</span>
    </div>
    <div className="anomaly-recovery-metadata-row">
      <span>目前 active membership</span>
      <span>{activeCount === null ? '尚未建立 receipt' : `${activeCount} 項`}</span>
    </div>
    <div className="anomaly-recovery-metadata-row">
      <span>最早阻擋步驟</span>
      <span>{alertDisplay?.earliest_blocked_step === null || alertDisplay === null
        ? '目前無 server 指定阻擋步驟'
        : `Step ${alertDisplay.earliest_blocked_step}`}</span>
    </div>

    {projection.reconciliation.status === 'outcome_unknown' && <div className="import-warning-transition-warning" role="alert">
      原 delivery 已保留，但提交後結果仍無法確認。請依 server referral 重新讀取；本畫面不會建立 reconcile 或 resolve mutation。
      {projection.reconciliation.reason_code && <div>原因碼：<code>{projection.reconciliation.reason_code}</code></div>}
      <div>Server referral：<code>{projection.reconciliation.referral}</code></div>
    </div>}

    {alertDisplay && alertDisplay.repair_referrals.length > 0 ? <div>
      <h4>Server typed repair referrals</h4>
      <ul aria-label="歷史基線修復轉介">
        {alertDisplay.repair_referrals.map((referral) => <li key={`${referral.step}:${referral.contract_id}`}>
          <strong>Step {referral.step}｜{referral.owner_domain}</strong>
          <div>契約：<code>{referral.contract_id}</code></div>
          <div>處理目標：<code>{referral.repair_target}</code></div>
          <div>修復能力：<code>{referral.repair_capability}</code></div>
        </li>)}
      </ul>
    </div> : <div className="anomalies-detail-empty">
      Server 目前沒有 active repair referral。
    </div>}
  </section>;
}

export default HistoricalBaselineProjectorReadback;
