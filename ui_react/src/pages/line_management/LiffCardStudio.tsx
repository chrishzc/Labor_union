/**
 * File: LiffCardStudio.tsx
 * Description: 保留 8 個 LIFF 與 4 個 Flex 原始設計資產，並標示 canonical route、typed API 與尚缺契約。
 */
import React, { useEffect, useState } from 'react';
import {
  lineIdentityRuntimeConfigClient,
  type LineIdentityRuntimeConfigClient,
} from '../../api/line_identity/line_identity_runtime_config_client';
import {
  LINE_FLEX_DESIGN_SOURCES,
  type LineFlexDesignSource,
} from '../../adapters/line_flex_design/line_flex_design_adapter';
import { LineFlexDesignPreview } from '../../components/LineFlexDesignPreview';
import '../LineManagementPage.css';

export type LiffAssetType = 'liff' | 'flex_card';

export interface LiffAssetItem {
  id: string;
  type: LiffAssetType;
  title: string;
  subtitle: string;
  badge: string;
  endpointUrl: string;
  launchPath?: string;
  authLevel: string;
  description: string;
  apiMapping: string;
  flexDesignSource?: LineFlexDesignSource;
}

const ASSET_ITEMS: LiffAssetItem[] = [
  {
    id: 'gateway',
    type: 'liff',
    title: '1. gateway.html',
    subtitle: '服務確認與身分先行導流',
    badge: '伺服器已驗證',
    endpointUrl: '/line-gateway',
    launchPath: '/line-gateway',
    authLevel: '後端驗證 LINE 登入憑證；網址列 userId 僅供導航，不具授權效果',
    description: '正式入口先詢問是否已登記市府平台：已申請者繼續填寫工會「需求調查表單」，未申請者引導至新竹市到宅坐月子媒合服務平台。',
    apiMapping: '身分開啟、候選綁定檢查與確認流程已接通',
  },
  {
    id: 'register',
    type: 'liff',
    title: '2. register.html',
    subtitle: '產婦需求調查表單',
    badge: '檢查後送出',
    endpointUrl: '/line-registration',
    launchPath: '/line-registration',
    authLevel: '後端驗證 LINE 登入憑證；不接受網址列身分',
    description: '登記資料先顯示去敏摘要，明確確認後才送出；完整建立服務需求調查。',
    apiMapping: '登記資料檢查、確認送出與結果回讀已接通',
  },
  {
    id: 'bind',
    type: 'liff',
    title: '3. bind.html',
    subtitle: '既有客戶綁定入口（正式身分分流）',
    badge: '檢查後送出',
    endpointUrl: '/line-bind',
    launchPath: '/line-bind',
    authLevel: '後端驗證 LINE 登入憑證；候選匹配後仍需明確確認',
    description: '正式入口先顯示登記選擇；選擇已登記後才進入候選資料檢查與明確確認，不以姓名、電話或網址列 userId 授權。',
    apiMapping: '候選綁定、資料檢查與確認送出已接通',
  },
  {
    id: 'profile_update',
    type: 'liff',
    title: '4. profile_update.html',
    subtitle: '客戶資料與服務異動申請',
    badge: '正式介面待補',
    endpointUrl: '/line-profile-update（規劃入口）',
    authLevel: '必須驗證 LINE 登入憑證、正式綁定、案件權限與狀態鎖',
    description: '保留原本預產期、地址、天數與服務需求異動設計；正式異動流程尚未接上，不得假存。',
    apiMapping: '待補：客戶資料異動的查詢、預覽、確認與結果回讀',
  },
  {
    id: 'staff_order_search',
    type: 'liff',
    title: '5. staff_order_search.html',
    subtitle: '月嫂安全查單',
    badge: '正式指派資料',
    endpointUrl: '/line-staff-orders',
    launchPath: '/line-staff-orders',
    authLevel: '後端驗證 LINE 登入憑證與正式月嫂綁定',
    description: '只呈現正式月嫂自助服務回傳的案件欄位、狀態與鎖定原因；本設計頁不載入或合成案件資料。',
    apiMapping: '月嫂安全查單與案件狀態流程已接通',
  },
  {
    id: 'staff_schedule',
    type: 'liff',
    title: '6. staff_schedule.html',
    subtitle: '月嫂月曆與不可服務期間',
    badge: '正式排班月曆',
    endpointUrl: '/line-staff-schedule',
    launchPath: '/line-staff-schedule',
    authLevel: '後端驗證 LINE 登入憑證與正式月嫂綁定',
    description: '只呈現正式月曆、待定金檔期鎖與不可服務期間；正式指派中的休息日僅稱休息日。',
    apiMapping: '月嫂排班月曆與檔期鎖定顯示已接通',
  },
  {
    id: 'identity',
    type: 'liff',
    title: '7. identity.html',
    subtitle: '通用身分認證與服務入口',
    badge: '伺服器已驗證',
    endpointUrl: '/line-identity',
    launchPath: '/line-identity',
    authLevel: '後端驗證 LINE 登入憑證；網址列 userId 僅供導航，不具授權效果',
    description: '依已驗證的 LINE 使用者開啟客戶、月嫂或管理員流程；驗證失敗時不顯示資料，並要求重新登入。',
    apiMapping: '身分開啟、綁定檢查與確認流程已接通',
  },
  {
    id: 'mobile_admin',
    type: 'liff',
    title: '8. mobile_admin.html',
    subtitle: '手機身分審核中心',
    badge: '檢查後送出',
    endpointUrl: '/line-mobile-admin',
    launchPath: '/line-mobile-admin',
    authLevel: '後端驗證 LINE 登入憑證與正式管理員綁定',
    description: '審核決策先顯示變更前後內容與影響，確認後送出並回讀結果。',
    apiMapping: '身分審核影響檢查、確認與結果回讀已接通',
  },
  {
    id: 'flex_dispatch',
    type: 'flex_card',
    title: '派案通知卡設計稿',
    subtitle: '去敏案件入口版面',
    badge: '設計稿',
    endpointUrl: '未發布',
    authLevel: '僅為設計稿，尚未接通正式發送檢查',
    description: '僅保留去敏視覺結構；不代表已建立發送工作或已送達。',
    apiMapping: '正式卡片素材清單與發送流程尚未接通',
    flexDesignSource: LINE_FLEX_DESIGN_SOURCES.flex_dispatch,
  },
  {
    id: 'flex_leave_confirm',
    type: 'flex_card',
    title: '服務日順延確認卡設計稿',
    subtitle: '雙選項版面',
    badge: '設計稿',
    endpointUrl: '未發布',
    authLevel: '僅為設計稿，尚未接通正式發送檢查',
    description: '僅呈現選項的視覺位置；不建立順延命令、不送出 postback。',
    apiMapping: '正式卡片素材清單與發送流程尚未接通',
    flexDesignSource: LINE_FLEX_DESIGN_SOURCES.flex_leave_confirm,
  },
  {
    id: 'flex_alert_critical',
    type: 'flex_card',
    title: '重大異常通報卡設計稿',
    subtitle: '幹部通知版面',
    badge: '設計稿',
    endpointUrl: '未發布',
    authLevel: '僅為設計稿，尚未接通正式發送檢查',
    description: '僅呈現去敏告警層級與處理入口位置；不代表群組已設定或訊息已送達。',
    apiMapping: '正式卡片素材清單與發送流程尚未接通',
    flexDesignSource: LINE_FLEX_DESIGN_SOURCES.flex_alert_critical,
  },
  {
    id: 'flex_negotiation',
    type: 'flex_card',
    title: '媒合條件溝通卡設計稿',
    subtitle: '服務條件確認版面',
    badge: '設計稿',
    endpointUrl: '未發布',
    authLevel: '僅為設計稿，尚未接通正式發送檢查',
    description: '僅呈現條件摘要與確認區；不修改媒合狀態、不建立 LINE 發送任務。',
    apiMapping: '正式卡片素材清單與發送流程尚未接通',
    flexDesignSource: LINE_FLEX_DESIGN_SOURCES.flex_negotiation,
  },
];

