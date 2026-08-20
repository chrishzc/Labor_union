/**
 * File: LineManagementPage.tsx
 * Description: 保留六頁籤 LINE 管理介面並接線客服結案與身分解除的查詢、預覽、套用及重查流程。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  adaptCustomerServiceDetail,
  adaptCustomerServicePage,
  adaptCustomerServiceResolvePreview,
  adaptCustomerServiceSummary,
  CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE,
  type CustomerServiceDetailModel,
  type CustomerServicePageModel,
  type CustomerServiceResolvePreviewModel,
  type CustomerServiceSummaryModel,
} from '../adapters/customer_service/customer_service_adapter';
import {
  adaptLineIdentityBinding,
  adaptLineIdentityBindingPage,
  adaptLineIdentityRevocationAccepted,
  adaptLineIdentityRevocationPreview,
  type LineIdentityBindingRowViewModel,
  type LineIdentityRevocationAcceptedViewModel,
  type LineIdentityRevocationPreviewViewModel,
} from '../adapters/line_identity/line_identity_adapter';
import {
  customerServiceClient,
  type CustomerServiceClient,
} from '../api/customer_service/customer_service_client';
import {
  ApiNetworkError,
  ApiTimeoutError,
  CustomerServiceClientError,
} from '../api/customer_service/customer_service_errors';
import type { CustomerServiceResolveApplyRequest } from '../api/customer_service/customer_service_schemas';
import {
  lineIdentityClient,
  type LineIdentityClient,
} from '../api/line_identity/line_identity_client';
import {
  lineConfigurationQueryClient,
  type LineConfigurationQueryClient,
} from '../api/line_configuration/line_configuration_query_client';
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
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';
import type {
  LineIdentityBindingView,
  LineIdentityRevocationApplyRequest,
} from '../api/line_identity/line_identity_schemas';
import { Drawer } from '../components/Drawer';
import './LineManagementPage.css';

type LineTab = 'tickets' | 'richmenu' | 'binding' | 'push_queue' | 'faq' | 'order_groups';

interface LineManagementPageProps {
  customerService?: CustomerServiceClient;
  lineIdentity?: LineIdentityClient;
  lineConfiguration?: LineConfigurationQueryClient;
}

interface TicketCommand {
  payload: CustomerServiceResolveApplyRequest;
  correlationId: string;
  idempotencyKey: string;
}

type TicketFlow =
  | { kind: 'closed' }
  | { kind: 'query_loading'; ticketId: number }
  | { kind: 'query_ready'; detail: CustomerServiceDetailModel; error?: string }
  | { kind: 'preview_loading'; detail: CustomerServiceDetailModel }
  | { kind: 'preview_ready'; detail: CustomerServiceDetailModel; preview: CustomerServiceResolvePreviewModel; command: TicketCommand }
  | { kind: 'apply_pending'; detail: CustomerServiceDetailModel; preview: CustomerServiceResolvePreviewModel; command: TicketCommand }
  | { kind: 'outcome_unknown'; detail: CustomerServiceDetailModel; preview: CustomerServiceResolvePreviewModel; command: TicketCommand; error: string }
  | { kind: 'requery_loading'; detail: CustomerServiceDetailModel }
  | { kind: 'observed'; detail: CustomerServiceDetailModel };

interface BindingRecord {
  source: LineIdentityBindingView;
  view: LineIdentityBindingRowViewModel;
}

interface IdentityCommand {
  payload: LineIdentityRevocationApplyRequest;
  lineUserId: string;
}

type IdentityFlow =
  | { kind: 'closed' }
  | { kind: 'query_loading'; lineUserId: string }
  | { kind: 'query_ready'; binding: BindingRecord; error?: string }
  | { kind: 'preview_loading'; binding: BindingRecord }
  | { kind: 'preview_ready'; binding: BindingRecord; preview: LineIdentityRevocationPreviewViewModel; command: IdentityCommand }
  | { kind: 'apply_pending'; binding: BindingRecord; preview: LineIdentityRevocationPreviewViewModel; command: IdentityCommand }
  | { kind: 'outcome_unknown'; binding: BindingRecord; preview: LineIdentityRevocationPreviewViewModel; command: IdentityCommand; error: string }
  | { kind: 'requery_loading'; binding: BindingRecord; accepted: LineIdentityRevocationAcceptedViewModel }
  | { kind: 'observation_failed'; binding: BindingRecord; accepted: LineIdentityRevocationAcceptedViewModel; error: string }
  | { kind: 'observed'; binding: BindingRecord; accepted: LineIdentityRevocationAcceptedViewModel };

const TABS: ReadonlyArray<readonly [LineTab, string, string]> = [
  ['tickets', '📋 1. 客服工單與案件追蹤', 'line.tab.tickets'],
  ['richmenu', '📱 2. 多角色 Rich Menu 圖文選單', 'line.tab.richmenu'],
  ['binding', '🔑 3. LINE 身分綁定與授權', 'line.tab.binding'],
  ['push_queue', '🔔 4. 通知規則目錄', 'line.tab.push-queue'],
  ['faq', '🧠 5. 智慧客服 FAQ 知識庫', 'line.tab.faq'],
  ['order_groups', '👥 6. 三方服務群組', 'line.tab.order-groups'],
];

function requestId(prefix: string): string {
  return `${prefix}-${globalThis.crypto.randomUUID()}`;
}

function displayError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function customerConflict(error: unknown): boolean {
  return error instanceof CustomerServiceClientError && ['conflict', 'idempotency_mismatch'].includes(error.category);
}

function customerOutcomeUnknown(error: unknown): boolean {
  return error instanceof ApiTimeoutError || error instanceof ApiNetworkError ||
    (error instanceof CustomerServiceClientError && error.category === 'unavailable' && error.retryable);
}

function ticketDetail(flow: TicketFlow): CustomerServiceDetailModel | null {
  return 'detail' in flow ? flow.detail : null;
}

function identityBinding(flow: IdentityFlow): BindingRecord | null {
  return 'binding' in flow ? flow.binding : null;
}

const lockedTicketDrawer = (flow: TicketFlow) => ['apply_pending', 'outcome_unknown', 'requery_loading'].includes(flow.kind);
const lockedIdentityDrawer = (flow: IdentityFlow) => ['apply_pending', 'outcome_unknown', 'requery_loading'].includes(flow.kind);

export const LineManagementPage: React.FC<LineManagementPageProps> = ({
  customerService = customerServiceClient,
  lineIdentity = lineIdentityClient,
  lineConfiguration = lineConfigurationQueryClient,
}) => {
  const [activeTab, setActiveTab] = useState<LineTab>('tickets');
  const [summary, setSummary] = useState<CustomerServiceSummaryModel | null>(null);
  const [tickets, setTickets] = useState<CustomerServicePageModel | null>(null);
  const [ticketLoadError, setTicketLoadError] = useState<string | null>(null);
  const [ticketReload, setTicketReload] = useState(0);
  const [ticketFlow, setTicketFlow] = useState<TicketFlow>({ kind: 'closed' });
  const [ticketNote, setTicketNote] = useState('');
  const [bindings, setBindings] = useState<BindingRecord[]>([]);
  const [bindingLoadError, setBindingLoadError] = useState<string | null>(null);
  const [bindingLoading, setBindingLoading] = useState(false);
  const [bindingReload, setBindingReload] = useState(0);
  const bindingRequested = useRef(false);
  const [identityFlow, setIdentityFlow] = useState<IdentityFlow>({ kind: 'closed' });
  const [reason, setReason] = useState('');
  const [rulesCatalog, setRulesCatalog] = useState<LineNotificationRulesCatalogModel | null>(null);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesReload, setRulesReload] = useState(0);
  const rulesRequested = useRef(false);
  const [selectedRule, setSelectedRule] = useState<LineNotificationRuleModel | null>(null);
  const [richMenuConfiguration, setRichMenuConfiguration] = useState<LineRichMenuConfigurationModel | null>(null);
  const [richMenuPublications, setRichMenuPublications] = useState<LineRichMenuPublicationPageModel | null>(null);
  const [richMenuError, setRichMenuError] = useState<string | null>(null);
  const [richMenuLoading, setRichMenuLoading] = useState(false);
  const [richMenuReload, setRichMenuReload] = useState(0);
  const richMenuRequested = useRef(false);
  const [selectedMenuId, setSelectedMenuId] = useState<string | null>(null);
  const [selectedPublication, setSelectedPublication] = useState<LineRichMenuPublicationModel | null>(null);
  const [publicationDetailError, setPublicationDetailError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setTicketLoadError(null);
      void Promise.all([
        customerService.getSummary({ signal: controller.signal }),
        customerService.listTickets({ page: 1, page_size: 100 }, { signal: controller.signal }),
      ]).then(([nextSummary, nextTickets]) => {
        setSummary(adaptCustomerServiceSummary(nextSummary));
        setTickets(adaptCustomerServicePage(nextTickets));
      }).catch((error: unknown) => {
        if (!controller.signal.aborted) setTicketLoadError(displayError(error, '客服資料載入失敗'));
      });
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [customerService, ticketReload]);

  useEffect(() => {
    if (activeTab !== 'binding' || bindingRequested.current) return;
    bindingRequested.current = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setBindingLoading(true);
      setBindingLoadError(null);
      void lineIdentity.listBindings({ page: 1, page_size: 100 }, { signal: controller.signal })
        .then((page) => {
          const views = adaptLineIdentityBindingPage(page);
          setBindings(page.items.map((source, index) => ({ source, view: views.items[index] })));
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) setBindingLoadError(displayError(error, '身分綁定資料載入失敗'));
        })
        .finally(() => { if (!controller.signal.aborted) setBindingLoading(false); });
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, bindingReload, lineIdentity]);

  useEffect(() => {
    if (activeTab !== 'push_queue' || rulesRequested.current) return;
    rulesRequested.current = true;
    const controller = new AbortController();
    setRulesLoading(true);
    setRulesError(null);
    void lineConfiguration.getNotificationRules({ signal: controller.signal })
      .then((source) => setRulesCatalog(adaptLineNotificationRulesCatalog(source)))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setRulesError(displayError(error, '通知規則目錄載入失敗'));
      })
      .finally(() => { if (!controller.signal.aborted) setRulesLoading(false); });
    return () => controller.abort();
  }, [activeTab, lineConfiguration, rulesReload]);

  useEffect(() => {
    if (activeTab !== 'richmenu' || richMenuRequested.current) return;
    richMenuRequested.current = true;
    const controller = new AbortController();
    setRichMenuLoading(true);
    setRichMenuError(null);
    void Promise.all([
      lineConfiguration.getRichMenuConfiguration({ signal: controller.signal }),
      lineConfiguration.listRichMenuPublications({ signal: controller.signal }),
    ]).then(([configuration, publications]) => {
      const nextConfiguration = adaptLineRichMenuConfiguration(configuration);
      setRichMenuConfiguration(nextConfiguration);
      setRichMenuPublications(adaptLineRichMenuPublicationPage(publications));
      setSelectedMenuId((current) => current ?? nextConfiguration.menus[0]?.id ?? null);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setRichMenuError(displayError(error, 'Rich Menu 查詢資料載入失敗'));
    }).finally(() => { if (!controller.signal.aborted) setRichMenuLoading(false); });
    return () => controller.abort();
  }, [activeTab, lineConfiguration, richMenuReload]);

  const reloadBindings = () => {
    bindingRequested.current = false;
    setBindingReload((value) => value + 1);
  };

  const reloadRules = () => {
    rulesRequested.current = false;
    setRulesReload((value) => value + 1);
  };

  const reloadRichMenus = () => {
    richMenuRequested.current = false;
    setRichMenuReload((value) => value + 1);
  };

  const openPublication = async (publication: LineRichMenuPublicationModel) => {
    setPublicationDetailError(null);
    try {
      setSelectedPublication(adaptLineRichMenuPublication(
        await lineConfiguration.getRichMenuPublication(publication.id)
      ));
    } catch (error) {
      setSelectedPublication(null);
      setPublicationDetailError(displayError(error, '發布紀錄明細載入失敗'));
    }
  };

  const openTicket = async (ticketId: number) => {
    setTicketNote('');
    setTicketFlow({ kind: 'query_loading', ticketId });
    try {
      setTicketFlow({ kind: 'query_ready', detail: adaptCustomerServiceDetail(await customerService.getTicketDetail(ticketId)) });
    } catch (error) {
      setTicketFlow({ kind: 'closed' });
      setTicketLoadError(displayError(error, '工單明細載入失敗'));
    }
  };

  const refreshTicket = async (detail: CustomerServiceDetailModel, message: string) => {
    try {
      const fresh = adaptCustomerServiceDetail(await customerService.getTicketDetail(detail.ticket.ticketId));
      setTicketFlow({ kind: 'query_ready', detail: fresh, error: `${message}；已重新載入最新版本，請再次預覽。` });
    } catch (error) {
      setTicketFlow({ kind: 'query_ready', detail, error: displayError(error, '重新載入工單失敗') });
    }
  };

  const previewResolve = async () => {
    const detail = ticketDetail(ticketFlow);
    if (!detail || detail.ticket.status === 'resolved') return;
    setTicketFlow({ kind: 'preview_loading', detail });
    const note = ticketNote.trim();
    const correlationId = requestId('ticket-correlation');
    try {
      const source = await customerService.previewResolve(detail.ticket.ticketId, {
        status: 'resolved', internal_note: note || null, expected_version: detail.ticket.version,
      }, { correlationId });
      const preview = adaptCustomerServiceResolvePreview(source);
      setTicketFlow({
        kind: 'preview_ready', detail, preview,
        command: {
          correlationId,
          idempotencyKey: requestId('ticket-idempotency'),
          payload: { status: 'resolved', internal_note: note || null, expected_version: preview.expectedVersion, preview_fingerprint: preview.previewFingerprint },
        },
      });
    } catch (error) {
      if (customerConflict(error)) await refreshTicket(detail, displayError(error, '工單版本已變更'));
      else setTicketFlow({ kind: 'query_ready', detail, error: displayError(error, '結案預覽失敗') });
    }
  };

  const applyResolve = async (detail: CustomerServiceDetailModel, preview: CustomerServiceResolvePreviewModel, command: TicketCommand) => {
    setTicketFlow({ kind: 'apply_pending', detail, preview, command });
    try {
      await customerService.applyResolve(detail.ticket.ticketId, command.payload, { correlationId: command.correlationId, idempotencyKey: command.idempotencyKey });
      setTicketFlow({ kind: 'requery_loading', detail });
      const observed = adaptCustomerServiceDetail(await customerService.getTicketDetail(detail.ticket.ticketId));
      setTicketFlow({ kind: 'observed', detail: observed });
      setTicketReload((value) => value + 1);
    } catch (error) {
      if (customerOutcomeUnknown(error)) {
        setTicketFlow({ kind: 'outcome_unknown', detail, preview, command, error: '套用結果未知；只能使用相同識別鍵重試，請勿關閉抽屜。' });
      } else if (customerConflict(error)) await refreshTicket(detail, displayError(error, '工單版本已變更'));
      else setTicketFlow({ kind: 'preview_ready', detail, preview, command });
    }
  };

  const openBinding = async (record: BindingRecord) => {
    setReason('');
    setIdentityFlow({ kind: 'query_loading', lineUserId: record.source.line_user_id });
    try {
      const source = await lineIdentity.getBinding(record.source.line_user_id);
      setIdentityFlow({ kind: 'query_ready', binding: { source, view: adaptLineIdentityBinding(source) } });
    } catch (error) {
      setIdentityFlow({ kind: 'closed' });
      setBindingLoadError(displayError(error, '身分綁定明細載入失敗'));
    }
  };

  const refreshBinding = async (binding: BindingRecord, message: string) => {
    try {
      const source = await lineIdentity.getBinding(binding.source.line_user_id);
      setIdentityFlow({ kind: 'query_ready', binding: { source, view: adaptLineIdentityBinding(source) }, error: `${message}；已重新載入最新版本，請再次預覽。` });
    } catch (error) {
      setIdentityFlow({ kind: 'query_ready', binding, error: displayError(error, '重新載入綁定失敗') });
    }
  };

  const previewRevocation = async () => {
    const binding = identityBinding(identityFlow);
    if (!binding || binding.source.status !== 'bound') return;
    setIdentityFlow({ kind: 'preview_loading', binding });
    try {
      const source = await lineIdentity.previewRevocation(binding.source.line_user_id);
      const preview = adaptLineIdentityRevocationPreview(source);
      setIdentityFlow({
        kind: 'preview_ready', binding, preview,
        command: {
          lineUserId: binding.source.line_user_id,
          payload: { expected_version: source.binding.version, reason: reason.trim(), idempotency_key: requestId('identity-idempotency'), correlation_id: requestId('identity-correlation') },
        },
      });
    } catch (error) {
      if (error instanceof LineIdentityClientError && error.code === 'CONFLICT') await refreshBinding(binding, error.message);
      else setIdentityFlow({ kind: 'query_ready', binding, error: displayError(error, '解除預覽失敗') });
    }
  };

  const applyRevocation = async (binding: BindingRecord, preview: LineIdentityRevocationPreviewViewModel, command: IdentityCommand) => {
    setIdentityFlow({ kind: 'apply_pending', binding, preview, command });
    try {
      const accepted = adaptLineIdentityRevocationAccepted(await lineIdentity.applyRevocation(command.lineUserId, command.payload));
      setIdentityFlow({ kind: 'requery_loading', binding, accepted });
      try {
        const source = await lineIdentity.getBinding(command.lineUserId);
        setIdentityFlow({ kind: 'observed', binding: { source, view: adaptLineIdentityBinding(source) }, accepted });
        reloadBindings();
      } catch (error) {
        setIdentityFlow({
          kind: 'observation_failed',
          binding,
          accepted,
          error: displayError(error, '解除申請已受理，但重新查詢失敗。'),
        });
      }
    } catch (error) {
      if (error instanceof LineIdentityClientError && error.outcomeUnknown) {
        setIdentityFlow({ kind: 'outcome_unknown', binding, preview, command, error: '解除申請結果未知；只能使用相同識別鍵重試，請勿關閉抽屜。' });
      } else if (error instanceof LineIdentityClientError && error.code === 'CONFLICT') await refreshBinding(binding, error.message);
      else setIdentityFlow({ kind: 'preview_ready', binding, preview, command });
    }
  };

  const retryIdentityObservation = async (binding: BindingRecord, accepted: LineIdentityRevocationAcceptedViewModel) => {
    setIdentityFlow({ kind: 'requery_loading', binding, accepted });
    try {
      const source = await lineIdentity.getBinding(binding.source.line_user_id);
      setIdentityFlow({ kind: 'observed', binding: { source, view: adaptLineIdentityBinding(source) }, accepted });
      reloadBindings();
    } catch (error) {
      setIdentityFlow({
        kind: 'observation_failed',
        binding,
        accepted,
        error: displayError(error, '解除申請已受理，但重新查詢仍失敗。'),
      });
    }
  };

  const currentTicket = ticketDetail(ticketFlow);
  const currentBinding = identityBinding(identityFlow);
  const selectedMenu = richMenuConfiguration?.menus.find((menu) => menu.id === selectedMenuId) ??
    richMenuConfiguration?.menus[0] ?? null;
  const closeTicket = () => { if (!lockedTicketDrawer(ticketFlow)) setTicketFlow({ kind: 'closed' }); };
  const closeIdentity = () => { if (!lockedIdentityDrawer(identityFlow)) setIdentityFlow({ kind: 'closed' }); };

  return (
    <div data-control-id="line.page">
      <div className="page-header-banner line-page-header"><div><h1 className="page-title">💬 LINE 官方帳號與推播管理中心</h1><p className="page-subtitle">客服工單、身分綁定、Rich Menu、通知規則、FAQ 與三方群組管理。</p></div></div>
      <div className="line-tab-bar" aria-label="LINE 管理工作區">
        {TABS.map(([tab, label, id]) => <button key={tab} type="button" data-control-id={id} className={`line-tab-btn ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>{label}</button>)}
      </div>

      {activeTab === 'tickets' && <section className="line-table-container">
        <div className="line-section-heading"><div><h3>📋 客服工單與案件關聯追蹤清單</h3><p>資料來自 Customer Service typed API；不從文案推導狀態。</p></div><button type="button" className="line-secondary-btn" onClick={() => setTicketReload((value) => value + 1)}>重新整理</button></div>
        <div className="line-kpi-grid"><div data-control-id="line.ticket.summary.waiting"><span>待處理</span><strong>{summary?.waiting ?? '—'}</strong></div><div data-control-id="line.ticket.summary.handling"><span>處理中</span><strong>{summary?.handling ?? '—'}</strong></div><div data-control-id="line.ticket.summary.resolved_today"><span>今日結案</span><strong>{summary?.resolvedToday ?? '—'}</strong></div></div>
        {ticketLoadError && <div className="line-error" role="alert">{ticketLoadError}</div>}
        {!tickets && !ticketLoadError && <div className="line-loading">正在載入客服工單…</div>}
        {tickets && <div className="line-table-scroll"><table className="line-data-table" data-control-id="line.ticket.table"><thead><tr><th>工單編號</th><th>提問對象</th><th>關聯案件</th><th>分類</th><th>問題摘要</th><th>時間</th><th>狀態</th><th>操作</th></tr></thead><tbody>
          {tickets.items.map((ticket) => <tr key={ticket.ticketId}><td><strong>#{ticket.ticketIdText}</strong></td><td>👤 {ticket.clientName ?? ticket.maskedLineUserId}</td><td>{ticket.caseNo ?? '無關聯'}</td><td>{ticket.categoryLabel}</td><td>{ticket.issueSummary ?? CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE}</td><td>{ticket.createdAt ?? '—'}</td><td><span className={`line-status line-status-${ticket.status}`}>{ticket.statusLabel}</span></td><td><div className="line-row-actions"><button type="button" data-control-id="line.ticket.open" disabled>開啟 LINE</button><button type="button" data-control-id="line.ticket.detail" onClick={() => void openTicket(ticket.ticketId)}>查看明細</button></div></td></tr>)}
        </tbody></table></div>}
      </section>}

      {activeTab === 'richmenu' && <section className="line-workspace-card" data-control-id="line.richmenu.configuration"><div className="line-section-heading"><div><h3>📱 多角色 Rich Menu 圖文選單動態發布管理</h3><p>顯示伺服器設定快照與最多 100 筆已載入發布紀錄；發布仍維持鎖定。</p></div><div className="line-row-actions"><button type="button" className="line-secondary-btn" data-control-id="line.richmenu.refresh" onClick={reloadRichMenus}>重新整理</button><button type="button" data-control-id="line.richmenu.publish" disabled>🚀 發布至 LINE 官方帳號</button></div></div>
        {richMenuLoading && <div className="line-loading">正在載入 Rich Menu 設定與發布紀錄…</div>}
        {richMenuError && <div className="line-error" data-control-id="line.richmenu.unavailable" role="alert">{richMenuError}</div>}
        {!richMenuLoading && !richMenuError && richMenuConfiguration?.isEmpty && <div className="line-empty-state"><div>📱</div><h4>目前尚未設定 Rich Menu</h4><p>此為伺服器回傳的空設定，不會套用前端預設選單。</p></div>}
        {!richMenuLoading && !richMenuError && richMenuConfiguration && !richMenuConfiguration.isEmpty && <>
          <div className="line-role-switcher">{richMenuConfiguration.menus.map((menu) => <button key={menu.id} type="button" className={selectedMenu?.id === menu.id ? 'active' : ''} onClick={() => setSelectedMenuId(menu.id)}>{menu.audienceRoleLabel}｜{menu.name}</button>)}</div>
          {selectedMenu && <div className="line-phone-preview"><div className="line-phone-header">{selectedMenu.name}</div><div className="line-phone-message">{selectedMenu.chatBarText}</div><div className="line-menu-grid">{selectedMenu.buttons.map((button) => <div key={button.id}>{button.label}</div>)}</div></div>}
          <div className="line-publication-history" data-control-id="line.richmenu.publications"><h4>已載入發布紀錄</h4><p>僅顯示本次 loaded scope（最多 100 筆），不代表完整歷史總數。</p>{richMenuPublications?.items.length ? <div className="line-table-scroll"><table className="line-data-table"><thead><tr><th>ID</th><th>選單</th><th>設定版本</th><th>狀態</th><th>操作</th></tr></thead><tbody>{richMenuPublications.items.map((publication) => <tr key={publication.id}><td>{publication.id}</td><td>{publication.menuDefinitionId}</td><td>{publication.configurationRevision}</td><td>{publication.statusLabel}</td><td><button type="button" data-control-id="line.richmenu.publication-detail" onClick={() => void openPublication(publication)}>查看</button></td></tr>)}</tbody></table></div> : <div className="line-empty-state"><h4>此 loaded scope 沒有發布紀錄</h4></div>}</div>
        </>}
        {publicationDetailError && <div className="line-error" role="alert">{publicationDetailError}</div>}
      </section>}

      {activeTab === 'binding' && <section className="line-workspace-card"><div className="line-section-heading"><div><h3>🔑 LINE 身分綁定與 LIFF 授權管理</h3><p>解除申請受理後仍須重新查詢。</p></div><div className="line-row-actions"><button type="button" data-control-id="line.identity.invite" disabled>+ 產生綁定邀請連結</button><button type="button" className="line-secondary-btn" onClick={reloadBindings}>重新整理</button></div></div>
        {bindingLoadError && <div className="line-error" role="alert">{bindingLoadError}</div>}{bindingLoading && <div className="line-loading">正在載入身分綁定…</div>}
        {!bindingLoading && !bindingLoadError && <div className="line-table-scroll"><table className="line-data-table" data-control-id="line.identity.table"><thead><tr><th>LINE User ID</th><th>實名姓名</th><th>角色</th><th>更新時間</th><th>狀態</th><th>解除狀態</th><th>操作</th></tr></thead><tbody>{bindings.map((record) => <tr key={`${record.view.maskedLineUserId}-${record.view.version}`}><td><code>{record.view.maskedLineUserId}</code></td><td>👤 {record.view.subjectName}</td><td>{record.view.subjectTypeLabel}</td><td>{record.view.updatedAt ?? '—'}</td><td>{record.view.statusLabel}</td><td>{record.view.revocationStatusLabel}</td><td><button type="button" data-control-id="line.identity.detail" onClick={() => void openBinding(record)}>查看明細</button></td></tr>)}</tbody></table></div>}
      </section>}

      {activeTab === 'push_queue' && <section className="line-workspace-card"><div className="line-section-heading"><div><h3>🔔 通知規則目錄</h3><p>查詢伺服器 current revision；規則修改與發送副作用仍維持鎖定。</p></div><div className="line-row-actions"><button type="button" className="line-secondary-btn" data-control-id="line.notification-rules.refresh" onClick={reloadRules}>重新整理</button><button type="button" data-control-id="line.notification-rule.create" disabled>+ 建立新通知規則</button></div></div>
        {rulesLoading && <div className="line-loading">正在載入通知規則目錄…</div>}
        {rulesError && <div className="line-error" data-control-id="line.notification-rules.unavailable" role="alert">{rulesError}</div>}
        {!rulesLoading && !rulesError && rulesCatalog?.isEmpty && <div className="line-empty-state" data-control-id="line.notification-rules.empty"><div>🔔</div><h4>目前尚未設定通知規則</h4><p>Current revision：{rulesCatalog.revision}。未使用前端預設規則。</p></div>}
        {!rulesLoading && !rulesError && rulesCatalog && !rulesCatalog.isEmpty && <div className="line-rule-list" data-control-id="line.notification-rules.list">{rulesCatalog.rules.map((rule) => <button key={rule.id} type="button" className="line-rule-card" onClick={() => setSelectedRule(rule)}><span>{rule.eventLabel}｜{rule.recipientLabel}</span><strong>{rule.id}</strong><small>{rule.scheduleLabel}｜{rule.frequencyLabel}｜{rule.enabled ? '已啟用' : '未啟用'}</small></button>)}</div>}
      </section>}
      {activeTab === 'faq' && <section className="line-workspace-card"><div className="line-section-heading"><div><h3>🧠 智慧客服 FAQ 知識庫</h3><p>知識版本與發布屬 Phase 4。</p></div><button type="button" data-control-id="line.faq.create" disabled>+ 新增 FAQ 詞條</button></div><div className="line-faq-list"><article><span>收費與補助</span><h4>❓ 政府產後月子補助如何請領？</h4><p>核准文案與版本管理將於後續階段接線。</p></article><article><span>合約與定金</span><h4>❓ 解約時定金如何處理？</h4><p>核准文案與版本管理將於後續階段接線。</p></article></div></section>}
      {activeTab === 'order_groups' && <section className="line-table-container"><div className="line-section-heading"><div><h3>👥 三方服務群組管理</h3><p>管理產婦、月嫂與客服的三方通訊群組。</p></div><button type="button" data-control-id="line.order-group.create" disabled>+ 建立三方群組</button></div><div className="line-empty-state"><div>👥</div><h4>目前尚無已接線的三方服務群組</h4><p>此功能將於 Phase 4 開放。</p></div></section>}

      <Drawer isOpen={ticketFlow.kind !== 'closed'} onClose={closeTicket} title={`客服工單明細${currentTicket ? ` #${currentTicket.ticket.ticketIdText}` : ''}`} size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeTicket} disabled={lockedTicketDrawer(ticketFlow)}>關閉</button>{ticketFlow.kind === 'query_ready' && ticketFlow.detail.ticket.status !== 'resolved' && <button type="button" data-control-id="line.ticket.resolve.preview" onClick={() => void previewResolve()}>預覽結案</button>}{ticketFlow.kind === 'preview_ready' && <button type="button" data-control-id="line.ticket.resolve.apply" disabled={!ticketFlow.preview.applyReady || ticketFlow.preview.blockers.length > 0} onClick={() => void applyResolve(ticketFlow.detail, ticketFlow.preview, ticketFlow.command)}>確認結案</button>}{ticketFlow.kind === 'apply_pending' && <button type="button" data-control-id="line.ticket.resolve.apply" disabled>套用中…</button>}{ticketFlow.kind === 'outcome_unknown' && <button type="button" data-control-id="line.ticket.resolve.apply" onClick={() => void applyResolve(ticketFlow.detail, ticketFlow.preview, ticketFlow.command)}>使用相同識別鍵重試</button>}</div>}>
        <div data-control-id="line.ticket.detail" className="line-drawer-content">{ticketFlow.kind === 'query_loading' && <div className="line-loading">正在載入工單明細…</div>}{currentTicket && <><div className="line-detail-grid"><div><span>客戶</span><strong>{currentTicket.ticket.clientName ?? currentTicket.ticket.maskedLineUserId}</strong></div><div><span>案件</span><strong>{currentTicket.ticket.caseNo ?? '無關聯'}</strong></div><div><span>狀態</span><strong>{currentTicket.ticket.statusLabel}</strong></div><div><span>版本</span><strong>{currentTicket.ticket.version}</strong></div></div>{ticketFlow.kind === 'query_ready' && ticketFlow.error && <div className="line-error" role="alert">{ticketFlow.error}</div>}{currentTicket.ticket.status !== 'resolved' && <label className="line-field"><span>內部結案備註（可空）</span><textarea value={ticketNote} maxLength={4000} disabled={ticketFlow.kind !== 'query_ready'} onChange={(event) => setTicketNote(event.target.value)} /></label>}{['preview_loading','apply_pending','requery_loading'].includes(ticketFlow.kind) && <div className="line-loading">{ticketFlow.kind === 'preview_loading' ? '正在建立零寫入預覽…' : ticketFlow.kind === 'apply_pending' ? '正在提交結案…' : '正在重新查詢…'}</div>}{'preview' in ticketFlow && <div className="line-preview-panel"><h4>結案預覽</h4><p>{ticketFlow.preview.beforeStatusLabel} → {ticketFlow.preview.afterStatusLabel}</p>{ticketFlow.preview.blockers.map((item) => <div key={item} className="line-warning">{item}</div>)}</div>}{ticketFlow.kind === 'outcome_unknown' && <div className="line-warning" role="alert">{ticketFlow.error}</div>}{ticketFlow.kind === 'observed' && <div className="line-success" role="status">重新查詢完成：伺服器目前狀態為「{ticketFlow.detail.ticket.statusLabel}」。</div>}<div className="line-events"><h4>事件紀錄</h4>{currentTicket.events.length === 0 ? <p>尚無事件紀錄</p> : currentTicket.events.map((event) => <article key={event.id}><strong>{event.eventType}</strong><span>{event.createdAt}</span><p>{event.messageText ?? '無訊息內容'}</p></article>)}</div></>}</div>
      </Drawer>

      <Drawer isOpen={identityFlow.kind !== 'closed'} onClose={closeIdentity} title="LINE 身分解除" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeIdentity} disabled={lockedIdentityDrawer(identityFlow)}>關閉</button>{identityFlow.kind === 'query_ready' && identityFlow.binding.source.status === 'bound' && <button type="button" data-control-id="line.identity.revocation.preview" disabled={!reason.trim()} onClick={() => void previewRevocation()}>預覽解除</button>}{identityFlow.kind === 'preview_ready' && <button type="button" data-control-id="line.identity.revocation.apply" disabled={identityFlow.preview.hasBlockers} onClick={() => void applyRevocation(identityFlow.binding, identityFlow.preview, identityFlow.command)}>提交解除申請</button>}{identityFlow.kind === 'apply_pending' && <button type="button" data-control-id="line.identity.revocation.apply" disabled>提交中…</button>}{identityFlow.kind === 'outcome_unknown' && <button type="button" data-control-id="line.identity.revocation.apply" onClick={() => void applyRevocation(identityFlow.binding, identityFlow.preview, identityFlow.command)}>使用相同識別鍵重試</button>}{identityFlow.kind === 'observation_failed' && <button type="button" data-control-id="line.identity.revocation.observe" onClick={() => void retryIdentityObservation(identityFlow.binding, identityFlow.accepted)}>重新查詢解除狀態</button>}</div>}>
        <div data-control-id="line.identity.revocation.drawer" className="line-drawer-content">{identityFlow.kind === 'query_loading' && <div className="line-loading">正在載入身分綁定明細…</div>}{currentBinding && <><div className="line-detail-grid"><div><span>LINE User ID</span><strong>{currentBinding.view.maskedLineUserId}</strong></div><div><span>實名姓名</span><strong>{currentBinding.view.subjectName}</strong></div><div><span>角色</span><strong>{currentBinding.view.subjectTypeLabel}</strong></div><div><span>狀態／版本</span><strong>{currentBinding.view.statusLabel}／{currentBinding.view.version}</strong></div></div>{identityFlow.kind === 'query_ready' && identityFlow.error && <div className="line-error" role="alert">{identityFlow.error}</div>}<label className="line-field"><span>解除原因（必填）</span><textarea data-control-id="line.identity.revocation.reason" value={reason} maxLength={1000} disabled={identityFlow.kind !== 'query_ready'} onChange={(event) => setReason(event.target.value)} /></label>{['preview_loading','apply_pending','requery_loading'].includes(identityFlow.kind) && <div className="line-loading">{identityFlow.kind === 'preview_loading' ? '正在建立零寫入預覽…' : identityFlow.kind === 'apply_pending' ? '正在提交解除申請…' : '申請已受理，正在重新查詢…'}</div>}{'preview' in identityFlow && <div className="line-preview-panel"><h4>解除預覽</h4><p>預設 Rich Menu：{identityFlow.preview.defaultMenuPublished ? '已發布' : '尚未發布'}</p>{identityFlow.preview.blockers.map((item) => <div key={item} className="line-warning">{item}</div>)}</div>}{identityFlow.kind === 'outcome_unknown' && <div className="line-warning" role="alert">{identityFlow.error}</div>}{identityFlow.kind === 'observation_failed' && <div className="line-warning" role="alert">解除申請已受理，但最新狀態尚未確認：{identityFlow.error}</div>}{identityFlow.kind === 'observed' && <div className="line-success" role="status">{identityFlow.accepted.notice} 重新查詢狀態：「{identityFlow.binding.view.statusLabel}」。</div>}<div className="line-locked-actions"><button type="button" data-control-id="line.identity.replacement" disabled>改綁其他身分</button><button type="button" data-control-id="line.identity.retry" disabled>重試 Rich Menu 回復</button><button type="button" data-control-id="line.identity.manual-complete" disabled>人工完成</button></div></>}</div>
      </Drawer>

      <Drawer isOpen={selectedRule !== null} onClose={() => setSelectedRule(null)} title={`通知規則（查詢模式）${selectedRule ? `－${selectedRule.id}` : ''}`} footer={<div className="line-drawer-footer"><button type="button" onClick={() => setSelectedRule(null)}>關閉</button><button type="button" data-control-id="line.notification-rule.save" disabled>儲存並發布</button></div>}>{selectedRule && <div className="line-drawer-content" data-control-id="line.notification-rule.detail"><div className="line-detail-grid"><div><span>事件</span><strong>{selectedRule.eventLabel}</strong></div><div><span>收件人</span><strong>{selectedRule.recipientLabel}</strong></div><div><span>模板</span><strong>{selectedRule.templateId}</strong></div><div><span>狀態</span><strong>{selectedRule.enabled ? '已啟用' : '未啟用'}</strong></div></div><p>{selectedRule.scheduleLabel}｜{selectedRule.frequencyLabel}</p>{selectedRule.predicateLabels.length > 0 && <p>條件：{selectedRule.predicateLabels.join('、')}</p>}<div className="line-warning">本頁只有查詢權限；規則 Preview／Save／Delete／Manual Replay 尚未開放。</div></div>}</Drawer>

      <Drawer isOpen={selectedPublication !== null} onClose={() => setSelectedPublication(null)} title={`Rich Menu 發布紀錄${selectedPublication ? ` #${selectedPublication.id}` : ''}`} footer={<div className="line-drawer-footer"><button type="button" onClick={() => setSelectedPublication(null)}>關閉</button><button type="button" data-control-id="line.richmenu.retry" disabled>重新發布</button></div>}>{selectedPublication && <div className="line-drawer-content" data-control-id="line.richmenu.publication-detail"><div className="line-detail-grid"><div><span>選單定義</span><strong>{selectedPublication.menuDefinitionId}</strong></div><div><span>設定版本</span><strong>{selectedPublication.configurationRevision}</strong></div><div><span>伺服器狀態</span><strong>{selectedPublication.statusLabel}</strong></div><div><span>紀錄 ID</span><strong>{selectedPublication.id}</strong></div></div><div className="line-warning">發布、重試、圖片上傳與刪除皆未在本 query-only slice 開放。</div></div>}</Drawer>
    </div>
  );
};

export default LineManagementPage;
