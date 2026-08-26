/**
 * File: DataBrowserPage.tsx
 * Description: 六來源去敏資料唯讀查詢，支援分頁、搜尋與業務欄位詳情。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './DataBrowserPage.css';
import { Drawer } from '../components/Drawer';
import { dataBrowserQueryClient } from '../api/data_browser/data_browser_query_client';
import {
  adaptDataBrowserPage,
  DATA_BROWSER_TABS,
  type DataBrowserRowViewModel,
  type DataBrowserTab,
  type DataBrowserTabId,
} from '../adapters/data_browser/data_browser_query_adapter';

type QueryState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; rows: DataBrowserRowViewModel[]; nextCursor: string | null }
  | { kind: 'empty' }
  | { kind: 'error'; message: string }
  | { kind: 'loading_more'; rows: DataBrowserRowViewModel[] }
  | { kind: 'page_error'; rows: DataBrowserRowViewModel[]; message: string; failedCursor: string };

const INITIAL_TAB = DATA_BROWSER_TABS[0];

export const DataBrowserPage: React.FC = () => {
  const [selectedTabId, setSelectedTabId] = useState<DataBrowserTabId>(INITIAL_TAB.tabId);
  const [queryInput, setQueryInput] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const [state, setState] = useState<QueryState>({ kind: 'idle' });
  const [selectedRecord, setSelectedRecord] = useState<DataBrowserRowViewModel | null>(null);
  const [copyStatus, setCopyStatus] = useState('');
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const seenCursors = useRef(new Set<string>());

  const selectedTab = DATA_BROWSER_TABS.find((tab) => tab.tabId === selectedTabId) ?? INITIAL_TAB;

  const loadSource = useCallback(async (
    tab: DataBrowserTab,
    query: string,
    after?: string,
    existingRows: DataBrowserRowViewModel[] = [],
    coalesceReplay = false
  ) => {
    const seq = ++generation.current;
    controller.current?.abort();
    const activeController = coalesceReplay ? null : new AbortController();
    controller.current = activeController;
    setSelectedRecord(null);
    setCopyStatus('');
    setState(after ? { kind: 'loading_more', rows: existingRows } : { kind: 'loading' });
    try {
      const page = await dataBrowserQueryClient.querySource(
        { sourceId: tab.sourceId, limit: 25, after, query: query || undefined },
        activeController === null ? undefined : { signal: activeController.signal }
      );
      if (seq !== generation.current || activeController?.signal.aborted) return;
      const adapted = adaptDataBrowserPage(page);
      if (adapted.sourceId !== tab.sourceId) throw new Error('data_browser_source_mismatch');
      const existingIds = new Set(existingRows.map((row) => row.id));
      if (adapted.rows.some((row) => existingIds.has(row.id))) {
        throw new Error('data_browser_duplicate_row_across_pages');
      }
      const rows = [...existingRows, ...adapted.rows];
      setState(rows.length === 0
        ? { kind: 'empty' }
        : { kind: 'ready', rows, nextCursor: adapted.nextCursor });
    } catch {
      if (seq !== generation.current || activeController?.signal.aborted) return;
      const message = after === undefined
        ? '目前無法載入此資料來源，請稍後重試。'
        : '下一頁資料暫時無法載入，請重試。';
      if (after !== undefined) seenCursors.current.delete(after);
      setState(existingRows.length > 0 && after !== undefined
        ? { kind: 'page_error', rows: existingRows, message, failedCursor: after }
        : { kind: 'error', message });
    }
  }, []);

  useEffect(() => {
    void loadSource(INITIAL_TAB, '', undefined, [], true);
    return () => {
      generation.current += 1;
      controller.current?.abort();
    };
  }, [loadSource]);

  const switchTab = (tab: DataBrowserTab) => {
    if (tab.tabId === selectedTabId) return;
    seenCursors.current.clear();
    setSelectedTabId(tab.tabId);
    setQueryInput('');
    setAppliedQuery('');
    void loadSource(tab, '');
  };

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const query = queryInput.trim();
    seenCursors.current.clear();
    setAppliedQuery(query);
    void loadSource(selectedTab, query);
  };

  const rows = state.kind === 'ready' || state.kind === 'loading_more' || state.kind === 'page_error'
    ? state.rows
    : [];
  const nextCursor = state.kind === 'ready' ? state.nextCursor : null;

  const loadNextPage = () => {
    if (!nextCursor || seenCursors.current.has(nextCursor)) return;
    seenCursors.current.add(nextCursor);
    void loadSource(selectedTab, appliedQuery, nextCursor, rows);
  };

  const retryNextPage = () => {
    if (state.kind !== 'page_error' || seenCursors.current.has(state.failedCursor)) return;
    seenCursors.current.add(state.failedCursor);
    void loadSource(selectedTab, appliedQuery, state.failedCursor, state.rows);
  };

  const copyMaskedView = async () => {
    if (!selectedRecord) return;
    const payload = {
      data_source: selectedTab.label,
      title: selectedRecord.title,
      details: selectedRecord.detail.map((item) => ({ label: item.label, value: item.value })),
      recorded_at: selectedRecord.recordedAt,
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setCopyStatus('已複製去敏資料');
    } catch {
      setCopyStatus('無法使用剪貼簿，請手動選取欄位');
    }
  };

  return (
    <div className="databrowser-page" data-surface-id="data-browser.page">
      {/* 頂部 Header Banner */}
      <div className="page-header-banner databrowser-page-header">
        <div className="databrowser-page-header-text">
          <h1 className="page-title databrowser-page-title">
            🔍 營運資料查詢
          </h1>
          <p className="page-subtitle databrowser-page-subtitle">
            依資料來源查詢已去敏的營運資料與更新紀錄。
          </p>
        </div>
        <span className="databrowser-header-badge">
          ● 唯讀查詢
        </span>
      </div>

      {/* 4 大統計與狀態指標卡 (KPI Grid) */}
      <div className="databrowser-kpi-grid">
        <div className="databrowser-kpi-card">
          <span className="databrowser-kpi-label">目前資料來源</span>
          <span className="databrowser-kpi-value" style={{ color: '#ea580c' }}>
            {selectedTab.label}
          </span>
          <span className="databrowser-kpi-desc">已套用去敏顯示規則</span>
        </div>
        <div className="databrowser-kpi-card">
          <span className="databrowser-kpi-label">目前載入筆數</span>
          <span className="databrowser-kpi-value">{rows.length} 筆</span>
          <span className="databrowser-kpi-desc">可繼續載入下一頁</span>
        </div>
        <div className="databrowser-kpi-card">
          <span className="databrowser-kpi-label">首筆記錄時間</span>
          <span className="databrowser-kpi-value" style={{ fontSize: '1.05rem', color: '#74593f' }}>
            {rows[0]?.recordedAt ?? '—'}
          </span>
          <span className="databrowser-kpi-desc">目前查詢結果中的最早記錄</span>
        </div>
        <div className="databrowser-kpi-card">
          <span className="databrowser-kpi-label">操作方式</span>
          <span className="databrowser-kpi-value" style={{ color: '#16a34a', fontSize: '1.15rem' }}>唯讀查詢</span>
          <span className="databrowser-kpi-desc">資料修正請前往對應業務頁面</span>
        </div>
      </div>

      {/* 6 大資料來源頁籤列 */}
      <div className="databrowser-tab-bar" aria-label="資料來源切換">
        {DATA_BROWSER_TABS.map((tab) => (
          <button
            key={tab.tabId}
            type="button"
            data-control-id={`data-browser.source.${tab.sourceId}`}
            className={`databrowser-tab-btn ${selectedTabId === tab.tabId ? 'active' : ''}`}
            onClick={() => switchTab(tab)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 搜尋與過濾工具列 */}
      <form className="databrowser-filter-bar" onSubmit={submitSearch}>
        <div className="databrowser-search-wrap">
          <div className="databrowser-search-input-box">
            <span className="databrowser-search-icon">🔍</span>
            <input
              data-control-id="data-browser.query"
              className="databrowser-search-input"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              maxLength={100}
              placeholder="搜尋案件編號、狀態或去敏欄位內容"
            />
            {queryInput && (
              <button
                type="button"
                className="databrowser-search-clear"
                onClick={() => setQueryInput('')}
                aria-label="清除搜尋關鍵字"
              >
                ✕
              </button>
            )}
          </div>
          <button
            data-control-id="data-browser.query.submit"
            className="databrowser-btn-primary"
            type="submit"
          >
            查詢
          </button>
        </div>
        <div
          data-surface-id="data-browser.loaded-count"
          className="databrowser-loaded-badge"
        >
          目前已載入 {rows.length} 筆
        </div>
      </form>

      {/* 載入與錯誤提示 */}
      {state.kind === 'loading' && <div className="anomalies-loading">正在載入去敏資料...</div>}
      {state.kind === 'error' && (
        <div className="anomalies-error">
          <span>載入失敗：{state.message}</span>
          <button
            type="button"
            data-control-id="data-browser.query.retry"
            onClick={() => loadSource(selectedTab, appliedQuery)}
          >
            重試
          </button>
        </div>
      )}
      {state.kind === 'empty' && (
        <div className="anomalies-empty">此來源目前沒有符合條件的去敏資料。</div>
      )}

      {/* 高密度等寬資料表格 */}
      {rows.length > 0 && (
        <div className="databrowser-table-container">
          <table className="databrowser-table">
            <thead>
              <tr>
                <th style={{ minWidth: '180px' }}>標題</th>
                <th style={{ minWidth: '320px' }}>去敏摘要</th>
                <th style={{ width: '170px' }}>紀錄時間</th>
                <th style={{ width: '120px' }}>來源操作者</th>
                <th style={{ width: '140px', textAlign: 'right' }}>詳情</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} data-surface-id={`data-browser.row.${row.sourceId}.${row.id}`}>
                  <td>
                    <strong>{row.title}</strong>
                  </td>
                  <td>
                    <div className="databrowser-summary-wrap">
                      {row.summary.map((cell) => (
                        <span key={cell.id} className="databrowser-cell-pill">
                          <span className="databrowser-cell-label">{cell.label}:</span>
                          <span className="databrowser-cell-value">{cell.value}</span>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ color: '#74593f', fontSize: '0.82rem' }}>{row.recordedAt}</td>
                  <td style={{ color: '#57423b' }}>{row.actorLabel}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      type="button"
                      data-control-id="data-browser.drawer.open"
                      className="databrowser-action-link-btn"
                      onClick={() => {
                        setSelectedRecord(row);
                        setCopyStatus('');
                      }}
                    >
                      檢視去敏詳情 ➔
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 分頁控制 */}
      {state.kind === 'loading_more' && <div className="anomalies-loading">正在載入下一頁...</div>}
      {state.kind === 'page_error' && (
        <div className="anomalies-error">
          <span>下一頁載入失敗：{state.message}</span>
          <button
            type="button"
            data-control-id="data-browser.next-page.retry"
            className="databrowser-pagination-btn"
            onClick={retryNextPage}
          >
            重試下一頁
          </button>
        </div>
      )}
      {nextCursor && (
        <div className="databrowser-pagination-bar">
          <button
            type="button"
            data-control-id="data-browser.next-page"
            className="databrowser-pagination-btn"
            onClick={loadNextPage}
          >
            載入下一頁
          </button>
        </div>
      )}

      {/* 去敏資料詳情抽屜 */}
      <Drawer
        isOpen={selectedRecord !== null}
        onClose={() => setSelectedRecord(null)}
        size="wide"
        title={`📑 去敏資料詳情 — ${selectedRecord?.title ?? ''}`}
        footer={
          <div className="databrowser-drawer-footer">
            <span
              data-surface-id="data-browser.drawer.copy-status"
              className="databrowser-copy-feedback"
              aria-live="polite"
            >
              {copyStatus}
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                data-control-id="data-browser.drawer.close"
                style={{
                  padding: '8px 18px',
                  border: '1px solid #dec0b6',
                  borderRadius: '10px',
                  background: '#ffffff',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
                onClick={() => setSelectedRecord(null)}
              >
                關閉
              </button>
              <button
                type="button"
                data-control-id="data-browser.drawer.copy-masked"
                className="databrowser-btn-primary"
                onClick={() => void copyMaskedView()}
              >
                複製去敏資料
              </button>
            </div>
          </div>
        }
      >
        {selectedRecord && (
          <div
            data-surface-id="data-browser.drawer"
            className="databrowser-drawer-wrap"
          >
            {/* 頂部記錄摘要 */}
            <div className="databrowser-drawer-meta-banner">
              <div className="databrowser-meta-item">
                <span className="databrowser-meta-item-label">資料來源</span>
                <span className="databrowser-meta-item-value" style={{ color: '#ea580c' }}>
                  {selectedTab.label}
                </span>
              </div>
              <div className="databrowser-meta-item">
                <span className="databrowser-meta-item-label">紀錄時間</span>
                <span className="databrowser-meta-item-value">
                  {selectedRecord.recordedAt}
                </span>
              </div>
              <div className="databrowser-meta-item">
                <span className="databrowser-meta-item-label">來源操作者</span>
                <span className="databrowser-meta-item-value">
                  {selectedRecord.actorLabel}
                </span>
              </div>
            </div>

            {/* 去敏欄位清單 */}
            {(
              <table className="databrowser-kv-table">
                <thead>
                  <tr>
                    <th style={{ width: '200px' }}>欄位名稱</th>
                    <th>去敏內容</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedRecord.detail.map((cell) => (
                    <tr key={cell.id}>
                      <td>
                        <strong>{cell.label}</strong>
                      </td>
                      <td style={{ fontFamily: 'ui-monospace, Consolas, monospace' }}>
                        {cell.value}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* 唯讀操作說明 */}
            <div className="databrowser-retired-panel">
              <div>
                <p>
                  <strong>唯讀查詢：</strong>
                  此頁只提供去敏資料查詢；如需修正，請前往對應業務頁面依正式流程辦理。
                </p>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default DataBrowserPage;
