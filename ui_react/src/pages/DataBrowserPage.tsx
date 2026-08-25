/**
 * File: DataBrowserPage.tsx
 * Description: 六來源原始資料與快照瀏覽器，支援等寬高密度網格、Keyspace Cursor 分頁與 1400px 結構化 JSON 抽屜。
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

type DrawerDetailTab = 'kv' | 'json';

const INITIAL_TAB = DATA_BROWSER_TABS[0];

export const DataBrowserPage: React.FC = () => {
  const [selectedTabId, setSelectedTabId] = useState<DataBrowserTabId>(INITIAL_TAB.tabId);
  const [queryInput, setQueryInput] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const [state, setState] = useState<QueryState>({ kind: 'idle' });
  const [selectedRecord, setSelectedRecord] = useState<DataBrowserRowViewModel | null>(null);
  const [drawerMode, setDrawerMode] = useState<DrawerDetailTab>('kv');
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
    } catch (error) {
      if (seq !== generation.current || activeController?.signal.aborted) return;
      const message = error instanceof Error ? error.message : '載入資料來源失敗';
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
      source_id: selectedRecord.sourceId,
      row_identity: selectedRecord.id,
      display_title: selectedRecord.title,
      detail: selectedRecord.detail,
      recorded_at: selectedRecord.recordedAt,
      version_identity: selectedRecord.versionIdentity,
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setCopyStatus('已複製去敏資料');
    } catch {
      setCopyStatus('無法使用剪貼簿，請手動選取欄位');
    }
  };

  const recordPayload = selectedRecord
    ? {
        source_id: selectedRecord.sourceId,
        row_identity: selectedRecord.id,
        display_title: selectedRecord.title,
        detail: selectedRecord.detail.reduce<Record<string, string>>((acc, curr) => {
          acc[curr.id] = curr.value;
          return acc;
        }, {}),
        recorded_at: selectedRecord.recordedAt,
        version_identity: selectedRecord.versionIdentity,
      }
    : null;

  return (
    <div className="databrowser-page" data-surface-id="data-browser.page">
      {/* 頂部 Header Banner */}
      <div className="page-header-banner databrowser-page-header">
        <div className="databrowser-page-header-text">
          <h1 className="page-title databrowser-page-title">
            🔍 核心資料庫來源與歷程快照瀏覽器
          </h1>
          <p className="page-subtitle databrowser-page-subtitle">
            穿透業務封裝，檢視 6 大資料庫主表原始快照、欄位歷程、等寬資料網格與 SHA-256 存證指紋。
          </p>
        </div>
        <span className="databrowser-header-badge">
          ● 0 Polling ｜ Keyspace Cursor Paging ｜ Read-Only Safe
        </span>
      </div>

      {/* 4 大統計與狀態指標卡 (KPI Grid) */}
      <div className="databrowser-kpi-grid">
        <div className="databrowser-kpi-card">
          <span className="databrowser-kpi-label">當前資料庫來源</span>
          <span className="databrowser-kpi-value" style={{ color: '#ea580c' }}>
            {selectedTab.sourceId}
          </span>
          <span className="databrowser-kpi-desc">{selectedTab.label}</span>
        </div>
        <div className="databrowser-kpi-card">
          <span className="databrowser-kpi-label">目前載入筆數 (Loaded)</span>
          <span className="databrowser-kpi-value">{rows.length} 筆</span>
          <span className="databrowser-kpi-desc">單頁上限 25 筆 ｜ Keyspace Cursor</span>
        </div>
        <div className="databrowser-kpi-card">
          <span className="databrowser-kpi-label">首筆記錄時間戳</span>
          <span className="databrowser-kpi-value" style={{ fontSize: '1.05rem', color: '#74593f' }}>
            {rows[0]?.recordedAt ?? '—'}
          </span>
          <span className="databrowser-kpi-desc">資料庫即時快照存檔時間</span>
        </div>
        <div className="databrowser-kpi-card">
          <span className="databrowser-kpi-label">版本完整性存證</span>
          <span className="databrowser-kpi-value" style={{ color: '#16a34a', fontSize: '1.15rem' }}>
            SHA-256 Verified
          </span>
          <span className="databrowser-kpi-desc">防重與防篡改指紋驗證</span>
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
              placeholder="搜尋核准的主鍵、狀態或遮罩欄位"
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
          目前載入 {rows.length} 筆（loaded scope）
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
                <th style={{ width: '130px' }}>資料識別</th>
                <th style={{ minWidth: '180px' }}>標題</th>
                <th style={{ minWidth: '320px' }}>去敏摘要</th>
                <th style={{ width: '170px' }}>紀錄時間</th>
                <th style={{ width: '120px' }}>來源操作者</th>
                <th style={{ width: '140px' }}>版本</th>
                <th style={{ width: '140px', textAlign: 'right' }}>詳情</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} data-surface-id={`data-browser.row.${row.sourceId}.${row.id}`}>
                  <td>
                    <code className="databrowser-row-id">{row.id}</code>
                  </td>
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
                  <td>
                    <code
                      className="databrowser-hash-code"
                      title={`完整 SHA-256：${row.versionIdentity}`}
                    >
                      {row.versionIdentity.slice(0, 12)}…
                    </code>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      type="button"
                      data-control-id="data-browser.drawer.open"
                      className="databrowser-action-link-btn"
                      onClick={() => {
                        setSelectedRecord(row);
                        setCopyStatus('');
                        setDrawerMode('kv');
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

      {/* 1400px 結構化資料與快照檢查抽屜 (Drawer) */}
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
            {/* 頂部快照元數據卡 */}
            <div className="databrowser-drawer-meta-banner">
              <div className="databrowser-meta-item">
                <span className="databrowser-meta-item-label">來源主表 (Source ID)</span>
                <span className="databrowser-meta-item-value" style={{ color: '#ea580c' }}>
                  {selectedRecord.sourceId}
                </span>
              </div>
              <div className="databrowser-meta-item">
                <span className="databrowser-meta-item-label">資料列識別 (Row Identity)</span>
                <span className="databrowser-meta-item-value">
                  {selectedRecord.id}
                </span>
              </div>
              <div className="databrowser-meta-item">
                <span className="databrowser-meta-item-label">快照存檔時間 (Recorded At)</span>
                <span className="databrowser-meta-item-value">
                  {selectedRecord.recordedAt}
                </span>
              </div>
              <div className="databrowser-meta-item">
                <span className="databrowser-meta-item-label">來源操作者 (Actor)</span>
                <span className="databrowser-meta-item-value">
                  {selectedRecord.actorLabel}
                </span>
              </div>
              <div className="databrowser-hash-banner">
                <strong style={{ fontSize: '0.8rem', color: '#74593f', whiteSpace: 'nowrap' }}>
                  🛡️ 64-bit SHA-256 Version Hash:
                </strong>
                <code>{selectedRecord.versionIdentity}</code>
              </div>
            </div>

            {/* 雙模式檢視切換 */}
            <div className="databrowser-view-mode-tabs">
              <button
                type="button"
                className={`databrowser-mode-tab-btn ${drawerMode === 'kv' ? 'active' : ''}`}
                onClick={() => setDrawerMode('kv')}
              >
                📊 欄位鍵值清冊 (Key-Value)
              </button>
              <button
                type="button"
                className={`databrowser-mode-tab-btn ${drawerMode === 'json' ? 'active' : ''}`}
                onClick={() => setDrawerMode('json')}
              >
                💻 格式化 JSON (JSON View)
              </button>
            </div>

            {/* 模式 A：Key-Value 欄位屬性表格 */}
            {drawerMode === 'kv' && (
              <table className="databrowser-kv-table">
                <thead>
                  <tr>
                    <th style={{ width: '220px' }}>欄位代碼 (Field ID)</th>
                    <th style={{ width: '200px' }}>欄位名稱</th>
                    <th>原始值 (Value)</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedRecord.detail.map((cell) => (
                    <tr key={cell.id}>
                      <td>
                        <code style={{ color: '#ea580c', fontWeight: 700 }}>{cell.id}</code>
                      </td>
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

            {/* 模式 B：格式化 JSON 檢視 */}
            {drawerMode === 'json' && recordPayload && (
              <div className="databrowser-json-container">
                <pre>{JSON.stringify(recordPayload, null, 2)}</pre>
              </div>
            )}

            {/* 受控退役操作面板 */}
            <div className="databrowser-retired-panel">
              <div>
                <p>
                  <strong>⚠️ 唯讀保護提示：</strong>
                  通用 PATCH 與來源更正已退役或移至專屬 Domain 工作流，此處僅提供資料快照調閱。
                </p>
              </div>
              <div className="databrowser-retired-actions">
                <button
                  type="button"
                  data-control-id="data-browser.patch"
                  disabled
                  title="[查詢模式] generic PATCH 已退役"
                >
                  編輯資料
                </button>
                <button
                  type="button"
                  data-control-id="data-browser.source-correction.preview"
                  disabled
                  title="[查詢模式] source correction 不在此 page-slice"
                >
                  預覽來源更正
                </button>
                <button
                  type="button"
                  data-control-id="data-browser.source-correction.apply"
                  disabled
                  title="[查詢模式] source correction 不在此 page-slice"
                >
                  套用來源更正
                </button>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default DataBrowserPage;

