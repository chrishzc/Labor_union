/**
 * File: LiffCardStudio.tsx
 * Description: 繁體中文 - LIFF 8大安全表單與4大 Flex 訊息卡片視覺化預覽中心。
 */
import React, { useState } from 'react';
import '../LineManagementPage.css';

export type LiffAssetType = 'liff' | 'flex_card';

export interface LiffAssetItem {
  id: string;
  type: LiffAssetType;
  title: string;
  subtitle: string;
  badge: string;
  endpointUrl: string;
  authLevel: string;
  description: string;
  apiMapping: string;
}

const ASSET_ITEMS: LiffAssetItem[] = [
  {
    id: 'gateway',
    type: 'liff',
    title: '1. gateway.html',
    subtitle: '服務確認與身分先行導流',
    badge: '身分先行',
    endpointUrl: '/line/gateway',
    authLevel: 'LINE Login ID Token (RSA256) 驗章',
    description: '訪客點擊服務登記後開啟，身分先行核對姓名+手機，分流舊客秒綁或新客問卷。',
    apiMapping: 'api/routes/line_identity.py ➔ _verified_line_user_id',
  },
  {
    id: 'register',
    type: 'liff',
    title: '2. register.html',
    subtitle: '產婦 60 題登記問卷 (BeClass 對齊)',
    badge: '91項全必填',
    endpointUrl: '/line/register',
    authLevel: '15分鐘一次性 Token (Single-Use)',
    description: '100% 對齊 BeClass 91 項欄位與 15 項廚具設備，3 大退費法規條款強制彈窗。',
    apiMapping: 'api/routes/line_identity.py ➔ /client/register',
  },
  {
    id: 'bind',
    type: 'liff',
    title: '3. bind.html',
    subtitle: '舊客快速綁定與防冒領驗證',
    badge: '防冒領保護',
    endpointUrl: '/line/bind',
    authLevel: 'LINE Login ID Token',
    description: '輸入姓名+手機秒綁既有正式訂單；若已被其他帳號占用則彈窗轉專員審核。',
    apiMapping: 'api/routes/line_identity.py ➔ /client/bind',
  },
  {
    id: 'profile_update',
    type: 'liff',
    title: '4. profile_update.html',
    subtitle: '客戶資料異動申請 (5大折疊)',
    badge: '狀態鎖定矩陣',
    endpointUrl: '/line/profile-update',
    authLevel: 'LINE Login ID Token ＋ 案件權限鎖',
    description: '預產期/地址/天數異動申請，敏感欄位彈窗確認，服務中鎖地址、結案退款前可改帳號。',
    apiMapping: 'api/routes/line_identity.py ➔ /client/profile-update',
  },
  {
    id: 'staff_order_search',
    type: 'liff',
    title: '5. staff_order_search.html',
    subtitle: '月嫂安全查單 (18px 大字版)',
    badge: '個資防洩漏',
    endpointUrl: '/line/staff-order-search',
    authLevel: 'RBAC 月嫂身分驗章 (staff_id 鎖定)',
    description: '受保護查閱 -1 與 -2 表單，零對話個資殘留；曾徵詢案件可重新表達接案意願。',
    apiMapping: 'api/routes/line_staff_self_service.py ➔ /orders',
  },
  {
    id: 'staff_schedule',
    type: 'liff',
    title: '6. staff_schedule.html',
    subtitle: '月曆排班與長假/調休順延',
    badge: '雙軌請假',
    endpointUrl: '/line/staff-schedule',
    authLevel: 'RBAC 月嫂身分驗章',
    description: '標準月曆網格點擊顯示姓名時段；長假區間選擇器 ＋ 服務日調休推播產婦順延。',
    apiMapping: 'api/routes/staff_leave_intake.py ➔ /leave/intake',
  },
  {
    id: 'identity',
    type: 'liff',
    title: '7. identity.html',
    subtitle: '通用身分認證 (動態切換)',
    badge: '特權密語觸發',
    endpointUrl: '/line/identity',
    authLevel: '15分鐘一次性 Token ＋ 5次防爆破',
    description: '月嫂身分自動即時綁定；工會專員 1對1 私訊密語觸發後台帳密綁定。',
    apiMapping: 'api/routes/line_identity.py ➔ /staff/apply & /admin/apply',
  },
  {
    id: 'mobile_admin',
    type: 'liff',
    title: '8. mobile_admin.html',
    subtitle: '工會手機審核中心 (三大待審)',
    badge: '一鍵秒批核',
    endpointUrl: '/line-mobile-admin',
    authLevel: 'RBAC 管理員權限驗章 (admin_users)',
    description: '專員外出手機工作台：一鍵核准/退回客戶資料異動 Diff、舊客重綁防冒領、月嫂重綁。',
    apiMapping: 'api/routes/line_mobile_admin.py ➔ /identity-reviews',
  },
  {
    id: 'flex_dispatch',
    type: 'flex_card',
    title: '派案通知卡 (去敏化安全入口)',
    subtitle: 'LINE 聊天室推播卡片',
    badge: '零對話個資',
    endpointUrl: 'Flex Message JSON Template',
    authLevel: 'LineOutbox Worker 推播',
    description: '僅發送案件編號與去敏化時段，附帶【🔒 開啟安全 LIFF 查閱訂單明細】直達按鈕。',
    apiMapping: 'domains/line/delivery.py ➔ LineDeliveryRequest',
  },
  {
    id: 'flex_leave_confirm',
    type: 'flex_card',
    title: '調休順延確認卡 (含雙按鈕)',
    subtitle: 'LINE 聊天室推播卡片',
    badge: 'Postback 確定性',
    endpointUrl: 'Flex Message JSON Template',
    authLevel: 'LineOutbox Worker ＋ Postback Token',
    description: '月嫂請假時推播給產婦，附帶 [🟢 我同意順延一日] 與 [🔴 不同意順延] 雙向按鈕。',
    apiMapping: 'subsystems/line/matching_postback_application.py',
  },
  {
    id: 'flex_alert_critical',
    type: 'flex_card',
    title: '幹部重大異常通報卡 (紅色急件)',
    subtitle: '幹部通知群組專用卡片',
    badge: '秒級告警',
    endpointUrl: 'Flex Message JSON Template',
    authLevel: 'LineAlertGroup 監聽廣播',
    description: '客訴急件、調休順延被拒或連續綁定失敗時，秒級推播至工會幹部群組。',
    apiMapping: 'subsystems/line/order_group_application.py',
  },
  {
    id: 'flex_negotiation',
    type: 'flex_card',
    title: '降維撮合協商建議卡',
    subtitle: '媒合意願反查撮合卡',
    badge: '10分鐘復活',
    endpointUrl: 'Flex Message JSON Template',
    authLevel: 'Matching Pool Negotiation',
    description: '全數拒接時彙整月嫂拒接原因，向產婦提出微調時段（如 09:00 上工）之成案建議。',
    apiMapping: 'subsystems/scheduling/matching_communication.py',
  },
];

