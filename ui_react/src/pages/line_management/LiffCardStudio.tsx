/**
 * File: LiffCardStudio.tsx
 * Description: 依用途分組呈現 LIFF 表單預覽，保留既有正式入口與身分驗證流程。
 */
import React, { useEffect, useId, useRef, useState } from 'react';
import { CheckSquare, ChevronRight, FileText, Maximize2, PanelTop, Search, Smartphone, X } from 'lucide-react';
import {
  lineIdentityRuntimeConfigClient,
  type LineIdentityRuntimeConfigClient,
} from '../../api/line_identity/line_identity_runtime_config_client';
import '../LineManagementPage.css';
import './LiffCardStudio.css';
import { NonCitizenLiffSettingsPanel } from './NonCitizenLiffSettingsPanel';

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

const ASSET_ITEMS: LiffAssetItem[] = [
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

function canonicalLiffUrl(path: string, origin: string): string {
  return new URL(path, origin).toString();
}

function liffHashParams(): URLSearchParams {
  return new URLSearchParams(window.location.hash.split('?', 2)[1] ?? '');
}

function LiffVisualPreview({ item }: { item: LiffAssetItem }) {
  if (item.id === 'gateway') {
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

  if (item.id === 'register' || item.id === 'non_citizen_registration') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">需求調查表單</div>
        <strong>1. 基本資料</strong>
        <label>產婦姓名 *</label><input type="text" placeholder="請填寫真實姓名" readOnly />
        <label>身分證字號（選填）</label><input type="text" placeholder="例如：A123456789" readOnly />
        <label>行動電話 *</label><input type="text" placeholder="例如：0912345678" readOnly />
        <label>服務地址 *</label><input type="text" placeholder="請填寫完整地址（含巷弄樓層）" readOnly />
        {item.id === 'non_citizen_registration' && <>
          <label>出生日期 *</label><input type="date" readOnly />
          <label>性別 *</label><input placeholder="請選擇性別" readOnly />
          <label>Email *</label><input type="email" readOnly />
          <label>縣市 *</label><input readOnly />
        </>}
        <strong>2. 照護與環境</strong>
        <label>預產期（或已生產日期） *</label><input type="date" readOnly />
        <label>預計服務天數 *</label><input type="number" readOnly />
        {item.id === 'non_citizen_registration' && <>
          <strong>服務條件（必填）</strong>
          <label>預計服務開始日 *</label><input type="date" readOnly />
          <label>服務時間 *</label><input placeholder="8小時 08:00-17:00" readOnly />
          <label>居住型態／生產方式／服務方式／寶寶資訊 *</label><textarea readOnly />
          <label>其他事項及 LINE ID（無則填「無」）*</label><input readOnly />
        </>}
        <strong>3. 飲食偏好</strong>
        <label><input type="radio" disabled /> 葷食</label>
        <label><input type="radio" disabled /> 素食</label>
        <strong>4. 居家設備與環境</strong>
        <label><input type="checkbox" disabled /> 大同電鍋</label>
        <label><input type="checkbox" disabled /> 奶瓶消毒鍋</label>
        <strong>5. 費用與同意條款</strong>
        {item.id === 'non_citizen_registration' && <><label>退款銀行／分行及帳戶 *</label><input readOnly /><small>送出後待工會核准才建立正式案件及配發 A 編號。</small></>}
        <label><input type="checkbox" disabled /> 已詳閱退費原則</label>
        <button type="button" className="mock-primary-btn" disabled>送出完整服務登記表單</button>
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
          <span><CheckSquare aria-hidden="true" /> 寶寶資訊</span>
          <span><CheckSquare aria-hidden="true" /> 生產方式</span>
        </div>
        <label>填寫異動內容</label>
        <textarea rows={2} placeholder="請輸入欲變更的新內容" readOnly />
        <button type="button" className="mock-primary-btn" disabled>預覽異動差異</button>
        <small>正式異動流程示意後端 API；送出後等待工會人員審核。</small>
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
          <span><CheckSquare aria-hidden="true" /> 服務天數</span>
          <span><CheckSquare aria-hidden="true" /> 每日時段</span>
        </div>
        <button type="button" className="mock-primary-btn" disabled>預覽修改內容</button>
        <small>送出後建立客服需求；正式訂單維持不變並等待工會確認。</small>
      </div>
    );
  }

  if (item.id === 'candidate_contact_customer') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">媒合條件協調</div>
        <p>請依工會提出的問題，填寫更新後的服務條件。</p>
        <div className="mock-placeholder-box">
          <strong>可協調項目</strong>
          <small>此處顯示工會人員自行輸入的詢問文案。</small>
        </div>
        <label>更新後的條件</label>
        <textarea rows={2} placeholder="請填寫更新後的條件" readOnly />
        <label>補充說明（選填）</label>
        <textarea rows={2} placeholder="可補充能調整的方式" readOnly />
        <button type="button" className="mock-primary-btn" disabled>送出回答</button>
        <small>工會審核通過即更新案件條件；未通過時由人員再次詢問。</small>
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
        <p>雙方自行協調後，由月嫂填入順延日期；無衝突即更新，需代班或有衝突才交工會。</p>
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
        <label>服務日</label><input type="text" value="請先載入服務日" readOnly />
        <label>寶寶日誌</label><textarea rows={2} placeholder="選擇服務日後填寫" readOnly />
        <button type="button" className="mock-primary-btn" disabled>送出日誌</button>
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

  if (item.id === 'candidate_contact') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">候選月嫂案件回覆</div>
        <p>可複選需要確認的資訊或希望客戶調整的條件，也可以直接選擇沒有意願。</p>
        <div className="mock-change-options">
          <span><CheckSquare aria-hidden="true" /> 服務地區</span>
          <span><CheckSquare aria-hidden="true" /> 服務日期／檔期</span>
          <span><CheckSquare aria-hidden="true" /> 每日服務時段／時數</span>
          <span><CheckSquare aria-hidden="true" /> 下廚、交通或個人因素</span>
          <span><CheckSquare aria-hidden="true" /> 沒有意願</span>
        </div>
        <button type="button" className="mock-primary-btn" disabled>送出回應</button>
        <small>調整條件只表示修改後可重新詢問，不會直接標示為願意承接。</small>
      </div>
    );
  }

  if (item.id === 'mobile_admin_staff_review') {
    return (
      <div className="mock-admin-view">
        <div className="mock-step-indicator">待辦工作台</div>
        <p>列出身分審核與案件待辦，可由工會決定是否發送提醒。</p>
        <div className="mock-placeholder-box">身分待審 ｜ 案件群組與連續缺漏天數 ｜ 各期逾期款項</div>
        <button type="button" className="mock-primary-btn" disabled>開啟月嫂驗證</button>
        <small>只顯示目前需要人員處理的項目。</small>
      </div>
    );
  }

  if (item.id === 'mobile_admin_customer_service') {
    return (
      <div className="mock-admin-view">
        <div className="mock-step-indicator">客服中心</div>
        <p>集中查看待處理客服案件與最近訊息。</p>
        <div className="mock-placeholder-box">等待處理 ｜ 處理中 ｜ 已解決</div>
        <button type="button" className="mock-primary-btn" disabled>查看客服案件</button>
      </div>
    );
  }

  if (item.id === 'mobile_admin_order_tracking') {
    return (
      <div className="mock-admin-view">
        <div className="mock-step-indicator">狀態追蹤</div>
        <p>查詢未完成訂單的目前階段、最後更新與下一步。</p>
        <div className="mock-placeholder-box">案件編號 ｜ 目前進度 ｜ 最後更新 ｜ 下一步</div>
        <small>此工作面只讀取進度，不會直接修改訂單。</small>
      </div>
    );
  }

  if (item.id === 'mobile_admin_dashboard') {
    return (
      <div className="mock-admin-view">
        <div className="mock-step-indicator">營運摘要</div>
        <p>依台北時區顯示本週營運統計。</p>
        <div className="mock-placeholder-box">申請數 ｜ 成案數 ｜ 服務中 ｜ 待媒合 ｜ 客服案件 ｜ LINE 異常</div>
        <small>同時標示統計期間與資料產生時間。</small>
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
  const [filterRole, setFilterRole] = useState<'all' | LiffAudienceRole>(() => {
    const requested = liffHashParams().get('role');
    return requested === 'visitor' || requested === 'customer' || requested === 'staff' || requested === 'union_staff'
      ? requested
      : 'all';
  });
  const [searchQuery, setSearchQuery] = useState(() => liffHashParams().get('q') ?? '');
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfigState>({ status: 'loading' });
  const [expanded, setExpanded] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const dialogTitleId = useId();

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

  const normalizedSearch = searchQuery.trim().toLocaleLowerCase('zh-TW');
  const filteredItems = ASSET_ITEMS.filter((item) => (
    (filterRole === 'all' || item.audienceRoles.includes(filterRole))
    && (!normalizedSearch || [item.title, item.subtitle, item.displayTitle, item.purpose, item.group, item.description, item.badge]
      .some((value) => value.toLocaleLowerCase('zh-TW').includes(normalizedSearch)))
  ));
  const selectedItem = filteredItems.find((item) => item.id === selectedId) ?? filteredItems[0];
  const hasFilters = filterRole !== 'all' || searchQuery !== '';
  const clearFilters = () => { setSearchQuery(''); setFilterRole('all'); };

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!expanded || !dialog) return undefined;
    const previousOverflow = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = 'hidden';
    return () => {
      dialog.close();
      document.body.style.overflow = previousOverflow;
    };
  }, [expanded]);

  useEffect(() => {
    if (selectedItem && selectedItem.id !== selectedId) {
      setSelectedId(selectedItem.id);
    }
  }, [selectedItem, selectedId]);

  useEffect(() => {
    const route = window.location.hash.replace(/^#\/?/, '').split('?', 1)[0];
    if (route !== 'line-liff-studio' && route !== 'line-studio') return;
    const params = liffHashParams();
    const setParam = (key: string, value: string, fallback: string) => {
      if (value === fallback || value === '') params.delete(key);
      else params.set(key, value);
    };
    setParam('asset', selectedId, 'gateway');
    params.delete('type');
    setParam('role', filterRole, 'all');
    setParam('q', searchQuery, '');
    const query = params.toString();
    const nextHash = `#${route}${query ? `?${query}` : ''}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}${nextHash}`);
    }
  }, [filterRole, searchQuery, selectedId]);

  const visualPreview = selectedItem && (
    <div className="liff-studio-device" key={selectedItem.id}>
      <div className="liff-studio-device-brand">新竹市到宅月子工會</div>
      <div className="liff-studio-device-content">
        <div className="mock-liff-body">
          <h3 className="mock-liff-title">{selectedItem.displayTitle}</h3>
          <p className="mock-liff-desc">{selectedItem.purpose}</p>
          <LiffVisualPreview item={selectedItem} />
        </div>
      </div>
    </div>
  );

  return (
    <div className="liff-studio-container liff-studio-clean">
      <header className="line-hub-page-header liff-studio-page-header">
        <div className="line-hub-page-heading">
          <span className="line-hub-page-icon" aria-hidden="true"><PanelTop /></span>
          <div>
            <p className="line-hub-eyebrow">LINE 專區</p>
            <h1>LINE 表單</h1>
            <p>找到需要的功能，查看 LINE 上的使用畫面。</p>
          </div>
        </div>
      </header>
      <div className="liff-studio-workspace">
        <section className="liff-studio-sidebar" aria-label="表單清單">
          <div className="liff-sidebar-header">
            <label className="liff-search-field">
              <span className="sr-only">搜尋表單</span>
              <Search aria-hidden="true" />
              <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜尋名稱或用途" />
            </label>
            <label className="line-filter-field liff-role-filter">
              <span>使用對象</span>
              <select
                aria-label="依適用角色篩選表單"
                value={filterRole}
                onChange={(event) => setFilterRole(event.target.value as 'all' | LiffAudienceRole)}
              >
                <option value="all">全部對象</option>
                <option value="visitor">訪客／未綁定</option>
                <option value="customer">產婦／客戶</option>
                <option value="staff">月嫂</option>
                <option value="union_staff">工會人員</option>
              </select>
            </label>
          </div>
          <div className="liff-studio-result-line">
            <span role="status" aria-live="polite">{filteredItems.length} 個項目</span>
            {hasFilters && <button type="button" className="liff-studio-clear" onClick={clearFilters}>清除篩選</button>}
          </div>
          <div className="liff-asset-list">
            {filteredItems.length === 0 && (
              <div className="line-empty-state compact" role="status">
                <strong>找不到符合條件的表單</strong>
                <button type="button" className="line-secondary-btn" onClick={clearFilters}>清除條件</button>
              </div>
            )}
            {['身分與服務入口', '客戶服務', '月嫂服務', '工會工作'].map((group) => {
              const items = filteredItems.filter((item) => item.group === group);
              return items.length > 0 && (
                <div key={group} className="liff-studio-group">
                  <h2>{group}</h2>
                  {items.map((item) => (
                      <button
                        type="button"
                        key={item.id}
                        className={`liff-asset-card ${item.id === selectedItem?.id ? 'active' : ''}`}
                        aria-pressed={item.id === selectedItem?.id}
                        onClick={() => setSelectedId(item.id)}
                      >
                        <span className="liff-studio-row-icon" aria-hidden="true"><FileText /></span>
                        <span className="liff-studio-row-copy"><strong>{item.displayTitle}</strong><span>{item.purpose}</span></span>
                        <ChevronRight className="liff-studio-row-arrow" aria-hidden="true" />
                      </button>
                  ))}
                </div>
              );
            })}
          </div>
        </section>

        <section className="liff-studio-detail" aria-label="所選項目預覽">
          {selectedItem ? (
            <>
              <div className="liff-studio-detail-header">
                <div className="liff-studio-detail-heading">
                  <div className="liff-studio-title-row">
                    <h2>{selectedItem.displayTitle}</h2>
                    <span className="liff-studio-audience">{selectedItem.audienceRoles.map((role) => ({ visitor: '訪客／未綁定', customer: '產婦／客戶', staff: '月嫂', union_staff: '工會人員' }[role])).join('、')}</span>
                  </div>
                  <p>{selectedItem.purpose}</p>
                </div>
                <div className="liff-studio-detail-actions">
                  <button type="button" className="line-secondary-btn" onClick={() => setExpanded(true)}><Maximize2 aria-hidden="true" />放大預覽</button>
                  {selectedItem.launchPath && runtimeConfig.status === 'ready' && (
                    <a
                      className="line-primary-btn"
                      href={canonicalLiffUrl(selectedItem.previewPath ?? selectedItem.launchPath, runtimeConfig.origin)}
                      aria-label={selectedItem.previewPath ? '在預覽中開啟安全展示頁' : '在預覽中開啟正式 LIFF 入口'}
                      target="_blank"
                      rel="noreferrer"
                    >{selectedItem.previewPath ? '開啟安全預覽' : '開啟正式 LIFF 入口'}</a>
                  )}
                </div>
              </div>
              <div className="liff-studio-preview-stage">
                <div className="liff-studio-stage-caption">
                  <span><Smartphone aria-hidden="true" />LINE 服務畫面</span>
                  <span>流程示意</span>
                </div>
                {selectedItem.launchPath && runtimeConfig.status !== 'ready' && (
                  <div className="line-warning liff-preview-warning" role="status">
                    {runtimeConfig.status === 'loading'
                      ? '正在取得正式 LIFF 測試網址…'
                      : '目前無法取得服務入口，請稍後再試。'}
                  </div>
                )}
                {!selectedItem.launchPath && (
                  <div className="line-warning liff-preview-warning" role="status">
                    {selectedItem.launchNote ?? '入口與正式服務尚待建立；設計與功能需求保留，不導向不存在的頁面。'}
                  </div>
                )}
                {visualPreview}
              </div>
              <dialog ref={dialogRef} className="liff-studio-dialog" aria-labelledby={dialogTitleId} onCancel={() => setExpanded(false)} onClose={() => setExpanded(false)}>
                <div className="liff-studio-dialog-header">
                  <h2 id={dialogTitleId}>{selectedItem.displayTitle}</h2>
                  <button type="button" className="liff-studio-dialog-close" aria-label="關閉放大預覽" onClick={() => setExpanded(false)}><X aria-hidden="true" /></button>
                </div>
                {expanded && visualPreview}
              </dialog>
            </>
          ) : (
            <div className="liff-studio-detail-empty" role="status"><Search aria-hidden="true" /><strong>找不到符合條件的內容</strong><p>調整搜尋或使用對象後，再查看預覽。</p></div>
          )}
          <NonCitizenLiffSettingsPanel active={selectedItem?.id === 'non_citizen_registration'} />
        </section>
      </div>
    </div>
  );
};
