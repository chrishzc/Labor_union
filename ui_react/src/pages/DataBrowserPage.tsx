/**
 * File: DataBrowserPage.tsx
 * Description: 六來源 masked query、StrictMode-safe首屏、cursor table 與 loaded-row Drawer。
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
      setCopyStatus('無法使用剪貼簿，請手動選取去敏欄位');
    }
  };

  return (
    <div data-surface-id="data-browser.page">
      <div className="page-header-banner">
        <h1 className="page-title">🔍 資料來源與歷史快照瀏覽器</h1>
        <p className="page-subtitle">只顯示後端 allowlist 產生的去敏欄位；原始資料與更正操作不在此頁開放。</p>
      </div>

      <div className="databrowser-tab-bar">
        {DATA_BROWSER_TABS.map((tab) => (
          <button
            key={tab.tabId}
            data-control-id={`data-browser.source.${tab.sourceId}`}
            className={`databrowser-tab-btn ${selectedTabId === tab.tabId ? 'active' : ''}`}
            onClick={() => switchTab(tab)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <form className="databrowser-filter-bar" onSubmit={submitSearch}>
        <div style={{ display: 'flex', gap: '10px', flex: 1, maxWidth: '560px' }}>
          <input
            data-control-id="data-browser.query"
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
            maxLength={100}
            placeholder="搜尋核准的主鍵、狀態或遮罩欄位"
            style={{ width: '100%', padding: '10px 14px', borderRadius: '10px', border: '1px solid #dec0b6' }}
          />
          <button data-control-id="data-browser.query.submit" type="submit">查詢</button>
        </div>
        <div data-surface-id="data-browser.loaded-count" style={{ fontSize: '0.85rem', color: '#74593f' }}>
          目前載入 {rows.length} 筆（loaded scope）
        </div>
      </form>

      {state.kind === 'loading' && <div className="anomalies-loading">正在載入去敏資料...</div>}
      {state.kind === 'error' && (
        <div className="anomalies-error">
          <span>載入失敗：{state.message}</span>
          <button data-control-id="data-browser.query.retry" onClick={() => loadSource(selectedTab, appliedQuery)}>重試</button>
        </div>
      )}
      {state.kind === 'empty' && <div className="anomalies-empty">此來源目前沒有符合條件的去敏資料。</div>}

      {rows.length > 0 && (
        <div className="databrowser-table-container">
          <table className="databrowser-table">
            <thead>
              <tr><th>資料識別</th><th>標題</th><th>去敏摘要</th><th>紀錄時間</th><th>來源操作者</th><th>版本</th><th>詳情</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} data-surface-id={`data-browser.row.${row.sourceId}.${row.id}`}>
                  <td><code>{row.id}</code></td>
                  <td>{row.title}</td>
                  <td>{row.summary.map((cell) => `${cell.label}: ${cell.value}`).join(' ｜ ')}</td>
                  <td>{row.recordedAt}</td>
                  <td>{row.actorLabel}</td>
                  <td><code>{row.versionIdentity.slice(0, 12)}…</code></td>
                  <td><button data-control-id="data-browser.drawer.open" onClick={() => { setSelectedRecord(row); setCopyStatus(''); }}>檢視去敏詳情 ➔</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {state.kind === 'loading_more' && <div className="anomalies-loading">正在載入下一頁...</div>}
      {state.kind === 'page_error' && (
        <div className="anomalies-error">
          <span>下一頁載入失敗：{state.message}</span>
          <button data-control-id="data-browser.next-page.retry" onClick={retryNextPage}>重試下一頁</button>
        </div>
      )}
      {nextCursor && <button data-control-id="data-browser.next-page" onClick={loadNextPage}>載入下一頁</button>}

      <Drawer
        isOpen={selectedRecord !== null}
        onClose={() => setSelectedRecord(null)}
        title={`📑 去敏資料詳情 — ${selectedRecord?.title ?? ''}`}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
            <span data-surface-id="data-browser.drawer.copy-status" aria-live="polite">{copyStatus}</span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button data-control-id="data-browser.drawer.close" onClick={() => setSelectedRecord(null)}>關閉</button>
              <button data-control-id="data-browser.drawer.copy-masked" onClick={copyMaskedView}>複製去敏資料</button>
            </div>
          </div>
        }
      >
        {selectedRecord && (
          <div data-surface-id="data-browser.drawer" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="account-table-container">
              {selectedRecord.detail.map((cell) => (
                <div key={cell.id} style={{ padding: '8px 0', borderBottom: '1px solid #f2e2dc' }}><strong>{cell.label}：</strong>{cell.value}</div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <button data-control-id="data-browser.patch" disabled title="[查詢模式] generic PATCH 已退役">編輯資料</button>
              <button data-control-id="data-browser.source-correction.preview" disabled title="[查詢模式] source correction 不在此 page-slice">預覽來源更正</button>
              <button data-control-id="data-browser.source-correction.apply" disabled title="[查詢模式] source correction 不在此 page-slice">套用來源更正</button>
            </div>
            <div style={{ color: '#888', fontSize: '0.82rem' }}>版本識別：<code>{selectedRecord.versionIdentity}</code></div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default DataBrowserPage;