export const LiffCardStudio: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string>('gateway');
  const [filterType, setFilterType] = useState<'all' | 'liff' | 'flex_card'>('all');
  const [copied, setCopied] = useState<boolean>(false);

  const selectedItem = ASSET_ITEMS.find((item) => item.id === selectedId) || ASSET_ITEMS[0];

  const filteredItems = ASSET_ITEMS.filter(
    (item) => filterType === 'all' || item.type === filterType
  );

  const handleCopyLink = () => {
    const fullUrl = `https://labor-union.org.tw${selectedItem.endpointUrl}?test_token=demo-token-${Date.now()}`;
    navigator.clipboard.writeText(fullUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="liff-studio-container">
      {/* 左側資產目錄 */}
      <div className="liff-studio-sidebar">
        <div className="liff-sidebar-header">
          <h3>🪟 LINE 視覺化資產目錄</h3>
          <div className="liff-filter-pills">
            <button
              className={filterType === 'all' ? 'active' : ''}
              onClick={() => setFilterType('all')}
            >
              全部 ({ASSET_ITEMS.length})
            </button>
            <button
              className={filterType === 'liff' ? 'active' : ''}
              onClick={() => setFilterType('liff')}
            >
              LIFF 表單 (8)
            </button>
            <button
              className={filterType === 'flex_card' ? 'active' : ''}
              onClick={() => setFilterType('flex_card')}
            >
              Flex 卡片 (4)
            </button>
          </div>
        </div>

        <div className="liff-asset-list">
          {filteredItems.map((item) => (
            <div
              key={item.id}
              className={`liff-asset-card ${item.id === selectedId ? 'active' : ''}`}
              onClick={() => setSelectedId(item.id)}
            >
              <div className="liff-card-header">
                <strong>{item.title}</strong>
                <span className="liff-tag">{item.badge}</span>
              </div>
              <p>{item.subtitle}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 中間高擬真手機模擬器 */}
      <div className="liff-simulator-workbench">
        <div className="liff-phone-frame">
          <div className="liff-phone-notch">
            <span className="notch-speaker" />
            <span className="notch-camera" />
          </div>
          <div className="liff-phone-statusbar">
            <span>09:41</span>
            <span>📶 5G 🔋 100%</span>
          </div>

          <div className="liff-phone-screen">
            {selectedItem.type === 'liff' ? (
              <div className="mock-liff-content">
                <div className="mock-liff-nav">
                  <span>🌸 新竹市到宅月子工會</span>
                </div>
                <div className="mock-liff-body">
                  <div className="mock-liff-badge">🔒 四層銀行級密碼學驗章保護</div>
                  <h4>{selectedItem.subtitle}</h4>
                  <p className="mock-liff-desc">{selectedItem.description}</p>

                  {selectedItem.id === 'gateway' && (
                    <div className="mock-form-inputs">
                      <label>產婦/申請人姓名</label>
                      <input type="text" placeholder="例：王小美" defaultValue="王小美" readOnly />
                      <label>手機號碼 (09xx-xxx-xxx)</label>
                      <input type="text" placeholder="0912-345-678" defaultValue="0912-345-678" readOnly />
                      <button className="mock-primary-btn">🟢 查詢既有登記 / 身分先行</button>
                    </div>
                  )}

                  {selectedItem.id === 'register' && (
                    <div className="mock-form-inputs">
                      <div className="mock-step-indicator">步驟 1/3：產婦與寶寶需求 (91項欄位)</div>
                      <label>預產期 (EDD)</label>
                      <input type="date" defaultValue="2026-10-15" readOnly />
                      <label>預計服務天數</label>
                      <input type="text" defaultValue="30 天 (含自費與補助)" readOnly />
                      <div className="mock-checkbox-box">
                        <input type="checkbox" checked readOnly /> 我已詳閱並同意【退費原則與法規條款】
                      </div>
                      <button className="mock-primary-btn">下一步：廚具與飲食偏好 ➔</button>
                    </div>
                  )}

                  {selectedItem.id === 'staff_order_search' && (
                    <div className="mock-caregiver-view">
                      <div className="mock-order-card">
                        <div className="mock-card-tag">案件編號：115000035</div>
                        <h3 style={{ fontSize: '1.25rem', margin: '6px 0', color: '#a43c12' }}>王小美 媽媽</h3>
                        <p>📍 服務地址：新竹市東區光復路一段1號</p>
                        <p>📅 服務時段：09:00 ～ 17:00 (每日8小時)</p>
                        <p>🍲 特殊備註：不吃海鮮、需熱炒月子餐、家有電鍋</p>
                      </div>
                      <button className="mock-primary-btn" style={{ fontSize: '1rem', padding: '12px' }}>
                        👓 查閱【訂單資訊 -2】照護細節
                      </button>
                    </div>
                  )}

                  {selectedItem.id === 'mobile_admin' && (
                    <div className="mock-admin-view">
                      <div className="mock-tab-pill">審核類別：客戶資料異動 (1)</div>
                      <div className="mock-review-card">
                        <strong>王小美 (115000035)</strong>
                        <p className="diff-text">預產期：10/15 ➔ <span style={{ color: '#166534', fontWeight: 'bold' }}>10/25 (順延10天)</span></p>
                        <p className="diff-text">地址：光復路一段 ➔ <span style={{ color: '#166534', fontWeight: 'bold' }}>北大路88號</span></p>
                        <div className="mock-btn-group">
                          <button className="mock-approve-btn">🟢 一鍵核准</button>
                          <button className="mock-reject-btn">🔴 退回</button>
                        </div>
                      </div>
                    </div>
                  )}

                  {!['gateway', 'register', 'staff_order_search', 'mobile_admin'].includes(selectedItem.id) && (
                    <div className="mock-generic-box">
                      <div className="mock-placeholder-box">
                        <span>📱 {selectedItem.title}</span>
                        <small>{selectedItem.authLevel}</small>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="mock-flex-content">
                <div className="mock-flex-bubble">
                  {selectedItem.id === 'flex_dispatch' && (
                    <div className="flex-card-inner">
                      <div className="flex-header">🌸 新竹市月子工會 ｜ 派案通知</div>
                      <div className="flex-body">
                        <strong>案件編號：【 115000035 】</strong>
                        <p>服務期間：2026/10/15 ~ 11/13 (30天)</p>
                        <p>服務時段：09:00 ~ 17:00</p>
                        <p>區域：新竹市東區 (詳細地址受保護)</p>
                      </div>
                      <button className="flex-action-btn">🔒 點此安全查閱訂單明細 (-1/-2)</button>
                    </div>
                  )}

                  {selectedItem.id === 'flex_leave_confirm' && (
                    <div className="flex-card-inner">
                      <div className="flex-header">🌸 服務調休與順延確認通知</div>
                      <div className="flex-body">
                        <p>月嫂【陳美英】申請 10/20 請假一日。</p>
                        <p>總天數不變，服務結束日將順延一日 (11/13 ➔ 11/14)。請問您是否同意順延？</p>
                      </div>
                      <div className="flex-btn-row">
                        <button className="flex-btn-agree">🟢 我同意順延一日</button>
                        <button className="flex-btn-disagree">🔴 不同意順延</button>
                      </div>
                    </div>
                  )}

                  {selectedItem.id === 'flex_alert_critical' && (
                    <div className="flex-card-inner alert-style">
                      <div className="flex-header alert-header">🚨【工會急件告警 ｜ 客訴爭議】</div>
                      <div className="flex-body">
                        <strong>客戶：王小姐 (0912-345-678)</strong>
                        <p>案件：115000035 ｜ 級別：HIGH</p>
                        <p>摘要：用戶反映月嫂遲到一小時，要求換人協處。</p>
                      </div>
                      <button className="flex-action-btn alert-btn">👉 開啟手機審核中心處理</button>
                    </div>
                  )}

                  {selectedItem.id === 'flex_negotiation' && (
                    <div className="flex-card-inner">
                      <div className="flex-header">💡 媒合進度與服務條件調整建議</div>
                      <div className="flex-body">
                        <p>多位月嫂反映【07:30 上工】過早無法配合。</p>
                        <p>若微調為【09:00 ~ 17:00】，已有優質月嫂可立即為您定案！</p>
                      </div>
                      <button className="flex-action-btn">🟢 我同意調整為 09:00 上工</button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 右側規格審查與實機掃碼區 */}
      <div className="liff-studio-inspector">
        <div className="liff-inspector-card">
          <h4>🔒 資安規格與存取權限</h4>
          <div className="spec-item">
            <span>端點路徑：</span>
            <code>{selectedItem.endpointUrl}</code>
          </div>
          <div className="spec-item">
            <span>身分驗證層級：</span>
            <strong>{selectedItem.authLevel}</strong>
          </div>
          <div className="spec-item">
            <span>資安邊界：</span>
            <small>外部瀏覽器開啟自動攔截 ｜ 零對話個資殘留</small>
          </div>
        </div>

        <div className="liff-inspector-card">
          <h4>📲 手機實機掃碼測試</h4>
          <div className="qr-preview-box">
            <div className="mock-qr-code">
              <span>[ QR Code ]</span>
            </div>
            <p>使用 LINE 掃碼，將自動帶入 15 分鐘開發者安全測試 Token。</p>
          </div>
          <button className="line-tab-btn active" style={{ width: '100%' }} onClick={handleCopyLink}>
            {copied ? '✅ 已複製測試連結！' : '📋 複製 15 分鐘安全測試連結'}
          </button>
        </div>

        <div className="liff-inspector-card">
          <h4>🔗 關聯後端代碼與狀態機</h4>
          <div className="code-mapping-box">
            <code>{selectedItem.apiMapping}</code>
          </div>
        </div>
      </div>
    </div>
  );
};
