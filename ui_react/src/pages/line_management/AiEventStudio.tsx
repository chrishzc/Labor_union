/**
 * File: AiEventStudio.tsx
 * Description: AI 客服引導動作工作室，提供分類篩選、觸發指令編輯維護與路由預覽。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  ExternalLink,
  Laptop,
  Navigation,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Save,
  ShieldCheck,
  X,
} from 'lucide-react';
import { applicationFetch } from '../../api/shared/application_fetch';
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

type TierCategory = 'all' | 'navigation' | 'identity' | 'admin';

const TIER_LABELS: Record<string, string> = {
  navigation: '服務導覽',
  identity: '身分綁定',
  admin: '工會管理',
};

export const AiEventStudio: React.FC = () => {
  const [catalog, setCatalog] = useState<NavigationCatalog | null>(null);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTier, setSelectedTier] = useState<TierCategory>('all');
  const [selectedRouteKey, setSelectedRouteKey] = useState<string | null>(null);
  const [routerInput, setRouterInput] = useState('我想修改登記資料');
  const routerScore = '90';
  const [routerPreview, setRouterPreview] = useState<RouterPreview | null>(null);
  const [routerNotice, setRouterNotice] = useState<string | null>(null);
  const [routerNoticeKind, setRouterNoticeKind] = useState<'success' | 'info' | 'error' | null>(null);
  const [routerBusy, setRouterBusy] = useState(false);
  const [liffId, setLiffId] = useState<string | null>(null);

  // Alias editing state
  const [isEditingAliases, setIsEditingAliases] = useState(false);
  const [editingAliases, setEditingAliases] = useState<string[]>([]);
  const [newAliasInput, setNewAliasInput] = useState('');
  const [aliasSaveBusy, setAliasSaveBusy] = useState(false);
  const [aliasEditError, setAliasEditError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const token = sessionClient.getToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    applicationFetch('/api/v1/line/identity/runtime-config')
      .then((res) => (res.ok ? res.json() : null))
      .then((payload: { data?: { liff_id?: string; public_base_url?: string } } | null) => {
        if (!active || !payload?.data) return;
        if (payload.data.liff_id) setLiffId(payload.data.liff_id);
      })
      .catch(() => {});

    applicationFetch('/api/v1/line/ai-events/catalog', {
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
        if (active) setCatalogNotice('引導動作讀取失敗，請稍後重新整理。');
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
    return groupedRules.filter((rule) => {
      if (selectedTier !== 'all' && rule.tier !== selectedTier) {
        return false;
      }
      if (!normalized) return true;
      return [
        rule.routeKey,
        rule.tier,
        TIER_LABELS[rule.tier] ?? '',
        rule.sourceIdentity,
        ...rule.aliases,
      ].some((value) => value.toLocaleLowerCase('zh-TW').includes(normalized));
    });
  }, [groupedRules, searchTerm, selectedTier]);

  const selectedRule = useMemo(() => {
    if (selectedRouteKey) {
      const match = groupedRules.find((r) => r.routeKey === selectedRouteKey);
      if (match) return match;
    }
    return filteredRules[0] ?? groupedRules[0] ?? null;
  }, [groupedRules, filteredRules, selectedRouteKey]);

  const selectRule = (routeKey: string) => {
    setSelectedRouteKey(routeKey);
    setIsEditingAliases(false);
    setAliasEditError(null);
    setNewAliasInput('');
  };

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

  const startEditing = () => {
    if (!selectedRule) return;
    setEditingAliases([...selectedRule.aliases]);
    setNewAliasInput('');
    setAliasEditError(null);
    setIsEditingAliases(true);
  };

  const handleAddAlias = () => {
    const trimmed = newAliasInput.trim();
    if (!trimmed) {
      setAliasEditError('請輸入觸發指令');
      return;
    }
    if (editingAliases.includes(trimmed)) {
      setAliasEditError('該指令已存在於目前清單中');
      return;
    }
    setEditingAliases((prev) => [...prev, trimmed]);
    setNewAliasInput('');
    setAliasEditError(null);
  };

  const handleRemoveAlias = (indexToRemove: number) => {
    if (editingAliases.length <= 1) {
      setAliasEditError('至少需保留一個觸發指令');
      return;
    }
    setEditingAliases((prev) => prev.filter((_, idx) => idx !== indexToRemove));
    setAliasEditError(null);
  };

  const handleSaveAliases = async () => {
    if (!selectedRule) return;
    if (editingAliases.length === 0) {
      setAliasEditError('至少需保留一個觸發指令');
      return;
    }
    setAliasSaveBusy(true);
    setAliasEditError(null);
    try {
      const token = sessionClient.getToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const response = await applicationFetch(`/api/v1/line/ai-events/catalog/${selectedRule.routeKey}/aliases`, {
        method: 'PUT',
        headers,
        credentials: 'include',
        body: JSON.stringify({ aliases: editingAliases }),
      });
      const payload = (await response.json()) as { data?: NavigationCatalog; message?: string; detail?: string };
      if (!response.ok || !payload.data) {
        throw new Error(payload.detail ?? '更新觸發指令失敗');
      }
      setCatalog(payload.data);
      setIsEditingAliases(false);
      setRouterNotice(`已成功更新「${selectedRule.aliases[0] || selectedRule.routeKey}」的觸發指令。`);
      setRouterNoticeKind('success');
    } catch (err: any) {
      const msg = err.message || '';
      if (msg.includes('alias_conflict')) {
        setAliasEditError('部分指令已屬於其他引導動作，無法重複設定。');
      } else {
        setAliasEditError(msg || '儲存指令失敗，請稍後再試。');
      }
    } finally {
      setAliasSaveBusy(false);
    }
  };

  const handleResetAliases = async () => {
    if (!selectedRule) return;
    setAliasSaveBusy(true);
    setAliasEditError(null);
    try {
      const token = sessionClient.getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const response = await applicationFetch(`/api/v1/line/ai-events/catalog/${selectedRule.routeKey}/reset`, {
        method: 'POST',
        headers,
        credentials: 'include',
      });
      const payload = (await response.json()) as { data?: NavigationCatalog; message?: string; detail?: string };
      if (!response.ok || !payload.data) {
        throw new Error(payload.detail ?? '恢復預設失敗');
      }
      setCatalog(payload.data);
      setIsEditingAliases(false);
      setRouterNotice(`已恢復「${selectedRule.aliases[0] || selectedRule.routeKey}」的預設觸發指令。`);
      setRouterNoticeKind('info');
    } catch (err: any) {
      setAliasEditError(err.message || '恢復預設失敗，請稍後再試。');
    } finally {
      setAliasSaveBusy(false);
    }
  };

  const executePreview = async (testText: string) => {
    if (routerBusy || !testText.trim()) return;
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
      const response = await applicationFetch('/api/v1/line/ai-events/router/preview', {
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
        setRouterNotice('已找到符合的引導動作。');
        setRouterNoticeKind('success');
      } else {
        setRouterNotice('未命中固定引導動作，請查看詳細結果。');
        setRouterNoticeKind('info');
      }
    } catch {
      setRouterNotice('引導動作預覽失敗，請稍後再試。');
      setRouterNoticeKind('error');
    } finally {
      setRouterBusy(false);
    }
  };

  const previewServerRouter = async () => {
    await executePreview(routerInput);
  };

  return (
    <div className="ai-studio-container studio-guidance-layout">
      <aside className="ai-studio-sidebar">
        <div className="ai-sidebar-top">
          <h3><Bot aria-hidden="true" />引導動作</h3>
        </div>

        <div className="liff-filter-pills studio-tier-pills" role="tablist" aria-label="引導動作分類">
          <button
            type="button"
            role="tab"
            aria-selected={selectedTier === 'all'}
            className={selectedTier === 'all' ? 'active' : ''}
            onClick={() => setSelectedTier('all')}
          >
            全部 ({groupedRules.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={selectedTier === 'navigation'}
            className={selectedTier === 'navigation' ? 'active' : ''}
            onClick={() => setSelectedTier('navigation')}
          >
            服務導覽 ({groupedRules.filter((r) => r.tier === 'navigation').length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={selectedTier === 'identity'}
            className={selectedTier === 'identity' ? 'active' : ''}
            onClick={() => setSelectedTier('identity')}
          >
            身分綁定 ({groupedRules.filter((r) => r.tier === 'identity').length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={selectedTier === 'admin'}
            className={selectedTier === 'admin' ? 'active' : ''}
            onClick={() => setSelectedTier('admin')}
          >
            工會管理 ({groupedRules.filter((r) => r.tier === 'admin').length})
          </button>
        </div>

        <div className="ai-editor-form ai-rule-search-form">
          <label htmlFor="server-ai-rule-search">搜尋引導動作</label>
          <input
            id="server-ai-rule-search"
            type="search"
            placeholder="搜尋動作、分類或常見問法"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
          <small>{catalog ? `目前顯示 ${filteredRules.length} / 共 ${groupedRules.length} 組引導動作` : '正在讀取引導動作…'}</small>
        </div>

        {catalogNotice && <div className="line-warning" role="status">{catalogNotice}</div>}

        <div className="ai-rule-cards-list">
          {filteredRules.map((rule) => {
            const isSelected = selectedRule?.routeKey === rule.routeKey;
            const isMatched = routerPreview?.route_key === rule.routeKey;
            return (
              <button
                type="button"
                key={`${rule.routeKey}:${rule.tier}`}
                id={`rule-card-${rule.routeKey}`}
                aria-pressed={isSelected}
                className={`ai-rule-item-card studio-rule-choice${isSelected ? ' is-selected' : ''}${isMatched ? ' is-matched' : ''}`}
                onClick={() => selectRule(rule.routeKey)}
              >
                <span className="ai-card-title-row">
                  <strong>{rule.aliases[0] || rule.routeKey}</strong>
                  <span className={`studio-category-pill is-${rule.tier}`}>
                    {TIER_LABELS[rule.tier] || rule.tier}
                  </span>
                  {isMatched && <span className="ai-rule-state is-matched"><CheckCircle2 aria-hidden="true" />命中</span>}
                </span>
                <span className="ai-card-metric-row">{rule.aliases.length} 種常見問法 · {rule.publicRoute ? '導向服務頁面' : '依系統流程處理'}</span>
              </button>
            );
          })}
          {catalog && filteredRules.length === 0 && <p className="studio-empty" role="status">沒有符合條件的引導動作。</p>}
        </div>
        <p className="studio-readonly-note"><ShieldCheck aria-hidden="true" />自訂觸發指令儲存後立即於 LINE 生效</p>
      </aside>

      <div className="ai-studio-editor-pane">
        {selectedRule ? (
          <div className="ai-editor-card ai-rule-detail-card">
            <div className="ai-editor-header">
              <div>
                <h2>{selectedRule.aliases[0] || selectedRule.routeKey}</h2>
                <p className="studio-description">查看觸發問法、服務入口與引導結果。</p>
              </div>
              <span className="studio-editable-badge">可自訂觸發指令</span>
            </div>

            <div className="studio-guidance-target">
              <Navigation aria-hidden="true" />
              <div>
                <small>觸發後的服務入口</small>
                <strong>{selectedRule.publicRoute ? '導向服務頁面' : '依系統流程處理'}</strong>
              </div>
              {selectedRule.publicRoute && getTrueLiffUrl(selectedRule.publicRoute) && (
                <a href={getTrueLiffUrl(selectedRule.publicRoute)!} target="_blank" rel="noreferrer" className="ai-route-link is-liff">
                  <ExternalLink aria-hidden="true" />開啟服務頁面
                </a>
              )}
            </div>

            {!isEditingAliases ? (
              <div className="ai-alias-section">
                <div className="ai-alias-header">
                  <strong>常見觸發問法</strong>
                  <div className="studio-alias-header-actions">
                    <small>點選帶入問句，再按「預覽引導動作」。</small>
                    <button
                      type="button"
                      className="studio-edit-aliases-btn"
                      onClick={startEditing}
                    >
                      <Pencil aria-hidden="true" /> 編輯指令
                    </button>
                  </div>
                </div>
                <div className="ai-alias-list">
                  {selectedRule.aliases.map((alias) => (
                    <button
                      type="button"
                      key={alias}
                      className="ai-alias-button"
                      disabled={routerBusy}
                      onClick={() => {
                        setRouterInput(alias);
                        setRouterPreview(null);
                        setRouterNotice(null);
                      }}
                    >
                      {alias}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="ai-alias-section studio-alias-edit-box">
                <div className="ai-alias-header">
                  <strong>編輯觸發指令（常見問法）</strong>
                  <small>點選指令旁的 ✕ 可移除，輸入文字可新增別名；儲存後立即於 LINE 與預覽生效。</small>
                </div>

                <div className="studio-alias-edit-tags">
                  {editingAliases.map((alias, idx) => (
                    <span key={`${alias}-${idx}`} className="studio-alias-tag">
                      {alias}
                      <button
                        type="button"
                        className="studio-alias-remove-btn"
                        aria-label={`移除 ${alias}`}
                        onClick={() => handleRemoveAlias(idx)}
                      >
                        <X aria-hidden="true" />
                      </button>
                    </span>
                  ))}
                </div>

                <div className="studio-alias-add-row">
                  <input
                    type="text"
                    className="studio-alias-input"
                    placeholder="輸入新觸發指令（例如：更正電話號碼）"
                    value={newAliasInput}
                    onChange={(event) => {
                      setNewAliasInput(event.target.value);
                      setAliasEditError(null);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        handleAddAlias();
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="line-primary-btn studio-alias-add-btn"
                    onClick={handleAddAlias}
                  >
                    <Plus aria-hidden="true" /> 新增指令
                  </button>
                </div>

                {aliasEditError && (
                  <p className="studio-field-error" role="alert">
                    {aliasEditError}
                  </p>
                )}

                <div className="studio-alias-action-bar">
                  <button
                    type="button"
                    className="line-primary-btn"
                    disabled={aliasSaveBusy || editingAliases.length === 0}
                    onClick={handleSaveAliases}
                  >
                    <Save aria-hidden="true" /> {aliasSaveBusy ? '儲存中…' : '儲存變更'}
                  </button>
                  <button
                    type="button"
                    className="line-secondary-btn"
                    disabled={aliasSaveBusy}
                    onClick={() => {
                      setIsEditingAliases(false);
                      setAliasEditError(null);
                    }}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    className="line-secondary-btn studio-reset-btn"
                    disabled={aliasSaveBusy}
                    onClick={handleResetAliases}
                  >
                    <RotateCcw aria-hidden="true" /> 恢復預設
                  </button>
                </div>
              </div>
            )}

            <details className="studio-technical">
              <summary>連結與技術資訊</summary>
              <dl className="studio-facts">
                <dt>動作代碼</dt>
                <dd><code>{selectedRule.routeKey}</code></dd>
                <dt>分類</dt>
                <dd>{TIER_LABELS[selectedRule.tier] || selectedRule.tier} ({selectedRule.tier})</dd>
                <dt>版本與來源</dt>
                <dd>Rev {selectedRule.revision} · {selectedRule.sourceIdentity}</dd>
                <dt>目錄版本</dt>
                <dd>規則版本 {catalog?.revision}</dd>
                <dt>目標路徑</dt>
                <dd>{selectedRule.publicRoute || '未設定跳轉頁面'}</dd>
              </dl>
              {selectedRule.publicRoute && (
                <div className="ai-route-actions">
                  {getTrueLiffUrl(selectedRule.publicRoute) && (
                    <a href={getTrueLiffUrl(selectedRule.publicRoute)!} target="_blank" rel="noreferrer" className="ai-route-link is-liff">
                      <ExternalLink aria-hidden="true" />開啟真實 LIFF
                    </a>
                  )}
                  <a href={getLocalTestUrl(selectedRule.publicRoute)} target="_blank" rel="noreferrer" className="ai-route-link">
                    <Laptop aria-hidden="true" />本機預覽
                  </a>
                </div>
              )}
              {selectedRule.publicRoute && getTrueLiffUrl(selectedRule.publicRoute) && (
                <p className="ai-liff-url">正式 LIFF 連結：{getTrueLiffUrl(selectedRule.publicRoute)}</p>
              )}
              {!liffId && <p className="studio-description">尚未取得 LIFF ID，目前無法顯示正式服務連結。</p>}
            </details>
          </div>
        ) : (
          <div className="ai-editor-card">
            <p className="studio-empty">
              {catalogNotice ? '暫時無法查看引導動作。' : catalog ? '目前沒有可查看的引導動作。' : '正在讀取引導動作…'}
            </p>
          </div>
        )}

        <div className="ai-simulator-card">
          <section className="ai-router-simulator" aria-labelledby="ai-router-simulator-title">
            <div className="ai-router-simulator-heading">
              <div>
                <h3 id="ai-router-simulator-title">預覽引導動作</h3>
                <p>確認問句會如何引導；不儲存變更、不產生實際 AI 回覆。</p>
              </div>
            </div>
            <label htmlFor="server-router-input">測試問句</label>
            <div className="ai-router-input-row">
              <input
                id="server-router-input"
                aria-label="客服測試問句"
                value={routerInput}
                disabled={routerBusy}
                onChange={(event) => setRouterInput(event.target.value)}
              />
              <button
                type="button"
                className="line-primary-btn"
                disabled={routerBusy || !routerInput.trim()}
                onClick={() => void previewServerRouter()}
              >
                <Play aria-hidden="true" />{routerBusy ? '預覽中…' : '預覽引導動作'}
              </button>
            </div>
            {!routerNotice && !routerPreview && <p className="ai-router-empty">尚未預覽引導動作。</p>}
            {routerNotice && <div className={`ai-router-notice is-${routerNoticeKind ?? 'info'}`} role="status">{routerNotice}</div>}
            {routerPreview && (
              <div aria-label="問句處理預覽結果">
                {routerPreview.route_key && (
                  <p className="studio-description">
                    引導動作：{groupedRules.find((rule) => rule.routeKey === routerPreview.route_key)?.aliases[0] || '已命中系統引導動作'}
                  </p>
                )}
                <details className="studio-technical">
                  <summary>詳細結果</summary>
                  <div className="ai-router-result">
                    <div><span>問句分類</span><strong>{routerPreview.semantic_bucket}</strong></div>
                    <div><span>引導動作代碼</span><strong>{routerPreview.route_key ?? '未命中固定動作'}</strong></div>
                    <div><span>信心度</span><strong>{routerPreview.confidence}%</strong></div>
                    <div><span>結果類型</span><strong>{routerPreview.kind}</strong></div>
                  </div>
                </details>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
};

export default AiEventStudio;
