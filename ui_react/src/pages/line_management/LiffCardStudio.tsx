/**
 * File: LiffCardStudio.tsx
 * Description: 呈現已接通的 LIFF 與 Flex 設計資產，並標示 canonical route 與 typed API。
 */
import React, { useEffect, useState } from 'react';
import { CheckSquare, Link2, PanelTop, Search, ShieldCheck } from 'lucide-react';
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
export type LiffAudienceRole = 'visitor' | 'customer' | 'staff' | 'union_staff';

export interface LiffAssetItem {
  id: string;
  type: LiffAssetType;
  title: string;
  subtitle: string;
  badge: string;
  endpointUrl: string;
  launchPath?: string;
  previewPath?: string;
  authLevel: string;
  description: string;
  apiMapping: string;
  audienceRoles: LiffAudienceRole[];
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
    audienceRoles: ['visitor'],
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
    audienceRoles: ['visitor'],
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
    audienceRoles: ['visitor'],
  },
  {
    id: 'profile_guard',
    type: 'liff',
    title: '4. profile_guard.html',
    subtitle: '修改登記資料身分門禁（阻擋未綁定用戶）',
    badge: '身分門禁查驗',
    endpointUrl: '/line-profile-guard',
    launchPath: '/line-profile-guard',
    authLevel: '伺服器端 Token 檢驗 ｜ 阻擋未綁定身分 ｜ 導流服務綁定',
    description: '修改登記資料前置門禁。先向伺服器驗證 LINE 登入憑證與客戶綁定資格：已綁定者放行進入 profile_update，未綁定者堅決阻擋並導流至服務綁定或需求填寫。',
    apiMapping: '門禁查驗：/api/v1/line/client-profile/query ＋ 資格放行 / 阻擋導流',
    audienceRoles: ['customer'],
  },
  {
    id: 'profile_update',
    type: 'liff',
    title: '5. profile_update.html',
    subtitle: '客戶個人資料異動申請（經門禁放行）',
    badge: '個資異動申請',
    endpointUrl: '/line-profile-update',
    launchPath: '/line-profile-guard',
    authLevel: '必須驗證 LINE 登入憑證與正式客戶綁定',
    description: '產婦可查詢目前已登記的個人資料，勾選聯絡電話、預產期或寶寶資訊等欄位並送審；服務地址與訂單條件改由 order_update 申請。',
    apiMapping: '客戶資料異動之查詢、預覽與申請流程已接通',
    audienceRoles: ['customer'],
  },
  {
    id: 'order_update',
    type: 'liff',
    title: '6. order_update.html',
    subtitle: '客戶訂單資訊異動申請',
    badge: '訂單異動申請',
    endpointUrl: '/line-order-update',
    launchPath: '/line-order-update',
    previewPath: '/line-order-update?studio_preview=1',
    authLevel: '後端驗證 LINE 登入憑證、正式客戶綁定、本人有效訂單與最新版本',
    description: '客戶選擇自己的有效訂單與異動項目，預覽修改前後內容後送出客服需求；不直接修改正式訂單、排班、費用或月嫂意願。',
    apiMapping: '訂單異動 Query／Preview／Apply 與客服案件回讀已接通',
    audienceRoles: ['customer'],
  },
  {
    id: 'staff_order_search',
    type: 'liff',
    title: '7. staff_order_search.html',
    subtitle: '月嫂安全查單',
    badge: '正式指派資料',
    endpointUrl: '/line-staff-orders',
    launchPath: '/line-staff-orders',
    authLevel: '後端驗證 LINE 登入憑證與正式月嫂綁定',
    description: '只呈現正式月嫂自助服務回傳的案件欄位、狀態與鎖定原因；本設計頁不載入或合成案件資料。',
    apiMapping: '月嫂安全查單與案件狀態流程已接通',
    audienceRoles: ['staff'],
  },
  {
    id: 'staff_schedule',
    type: 'liff',
    title: '8. staff_schedule.html',
    subtitle: '月嫂月曆、不可服務期間與請假',
    badge: '正式排班月曆',
    endpointUrl: '/line-staff-schedule',
    launchPath: '/line-staff-schedule',
    authLevel: '後端驗證 LINE 登入憑證與正式月嫂綁定',
    description: '呈現正式月曆、待定金檔期鎖、不可服務期間與請假申請；正式指派中的休息日僅稱休息日。',
    apiMapping: '月嫂排班月曆、檔期鎖定與請假 Preview／Apply 已接通',
    audienceRoles: ['staff'],
  },
  {
    id: 'staff_baby_log',
    type: 'liff',
    title: '9. staff_baby_log.html',
    subtitle: '正式服務日寶寶日誌與餐食照片',
    badge: '服務日受控登錄',
    endpointUrl: '/line-staff-baby-log',
    launchPath: '/line-staff-baby-log',
    authLevel: '後端驗證 LINE 登入憑證、正式月嫂綁定與 assignment/service-day ownership',
    description: '先由正式班表選取服務日，再預覽並送出寶寶日誌；需要下廚時照片會經受控檔案 staging。',
    apiMapping: '服務日選取、日誌與餐食照片 Preview／Apply／Readback 已接通',
    audienceRoles: ['staff'],
  },
  {
    id: 'staff_payout',
    type: 'liff',
    title: '10. staff_payout.html',
    subtitle: '本人逐案薪資請款與付款紀錄',
    badge: '正式綁定唯讀',
    endpointUrl: '/line-staff-payout',
    launchPath: '/line-staff-payout',
    authLevel: '後端驗證 LINE 登入憑證與正式月嫂綁定；只能依本人 staff_id 查詢',
    description: '依目標付款月份顯示逐案應付金額、已付金額、狀態、目標付款日、實際付款日與交易紀錄。',
    apiMapping: '本人 staff_id ＋目標付款月份的 bounded typed query 已接通',
    audienceRoles: ['staff'],
  },
  {
    id: 'identity',
    type: 'liff',
    title: '11. identity.html',
    subtitle: '通用身分認證與服務入口',
    badge: '伺服器已驗證',
    endpointUrl: '/line-identity',
    launchPath: '/line-identity',
    authLevel: '後端驗證 LINE 登入憑證；網址列 userId 僅供導航，不具授權效果',
    description: '依已驗證的 LINE 使用者開啟客戶、月嫂或管理員流程；驗證失敗時不顯示資料，並要求重新登入。',
    apiMapping: '身分開啟、綁定檢查與確認流程已接通',
    audienceRoles: ['visitor', 'customer', 'staff', 'union_staff'],
  },
  {
    id: 'mobile_admin',
    type: 'liff',
    title: '12. mobile_admin.html',
    subtitle: '手機身分審核中心',
    badge: '檢查後送出',
    endpointUrl: '/line-mobile-admin',
    launchPath: '/line-mobile-admin',
    authLevel: '後端驗證 LINE 登入憑證與正式管理員綁定',
    description: '審核決策先顯示變更前後內容與影響，確認後送出並回讀結果。',
    apiMapping: '身分審核影響檢查、確認與結果回讀已接通',
    audienceRoles: ['union_staff'],
  },
  {
    id: 'flex_dispatch',
    type: 'flex_card',
    title: '派案通知卡設計稿（模組三：月嫂派案意願）',
    subtitle: '【模組三】候選月嫂派案意願調查 ｜ 去敏案件入口',
    badge: '模組三範本',
    endpointUrl: '排定於模組三：月嫂派案與媒合 Subsystem',
    authLevel: '候選月嫂專屬 ｜ LINE Flex 去敏安全版面（受派案資格保護）',
    description: '【業務定位】當系統媒合成功時向候選月嫂推播。去敏呈現服務期間、時段與區域，詳細地址不留在對話中；供月嫂查閱案件或回覆接案意願。',
    apiMapping: '模組三排定：LineBotPushService.send_dispatch_notice() ＋ Postback 意願回覆',
    audienceRoles: ['staff'],
    flexDesignSource: LINE_FLEX_DESIGN_SOURCES.flex_dispatch,
  },
  {
    id: 'flex_leave_confirm',
    type: 'flex_card',
    title: '服務日順延確認卡設計稿（模組三：產婦順延確認）',
    subtitle: '【模組三】產婦調休/順延雙選項確認 ｜ 雙向決策卡',
    badge: '模組三範本',
    endpointUrl: '排定於模組三：月嫂排班與請假 Subsystem',
    authLevel: '簽約產婦專屬 ｜ 雙選項互動確認（受簽約案件版本保護）',
    description: '【業務定位】月嫂因故請假時自動推播給產婦。提供「同意順延一日」或「由工會派代班」決策按鈕，回覆後經後端排班狀態機核對生效。',
    apiMapping: '模組三排定：LeaveWorkflow.push_extension_confirm() ＋ Postback 順延決策確認',
    audienceRoles: ['customer'],
    flexDesignSource: LINE_FLEX_DESIGN_SOURCES.flex_leave_confirm,
  },
  {
    id: 'flex_alert_critical',
    type: 'flex_card',
    title: '重大異常通報卡設計稿（模組四：幹部重大告警）',
    subtitle: '【模組四】工會幹部群重大告警 ｜ 幹部通知版面',
    badge: '模組四範本',
    endpointUrl: '排定於模組四：客服與異常處置 Subsystem',
    authLevel: '工會幹部群組專屬 ｜ 去敏高層級告警（僅推播已授權幹部群）',
    description: '【業務定位】重大客訴、連續身分核對異常或重大排班衝突時，自動推播至幹部群組，並附帶一鍵進入手機管理中心審核處理之入口。',
    apiMapping: '模組四排定：AlertDispatchService.broadcast_critical_alert() ＋ 管理中心一鍵處置',
    audienceRoles: ['union_staff'],
    flexDesignSource: LINE_FLEX_DESIGN_SOURCES.flex_alert_critical,
  },
  {
    id: 'flex_negotiation',
    type: 'flex_card',
    title: '媒合條件溝通卡設計稿（模組三：服務條件調解）',
    subtitle: '【模組三】零媒合服務條件調解建議 ｜ 條件確認卡',
    badge: '模組三範本',
    endpointUrl: '排定於模組三：月嫂派案與媒合 Subsystem',
    authLevel: '簽約產婦專屬 ｜ 條件調解確認（受需求登記保護）',
    description: '【業務定位】當案件無候選月嫂可接單時，系統自動分析並向產婦提出可微調方案（如時數、天數建議），產婦可一鍵確認調整以加速媒合。',
    apiMapping: '模組三排定：ZeroPoolEngine.push_compromise_options() ＋ 方案確認 postback',
    audienceRoles: ['customer'],
    flexDesignSource: LINE_FLEX_DESIGN_SOURCES.flex_negotiation,
  },
];

