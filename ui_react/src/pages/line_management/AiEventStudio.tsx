/**
 * File: AiEventStudio.tsx
 * Description: 保留 LINE 事件規則編輯與本機模擬設計，並將正式發布鎖在 typed Preview／Apply 契約之後。
 */
import React, { useState } from 'react';
import '../LineManagementPage.css';

export interface AiEventRule {
  id: string;
  name: string;
  category: string;
  tags: string[];
  replyTemplate: string;
  liffAction: string | null;
  escalatePriority: 'NONE' | 'NORMAL' | 'HIGH';
  satisfactionRate: number | null;
  feedbackCount: number | null;
  isActive: boolean;
}

const DEFAULT_CATEGORIES = ['補助與費用', '服務異動', '爭議客訴', '服務流程', '一般諮詢'];

const HUMAN_ASSISTANCE_MARKERS = [
  '人工',
  '真人',
  '客服',
  '聯絡工會',
  '找專員',
  '答錯',
  '不正確',
  '沒解決',
  '未解決',
];

const LIFF_ACTION_LABELS: Record<string, string> = {
  '/line-registration': '服務登記入口',
  '/line-identity': '身分確認入口',
  'profile_update.html': '客戶資料異動入口（正式流程待補）',
};

const getLiffActionLabel = (action: string): string => (
  LIFF_ACTION_LABELS[action] ?? '受保護服務入口'
);

const INITIAL_RULES: AiEventRule[] = [
  {
    id: 'evt_subsidy',
    name: '💰 新竹市月子補助計算與收費說明',
    category: '補助與費用',
    tags: ['補助怎麼算', '一天補助幾小時', '補助上限多少', '能折抵多少錢', '市民補助條件'],
    replyTemplate:
      '親愛的家長您好！新竹市到宅月子補助標準為：自 115 年 1 月 1 日起，每日最高補助 4 小時、每戶最高上限 40 小時。超出部分將依工會定型化契約以自費時薪計算。服務完成後由工會協助向市府核銷退款。',
    liffAction: null,
    escalatePriority: 'NONE',
    satisfactionRate: null,
    feedbackCount: null,
    isActive: true,
  },
  {
    id: 'evt_profile_update',
    name: '✏️ 客戶資料與服務異動申請 (改地址/預產期)',
    category: '服務異動',
    tags: ['我想改地址', '預產期提前了', '想加做天數', '修改登記資料', '搬家改時段'],
    replyTemplate:
      '已為您開啟資料異動安全通道！為確保月嫂檔期與地址保險正確，請點擊下方專屬表單進行修改申請：',
    liffAction: 'profile_update.html',
    escalatePriority: 'NORMAL',
    satisfactionRate: null,
    feedbackCount: null,
    isActive: true,
  },
  {
    id: 'evt_complaint',
    name: '⚠️ 服務態度與爭議客訴 (轉真人急件)',
    category: '爭議客訴',
    tags: ['月嫂遲到', '服務態度很差', '我想換人', '菜煮得很難吃', '月嫂抱小孩不熟練', '客訴'],
    replyTemplate:
      '親愛的家長您好：非常抱歉造成您的困擾！工會重視寶寶照護品質與您的感受。系統完成急件建案後會顯示可追蹤編號，再由督導依案件狀態與您聯繫協處。',
    liffAction: null,
    escalatePriority: 'HIGH',
    satisfactionRate: null,
    feedbackCount: null,
    isActive: true,
  },
  {
    id: 'evt_leave_info',
    name: '🌸 月嫂調休與順延機制說明',
    category: '服務流程',
    tags: ['月嫂請假怎麼辦', '順延是什麼意思', '可以換代班嗎', '服務會少一天嗎'],
    replyTemplate:
      '月嫂若因事請假，須由正式請假流程建立並送出順延確認。產婦確認同意後才會依契約推進順延；不同意時由工會人工評估代班或其他處理方式。',
    liffAction: null,
    escalatePriority: 'NONE',
    satisfactionRate: null,
    feedbackCount: null,
    isActive: true,
  },
];

