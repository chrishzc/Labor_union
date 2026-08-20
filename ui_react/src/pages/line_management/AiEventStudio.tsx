/**
 * File: AiEventStudio.tsx
 * Description: 繁體中文 - AI 客服事件與意圖規則可視化管理工作台 (含語意標籤與實時模擬器)。
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
  satisfactionRate: number;
  feedbackCount: number;
  isActive: boolean;
}

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
    satisfactionRate: 96,
    feedbackCount: 142,
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
    satisfactionRate: 92,
    feedbackCount: 88,
    isActive: true,
  },
  {
    id: 'evt_complaint',
    name: '⚠️ 服務態度與爭議客訴 (轉真人急件)',
    category: '爭議客訴',
    tags: ['月嫂遲到', '服務態度很差', '我想換人', '菜煮得很難吃', '月嫂抱小孩不熟練', '客訴'],
    replyTemplate:
      '親愛的家長您好：非常抱歉造成您的困擾！工會極度重視寶寶照護品質與您的滿意度。已為您建立【專人客訴急件工單】，督導將於最快時間內以電話或私訊主動與您聯繫協處！',
    liffAction: null,
    escalatePriority: 'HIGH',
    satisfactionRate: 100,
    feedbackCount: 35,
    isActive: true,
  },
  {
    id: 'evt_leave_info',
    name: '🌸 月嫂調休與順延機制說明',
    category: '服務流程',
    tags: ['月嫂請假怎麼辦', '順延是什麼意思', '可以換代班嗎', '服務會少一天嗎'],
    replyTemplate:
      '月嫂若因事請假，系統會自動發送順延確認給產婦。若同意順延，總服務天數完全不變，結束日自動往後順延一日；若不同意順延，工會將評估指派代班月嫂！',
    liffAction: null,
    escalatePriority: 'NONE',
    satisfactionRate: 94,
    feedbackCount: 61,
    isActive: true,
  },
];

export const AiEventStudio: React.FC = () => {
  const [rules, setRules] = useState<AiEventRule[]>(INITIAL_RULES);
  const [selectedRuleId, setSelectedRuleId] = useState<string>('evt_subsidy');
  const [newTagInput, setNewTagInput] = useState<string>('');
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
  const [saveToast, setSaveToast] = useState<boolean>(false);

  const currentRule = rules.find((r) => r.id === selectedRuleId) || rules[0];

  const handleAddTag = () => {
    const trimmed = newTagInput.trim();
    if (!trimmed || currentRule.tags.includes(trimmed)) return;
    const updated = rules.map((r) =>
      r.id === currentRule.id ? { ...r, tags: [...r.tags, trimmed] } : r
    );
    setRules(updated);
    setNewTagInput('');
  };

  const handleRemoveTag = (tagToRemove: string) => {
    const updated = rules.map((r) =>
      r.id === currentRule.id
        ? { ...r, tags: r.tags.filter((t) => t !== tagToRemove) }
        : r
    );
    setRules(updated);
  };

  const handleUpdateCurrent = (field: keyof AiEventRule, val: any) => {
    const updated = rules.map((r) =>
      r.id === currentRule.id ? { ...r, [field]: val } : r
    );
    setRules(updated);
  };

  const handleSavePublish = () => {
    setSaveToast(true);
    setTimeout(() => setSaveToast(false), 2500);
  };

  const handleRunSim = () => {
    if (!simInput.trim()) return;
    const userMsg = simInput.trim();
    
    // 簡單的模擬比對
    let matched = rules.find((r) =>
      r.tags.some((t) => userMsg.includes(t) || t.includes(userMsg))
    );

    if (!matched) {
      matched = currentRule;
    }

    setSimMessages([
      ...simMessages,
      { sender: 'user', text: userMsg },
      {
        sender: 'bot',
        text: matched.replyTemplate,
        liff: matched.liffAction,
        high: matched.escalatePriority === 'HIGH',
      },
    ]);
    setSimInput('');
  };

  return (
    <div className="ai-studio-container">
      {saveToast && (
        <div className="line-success" style={{ position: 'fixed', top: '20px', right: '30px', zIndex: 9999 }}>
          ✅ 【{currentRule.name}】規則已成功儲存並同步至 AI 語意路由器！
        </div>
      )}

      {/* 左側：事件清單 */}
      <div className="ai-studio-sidebar">
        <div className="ai-sidebar-top">
          <h3>🤖 AI 客服事件規則庫</h3>
          <button
            className="mock-primary-btn"
            style={{ fontSize: '0.82rem', padding: '6px 12px' }}
            onClick={() => {
              const newId = `evt_${Date.now()}`;
              const newEvt: AiEventRule = {
                id: newId,
                name: '✨ 新增業務事件規則',
                category: '一般諮詢',
                tags: ['輸入常見問法1', '輸入常見問法2'],
                replyTemplate: '請在此輸入官方核定之標準回覆說明...',
                liffAction: null,
                escalatePriority: 'NONE',
                satisfactionRate: 100,
                feedbackCount: 0,
                isActive: true,
              };
              setRules([...rules, newEvt]);
              setSelectedRuleId(newId);
            }}
          >
            ＋ 新增事件
          </button>
        </div>

        <div className="ai-rule-cards-list">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className={`ai-rule-item-card ${rule.id === selectedRuleId ? 'active' : ''}`}
              onClick={() => setSelectedRuleId(rule.id)}
            >
              <div className="ai-card-title-row">
                <strong>{rule.name}</strong>
                <span className="category-badge">{rule.category}</span>
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
                <span>👍 {rule.satisfactionRate}% 有幫助 ({rule.feedbackCount}則)</span>
                {rule.escalatePriority === 'HIGH' && <span className="urgent-badge">🔴 急件通報</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 右側：可視化編輯器 ＋ 實時模擬器 */}
      <div className="ai-studio-editor-pane">
        <div className="ai-editor-card">
          <div className="ai-editor-header">
            <h4>🛠️ 規則編輯器：{currentRule.name}</h4>
            <div className="ai-editor-actions">
              <button className="line-tab-btn active" onClick={handleSavePublish}>
                💾 儲存並即時發布
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
                  onChange={(e) => handleUpdateCurrent('name', e.target.value)}
                />
              </div>
              <div className="form-field-half">
                <label>業務分類</label>
                <select
                  value={currentRule.category}
                  onChange={(e) => handleUpdateCurrent('category', e.target.value)}
                >
                  <option value="補助與費用">補助與費用</option>
                  <option value="服務異動">服務異動</option>
                  <option value="爭議客訴">爭議客訴</option>
                  <option value="服務流程">服務流程</option>
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
                    <button type="button" onClick={() => handleRemoveTag(t)}>
                      ✕
                    </button>
                  </span>
                ))}
                <div className="add-tag-inline">
                  <input
                    type="text"
                    placeholder="＋ 輸入代表問法按 Enter"
                    value={newTagInput}
                    onChange={(e) => setNewTagInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        handleAddTag();
                      }
                    }}
                  />
                  <button type="button" onClick={handleAddTag}>
                    新增
                  </button>
                </div>
              </div>
              <p className="field-hint">
                💡 專員提示：這是提供給 AI 學習的「語意例句」。AI 會自動理解同義詞、倒裝句與不同口氣，填寫 3~5 組即可精準覆蓋！
              </p>
            </div>

            {/* 回覆文案 */}
            <div className="form-group">
              <label>官方核定標準回覆文案 (100% 零幻覺輸出)</label>
              <textarea
                rows={4}
                value={currentRule.replyTemplate}
                onChange={(e) => handleUpdateCurrent('replyTemplate', e.target.value)}
              />
            </div>

            {/* 附帶動作 */}
            <div className="form-group-actions">
              <label>觸發後的執行動作 (Actions)</label>
              <div className="action-checkbox-grid">
                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={currentRule.liffAction !== null}
                    onChange={(e) =>
                      handleUpdateCurrent(
                        'liffAction',
                        e.target.checked ? 'profile_update.html' : null
                      )
                    }
                  />
                  附帶安全 LIFF 表單按鈕：
                  {currentRule.liffAction !== null && (
                    <select
                      value={currentRule.liffAction}
                      onChange={(e) => handleUpdateCurrent('liffAction', e.target.value)}
                    >
                      <option value="profile_update.html">profile_update.html (修改資料)</option>
                      <option value="gateway.html">gateway.html (服務登記)</option>
                      <option value="bind.html">bind.html (舊客綁定)</option>
                    </select>
                  )}
                </label>

                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={currentRule.escalatePriority === 'HIGH'}
                    onChange={(e) =>
                      handleUpdateCurrent(
                        'escalatePriority',
                        e.target.checked ? 'HIGH' : 'NONE'
                      )
                    }
                  />
                  建立 HIGH 急件客訴工單 ＋ 秒級推播至 LINE 幹部通知群組
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* 實時對話模擬器 */}
        <div className="ai-simulator-card">
          <h4>💬 即時對話模擬器 (Live Chat Simulator)</h4>
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
                    <button className="sim-liff-btn">👉 前往填寫：{msg.liff}</button>
                  )}
                  {msg.high && (
                    <div className="sim-alert-chip">🚨 已為您通報工會幹部群組，專員即刻接手！</div>
                  )}
                  {msg.sender === 'bot' && (
                    <div className="sim-feedback-row">
                      <small>本則由 AI 智能助手回覆，是否有解答問題？</small>
                      <button>👍 有幫助</button>
                      <button>👎 未解決</button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

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
              🧪 發送測試
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