function canonicalLiffUrl(path: string, origin: string): string {
  return new URL(path, origin).toString();
}

function liffHashParams(): URLSearchParams {
  return new URLSearchParams(window.location.hash.split('?', 2)[1] ?? '');
}

function LiffVisualPreview({ item }: { item: LiffAssetItem }) {
  if (item.id === 'gateway' || item.id === 'identity') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">服務確認與導流</div>
        <p>請確認您是否已於新竹市政府平台完成申請登記：</p>
        <button type="button" className="mock-primary-btn" disabled>已申請市府平台</button>
        <small>我已在市府媒合服務平台完成登記，要繼續填寫工會【需求調查表單】。</small>
        <button type="button" className="mock-primary-btn" disabled>未申請市府平台</button>
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
        <strong>1. 基本資料</strong>
        <label>產婦姓名 *</label><input type="text" placeholder="請填寫真實姓名" readOnly />
        <label>身分證字號 *</label><input type="text" placeholder="例如：A123456789" readOnly />
        <label>行動電話 *</label><input type="text" placeholder="例如：0912345678" readOnly />
        <label>服務地址 *</label><input type="text" placeholder="請填寫完整地址（含巷弄樓層）" readOnly />
        <strong>2. 照護與環境</strong>
        <label>預產期（或已生產日期） *</label><input type="date" readOnly />
        <label>預計服務天數 *</label><input type="number" readOnly />
        <strong>3. 飲食偏好</strong>
        <label><input type="radio" disabled /> 葷食</label>
        <label><input type="radio" disabled /> 素食</label>
        <strong>4. 居家設備與環境</strong>
        <label><input type="checkbox" disabled /> 大同電鍋</label>
        <label><input type="checkbox" disabled /> 奶瓶消毒鍋</label>
        <strong>5. 費用與同意條款</strong>
        <label><input type="checkbox" disabled /> 已詳閱退費原則</label>
        <button type="button" className="mock-primary-btn" disabled>預覽登記資料</button>
      </div>
    );
  }

  if (item.id === 'profile_guard') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator mock-step-danger">身分資格門禁</div>
        <p className="mock-blocked-title">尚未完成工會服務綁定</p>
        <small className="mock-blocked-description">
          修改登記資料僅限已在工會完成媒合登記或服務綁定之產婦使用。系統查無此 LINE 帳號之客戶綁定，直接在此阻擋。
        </small>
        <button type="button" className="mock-primary-btn mock-action-spacing" disabled>
          前往服務綁定 (/line-bind)
        </button>
        <button type="button" className="mock-primary-btn mock-secondary-preview-action" disabled>
          填寫需求調查表單 (/line-registration)
        </button>
        <small className="mock-security-note">
          伺服器端 Token 檢驗 ｜ 阻擋未綁定身分 ｜ 防竄改架構
        </small>
      </div>
    );
  }

  if (item.id === 'profile_update') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">修改登記資料申請</div>
        <p>產婦可查詢目前已登記資料，勾選欲異動之項目並送審：</p>
        <label>欲異動項目</label>
        <div className="mock-change-options">
          <span><CheckSquare aria-hidden="true" /> 聯絡電話</span>
          <span><CheckSquare aria-hidden="true" /> 預產期</span>
          <span><CheckSquare aria-hidden="true" /> 寶寶資訊</span>
          <span><CheckSquare aria-hidden="true" /> 生產方式</span>
        </div>
        <label>填寫異動內容</label>
        <textarea rows={2} placeholder="請輸入欲變更的新內容" readOnly />
        <button type="button" className="mock-primary-btn" disabled>預覽異動差異</button>
        <small>正式異動流程已接通後端 API；送出後等待工會人員審核。</small>
      </div>
    );
  }

  if (item.id === 'order_update') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">修改訂單資訊申請</div>
        <p>選擇本人的有效訂單與異動項目，確認修改前後內容後送出申請。</p>
        <label>選擇訂單</label>
        <div className="mock-placeholder-box">
          <strong>案件 CASE-2026-018</strong>
          <small>訂單成立 ｜ 2026-10-01 至 2026-10-20</small>
        </div>
        <label>修改項目</label>
        <div className="mock-change-options">
          <span><CheckSquare aria-hidden="true" /> 服務地址</span>
          <span><CheckSquare aria-hidden="true" /> 下廚需求</span>
          <span><CheckSquare aria-hidden="true" /> 服務日期／天數</span>
          <span><CheckSquare aria-hidden="true" /> 每日時段</span>
        </div>
        <button type="button" className="mock-primary-btn" disabled>預覽修改內容</button>
        <small>送出後建立客服需求；正式訂單維持不變並等待工會確認。</small>
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
        <div className="mock-step-indicator">排班資訊與請假</div>
        <p>您可以查詢個人班表月曆，並預覽、確認請假申請。</p>
        <label>查詢月份</label><input type="month" readOnly />
        <button type="button" className="mock-primary-btn" disabled>查詢班表</button>
        <div className="mock-placeholder-box">
          <small>服務日 ｜ 指派休息日 ｜ 已鎖定／待成立</small>
          <small>正式不可服務 ｜ 歷史指派 ｜ 未排班</small>
        </div>
      </div>
    );
  }

  if (item.id === 'staff_baby_log') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">寶寶日誌</div>
        <label>服務月份</label><input type="month" readOnly />
        <label>正式服務日</label><input type="text" value="請先載入正式服務日" readOnly />
        <label>寶寶日誌</label><textarea rows={2} placeholder="選擇服務日後填寫" readOnly />
        <button type="button" className="mock-primary-btn" disabled>預覽寶寶日誌</button>
      </div>
    );
  }

  if (item.id === 'staff_payout') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">薪資請款明細</div>
        <label>目標付款月份</label><input type="month" readOnly />
        <button type="button" className="mock-primary-btn" disabled>查詢薪資明細</button>
        <div className="mock-placeholder-box">
          <strong>案件編號｜應付金額｜付款狀態</strong>
          <small>目標付款日｜實際付款日｜逐筆交易紀錄</small>
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
        <div className="mock-placeholder-box">審核中心待辦：客服工單、排班審核與月嫂驗證。</div>
      </div>
    );
  }

  if (item.id === 'identity') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">通用身分認證入口</div>
        <p>依 LINE 登入憑證開啟客戶、月嫂或幹部服務流程：</p>
        <button type="button" className="mock-primary-btn" disabled>LINE 快速登入驗證</button>
        <small>網址列 userId 僅供導航，不具授權效果；由伺服器驗證 ID Token。</small>
      </div>
    );
  }

  return (
    <div className="mock-admin-view">
      <div className="mock-placeholder-box">此頁面可點擊下方連結直接開啟實體網頁進行測試。</div>
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
  const [selectedId, setSelectedId] = useState<string>(() => {
    const requested = liffHashParams().get('asset');
    return requested && ASSET_ITEMS.some((item) => item.id === requested) ? requested : 'gateway';
  });
  const [filterType, setFilterType] = useState<'all' | 'liff' | 'flex_card'>(() => {
    const requested = liffHashParams().get('type');
    return requested === 'liff' || requested === 'flex_card' ? requested : 'all';
  });
  const [filterRole, setFilterRole] = useState<'all' | LiffAudienceRole>(() => {
    const requested = liffHashParams().get('role');
    return requested === 'visitor' || requested === 'customer' || requested === 'staff' || requested === 'union_staff'
      ? requested
      : 'all';
  });
  const [searchQuery, setSearchQuery] = useState(() => liffHashParams().get('q') ?? '');
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
  const normalizedSearch = searchQuery.trim().toLocaleLowerCase('zh-TW');
  const filteredItems = ASSET_ITEMS.filter((item) => (
    (filterType === 'all' || item.type === filterType)
    && (filterRole === 'all' || item.audienceRoles.includes(filterRole))
    && (!normalizedSearch || [item.title, item.subtitle, item.description, item.badge]
      .some((value) => value.toLocaleLowerCase('zh-TW').includes(normalizedSearch)))
  ));
  const liffCount = ASSET_ITEMS.filter((item) => item.type === 'liff').length;
  const flexCount = ASSET_ITEMS.filter((item) => item.type === 'flex_card').length;

  useEffect(() => {
    if (filteredItems.length > 0 && !filteredItems.some((item) => item.id === selectedId)) {
      setSelectedId(filteredItems[0].id);
    }
  }, [filterRole, filterType, normalizedSearch, selectedId]);

  useEffect(() => {
    const route = window.location.hash.replace(/^#\/?/, '').split('?', 1)[0];
    if (route !== 'line-liff-studio' && route !== 'line-studio') return;
    const params = liffHashParams();
    const setParam = (key: string, value: string, fallback: string) => {
      if (value === fallback || value === '') params.delete(key);
      else params.set(key, value);
    };
    setParam('asset', selectedId, 'gateway');
    setParam('type', filterType, 'all');
    setParam('role', filterRole, 'all');
    setParam('q', searchQuery, '');
    const query = params.toString();
    const nextHash = `#${route}${query ? `?${query}` : ''}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}${nextHash}`);
    }
  }, [filterRole, filterType, searchQuery, selectedId]);

  return (
    <div className="liff-studio-container">
      <header className="line-hub-page-header liff-studio-page-header">
        <div className="line-hub-page-heading">
          <span className="line-hub-page-icon" aria-hidden="true"><PanelTop /></span>
          <div>
            <p className="line-hub-eyebrow">LINE 專區</p>
            <h1>LIFF 資產工作室</h1>
            <p>查找、預覽並驗收正式 LIFF 入口與 Flex 卡片設計。</p>
          </div>
        </div>
      </header>
      <div className="liff-studio-sidebar">
        <div className="liff-sidebar-header">
          <h2>資產目錄</h2>
          <label className="liff-search-field">
            <span className="sr-only">搜尋資產</span>
            <Search aria-hidden="true" />
            <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜尋名稱或用途" />
          </label>
          <div className="liff-filter-pills">
            <button className={filterType === 'all' ? 'active' : ''} onClick={() => setFilterType('all')}>全部 ({ASSET_ITEMS.length})</button>
            <button className={filterType === 'liff' ? 'active' : ''} onClick={() => setFilterType('liff')}>LIFF 表單 ({liffCount})</button>
            <button className={filterType === 'flex_card' ? 'active' : ''} onClick={() => setFilterType('flex_card')}>Flex 卡片 ({flexCount})</button>
          </div>
          <label className="line-filter-field liff-role-filter">
            <span>適用角色</span>
            <select
              aria-label="依適用角色篩選資產"
              value={filterRole}
              onChange={(event) => setFilterRole(event.target.value as 'all' | LiffAudienceRole)}
            >
              <option value="all">全部角色</option>
              <option value="visitor">訪客／未綁定</option>
              <option value="customer">產婦／客戶</option>
              <option value="staff">月嫂</option>
              <option value="union_staff">工會人員</option>
            </select>
          </label>
        </div>

        <div className="liff-asset-list">
          {filteredItems.length === 0 && (
            <div className="line-empty-state compact" role="status">
              <strong>找不到符合條件的資產</strong>
              <button type="button" className="line-secondary-btn" onClick={() => { setSearchQuery(''); setFilterType('all'); setFilterRole('all'); }}>清除條件</button>
            </div>
          )}
          {filteredItems.map((item) => (
            <button
              type="button"
              key={item.id}
              className={`liff-asset-card ${item.id === selectedId ? 'active' : ''}`}
              onClick={() => setSelectedId(item.id)}
            >
              <div className="liff-card-header"><strong>{item.title.replace(/^\d+\.\s*/, '')}</strong><span className="liff-tag">{item.badge}</span></div>
              <p>{item.subtitle}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="liff-simulator-workbench">
        <div className="liff-phone-frame" key={selectedItem.id}>
          <div className="liff-phone-notch"><span className="notch-speaker" /><span className="notch-camera" /></div>
          <div className="liff-phone-statusbar"><span>09:41</span><span>5G · 100%</span></div>
          <div className="liff-phone-screen">
            {selectedItem.type === 'liff' ? (
              <div className="mock-liff-content">
                <div className="mock-liff-nav"><span>新竹市到宅月子工會</span></div>
                <div className="mock-liff-body">
                  <div className="mock-liff-badge">身分由伺服器驗證</div>
                  <h3 className="mock-liff-title">{selectedItem.subtitle}</h3>
                  <p className="mock-liff-desc">{selectedItem.description}</p>
                  <LiffVisualPreview item={selectedItem} />
                  {selectedItem.launchPath ? (
                    runtimeConfig.status === 'ready' ? (
                      <a
                        className="mock-primary-btn liff-preview-open-link"
                        href={canonicalLiffUrl(selectedItem.previewPath ?? selectedItem.launchPath, runtimeConfig.origin)}
                        aria-label={selectedItem.previewPath ? '在預覽中開啟安全展示頁' : '在預覽中開啟正式 LIFF 入口'}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {selectedItem.previewPath ? '開啟安全預覽' : '開啟正式 LIFF 入口'}
                      </a>
                    ) : (
                      <div className="line-warning liff-preview-warning" role="status">
                        {runtimeConfig.status === 'loading'
                          ? '正在取得正式 LIFF 測試網址…'
                          : `正式 LIFF 測試網址無法使用：${runtimeConfig.message}`}
                      </div>
                    )
                  ) : (
                    <div className="line-warning liff-preview-warning" role="status">
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
          <h3><ShieldCheck aria-hidden="true" /> 資安與存取摘要</h3>
          <div className="spec-item"><span>適用角色：</span><strong>{selectedItem.audienceRoles.map((role) => ({ visitor: '訪客／未綁定', customer: '產婦／客戶', staff: '月嫂', union_staff: '工會人員' }[role])).join('、')}</strong></div>
          <div className="spec-item"><span>驗證摘要：</span><strong>{selectedItem.authLevel}</strong></div>
          <details className="liff-security-details">
            <summary>查看技術與資安細節</summary>
            <div className="spec-item"><span>端點路徑：</span><code>{selectedItem.endpointUrl}</code></div>
            <div className="spec-item"><span>資安邊界：</span><small>網址列 userId 僅導航、不授權 ｜ 不顯示原始憑證 ｜ 不把排入發送當成已送達</small></div>
          </details>
        </div>

        <div className="liff-inspector-card">
          <h3><Link2 aria-hidden="true" /> 關聯功能與目前狀態</h3>
          <div className="code-mapping-box">{selectedItem.apiMapping}</div>
        </div>
      </div>
    </div>
  );
};
