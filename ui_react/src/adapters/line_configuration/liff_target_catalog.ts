/**
 * File: liff_target_catalog.ts
 * Description: 統一集中 LIFF 表單資產定義，並自動衍生 Rich Menu 的 LIFF 入口清單。
 */

export type LiffAssetType = 'liff';
export type LiffAudienceRole = 'visitor' | 'customer' | 'staff' | 'union_staff';

export interface LiffAssetItem {
  id: string;
  displayTitle: string;
  purpose: string;
  group: string;
  type: LiffAssetType;
  title: string;
  subtitle: string;
  badge: string;
  endpointUrl: string;
  launchPath?: string;
  previewPath?: string;
  launchNote?: string;
  authLevel: string;
  description: string;
  apiMapping: string;
  audienceRoles: LiffAudienceRole[];
}

export const ASSET_ITEMS: LiffAssetItem[] = [
  {
    id: 'gateway',
    displayTitle: "服務申請入口",
    purpose: "確認市府登記，前往適合的服務。",
    group: "身分與服務入口",
    type: 'liff',
    title: '1. gateway.html',
    subtitle: '服務確認與身分先行導流',
    badge: '伺服器已驗證',
    endpointUrl: '/line-gateway',
    launchPath: '/line-gateway',
    authLevel: '後端驗證 LINE 登入憑證；網址列 userId 僅供導航，不具授權效果',
    description: '正式入口先詢問是否已登記市府平台：已申請者繼續填寫工會「需求調查表單」，未申請者引導至新竹市到宅坐月子媒合服務平台。',
    apiMapping: '身分開啟、候選綁定檢查與確認流程示意',
    audienceRoles: ['visitor'],
  },
  {
    id: 'register',
    displayTitle: "需求調查",
    purpose: "填寫基本資料與到宅照護需求。",
    group: "身分與服務入口",
    type: 'liff',
    title: '2. register.html',
    subtitle: '產婦需求調查表單',
    badge: '檢查後送出',
    endpointUrl: '/line-registration',
    launchPath: '/line-registration',
    authLevel: '後端驗證 LINE 登入憑證；不接受網址列身分',
    description: '登記資料先顯示隱去個資的摘要，明確確認後才送出；完整建立服務需求調查。',
    apiMapping: '登記資料檢查、確認送出與結果回讀',
    audienceRoles: ['visitor'],
  },
  {
    id: 'bind',
    displayTitle: "連結客戶資料",
    purpose: "將 LINE 帳號連結既有客戶資料。",
    group: "身分與服務入口",
    type: 'liff',
    title: '3. bind.html',
    subtitle: '既有客戶綁定入口（正式身分分流）',
    badge: '檢查後送出',
    endpointUrl: '/line-bind',
    launchPath: '/line-bind',
    authLevel: '後端驗證 LINE 登入憑證；候選匹配後仍需明確確認',
    description: '正式入口先顯示登記選擇；選擇已登記後才進入候選資料檢查與明確確認，不以姓名、電話或網址列 userId 授權。',
    apiMapping: '候選綁定、資料檢查與確認送出流程示意',
    audienceRoles: ['visitor'],
  },
  {
    id: 'non_citizen_registration', displayTitle: '非市民服務申請', purpose: '填寫非市民服務需求，送工會核准建案。',
    group: '身分與服務入口', type: 'liff', title: '非市民服務申請', subtitle: '自費服務申請', badge: '待工會核准',
    endpointUrl: '/line-non-citizen-registration', launchPath: '/line-non-citizen-registration',
    authLevel: '後端驗證 LINE 登入憑證', description: '合併服務需求及報名問卷，工會核准後才建立正式案件。',
    apiMapping: '既有 registration Preview／Apply 及工會核准', audienceRoles: ['visitor', 'customer'],
  },
  {
    id: 'profile_guard',
    displayTitle: "修改資料前的身分確認",
    purpose: "查看已綁定與未綁定時的引導。",
    group: "客戶服務",
    type: 'liff',
    title: '4. profile_guard.html',
    subtitle: '修改登記資料前的身分確認',
    badge: '身分門禁查驗',
    endpointUrl: '/line-profile-guard',
    launchPath: '/line-profile-guard',
    authLevel: '伺服器端 Token 檢驗 ｜ 阻擋未綁定身分 ｜ 導流服務綁定',
    description: '修改登記資料前置門禁。先向伺服器驗證 LINE 登入憑證與客戶綁定資格：已綁定者可修改資料；未綁定者需先連結客戶資料或填寫需求。',
    apiMapping: '門禁查驗：/api/v1/line/client-profile/query ＋ 資格放行 / 阻擋導流',
    audienceRoles: ['customer'],
  },
  {
    id: 'profile_update',
    displayTitle: "修改個人資料",
    purpose: "申請變更聯絡方式與寶寶資訊。",
    group: "客戶服務",
    type: 'liff',
    title: '5. profile_update.html',
    subtitle: '客戶個人資料異動申請',
    badge: '個資異動申請',
    endpointUrl: '/line-profile-update',
    launchPath: '/line-profile-guard',
    authLevel: '必須驗證 LINE 登入憑證與正式客戶綁定',
    description: '產婦可查詢目前已登記的個人資料，勾選聯絡電話或寶寶資訊等欄位並送審；服務地址與訂單條件請從「訂單資訊異動申請」提出。',
    apiMapping: '客戶資料異動之查詢、預覽與申請流程示意',
    audienceRoles: ['customer'],
  },
  {
    id: 'order_update',
    displayTitle: "申請訂單異動",
    purpose: "提出服務地址、天數或時段異動。",
    group: "客戶服務",
    type: 'liff',
    title: '6. order_update.html',
    subtitle: '客戶訂單資訊異動申請',
    badge: '訂單異動申請',
    endpointUrl: '/line-order-update',
    launchPath: '/line-order-update',
    previewPath: '/line-order-update?studio_preview=1',
    authLevel: '後端驗證 LINE 登入憑證、正式客戶綁定、本人有效訂單與最新版本',
    description: '客戶選擇自己的有效訂單與異動項目，預覽修改前後內容後送出客服需求；不直接修改正式訂單、排班、費用或月嫂意願。',
    apiMapping: '訂單異動 Query／Preview／Apply 與客服案件回讀流程示意',
    audienceRoles: ['customer'],
  },
  {
    id: 'candidate_contact_customer',
    displayTitle: "媒合條件協調",
    purpose: "回覆可調整的服務條件。",
    group: "客戶服務",
    type: 'liff',
    title: '7. candidate_contact_customer.html',
    subtitle: '客戶確認可調整的媒合條件',
    badge: '案件專屬回覆',
    endpointUrl: '/line-candidate-contact-customer?ref={案件專屬識別碼}',
    authLevel: '後端驗證 LINE 登入憑證、正式客戶綁定、案件與協調事件；只允許通知收件人回覆',
    description: '工會自行輸入詢問文案；客戶回答更新後的條件，工會審核通過即更新案件條件，再選月嫂重新詢問意願。',
    apiMapping: '客戶回答更新條件，工會審核並重新詢問意願',
    audienceRoles: ['customer'],
    launchNote: '此頁必須由客戶收到的案件協調卡帶入專屬識別碼，無法從管理頁建立通用正式入口。',
  },
  {
    id: 'staff_order_search',
    displayTitle: "我的案件",
    purpose: "查詢已指派的案件與服務摘要。",
    group: "月嫂服務",
    type: 'liff',
    title: '8. staff_order_search.html',
    subtitle: '月嫂安全查單',
    badge: '正式指派資料',
    endpointUrl: '/line-staff-orders',
    launchPath: '/line-staff-orders',
    authLevel: '後端驗證 LINE 登入憑證與正式月嫂綁定',
    description: '只呈現正式月嫂自助服務回傳的案件欄位、狀態與鎖定原因；本設計頁不載入或合成案件資料。',
    apiMapping: '月嫂安全查單與案件狀態流程示意',
    audienceRoles: ['staff'],
  },
  {
    id: 'staff_schedule',
    displayTitle: "班表與請假",
    purpose: "查看班表，記錄已協調的順延或提出代班需求。",
    group: "月嫂服務",
    type: 'liff',
    title: '9. staff_schedule.html',
    subtitle: '月嫂月曆、不可服務期間與請假',
    badge: '排班月曆',
    endpointUrl: '/line-staff-schedule',
    launchPath: '/line-staff-schedule',
    authLevel: '後端驗證 LINE 登入憑證與正式月嫂綁定',
    description: '呈現班表與不可服務期間；月嫂填入已協調的順延日期，無衝突即更新排班、帳務並發日期表到案件群組；需要代班或有衝突才交工會。',
    apiMapping: '班表、已協調順延及代班需求',
    audienceRoles: ['staff'],
  },
  {
    id: 'staff_baby_log',
    displayTitle: "寶寶日誌與餐食照片",
    purpose: "依服務日填寫照護紀錄。",
    group: "月嫂服務",
    type: 'liff',
    title: '10. staff_baby_log.html',
    subtitle: '服務日寶寶日誌與餐食照片',
    badge: '服務日受控登錄',
    endpointUrl: '/line-staff-baby-log',
    launchPath: '/line-staff-baby-log',
    authLevel: '後端驗證 LINE 登入憑證、正式月嫂綁定與本人排班與服務日期',
    description: '選取服務日並填寫日誌與照片，點擊送出即儲存並顯示成功；可提前填寫，送出後無修改入口。',
    apiMapping: '服務日選取、日誌與照片直接送出',
    audienceRoles: ['staff'],
  },
  {
    id: 'staff_payout',
    displayTitle: "薪資與付款紀錄",
    purpose: "依月份查看逐案薪資與付款明細。",
    group: "月嫂服務",
    type: 'liff',
    title: '11. staff_payout.html',
    subtitle: '本人逐案薪資請款與付款紀錄',
    badge: '正式綁定唯讀',
    endpointUrl: '/line-staff-payout',
    launchPath: '/line-staff-payout',
    authLevel: '後端驗證 LINE 登入憑證與正式月嫂綁定；只能依本人 staff_id 查詢',
    description: '依目標付款月份顯示逐案應付金額、已付金額、狀態、目標付款日、實際付款日與交易紀錄。',
    apiMapping: '本人 staff_id ＋目標付款月份的 bounded typed query 流程示意',
    audienceRoles: ['staff'],
  },
  {
    id: 'candidate_contact',
    displayTitle: "接案回覆",
    purpose: "提出疑問、調整條件或回覆無意願。",
    group: "月嫂服務",
    type: 'liff',
    title: '12. candidate_contact.html',
    subtitle: '候選月嫂提出疑問或回覆無法承接',
    badge: '案件回覆',
    endpointUrl: '/line-candidate-contact?ref={案件專屬識別碼}',
    launchPath: '/line-candidate-contact',
    previewPath: '/line-candidate-contact?studio_preview=1',
    authLevel: '後端驗證 LINE 登入憑證、候選月嫂身分、案件收件人；24 小時僅作內部提醒',
    description: '候選月嫂可針對服務地區、日期、時段、時數、下廚、交通或個人因素提出資訊問題、調整條件，或直接回覆沒有意願。',
    apiMapping: '月嫂回覆 Query／Submit、最新意願投影與客戶協調通知流程示意',
    audienceRoles: ['staff'],
  },
  {
    id: 'identity',
    displayTitle: "身分認證",
    purpose: "登入 LINE，進入自己的服務。",
    group: "身分與服務入口",
    type: 'liff',
    title: '13. identity.html',
    subtitle: '通用身分認證與服務入口',
    badge: '伺服器已驗證',
    endpointUrl: '/line-identity',
    launchPath: '/line-identity',
    authLevel: '後端驗證 LINE 登入憑證；網址列 userId 僅供導航，不具授權效果',
    description: '依已驗證的 LINE 使用者開啟客戶、月嫂或管理員流程；驗證失敗時不顯示資料，並要求重新登入。',
    apiMapping: '身分開啟、綁定檢查與確認流程示意',
    audienceRoles: ['visitor', 'customer', 'staff', 'union_staff'],
  },
  {
    id: 'mobile_admin_staff_review',
    displayTitle: "待辦工作台",
    purpose: "查看身分審核與案件待辦。",
    group: "工會工作",
    type: 'liff',
    title: '14. mobile_admin.html · 待辦工作台',
    subtitle: '待辦工作台',
    badge: '月嫂身分待審',
    endpointUrl: '/line-mobile-admin?target=staff_review',
    launchPath: '/line-mobile-admin?target=staff_review',
    previewPath: '/line-mobile-admin?target=staff_review&studio_preview=1',
    authLevel: '後端驗證 LINE 登入憑證與正式管理員綁定',
    description: '呈現月嫂身分審核與案件待辦；工會查看目前待處理項目並決定是否發送提醒。',
    apiMapping: '月嫂身分審核 Query／Preview／Apply 與排班案號工具流程示意',
    audienceRoles: ['union_staff'],
  },
  {
    id: 'mobile_admin_customer_service',
    displayTitle: "客服中心",
    purpose: "查看客服案件與對話。",
    group: "工會工作",
    type: 'liff',
    title: '15. mobile_admin.html · 客服中心',
    subtitle: '客服中心',
    badge: '客服案件',
    endpointUrl: '/line-mobile-admin?target=customer_service',
    launchPath: '/line-mobile-admin?target=customer_service',
    previewPath: '/line-mobile-admin?target=customer_service&studio_preview=1',
    authLevel: '後端驗證 LINE 登入憑證與正式管理員綁定',
    description: '只載入客服案件、對話與回覆流程，不與身分審核共用可見工作面。',
    apiMapping: '客服摘要、案件列表、回覆 Preview／Apply 與結果回讀流程示意',
    audienceRoles: ['union_staff'],
  },
  {
    id: 'mobile_admin_order_tracking',
    displayTitle: "訂單進度",
    purpose: "依案件編號查詢目前進度。",
    group: "工會工作",
    type: 'liff',
    title: '16. mobile_admin.html · 狀態追蹤',
    subtitle: '狀態追蹤',
    badge: 'Orders 唯讀',
    endpointUrl: '/line-mobile-admin?target=order_tracking',
    launchPath: '/line-mobile-admin?target=order_tracking',
    previewPath: '/line-mobile-admin?target=order_tracking&studio_preview=1',
    authLevel: '後端驗證 LINE 登入憑證與正式管理員綁定；訂單進度為唯讀',
    description: '依案件編號查詢未完成訂單目前階段、最後更新與下一步；此入口不修改訂單。',
    apiMapping: 'Orders operational-stage projection bounded typed readback 流程示意',
    audienceRoles: ['union_staff'],
  },
  {
    id: 'mobile_admin_dashboard',
    displayTitle: "營運摘要",
    purpose: "查看本週的營運統計。",
    group: "工會工作",
    type: 'liff',
    title: '17. mobile_admin.html · 營運摘要',
    subtitle: '營運摘要',
    badge: '本週六項統計',
    endpointUrl: '/line-mobile-admin?target=dashboard',
    launchPath: '/line-mobile-admin?target=dashboard',
    previewPath: '/line-mobile-admin?target=dashboard&studio_preview=1',
    authLevel: '後端驗證 LINE 登入憑證與正式管理員綁定；只回傳本週彙總',
    description: '依 Asia／Taipei 業務週顯示本週六項營運統計、期間與產生時間。',
    apiMapping: 'operations-report.v3 本週 bounded summary query 流程示意',
    audienceRoles: ['union_staff'],
  },

];