function canonicalLiffUrl(path: string, origin: string): string {
  return new URL(path, origin).toString();
}

function LiffVisualPreview({ item }: { item: LiffAssetItem }) {
  if (item.id === 'gateway' || item.id === 'identity') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">服務確認與導流</div>
        <p>請確認您是否已於新竹市政府平台完成申請登記：</p>
        <button type="button" className="mock-primary-btn" disabled>📝 已申請市府平台</button>
        <small>我已在市府媒合服務平台完成登記，要繼續填寫工會【需求調查表單】。</small>
        <button type="button" className="mock-primary-btn" disabled>🏛️ 未申請市府平台</button>
        <small>我尚未於市府平台登記，請先前往新竹市政府到宅月子媒合服務平台提出申請。</small>
      </div>
    );
  }

  if (item.id === 'bind') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">服務綁定與訂單查詢</div>
        <p>請填寫基本資料，以完成 LINE 帳號與最新訂單的綁定：</p>
        <label>您的真實姓名</label>
        <input type="text" placeholder="請輸入姓名" readOnly />
        <label>您的聯絡電話</label>
        <input type="tel" placeholder="請輸入聯絡電話（例 0912345678）" readOnly />
        <button type="button" className="mock-primary-btn" disabled>確認綁定</button>
      </div>
    );
  }

  if (item.id === 'register') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">需求調查表單</div>
        <strong>👩 1. 基本資料</strong>
        <label>產婦姓名 *</label><input type="text" placeholder="請填寫真實姓名" readOnly />
        <label>行動電話 *</label><input type="text" placeholder="例如：0912345678" readOnly />
        <label>服務地址 *</label><input type="text" placeholder="請填寫完整地址（含巷弄樓層）" readOnly />
        <strong>🍼 2. 照護與環境</strong>
        <label>預產期（或已生產日期） *</label><input type="date" readOnly />
        <label>預計服務天數 *</label><input type="number" readOnly />
        <strong>🍲 3. 飲食偏好</strong>
        <label><input type="radio" disabled /> 葷食</label>
        <label><input type="radio" disabled /> 素食</label>
        <strong>🍳 4. 居家設備與環境</strong>
        <label><input type="checkbox" disabled /> 大同電鍋</label>
        <label><input type="checkbox" disabled /> 奶瓶消毒鍋</label>
        <strong>💰 5. 費用與同意條款</strong>
        <label><input type="checkbox" disabled /> 已詳閱退費原則</label>
        <button type="button" className="mock-primary-btn" disabled>預覽登記資料</button>
      </div>
    );
  }

  if (item.id === 'profile_update') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">客戶資料與服務異動</div>
        <label>異動類型</label>
        <select disabled defaultValue="service_address">
          <option value="service_address">服務地址</option>
          <option value="expected_date">預產期／生產日</option>
          <option value="service_days">服務天數</option>
          <option value="service_preferences">服務需求</option>
        </select>
        <label>異動內容</label>
        <textarea rows={3} placeholder="正式資料會載入目前登錄內容" readOnly />
        <button type="button" className="mock-primary-btn" disabled>預覽異動差異</button>
        <small>功能與版面已保留；待正式查詢與異動流程接妥後啟用。</small>
      </div>
    );
  }

  if (item.id === 'staff_order_search') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">訂單查詢</div>
        <p>只會搜尋目前 LINE 身分已被正式指派的案件。</p>
        <label>案件編號或客戶姓名</label>
        <input type="text" placeholder="例如：115000035 或客戶姓名" readOnly />
        <button type="button" className="mock-primary-btn" disabled>查詢訂單資訊</button>
      </div>
    );
  }

  if (item.id === 'staff_schedule') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">排班資訊</div>
        <p>您可以查詢個人班表月曆。</p>
        <label>查詢月份</label><input type="month" readOnly />
        <button type="button" className="mock-primary-btn" disabled>查詢班表</button>
        <div className="mock-placeholder-box">
          <small>服務日 ｜ 指派休息日 ｜ 已鎖定／待成立</small>
          <small>正式不可服務 ｜ 歷史指派 ｜ 未排班</small>
        </div>
      </div>
    );
  }

  if (item.id === 'mobile_admin') {
    return (
      <div className="mock-admin-view">
        <div className="mock-step-indicator">工會手機管理</div>
        <p>登入後依已驗證的管理員身分載入待辦。</p>
        <div className="mock-btn-group">
          <button type="button" className="mock-primary-btn" disabled>客服中心</button>
          <button type="button" className="mock-primary-btn" disabled>月嫂驗證</button>
        </div>
        <div className="mock-placeholder-box">尚未載入資料，不以樣本工單補空。</div>
      </div>
    );
  }

  return (
    <div className="mock-admin-view">
      <div className="mock-placeholder-box">此資產的高擬真預覽待完成。</div>
    </div>
  );
}

