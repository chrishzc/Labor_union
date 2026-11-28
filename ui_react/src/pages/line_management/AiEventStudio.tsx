/**
 * File: AiEventStudio.tsx
 * Description: AI 客服引導動作工作室，提供分類篩選、觸發指令編輯維護與路由預覽。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  ExternalLink,
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
import {
  notificationMessageHref,
  ORDER_GROUP_BIND_REPLY_TEMPLATES,
  ORDER_GROUP_INVITE_REPLY_TEMPLATES,
} from '../../adapters/line_configuration/line_message_flow_adapter';
import {
  loadLineGuidanceCatalog,
  previewLineGuidance,
  type NavigationCatalog,
  type RouterPreview,
} from '../../api/line_configuration/line_guidance_client';
import '../LineManagementPage.css';

type TierCategory = 'all' | 'navigation' | 'identity' | 'admin';
type GuidanceTier = Exclude<TierCategory, 'all'>;

interface GuidanceAction {
  tier: GuidanceTier;
  chat: string;
  description: string;
  alternateEntry: string | null;
  editable?: boolean;
  previewable?: boolean;
  canonicalCommand?: string;
  fixedAliases?: string[];
  exampleSuffix?: string;
  replyTemplates?: readonly { id: string; label: string }[];
}

interface CatalogGroup extends GuidanceAction {
  routeKey: string;
  aliases: string[];
  catalogAliases: string[];
}

const TIER_LABELS: Record<string, string> = {
  navigation: '服務導覽',
  identity: '身分綁定',
  admin: '工會管理',
};

const GUIDANCE_ACTIONS: Record<string, GuidanceAction> = {
  admin_binding: {
    tier: 'identity', chat: '一對一聊天室', editable: true, previewable: true,
    description: '取得工會後台帳號綁定連結。連結有效時間為 15 分鐘。',
    alternateEntry: null,
    replyTemplates: [{ id: 'identity-admin-link', label: '工會帳號綁定連結' }],
  },
  service_help_menu: {
    tier: 'navigation', chat: '一對一聊天室', previewable: true,
    description: '開啟目前已發布的常見問答分類選單。',
    alternateEntry: '訪客與客戶的圖文選單「常見問題」會代送指令',
    canonicalCommand: '常見問題',
    replyTemplates: [{ id: 'service-menu', label: '常見問答選單' }],
  },
  service_progress: {
    tier: 'navigation', chat: '一對一聊天室', previewable: true,
    description: '查看已綁定案件的進度。尚未綁定的客戶可從訪客圖文選單的「預約與登記」進入。',
    alternateEntry: '常見問題的「查詢進度」按鈕會代送指令',
    canonicalCommand: '查詢服務進度',
    replyTemplates: [
      { id: 'service-progress', label: '案件進度' },
      { id: 'service-progress-unbound', label: '尚未綁定提示' },
    ],
  },
  order_group_bind: {
    tier: 'admin', chat: '案件群組', editable: true, fixedAliases: ['綁定群組', '綁定訂單'],
    description: '工會人員可輸入「綁定群組」或「綁定訂單」，依提示分次傳送案號與邀請網址。也可一次輸入「指令 案件編號 邀請網址」。',
    alternateEntry: null,
    replyTemplates: ORDER_GROUP_BIND_REPLY_TEMPLATES,
  },
  order_group_invite: {
    tier: 'admin', chat: '案件群組',
    description: '工會人員可為已綁定的案件重新排入客戶與月嫂的私人邀請卡。系統會在群組回覆排入結果。',
    alternateEntry: null,
    replyTemplates: ORDER_GROUP_INVITE_REPLY_TEMPLATES,
  },
  group_helper_menu: {
    tier: 'navigation', chat: '案件群組', editable: true,
    description: '本案客戶、月嫂或有權限的工會人員可開啟小幫手選單。選單依身分及案件進度顯示可用功能。',
    alternateEntry: null,
    replyTemplates: [{ id: 'helper-menu-card', label: '小幫手選單' }],
  },
  group_postponement: {
    tier: 'navigation', chat: '案件群組',
    description: '本案月嫂可在指令後帶入原服務日與補班日。',
    alternateEntry: '案件群組小幫手的「雙方合意延期」按鈕可開啟 LIFF',
    canonicalCommand: '雙方合意延期',
    exampleSuffix: '：2026-12-01 順延至 2026-12-10',
    replyTemplates: [
      { id: 'helper-postponement-card', label: '延期確認卡' },
      { id: 'helper-postponement-completed', label: '延期完成通知' },
    ],
  },
  group_payment_ack: {
    tier: 'navigation', chat: '案件群組', canonicalCommand: '已經匯款',
    description: '本案已驗證的客戶可在首期款提醒後回報匯款，入帳仍由工會核對。',
    alternateEntry: '客戶私聊的首期款逾期提醒卡有「已經匯款」按鈕',
    replyTemplates: [{ id: 'payment-reminder-ack', label: '已匯款受理回覆' }],
  },
  group_payment_assistance: {
    tier: 'navigation', chat: '案件群組', fixedAliases: ['有疑問需要解決'],
    description: '本案已驗證的客戶可在首期款提醒後查閱繳款疑問的處理方式。',
    alternateEntry: null,
  },
};

export const AiEventStudio: React.FC = () => {
  const [catalog, setCatalog] = useState<NavigationCatalog | null>(null);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTier, setSelectedTier] = useState<TierCategory>('all');
  const [manualOnly, setManualOnly] = useState(false);
  const [selectedRouteKey, setSelectedRouteKey] = useState<string | null>(null);
  const [routerInput, setRouterInput] = useState('');
  const [routerPreview, setRouterPreview] = useState<RouterPreview | null>(null);
  const [routerNotice, setRouterNotice] = useState<string | null>(null);
  const [routerNoticeKind, setRouterNoticeKind] = useState<'success' | 'info' | 'error' | null>(null);
  const [routerBusy, setRouterBusy] = useState(false);

  // Alias editing state
  const [isEditingAliases, setIsEditingAliases] = useState(false);
  const [editingAliases, setEditingAliases] = useState<string[]>([]);
  const [newAliasInput, setNewAliasInput] = useState('');
  const [aliasSaveBusy, setAliasSaveBusy] = useState(false);
  const [aliasEditError, setAliasEditError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadLineGuidanceCatalog()
      .then((nextCatalog) => {
        if (!active) return;
        setCatalog(nextCatalog);
        setCatalogNotice(null);
      })
      .catch(() => {
        if (active) setCatalogNotice('引導動作讀取失敗，請稍後重新整理。');
      });

    return () => { active = false; };
  }, []);

  const groupedRules = useMemo<CatalogGroup[]>(() => {
    if (!catalog) return [];
    const aliasesByRoute = new Map<string, string[]>();
    for (const entry of catalog.entries) {
      const aliases = aliasesByRoute.get(entry.route_key) ?? [];
      aliases.push(entry.alias);
      aliasesByRoute.set(entry.route_key, aliases);
    }
    return Object.entries(GUIDANCE_ACTIONS).flatMap(([routeKey, action]) => {
      const catalogAliases = aliasesByRoute.get(routeKey) ?? [];
      const aliases = action.canonicalCommand
        ? [action.canonicalCommand]
        : [...new Set([...catalogAliases, ...(action.fixedAliases ?? [])])];
      return aliases.length ? [{ ...action, routeKey, aliases, catalogAliases }] : [];
    });
  }, [catalog]);

  const filteredRules = useMemo(() => {
    const normalized = searchTerm.trim().toLocaleLowerCase('zh-TW');
    return groupedRules.filter((rule) => {
      if (selectedTier !== 'all' && rule.tier !== selectedTier) {
        return false;
      }
      if (manualOnly && rule.alternateEntry !== null) return false;
      if (!normalized) return true;
      return [
        rule.chat,
        TIER_LABELS[rule.tier],
        ...rule.aliases,
      ].some((value) => value.toLocaleLowerCase('zh-TW').includes(normalized));
    });
  }, [groupedRules, searchTerm, selectedTier, manualOnly]);

  const selectedRule = useMemo(() => {
    if (selectedRouteKey) {
      const selectableRules = manualOnly && !isEditingAliases ? filteredRules : groupedRules;
      const match = selectableRules.find((r) => r.routeKey === selectedRouteKey);
      if (match) return match;
    }
    return filteredRules[0] ?? (manualOnly ? null : groupedRules[0] ?? null);
  }, [groupedRules, filteredRules, selectedRouteKey, manualOnly, isEditingAliases]);

  const previewedRule = groupedRules.find((rule) => rule.previewable && rule.routeKey === routerPreview?.route_key);

  const selectRule = (routeKey: string) => {
    setSelectedRouteKey(routeKey);
    setIsEditingAliases(false);
    setAliasEditError(null);
    setNewAliasInput('');
  };

  const startEditing = () => {
    if (!selectedRule?.editable) return;
    setSelectedRouteKey(selectedRule.routeKey);
    setEditingAliases([...selectedRule.catalogAliases]);
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
        setAliasEditError('部分指令已用於其他引導動作。請修改或移除重複指令，再儲存變更。');
      } else {
        setAliasEditError('無法確認觸發指令是否已儲存。請先記下修改內容，再重新整理核對目前的指令。');
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
    } catch {
      setAliasEditError('無法確認指令是否已恢復預設。請重新整理，核對目前的觸發指令。');
    } finally {
      setAliasSaveBusy(false);
    }
  };

  const executePreview = async (testText: string) => {
    if (routerBusy || !testText.trim()) return;
    setRouterNotice(null);
    setRouterNoticeKind(null);
    setRouterPreview(null);
    setRouterBusy(true);
    try {
      const preview = await previewLineGuidance(testText);
      const matchedRule = groupedRules.find((rule) => (
        rule.previewable && rule.routeKey === preview.route_key
        && (!rule.canonicalCommand || rule.canonicalCommand === testText.trim())
      ));
      if (matchedRule) {
        setRouterPreview(preview);
        if (!manualOnly || matchedRule.alternateEntry === null) {
          if (!isEditingAliases) selectRule(matchedRule.routeKey);
          document.getElementById(`rule-card-${matchedRule.routeKey}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
        }
        setRouterNotice('已找到符合的引導動作。');
        setRouterNoticeKind('success');
      } else {
        setRouterNotice('沒有可在此確認的引導動作。請依指令清單查看適用聊天室和使用條件。');
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
          <h3><Bot aria-hidden="true" />聊天室觸發指令</h3>
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

        <label className="studio-trigger-filter">
          <input type="checkbox" checked={manualOnly} onChange={(event) => setManualOnly(event.target.checked)} />
          僅手動輸入
        </label>

        <div className="ai-editor-form ai-rule-search-form">
          <label htmlFor="server-ai-rule-search">搜尋引導動作</label>
          <input
            id="server-ai-rule-search"
            type="search"
            placeholder="搜尋動作、分類或指令"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
          <small>{catalog ? `目前顯示 ${filteredRules.length} / 共 ${groupedRules.length} 組引導動作` : '正在讀取引導動作…'}</small>
        </div>

        {catalogNotice && <div className="line-warning" role="status">{catalogNotice}</div>}

        <div className="ai-rule-cards-list">
          {filteredRules.map((rule) => {
            const isSelected = selectedRule?.routeKey === rule.routeKey;
            const isMatched = previewedRule?.routeKey === rule.routeKey;
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
                <span className="ai-card-metric-row">
                  {rule.chat} · {rule.aliases.length} 個指令{' '}
                  <span className="studio-trigger-source">· {rule.alternateEntry === null ? '僅手動輸入' : '有其他入口'}</span>
                </span>
              </button>
            );
          })}
          {catalog && filteredRules.length === 0 && <p className="studio-empty" role="status">沒有符合條件的引導動作。請調整搜尋或篩選條件。</p>}
        </div>
        <p className="studio-readonly-note"><ShieldCheck aria-hidden="true" />自訂觸發指令儲存後立即於 LINE 生效</p>
      </aside>

      <div className="ai-studio-editor-pane">
        {selectedRule ? (
          <div className="ai-editor-card ai-rule-detail-card">
            <div className="ai-editor-header">
              <div>
                <h2>{selectedRule.aliases[0] || selectedRule.routeKey}</h2>
                <p className="studio-description">{selectedRule.chat}。{selectedRule.description}</p>
                <p className="studio-description">
                  {selectedRule.alternateEntry === null ? '僅手動輸入' : `${selectedRule.alternateEntry}。`}
                </p>
                {selectedRule.exampleSuffix && (
                  <p className="studio-description">輸入範例「{selectedRule.aliases[0]}{selectedRule.exampleSuffix}」。</p>
                )}
              </div>
              {selectedRule.editable && <span className="studio-editable-badge">可自訂觸發指令</span>}
            </div>

            {!isEditingAliases ? (
              <div className="ai-alias-section">
                <div className="ai-alias-header">
                  <strong>觸發指令</strong>
                  <div className="studio-alias-header-actions">
                    {selectedRule.previewable && <small>點選帶入問句，再按「預覽引導動作」。</small>}
                    {selectedRule.editable && (
                      <button type="button" className="studio-edit-aliases-btn" onClick={startEditing}>
                        <Pencil aria-hidden="true" /> 編輯指令
                      </button>
                    )}
                  </div>
                </div>
                <div className="ai-alias-list">
                  {selectedRule.aliases.map((alias) => selectedRule.previewable ? (
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
                  ) : (
                    <span key={alias} className="studio-alias-tag">{alias}</span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="ai-alias-section studio-alias-edit-box">
                <div className="ai-alias-header">
                  <strong>編輯觸發指令（常見問法）</strong>
                  <small>點選指令旁的 ✕ 可移除，輸入文字可新增別名。儲存後立即於 LINE 生效。</small>
                  {selectedRule.fixedAliases && (
                    <small>分次操作固定使用「{selectedRule.fixedAliases.join('」或「')}」。</small>
                  )}
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

            {!isEditingAliases && !!selectedRule.replyTemplates?.length && (
              <section className="ai-alias-section" aria-labelledby="guidance-reply-copy">
                <h3 id="guidance-reply-copy">編輯 Reply 文案</h3>
                <ul>
                  {selectedRule.replyTemplates.map(({ id, label }) => (
                    <li key={id}>
                      <a href={notificationMessageHref(id)}>
                        {label}<ExternalLink aria-hidden="true" size={14} />
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            )}
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
                <p>預覽部分一對一指令的文字比對。群組、身分、案件狀態與實際回覆請依各指令的使用條件確認。</p>
              </div>
            </div>
            <label htmlFor="server-router-input">測試問句</label>
            <div className="ai-router-input-row">
              <input
                id="server-router-input"
                aria-label="客服測試問句"
                placeholder="例如「綁定後台帳號」"
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
            {!routerNotice && !routerPreview && <p className="ai-router-empty">輸入要測試的文字，即可預覽會觸發的引導動作。</p>}
            {routerNotice && <div className={`ai-router-notice is-${routerNoticeKind ?? 'info'}`} role="status">{routerNotice}</div>}
            {previewedRule && (
              <div aria-label="問句處理預覽結果">
                <p className="studio-description">{previewedRule.aliases[0]}</p>
                {manualOnly && previewedRule.alternateEntry !== null && (
                  <p className="studio-description">這個動作另有入口，未列在目前的手動指令清單。</p>
                )}
              </div>
            )}
          </section>
        </div>
        <section className="ai-editor-card" aria-labelledby="guidance-menu-entries">
          <h3 id="guidance-menu-entries">LINE 操作入口</h3>
          <ul>
            <li>訪客可從圖文選單的「預約與登記」辦理客戶綁定，或從「月嫂認證」辦理月嫂綁定。</li>
            <li>客戶可從圖文選單的「案件資訊」查閱服務條件與費用。</li>
            <li>訪客與客戶可從圖文選單的「常見問題」查閱服務流程、費用與補助。</li>
            <li>工會圖文選單有「待辦工作台」、「狀態追蹤」和「營運摘要」。</li>
            <li>案件群組的小幫手選單有「雙方合意延期」。群組邀請的操作說明可在「LINE 營運」的「案件群組」查看。</li>
          </ul>
          <p className="studio-description">客戶如需修改個人資料或訂單內容，請直接在官方帳號或原案件群組留言。</p>
        </section>
      </div>
    </div>
  );
};

export default AiEventStudio;