export interface LiffTargetOption {
  value: string;
  label: string;
  audienceRoles: LiffAudienceRole[];
}

/**
 * 依據既有 LIFF 資產 ID 映射為對應的 Rich Menu target 參數。
 */
const ASSET_TO_TARGET_MAP: Record<string, { value: string; overrideLabel?: string }> = {
  gateway: { value: '?entry=gateway' },
  bind: { value: '?entry=registration' },
  profile_update: { value: '?target=profile_update' },
  order_update: { value: '?target=order_update' },
  staff_order_search: { value: '?target=staff_order_search' },
  staff_schedule: { value: '?target=staff_schedule' },
  staff_baby_log: { value: '?target=staff_baby_log' },
  staff_payout: { value: '?target=staff_payout' },
  identity: { value: '?target=staff_verification', overrideLabel: '月嫂身分綁定' },
  mobile_admin_staff_review: { value: '?target=staff_review' },
  mobile_admin_customer_service: { value: '?target=customer_service' },
  mobile_admin_order_tracking: { value: '?target=order_tracking' },
  mobile_admin_dashboard: { value: '?target=dashboard' },
};

/**
 * 通用服務入口（不在獨立表單資產卡片內，但屬正式 LINE 入口）。
 */
const ADDITIONAL_TARGETS: LiffTargetOption[] = [
  { value: '?target=gateway', label: '服務申請入口（?target=gateway）', audienceRoles: ['visitor'] },
  { value: '?target=staff_leave_apply', label: '月嫂請假登記，相容入口（?target=staff_leave_apply）', audienceRoles: ['staff'] },
  { value: '?target=faq', label: '常見問答（?target=faq）', audienceRoles: ['visitor', 'customer'] },
  { value: '?target=ai_assistant', label: 'AI 智慧問答（?target=ai_assistant）', audienceRoles: ['visitor', 'customer'] },
  { value: '?target=scheduling_review', label: '排班審核（?target=scheduling_review）', audienceRoles: ['union_staff'] },
];

