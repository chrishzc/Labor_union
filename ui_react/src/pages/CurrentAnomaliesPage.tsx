/** Current-only Anomalies page: current rows, typed detail and owner action descriptors. */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './AnomaliesPage.css';
import { Drawer } from '../components/Drawer';
import { currentAnomalyQueryClient } from '../api/anomalies/current_anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import type { AnomalyRecoveryContextView } from '../api/anomalies/anomaly_detail_schemas';
import {
  adaptCurrentAnomalySummary,
  type CurrentAnomalyRowViewModel,
} from '../adapters/anomalies/current_anomaly_adapter';

const PAGE_SIZE = 50;

function displayError(error: unknown): string {
  const code = String((error as { code?: unknown })?.code ?? '').toUpperCase();
  const status = Number((error as { status?: unknown })?.status ?? 0);
  if (status === 401 || code.includes('UNAUTHENTICATED')) return '登入狀態已失效，請重新登入後再查詢。';
  if (status === 403 || code.includes('FORBIDDEN')) return '目前帳號沒有查看異常資料的權限。';
  if (status === 404 || code.includes('NOT_FOUND')) return '這筆問題已不存在，請重新整理目前異常清單。';
  if (status === 409 || code.includes('STALE') || code.includes('CONFLICT')) return '問題資料已變更，請重新整理後再查看。';
  if (code.includes('NETWORK') || code.includes('TIMEOUT') || code.includes('UNAVAILABLE')) return '異常資料暫時無法取得，請稍後重試。';
  return '目前異常資料暫時無法使用，請稍後重試。';
}

function renderEvidence(value: unknown): string {
  return Array.isArray(value) ? value.join('、') : String(value);
}

function ownerLabel(owner: string): string {
  return ({
    scheduling: '排班管理',
    staff_payables: '服務人員應付款',
    government_subsidy: '政府補助',
    case_import: '案件資料匯入',
    finance_import: '銀行流水匯入',
    line: 'LINE 管理',
  } as Record<string, string>)[owner] ?? '對應業務流程';
}

export const CurrentAnomaliesPage: React.FC = () => {
  const [items, setItems] = useState<CurrentAnomalyRowViewModel[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<CurrentAnomalyRowViewModel | null>(null);
  const [detail, setDetail] = useState<AnomalyRecoveryContextView | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async (cursor?: string) => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const page = await currentAnomalyQueryClient.queryCurrentAnomalies({
        limit: PAGE_SIZE,
        cursor,
      });
      if (sequence !== requestSequence.current) return;
      const incoming = page.items.map(adaptCurrentAnomalySummary);
      setItems((existing) => {
        if (!cursor) return incoming;
        const byKey = new Map(existing.map((item) => [item.issueKey, item]));
        for (const item of incoming) byKey.set(item.issueKey, item);
        return [...byKey.values()];
      });
      setNextCursor(page.next_cursor);
    } catch (caught) {
      if (sequence === requestSequence.current) setError(displayError(caught));
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openDetail = useCallback(async (item: CurrentAnomalyRowViewModel) => {
    setSelected(item);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const current = await anomalyDetailClient.queryAnomalyRecovery({ issueKey: item.issueKey });
      setDetail(current);
    } catch (caught) {
      setDetailError(displayError(caught));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  return (
    <main className="anomalies-page" aria-labelledby="current-anomalies-title">
      <header className="page-header">
        <div>
          <h1 id="current-anomalies-title">目前異常</h1>
          <p>只顯示現在仍成立、需要回到資料擁有者處理的問題。</p>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading}>重新查詢</button>
      </header>

      {error && <div role="alert" className="error-message">{error}</div>}
      {!loading && items.length === 0 && !error && <p>目前沒有異常。</p>}

      <section aria-label="目前異常清單" className="anomaly-list">
        {items.map((item) => (
          <button
            type="button"
            className="anomaly-card"
            key={item.issueKey}
            onClick={() => void openDetail(item)}
          >
            <strong>{item.definitionCode}</strong>
            <span>{ownerLabel(item.ownerDomain)}</span>
            <span>{item.blocking ? '阻擋作業' : '需要處理'}</span>
            <span>最近確認：{new Date(item.lastVerifiedAt).toLocaleString('zh-TW')}</span>
          </button>
        ))}
      </section>

      {nextCursor && (
        <button type="button" onClick={() => void load(nextCursor)} disabled={loading}>
          載入更多
        </button>
      )}

      <Drawer
        isOpen={selected !== null}
        onClose={() => { setSelected(null); setDetail(null); setDetailError(null); }}
        title={selected ? `${selected.definitionCode} 詳情` : '異常詳情'}
        size="wide"
      >
        {detailLoading && <p>正在讀取最新業務資料…</p>}
        {detailError && <div role="alert" className="error-message">{detailError}</div>}
        {detail && (
          <div>
            <p><strong>負責流程：</strong>{ownerLabel(detail.owner_domain)}</p>
            <p><strong>影響：</strong>{detail.blocking ? '目前會阻擋作業' : '目前需要人工確認'}</p>
            <details><summary>技術詳情與資料來源</summary><p>資料版本：{detail.owner_version}</p><p>負責模組：{detail.owner_domain}</p></details>
            <h3>目前可判斷資料</h3>
            <dl>
              {[...detail.subject.fields, ...detail.details.fields].map((field) => (
                <React.Fragment key={`${field.kind}:${field.key}`}>
                  <dt>{field.key}</dt>
                  <dd>{renderEvidence(field.value)}</dd>
                </React.Fragment>
              ))}
            </dl>
            <h3>人工處理入口</h3>
            {detail.available_actions.length === 0 ? (
              <p>這類問題目前沒有可安全執行的處理操作；系統不會用通用結案取代業務修正。</p>
            ) : detail.available_actions.map((action) => (
              <article key={action.action_key} className="anomaly-action">
                <strong>{action.label}</strong>
                <p>完成操作後，系統會重新查詢最新業務資料並確認問題是否解除。</p>
                <details><summary>操作技術詳情</summary><p>{action.owning_domain} · {action.preview_operation} → {action.apply_operation ?? '僅供查詢'}</p><p>完成條件：{action.completion_predicate}</p></details>
              </article>
            ))}
            <button type="button" onClick={() => selected && void openDetail(selected)}>
              重新查詢最新資料
            </button>
            <p>只有重新檢查證實問題原因已消失後，這筆提醒才會從清單移除。</p>
          </div>
        )}
      </Drawer>
    </main>
  );
};

export default CurrentAnomaliesPage;