export const AiEventStudio: React.FC = () => {
  const [rules, setRules] = useState<AiEventRule[]>(INITIAL_RULES);
  const [selectedRuleId, setSelectedRuleId] = useState<string>('evt_subsidy');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [pendingDeleteRuleId, setPendingDeleteRuleId] = useState<string | null>(null);
  const [newTagInput, setNewTagInput] = useState<string>('');
  const [draftNotice, setDraftNotice] = useState<string | null>(null);
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null);
  const [automationHoldPreview, setAutomationHoldPreview] = useState<boolean>(false);
  const [simInput, setSimInput] = useState<string>('請問新竹市補助可以折抵幾小時？');
  const [simMessages, setSimMessages] = useState<
    Array<{ sender: 'user' | 'bot'; text: string; liff?: string | null; high?: boolean }>
  >([
    {
      sender: 'user',
      text: '請問新竹市補助可以折抵幾小時？',
    },
    {
      sender: 'bot',
      text: INITIAL_RULES[0].replyTemplate,
      liff: null,
      high: false,
    },
  ]);
  const currentRule = rules.find((r) => r.id === selectedRuleId) || rules[0];
  const categoryOptions = Array.from(new Set([
    ...DEFAULT_CATEGORIES,
    ...rules.map((rule) => rule.category),
  ]));
  const normalizedSearch = searchTerm.trim().toLocaleLowerCase('zh-TW');
  const filteredRules = rules.filter((rule) => {
    const matchesCategory = categoryFilter === 'ALL' || rule.category === categoryFilter;
    const matchesSearch = !normalizedSearch || [rule.name, rule.category, ...rule.tags]
      .some((value) => value.toLocaleLowerCase('zh-TW').includes(normalizedSearch));
    return matchesCategory && matchesSearch;
  });

  const handleAddTag = () => {
    const trimmed = newTagInput.trim();
    if (!trimmed || currentRule.tags.includes(trimmed)) return;
    setRules((existing) => existing.map((rule) => (
      rule.id === currentRule.id ? { ...rule, tags: [...rule.tags, trimmed] } : rule
    )));
    setNewTagInput('');
    setDraftNotice(null);
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setRules((existing) => existing.map((rule) => (
      rule.id === currentRule.id
        ? { ...rule, tags: rule.tags.filter((tag) => tag !== tagToRemove) }
        : rule
    )));
    setDraftNotice(null);
  };

  const handleUpdateCurrent = <K extends keyof AiEventRule>(field: K, value: AiEventRule[K]) => {
    setRules((existing) => existing.map((rule) => (
      rule.id === currentRule.id ? { ...rule, [field]: value } : rule
    )));
    setDraftNotice(null);
  };

  const handlePreviewDraft = () => {
    setDraftNotice(
      `已在本機預覽「${currentRule.name}」：${currentRule.tags.length} 個觸發問法；尚未寫入後端或發布至 LINE。`,
    );
  };

  const handleDeleteDraft = () => {
    if (rules.length === 1) {
      setDraftNotice('至少保留一筆本機草稿，避免編輯器失去可檢視項目；此操作沒有寫入後端。');
      return;
    }
    if (pendingDeleteRuleId !== currentRule.id) {
      setPendingDeleteRuleId(currentRule.id);
      setDraftNotice(`即將從瀏覽器記憶體移除「${currentRule.name}」；請再次確認。正式 catalog 尚未變更。`);
      return;
    }

    const remainingRules = rules.filter((rule) => rule.id !== currentRule.id);
    setRules(remainingRules);
    setSelectedRuleId(remainingRules[0].id);
    setPendingDeleteRuleId(null);
    setDraftNotice(`已從本機草稿移除「${currentRule.name}」；重新載入頁面即恢復，後端與 LINE 均未變更。`);
  };

  const handleFeedbackPreview = (choice: 'helpful' | 'unresolved') => {
    setFeedbackNotice(
      choice === 'helpful'
        ? '已在本機預覽「有幫助」回饋；正式回饋統計尚未接通，不會寫入數據。'
        : '已在本機預覽「未解決」回饋；正式客服待辦尚未接通，不會假造工單。',
    );
  };

  const handleRunSim = () => {
    if (!simInput.trim()) return;
    const userMsg = simInput.trim();
    const requestsHumanAssistance = HUMAN_ASSISTANCE_MARKERS.some((marker) => userMsg.includes(marker));

    // 僅在瀏覽器記憶體內比對目前畫面草稿，不呼叫後端或 LINE provider。
    const matched = automationHoldPreview || requestsHumanAssistance
      ? undefined
      : rules.find((r) =>
        r.isActive && r.tags.some((t) => userMsg.includes(t) || t.includes(userMsg))
      );
    const replyText = automationHoldPreview
      ? '目前模擬為自動回覆暫停；正式流程必須由人工處理，不會套用自動規則。'
      : requestsHumanAssistance
        ? '偵測到人工協助或回覆不正確需求；正式流程必須優先轉人工，不會套用自動規則。'
        : matched
          ? matched.replyTemplate
          : '目前草稿沒有符合的回覆規則；正式流程應轉入人工客服待辦，不得套用目前編輯中的規則。';

    setSimMessages([
      ...simMessages,
      { sender: 'user', text: userMsg },
      {
        sender: 'bot',
        text: replyText,
        liff: matched?.liffAction ?? null,
        high: automationHoldPreview || requestsHumanAssistance || matched?.escalatePriority === 'HIGH',
      },
    ]);
    setSimInput('');
  };

  return (
    <div className="ai-studio-container">
      {/* 左側：事件清單 */}
      <div className="ai-studio-sidebar">
        <div className="ai-sidebar-top">
          <h3>🤖 AI 客服事件規則庫</h3>
          <button
            type="button"
            className="mock-primary-btn"
            style={{ fontSize: '0.82rem', padding: '6px 12px' }}
            onClick={() => {
              const newId = `draft-event-${Date.now()}`;
              setRules((existing) => [...existing, {
                id: newId,
                name: '✨ 新增業務事件規則',
                category: '一般諮詢',
                tags: ['輸入常見問法1', '輸入常見問法2'],
                replyTemplate: '請在此輸入官方核定之標準回覆說明...',
                liffAction: null,
                escalatePriority: 'NONE',
                satisfactionRate: null,
                feedbackCount: null,
                isActive: true,
              }]);
              setSelectedRuleId(newId);
              setPendingDeleteRuleId(null);
              setDraftNotice(null);
            }}
          >
            ＋ 新增事件
          </button>
        </div>

        <div className="ai-editor-form" style={{ padding: '0 16px 12px' }}>
          <div className="form-group-row">
            <div className="form-field-half">
              <label htmlFor="ai-rule-category-filter">事件分類</label>
              <select
                id="ai-rule-category-filter"
                aria-label="事件分類篩選"
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
              >
                <option value="ALL">全部事件（{rules.length}）</option>
                {categoryOptions.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
            </div>
            <div className="form-field-half">
              <label htmlFor="ai-rule-search">搜尋規則</label>
              <input
                id="ai-rule-search"
                aria-label="搜尋事件名稱或標籤"
                type="search"
                placeholder="搜尋事件名稱或標籤"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
              />
            </div>
          </div>
          <small>目前顯示 {filteredRules.length}／{rules.length} 筆本機草稿；正式規則數量尚未接通。</small>
        </div>

        <div className="ai-rule-cards-list">
          {filteredRules.map((rule) => (
            <div
              key={rule.id}
              className={`ai-rule-item-card ${rule.id === selectedRuleId ? 'active' : ''}`}
              onClick={() => {
                setSelectedRuleId(rule.id);
                setPendingDeleteRuleId(null);
              }}
            >
              <div className="ai-card-title-row">
                <strong>{rule.name}</strong>
                <span className="category-badge">{rule.isActive ? '啟用' : '暫停'} · {rule.category}</span>
              </div>
              <div className="ai-card-tags-row">
                {rule.tags.slice(0, 3).map((t, idx) => (
                  <span key={idx} className="tag-chip-sm">
                    {t}
                  </span>
                ))}
                {rule.tags.length > 3 && <small>+{rule.tags.length - 3}</small>}
              </div>
              <div className="ai-card-metric-row">
                <span>
                  {rule.satisfactionRate === null || rule.feedbackCount === null
                    ? '回饋統計尚未接通'
                    : `👍 ${rule.satisfactionRate}% 有幫助 (${rule.feedbackCount}則)`}
                </span>
                {rule.escalatePriority === 'HIGH' && <span className="urgent-badge">🔴 急件通報</span>}
              </div>
            </div>
          ))}
          {filteredRules.length === 0 && (
            <div className="line-warning" role="status">
              沒有符合目前搜尋與分類的本機草稿；請調整條件。這不代表後端 catalog 為空。
            </div>
          )}
        </div>
      </div>

      {/* 右側：可視化編輯器 ＋ 實時模擬器 */}
      <div className="ai-studio-editor-pane">
        <div className="line-warning" role="status">
          規則編輯、標籤管理與本機模擬均可操作。正式儲存與發布尚未接通；在完成前，本頁不會假造成功、建立工單或實際發送 LINE 訊息。
        </div>
        {draftNotice && <div className="line-success" role="status">{draftNotice}</div>}
        <div className="ai-editor-card">
          <div className="ai-editor-header">
            <h4>🛠️ 規則編輯器：{currentRule.name}</h4>
            <div className="ai-editor-actions">
              <button type="button" className="line-secondary-btn" onClick={handlePreviewDraft}>
                預覽規則變更
              </button>
              <button type="button" className="line-secondary-btn" onClick={handleDeleteDraft}>
                {pendingDeleteRuleId === currentRule.id ? '確認移除本機草稿' : '🗑️ 刪除本機草稿'}
              </button>
              <button
                type="button"
                className="line-tab-btn active"
                disabled
                title="正式儲存與發布功能接通後啟用"
              >
                💾 儲存並發布
              </button>
            </div>
          </div>

          <div className="ai-editor-form">
            <div className="form-group-row">
              <div className="form-field-half">
                <label>事件名稱</label>
                <input
                  type="text"
                  value={currentRule.name}
                  onChange={(event) => handleUpdateCurrent('name', event.target.value)}
                />
              </div>
              <div className="form-field-half">
                <label>業務分類</label>
                <select
                  value={currentRule.category}
                  onChange={(event) => handleUpdateCurrent('category', event.target.value)}
                >
                  {categoryOptions.map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* 觸發語意錨點 Tags */}
            <div className="form-group-tags">
              <label>觸發語意錨點標籤 (Semantic Anchors / Tags)</label>
              <div className="tags-container">
                {currentRule.tags.map((t, idx) => (
                  <span key={idx} className="tag-chip-editable">
                    {t}
                    <button type="button" onClick={() => handleRemoveTag(t)}>✕</button>
                  </span>
                ))}
                <div className="add-tag-inline">
                  <input
                    type="text"
                    placeholder="＋ 輸入代表問法按 Enter"
                    value={newTagInput}
                    onChange={(event) => setNewTagInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        handleAddTag();
                      }
                    }}
                  />
                  <button type="button" onClick={handleAddTag}>新增</button>
                </div>
              </div>
              <p className="field-hint">
                💡 這些問法用於判斷應套用哪一則回覆；正式發布前必須由管理員預覽並確認。
              </p>
            </div>

            {/* 回覆文案 */}
            <div className="form-group">
              <label>官方核定標準回覆文案 (100% 零幻覺輸出)</label>
              <textarea
                rows={4}
                value={currentRule.replyTemplate}
                onChange={(event) => handleUpdateCurrent('replyTemplate', event.target.value)}
              />
            </div>

            {/* 附帶動作 */}
            <div className="form-group-actions">
              <label>觸發後的執行動作 (Actions)</label>
              <div className="action-checkbox-grid">
                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={currentRule.isActive}
                    onChange={(event) => handleUpdateCurrent('isActive', event.target.checked)}
                  />
                  本機草稿啟用；停用後不參與本頁測試比對
                </label>

                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={currentRule.liffAction !== null}
                    onChange={(event) => handleUpdateCurrent(
                      'liffAction',
                      event.target.checked ? '/line-registration' : null,
                    )}
                  />
                  附帶安全 LIFF 表單按鈕：
                  {currentRule.liffAction !== null && (
                    <select
                      value={currentRule.liffAction}
                      onChange={(event) => handleUpdateCurrent('liffAction', event.target.value)}
                    >
                      <option value="/line-registration">服務登記入口</option>
                      <option value="/line-identity">身分確認入口</option>
                      <option value="profile_update.html">客戶資料異動入口（正式流程待補）</option>
                    </select>
                  )}
                </label>

                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={currentRule.escalatePriority !== 'NONE'}
                    onChange={(event) => handleUpdateCurrent(
                      'escalatePriority',
                      event.target.checked ? 'NORMAL' : 'NONE',
                    )}
                  />
                  通報真人專員介入
                  {currentRule.escalatePriority !== 'NONE' && (
                    <select
                      aria-label="人工工單優先級"
                      value={currentRule.escalatePriority}
                      onChange={(event) => handleUpdateCurrent(
                        'escalatePriority',
                        event.target.value as AiEventRule['escalatePriority'],
                      )}
                    >
                      <option value="NORMAL">一般待辦</option>
                      <option value="HIGH">高優先急件</option>
                    </select>
                  )}
                  （僅預覽；正式工單由客服升級流程建立）
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* 本機草稿比對器 */}
        <div className="ai-simulator-card">
          <h4>💬 本機畫面比對（不發送）</h4>
          {feedbackNotice && <div className="line-warning" role="status">{feedbackNotice}</div>}
          <div className="sim-chat-window">
            {simMessages.map((msg, idx) => (
              <div key={idx} className={`sim-msg-row ${msg.sender}`}>
                {msg.sender === 'bot' && <div className="sim-bot-avatar">🤖</div>}
                <div className={`sim-bubble ${msg.sender}`}>
                  {msg.sender === 'bot' && (
                    <div className="sim-bot-header">
                      <span>🤖【新竹市月子工會 ｜ AI 智能小幫手】</span>
                    </div>
                  )}
                  <p>{msg.text}</p>
                  {msg.liff && (
                    <div className="sim-liff-btn">草稿動作：{getLiffActionLabel(msg.liff)}（本頁不開啟）</div>
                  )}
                  {msg.high && (
                    <div className="sim-alert-chip">🚨 草稿預期：需要人工升級並建立待寄送工作；本頁不會送出訊息。</div>
                  )}
                  {msg.sender === 'bot' && (
                    <div className="sim-feedback-row">
                      <small>回覆滿意度調查：本則回覆是否有解答問題？</small>
                      <button type="button" onClick={() => handleFeedbackPreview('helpful')}>👍 有幫助</button>
                      <button type="button" onClick={() => handleFeedbackPreview('unresolved')}>👎 未解決</button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          <label className="checkbox-item">
            <input
              type="checkbox"
              aria-label="模擬自動回覆暫停"
              checked={automationHoldPreview}
              onChange={(event) => setAutomationHoldPreview(event.target.checked)}
            />
            模擬自動回覆暫停（僅影響本頁測試）
          </label>

          <div className="sim-input-bar">
            <input
              type="text"
              placeholder="輸入民眾的測試問法 (例：補助最多幾天？我想改地址...)"
              value={simInput}
              onChange={(e) => setSimInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleRunSim();
                }
              }}
            />
            <button className="mock-primary-btn" onClick={handleRunSim}>
              🔎 預覽本機規則比對（不發送）
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
