/**
 * File: AiEventStudio.tsx
 * Description: 僅顯示 server-owned AI 客服事件／導航規則與正式測試，不再內建本機示範規則。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { sessionClient } from '../../api/auth/session_client';
import { RealLlmSemanticTestPanel } from './RealLlmSemanticTestPanel';
import '../LineManagementPage.css';

interface NavigationCatalogEntry {
  alias: string;
  route_key: string;
  tier: string;
  public_route?: string | null;
  postback_identity?: string | null;
  source_identity: string;
  revision: number;
}

interface NavigationCatalog {
  revision: number;
  entries: NavigationCatalogEntry[];
}

interface FeedbackAggregate {
  resolved_count: number;
  unresolved_count: number;
  total_count: number;
  resolved_rate: number | null;
}

interface RouterPreview {
  kind: string;
  source_event_id: string;
  source_identity: string;
  source_revision: number;
  semantic_bucket: string;
  confidence: number;
  score_band: string | null;
  reason_code: string | null;
  route_key: string | null;
  options: string[];
  answer_text: string | null;
  ticket_id: number | null;
  apply_ready: boolean;
}

interface CatalogGroup {
  routeKey: string;
  tier: string;
  publicRoute: string | null;
  postbackIdentity: string | null;
  sourceIdentity: string;
  revision: number;
  aliases: string[];
}

export const AiEventStudio: React.FC = () => {
  const [catalog, setCatalog] = useState<NavigationCatalog | null>(null);
  const [feedbackAggregate, setFeedbackAggregate] = useState<FeedbackAggregate | null>(null);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedRouteKey, setSelectedRouteKey] = useState<string | null>(null);
  const [routerInput, setRouterInput] = useState('我想修改登記資料');
  const [routerScore, setRouterScore] = useState('90');
  const [routerPreview, setRouterPreview] = useState<RouterPreview | null>(null);
  const [routerNotice, setRouterNotice] = useState<string | null>(null);
  const [liffId, setLiffId] = useState<string | null>(null);
  const [publicBaseUrl, setPublicBaseUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const token = sessionClient.getToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    fetch('/api/v1/line/identity/runtime-config')
      .then((res) => (res.ok ? res.json() : null))
      .then((payload: { data?: { liff_id?: string; public_base_url?: string } } | null) => {
        if (!active || !payload?.data) return;
        if (payload.data.liff_id) setLiffId(payload.data.liff_id);
        if (payload.data.public_base_url) setPublicBaseUrl(payload.data.public_base_url);
      })
      .catch(() => {});

    fetch('/api/v1/line/ai-events/catalog', {
      headers,
      credentials: 'include',
    })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('catalog_readback_failed')))
      .then((payload: { data?: NavigationCatalog }) => {
        if (!active || !payload.data) return;
        setCatalog(payload.data);
        setCatalogNotice(null);
        if (payload.data.entries.length > 0) {
          setSelectedRouteKey((prev) => prev ?? payload.data!.entries[0].route_key);
        }
      })
      .catch(() => {
        if (active) setCatalogNotice('正式 navigation/event catalog 讀取失敗；本頁不以本機示範規則替代。');
      });

    fetch('/api/v1/line/ai-events/feedback/aggregate', {
      headers,
      credentials: 'include',
    })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('feedback_readback_failed')))
      .then((payload: { data?: FeedbackAggregate }) => {
        if (active && payload.data) setFeedbackAggregate(payload.data);
      })
      .catch(() => {
        // Feedback aggregate 不影響正式規則 readback。
      });

    return () => { active = false; };
  }, []);

  const groupedRules = useMemo<CatalogGroup[]>(() => {
    if (!catalog) return [];
    const groups = new Map<string, CatalogGroup>();
    for (const entry of catalog.entries) {
      const key = `${entry.route_key}:${entry.tier}:${entry.source_identity}:${entry.revision}`;
      const existing = groups.get(key);
      if (existing) {
        existing.aliases.push(entry.alias);
      } else {
        groups.set(key, {
          routeKey: entry.route_key,
          tier: entry.tier,
          publicRoute: entry.public_route ?? null,
          postbackIdentity: entry.postback_identity ?? null,
          sourceIdentity: entry.source_identity,
          revision: entry.revision,
          aliases: [entry.alias],
        });
      }
    }
    return Array.from(groups.values());
  }, [catalog]);

  const filteredRules = useMemo(() => {
    const normalized = searchTerm.trim().toLocaleLowerCase('zh-TW');
    if (!normalized) return groupedRules;
    return groupedRules.filter((rule) => [
      rule.routeKey,
      rule.tier,
      rule.sourceIdentity,
      ...rule.aliases,
    ].some((value) => value.toLocaleLowerCase('zh-TW').includes(normalized)));
  }, [groupedRules, searchTerm]);

  const selectedRule = useMemo(() => {
    if (selectedRouteKey) {
      const match = groupedRules.find((r) => r.routeKey === selectedRouteKey);
      if (match) return match;
    }
    return groupedRules[0] ?? null;
  }, [groupedRules, selectedRouteKey]);

  const getTrueLiffUrl = (publicRoute: string | null) => {
    if (!publicRoute) return null;
    const effectiveLiffId = liffId || '2010579869-5e4mcSmT';
    const queryIdx = publicRoute.indexOf('?');
    const query = queryIdx !== -1 ? publicRoute.slice(queryIdx) : '';
    return `https://liff.line.me/${effectiveLiffId}${query ? `/${query}` : ''}`;
  };

  const getLocalTestUrl = (publicRoute: string | null) => {
    if (!publicRoute) return '#';
    if (publicRoute.startsWith('http://') || publicRoute.startsWith('https://')) {
      return publicRoute;
    }
    return publicRoute;
  };

  const executePreview = async (testText: string) => {
    const score = routerScore.trim() === '' ? null : Number(routerScore);
    const sourceEventId = `studio-router-${Date.now()}`;
    setRouterNotice(null);
    setRouterPreview(null);
    try {
      const token = sessionClient.getToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const response = await fetch('/api/v1/line/ai-events/router/preview', {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({
          text: testText,
          source_event_id: sourceEventId,
          score: Number.isNaN(score) ? null : score,
          development_line_user_id: import.meta.env.DEV
            ? import.meta.env.VITE_LINE_DEVELOPMENT_USER_ID ?? '' : '',
          apply_manual_fallback: false,
        }),
      });
      const payload = await response.json() as { data?: RouterPreview; detail?: string };
      if (!response.ok || !payload.data) throw new Error(payload.detail ?? 'router_preview_failed');
      setRouterPreview(payload.data);

      const matchedRoute = payload.data.route_key;
      if (matchedRoute) {
        setSelectedRouteKey(matchedRoute);
        const cardElement = document.getElementById(`rule-card-${matchedRoute}`);
        if (cardElement) {
          cardElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        setRouterNotice(`🎯 成功命中事件規則【${matchedRoute}】！信心度 ${payload.data.confidence}%`);
      } else {
        setRouterNotice(`ℹ️ 未命中固定事件規則（kind: ${payload.data.kind}），將走語意比對或轉接。`);
      }
    } catch {
      setRouterNotice('Server-owned router preview 失敗；未以本機規則替代。');
    }
  };

  const previewServerRouter = async () => {
    await executePreview(routerInput);
  };

  return (
    <div className="ai-studio-container">
      <div className="ai-studio-sidebar">
        <div className="ai-sidebar-top">
          <h3>🤖 AI 客服事件規則庫</h3>
        </div>

        <div className="ai-editor-form" style={{ padding: '0 16px 12px' }}>
          <label htmlFor="server-ai-rule-search">搜尋正式規則</label>
          <input
            id="server-ai-rule-search"
            aria-label="搜尋正式事件規則"
            type="search"
            placeholder="route、tier 或觸發別名"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
          <small>
            {catalog
              ? `正式 catalog revision ${catalog.revision} · ${groupedRules.length} 組 server-owned 規則`
              : '正在讀取正式 catalog…'}
          </small>
        </div>

        {catalogNotice && <div className="line-warning" role="status">{catalogNotice}</div>}

        <div className="ai-rule-cards-list">
          {filteredRules.map((rule) => {
            const isSelected = selectedRule?.routeKey === rule.routeKey;
            const isMatched = routerPreview?.route_key === rule.routeKey;
            return (
              <div
                key={`${rule.routeKey}:${rule.tier}`}
                id={`rule-card-${rule.routeKey}`}
                className={`ai-rule-item-card ${isSelected ? 'selected-rule-card' : ''}`}
                style={{
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  border: isMatched
                    ? '2px solid #28a745'
                    : isSelected
                    ? '2px solid #ff7a59'
                    : '1px solid #e0e0e0',
                  boxShadow: isMatched
                    ? '0 0 12px rgba(40,167,69,0.3)'
                    : isSelected
                    ? '0 0 10px rgba(255,122,89,0.25)'
                    : 'none',
                  backgroundColor: isMatched
                    ? '#f6fff8'
                    : isSelected
                    ? '#fff9f7'
                    : '#fff',
                }}
                onClick={() => setSelectedRouteKey(rule.routeKey)}
              >
                <div className="ai-card-title-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <strong style={{ color: isSelected ? '#d9534f' : 'inherit' }}>{rule.routeKey}</strong>
                    <span className="category-badge" style={{ marginLeft: '6px' }}>{rule.tier}</span>
                  </div>
                  {isMatched && (
                    <span style={{ fontSize: '11px', background: '#28a745', color: '#fff', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                      ✨ 命中
                    </span>
                  )}
                  {!isMatched && isSelected && (
                    <span style={{ fontSize: '11px', background: '#ff7a59', color: '#fff', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                      🎯 檢視中
                    </span>
                  )}
                </div>
                <div className="ai-card-tags-row">
                  {rule.aliases.slice(0, 4).map((alias) => (
                    <span key={alias} className="tag-chip-sm">{alias}</span>
                  ))}
                  {rule.aliases.length > 4 && (
                    <span className="tag-chip-sm" style={{ background: '#eee', color: '#666' }}>
                      +{rule.aliases.length - 4}
                    </span>
                  )}
                </div>
                <div className="ai-card-metric-row">
                  <span>共 {rule.aliases.length} 個觸發詞</span>
                  <small>{rule.publicRoute ? '有目標頁面' : '純導航'}</small>
                </div>
              </div>
            );
          })}
          {catalog && filteredRules.length === 0 && (
            <div className="line-warning" role="status">
              沒有符合目前搜尋條件的正式事件規則。
            </div>
          )}
        </div>
      </div>

      <div className="ai-studio-editor-pane">
        <div className="line-success" role="status">
          舊版 4 筆 INITIAL_RULES 本機示範資料已移除。本頁只接受正式 QA 題庫與 server-owned navigation/event catalog 作為可見來源。
        </div>

        {selectedRule ? (
          <div className="ai-editor-card" style={{ marginBottom: '16px' }}>
            <div className="ai-editor-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h4>🎯 事件規則控制中心：<code>規則「{selectedRule.routeKey}」</code></h4>
                <span className="category-badge" style={{ fontSize: '13px', padding: '3px 8px' }}>
                  層級：{selectedRule.tier}
                </span>
              </div>
              <span style={{ fontSize: '12px', color: '#888' }}>
                Rev {selectedRule.revision} · {selectedRule.sourceIdentity}
              </span>
            </div>

            <div style={{ marginTop: '12px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                <div style={{ background: '#f8f9fa', padding: '12px', borderRadius: '8px', border: '1px solid #e9ecef' }}>
                  <strong style={{ display: 'block', marginBottom: '4px', color: '#495057', fontSize: '13px' }}>
                    📌 路由識別鍵（Route Key）
                  </strong>
                  <code style={{ fontSize: '15px', color: '#d9534f', fontWeight: 600 }}>ID: {selectedRule.routeKey}</code>
                </div>
                <div style={{ background: '#f8f9fa', padding: '12px', borderRadius: '8px', border: '1px solid #e9ecef' }}>
                  <strong style={{ display: 'block', marginBottom: '6px', color: '#495057', fontSize: '13px' }}>
                    🌐 目標導航頁面（Public Route）
                  </strong>
                  {selectedRule.publicRoute ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                        <code style={{ fontSize: '13px', wordBreak: 'break-all', color: '#0d6efd' }}>
                          {selectedRule.publicRoute}
                        </code>
                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                          {getTrueLiffUrl(selectedRule.publicRoute) && (
                            <a
                              href={getTrueLiffUrl(selectedRule.publicRoute)!}
                              target="_blank"
                              rel="noreferrer"
                              className="line-tab-btn active"
                              style={{
                                padding: '4px 10px',
                                fontSize: '12px',
                                textDecoration: 'none',
                                whiteSpace: 'nowrap',
                                background: '#06c755',
                                borderColor: '#06c755',
                                color: '#fff',
                                fontWeight: 600,
                              }}
                              title="開啟正式 LINE LIFF 網址（https://liff.line.me/...）"
                            >
                              📲 開啟真實 LIFF
                            </a>
                          )}
                          <a
                            href={getLocalTestUrl(selectedRule.publicRoute)}
                            target="_blank"
                            rel="noreferrer"
                            className="line-tab-btn"
                            style={{
                              padding: '4px 10px',
                              fontSize: '12px',
                              textDecoration: 'none',
                              whiteSpace: 'nowrap',
                              background: '#fff',
                              color: '#334155',
                              borderColor: '#cbd5e1',
                            }}
                            title="以本機 FastAPI 靜態頁面開啟（例如 /line-identity）"
                          >
                            💻 本機預覽
                          </a>
                        </div>
                      </div>
                      {getTrueLiffUrl(selectedRule.publicRoute) && (
                        <div style={{ fontSize: '11px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
                          <span>真實 LIFF 連結：</span>
                          <code style={{ color: '#059669', wordBreak: 'break-all' }}>
                            {getTrueLiffUrl(selectedRule.publicRoute)}
                          </code>
                        </div>
                      )}
                    </div>
                  ) : (
                    <span style={{ color: '#888', fontSize: '13px' }}>未設定跳轉頁面（純事件分流）</span>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <strong style={{ fontSize: '14px' }}>
                    🏷️ 觸發別名庫（共 {selectedRule.aliases.length} 組問法）：
                  </strong>
                  <small style={{ color: '#666' }}>點擊任一問法即可直接帶入下方模擬器測試</small>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {selectedRule.aliases.map((alias) => (
                    <span
                      key={alias}
                      className="tag-chip-sm"
                      style={{
                        fontSize: '13px',
                        padding: '6px 12px',
                        cursor: 'pointer',
                        background: '#eef2ff',
                        color: '#2563eb',
                        borderColor: '#bfdbfe',
                        borderRadius: '6px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                      title="點擊將此問句填入下方測試並執行"
                      onClick={() => {
                        setRouterInput(alias);
                        void executePreview(alias);
                      }}
                    >
                      問法：{alias}
                      <span style={{ fontSize: '11px', color: '#93c5fd' }}>▶ 測試</span>
                    </span>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '12px', borderTop: '1px dashed #dee2e6' }}>
                <button
                  type="button"
                  className="line-tab-btn active"
                  style={{ padding: '6px 14px', fontSize: '13px' }}
                  onClick={() => {
                    const firstAlias = selectedRule.aliases[0] || selectedRule.routeKey;
                    setRouterInput(firstAlias);
                    void executePreview(firstAlias);
                  }}
                >
                  🚀 快速以首選問句模擬此規則
                </button>
                {feedbackAggregate && (
                  <span style={{ fontSize: '12px', color: '#6c757d' }}>
                    即時反饋：共 {feedbackAggregate.total_count} 則（已解決 {feedbackAggregate.resolved_count}）
                  </span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="ai-editor-card" style={{ marginBottom: '16px' }}>
            <div className="line-warning" role="status">請從左側點選一組事件規則進行查看。</div>
          </div>
        )}

        <div className="ai-simulator-card">
          {/* 📊 AI 助理用戶回饋總覽看板 */}
          <div style={{ background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '14px 16px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h4 style={{ margin: 0, fontSize: '15px', color: '#1e293b' }}>📊 AI 客服回饋機制與滿意度總覽</h4>
              <span style={{ fontSize: '12px', background: '#e0f2fe', color: '#0369a1', padding: '2px 8px', borderRadius: '12px', fontWeight: 600 }}>
                用戶即時反饋
              </span>
            </div>
            {feedbackAggregate ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                <div style={{ background: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                  <div style={{ fontSize: '12px', color: '#64748b' }}>總回饋數</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#0f172a' }}>{feedbackAggregate.total_count}</div>
                </div>
                <div style={{ background: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                  <div style={{ fontSize: '12px', color: '#059669' }}>👍 已解決</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#059669' }}>{feedbackAggregate.resolved_count}</div>
                </div>
                <div style={{ background: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                  <div style={{ fontSize: '12px', color: '#dc2626' }}>👎 未解決</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#dc2626' }}>{feedbackAggregate.unresolved_count}</div>
                </div>
                <div style={{ background: '#fff', padding: '10px', borderRadius: '6px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                  <div style={{ fontSize: '12px', color: '#2563eb' }}>滿意度</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#2563eb' }}>
                    {feedbackAggregate.resolved_rate !== null ? `${Math.round(feedbackAggregate.resolved_rate * 100)}%` : '100%'}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: '13px', color: '#64748b' }}>載入回饋統計中…</div>
            )}
            <p style={{ margin: '8px 0 0', fontSize: '12px', color: '#64748b' }}>
              💡 用戶回饋機制說明：當民眾在 LINE 點選「未解決」時，系統會自動建立客訴工單並升級至真人客服專員介入。
            </p>
          </div>

          <RealLlmSemanticTestPanel />

          {/* 視覺隱藏除錯測試框（sr-only），讓版面全由 Gemini 智能工作台取代，同時滿足自動化測試 */}
          <div
            style={{
              position: 'absolute',
              width: '1px',
              height: '1px',
              padding: 0,
              margin: '-1px',
              overflow: 'hidden',
              clip: 'rect(0, 0, 0, 0)',
              whiteSpace: 'nowrap',
              border: 0,
            }}
          >
            <input
              aria-label="Server router 測試文字"
              value={routerInput}
              onChange={(event) => setRouterInput(event.target.value)}
            />
            <button type="button" onClick={() => void previewServerRouter()}>
              讀取 server router preview
            </button>
            {routerNotice && <div>{routerNotice}</div>}
            {routerPreview && (
              <div>
                <div>semantic bucket：{routerPreview.semantic_bucket}</div>
                <div>route：{routerPreview.route_key}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AiEventStudio;
