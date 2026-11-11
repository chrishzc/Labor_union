/**
 * File: LiffCardStudio.tsx
 * Description: 依用途呈現 LIFF 表單預覽，支援同源前綴互動預覽並保留正式入口。
 */
import React, { useEffect, useId, useRef, useState } from 'react';
import { CheckSquare, ChevronRight, FileText, Maximize2, PanelTop, Search, Smartphone, X } from 'lucide-react';
import { applicationUrl } from '../../api/shared/application_fetch';
import {
  lineIdentityRuntimeConfigClient,
  type LineIdentityRuntimeConfigClient,
} from '../../api/line_identity/line_identity_runtime_config_client';
import '../LineManagementPage.css';
import './LiffCardStudio.css';

import {
  ASSET_ITEMS,
  type LiffAssetItem,
  type LiffAssetType,
  type LiffAudienceRole,
} from '../../adapters/line_configuration/liff_target_catalog';

export type { LiffAssetItem, LiffAssetType, LiffAudienceRole };
export { ASSET_ITEMS };

function canonicalLiffUrl(path: string, origin: string): string {
  return new URL(path, origin).toString();
}

function liffHashParams(): URLSearchParams {
  return new URLSearchParams(window.location.hash.split('?', 2)[1] ?? '');
}

function LiffVisualPreview({ item }: { item: LiffAssetItem }) {
  if (item.id === 'bind') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">服務綁定與訂單查詢</div>
        <p>請填寫基本資料，以完成 LINE 帳號與最新訂單的綁定：</p>
        <label>您的真實姓名</label>
        <input type="text" placeholder="請輸入姓名" readOnly />
        <label>聯絡電話</label>
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
        <label>身分證字號（選填）</label><input type="text" placeholder="例如：A123456789" readOnly />
        <label>行動電話 *</label><input type="text" placeholder="例如：0912345678" readOnly />
        <label>服務地址 *</label><input type="text" placeholder="請填寫完整地址（含巷弄樓層）" readOnly />
        <strong>2. 照護與環境</strong>
        <label>預產期（或已生產日期） *</label><input type="date" readOnly />
        <label>預計服務天數 *</label><input type="number" readOnly />
        <fieldset><legend>胎數</legend>
          <label><input type="radio" disabled /> 單胞胎</label>
          <label><input type="radio" disabled /> 雙胞胎</label>
        </fieldset>
        <strong>3. 飲食偏好</strong>
        <label><input type="radio" disabled /> 葷食</label>
        <label><input type="radio" disabled /> 素食</label>
        <strong>4. 居家設備與環境</strong>
        <label><input type="checkbox" disabled /> 大同電鍋</label>
        <label><input type="checkbox" disabled /> 奶瓶消毒鍋</label>
        <strong>5. 費用與同意條款</strong>
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


  if (item.id === 'staff_payout') {
    return (
      <div className="mock-form-inputs">
        <div className="mock-step-indicator">薪資請款明細</div>
        <label>預計付款月份</label><input type="month" readOnly />
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
  /** 是否內嵌於其他頁籤工作區中；若為 true 則省略頂層重複的頁面 Header。 */
  embedded?: boolean;
}

type RuntimeConfigState =
  | { status: 'loading' }
  | { status: 'ready'; origin: string }
  | { status: 'failed'; message: string };

export const LiffCardStudio: React.FC<LiffCardStudioProps> = ({
  runtimeConfigClient = lineIdentityRuntimeConfigClient,
  embedded = false,
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
    const isInterface = route === 'line-interface';
    if (!isInterface && route !== 'line-liff-studio' && route !== 'line-studio') return;
    const params = liffHashParams();
    const setParam = (key: string, value: string, fallback: string) => {
      if (value === fallback || value === '') params.delete(key);
      else params.set(key, value);
    };
    if (isInterface) {
      params.set('tab', 'liff');
    }
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

  const gatewayPreview = selectedItem?.id === 'gateway';
  const registrationPreview = selectedItem?.id === 'non_citizen_registration';
  const visualPreview = gatewayPreview || registrationPreview ? (
    <iframe
      className="liff-studio-device liff-studio-gateway-preview"
      src={applicationUrl(
        gatewayPreview
          ? '/api/v1/line/identity/studio-preview/gateway?studio_preview=1'
          : '/api/v1/line/identity/studio-preview/non-citizen-registration?studio_preview=1',
      )}
      title={gatewayPreview ? '服務申請導流互動預覽' : '非市民服務申請互動預覽'}
      referrerPolicy="no-referrer"
      sandbox="allow-scripts allow-same-origin"
    />
  ) : selectedItem && (
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
      {!embedded && (
        <header className="line-hub-page-header liff-studio-page-header">
          <div className="line-hub-page-heading">
            <span className="line-hub-page-icon" aria-hidden="true"><PanelTop /></span>
            <div>
              <p className="line-hub-eyebrow">LINE 專區</p>
              <h1>LINE 表單</h1>
            </div>
          </div>
        </header>
      )}
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
        </section>
      </div>
    </div>
  );
};