export interface LiffCardStudioProps {
  runtimeConfigClient?: LineIdentityRuntimeConfigClient;
}

type RuntimeConfigState =
  | { status: 'loading' }
  | { status: 'ready'; origin: string }
  | { status: 'failed'; message: string };

export const LiffCardStudio: React.FC<LiffCardStudioProps> = ({
  runtimeConfigClient = lineIdentityRuntimeConfigClient,
}) => {
  const [selectedId, setSelectedId] = useState<string>('gateway');
  const [filterType, setFilterType] = useState<'all' | 'liff' | 'flex_card'>('all');
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  const [previewRevision, setPreviewRevision] = useState<number>(1);
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfigState>({ status: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    setRuntimeConfig({ status: 'loading' });
    void runtimeConfigClient.get({ signal: controller.signal })
      .then((result) => {
        setRuntimeConfig({
          status: 'ready',
          origin: result.public_base_url ?? window.location.origin,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setRuntimeConfig({
          status: 'failed',
          message: error instanceof Error ? error.message : '無法載入 LIFF 公開網址。',
        });
      });
    return () => controller.abort();
  }, [runtimeConfigClient]);

  const selectedItem = ASSET_ITEMS.find((item) => item.id === selectedId) || ASSET_ITEMS[0];
  const filteredItems = ASSET_ITEMS.filter((item) => filterType === 'all' || item.type === filterType);
  const liffCount = ASSET_ITEMS.filter((item) => item.type === 'liff').length;
  const flexCount = ASSET_ITEMS.filter((item) => item.type === 'flex_card').length;

  const handleCopyLink = async () => {
    if (!selectedItem.launchPath || runtimeConfig.status !== 'ready') return;
    try {
      await navigator.clipboard.writeText(canonicalLiffUrl(selectedItem.launchPath, runtimeConfig.origin));
      setCopyStatus('copied');
    } catch {
      setCopyStatus('failed');
    }
  };

  return (
    <div className="liff-studio-container">
      <div className="liff-studio-sidebar">
        <div className="liff-sidebar-header">
          <h3>🪟 LINE 視覺化資產目錄</h3>
          <div className="liff-filter-pills">
            <button className={filterType === 'all' ? 'active' : ''} onClick={() => setFilterType('all')}>全部 ({ASSET_ITEMS.length})</button>
            <button className={filterType === 'liff' ? 'active' : ''} onClick={() => setFilterType('liff')}>LIFF 表單 ({liffCount})</button>
            <button className={filterType === 'flex_card' ? 'active' : ''} onClick={() => setFilterType('flex_card')}>Flex 卡片 ({flexCount})</button>
          </div>
        </div>

        <div className="liff-asset-list">
          {filteredItems.map((item) => (
            <button
              type="button"
              key={item.id}
              className={`liff-asset-card ${item.id === selectedId ? 'active' : ''}`}
              onClick={() => {
                setSelectedId(item.id);
                setCopyStatus('idle');
                setPreviewRevision(1);
              }}
            >
              <div className="liff-card-header"><strong>{item.title}</strong><span className="liff-tag">{item.badge}</span></div>
              <p>{item.subtitle}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="liff-simulator-workbench">
        <div className="liff-phone-frame" key={`${selectedItem.id}:${previewRevision}`}>
          <div className="liff-phone-notch"><span className="notch-speaker" /><span className="notch-camera" /></div>
          <div className="liff-phone-statusbar"><span>09:41</span><span>📶 5G 🔋 100%</span></div>
          <div className="liff-phone-screen">
            {selectedItem.type === 'liff' ? (
              <div className="mock-liff-content">
                <div className="mock-liff-nav"><span>🌸 新竹市到宅月子工會</span></div>
                <div className="mock-liff-body">
                  <div className="mock-liff-badge">🔒 身分由伺服器驗證</div>
                  <h4>{selectedItem.subtitle}</h4>
                  <p className="mock-liff-desc">{selectedItem.description}</p>
                  <LiffVisualPreview item={selectedItem} />
                  {selectedItem.launchPath ? (
                    runtimeConfig.status === 'ready' ? (
                      <a
                        className="mock-primary-btn"
                        href={canonicalLiffUrl(selectedItem.launchPath, runtimeConfig.origin)}
                        target="_blank"
                        rel="noreferrer"
                        style={{ display: 'block', marginTop: '16px', textAlign: 'center' }}
                      >
                        開啟正式 LIFF 入口
                      </a>
                    ) : (
                      <div className="line-warning" role="status" style={{ marginTop: '16px' }}>
                        {runtimeConfig.status === 'loading'
                          ? '正在取得正式 LIFF 測試網址…'
                          : `正式 LIFF 測試網址無法使用：${runtimeConfig.message}`}
                      </div>
                    )
                  ) : (
                    <div className="line-warning" role="status" style={{ marginTop: '16px' }}>
                      入口與正式服務尚待建立；設計與功能需求保留，不導向不存在的頁面。
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <LineFlexDesignPreview source={selectedItem.flexDesignSource} />
            )}
          </div>
        </div>
      </div>

      <div className="liff-studio-inspector">
        <div className="liff-inspector-card">
          <h4>🔒 資安規格與存取權限</h4>
          <div className="spec-item"><span>端點路徑：</span><code>{selectedItem.endpointUrl}</code></div>
          <div className="spec-item"><span>身分驗證層級：</span><strong>{selectedItem.authLevel}</strong></div>
          <div className="spec-item"><span>資安邊界：</span><small>網址列 userId 僅導航、不授權 ｜ 不顯示原始憑證 ｜ 不把排入發送當成已送達</small></div>
        </div>

        <div className="liff-inspector-card">
          <h4>📲 實機驗收入口</h4>
          <div className="qr-preview-box">
            <div className="mock-qr-code">
              <span>{selectedItem.launchPath ? '[ 正式 LIFF 測試網址 ]' : '[ 尚待建立入口 ]'}</span>
            </div>
            <p>
              {selectedItem.launchPath
                ? runtimeConfig.status === 'ready'
                  ? canonicalLiffUrl(selectedItem.launchPath, runtimeConfig.origin)
                  : '正式 LIFF 測試網址尚未可用。'
                : '此功能仍需建立正式頁面與後端服務。'}
            </p>
            <small>
              本機預覽已更新；目前僅保留正式測試網址，
              不呼叫外部 QR 服務或繪製不可掃描的假碼。
            </small>
          </div>
          <button
            type="button"
            className="line-secondary-btn"
            style={{ width: '100%', marginBottom: '8px' }}
            onClick={() => {
              setPreviewRevision((current) => current + 1);
              setCopyStatus('idle');
            }}
          >
            🔄 重新整理預覽
          </button>
          <button
            type="button"
            className="line-tab-btn active"
            style={{ width: '100%' }}
            onClick={() => void handleCopyLink()}
            disabled={!selectedItem.launchPath || runtimeConfig.status !== 'ready'}
          >
            {copyStatus === 'copied'
              ? '✅ 已複製正式測試連結'
              : copyStatus === 'failed'
                ? '複製失敗，請直接使用上方網址'
                : '📋 複製正式測試連結'}
          </button>
        </div>

        <div className="liff-inspector-card">
          <h4>🔗 關聯功能與目前狀態</h4>
          <div className="code-mapping-box">{selectedItem.apiMapping}</div>
        </div>
      </div>
    </div>
  );
};