/**
 * 動態從 ASSET_ITEMS 衍生所有標準的 LIFF targets。
 * 未來只要在 ASSET_ITEMS 更新表單名稱或新增項目，此處自動即時更新，不需手動維護寫死清單。
 */
export function buildLiffTargetsFromAssets(): LiffTargetOption[] {
  const targets: LiffTargetOption[] = [];
  const seenValues = new Set<string>();

  for (const item of ASSET_ITEMS) {
    const mapping = ASSET_TO_TARGET_MAP[item.id];
    if (!mapping) continue;

    const title = mapping.overrideLabel ?? item.displayTitle;
    const value = mapping.value;
    if (seenValues.has(value)) continue;
    seenValues.add(value);

    targets.push({
      value,
      label: `${title}（${value}）`,
      audienceRoles: item.audienceRoles,
    });
  }

  for (const extra of ADDITIONAL_TARGETS) {
    if (!seenValues.has(extra.value)) {
      seenValues.add(extra.value);
      targets.push(extra);
    }
  }

  return targets;
}

export const CANONICAL_LIFF_TARGETS: LiffTargetOption[] = buildLiffTargetsFromAssets();

/**
 * 依選單適用對象（visitor, customer, staff, union_staff）智慧過濾 LIFF 目標。
 * 若指定角色，將該角色適用的項目排在最前或專屬呈現。
 */
export function getLiffTargetsForRole(role?: string | null): LiffTargetOption[] {
  const all = buildLiffTargetsFromAssets();
  if (!role || role === 'all') return all;

  const matched = all.filter((item) => item.audienceRoles.includes(role as LiffAudienceRole));
  const others = all.filter((item) => !item.audienceRoles.includes(role as LiffAudienceRole));

  return [...matched, ...others];
}
