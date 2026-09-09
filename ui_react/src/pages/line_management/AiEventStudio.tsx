/**
 * File: AiEventStudio.tsx
 * Description: 僅顯示 server-owned AI 客服事件／導航規則與正式測試，不再內建本機示範規則。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  Laptop,
  Lightbulb,
  Navigation,
  Play,
  Route,
  Tag,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { sessionClient } from '../../api/auth/session_client';
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
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedRouteKey, setSelectedRouteKey] = useState<string | null>(null);
  const [routerInput, setRouterInput] = useState('我想修改登記資料');
  const routerScore = '90';
  const [routerPreview, setRouterPreview] = useState<RouterPreview | null>(null);
  const [routerNotice, setRouterNotice] = useState<string | null>(null);
  const [routerNoticeKind, setRouterNoticeKind] = useState<'success' | 'info' | 'error' | null>(null);
  const [routerBusy, setRouterBusy] = useState(false);
  const [liffId, setLiffId] = useState<string | null>(null);

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
        if (active && payload.data) {
          setFeedbackAggregate(payload.data);
          setFeedbackNotice(null);
        }
      })
      .catch(() => {
        if (active) setFeedbackNotice('回饋統計讀取失敗，請稍後重新整理。');
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
    if (!publicRoute || !liffId) return null;
    const queryIdx = publicRoute.indexOf('?');
    const query = queryIdx !== -1 ? publicRoute.slice(queryIdx) : '';
    return `https://liff.line.me/${liffId}${query ? `/${query}` : ''}`;
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
    setRouterNoticeKind(null);
    setRouterPreview(null);
    setRouterBusy(true);
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
        setRouterNotice(`成功命中事件規則【${matchedRoute}】，信心度 ${payload.data.confidence}%`);
        setRouterNoticeKind('success');
      } else {
        setRouterNotice(`未命中固定事件規則（kind: ${payload.data.kind}），將走語意比對或轉接。`);
        setRouterNoticeKind('info');
      }
    } catch {
      setRouterNotice('Server-owned router preview 失敗；未以本機規則替代。');
      setRouterNoticeKind('error');
    } finally {
      setRouterBusy(false);
    }
  };

  const previewServerRouter = async () => {
    await executePreview(routerInput);
  };

  return (
    <div className="ai-studio-container">
      <div className="ai-studio-sidebar">
        <div className="ai-sidebar-top">
          <h3><Bot aria-hidden="true" />AI 客服事件規則庫</h3>
        </div>

        <div className="ai-editor-form ai-rule-search-form">
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
                className={`ai-rule-item-card${isSelected ? ' is-selected' : ''}${isMatched ? ' is-matched' : ''}`}
                onClick={() => setSelectedRouteKey(rule.routeKey)}
              >
                <div className="ai-card-title-row">
                  <div>
                    <strong>{rule.routeKey}</strong>
                    <span className="category-badge ai-rule-tier">{rule.tier}</span>
                  </div>
                  {isMatched && (
                    <span className="ai-rule-state is-matched">
                      <CheckCircle2 aria-hidden="true" />命中
                    </span>
                  )}
                  {!isMatched && isSelected && (
                    <span className="ai-rule-state is-selected">
                      <Navigation aria-hidden="true" />檢視中
                    </span>
                  )}
                </div>
                <div className="ai-card-tags-row">
                  {rule.aliases.slice(0, 4).map((alias) => (
                    <span key={alias} className="tag-chip-sm">{alias}</span>
                  ))}
                  {rule.aliases.length > 4 && (
                    <span className="tag-chip-sm ai-rule-more-count">
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
          <div className="ai-editor-card ai-rule-detail-card">
            <div className="ai-editor-header">
              <div className="ai-editor-heading-group">
                <h4><Route aria-hidden="true" />事件規則：<code>{selectedRule.routeKey}</code></h4>
                <span className="category-badge ai-rule-detail-tier">
                  層級：{selectedRule.tier}
                </span>
              </div>
              <span className="ai-rule-revision">
                Rev {selectedRule.revision} · {selectedRule.sourceIdentity}
              </span>
            </div>

            <div className="ai-rule-detail-body">
              <div className="ai-rule-fact-grid">
                <div className="ai-rule-fact-card">
                  <strong><Route aria-hidden="true" />路由識別鍵（Route Key）
                  </strong>
                  <code className="ai-route-key">ID: {selectedRule.routeKey}</code>
                </div>
                <div className="ai-rule-fact-card">
                  <strong><Navigation aria-hidden="true" />目標導航頁面（Public Route）
                  </strong>
                  {selectedRule.publicRoute ? (
                    <div className="ai-route-stack">
                      <div className="ai-route-row">
                        <code className="ai-public-route">
                          {selectedRule.publicRoute}
                        </code>
                        <div className="ai-route-actions">
                          {getTrueLiffUrl(selectedRule.publicRoute) && (
                            <a
                              href={getTrueLiffUrl(selectedRule.publicRoute)!}
                              target="_blank"
                              rel="noreferrer"
                              className="ai-route-link is-liff"
                              title="開啟正式 LINE LIFF 網址（https://liff.line.me/...）"
                            >
                              <ExternalLink aria-hidden="true" />開啟真實 LIFF
                            </a>
                          )}
                          <a
                            href={getLocalTestUrl(selectedRule.publicRoute)}
                            target="_blank"
                            rel="noreferrer"
                            className="ai-route-link"
                            title="以本機 FastAPI 靜態頁面開啟（例如 /line-identity）"
                          >
                            <Laptop aria-hidden="true" />本機預覽
                          </a>
                        </div>
                      </div>
                      {getTrueLiffUrl(selectedRule.publicRoute) && (
                        <div className="ai-liff-url">
                          <span>真實 LIFF 連結：</span>
                          <code>
                            {getTrueLiffUrl(selectedRule.publicRoute)}
                          </code>
                        </div>
                      )}
                      {!liffId && (
                        <small className="ai-route-config-note">尚未從 runtime config 取得 LIFF ID，因此不顯示正式 LIFF 連結。</small>
                      )}
                    </div>
                  ) : (
                    <span className="ai-route-empty">未設定跳轉頁面（純事件分流）</span>
                  )}
                </div>
              </div>

              <div className="ai-alias-section">
                <div className="ai-alias-header">
                  <strong><Tag aria-hidden="true" />觸發別名庫（共 {selectedRule.aliases.length} 組問法）
                  </strong>
                  <small>選擇任一問法即可帶入下方模擬器測試</small>
                </div>
                <div className="ai-alias-list">
                  {selectedRule.aliases.map((alias) => (
                    <button
                      type="button"
                      key={alias}
                      className="ai-alias-button"
                      title="點擊將此問句填入下方測試並執行"
                      onClick={() => {
                        setRouterInput(alias);
                        void executePreview(alias);
                      }}
                    >
                      問法：{alias}
                      <span><Play aria-hidden="true" />測試</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="ai-rule-quick-row">
                <button
                  type="button"
                  className="line-primary-btn"
                  onClick={() => {
                    const firstAlias = selectedRule.aliases[0] || selectedRule.routeKey;
                    setRouterInput(firstAlias);
                    void executePreview(firstAlias);
                  }}
                >
                  <Play aria-hidden="true" />以首選問句模擬此規則
                </button>
                {feedbackAggregate && (
                  <span className="ai-feedback-inline-summary">
                    即時反饋：共 {feedbackAggregate.total_count} 則（已解決 {feedbackAggregate.resolved_count}）
                  </span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="ai-editor-card ai-rule-detail-card">
            <div className="line-warning" role="status">請從左側點選一組事件規則進行查看。</div>
          </div>
        )}

        <div className="ai-simulator-card">
          <section className="ai-feedback-overview" aria-labelledby="ai-feedback-title">
            <div className="ai-feedback-header">
              <h4 id="ai-feedback-title"><ThumbsUp aria-hidden="true" />AI 客服回饋與滿意度</h4>
              <span className="ai-feedback-badge">
                用戶即時反饋
              </span>
            </div>
            {feedbackAggregate ? (
              <div className="ai-feedback-grid">
                <div className="ai-feedback-metric">
                  <span>總回饋數</span>
                  <strong>{feedbackAggregate.total_count}</strong>
                </div>
                <div className="ai-feedback-metric is-positive">
                  <span><ThumbsUp aria-hidden="true" />已解決</span>
                  <strong>{feedbackAggregate.resolved_count}</strong>
                </div>
                <div className="ai-feedback-metric is-negative">
                  <span><ThumbsDown aria-hidden="true" />未解決</span>
                  <strong>{feedbackAggregate.unresolved_count}</strong>
                </div>
                <div className="ai-feedback-metric is-rate">
                  <span>滿意度</span>
                  <strong>
                    {feedbackAggregate.resolved_rate !== null ? `${Math.round(feedbackAggregate.resolved_rate * 100)}%` : '尚無回饋'}
                  </strong>
                </div>
              </div>
            ) : feedbackNotice ? (
              <div className="line-warning" role="status"><CircleAlert aria-hidden="true" />{feedbackNotice}</div>
            ) : (
              <div className="ai-feedback-loading" role="status">載入回饋統計中…</div>
            )}
            <p className="ai-feedback-help">
              <Lightbulb aria-hidden="true" />民眾在 LINE 選擇「未解決」後，系統會建立客訴工單並轉由真人客服處理。
            </p>
          </section>

          <section className="ai-router-simulator" aria-labelledby="ai-router-simulator-title">
            <div className="ai-router-simulator-heading">
              <div>
                <h4 id="ai-router-simulator-title"><Navigation aria-hidden="true" />事件路由模擬器</h4>
                <p>送到正式 server-owned router 預覽端點；不會套用或儲存變更。</p>
              </div>
            </div>
            <label htmlFor="server-router-input">測試問句</label>
            <div className="ai-router-input-row">
            <input
              id="server-router-input"
              aria-label="Server router 測試文字"
              value={routerInput}
              onChange={(event) => setRouterInput(event.target.value)}
            />
            <button type="button" className="line-primary-btn" disabled={routerBusy || !routerInput.trim()} onClick={() => void previewServerRouter()}>
              <Play aria-hidden="true" />{routerBusy ? '測試中…' : '讀取 server router preview'}
            </button>
            </div>
            {!routerNotice && !routerPreview && <p className="ai-router-empty">尚未執行路由測試。</p>}
            {routerNotice && <div className={`ai-router-notice is-${routerNoticeKind ?? 'info'}`} role="status">{routerNotice}</div>}
            {routerPreview && (
              <div className="ai-router-result" aria-label="路由測試結果">
                <div><span>semantic bucket</span><strong>{routerPreview.semantic_bucket}</strong></div>
                <div><span>route</span><strong>{routerPreview.route_key ?? '未命中固定路由'}</strong></div>
                <div><span>信心度</span><strong>{routerPreview.confidence}%</strong></div>
                <div><span>結果類型</span><strong>{routerPreview.kind}</strong></div>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
};

export default AiEventStudio;
