/**
 * File: AiEventStudio.tsx
 * Description: 僅顯示 server-owned AI 客服事件／導航規則與正式測試，不再內建本機示範規則。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { RealLlmSemanticTestPanel } from './RealLlmSemanticTestPanel';
import '../LineManagementPage.css';

interface NavigationCatalogEntry {
  alias: string;
  route_key: string;
  tier: string;
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
  sourceIdentity: string;
  revision: number;
  aliases: string[];
}

export const AiEventStudio: React.FC = () => {
  const [catalog, setCatalog] = useState<NavigationCatalog | null>(null);
  const [feedbackAggregate, setFeedbackAggregate] = useState<FeedbackAggregate | null>(null);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [routerInput, setRouterInput] = useState('我想修改登記資料');
  const [routerScore, setRouterScore] = useState('90');
  const [routerPreview, setRouterPreview] = useState<RouterPreview | null>(null);
  const [routerNotice, setRouterNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch('/api/v1/line/ai-events/catalog')
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('catalog_readback_failed')))
      .then((payload: { data?: NavigationCatalog }) => {
        if (!active || !payload.data) return;
        setCatalog(payload.data);
        setCatalogNotice(null);
      })
      .catch(() => {
        if (active) setCatalogNotice('正式 navigation/event catalog 讀取失敗；本頁不以本機示範規則替代。');
      });

    fetch('/api/v1/line/ai-events/feedback/aggregate')
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

  const previewServerRouter = async () => {
    const score = routerScore.trim() === '' ? null : Number(routerScore);
    const sourceEventId = `studio-router-${Date.now()}`;
    setRouterNotice(null);
    setRouterPreview(null);
    try {
      const response = await fetch('/api/v1/line/ai-events/router/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: routerInput,
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
      setRouterNotice('Server-owned router preview 已讀回；本次不寫入資料、不發送 LINE。');
    } catch {
      setRouterNotice('Server-owned router preview 失敗；未以本機規則替代。');
    }
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
          {filteredRules.map((rule) => (
            <div key={`${rule.routeKey}:${rule.tier}`} className="ai-rule-item-card">
              <div className="ai-card-title-row">
                <strong>{rule.routeKey}</strong>
                <span className="category-badge">{rule.tier}</span>
              </div>
              <div className="ai-card-tags-row">
                {rule.aliases.map((alias) => (
                  <span key={alias} className="tag-chip-sm">{alias}</span>
                ))}
              </div>
              <div className="ai-card-metric-row">
                <span>revision {rule.revision}</span>
                <small>{rule.sourceIdentity}</small>
              </div>
            </div>
          ))}
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

        <div className="ai-editor-card">
          <div className="ai-editor-header">
            <h4>🧭 正式事件規則狀態</h4>
          </div>
          {catalog ? (
            <div className="ai-editor-form">
              <div>Catalog revision：{catalog.revision}</div>
              <div>Server-owned aliases：{catalog.entries.length}</div>
              <div>Grouped routes：{groupedRules.length}</div>
              {feedbackAggregate && (
                <div>
                  Feedback：{feedbackAggregate.total_count} 則 · 已解決 {feedbackAggregate.resolved_count} · 未解決 {feedbackAggregate.unresolved_count}
                  {feedbackAggregate.resolved_rate === null ? '' : ` · ${Math.round(feedbackAggregate.resolved_rate * 100)}% resolved`}
                </div>
              )}
            </div>
          ) : (
            <div className="line-warning" role="status">尚未取得正式事件規則 catalog。</div>
          )}
        </div>

        <div className="ai-simulator-card">
          <RealLlmSemanticTestPanel />

          <h4>🧭 Server-owned router preview</h4>
          <div className="line-warning" role="status">
            此區只讀取伺服器正式 router outcome；不再使用已移除的本機 INITIAL_RULES 做假比對。
          </div>
          <div className="sim-input-bar">
            <input
              aria-label="Server router 測試文字"
              value={routerInput}
              onChange={(event) => setRouterInput(event.target.value)}
            />
            <input
              aria-label="Server router confidence"
              type="number"
              min="0"
              max="100"
              value={routerScore}
              onChange={(event) => setRouterScore(event.target.value)}
            />
            <button type="button" className="mock-primary-btn" onClick={() => void previewServerRouter()}>
              讀取 server router preview
            </button>
          </div>

          {routerNotice && <div className="line-warning" role="status">{routerNotice}</div>}
          {routerPreview && (
            <div className="line-success" role="status">
              <div>結果：{routerPreview.kind} · semantic bucket：{routerPreview.semantic_bucket} · confidence：{routerPreview.confidence}</div>
              <div>reason：{routerPreview.reason_code ?? '—'} · score band：{routerPreview.score_band ?? '—'}</div>
              <div>source：{routerPreview.source_identity} · revision {routerPreview.source_revision}</div>
              {routerPreview.route_key && <div>route：{routerPreview.route_key}</div>}
              {routerPreview.options.length > 0 && <div>options：{routerPreview.options.join('、')}</div>}
              {routerPreview.answer_text && <div>{routerPreview.answer_text}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AiEventStudio;
