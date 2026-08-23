/**
 * File: LineManagementPage.tsx
 * Description: 以四組 typed GET 呈現 LINE 六頁籤查詢；未開放能力明確鎖定且不觸發副作用。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  adaptCustomerServiceDetail,
  adaptCustomerServicePage,
  adaptCustomerServiceSummary,
  CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE,
  type CustomerServiceDetailModel,
  type CustomerServicePageModel,
  type CustomerServiceSummaryModel,
} from '../adapters/customer_service/customer_service_adapter';
import {
  adaptLineIdentityBinding,
  adaptLineIdentityBindingPage,
  type LineIdentityBindingRowViewModel,
} from '../adapters/line_identity/line_identity_adapter';
import {
  adaptLineNotificationRulesCatalog,
  adaptLineRichMenuConfiguration,
  adaptLineRichMenuPublication,
  adaptLineRichMenuPublicationPage,
  type LineNotificationRuleModel,
  type LineNotificationRulesCatalogModel,
  type LineRichMenuConfigurationModel,
  type LineRichMenuPublicationModel,
  type LineRichMenuPublicationPageModel,
} from '../adapters/line_configuration/line_configuration_query_adapter';
import {
  customerServiceClient,
  type CustomerServiceClient,
} from '../api/customer_service/customer_service_client';
import { CustomerServiceClientError } from '../api/customer_service/customer_service_errors';
import {
  lineIdentityClient,
  type LineIdentityClient,
} from '../api/line_identity/line_identity_client';
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';
import {
  lineConfigurationQueryClient,
  type LineConfigurationQueryClient,
} from '../api/line_configuration/line_configuration_query_client';
import { LineConfigurationQueryError } from '../api/line_configuration/line_configuration_query_errors';
import { Drawer } from '../components/Drawer';
import './LineManagementPage.css';

type LineTab = 'tickets' | 'richmenu' | 'binding' | 'push_queue' | 'faq' | 'order_groups';

type CustomerServiceQueryClient = Pick<
  CustomerServiceClient,
  'getSummary' | 'listTickets' | 'getTicketDetail'
>;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

interface LineManagementPageProps {
  customerService?: CustomerServiceQueryClient;
  lineIdentity?: LineIdentityQueryClient;
  lineConfiguration?: LineConfigurationQueryClient;
}

type QueryStatus = 'idle' | 'loading' | 'loaded' | 'error';

interface QueryState<T> {
  status: QueryStatus;
  value: T | null;
  error: string | null;
}

function idleState<T>(): QueryState<T> {
  return { status: 'idle', value: null, error: null };
}

function loadingState<T>(): QueryState<T> {
  return { status: 'loading', value: null, error: null };
}

function loadedState<T>(value: T): QueryState<T> {
  return { status: 'loaded', value, error: null };
}

function errorState<T>(error: string): QueryState<T> {
  return { status: 'error', value: null, error };
}

function displayQueryError(error: unknown, fallback: string): string {
  if (error instanceof CustomerServiceClientError) return `${error.code}：${error.message}`;
  if (error instanceof LineIdentityClientError) return `${error.code}：${error.message}`;
  if (error instanceof LineConfigurationQueryError) return `${error.code}：${error.message}`;
  return fallback;
}

const TABS: ReadonlyArray<readonly [LineTab, string, string]> = [
  ['tickets', '📋 1. 客服工單與案件追蹤', 'line.tab.tickets'],
  ['richmenu', '📱 2. 多角色 Rich Menu 圖文選單', 'line.tab.richmenu'],
  ['binding', '🔑 3. LINE 身分綁定與授權', 'line.tab.binding'],
  ['push_queue', '🔔 4. 通知規則目錄', 'line.tab.push-queue'],
  ['faq', '🧠 5. 智慧客服 FAQ 知識庫', 'line.tab.faq'],
  ['order_groups', '👥 6. 三方服務群組', 'line.tab.order-groups'],
];

const unavailableText = '後端 typed query 尚未納入本頁工作包。';

function UnavailableSurface({ controlId, title, description }: { controlId: string; title: string; description: string }) {
  return (
    <div className="line-unavailable" data-control-id={controlId}>
      <span className="line-unavailable-icon" aria-hidden="true">⏸</span>
      <div><h4>{title}</h4><p>{description}</p></div>
    </div>
  );
}

function LoadingOrError({ state, loadingText }: { state: QueryState<unknown>; loadingText: string }) {
  if (state.status === 'loading') return <div className="line-loading">{loadingText}</div>;
  if (state.status === 'error') return <div className="line-error" role="alert">{state.error}</div>;
  return null;
}

export const LineManagementPage: React.FC<LineManagementPageProps> = ({
  customerService = customerServiceClient,
  lineIdentity = lineIdentityClient,
  lineConfiguration = lineConfigurationQueryClient,
}) => {
  const [activeTab, setActiveTab] = useState<LineTab>('tickets');
  const [ticketSummary, setTicketSummary] = useState<QueryState<CustomerServiceSummaryModel>>(idleState);
  const [ticketPage, setTicketPage] = useState<QueryState<CustomerServicePageModel>>(idleState);
  const [ticketReload, setTicketReload] = useState(0);
  const [ticketDetail, setTicketDetail] = useState<QueryState<CustomerServiceDetailModel>>(idleState);
  const ticketDetailController = useRef<AbortController | null>(null);
  const ticketDetailGeneration = useRef(0);
  const ticketDetailId = useRef<number | null>(null);

  const [bindingPage, setBindingPage] = useState<QueryState<{ items: LineIdentityBindingRowViewModel[]; total: number; page: number; pageSize: number }>>(idleState);
  const [bindingSources, setBindingSources] = useState<readonly string[]>([]);
  const [bindingReload, setBindingReload] = useState(0);
  const [bindingDetail, setBindingDetail] = useState<QueryState<LineIdentityBindingRowViewModel>>(idleState);
  const bindingDetailController = useRef<AbortController | null>(null);
  const bindingDetailGeneration = useRef(0);
  const bindingDetailId = useRef<string | null>(null);

  const [rules, setRules] = useState<QueryState<LineNotificationRulesCatalogModel>>(idleState);
  const [rulesReload, setRulesReload] = useState(0);
  const [selectedRule, setSelectedRule] = useState<LineNotificationRuleModel | null>(null);

  const [richMenuConfiguration, setRichMenuConfiguration] = useState<QueryState<LineRichMenuConfigurationModel>>(idleState);
  const [richMenuPublications, setRichMenuPublications] = useState<QueryState<LineRichMenuPublicationPageModel>>(idleState);
  const [richMenuReload, setRichMenuReload] = useState(0);
  const [selectedMenuId, setSelectedMenuId] = useState<string | null>(null);
  const [selectedPublication, setSelectedPublication] = useState<QueryState<LineRichMenuPublicationModel>>(idleState);
  const publicationController = useRef<AbortController | null>(null);
  const publicationGeneration = useRef(0);
  const publicationDetailId = useRef<number | null>(null);

  useEffect(() => {
    if (activeTab !== 'tickets') return;
    const controller = new AbortController();
    let cancelled = false;
    setTicketSummary(loadingState());
    setTicketPage(loadingState());
    const timer = window.setTimeout(() => {
      void Promise.allSettled([
        customerService.getSummary({ signal: controller.signal }),
        customerService.listTickets({ page: 1, page_size: 100 }, { signal: controller.signal }),
      ]).then(([summaryResult, pageResult]) => {
        if (cancelled) return;
        if (summaryResult.status === 'fulfilled') setTicketSummary(loadedState(adaptCustomerServiceSummary(summaryResult.value)));
        else setTicketSummary(errorState(displayQueryError(summaryResult.reason, '客服摘要載入失敗')));
        if (pageResult.status === 'fulfilled') setTicketPage(loadedState(adaptCustomerServicePage(pageResult.value)));
        else setTicketPage(errorState(displayQueryError(pageResult.reason, '客服工單清單載入失敗')));
      });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, customerService, ticketReload]);

  useEffect(() => {
    if (activeTab !== 'binding') return;
    const controller = new AbortController();
    let cancelled = false;
    setBindingPage(loadingState());
    const timer = window.setTimeout(() => {
      void lineIdentity.listBindings({ page: 1, page_size: 100 }, { signal: controller.signal })
        .then((page) => {
          if (cancelled) return;
          setBindingSources(page.items.map((item) => item.line_user_id));
          setBindingPage(loadedState({ items: adaptLineIdentityBindingPage(page).items, total: page.total, page: page.page, pageSize: page.page_size }));
        })
        .catch((error: unknown) => { if (!cancelled) setBindingPage(errorState(displayQueryError(error, 'LINE 身分清單載入失敗'))); });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, bindingReload, lineIdentity]);

  useEffect(() => {
    if (activeTab !== 'push_queue') return;
    const controller = new AbortController();
    let cancelled = false;
    setRules(loadingState());
    const timer = window.setTimeout(() => {
      void lineConfiguration.getNotificationRules({ signal: controller.signal })
        .then((catalog) => { if (!cancelled) setRules(loadedState(adaptLineNotificationRulesCatalog(catalog))); })
        .catch((error: unknown) => { if (!cancelled) setRules(errorState(displayQueryError(error, '通知規則目錄載入失敗'))); });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, lineConfiguration, rulesReload]);

  useEffect(() => {
    if (activeTab !== 'richmenu') return;
    const controller = new AbortController();
    let cancelled = false;
    setRichMenuConfiguration(loadingState());
    setRichMenuPublications(loadingState());
    const timer = window.setTimeout(() => {
      void Promise.allSettled([
        lineConfiguration.getRichMenuConfiguration({ signal: controller.signal }),
        lineConfiguration.listRichMenuPublications({ signal: controller.signal }),
      ]).then(([configurationResult, publicationResult]) => {
        if (cancelled) return;
        if (configurationResult.status === 'fulfilled') {
          const nextConfiguration = adaptLineRichMenuConfiguration(configurationResult.value);
          setRichMenuConfiguration(loadedState(nextConfiguration));
          setSelectedMenuId((current) => current ?? nextConfiguration.menus[0]?.id ?? null);
        } else setRichMenuConfiguration(errorState(displayQueryError(configurationResult.reason, 'Rich Menu 設定載入失敗')));
        if (publicationResult.status === 'fulfilled') setRichMenuPublications(loadedState(adaptLineRichMenuPublicationPage(publicationResult.value)));
        else setRichMenuPublications(errorState(displayQueryError(publicationResult.reason, 'Rich Menu 發布紀錄載入失敗')));
      });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, lineConfiguration, richMenuReload]);

  useEffect(() => {
    if (activeTab !== 'tickets') {
      ticketDetailController.current?.abort();
      ticketDetailController.current = null;
      ticketDetailGeneration.current += 1;
      ticketDetailId.current = null;
      setTicketDetail(idleState());
    }
    if (activeTab !== 'binding') {
      bindingDetailController.current?.abort();
      bindingDetailController.current = null;
      bindingDetailGeneration.current += 1;
      bindingDetailId.current = null;
      setBindingDetail(idleState());
    }
    if (activeTab !== 'richmenu') {
      publicationController.current?.abort();
      publicationController.current = null;
      publicationGeneration.current += 1;
      publicationDetailId.current = null;
      setSelectedPublication(idleState());
    }
  }, [activeTab]);

  useEffect(() => () => {
    ticketDetailController.current?.abort();
    bindingDetailController.current?.abort();
    publicationController.current?.abort();
    ticketDetailGeneration.current += 1;
    bindingDetailGeneration.current += 1;
    publicationGeneration.current += 1;
  }, []);

  const openTicket = (ticketId: number) => {
    ticketDetailController.current?.abort();
    const controller = new AbortController();
    ticketDetailController.current = controller;
    ticketDetailId.current = ticketId;
    const generation = ticketDetailGeneration.current + 1;
    ticketDetailGeneration.current = generation;
    setTicketDetail(loadingState());
    void customerService.getTicketDetail(ticketId, { signal: controller.signal })
      .then((detail) => { if (!controller.signal.aborted && generation === ticketDetailGeneration.current) setTicketDetail(loadedState(adaptCustomerServiceDetail(detail))); })
      .catch((error: unknown) => { if (!controller.signal.aborted && generation === ticketDetailGeneration.current) setTicketDetail(errorState(displayQueryError(error, '客服工單明細載入失敗'))); });
  };

  const closeTicket = () => {
    ticketDetailController.current?.abort();
    ticketDetailController.current = null;
    ticketDetailGeneration.current += 1;
    ticketDetailId.current = null;
    setTicketDetail(idleState());
  };

  const openBinding = (lineUserId: string) => {
    bindingDetailController.current?.abort();
    const controller = new AbortController();
    bindingDetailController.current = controller;
    bindingDetailId.current = lineUserId;
    const generation = bindingDetailGeneration.current + 1;
    bindingDetailGeneration.current = generation;
    setBindingDetail(loadingState());
    void lineIdentity.getBinding(lineUserId, { signal: controller.signal })
      .then((binding) => { if (!controller.signal.aborted && generation === bindingDetailGeneration.current) setBindingDetail(loadedState(adaptLineIdentityBinding(binding))); })
      .catch((error: unknown) => { if (!controller.signal.aborted && generation === bindingDetailGeneration.current) setBindingDetail(errorState(displayQueryError(error, 'LINE 身分明細載入失敗'))); });
  };

  const closeBinding = () => {
    bindingDetailController.current?.abort();
    bindingDetailController.current = null;
    bindingDetailGeneration.current += 1;
    bindingDetailId.current = null;
    setBindingDetail(idleState());
  };

  const openPublication = (publicationId: number) => {
    publicationController.current?.abort();
    const controller = new AbortController();
    publicationController.current = controller;
    publicationDetailId.current = publicationId;
    const generation = publicationGeneration.current + 1;
    publicationGeneration.current = generation;
    setSelectedPublication(loadingState());
    void lineConfiguration.getRichMenuPublication(publicationId, { signal: controller.signal })
      .then((publication) => { if (!controller.signal.aborted && generation === publicationGeneration.current) setSelectedPublication(loadedState(adaptLineRichMenuPublication(publication))); })
      .catch((error: unknown) => { if (!controller.signal.aborted && generation === publicationGeneration.current) setSelectedPublication(errorState(displayQueryError(error, 'Rich Menu 發布明細載入失敗'))); });
  };

  const closePublication = () => {
    publicationController.current?.abort();
    publicationController.current = null;
    publicationGeneration.current += 1;
    publicationDetailId.current = null;
    setSelectedPublication(idleState());
  };

  const selectedMenu = richMenuConfiguration.value?.menus.find((menu) => menu.id === selectedMenuId) ?? null;

  return (
    <div className="line-page-wrapper" data-control-id="line.page">
      <div className="page-header-banner line-page-header"><div><h1 className="page-title">💬 LINE 官方帳號與推播管理中心</h1><p className="page-subtitle">客服工單、身分綁定、Rich Menu、通知規則、FAQ 與三方群組查詢工作區。</p></div><span className="line-query-badge">唯讀查詢模式</span></div>
      <div className="line-tab-bar" aria-label="LINE 管理工作區">{TABS.map(([tab, label, id]) => <button key={tab} type="button" data-control-id={id} className={`line-tab-btn ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>{label}</button>)}</div>

      {activeTab === 'tickets' && <section className="line-table-container"><div className="line-section-heading"><div><h3>📋 客服工單與案件關聯追蹤清單</h3><p>資料來自 Customer Service typed API；未提供欄位不由前端補算。</p></div><button type="button" className="line-secondary-btn" onClick={() => setTicketReload((value) => value + 1)}>重新整理</button></div><div className="line-kpi-grid"><div data-control-id="line.ticket.summary.waiting"><span>待處理</span><strong>{ticketSummary.value?.waiting ?? '—'}</strong></div><div data-control-id="line.ticket.summary.handling"><span>處理中</span><strong>{ticketSummary.value?.handling ?? '—'}</strong></div><div data-control-id="line.ticket.summary.resolved_today"><span>今日結案</span><strong>{ticketSummary.value?.resolvedToday ?? '—'}</strong></div></div>{ticketSummary.status === 'loading' && <div className="line-loading">正在載入客服摘要…</div>}{ticketSummary.status === 'error' && <div className="line-error" role="alert">{ticketSummary.error}</div>}{ticketPage.status === 'loading' && <div className="line-loading">正在載入客服工單…</div>}{ticketPage.status === 'error' && <div className="line-error" role="alert">{ticketPage.error}</div>}{ticketPage.status === 'loaded' && ticketPage.value && (ticketPage.value.items.length === 0 ? <div className="line-empty-state"><div>📋</div><h4>目前 loaded scope 沒有客服工單</h4><p>伺服器回傳的第 {ticketPage.value.page} 頁為空。</p></div> : <><div className="line-scope-note">目前顯示 loaded scope：第 {ticketPage.value.page} 頁，共載入 {ticketPage.value.items.length} 筆；伺服器總數 {ticketPage.value.total}。</div><div className="line-table-scroll"><table className="line-data-table" data-control-id="line.ticket.table"><thead><tr><th>工單編號</th><th>提問對象</th><th>關聯案件</th><th>分類</th><th>問題摘要</th><th>時間</th><th>狀態</th><th>操作</th></tr></thead><tbody>{ticketPage.value.items.map((ticket) => <tr key={ticket.ticketId}><td><strong>#{ticket.ticketIdText}</strong></td><td>👤 {ticket.maskedLineUserId}</td><td>{ticket.caseNo ?? '無關聯'}</td><td>{ticket.categoryLabel}</td><td>{ticket.issueSummary ?? CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE}</td><td>{ticket.createdAt ?? '—'}</td><td><span className={`line-status line-status-${ticket.status}`}>{ticket.statusLabel}</span></td><td><div className="line-row-actions"><button type="button" data-control-id="line.ticket.open" disabled>開啟 LINE</button><button type="button" data-control-id="line.ticket.detail" onClick={() => openTicket(ticket.ticketId)}>查看明細</button></div></td></tr>)}</tbody></table></div></>)}</section>}

      {activeTab === 'richmenu' && <section className="line-workspace-card" data-control-id="line.richmenu.configuration"><div className="line-section-heading"><div><h3>📱 多角色 Rich Menu 圖文選單查詢</h3><p>只顯示 server configuration 與 loaded publication history；provider 動作不進入本頁。</p></div><div className="line-row-actions"><button type="button" className="line-secondary-btn" data-control-id="line.richmenu.refresh" onClick={() => setRichMenuReload((value) => value + 1)}>重新整理</button><button type="button" data-control-id="line.richmenu.publish" disabled>🚀 發布至 LINE 官方帳號</button><button type="button" data-control-id="line.richmenu.upload" disabled>上傳圖片</button><button type="button" data-control-id="line.richmenu.delete" disabled>刪除選單</button></div></div><LoadingOrError state={richMenuConfiguration} loadingText="正在載入 Rich Menu 設定…" />{richMenuConfiguration.status === 'loaded' && richMenuConfiguration.value?.isEmpty && <div className="line-empty-state"><div>📱</div><h4>目前尚未設定 Rich Menu</h4><p>此為伺服器回傳的空設定，不套用前端預設選單。</p></div>}{richMenuConfiguration.status === 'loaded' && richMenuConfiguration.value && !richMenuConfiguration.value.isEmpty && <><div className="line-role-switcher">{richMenuConfiguration.value.menus.map((menu) => <button key={menu.id} type="button" className={selectedMenu?.id === menu.id ? 'active' : ''} onClick={() => setSelectedMenuId(menu.id)}>{menu.audienceRoleLabel}｜{menu.name}</button>)}</div>{selectedMenu && <div className="line-phone-preview"><div className="line-phone-header">{selectedMenu.name}</div><div className="line-phone-message">{selectedMenu.chatBarText}</div><div className="line-menu-grid">{selectedMenu.buttons.map((button) => <div key={button.id}>{button.label}</div>)}</div></div>}</>}{richMenuPublications.status === 'loading' && <div className="line-loading">正在載入 Rich Menu 發布紀錄…</div>}{richMenuPublications.status === 'error' && <div className="line-error" role="alert">{richMenuPublications.error}</div>}{richMenuPublications.status === 'loaded' && richMenuPublications.value && <div className="line-publication-history" data-control-id="line.richmenu.publications"><h4>已載入發布紀錄</h4><p>僅顯示本次 loaded scope（最多 100 筆），不代表完整歷史總數。</p>{richMenuPublications.value.items.length ? <div className="line-table-scroll"><table className="line-data-table"><thead><tr><th>ID</th><th>選單</th><th>設定版本</th><th>狀態</th><th>操作</th></tr></thead><tbody>{richMenuPublications.value.items.map((publication) => <tr key={publication.id}><td>{publication.id}</td><td>{publication.menuDefinitionId}</td><td>{publication.configurationRevision}</td><td>{publication.statusLabel}</td><td><button type="button" data-control-id="line.richmenu.publication-detail" onClick={() => openPublication(publication.id)}>查看</button></td></tr>)}</tbody></table></div> : <div className="line-empty-state"><h4>此 loaded scope 沒有發布紀錄</h4></div>}</div>}</section>}

      {activeTab === 'binding' && <section className="line-workspace-card"><div className="line-section-heading"><div><h3>🔑 LINE 身分綁定查詢</h3><p>只呈現遮罩 LINE user id、subject、status 與 server version；解除流程不在本頁。</p></div><div className="line-row-actions"><button type="button" data-control-id="line.identity.invite" disabled>+ 產生綁定邀請連結</button><button type="button" className="line-secondary-btn" onClick={() => setBindingReload((value) => value + 1)}>重新整理</button></div></div><LoadingOrError state={bindingPage} loadingText="正在載入身分綁定…" />{bindingPage.status === 'loaded' && bindingPage.value && (bindingPage.value.items.length === 0 ? <div className="line-empty-state"><div>🔑</div><h4>目前 loaded scope 沒有身分綁定</h4><p>伺服器總數：{bindingPage.value.total}。</p></div> : <><div className="line-scope-note">目前顯示 loaded scope：第 {bindingPage.value.page} 頁，共載入 {bindingPage.value.items.length} 筆；伺服器總數 {bindingPage.value.total}。</div><div className="line-table-scroll"><table className="line-data-table" data-control-id="line.identity.table"><thead><tr><th>LINE User ID</th><th>實名姓名</th><th>角色</th><th>更新時間</th><th>狀態</th><th>解除狀態</th><th>操作</th></tr></thead><tbody>{bindingPage.value.items.map((record, index) => <tr key={`${record.maskedLineUserId}-${record.version}`}><td><code>{record.maskedLineUserId}</code></td><td>👤 {record.subjectName}</td><td>{record.subjectTypeLabel}</td><td>{record.updatedAt ?? '—'}</td><td>{record.statusLabel}</td><td>{record.revocationStatusLabel}</td><td><button type="button" data-control-id="line.identity.detail" onClick={() => openBinding(bindingSources[index] ?? '')}>查看明細</button></td></tr>)}</tbody></table></div></>)}</section>}

      {activeTab === 'push_queue' && <section className="line-workspace-card"><div className="line-section-heading"><div><h3>🔔 通知規則目錄</h3><p>只查詢 server current revision；本頁不含 delivery queue 與任何發送副作用。</p></div><div className="line-row-actions"><button type="button" className="line-secondary-btn" data-control-id="line.notification-rules.refresh" onClick={() => setRulesReload((value) => value + 1)}>重新整理</button><button type="button" data-control-id="line.notification-rule.create" disabled>+ 建立新通知規則</button></div></div><LoadingOrError state={rules} loadingText="正在載入通知規則目錄…" />{rules.status === 'loaded' && rules.value?.isEmpty && <div className="line-empty-state" data-control-id="line.notification-rules.empty"><div>🔔</div><h4>目前尚未設定通知規則</h4><p>Current revision：{rules.value.revision}。未使用前端預設規則。</p></div>}{rules.status === 'loaded' && rules.value && !rules.value.isEmpty && <div className="line-rule-list" data-control-id="line.notification-rules.list">{rules.value.rules.map((rule) => <button key={rule.id} type="button" className="line-rule-card" onClick={() => setSelectedRule(rule)}><span>{rule.eventLabel}｜{rule.recipientLabel}</span><strong>{rule.id}</strong><small>{rule.scheduleLabel}｜{rule.frequencyLabel}｜{rule.enabled ? '已啟用' : '未啟用'}</small></button>)}</div>}<div className="line-unavailable-panel"><UnavailableSurface controlId="line.delivery.unavailable" title="Delivery 任務查詢未開放" description={unavailableText} /><div className="line-locked-actions"><button type="button" data-control-id="line.delivery.retry" disabled>重試發送</button><button type="button" data-control-id="line.delivery.replay" disabled>重播</button><button type="button" data-control-id="line.delivery.cancel" disabled>取消任務</button><button type="button" data-control-id="line.delivery.run-now" disabled>立即執行</button></div></div></section>}

      {activeTab === 'faq' && <section className="line-workspace-card"><div className="line-section-heading"><div><h3>🧠 智慧客服 FAQ 知識庫</h3><p>Knowledge typed query 尚未納入本頁工作包。</p></div><button type="button" data-control-id="line.faq.create" disabled>+ 新增 FAQ 詞條</button></div><UnavailableSurface controlId="line.faq.unavailable" title="FAQ 查詢 unavailable" description={unavailableText} /><div className="line-locked-actions"><button type="button" data-control-id="line.faq.save" disabled>儲存</button><button type="button" data-control-id="line.faq.publish" disabled>發布</button><button type="button" data-control-id="line.faq.retire" disabled>退役</button><button type="button" data-control-id="line.faq.reindex" disabled>重建索引</button></div></section>}

      {activeTab === 'order_groups' && <section className="line-table-container"><div className="line-section-heading"><div><h3>👥 三方服務群組查詢</h3><p>Order Groups typed query 尚未納入本頁工作包。</p></div><button type="button" data-control-id="line.order-group.create" disabled>+ 建立三方群組</button></div><UnavailableSurface controlId="line.order-groups.unavailable" title="Order Groups 查詢 unavailable" description={unavailableText} /><div className="line-locked-actions"><button type="button" data-control-id="line.order-group.bind" disabled>綁定成員</button><button type="button" data-control-id="line.order-group.unbind" disabled>解除成員</button><button type="button" data-control-id="line.order-group.replay" disabled>重播</button></div></section>}

      <Drawer isOpen={ticketDetail.status !== 'idle'} onClose={closeTicket} title="客服工單明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeTicket}>關閉</button>{ticketDetail.status === 'error' && ticketDetailId.current !== null && <button type="button" onClick={() => openTicket(ticketDetailId.current!)}>重試查詢</button>}<button type="button" data-control-id="line.ticket.resolve.preview" disabled>預覽結案（未開放）</button><button type="button" data-control-id="line.ticket.resolve.apply" disabled>確認結案（未開放）</button><button type="button" data-control-id="line.ticket.resolve.retry" disabled>重試結案（未開放）</button></div>}><div data-control-id="line.ticket.detail" className="line-drawer-content"><LoadingOrError state={ticketDetail} loadingText="正在載入工單明細…" />{ticketDetail.status === 'loaded' && ticketDetail.value && <><div className="line-detail-grid"><div><span>客戶</span><strong>{ticketDetail.value.ticket.maskedLineUserId}</strong></div><div><span>案件</span><strong>{ticketDetail.value.ticket.caseNo ?? '無關聯'}</strong></div><div><span>狀態</span><strong>{ticketDetail.value.ticket.statusLabel}</strong></div><div><span>版本</span><strong>{ticketDetail.value.ticket.version}</strong></div></div><UnavailableSurface controlId="line.ticket.resolve.unavailable" title="客服結案 mutation 未開放" description="本頁僅呈現 typed detail；resolve Preview／Apply 由後續 mutation 工作包負責。" /><div className="line-locked-actions"><button type="button" data-control-id="line.ticket.update" disabled>更新工單</button><button type="button" data-control-id="line.ticket.reply" disabled>回覆客戶</button></div><div className="line-events"><h4>事件紀錄</h4>{ticketDetail.value.events.length === 0 ? <p>尚無事件紀錄</p> : ticketDetail.value.events.map((event) => <article key={event.id}><strong>{event.eventType}</strong><span>{event.createdAt}</span><p>{event.messageText ?? '無訊息內容'}</p></article>)}</div></>}</div></Drawer>

      <Drawer isOpen={bindingDetail.status !== 'idle'} onClose={closeBinding} title="LINE 身分綁定明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeBinding}>關閉</button>{bindingDetail.status === 'error' && bindingDetailId.current !== null && <button type="button" onClick={() => openBinding(bindingDetailId.current!)}>重試查詢</button>}<button type="button" data-control-id="line.identity.revocation.preview" disabled>預覽解除（未開放）</button><button type="button" data-control-id="line.identity.revocation.apply" disabled>提交解除（未開放）</button><button type="button" data-control-id="line.identity.revocation.observe" disabled>觀察解除（未開放）</button></div>}><div data-control-id="line.identity.detail" className="line-drawer-content"><LoadingOrError state={bindingDetail} loadingText="正在載入身分綁定明細…" />{bindingDetail.status === 'loaded' && bindingDetail.value && <><div className="line-detail-grid"><div><span>LINE User ID</span><strong>{bindingDetail.value.maskedLineUserId}</strong></div><div><span>實名姓名</span><strong>{bindingDetail.value.subjectName}</strong></div><div><span>角色</span><strong>{bindingDetail.value.subjectTypeLabel}</strong></div><div><span>狀態／版本</span><strong>{bindingDetail.value.statusLabel}／{bindingDetail.value.version}</strong></div><div><span>更新時間</span><strong>{bindingDetail.value.updatedAt ?? '—'}</strong></div><div><span>解除狀態</span><strong>{bindingDetail.value.revocationStatusLabel}</strong></div></div><UnavailableSurface controlId="line.identity.revocation.unavailable" title="身分解除 mutation 未開放" description="本頁僅呈現 typed binding detail；revocation Preview／Apply 不在 query slice。" /><div className="line-locked-actions"><button type="button" data-control-id="line.identity.replacement" disabled>改綁其他身分</button><button type="button" data-control-id="line.identity.retry" disabled>重試 Rich Menu 回復</button><button type="button" data-control-id="line.identity.manual-complete" disabled>人工完成</button></div></>}</div></Drawer>

      <Drawer isOpen={selectedRule !== null} onClose={() => setSelectedRule(null)} title={`通知規則（查詢模式）${selectedRule ? `－${selectedRule.id}` : ''}`} footer={<div className="line-drawer-footer"><button type="button" onClick={() => setSelectedRule(null)}>關閉</button><button type="button" data-control-id="line.notification-rule.save" disabled>儲存並發布</button><button type="button" data-control-id="line.notification-rule.delete" disabled>刪除</button><button type="button" data-control-id="line.notification-rule.replay" disabled>手動重播</button></div>}>{selectedRule && <div className="line-drawer-content" data-control-id="line.notification-rule.detail"><div className="line-detail-grid"><div><span>事件</span><strong>{selectedRule.eventLabel}</strong></div><div><span>收件人</span><strong>{selectedRule.recipientLabel}</strong></div><div><span>模板</span><strong>{selectedRule.templateId}</strong></div><div><span>狀態</span><strong>{selectedRule.enabled ? '已啟用' : '未啟用'}</strong></div></div><p>{selectedRule.scheduleLabel}｜{selectedRule.frequencyLabel}</p>{selectedRule.predicateLabels.length > 0 && <p>條件：{selectedRule.predicateLabels.join('、')}</p>}<div className="line-warning">本頁只有查詢權限；規則 Preview／Save／Delete／Manual Replay 尚未開放。</div></div>}</Drawer>

      <Drawer isOpen={selectedPublication.status !== 'idle'} onClose={closePublication} title="Rich Menu 發布紀錄" footer={<div className="line-drawer-footer"><button type="button" onClick={closePublication}>關閉</button>{selectedPublication.status === 'error' && publicationDetailId.current !== null && <button type="button" onClick={() => openPublication(publicationDetailId.current!)}>重試查詢</button>}<button type="button" data-control-id="line.richmenu.retry" disabled>重新發布</button></div>}><div className="line-drawer-content"><LoadingOrError state={selectedPublication} loadingText="正在載入發布紀錄明細…" />{selectedPublication.status === 'loaded' && selectedPublication.value && <><div className="line-detail-grid"><div><span>選單定義</span><strong>{selectedPublication.value.menuDefinitionId}</strong></div><div><span>設定版本</span><strong>{selectedPublication.value.configurationRevision}</strong></div><div><span>伺服器狀態</span><strong>{selectedPublication.value.statusLabel}</strong></div><div><span>紀錄 ID</span><strong>{selectedPublication.value.id}</strong></div></div><div className="line-warning">發布、重試、圖片上傳與刪除皆未在本 query-only slice 開放。</div></>}</div></Drawer>
    </div>
  );
};

export default LineManagementPage;
