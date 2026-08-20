/**
 * File: DataImportPage.tsx
 * Description: 顯示 HCM 最近匯入批次、新增訂單與問題導向；其他匯入family維持原位鎖定。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adaptHcmImportResult, type HcmImportResultViewModel } from '../adapters/case_import/hcm_import_result_adapter';
import { hcmImportResultClient } from '../api/case_import/hcm_import_result_client';
import './DataImportPage.css';

const LOCKED_CATEGORIES = [
  ['hcm-historical', '📜', '2. HCM 歷史過渡匯入', '已退役', 'Historical whole-row overwrite 已退役'],
  ['client-beclass', '👥', '3. 客戶 BeClass 問卷匯入', '本波未開放', '等待獨立 bounded contract'],
  ['staff-historical', '👩‍🍼', '4. 月嫂歷史資料匯入', '本波未開放', '等待獨立 bounded contract'],
  ['historic-orders', '📦', '5. 歷史訂單認領匯入', '本波未開放', '等待獨立 bounded contract'],
  ['bank-statements', '🏦', '6. 銀行對帳單流水匯入', '本波未開放', '等待 Finance Import 專屬工作包'],
] as const;

type ResultState =
  | { kind: 'loading' }
  | { kind: 'ready'; items: HcmImportResultViewModel[] }
  | { kind: 'empty' }
  | { kind: 'error'; message: string };

export const DataImportPage: React.FC = () => {
  const [state, setState] = useState<ResultState>({ kind: 'loading' });
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const loadResults = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setState({ kind: 'loading' });
    try {
      const page = await hcmImportResultClient.query({ limit: 20 }, { signal: controller.signal });
      if (controller.signal.aborted || generation !== generationRef.current) return;
      const items = page.items.map(adaptHcmImportResult);
      setState(items.length ? { kind: 'ready', items } : { kind: 'empty' });
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current) return;
      setState({ kind: 'error', message: error instanceof Error ? error.message : 'HCM 匯入結果載入失敗。' });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => { if (!cancelled) void loadResults(); });
    return () => {
      cancelled = true;
      abortRef.current?.abort();
      generationRef.current += 1;
    };
  }, [loadResults]);

  const navigateToWarning = () => {
    window.location.hash = '#anomalies';
  };

  return (
    <div data-surface-id="imports.page">
      <header className="page-header-banner import-result-header">
        <div>
          <h1 className="page-title">📥 批次資料匯入中心</h1>
          <p className="page-subtitle">查看 HCM 已完成批次的新增訂單與問題欄位；Apply 仍由獨立安全流程管理。</p>
        </div>
        <button type="button" className="import-result-refresh" data-control-id="imports.hcm-results.refresh" onClick={() => void loadResults()}>
          重新整理結果
        </button>
      </header>

      <section className="import-result-workbench" data-surface-id="imports.hcm-results.open">
        <div className="import-result-title-row">
          <div><span className="import-icon">🏢</span><h2>HCM 最近匯入結果與問題檢查</h2></div>
          <span className="import-status-badge ready">GET-only</span>
        </div>

        {state.kind === 'loading' && <div className="import-result-state" role="status">正在載入最近匯入結果…</div>}
        {state.kind === 'error' && <div className="import-result-state import-result-error" data-surface-id="imports.hcm-results.error" role="alert">{state.message}</div>}
        {state.kind === 'empty' && <div className="import-result-state" data-surface-id="imports.hcm-results.empty">目前沒有可查詢的 HCM 匯入receipt。</div>}

        {state.kind === 'ready' && state.items.map((result) => (
          <article key={result.receiptId} className="import-result-batch" data-surface-id={`imports.hcm-results.receipt.${result.receiptId}`}>
            <header>
              <div><strong>Receipt #{result.receiptId}</strong><span>{result.completedAt}</span></div>
              <code>{result.digestShort}</code>
            </header>
            <p className="import-result-summary">{result.summary}｜來源 {result.sourceRowCount} 列</p>

            {!result.rowOutcomesAvailable ? (
              <div className="import-result-legacy" data-surface-id="imports.hcm-results.legacy-unavailable">
                舊receipt未保存逐列membership；不能判定本次新增了哪些訂單。
              </div>
            ) : (
              <div className="import-result-columns">
                <section data-surface-id="imports.hcm-results.new-orders">
                  <h3>本次新增訂單</h3>
                  {result.newOrders.length === 0 ? <p>本批次沒有新增訂單。</p> : result.newOrders.map((row) => (
                    <div key={row.source_row} className="import-result-row" data-surface-id={`imports.hcm-results.new-order.${encodeURIComponent(row.case_no ?? `row-${row.source_row}`)}`}>
                      <strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong><span>{row.outcome}</span>
                    </div>
                  ))}
                </section>

                <section data-surface-id="imports.hcm-results.problems">
                  <h3>需要檢查</h3>
                  {result.problems.length === 0 ? <p>本批次沒有問題列。</p> : result.problems.map((row) => (
                    <div key={row.source_row} className="import-result-problem" data-surface-id={`imports.hcm-results.problem.${encodeURIComponent(row.problem_identity ?? `row-${row.source_row}`)}`}>
                      <strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong>
                      <span>欄位：{row.problem_fields.join('、') || '未提供'}</span>
                      <span>代碼：{row.issue_codes.join('、') || '未提供'}</span>
                      <button type="button" data-control-id={`imports.hcm-results.problem.referral.${encodeURIComponent(row.problem_identity ?? `row-${row.source_row}`)}`} onClick={navigateToWarning}>
                        前往異常與匯入警示中心
                      </button>
                    </div>
                  ))}
                </section>

                <section data-surface-id="imports.hcm-results.replays">
                  <h3>Exact Replay</h3>
                  {result.replays.length === 0 ? <p>本批次沒有replay。</p> : result.replays.map((row) => (
                    <div key={row.source_row} className="import-result-row"><strong>{row.case_no ?? `來源列 ${row.source_row}`}</strong><span>未列為新增</span></div>
                  ))}
                </section>
              </div>
            )}
          </article>
        ))}
      </section>

      <div className="import-cards-grid import-locked-grid">
        {LOCKED_CATEGORIES.map(([id, icon, title, status, specs]) => (
          <article key={id} className="import-category-card">
            <div className="import-card-header"><div className="import-icon-title"><span className="import-icon">{icon}</span><span className="import-title">{title}</span></div><span className="import-status-badge locked">{status}</span></div>
            <p className="import-description">保留原工作區位置；本結果頁不共用 HCM contract。</p>
            <div className="import-specs-box">{specs}</div>
            <div className="import-card-actions">
              <button type="button" className="import-action secondary" data-control-id={`imports.${id}.preview`} disabled>未開放</button>
              <button type="button" className="import-action primary" data-control-id={`imports.${id}.apply`} disabled>Apply 未開放</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
};

export default DataImportPage;
