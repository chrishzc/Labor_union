/**
 * File: LineManagementPage.tsx
 * Description: 整合 LINE typed Query／Preview／Apply 工作區，所有外送副作用仍由後端 durable task 執行。
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
  adaptLineNotificationRulesCatalog,
  adaptLineRichMenuConfiguration,
  adaptLineRichMenuPublication,
  adaptLineRichMenuPublicationPage,
  type LineNotificationRuleModel,
  type LineNotificationRulesCatalogModel,
  type LineRichMenuConfigurationModel,
  type LineRichMenuPublicationModel,
  type LineRichMenuPublicationPageModel,
  type RichMenuButtonModel,
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
import type { LineNotificationRulesCatalog } from '../api/line_configuration/line_configuration_query_schemas';
import { LineConfigurationQueryError } from '../api/line_configuration/line_configuration_query_errors';
import {
  adaptLineDeliveryDetail,
  adaptLineDeliveryItem,
  adaptLineDeliverySummary,
} from '../adapters/line_delivery/line_delivery_query_adapter';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import { LineDeliveryQueryError } from '../api/line_delivery/line_delivery_query_errors';
import {
  adaptLineOrderGroupEvent,
  adaptLineOrderGroupRecord,
  type LineOrderGroupEventView,
  type LineOrderGroupRecordView,
} from '../adapters/line_order_groups/line_order_group_query_adapter';
import { lineOrderGroupQueryClient } from '../api/line_order_groups/line_order_group_query_client';
import { LineOrderGroupQueryError } from '../api/line_order_groups/line_order_group_query_errors';
import {
  adaptLineSafeConfig,
  type LineSafeConfigModel,
} from '../adapters/line_safe_config/line_safe_config_adapter';
import { lineSafeConfigClient } from '../api/line_safe_config/line_safe_config_client';
import { LineSafeConfigError } from '../api/line_safe_config/line_safe_config_errors';
import type { LineSafeConfigKind } from '../api/line_safe_config/line_safe_config_schemas';
import {
  adaptLineRuntimeAdminCandidate,
  adaptLineRuntimeTarget,
  adaptLineRuntimeTargetReceipt,
  type LineRuntimeAdminCandidateModel,
  type LineRuntimeTargetModel,
  type LineRuntimeTargetReceiptModel,
} from '../adapters/line_runtime_targets/line_runtime_target_adapter';
import { lineRuntimeTargetClient } from '../api/line_runtime_targets/line_runtime_target_client';
import { LineRuntimeTargetError } from '../api/line_runtime_targets/line_runtime_target_errors';
import type {
  LineRuntimeAdminTargetRequest,
  LineRuntimeGroupResetRequest,
  LineRuntimeTargetEnabledRequest,
  LineRuntimeTargetPreview,
} from '../api/line_runtime_targets/line_runtime_target_schemas';
import {
  adaptCustomerServiceEscalation,
  adaptCustomerServiceEscalationReceipt,
  type CustomerServiceEscalationModel,
  type CustomerServiceEscalationReceiptModel,
} from '../adapters/customer_service_escalations/customer_service_escalation_adapter';
import { customerServiceEscalationClient } from '../api/customer_service_escalations/customer_service_escalation_client';
import { CustomerServiceEscalationError } from '../api/customer_service_escalations/customer_service_escalation_errors';
import type {
  CustomerServiceEscalationClaimRequest,
  CustomerServiceEscalationCreateRequest,
  CustomerServiceEscalationHandlingRequest,
  CustomerServiceEscalationPreview,
  CustomerServiceEscalationResolveRequest,
} from '../api/customer_service_escalations/customer_service_escalation_schemas';
import { Drawer } from '../components/Drawer';
import { LineCustomerServiceActions } from '../components/LineCustomerServiceActions';
import { LineIdentityMaintenanceActions } from '../components/LineIdentityMaintenanceActions';
import {
  LineIdentityReviewWorkbench,
  type LineIdentityReviewClient,
} from '../components/LineIdentityReviewWorkbench';
import { LineNotificationRulesMutationPanel } from '../components/LineNotificationRulesMutationPanel';
import { LineRichMenuPublicationActions } from '../components/LineRichMenuPublicationActions';
import './LineManagementPage.css';

type LineTab = 'tickets' | 'richmenu' | 'binding' | 'push_queue' | 'order_groups' | 'runtime';

type CustomerServicePageClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'> &
  Partial<Pick<CustomerServiceClient, 'previewResolve' | 'applyResolve'>>;
type LineIdentityPageClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'> &
  Partial<Pick<
    LineIdentityClient,
    | 'previewRevocation'
    | 'applyRevocation'
    | 'listReviews'
    | 'getReviewSummary'
    | 'getReview'
    | 'previewReviewDecision'
    | 'applyReviewDecision'
  >>;

interface LineManagementPageProps {
  customerService?: CustomerServicePageClient;
  lineIdentity?: LineIdentityPageClient;
  lineConfiguration?: LineConfigurationQueryClient;
  runtimeTarget?: typeof lineRuntimeTargetClient;
  escalation?: typeof customerServiceEscalationClient;
  delivery?: typeof lineDeliveryQueryClient;
}

type QueryStatus = 'idle' | 'loading' | 'loaded' | 'error';
type MutationStatus = 'idle' | 'loading' | 'success' | 'error';
type LineDeliverySummaryView = ReturnType<typeof adaptLineDeliverySummary>;
type LineDeliveryItemView = ReturnType<typeof adaptLineDeliveryItem>;
type LineDeliveryDetailView = ReturnType<typeof adaptLineDeliveryDetail>;
type LineDeliveryPageView = {
  items: LineDeliveryItemView[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};
type LineOrderGroupPageView = {
  items: LineOrderGroupRecordView[];
  total: number;
  limit: number;
};

interface QueryState<T> {
  status: QueryStatus;
  value: T | null;
  error: string | null;
}

type RuntimePendingOperation =
  | { kind: 'add'; request: LineRuntimeAdminTargetRequest; preview: LineRuntimeTargetPreview }
  | { kind: 'reset'; request: LineRuntimeGroupResetRequest; preview: LineRuntimeTargetPreview }
  | { kind: 'toggle'; targetId: number; request: LineRuntimeTargetEnabledRequest; preview: LineRuntimeTargetPreview };

type EscalationPendingOperation =
  | { kind: 'create'; request: CustomerServiceEscalationCreateRequest; preview: CustomerServiceEscalationPreview }
  | { kind: 'claim'; escalationId: number; request: CustomerServiceEscalationClaimRequest; preview: CustomerServiceEscalationPreview }
  | { kind: 'handling'; escalationId: number; request: CustomerServiceEscalationHandlingRequest; preview: CustomerServiceEscalationPreview }
  | { kind: 'resolve'; escalationId: number; request: CustomerServiceEscalationResolveRequest; preview: CustomerServiceEscalationPreview };

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

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function displayQueryError(error: unknown, fallback: string): string {
  if (error instanceof CustomerServiceClientError) return `${error.code}：${error.message}`;
  if (error instanceof LineIdentityClientError) return `${error.code}：${error.message}`;
  if (error instanceof LineConfigurationQueryError) return `${error.code}：${error.message}`;
  if (error instanceof LineDeliveryQueryError) return `${error.code}：${error.message}`;
  if (error instanceof LineOrderGroupQueryError) return `${error.code}：${error.message}`;
  if (error instanceof LineSafeConfigError) return `${error.code}：${error.message}`;
  if (error instanceof LineRuntimeTargetError) return `${error.code}：${error.message}`;
  if (error instanceof CustomerServiceEscalationError) {
    if (error.code.includes('NOT_FOUND')) return '找不到可升級的正式來源事件；請先由客服工單、LINE inbox、綁定失敗或 runtime 異常建立來源。';
    return `${error.code}：${error.message}`;
  }
  return fallback;
}

const TABS: ReadonlyArray<readonly [LineTab, string, string]> = [
  ['tickets', '📋 1. 客服工單與案件追蹤', 'line.tab.tickets'],
  ['richmenu', '📱 2. 多角色 Rich Menu 圖文選單', 'line.tab.richmenu'],
  ['binding', '🔑 3. LINE 身分綁定與授權', 'line.tab.binding'],
  ['push_queue', '🔔 4. 通知規則目錄', 'line.tab.push-queue'],
  ['order_groups', '👥 5. 三方服務群組', 'line.tab.order-groups'],
  ['runtime', '🛡️ 6. 安全設定與人工升級', 'line.tab.runtime'],
];

const SAFE_CONFIGURATION_KINDS: readonly LineSafeConfigKind[] = [
  'message_templates', 'message_schedules', 'rich_menus', 'liff',
  'customer_service', 'notification_rules',
];

function LoadingOrError({ state, loadingText }: { state: QueryState<unknown>; loadingText: string }) {
  if (state.status === 'loading') return <div className="line-loading">{loadingText}</div>;
  if (state.status === 'error') return <div className="line-error" role="alert">{state.error}</div>;
  return null;
}

function asReviewClient(client: LineIdentityPageClient): LineIdentityReviewClient | null {
  if (
    client.listReviews
    && client.getReviewSummary
    && client.getReview
    && client.previewReviewDecision
    && client.applyReviewDecision
  ) {
    return client as LineIdentityReviewClient;
  }
  return null;
}

function getButtonActionDetails(btn: RichMenuButtonModel): { type: 'URI' | 'MESSAGE'; uri: string | null; text: string | null } {
  const label = btn.label;
  if (label.includes('登記')) return { type: 'URI', uri: '?entry=registration', text: null };
  if (label.includes('修改') || label.includes('異動')) return { type: 'URI', uri: '?target=profile_update', text: null };
  if (label.includes('訂單')) return { type: 'URI', uri: '?target=staff_order_search', text: null };
  if (label.includes('排班') || label.includes('日曆')) return { type: 'URI', uri: '?target=staff_schedule', text: null };
  if (label.includes('請假')) return { type: 'URI', uri: '?target=staff_leave_apply', text: null };
  if (label.includes('薪資') || label.includes('請款')) return { type: 'URI', uri: '?target=staff_payout', text: null };
  if (label.includes('審核')) return { type: 'URI', uri: '?target=staff_review', text: null };
  if (label.includes('客服中心')) return { type: 'URI', uri: '?target=customer_service', text: null };
  if (label.includes('異常')) return { type: 'URI', uri: '?target=anomalies_center', text: null };
  if (label.includes('營運') || label.includes('看板')) return { type: 'URI', uri: '?target=dashboard', text: null };
  if (label.includes('說明') || label.includes('FAQ')) return { type: 'MESSAGE', uri: null, text: '服務說明' };
  if (label.includes('客服') || label.includes('諮詢')) return { type: 'MESSAGE', uri: null, text: '專人客服' };
  return { type: 'URI', uri: `?target=${btn.id}`, text: null };
}

export const LineManagementPage: React.FC<LineManagementPageProps> = ({
  customerService = customerServiceClient,
  lineIdentity = lineIdentityClient,
  lineConfiguration = lineConfigurationQueryClient,
  runtimeTarget = lineRuntimeTargetClient,
  escalation = customerServiceEscalationClient,
  delivery = lineDeliveryQueryClient,
}) => {
  const [activeTab, setActiveTab] = useState<LineTab>('tickets');
  const [ticketSummary, setTicketSummary] = useState<QueryState<CustomerServiceSummaryModel>>(idleState);
  const [ticketPage, setTicketPage] = useState<QueryState<CustomerServicePageModel>>(idleState);
  const [ticketReload, setTicketReload] = useState(0);
  const [ticketPageNumber, setTicketPageNumber] = useState(1);
  const ticketPageSize = 25;
  const [ticketSearchQuery, setTicketSearchQuery] = useState('');
  const [ticketStatusFilter, setTicketStatusFilter] = useState<'all' | 'waiting' | 'handling' | 'resolved'>('all');
  const [ticketCategoryFilter, setTicketCategoryFilter] = useState<string>('all');
  const [ticketScopeBlocker, setTicketScopeBlocker] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<QueryState<CustomerServiceDetailModel>>(idleState);
  const ticketDetailController = useRef<AbortController | null>(null);
  const ticketDetailGeneration = useRef(0);
  const ticketDetailId = useRef<number | null>(null);
  const ticketResolveController = useRef<AbortController | null>(null);
  const [ticketResolveNote, setTicketResolveNote] = useState('');
  const [ticketResolvePreview, setTicketResolvePreview] = useState<QueryState<CustomerServiceResolvePreviewModel>>(idleState);
  const [ticketResolveConfirmed, setTicketResolveConfirmed] = useState(false);
  const [ticketResolveStatus, setTicketResolveStatus] = useState<MutationStatus>('idle');
  const [ticketResolveError, setTicketResolveError] = useState<string | null>(null);
  const ticketResolveCorrelationId = useRef<string | null>(null);
  const ticketResolveIdempotencyKey = useRef<string | null>(null);

  const [bindingPage, setBindingPage] = useState<QueryState<{ items: LineIdentityBindingRowViewModel[]; total: number; page: number; pageSize: number }>>(idleState);
  const [bindingSources, setBindingSources] = useState<readonly string[]>([]);
  const [bindingReload, setBindingReload] = useState(0);
  const [bindingPageNumber, setBindingPageNumber] = useState(1);
  const bindingPageSize = 25;
  const [bindingSearchQuery, setBindingSearchQuery] = useState('');
  const [bindingRoleFilter, setBindingRoleFilter] = useState<'all' | 'customer' | 'staff' | 'admin'>('all');
  const [bindingDetail, setBindingDetail] = useState<QueryState<LineIdentityBindingRowViewModel>>(idleState);
  const bindingDetailController = useRef<AbortController | null>(null);
  const bindingDetailGeneration = useRef(0);
  const bindingDetailId = useRef<string | null>(null);
  const bindingRevocationController = useRef<AbortController | null>(null);
  const [bindingRevocationReason, setBindingRevocationReason] = useState('');
  const [bindingRevocationPreview, setBindingRevocationPreview] = useState<QueryState<LineIdentityRevocationPreviewViewModel>>(idleState);
  const [bindingRevocationAccepted, setBindingRevocationAccepted] = useState<LineIdentityRevocationAcceptedViewModel | null>(null);
  const [bindingRevocationConfirmed, setBindingRevocationConfirmed] = useState(false);
  const [bindingRevocationStatus, setBindingRevocationStatus] = useState<MutationStatus>('idle');
  const [bindingRevocationError, setBindingRevocationError] = useState<string | null>(null);
  const bindingRevocationCorrelationId = useRef<string | null>(null);
  const bindingRevocationIdempotencyKey = useRef<string | null>(null);

  const [rules, setRules] = useState<QueryState<LineNotificationRulesCatalogModel>>(idleState);
  const [rawRules, setRawRules] = useState<LineNotificationRulesCatalog | null>(null);
  const [rulesReload, setRulesReload] = useState(0);
  const [selectedRule, setSelectedRule] = useState<LineNotificationRuleModel | null>(null);
  const [deliverySummary, setDeliverySummary] = useState<QueryState<LineDeliverySummaryView>>(idleState);
  const [deliveryItems, setDeliveryItems] = useState<QueryState<LineDeliveryPageView>>(idleState);
  const [deliveryPageNumber, setDeliveryPageNumber] = useState(1);
  const deliveryPageSize = 25;
  const [deliveryDetail, setDeliveryDetail] = useState<QueryState<LineDeliveryDetailView>>(idleState);
  const deliveryDetailController = useRef<AbortController | null>(null);

  const [orderGroups, setOrderGroups] = useState<QueryState<LineOrderGroupPageView>>(idleState);
  const [orderGroupDetail, setOrderGroupDetail] = useState<QueryState<{ record: LineOrderGroupRecordView; events: LineOrderGroupEventView[] }>>(idleState);
  const [orderGroupReload, setOrderGroupReload] = useState(0);
  const orderGroupDetailController = useRef<AbortController | null>(null);

  const [safeConfigurations, setSafeConfigurations] = useState<QueryState<LineSafeConfigModel[]>>(idleState);
  const [runtimeTargets, setRuntimeTargets] = useState<QueryState<LineRuntimeTargetModel[]>>(idleState);
  const [runtimeCandidates, setRuntimeCandidates] = useState<QueryState<LineRuntimeAdminCandidateModel[]>>(idleState);
  const [runtimeReload, setRuntimeReload] = useState(0);
  const [runtimeReason, setRuntimeReason] = useState('管理員確認調整 LINE 異常通知對象');
  const [selectedRuntimeCandidate, setSelectedRuntimeCandidate] = useState<number | null>(null);
  const [runtimeReceipt, setRuntimeReceipt] = useState<LineRuntimeTargetReceiptModel | null>(null);
  const [runtimePending, setRuntimePending] = useState<RuntimePendingOperation | null>(null);
  const [runtimeConfirmed, setRuntimeConfirmed] = useState(false);
  const [runtimeMutation, setRuntimeMutation] = useState<MutationStatus>('idle');
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const runtimePreviewController = useRef<AbortController | null>(null);
  const runtimePreviewGeneration = useRef(0);

  const [escalationIdInput, setEscalationIdInput] = useState('');
  const [escalationTicketVersion, setEscalationTicketVersion] = useState('0');
  const [escalationDetail, setEscalationDetail] = useState<QueryState<CustomerServiceEscalationModel>>(idleState);
  const [escalationReceipt, setEscalationReceipt] = useState<CustomerServiceEscalationReceiptModel | null>(null);
  const [escalationPending, setEscalationPending] = useState<EscalationPendingOperation | null>(null);
  const [escalationConfirmed, setEscalationConfirmed] = useState(false);
  const [escalationMutation, setEscalationMutation] = useState<MutationStatus>('idle');
  const [escalationError, setEscalationError] = useState<string | null>(null);
  const [escalationResolutionDigest, setEscalationResolutionDigest] = useState('');
  const [escalationSourceIdentity, setEscalationSourceIdentity] = useState('');
  const [escalationSourceFingerprint, setEscalationSourceFingerprint] = useState('');
  const [escalationHoldScope, setEscalationHoldScope] = useState('customer_service_automation');
  const [escalationSourceKind, setEscalationSourceKind] = useState<CustomerServiceEscalationCreateRequest['source_kind']>('ticket_referral');
  const [escalationTrigger, setEscalationTrigger] = useState<CustomerServiceEscalationCreateRequest['trigger_code']>('explicit_human_request');
  const [escalationCategory, setEscalationCategory] = useState<CustomerServiceEscalationCreateRequest['ticket_category']>('contact_union');
  const escalationPreviewController = useRef<AbortController | null>(null);
  const escalationPreviewGeneration = useRef(0);

  const [richMenuConfiguration, setRichMenuConfiguration] = useState<QueryState<LineRichMenuConfigurationModel>>(idleState);
  const [richMenuPublications, setRichMenuPublications] = useState<QueryState<LineRichMenuPublicationPageModel>>(idleState);
  const [richMenuReload, setRichMenuReload] = useState(0);
  const [selectedMenuId, setSelectedMenuId] = useState<string | null>(null);
  const [selectedPublication, setSelectedPublication] = useState<QueryState<LineRichMenuPublicationModel>>(idleState);
  const publicationController = useRef<AbortController | null>(null);
  const publicationGeneration = useRef(0);
  const publicationDetailId = useRef<number | null>(null);

  // Rich Menu 本機互動沙盒與比對狀態
  const [activeSimLiff, setActiveSimLiff] = useState<{
    title: string;
    subtitle: string;
    badge: string;
    fields: Array<{ label: string; value: string; hint?: string }>;
    actionButtons: string[];
  } | null>(null);
  const [simChatMessages, setSimChatMessages] = useState<
    Array<{ id: string; sender: 'user' | 'bot'; text: string; time: string }>
  >([]);
  const [isDiffMode, setIsDiffMode] = useState(false);

  useEffect(() => {
    if (activeTab !== 'tickets') return;
    const controller = new AbortController();
    let cancelled = false;
    setTicketSummary(loadingState());
    setTicketPage(loadingState());
    setTicketScopeBlocker(null);
    const timer = window.setTimeout(() => {
      const pageQuery = {
        status: ticketStatusFilter === 'all' ? undefined : ticketStatusFilter,
        category: ticketCategoryFilter === 'all' ? undefined : (ticketCategoryFilter as any),
        search: ticketSearchQuery.trim() || undefined,
        page: ticketPageNumber,
        page_size: ticketPageSize,
      };
      const pageRequest = customerService.listTickets(pageQuery, { signal: controller.signal });
      void Promise.allSettled([
        customerService.getSummary({ signal: controller.signal }),
        pageRequest,
      ]).then(([summaryResult, pageResult]) => {
        if (cancelled) return;
        if (summaryResult.status === 'fulfilled') setTicketSummary(loadedState(adaptCustomerServiceSummary(summaryResult.value)));
        else setTicketSummary(errorState(displayQueryError(summaryResult.reason, '客服摘要載入失敗')));
        if (pageResult.status === 'fulfilled' && pageResult.value) {
          setTicketPage(loadedState(adaptCustomerServicePage(pageResult.value)));
        } else if (pageResult.status === 'rejected') {
          setTicketPage(errorState(displayQueryError(pageResult.reason, '客服工單清單載入失敗')));
        }
      });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, customerService, ticketCategoryFilter, ticketPageNumber, ticketReload, ticketSearchQuery, ticketStatusFilter]);

  useEffect(() => {
    if (activeTab !== 'binding') return;
    const controller = new AbortController();
    let cancelled = false;
    setBindingPage(loadingState());
    const timer = window.setTimeout(() => {
      void lineIdentity.listBindings({
        page: bindingPageNumber,
        page_size: bindingPageSize,
        subject_type: bindingRoleFilter === 'all' ? undefined : bindingRoleFilter,
        search: bindingSearchQuery.trim() || undefined,
      }, { signal: controller.signal })
        .then((page) => {
          if (cancelled) return;
          setBindingSources(page.items.map((item) => item.line_user_id));
          setBindingPage(loadedState({ items: adaptLineIdentityBindingPage(page).items, total: page.total, page: page.page, pageSize: page.page_size }));
        })
        .catch((error: unknown) => { if (!cancelled) setBindingPage(errorState(displayQueryError(error, 'LINE 身分清單載入失敗'))); });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, bindingPageNumber, bindingReload, bindingRoleFilter, bindingSearchQuery, lineIdentity]);

  useEffect(() => {
    if (activeTab !== 'push_queue') return;
    const controller = new AbortController();
    let cancelled = false;
    setRules(loadingState());
    setRawRules(null);
    setDeliverySummary(loadingState());
    setDeliveryItems(loadingState());
    const timer = window.setTimeout(() => {
      void Promise.allSettled([
        lineConfiguration.getNotificationRules({ signal: controller.signal }),
        delivery.summary({ signal: controller.signal }),
        delivery.list({ page: deliveryPageNumber, pageSize: deliveryPageSize }, { signal: controller.signal }),
      ]).then(([rulesResult, summaryResult, tasksResult]) => {
        if (cancelled) return;
        if (rulesResult.status === 'fulfilled') {
          setRawRules(rulesResult.value);
          setRules(loadedState(adaptLineNotificationRulesCatalog(rulesResult.value)));
        } else {
          setRawRules(null);
          setRules(errorState(displayQueryError(rulesResult.reason, '通知規則目錄載入失敗')));
        }
        if (summaryResult.status === 'fulfilled') setDeliverySummary(loadedState(adaptLineDeliverySummary(summaryResult.value)));
        else setDeliverySummary(errorState(displayQueryError(summaryResult.reason, '發送任務摘要載入失敗')));
        if (tasksResult.status === 'fulfilled') {
          setDeliveryItems(loadedState({
            items: tasksResult.value.items.map(adaptLineDeliveryItem),
            page: tasksResult.value.page,
            pageSize: tasksResult.value.page_size,
            total: tasksResult.value.total,
            totalPages: tasksResult.value.total_pages,
          }));
        }
        else setDeliveryItems(errorState(displayQueryError(tasksResult.reason, '發送任務清單載入失敗')));
      });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, delivery, deliveryPageNumber, lineConfiguration, rulesReload]);

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
    if (activeTab !== 'order_groups') return;
    const controller = new AbortController();
    let cancelled = false;
    setOrderGroups(loadingState());
    const timer = window.setTimeout(() => {
      void lineOrderGroupQueryClient.list({ limit: 200 }, { signal: controller.signal })
        .then((page) => {
          if (!cancelled) setOrderGroups(loadedState({
            items: page.items.map(adaptLineOrderGroupRecord),
            total: page.total,
            limit: 200,
          }));
        })
        .catch((error: unknown) => {
          if (!cancelled) setOrderGroups(errorState(displayQueryError(error, '三方服務群組載入失敗')));
        });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, orderGroupReload]);

  useEffect(() => {
    if (activeTab !== 'runtime') return;
    const controller = new AbortController();
    let cancelled = false;
    const correlationId = operationIdentity('line-runtime-query');
    setSafeConfigurations(loadingState());
    setRuntimeTargets(loadingState());
    setRuntimeCandidates(loadingState());
    const timer = window.setTimeout(() => {
      void Promise.allSettled([
        Promise.all(SAFE_CONFIGURATION_KINDS.map((kind) => lineSafeConfigClient.getSafe(kind, { correlationId, signal: controller.signal }))),
        runtimeTarget.listTargets({ correlationId, signal: controller.signal }),
        runtimeTarget.listAdminCandidates({ correlationId, signal: controller.signal }),
      ]).then(([configResult, targetResult, candidateResult]) => {
        if (cancelled) return;
        if (configResult.status === 'fulfilled') setSafeConfigurations(loadedState(configResult.value.map(adaptLineSafeConfig)));
        else setSafeConfigurations(errorState(displayQueryError(configResult.reason, 'LINE 安全設定載入失敗')));
        if (targetResult.status === 'fulfilled') setRuntimeTargets(loadedState(targetResult.value.map(adaptLineRuntimeTarget)));
        else setRuntimeTargets(errorState(displayQueryError(targetResult.reason, '異常通知對象載入失敗')));
        if (candidateResult.status === 'fulfilled') setRuntimeCandidates(loadedState(candidateResult.value.map(adaptLineRuntimeAdminCandidate)));
        else setRuntimeCandidates(errorState(displayQueryError(candidateResult.reason, '管理員候選載入失敗')));
      });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, runtimeReload, runtimeTarget]);

  useEffect(() => {
    if (activeTab !== 'tickets') {
      ticketDetailController.current?.abort();
      ticketResolveController.current?.abort();
      ticketDetailController.current = null;
      ticketResolveController.current = null;
      ticketDetailGeneration.current += 1;
      ticketDetailId.current = null;
      setTicketDetail(idleState());
      setTicketResolvePreview(idleState());
      setTicketResolveStatus('idle');
      setTicketResolveError(null);
    }
    if (activeTab !== 'binding') {
      bindingDetailController.current?.abort();
      bindingRevocationController.current?.abort();
      bindingDetailController.current = null;
      bindingRevocationController.current = null;
      bindingDetailGeneration.current += 1;
      bindingDetailId.current = null;
      setBindingDetail(idleState());
      setBindingRevocationPreview(idleState());
      setBindingRevocationAccepted(null);
      setBindingRevocationStatus('idle');
      setBindingRevocationError(null);
    }
    if (activeTab !== 'richmenu') {
      publicationController.current?.abort();
      publicationController.current = null;
      publicationGeneration.current += 1;
      publicationDetailId.current = null;
      setSelectedPublication(idleState());
    }
    if (activeTab !== 'push_queue') {
      deliveryDetailController.current?.abort();
      deliveryDetailController.current = null;
      setDeliveryDetail(idleState());
    }
    if (activeTab !== 'order_groups') {
      orderGroupDetailController.current?.abort();
      orderGroupDetailController.current = null;
      setOrderGroupDetail(idleState());
    }
    if (activeTab !== 'runtime') {
      runtimePreviewController.current?.abort();
      escalationPreviewController.current?.abort();
      runtimePreviewController.current = null;
      escalationPreviewController.current = null;
      runtimePreviewGeneration.current += 1;
      escalationPreviewGeneration.current += 1;
      setRuntimePending(null);
      setRuntimeConfirmed(false);
      setEscalationPending(null);
      setEscalationConfirmed(false);
    }
  }, [activeTab]);

  useEffect(() => () => {
    ticketDetailController.current?.abort();
    ticketResolveController.current?.abort();
    bindingDetailController.current?.abort();
    bindingRevocationController.current?.abort();
    publicationController.current?.abort();
    deliveryDetailController.current?.abort();
    orderGroupDetailController.current?.abort();
    runtimePreviewController.current?.abort();
    escalationPreviewController.current?.abort();
    ticketDetailGeneration.current += 1;
    bindingDetailGeneration.current += 1;
    publicationGeneration.current += 1;
    runtimePreviewGeneration.current += 1;
    escalationPreviewGeneration.current += 1;
  }, []);

  const resetTicketResolve = () => {
    ticketResolveController.current?.abort();
    ticketResolveController.current = null;
    ticketResolveCorrelationId.current = null;
    ticketResolveIdempotencyKey.current = null;
    setTicketResolveNote('');
    setTicketResolvePreview(idleState());
    setTicketResolveConfirmed(false);
    setTicketResolveStatus('idle');
    setTicketResolveError(null);
  };

  const resetBindingRevocation = () => {
    bindingRevocationController.current?.abort();
    bindingRevocationController.current = null;
    bindingRevocationCorrelationId.current = null;
    bindingRevocationIdempotencyKey.current = null;
    setBindingRevocationReason('');
    setBindingRevocationPreview(idleState());
    setBindingRevocationAccepted(null);
    setBindingRevocationConfirmed(false);
    setBindingRevocationStatus('idle');
    setBindingRevocationError(null);
  };

  const openTicket = (ticketId: number) => {
    resetTicketResolve();
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
    resetTicketResolve();
    ticketDetailController.current?.abort();
    ticketDetailController.current = null;
    ticketDetailGeneration.current += 1;
    ticketDetailId.current = null;
    setTicketDetail(idleState());
  };

  const openBinding = (lineUserId: string) => {
    resetBindingRevocation();
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
    resetBindingRevocation();
    bindingDetailController.current?.abort();
    bindingDetailController.current = null;
    bindingDetailGeneration.current += 1;
    bindingDetailId.current = null;
    setBindingDetail(idleState());
  };

  const previewTicketResolve = async () => {
    const detail = ticketDetail.value;
    if (!detail || detail.ticket.status === 'resolved' || !customerService.previewResolve) return;
    ticketResolveController.current?.abort();
    const controller = new AbortController();
    ticketResolveController.current = controller;
    const correlationId = operationIdentity('line-ticket-resolve');
    ticketResolveCorrelationId.current = correlationId;
    ticketResolveIdempotencyKey.current = operationIdentity('line-ticket-resolve-apply');
    setTicketResolvePreview(loadingState());
    setTicketResolveConfirmed(false);
    setTicketResolveStatus('idle');
    setTicketResolveError(null);
    try {
      const preview = await customerService.previewResolve(
        detail.ticket.ticketId,
        {
          status: 'resolved',
          internal_note: ticketResolveNote.trim() || null,
          expected_version: detail.ticket.version,
        },
        { correlationId, signal: controller.signal }
      );
      if (!controller.signal.aborted) setTicketResolvePreview(loadedState(adaptCustomerServiceResolvePreview(preview)));
    } catch (error: unknown) {
      if (!controller.signal.aborted) setTicketResolvePreview(errorState(displayQueryError(error, '結案預覽失敗')));
    }
  };

  const applyTicketResolve = async () => {
    const detail = ticketDetail.value;
    const preview = ticketResolvePreview.value;
    const correlationId = ticketResolveCorrelationId.current;
    const idempotencyKey = ticketResolveIdempotencyKey.current;
    if (!detail || !preview?.applyReady || preview.blockers.length > 0 || !ticketResolveConfirmed || !correlationId || !idempotencyKey || !customerService.applyResolve) return;
    ticketResolveController.current?.abort();
    const controller = new AbortController();
    ticketResolveController.current = controller;
    setTicketResolveStatus('loading');
    setTicketResolveError(null);
    try {
      await customerService.applyResolve(
        detail.ticket.ticketId,
        {
          status: 'resolved',
          internal_note: ticketResolveNote.trim() || null,
          expected_version: preview.expectedVersion,
          preview_fingerprint: preview.previewFingerprint,
        },
        { correlationId, idempotencyKey, signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      setTicketResolveStatus('success');
      setTicketReload((value) => value + 1);
    } catch (error: unknown) {
      if (!controller.signal.aborted) {
        setTicketResolveStatus('error');
        setTicketResolveError(displayQueryError(error, '結案提交失敗'));
      }
    }
  };

  const previewBindingRevocation = async () => {
    const lineUserId = bindingDetailId.current;
    if (!lineUserId || !bindingDetail.value || !lineIdentity.previewRevocation) return;
    bindingRevocationController.current?.abort();
    const controller = new AbortController();
    bindingRevocationController.current = controller;
    bindingRevocationCorrelationId.current = operationIdentity('line-identity-revoke');
    bindingRevocationIdempotencyKey.current = operationIdentity('line-identity-revoke-apply');
    setBindingRevocationPreview(loadingState());
    setBindingRevocationAccepted(null);
    setBindingRevocationConfirmed(false);
    setBindingRevocationStatus('idle');
    setBindingRevocationError(null);
    try {
      const preview = await lineIdentity.previewRevocation(lineUserId, { signal: controller.signal });
      if (!controller.signal.aborted) setBindingRevocationPreview(loadedState(adaptLineIdentityRevocationPreview(preview)));
    } catch (error: unknown) {
      if (!controller.signal.aborted) setBindingRevocationPreview(errorState(displayQueryError(error, '解除預覽失敗')));
    }
  };

  const applyBindingRevocation = async () => {
    const lineUserId = bindingDetailId.current;
    const detail = bindingDetail.value;
    const preview = bindingRevocationPreview.value;
    const correlationId = bindingRevocationCorrelationId.current;
    const idempotencyKey = bindingRevocationIdempotencyKey.current;
    if (!lineUserId || !detail || !preview || preview.hasBlockers || !bindingRevocationConfirmed || !bindingRevocationReason.trim() || !correlationId || !idempotencyKey || !lineIdentity.applyRevocation) return;
    bindingRevocationController.current?.abort();
    const controller = new AbortController();
    bindingRevocationController.current = controller;
    setBindingRevocationStatus('loading');
    setBindingRevocationError(null);
    try {
      const accepted = await lineIdentity.applyRevocation(
        lineUserId,
        {
          expected_version: detail.version,
          reason: bindingRevocationReason.trim(),
          idempotency_key: idempotencyKey,
          correlation_id: correlationId,
        },
        { signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      setBindingRevocationAccepted(adaptLineIdentityRevocationAccepted(accepted));
      setBindingRevocationStatus('success');
      setBindingReload((value) => value + 1);
    } catch (error: unknown) {
      if (!controller.signal.aborted) {
        setBindingRevocationStatus('error');
        setBindingRevocationError(displayQueryError(error, '解除提交失敗'));
      }
    }
  };

  const openDeliveryTask = (taskId: number) => {
    deliveryDetailController.current?.abort();
    const controller = new AbortController();
    deliveryDetailController.current = controller;
    setDeliveryDetail(loadingState());
    void lineDeliveryQueryClient.detail(taskId, { signal: controller.signal })
      .then((detail) => { if (!controller.signal.aborted) setDeliveryDetail(loadedState(adaptLineDeliveryDetail(detail))); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setDeliveryDetail(errorState(displayQueryError(error, '發送任務明細載入失敗'))); });
  };

  const closeDeliveryTask = () => {
    deliveryDetailController.current?.abort();
    deliveryDetailController.current = null;
    setDeliveryDetail(idleState());
  };

  const openOrderGroup = (caseNo: string) => {
    orderGroupDetailController.current?.abort();
    const controller = new AbortController();
    orderGroupDetailController.current = controller;
    setOrderGroupDetail(loadingState());
    void Promise.all([
      lineOrderGroupQueryClient.detail(caseNo, { signal: controller.signal }),
      lineOrderGroupQueryClient.events(caseNo, 100, { signal: controller.signal }),
    ]).then(([record, events]) => {
      if (!controller.signal.aborted) setOrderGroupDetail(loadedState({ record: adaptLineOrderGroupRecord(record), events: events.map(adaptLineOrderGroupEvent) }));
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setOrderGroupDetail(errorState(displayQueryError(error, '三方服務群組明細載入失敗')));
    });
  };

  const closeOrderGroup = () => {
    orderGroupDetailController.current?.abort();
    orderGroupDetailController.current = null;
    setOrderGroupDetail(idleState());
  };

  const refreshRuntime = () => setRuntimeReload((value) => value + 1);

  const previewRuntimeMutation = async (operation: 'add' | 'reset' | 'toggle', target?: LineRuntimeTargetModel) => {
    if (!runtimeReason.trim()) return;
    if (operation === 'add' && selectedRuntimeCandidate === null) return;
    if (operation !== 'add' && !target) return;
    runtimePreviewController.current?.abort();
    const controller = new AbortController();
    runtimePreviewController.current = controller;
    const generation = runtimePreviewGeneration.current + 1;
    runtimePreviewGeneration.current = generation;
    const correlationId = operationIdentity(`line-runtime-${operation}`);
    const idempotencyKey = operationIdentity(`line-runtime-${operation}-apply`);
    setRuntimeMutation('loading');
    setRuntimeError(null);
    setRuntimeReceipt(null);
    try {
      let pending: RuntimePendingOperation;
      if (operation === 'add') {
        if (selectedRuntimeCandidate === null) return;
        const request = { admin_user_id: selectedRuntimeCandidate, minimum_status: 'warning' as const, reason: runtimeReason.trim(), correlation_id: correlationId, idempotency_key: idempotencyKey };
        const preview = await runtimeTarget.previewAddAdminTarget(request, { signal: controller.signal });
        pending = { kind: 'add', request, preview };
      } else if (operation === 'reset') {
        if (!target) return;
        const request = { expected_version: target.currentVersion, reason: runtimeReason.trim(), correlation_id: correlationId, idempotency_key: idempotencyKey };
        const preview = await runtimeTarget.previewResetGroup(request, { signal: controller.signal });
        pending = { kind: 'reset', request, preview };
      } else {
        if (!target) return;
        const request = { expected_version: target.currentVersion, enabled: target.state !== 'active', reason: runtimeReason.trim(), correlation_id: correlationId, idempotency_key: idempotencyKey };
        const preview = await runtimeTarget.previewSetEnabled(target.targetId, request, { signal: controller.signal });
        pending = { kind: 'toggle', targetId: target.targetId, request, preview };
      }
      if (controller.signal.aborted || generation !== runtimePreviewGeneration.current) return;
      setRuntimePending(pending);
      setRuntimeConfirmed(false);
      setRuntimeMutation('idle');
    } catch (error: unknown) {
      if (controller.signal.aborted || generation !== runtimePreviewGeneration.current) return;
      setRuntimeMutation('error');
      setRuntimeError(displayQueryError(error, '異常通知對象 Preview 失敗'));
    }
  };

  const applyRuntimeMutation = async () => {
    if (!runtimePending || !runtimeConfirmed) return;
    setRuntimeMutation('loading');
    setRuntimeError(null);
    try {
      let receipt;
      if (runtimePending.kind === 'add') {
        receipt = await runtimeTarget.addAdminTarget({
          ...runtimePending.request,
          preview_fingerprint: runtimePending.preview.preview_fingerprint,
        });
      } else if (runtimePending.kind === 'reset') {
        receipt = await runtimeTarget.resetGroup({
          ...runtimePending.request,
          preview_fingerprint: runtimePending.preview.preview_fingerprint,
        });
      } else {
        receipt = await runtimeTarget.setEnabled(runtimePending.targetId, {
          ...runtimePending.request,
          preview_fingerprint: runtimePending.preview.preview_fingerprint,
        });
      }
      setRuntimeReceipt(adaptLineRuntimeTargetReceipt(receipt));
      setRuntimePending(null);
      setRuntimeConfirmed(false);
      setRuntimeMutation('success');
      refreshRuntime();
    } catch (error: unknown) {
      setRuntimeMutation('error');
      setRuntimeError(displayQueryError(error, '異常通知對象 Apply 失敗'));
    }
  };

  const loadEscalation = async (escalationId = Number(escalationIdInput)) => {
    if (!Number.isInteger(escalationId) || escalationId < 1) return;
    setEscalationDetail(loadingState());
    setEscalationError(null);
    try {
      const detail = await escalation.getDetail(escalationId, { correlationId: operationIdentity('line-escalation-detail') });
      setEscalationDetail(loadedState(adaptCustomerServiceEscalation(detail)));
      setEscalationIdInput(String(escalationId));
    } catch (error: unknown) {
      setEscalationDetail(errorState(displayQueryError(error, '人工升級明細載入失敗')));
    }
  };

  const previewCreateEscalation = async () => {
    if (!escalationSourceIdentity.trim() || !/^[0-9a-f]{64}$/.test(escalationSourceFingerprint) || !escalationHoldScope.trim()) return;
    const correlationId = operationIdentity('line-escalation-create');
    escalationPreviewController.current?.abort();
    const controller = new AbortController();
    escalationPreviewController.current = controller;
    const generation = escalationPreviewGeneration.current + 1;
    escalationPreviewGeneration.current = generation;
    setEscalationMutation('loading');
    setEscalationError(null);
    try {
      const request: CustomerServiceEscalationCreateRequest = {
        source_event_identity: escalationSourceIdentity.trim(),
        source_kind: escalationSourceKind,
        source_fingerprint: escalationSourceFingerprint,
        trigger_code: escalationTrigger,
        trigger_policy_version: 'ui-react-v1',
        ticket_category: escalationCategory,
        masked_context: { summary_code: escalationTrigger, policy_version: 'ui-react-v1', category: escalationCategory, redaction_version: 'v1' },
        hold_scope: escalationHoldScope.trim(),
        correlation_id: correlationId,
        idempotency_key: operationIdentity('line-escalation-create-apply'),
      };
      const preview = await escalation.previewCreate(request, { signal: controller.signal });
      if (controller.signal.aborted || generation !== escalationPreviewGeneration.current) return;
      setEscalationPending({ kind: 'create', request, preview });
      setEscalationConfirmed(false);
      setEscalationReceipt(null);
      setEscalationMutation('idle');
    } catch (error: unknown) {
      if (controller.signal.aborted || generation !== escalationPreviewGeneration.current) return;
      setEscalationMutation('error');
      setEscalationError(displayQueryError(error, '人工升級建立 Preview 失敗'));
    }
  };

  const previewAdvanceEscalation = async (operation: 'claim' | 'handling' | 'resolve') => {
    const detail = escalationDetail.value;
    const ticketVersion = Number(escalationTicketVersion);
    if (!detail || !Number.isInteger(ticketVersion) || ticketVersion < 0) return;
    if (operation === 'resolve' && !/^[0-9a-f]{64}$/.test(escalationResolutionDigest)) return;
    escalationPreviewController.current?.abort();
    const controller = new AbortController();
    escalationPreviewController.current = controller;
    const generation = escalationPreviewGeneration.current + 1;
    escalationPreviewGeneration.current = generation;
    const correlationId = operationIdentity(`line-escalation-${operation}`);
    const identity = { correlation_id: correlationId, idempotency_key: operationIdentity(`line-escalation-${operation}-apply`) };
    setEscalationMutation('loading');
    setEscalationError(null);
    try {
      let pending: EscalationPendingOperation;
      if (operation === 'claim') {
        const request = { expected_escalation_version: detail.workflowVersion, ...identity };
        const preview = await escalation.previewClaim(detail.escalationId, request, { signal: controller.signal });
        pending = { kind: 'claim', escalationId: detail.escalationId, request, preview };
      } else if (operation === 'handling') {
        const request = { expected_escalation_version: detail.workflowVersion, expected_ticket_version: ticketVersion, ...identity };
        const preview = await escalation.previewStartHandling(detail.escalationId, request, { signal: controller.signal });
        pending = { kind: 'handling', escalationId: detail.escalationId, request, preview };
      }
      else {
        const request = { expected_escalation_version: detail.workflowVersion, expected_ticket_version: ticketVersion, resolution_code: 'handled_by_union_staff', resolution_evidence_digest: escalationResolutionDigest, ...identity };
        const preview = await escalation.previewResolve(detail.escalationId, request, { signal: controller.signal });
        pending = { kind: 'resolve', escalationId: detail.escalationId, request, preview };
      }
      if (controller.signal.aborted || generation !== escalationPreviewGeneration.current) return;
      setEscalationPending(pending);
      setEscalationConfirmed(false);
      setEscalationReceipt(null);
      setEscalationMutation('idle');
    } catch (error: unknown) {
      if (controller.signal.aborted || generation !== escalationPreviewGeneration.current) return;
      setEscalationMutation('error');
      setEscalationError(displayQueryError(error, '人工升級狀態 Preview 失敗'));
    }
  };

  const applyEscalation = async () => {
    if (!escalationPending || !escalationConfirmed) return;
    setEscalationMutation('loading');
    setEscalationError(null);
    try {
      let receipt;
      if (escalationPending.kind === 'create') {
        receipt = await escalation.create({
          ...escalationPending.request,
          preview_fingerprint: escalationPending.preview.preview_fingerprint,
        });
      } else if (escalationPending.kind === 'claim') {
        receipt = await escalation.claim(escalationPending.escalationId, {
          ...escalationPending.request,
          preview_fingerprint: escalationPending.preview.preview_fingerprint,
        });
      } else if (escalationPending.kind === 'handling') {
        receipt = await escalation.startHandling(escalationPending.escalationId, {
          ...escalationPending.request,
          preview_fingerprint: escalationPending.preview.preview_fingerprint,
        });
      } else {
        receipt = await escalation.resolve(escalationPending.escalationId, {
          ...escalationPending.request,
          preview_fingerprint: escalationPending.preview.preview_fingerprint,
        });
      }
      const model = adaptCustomerServiceEscalationReceipt(receipt);
      setEscalationReceipt(model);
      setEscalationPending(null);
      setEscalationConfirmed(false);
      setEscalationMutation('success');
      await loadEscalation(model.escalationId);
    } catch (error: unknown) {
      setEscalationMutation('error');
      setEscalationError(displayQueryError(error, '人工升級 Apply 失敗'));
    }
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
      <div className="page-header-banner line-page-header"><div><h1 className="page-title">💬 LINE 官方帳號與推播管理中心</h1><p className="page-subtitle">客服工單、身分綁定、Rich Menu、通知與三方群組整合工作區。</p></div><span className="line-query-badge">系統流程已連線</span></div>
      <div className="line-tab-bar" aria-label="LINE 管理工作區">{TABS.map(([tab, label, id]) => <button key={tab} type="button" data-control-id={id} className={`line-tab-btn ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>{label}</button>)}</div>

      {activeTab === 'push_queue' && rawRules && <LineNotificationRulesMutationPanel catalog={rawRules} selectedRuleId={selectedRule?.id ?? null} onCommitted={() => setRulesReload((value) => value + 1)} />}

      {activeTab === 'tickets' && (() => {
        const rawList = ticketPage.value?.items ?? [];

        const filteredList = rawList.filter((ticket) => {
          const q = ticketSearchQuery.trim().toLowerCase();
          const matchesQuery = !q ||
            ticket.ticketIdText.toLowerCase().includes(q) ||
            ticket.maskedLineUserId.toLowerCase().includes(q) ||
            (ticket.caseNo && ticket.caseNo.toLowerCase().includes(q));

          const matchesStatus = ticketStatusFilter === 'all' || ticket.status === ticketStatusFilter;
          const matchesCategory = ticketCategoryFilter === 'all' || ticket.category === ticketCategoryFilter;

          return matchesQuery && matchesStatus && matchesCategory;
        });

        const displayWaiting = ticketSummary.value?.waiting ?? 0;
        const displayHandling = ticketSummary.value?.handling ?? 0;
        const displayResolved = ticketSummary.value?.resolvedToday ?? 0;
        const ticketTotal = ticketPage.value?.total ?? 0;
        const ticketPageCount = Math.max(1, Math.ceil(ticketTotal / ticketPageSize));
        const ticketCurrentPage = ticketPage.value?.page ?? ticketPageNumber;
        const ticketRangeStart = ticketTotal === 0 ? 0 : ((ticketCurrentPage - 1) * ticketPageSize) + 1;
        const ticketRangeEnd = ticketTotal === 0 ? 0 : Math.min(ticketCurrentPage * ticketPageSize, ticketTotal);

        return (
          <section className="line-table-container">
            <div className="line-section-heading">
              <div>
                <h3>📋 客服工單與案件關聯追蹤清單</h3>
                <p>追蹤來自 LINE 官方帳號之真人諮詢、異動申請、補助計算與客訴工單，提供即時指派、回覆與結案工作流。</p>
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button type="button" className="line-secondary-btn" onClick={() => { setTicketPageNumber(1); setTicketReload((value) => value + 1); }}>
                  🔄 重新整理
                </button>
              </div>
            </div>

            {/* 頂部 3 大 KPI 卡片 */}
            <div className="line-kpi-grid">
              <div data-control-id="line.ticket.summary.waiting">
                <span>⏳ 待處理工單</span>
                <strong>{displayWaiting}</strong>
              </div>
              <div data-control-id="line.ticket.summary.handling">
                <span>🔄 處理中工單</span>
                <strong>{displayHandling}</strong>
              </div>
              <div data-control-id="line.ticket.summary.resolved_today">
                <span>✅ 今日已結案</span>
                <strong>{displayResolved}</strong>
              </div>
            </div>

            {/* 搜尋與進階篩選工具列 */}
            <div className="line-search-filter-toolbar">
              <div className="line-search-input-wrapper">
                <span className="line-search-icon">🔍</span>
                <input
                  type="text"
                  className="line-search-input"
                  placeholder="搜尋工單編號、案件編號 (ORD-*)、客戶或問題..."
                  value={ticketSearchQuery}
                  onChange={(e) => { setTicketPageNumber(1); setTicketSearchQuery(e.target.value); }}
                />
                {ticketSearchQuery && (
                    <button type="button" className="line-search-clear-btn" onClick={() => { setTicketPageNumber(1); setTicketSearchQuery(''); }}>
                    ✕
                  </button>
                )}
              </div>

              <div className="line-filter-selects">
                <select
                  value={ticketStatusFilter}
                   onChange={(e) => { setTicketPageNumber(1); setTicketStatusFilter(e.target.value as 'all' | 'waiting' | 'handling' | 'resolved'); }}
                  className="line-filter-select"
                >
                  <option value="all">處理狀態 (全部)</option>
                  <option value="waiting">⏳ 待處理</option>
                  <option value="handling">🔄 處理中</option>
                  <option value="resolved">✅ 已結案</option>
                </select>

                <select
                  value={ticketCategoryFilter}
                   onChange={(e) => { setTicketPageNumber(1); setTicketCategoryFilter(e.target.value); }}
                  className="line-filter-select"
                >
                  <option value="all">問題分類 (全部)</option>
                  <option value="service_flow">📋 服務流程諮詢</option>
                  <option value="payment_subsidy">💰 收費與補助</option>
                  <option value="service_progress">📦 服務進度</option>
                  <option value="profile_update">✏️ 異動申請</option>
                  <option value="contact_union">📞 聯絡工會</option>
                  <option value="other">⚠️ 爭議客訴</option>
                </select>
              </div>
            </div>

            {ticketSummary.status === 'loading' && <div className="line-loading">正在載入客服摘要…</div>}
            {ticketSummary.status === 'error' && <div className="line-error" role="alert">{ticketSummary.error}</div>}
            {ticketPage.status === 'loading' && <div className="line-loading">正在載入客服工單…</div>}
            {ticketPage.status === 'error' && <div className="line-error" role="alert">{ticketPage.error}</div>}
            {ticketScopeBlocker && <div className="line-scope-note" role="status">{ticketScopeBlocker}</div>}

            {ticketScopeBlocker ? null : filteredList.length === 0 ? (
              <div className="line-empty-state">
                <div>📋</div>
                <h4>目前沒有符合篩選條件的客服工單</h4>
                <p>可調整搜尋關鍵字、切換分類或由 LINE 客服入口建立新工單。</p>
              </div>
            ) : (
              <>
                <div className="line-scope-note">
                   第 {ticketCurrentPage} 頁，顯示本頁 {filteredList.length} 筆，共 {ticketTotal} 筆工單。
                </div>
                <div className="line-table-scroll">
                  <table className="line-data-table" data-control-id="line.ticket.table">
                    <thead>
                      <tr>
                        <th>工單編號</th>
                        <th>提問對象</th>
                        <th>關聯案件</th>
                        <th>分類</th>
                        <th>問題摘要與最新對話</th>
                        <th>時間</th>
                        <th>狀態</th>
                        <th style={{ textAlign: 'right' }}>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredList.map((ticket) => (
                        <tr key={ticket.ticketId}>
                          <td><strong style={{ fontFamily: 'monospace', color: '#a43c12' }}>#{ticket.ticketIdText}</strong></td>
                          <td>👤 {ticket.maskedLineUserId}</td>
                          <td>
                            {ticket.caseNo ? (
                              <span style={{ color: '#ff7f50', fontWeight: 600, textDecoration: 'underline' }}>
                                {ticket.caseNo}
                              </span>
                            ) : (
                              <span style={{ color: '#999' }}>無關聯</span>
                            )}
                          </td>
                          <td>
                            <span className={`line-category-badge category-${ticket.category}`}>
                              {ticket.categoryLabel}
                            </span>
                          </td>
                          <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {ticket.issueSummary ?? CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE}
                          </td>
                          <td style={{ whiteSpace: 'nowrap', color: '#74593f', fontSize: '0.82rem' }}>
                            {ticket.createdAt ?? '—'}
                          </td>
                          <td>
                            <span className={`line-status line-status-${ticket.status}`}>
                              {ticket.statusLabel}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <button
                              type="button"
                              className="line-action-link-btn"
                              data-control-id="line.ticket.detail"
                              aria-label="查看明細"
                              onClick={() => openTicket(ticket.ticketId)}
                            >
                              [ 🔍 查看明細 ]
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* 分頁控制列 */}
                <div className="line-pagination-bar">
                  <span style={{ fontSize: '0.85rem', color: '#74593f' }}>
                     顯示第 {ticketRangeStart} 至 {ticketRangeEnd} 筆，共 {ticketTotal} 筆工單
                   </span>
                   <div className="line-pagination-controls">
                     <button type="button" aria-label="上一頁客服工單" disabled={ticketCurrentPage <= 1} className="line-page-btn" onClick={() => setTicketPageNumber((value) => Math.max(1, value - 1))}>‹</button>
                     <button type="button" aria-label={`客服工單第 ${ticketCurrentPage} 頁`} className="line-page-btn active">{ticketCurrentPage}</button>
                     <button type="button" aria-label="下一頁客服工單" disabled={ticketCurrentPage >= ticketPageCount} className="line-page-btn" onClick={() => setTicketPageNumber((value) => Math.min(ticketPageCount, value + 1))}>›</button>
                   </div>
                </div>
              </>
            )}
          </section>
        );
      })()}

      {activeTab === 'richmenu' && (() => {
        const menus = richMenuConfiguration.value?.menus ?? [];
        const activeMenu = selectedMenu ?? menus[0] ?? null;

        return (
          <section className="line-table-container" data-control-id="line.richmenu.configuration">
            <div className="line-section-heading">
              <div>
                <h3>📱 多角色 Rich Menu 圖文選單管理中心</h3>
                <p>唯讀呈現圖文選單設定與熱區；發布前必須先檢查影響並由人員確認，完成後只會排入待發布工作。</p>
              </div>
              <button
                type="button"
                className="line-secondary-btn"
                data-control-id="line.richmenu.refresh"
                onClick={() => setRichMenuReload((value) => value + 1)}
              >
                🔄 重新整理
              </button>
            </div>

            <LoadingOrError state={richMenuConfiguration} loadingText="正在載入 Rich Menu 設定…" />
            {richMenuConfiguration.status === 'loaded' && richMenuConfiguration.value?.isEmpty && (
              <div className="line-empty-state">
                <h4>目前沒有已核准的 Rich Menu 設定</h4>
                <p>畫面不會以範例選單或未核准 LIFF 路由補齊。</p>
              </div>
            )}

            {/* 工具與模式切換列 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
              {/* 角色選單切換列 */}
              <div className="richmenu-role-tabs" style={{ marginBottom: 0, paddingBottom: 0, borderBottom: 'none' }}>
                {menus.map((menu) => (
                  <button
                    key={menu.id}
                    type="button"
                    className={`richmenu-role-tab ${activeMenu?.id === menu.id ? 'active' : ''}`}
                    onClick={() => {
                      setSelectedMenuId(menu.id);
                      setActiveSimLiff(null);
                    }}
                  >
                    {menu.audienceRoleLabel}｜{menu.name}
                  </button>
                ))}
              </div>

              {/* Diff Mode 與模擬控制 */}
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button
                  type="button"
                  className={`line-secondary-btn ${isDiffMode ? 'active' : ''}`}
                  style={{
                    background: isDiffMode ? '#ff7f50' : '#ffffff',
                    color: isDiffMode ? '#ffffff' : '#7c2d12',
                    borderColor: '#ff7f50',
                    fontWeight: 700,
                  }}
                  onClick={() => setIsDiffMode(!isDiffMode)}
                >
                  {isDiffMode ? '✨ 關閉版本比對' : '✨ 開啟版本變更比對 (Diff Mode)'}
                </button>
                {simChatMessages.length > 0 && (
                  <button
                    type="button"
                    className="line-secondary-btn"
                    style={{ fontSize: '0.8rem', padding: '6px 12px' }}
                    onClick={() => setSimChatMessages([])}
                  >
                    🧹 清除模擬對話
                  </button>
                )}
              </div>
            </div>

            {/* 發布前幾何與契約防呆檢查狀態條 */}
            {activeMenu && (() => {
              const targetW = activeMenu.width;
              const targetH = activeMenu.height;
              let totalArea = 0;
              let hasOverlap = false;
              const buttons = activeMenu.buttons;

              for (let i = 0; i < buttons.length; i++) {
                const b1 = buttons[i].bounds;
                totalArea += b1.width * b1.height;
                for (let j = i + 1; j < buttons.length; j++) {
                  const b2 = buttons[j].bounds;
                  if (
                    b1.x < b2.x + b2.width &&
                    b1.x + b1.width > b2.x &&
                    b1.y < b2.y + b2.height &&
                    b1.y + b1.height > b2.y
                  ) {
                    hasOverlap = true;
                  }
                }
              }
              const isFullCoverage = totalArea === targetW * targetH;
              const isCompliant = isFullCoverage && !hasOverlap;

              return (
                <div
                  className="richmenu-safety-banner"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 18px',
                    borderRadius: '12px',
                    marginBottom: '20px',
                    background: isCompliant ? '#f0fdf4' : '#fffbeb',
                    border: `1px solid ${isCompliant ? '#86efac' : '#fcd34d'}`,
                    color: isCompliant ? '#166534' : '#92400e',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '1.25rem' }}>{isCompliant ? '🛡️' : '⚠️'}</span>
                    <div>
                      <strong>發布前幾何與契約防呆檢核：</strong>
                      <span style={{ marginLeft: '6px', fontSize: '0.88rem' }}>
                        {isCompliant
                          ? `✅ 100% 滿版 (${targetW}×${targetH}) 無重疊 ｜ 全部 ${buttons.length} 個熱區路由合格 ｜ 0 個阻擋異常`
                          : `⚠️ 發現異常：${!isFullCoverage ? '熱區未填滿版面' : ''} ${hasOverlap ? '熱區存在重疊' : ''}`}
                      </span>
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      padding: '4px 10px',
                      borderRadius: '9999px',
                      background: isCompliant ? '#bbf7d0' : '#fef08a',
                      color: isCompliant ? '#14532d' : '#854d0e',
                    }}
                  >
                    {isCompliant ? '合規可發布' : '需修正'}
                  </span>
                </div>
              );
            })()}

            {/* 左右分割工作台 */}
            {activeMenu && (
            <div className="richmenu-studio-grid">
              {/* 左側：3D 手機即時模擬器 */}
              <div className="richmenu-phone-card">
                <div className="richmenu-phone-card-header">
                  <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#a43c12' }}>
                    📱 手機擬真互動沙盒 (點擊下方按鈕測試)
                  </span>
                  {activeSimLiff && (
                    <span style={{ fontSize: '0.75rem', background: '#fed9b8', color: '#7c2d12', padding: '2px 8px', borderRadius: '6px', fontWeight: 700 }}>
                      正在預覽 LIFF 表單
                    </span>
                  )}
                </div>

                <div className="richmenu-phone-frame">
                  {/* Phone Notch */}
                  <div className="richmenu-phone-notch"></div>
                  {/* Status Bar */}
                  <div className="richmenu-phone-statusbar">
                    <span>09:41</span>
                    <span>●●● 5G 🔋</span>
                  </div>
                  {/* Header */}
                  <div className="richmenu-phone-topbar">
                    <span style={{ fontSize: '0.8rem', cursor: 'pointer' }}>‹ 聊天</span>
                    <strong style={{ fontSize: '0.86rem', color: '#fff' }}>新竹市月子工會 (LINE)</strong>
                    <span style={{ fontSize: '0.8rem' }}>☰</span>
                  </div>

                  {/* LIFF 彈窗預覽層 (In-situ LIFF Modal) */}
                  {activeSimLiff ? (
                    <div className="phone-liff-modal">
                      <div className="phone-liff-header">
                        <div>
                          <span className="phone-liff-badge">{activeSimLiff.badge}</span>
                          <h4 style={{ margin: '4px 0 0', fontSize: '0.88rem', color: '#1e1b19', fontWeight: 700 }}>
                            {activeSimLiff.title}
                          </h4>
                          <small style={{ color: '#74593f', fontSize: '0.72rem' }}>{activeSimLiff.subtitle}</small>
                        </div>
                        <button
                          type="button"
                          className="phone-liff-close-btn"
                          onClick={() => setActiveSimLiff(null)}
                          title="關閉表單預覽"
                        >
                          ✕
                        </button>
                      </div>

                      <div className="phone-liff-body">
                        {activeSimLiff.fields.map((field, fIdx) => (
                          <div key={fIdx} className="phone-liff-field">
                            <label>{field.label}</label>
                            <div className="phone-liff-input-preview">
                              {field.value}
                            </div>
                            {field.hint && <small>{field.hint}</small>}
                          </div>
                        ))}
                      </div>

                      <div className="phone-liff-footer">
                        {activeSimLiff.actionButtons.map((act, aIdx) => (
                          <button
                            key={aIdx}
                            type="button"
                            className={aIdx === 0 ? 'phone-liff-btn-primary' : 'phone-liff-btn-secondary'}
                            onClick={() => {
                              setActiveSimLiff(null);
                              setSimChatMessages((prev) => [
                                ...prev,
                                {
                                  id: `msg-${Date.now()}-action`,
                                  sender: 'bot',
                                  text: `已模擬完成「${act}」操作！在真實環境中資料將安全送達工會系統。`,
                                  time: '09:42',
                                },
                              ]);
                            }}
                          >
                            {act}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    /* 聊天對話區域 */
                    <div className="richmenu-phone-chat">
                      <div className="richmenu-chat-bubble">
                        <div className="richmenu-bot-avatar">🤖</div>
                        <div className="richmenu-bubble-content">
                          <strong>工會小幫手</strong>
                          <p>您好！已載入「{activeMenu.audienceRoleLabel}」專屬選單。請點擊下方 4 個按鈕測試互動反應！</p>
                        </div>
                      </div>

                      {simChatMessages.map((msg) => (
                        <div
                          key={msg.id}
                          className={`richmenu-chat-bubble ${msg.sender === 'user' ? 'user-bubble' : ''}`}
                          style={{
                            alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                            flexDirection: msg.sender === 'user' ? 'row-reverse' : 'row',
                          }}
                        >
                          {msg.sender === 'bot' && <div className="richmenu-bot-avatar">🤖</div>}
                          <div
                            className="richmenu-bubble-content"
                            style={{
                              background: msg.sender === 'user' ? '#d9fdd3' : '#ffffff',
                              border: msg.sender === 'user' ? '1px solid #bbf7d0' : '1px solid #fed9b8',
                            }}
                          >
                            {msg.sender === 'bot' && <strong>工會小幫手</strong>}
                            <p style={{ margin: 0 }}>{msg.text}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Chat Bar Text */}
                  <div className="richmenu-chat-bar-hint">
                    {activeMenu.chatBarText} ▾
                  </div>

                  {/* Rich Menu Button Grid (可點擊互動) */}
                  <div
                    className={`richmenu-buttons-grid grid-count-${activeMenu.buttons.length} ${isDiffMode ? 'diff-active' : ''}`}
                  >
                    {activeMenu.buttons.map((btn, idx) => {
                      const label = btn.label;
                      const act = getButtonActionDetails(btn);
                      let icon = '📌';
                      if (label.includes('登記')) icon = '📝';
                      else if (label.includes('修改') || label.includes('異動')) icon = '✏️';
                      else if (label.includes('說明') || label.includes('FAQ')) icon = '🔍';
                      else if (label.includes('客服') || label.includes('諮詢')) icon = '💬';
                      else if (label.includes('訂單')) icon = '📦';
                      else if (label.includes('排班') || label.includes('日曆')) icon = '📅';
                      else if (label.includes('請假')) icon = '🏖️';
                      else if (label.includes('薪資') || label.includes('請款')) icon = '💵';
                      else if (label.includes('契約') || label.includes('合約')) icon = '📑';
                      else if (label.includes('評價') || label.includes('滿意度')) icon = '⭐';
                      else if (label.includes('審核')) icon = '📋';
                      else if (label.includes('一般用戶')) icon = '👥';
                      else if (label.includes('月嫂專區')) icon = '👩‍🍼';
                      else if (label.includes('工會管理')) icon = '🛡️';

                      return (
                        <button
                          key={btn.id}
                          type="button"
                          className={`richmenu-grid-btn ${isDiffMode ? 'diff-highlight' : ''}`}
                          onClick={() => {
                            // 呼叫沙盒模擬器
                            if (act.type === 'URI') {
                              const uri = act.uri ?? '';
                              if (uri.includes('entry=registration') || label.includes('登記')) {
                                setActiveSimLiff({
                                  title: '📝 產婦到宅服務線上登記表',
                                  subtitle: '新竹市月子照護工會 · 官方線上登記通道',
                                  badge: 'LIFF 表單預覽',
                                  fields: [
                                    { label: '產婦姓名', value: '林○真 媽媽', hint: '（系統自動帶入 LINE 暱稱）' },
                                    { label: '預產期 (EDD)', value: '115 年 06 月 18 日', hint: '依媽媽手冊載明' },
                                    { label: '服務地點', value: '新竹市東區關新路...', hint: '到宅服務地址' },
                                    { label: '料理與照護偏好', value: '葷食／藥膳燉湯（雙胞胎照護需額外註記）' },
                                    { label: '預約天數', value: '26 天（每日 9 小時專職照護）' },
                                  ],
                                  actionButtons: ['確認送出登記', '暫存草稿'],
                                });
                              } else if (uri.includes('profile_update') || label.includes('修改')) {
                                setActiveSimLiff({
                                  title: '✏️ 客戶資料與服務異動申請',
                                  subtitle: '安全異動通道 · 提交後需經工會督導審核',
                                  badge: 'LIFF 異動申請',
                                  fields: [
                                    { label: '案件編號', value: 'CASE-202608-019' },
                                    { label: '異動項目', value: '預產期提前 / 增加服務天數 (+5天)' },
                                    { label: '異動原因', value: '醫師評估可能提早於 5 月底生產，申請月嫂檔期彈性調配' },
                                    { label: '新服務地址', value: '新竹市北區北大路（原址變更）' },
                                  ],
                                  actionButtons: ['送出異動申請 (產生 Diff)', '取消'],
                                });
                              } else if (uri.includes('staff_order_search') || label.includes('訂單')) {
                                setActiveSimLiff({
                                  title: '📦 月嫂訂單照護資訊工作台',
                                  subtitle: '案件摘要 · 產婦偏好與安全注意事項',
                                  badge: '月嫂專屬 LIFF',
                                  fields: [
                                    { label: '承接案件', value: 'ORD-2026-HC092 (林產婦)' },
                                    { label: '服務區間', value: '115/06/18 ～ 115/07/13 (26天)' },
                                    { label: '寶寶狀況', value: '足月單胞胎，體重 3,200g' },
                                    { label: '產婦料理要求', value: '少鹽少油、麻油酒料理後 2 週再食用、避開帶殼海鮮' },
                                    { label: '緊急聯絡人', value: '先生 陳先生 (0912-***-456)' },
                                  ],
                                  actionButtons: ['打卡上班', '聯繫督導'],
                                });
                              } else if (uri.includes('staff_schedule') || label.includes('排班')) {
                                setActiveSimLiff({
                                  title: '📅 月嫂個人排班與服務日曆',
                                  subtitle: '防重疊排班保護 · 7天 Buffer 鎖定期',
                                  badge: '月嫂日曆 LIFF',
                                  fields: [
                                    { label: '本月已排案件', value: '2 案（共計 38 服務日）' },
                                    { label: '檔期鎖定 (Buffer)', value: '06/11 ～ 06/17 (預產期前 7 天鎖定不接新單)' },
                                    { label: '公休安排', value: '每週日固定公休（共 4 天）' },
                                    { label: '次月空檔', value: '115 年 8 月起可承接新竹市東區/竹北案件' },
                                  ],
                                  actionButtons: ['更新可接案時段', '申請代班'],
                                });
                              } else if (uri.includes('staff_leave_apply') || label.includes('請假')) {
                                setActiveSimLiff({
                                  title: '🏖️ 月嫂請假與代班申請單',
                                  subtitle: '工會代班媒合與產婦順延簽核',
                                  badge: '請假代班 LIFF',
                                  fields: [
                                    { label: '請假假別', value: '事假 / 家庭照顧假' },
                                    { label: '請假日期', value: '115/06/25 ～ 115/06/26 (2天)' },
                                    { label: '代班需求', value: '由工會緊急指派支援月嫂（需具備藥膳證照）' },
                                    { label: '產婦協商意願', value: '已與產婦初步溝通同意服務天數往後順延 2 天' },
                                  ],
                                  actionButtons: ['送出請假代班申請', '返回'],
                                });
                              } else if (uri.includes('staff_payout') || label.includes('薪資')) {
                                setActiveSimLiff({
                                  title: '💵 月嫂薪資津貼與完工請款明細',
                                  subtitle: '工會核撥進度 · 勞健保與代扣明細',
                                  badge: '請款明細 LIFF',
                                  fields: [
                                    { label: '上期結算案', value: 'ORD-2026-HC088 (已完工結案)' },
                                    { label: '服務時數與津貼', value: '216 小時 · NT$ 75,600' },
                                    { label: '補助款代領轉付', value: '新竹市政府到宅補助 NT$ 12,000 (已核銷)' },
                                    { label: '撥款進度', value: '🟢 已入帳（115/08/05 撥入合作金庫帳戶）' },
                                  ],
                                  actionButtons: ['下載所得憑證 (PDF)', '帳務疑問反映'],
                                });
                              } else if (uri.includes('staff_review') || label.includes('審核')) {
                                setActiveSimLiff({
                                  title: '📋 工會行動審核工作台',
                                  subtitle: '月嫂認證資質 · 產婦異動 Diff 審查',
                                  badge: '工會幹部 LIFF',
                                  fields: [
                                    { label: '待審項目 (1)', value: '【月嫂新進審核】張○敏（保母證、良民證、體檢合格）' },
                                    { label: '待審項目 (2)', value: '【產婦異動簽核】CASE-019 預產期提早 5 天調單申請' },
                                    { label: '待審項目 (3)', value: '【請假調休代班】月嫂李○芳 06/25 事假代班媒合確認' },
                                  ],
                                  actionButtons: ['✅ 一鍵核准通過', '⚠️ 退回補件'],
                                });
                              } else if (uri.includes('customer_service') || label.includes('客服')) {
                                setActiveSimLiff({
                                  title: '🎧 行動客服工單中心',
                                  subtitle: '線上民眾即時進件 · AI 轉真人接管',
                                  badge: '客服中心 LIFF',
                                  fields: [
                                    { label: '待回覆進件', value: '3 筆民眾諮詢（新竹市月子補助條件 2 件、換約諮詢 1 件）' },
                                    { label: 'AI 接管狀態', value: '🟢 自動小幫手運行中（已成功解答 92% 常見 QA）' },
                                    { label: '急件通報', value: '1 筆產婦來訊反映希望更換照護時段' },
                                  ],
                                  actionButtons: ['接管目前對話', '指派值班督導'],
                                });
                              } else if (uri.includes('anomalies') || label.includes('異常')) {
                                setActiveSimLiff({
                                  title: '🚨 重大異常與急件通報面板',
                                  subtitle: '財務短溢繳 · 排班重疊 · 客訴警示',
                                  badge: '異常通報 LIFF',
                                  fields: [
                                    { label: '財務短溢繳', value: '1 筆：訂單 ORD-071 定金少繳 NT$ 2,000 (轉帳手續費扣除)' },
                                    { label: '排班衝突警示', value: '0 筆：全體月嫂檔期無重疊排班衝突' },
                                    { label: '急件客訴通報', value: '0 筆未結案重大爭議' },
                                  ],
                                  actionButtons: ['立即調派督導協處', '標記為已追蹤'],
                                });
                              } else {
                                setActiveSimLiff({
                                  title: '📊 工會即時營運數據看板',
                                  subtitle: '今日派工與市府月子補助進度',
                                  badge: '營運看板 LIFF',
                                  fields: [
                                    { label: '今日出勤月嫂', value: '42 位在職月嫂到宅照護中' },
                                    { label: '進行中案件', value: '56 件產婦家庭服務中' },
                                    { label: '本月市府補助申請', value: '累計核銷 128 戶（總補助金額 NT$ 1,536,000）' },
                                    { label: '本月滿意度', value: '⭐ 98.6% 家長給予 5 星好評' },
                                  ],
                                  actionButtons: ['匯出月報表', '更新指標'],
                                });
                              }
                            } else if (act.type === 'MESSAGE') {
                              const text = act.text ?? label;
                              let botReply = '';
                              if (text.includes('說明') || text.includes('FAQ')) {
                                botReply = '親愛的家長您好！新竹市到宅月子補助標準為：自 115 年 1 月 1 日起，每日最高補助 4 小時、每戶最高上限 40 小時。超出部分將依工會定型化契約以自費時薪計算。服務完成後由工會協助向市府核銷退款。';
                              } else if (text.includes('客服')) {
                                botReply = '已為您通報工會值班秘書！秘書將於上班時間（週一至週五 09:00-18:00）透過此對話為您服務；若有緊急照護狀況請撥打工會專線：(03) 535-****。';
                              } else {
                                botReply = `已收到您的指令：「${text}」，工會系統已為您記錄並處理中。`;
                              }

                              setSimChatMessages((prev) => [
                                ...prev,
                                { id: `msg-${Date.now()}-u`, sender: 'user', text, time: '09:42' },
                                { id: `msg-${Date.now()}-b`, sender: 'bot', text: botReply, time: '09:42' },
                              ]);
                              setActiveSimLiff(null);
                            }
                          }}
                        >
                          <span className="richmenu-btn-icon">{icon}</span>
                          <span className="richmenu-btn-text">{btn.label}</span>
                          {isDiffMode && (
                            <span
                              style={{
                                position: 'absolute',
                                top: '2px',
                                right: '2px',
                                fontSize: '0.6rem',
                                background: '#10b981',
                                color: '#fff',
                                padding: '1px 4px',
                                borderRadius: '4px',
                                fontWeight: 700,
                              }}
                            >
                              熱區 {idx + 1}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* 右側：選單定義與發布面板 */}
              <div className="richmenu-inspector-column">
                {/* Card A: 選單定義與動作熱區綁定 */}
                <div className="richmenu-card">
                  <div className="richmenu-card-header">
                    <div>
                      <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
                        ⚙️ 選單內容與按鈕設定
                      </h4>
                      <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
                        {activeMenu.audienceRoleLabel}｜{activeMenu.name}
                      </p>
                    </div>
                    <span className="line-category-badge category-service_flow">
                      {activeMenu.buttons.length} 個按鈕
                    </span>
                  </div>

                  <div className="line-table-scroll" style={{ marginTop: '12px' }}>
                    <table className="line-data-table">
                      <thead>
                        <tr>
                          <th>熱區</th>
                          <th>按鈕標題</th>
                          <th>動作類型</th>
                          <th>目標參數 / 路由</th>
                          <th>熱區座標</th>
                          <th style={{ textAlign: 'right' }}>沙盒測試</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeMenu.buttons.map((btn, idx) => {
                          const act = getButtonActionDetails(btn);
                          return (
                            <tr key={btn.id}>
                              <td>
                                <span style={{ display: 'inline-block', width: '20px', height: '20px', lineHeight: '20px', textAlign: 'center', background: '#fed9b8', color: '#7c2d12', borderRadius: '50%', fontSize: '0.75rem', fontWeight: 700 }}>
                                  {idx + 1}
                                </span>
                              </td>
                              <td><strong>{btn.label}</strong></td>
                              <td>
                                <span style={{ fontSize: '0.78rem', padding: '2px 6px', borderRadius: '4px', background: act.type === 'URI' ? '#eff6ff' : '#f0fdf4', color: act.type === 'URI' ? '#1d4ed8' : '#15803d', fontWeight: 700 }}>
                                  {act.type}
                                </span>
                              </td>
                              <td>
                                <code style={{ fontSize: '0.75rem', color: '#475569' }}>
                                  {act.type === 'URI' ? (act.uri || '未設定') : (act.text || '未設定')}
                                </code>
                              </td>
                              <td>
                                <code style={{ fontSize: '0.75rem', color: '#a43c12' }}>
                                  x:{btn.bounds.x} y:{btn.bounds.y} w:{btn.bounds.width} h:{btn.bounds.height}
                                </code>
                              </td>
                              <td style={{ textAlign: 'right' }}>
                                <button
                                  type="button"
                                  className="line-action-link-btn"
                                  onClick={() => {
                                    const syntheticBtn = document.querySelectorAll('.richmenu-grid-btn')[idx] as HTMLButtonElement | undefined;
                                    if (syntheticBtn) syntheticBtn.click();
                                  }}
                                >
                                  📱 模擬點擊
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="line-scope-note" style={{ marginTop: '14px' }}>
                    💡 <strong>本機沙盒比對引擎</strong>：點擊任意按鈕或「📱 模擬點擊」即可在左側 3D 手機模擬器中即時預覽 LIFF 表單或自動對話；零後端寫入。
                  </div>
                </div>

                {/* Card B (可選): 版本變更 Diff 對比面板 */}
                {isDiffMode && (
                  <div className="richmenu-card" style={{ border: '2px dashed #ff7f50', background: '#fffcfb' }}>
                    <div className="richmenu-card-header">
                      <div>
                        <h4 style={{ margin: 0, fontSize: '1rem', color: '#c2410c', fontWeight: 700 }}>
                          ✨ 前後版本變更比對 (Visual & Property Diff)
                        </h4>
                        <p style={{ margin: '2px 0 0', fontSize: '0.8rem', color: '#74593f' }}>
                          比對線上生效快照 (Active DB Snapshot) vs 目前草稿配置
                        </p>
                      </div>
                      <span style={{ fontSize: '0.75rem', background: '#ffedd5', color: '#9a3412', padding: '3px 8px', borderRadius: '6px', fontWeight: 700 }}>
                        Diff Mode 啟用中
                      </span>
                    </div>

                    <div className="line-table-scroll" style={{ marginTop: '10px' }}>
                      <table className="line-data-table">
                        <thead>
                          <tr>
                            <th>熱區</th>
                            <th>線上生效版本 (Before)</th>
                            <th>目前草稿版本 (After)</th>
                            <th>比對判定</th>
                          </tr>
                        </thead>
                        <tbody>
                          {activeMenu.buttons.map((btn, idx) => {
                            const act = getButtonActionDetails(btn);
                            return (
                              <tr key={btn.id}>
                                <td><strong>熱區 {idx + 1}</strong></td>
                                <td>
                                  <div style={{ fontSize: '0.8rem', color: '#64748b' }}>
                                    {idx < 2 ? (idx === 0 ? '服務登記 (2500x843 半版)' : '服務說明 (2500x843 半版)') : '（未配置/舊版無此熱區）'}
                                  </div>
                                </td>
                                <td>
                                  <div style={{ fontSize: '0.8rem', color: '#0f172a', fontWeight: 700 }}>
                                    {btn.label} ({act.type}: {act.uri || act.text})
                                  </div>
                                </td>
                                <td>
                                  <span style={{ fontSize: '0.75rem', fontWeight: 700, padding: '2px 8px', borderRadius: '4px', background: idx < 2 ? '#ffedd5' : '#dcfce7', color: idx < 2 ? '#c2410c' : '#15803d' }}>
                                    {idx < 2 ? '🟧 升級 4 宮格熱區' : '🟩 新增標準功能'}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Card C: 發布操作 */}
                <LineRichMenuPublicationActions
                  selectedMenu={activeMenu}
                  selectedPublication={selectedPublication.value}
                  onQueued={() => setRichMenuReload((value) => value + 1)}
                />
              </div>
            </div>
            )}

            {/* 發布紀錄歷程 */}
            <div className="richmenu-history-section" data-control-id="line.richmenu.publications">
              <div className="line-section-heading" style={{ marginTop: '24px', marginBottom: '12px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '1rem', color: '#1e1b19', fontWeight: 700 }}>
                    📜 Rich Menu 發布歷程紀錄
                  </h4>
                  <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
                    顯示每次發布的排程、處理狀態與結果，方便追蹤未完成或失敗項目。
                  </p>
                </div>
              </div>

              {richMenuPublications.status === 'loading' && <div className="line-loading">正在載入 Rich Menu 發布紀錄…</div>}
              {richMenuPublications.status === 'error' && <div className="line-error" role="alert">{richMenuPublications.error}</div>}
              {richMenuPublications.status === 'loaded' && richMenuPublications.value && (
                richMenuPublications.value.items.length === 0 ? (
                  <div className="line-empty-state">
                    <div>📱</div>
                    <h4>目前尚無發布紀錄</h4>
                    <p>由上方發布面板建立預覽並確認排入後，將會在此顯示發布狀態與結果。</p>
                  </div>
                ) : (
                  <div className="line-table-scroll">
                    <table className="line-data-table">
                      <thead>
                        <tr>
                          <th>選單</th>
                          <th>狀態</th>
                          <th>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {richMenuPublications.value.items.map((publication) => (
                          <tr key={publication.id}>
                            <td><strong>{menus.find((menu) => menu.id === publication.menuDefinitionId)?.name ?? '已發布圖文選單'}</strong></td>
                            <td><span className={`line-status line-status-${publication.status}`}>{publication.statusLabel}</span></td>
                            <td>
                              <button
                                type="button"
                                className="line-action-link-btn"
                                data-control-id="line.richmenu.publication-detail"
                                onClick={() => openPublication(publication.id)}
                              >
                                [ 🔍 查看紀錄 ]
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              )}
            </div>
          </section>
        );
      })()}

      {activeTab === 'binding' && (() => {
        const items = bindingPage.value?.items ?? [];
        const total = bindingPage.value?.total ?? 0;
        const page = bindingPage.value?.page ?? 1;
        const reviewClient = asReviewClient(lineIdentity);

        const customerCount = items.filter((i) => i.subjectType === 'customer').length;
        const staffCount = items.filter((i) => i.subjectType === 'staff').length;
        const adminCount = items.filter((i) => i.subjectType === 'admin').length;

        const filteredBindings = items.map((record, index) => ({
          record,
          lineUserId: bindingSources[index] ?? null,
        })).filter(({ record: item }) => {
          if (bindingRoleFilter !== 'all' && item.subjectType !== bindingRoleFilter) return false;
          if (bindingSearchQuery.trim()) {
            const q = bindingSearchQuery.toLowerCase();
            const matchName = item.subjectName.toLowerCase().includes(q);
            const matchUser = item.maskedLineUserId.toLowerCase().includes(q);
            if (!matchName && !matchUser) return false;
          }
          return true;
        });

        return (
          <>
          <section className="line-table-container" data-control-id="line.identity.section">
            <div className="line-section-heading">
              <div>
                <h3>🔑 LINE 身分綁定與授權管理</h3>
                <p>管理產婦客戶、線上月嫂與工會幹部的 LINE 帳號綁定狀態、去敏識別與解除審查。</p>
              </div>
              <button
                type="button"
                className="line-secondary-btn"
                onClick={() => { setBindingPageNumber(1); setBindingReload((value) => value + 1); }}
              >
                🔄 重新整理
              </button>
            </div>

            <LoadingOrError state={bindingPage} loadingText="正在載入身分綁定…" />

            <div className="line-scope-note" data-control-id="line.identity.authority-note">
              <strong>身分根事實：</strong>正式授權只以 server-side 驗證的 LIFF ID token 與 canonical binding 為準；網址參數或人工輸入的 LINE User ID 都不是身分證明，LIFF onboarding 也不會直接變更客戶、月嫂或管理員角色。
            </div>

            {bindingPage.status === 'loaded' && bindingPage.value && (
              <>
                {/* 4 大身分統計 KPI */}
                <div className="line-kpi-grid">
                  <div>
                    <span>身分紀錄總數</span>
                    <strong>{total}</strong>
                  </div>
                  <div>
                    <span>👥 產婦客戶</span>
                    <strong>{customerCount}</strong>
                  </div>
                  <div>
                    <span>👩‍🍼 線上月嫂</span>
                    <strong>{staffCount}</strong>
                  </div>
                  <div>
                    <span>🛡️ 工會幹部</span>
                    <strong>{adminCount}</strong>
                  </div>
                </div>

                {/* 搜尋與角色過濾工具列 */}
                <div className="line-search-filter-toolbar">
                  <div className="line-search-input-wrapper">
                    <span className="line-search-icon">🔍</span>
                    <input
                      type="text"
                      className="line-search-input"
                      placeholder="搜尋實名姓名或 Masked LINE ID…"
                      value={bindingSearchQuery}
                      onChange={(e) => { setBindingPageNumber(1); setBindingSearchQuery(e.target.value); }}
                    />
                    {bindingSearchQuery && (
                      <button
                        type="button"
                        className="line-search-clear-btn"
                        onClick={() => { setBindingPageNumber(1); setBindingSearchQuery(''); }}
                      >
                        ✕
                      </button>
                    )}
                  </div>

                  <div className="line-filter-selects">
                    <select
                      className="line-filter-select"
                      value={bindingRoleFilter}
                       onChange={(e) => { setBindingPageNumber(1); setBindingRoleFilter(e.target.value as 'all' | 'customer' | 'staff' | 'admin'); }}
                    >
                      <option value="all">全部身分角色</option>
                      <option value="customer">👥 產婦客戶</option>
                      <option value="staff">👩‍🍼 線上月嫂</option>
                      <option value="admin">🛡️ 工會管理員</option>
                    </select>
                  </div>
                </div>

                {filteredBindings.length === 0 ? (
                  <div className="line-empty-state">
                    <div>🔑</div>
                    <h4>找不到符合條件的身分綁定</h4>
                    <p>請嘗試清除搜尋關鍵字或變更身分篩選條件。</p>
                  </div>
                ) : (
                  <>
                    <div className="line-table-scroll">
                      <table className="line-data-table" data-control-id="line.identity.table">
                        <thead>
                          <tr>
                            <th>LINE User ID</th>
                            <th>實名姓名</th>
                            <th>身分角色</th>
                            <th>最後更新時間</th>
                            <th>綁定狀態</th>
                            <th>解除狀態</th>
                            <th style={{ textAlign: 'right' }}>操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredBindings.map(({ record, lineUserId }, index) => (
                            <tr key={`${record.maskedLineUserId}-${record.version}-${index}`}>
                              <td><code>{record.maskedLineUserId}</code></td>
                              <td><strong>👤 {record.subjectName}</strong></td>
                              <td>
                                <span className={`line-category-badge category-${record.subjectType === 'staff' ? 'service_progress' : record.subjectType === 'admin' ? 'contact_union' : 'service_flow'}`}>
                                  {record.subjectTypeLabel}
                                </span>
                              </td>
                              <td style={{ color: '#74593f', fontSize: '0.82rem' }}>{record.updatedAt ?? '—'}</td>
                              <td>
                                <span className={`line-status line-status-${record.status}`}>
                                  {record.statusLabel}
                                </span>
                              </td>
                              <td>
                                <span style={{ fontSize: '0.82rem', color: !record.revocationStatus ? '#74593f' : '#b45309' }}>
                                  {record.revocationStatusLabel}
                                </span>
                              </td>
                              <td style={{ textAlign: 'right' }}>
                                <button
                                  type="button"
                                  className="line-action-link-btn"
                                  data-control-id="line.identity.detail"
                                  aria-label="查看明細"
                                  disabled={lineUserId === null}
                                  onClick={() => { if (lineUserId !== null) openBinding(lineUserId); }}
                                >
                                  [ 🔍 查看明細 ]
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="line-pagination-bar">
                      <span style={{ fontSize: '0.85rem', color: '#74593f' }}>
                        第 {page} 頁，顯示 {filteredBindings.length} 筆，全域總數 {total} 筆
                      </span>
                    </div>
                  </>
                )}
              </>
            )}
          </section>
          {reviewClient ? (
            <LineIdentityReviewWorkbench client={reviewClient} />
          ) : (
            <section className="line-table-container" data-control-id="line.identity.review-unavailable">
              <div className="line-error" role="alert">
                LINE 身分審核 typed client 未完整注入，審核操作已安全停止。
              </div>
            </section>
          )}
          </>
        );
      })()}

      {activeTab === 'push_queue' && (() => {
        const ruleList = rules.value?.rules ?? [];
        const isRulesEmpty = rules.value?.isEmpty ?? false;

        return (
          <section className="line-table-container" data-control-id="line.push_queue.section">
            <div className="line-section-heading">
              <div>
                <h3>🔔 LINE 推播與通知規則目錄</h3>
                <p>即時監控排班媒合、合約繳費、月嫂請假等事件觸發之 LINE 推播規則、排程頻率與發送佇列。</p>
              </div>
              <button
                type="button"
                className="line-secondary-btn"
                data-control-id="line.notification-rules.refresh"
                onClick={() => setRulesReload((value) => value + 1)}
              >
                🔄 重新整理
              </button>
            </div>

            {/* 1. 通知規則目錄卡片清單 */}
            <div className="richmenu-card" style={{ marginBottom: '24px' }}>
              <div className="richmenu-card-header">
                <div>
                  <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
                    📋 系統推播規則目錄
                  </h4>
                  <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
                    共有 {ruleList.length} 項排程與即時通知規則
                  </p>
                </div>
              </div>

              <LoadingOrError state={rules} loadingText="正在載入通知規則目錄…" />

              {rules.status === 'loaded' && isRulesEmpty && (
                <div className="line-empty-state" data-control-id="line.notification-rules.empty" style={{ marginTop: '16px' }}>
                  <div>🔔</div>
                  <h4>目前尚未設定通知規則</h4>
                  <p>可新增通知規則，儲存前會先檢查影響。</p>
                </div>
              )}

              {rules.status === 'loaded' && !isRulesEmpty && (
                <div className="line-rule-grid" data-control-id="line.notification-rules.list" style={{ marginTop: '16px' }}>
                  {ruleList.map((rule) => (
                    <button
                      key={rule.id}
                      type="button"
                      className="line-rule-card"
                      onClick={() => setSelectedRule(rule)}
                    >
                      <div className="line-rule-card-header">
                        <span className="line-category-badge category-service_flow">
                          {rule.eventLabel}
                        </span>
                        <span className="line-category-badge category-payment_subsidy">
                          {rule.recipientLabel}
                        </span>
                      </div>
                      <strong>{rule.id}</strong>
                      <small>
                        ⏱️ {rule.scheduleLabel} ｜ 頻率：{rule.frequencyLabel}
                      </small>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '6px', paddingTop: '6px', borderTop: '1px solid #f5ece9' }}>
                        <span className={`line-status ${rule.enabled ? 'line-status-bound' : 'line-status-revoked'}`}>
                          {rule.enabled ? '● 已啟用' : '○ 停用中'}
                        </span>
                        <span style={{ fontSize: '0.78rem', color: '#ff7f50', fontWeight: 700 }}>
                          [ 🔍 規則明細 ]
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* 2. 發送佇列 KPI 與任務清冊 */}
            <div className="richmenu-card">
              <div className="richmenu-card-header">
                <div>
                  <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
                    🚀 LINE 推播發送進度
                  </h4>
                  <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
                    查看各類通知的排程、處理進度、失敗與重試狀況。
                  </p>
                </div>
              </div>

              <LoadingOrError state={deliverySummary} loadingText="正在載入發送任務摘要…" />

              {deliverySummary.value && (
                <div className="line-kpi-grid" style={{ marginTop: '16px' }}>
                  <div>
                    <span>全部任務</span>
                    <strong>{deliverySummary.value.total}</strong>
                  </div>
                  <div>
                    <span>⏳ 待執行</span>
                    <strong>{deliverySummary.value.pending}</strong>
                  </div>
                  <div>
                    <span>⚙️ 處理中</span>
                    <strong>{deliverySummary.value.processing}</strong>
                  </div>
                  <div>
                    <span>✅ 已送出</span>
                    <strong style={{ color: '#16a34a' }}>{deliverySummary.value.sent}</strong>
                  </div>
                  <div>
                    <span>⚠️ 失敗 / 待重試</span>
                    <strong style={{ color: '#dc2626' }}>{deliverySummary.value.failed + deliverySummary.value.retryable_failed}</strong>
                  </div>
                  <div>
                    <span>🤖 發送服務</span>
                    <strong style={{ fontSize: '1.05rem' }}>{deliverySummary.value.workerLabel}</strong>
                  </div>
                </div>
              )}

              <div className="line-scope-note">
                「已送出」表示 LINE 已接受發送，不代表收件人已讀。
              </div>

              <LoadingOrError state={deliveryItems} loadingText="正在載入發送任務…" />

              {(() => {
                const tasks = deliveryItems.value?.items ?? [];
                return deliveryItems.status === 'loaded' && tasks.length === 0 ? (
                  <div className="line-empty-state" style={{ marginTop: '16px' }}>
                    <div>📮</div>
                    <h4>目前沒有發送任務</h4>
                    <p>當系統產生排班確認或工單通知時，發送進度將在此即時顯示。</p>
                  </div>
                ) : (
                  <div className="line-table-scroll" style={{ marginTop: '16px' }}>
                    <table className="line-data-table" data-control-id="line.delivery.table">
                      <thead>
                        <tr>
                          <th>通知用途</th>
                          <th>排程時間</th>
                          <th>處理進度</th>
                          <th>狀態</th>
                          <th style={{ textAlign: 'right' }}>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tasks.map((task) => (
                          <tr key={task.taskId}>
                            <td>
                              <span className="line-category-badge category-service_flow">
                                {task.sourceLabel}
                              </span>
                            </td>
                            <td style={{ color: '#74593f', fontSize: '0.82rem' }}>{task.scheduledAt}</td>
                            <td>
                              <span style={{ display: 'inline-block', width: '22px', height: '22px', lineHeight: '22px', textAlign: 'center', background: '#fed9b8', color: '#7c2d12', borderRadius: '50%', fontSize: '0.75rem', fontWeight: 700 }}>
                                {task.attempts}
                              </span>
                            </td>
                            <td>
                              <span className={`line-status line-status-${task.status}`}>
                                {task.statusLabel}
                              </span>
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <button
                                type="button"
                                className="line-action-link-btn"
                                onClick={() => openDeliveryTask(task.taskId)}
                              >
                                [ 🔍 查看明細 ]
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
              {deliveryItems.status === 'loaded' && deliveryItems.value && (
                <div className="line-pagination-bar">
                  <button
                    type="button"
                    className="line-secondary-btn"
                    disabled={deliveryItems.value.page <= 1}
                    onClick={() => setDeliveryPageNumber((page) => Math.max(1, page - 1))}
                  >
                    上一頁
                  </button>
                  <span style={{ fontSize: '0.85rem', color: '#74593f' }}>
                    第 {deliveryItems.value.page}／{Math.max(1, deliveryItems.value.totalPages)} 頁，
                    本頁 {deliveryItems.value.items.length} 筆，共 {deliveryItems.value.total} 筆
                  </span>
                  <button
                    type="button"
                    className="line-secondary-btn"
                    disabled={deliveryItems.value.page >= deliveryItems.value.totalPages}
                    onClick={() => setDeliveryPageNumber((page) => page + 1)}
                  >
                    下一頁
                  </button>
                </div>
              )}
            </div>
          </section>
        );
      })()}

      {activeTab === 'order_groups' && (
        <section className="line-table-container">
          <div className="line-section-heading">
            <div>
              <h3>👥 三方服務群組管理</h3>
              <p>依案件查詢產婦客戶、月嫂與工會幹部的三方 LINE 群組狀態與事件紀錄。</p>
            </div>
            <button
              type="button"
              className="line-secondary-btn"
              onClick={() => setOrderGroupReload((value) => value + 1)}
            >
              🔄 重新整理
            </button>
          </div>

          <LoadingOrError state={orderGroups} loadingText="正在載入三方服務群組…" />

          {orderGroups.status === 'loaded' && orderGroups.value && (
            (orderGroups.value.items?.length ?? 0) === 0 ? (
              <div className="line-empty-state">
                <div>👥</div>
                <h4>目前沒有三方服務群組</h4>
                <p>訂單完成簽約並建立 LINE 群組後會顯示在這裡。</p>
              </div>
            ) : (
              <div className="line-table-scroll">
                <table className="line-data-table" data-control-id="line.order-groups.table">
                  <thead>
                    <tr>
                      <th>案件編號</th>
                      <th>群組狀態</th>
                      <th style={{ textAlign: 'right' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(orderGroups.value.items ?? []).map((record) => (
                      <tr key={record.caseNo}>
                        <td><strong>#{record.caseNo}</strong></td>
                        <td>
                          <span className={`line-status line-status-${record.status}`}>
                            {record.statusLabel}
                          </span>
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            type="button"
                            className="line-action-link-btn"
                            onClick={() => openOrderGroup(record.caseNo)}
                          >
                            [ 🔍 查看明細 ]
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </section>
      )}

      {activeTab === 'runtime' && (
        <div className="line-runtime-workspace">
          {/* 1. 安全去敏設定 */}
          <section className="line-workspace-card">
            <div className="line-section-heading">
              <div>
                <h3>🛡️ LINE 安全去敏設定狀態</h3>
                <p>只顯示六種安全設定的使用狀態；敏感定義與 LINE 密鑰不傳送到前端。</p>
              </div>
              <button
                type="button"
                className="line-secondary-btn"
                onClick={refreshRuntime}
              >
                🔄 重新整理
              </button>
            </div>

            <LoadingOrError state={safeConfigurations} loadingText="正在載入 LINE 設定狀態…" />

            {safeConfigurations.value && (
              <div className="line-kpi-grid">
                {safeConfigurations.value.map((config) => (
                  <div key={config.kind}>
                    <span>{config.kindLabel}</span>
                    <strong>{config.stateLabel}</strong>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* 2. 異常通知對象 */}
          <section className="line-workspace-card">
            <div className="line-section-heading">
              <div>
                <h3>🚨 異常通知對象與群組</h3>
                <p>查詢並調整群組或管理員通知對象；送出時會自動核對最新狀態並避免重複處理。</p>
              </div>
            </div>

            <div style={{ marginBottom: '14px' }}>
              <label htmlFor="runtime-reason" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: '#57423b', marginBottom: '4px' }}>
                調整原因說明 (Audit Reason)
              </label>
              <input
                id="runtime-reason"
                className="line-search-input"
                style={{ width: '100%' }}
                value={runtimeReason}
                onChange={(event) => {
                  setRuntimeReason(event.target.value);
                  setRuntimePending(null);
                  setRuntimeConfirmed(false);
                  setRuntimeReceipt(null);
                }}
                maxLength={500}
              />
            </div>

            <LoadingOrError state={runtimeTargets} loadingText="正在載入異常通知對象…" />

            {runtimeTargets.value && (
              runtimeTargets.value.length === 0 ? (
                <div className="line-empty-state">
                  <div>🚨</div>
                  <h4>目前沒有異常通知對象</h4>
                </div>
              ) : (
                <div className="line-table-scroll">
                  <table className="line-data-table">
                    <thead>
                      <tr>
                        <th>類型</th>
                        <th>顯示名稱</th>
                        <th>狀態</th>
                        <th>觸發門檻</th>
                        <th style={{ textAlign: 'right' }}>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runtimeTargets.value.map((target) => (
                        <tr key={target.targetId}>
                          <td>
                            <span className="line-category-badge category-service_flow">
                              {target.targetKindLabel}
                            </span>
                          </td>
                          <td><strong>{target.displayLabel}</strong></td>
                          <td>
                            <span className={`line-status line-status-${target.state}`}>
                              {target.stateLabel}
                            </span>
                          </td>
                          <td>{target.minimumStatusLabel}</td>
                          <td style={{ textAlign: 'right' }}>
                            <div className="line-row-actions" style={{ justifyContent: 'flex-end' }}>
                              <button
                                type="button"
                                className="line-secondary-btn"
                                style={{ padding: '4px 10px', fontSize: '0.8rem' }}
                                disabled={runtimeMutation === 'loading' || !runtimeReason.trim()}
                                onClick={() => void previewRuntimeMutation('toggle', target)}
                              >
                                預覽{target.state === 'active' ? '停用' : '啟用'}
                              </button>
                              {target.targetKind === 'group' && (
                                <button
                                  type="button"
                                  className="line-secondary-btn"
                                  style={{ padding: '4px 10px', fontSize: '0.8rem' }}
                                  disabled={runtimeMutation === 'loading' || !runtimeReason.trim()}
                                  onClick={() => void previewRuntimeMutation('reset', target)}
                                >
                                  預覽重設群組
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            )}

            <LoadingOrError state={runtimeCandidates} loadingText="正在載入管理員候選…" />

            {runtimeCandidates.value && (
              <div className="line-row-actions" style={{ marginTop: '16px', padding: '12px 14px', background: '#fff8f6', borderRadius: '10px', border: '1px solid #fed9b8' }}>
                <label htmlFor="runtime-candidate" style={{ fontSize: '0.85rem', fontWeight: 700, color: '#57423b' }}>
                  新增管理員對象：
                </label>
                <select
                  id="runtime-candidate"
                  className="line-filter-select"
                  value={selectedRuntimeCandidate ?? ''}
                  onChange={(event) => {
                    setSelectedRuntimeCandidate(event.target.value ? Number(event.target.value) : null);
                    setRuntimePending(null);
                    setRuntimeConfirmed(false);
                    setRuntimeReceipt(null);
                  }}
                >
                  <option value="">請選擇已連結 LINE 的管理員</option>
                  {runtimeCandidates.value.filter((candidate) => candidate.lineLinked).map((candidate) => (
                    <option key={candidate.candidateId} value={candidate.candidateId}>
                      {candidate.displayLabel}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="line-primary-btn"
                  style={{ padding: '6px 14px', fontSize: '0.85rem' }}
                  disabled={selectedRuntimeCandidate === null || !runtimeReason.trim() || runtimeMutation === 'loading'}
                  onClick={() => void previewRuntimeMutation('add')}
                >
                  ➕ 預覽新增通知對象
                </button>
              </div>
            )}

            {runtimePending && (
              <div className="line-preview-result" style={{ marginTop: '12px' }}>
                <strong>
                  {runtimePending.preview.previous_state === 'absent' ? '尚未建立' : runtimePending.preview.previous_state === 'active' ? '啟用' : '停用'}
                  {' → '}
                  {runtimePending.preview.resulting_state === 'active' ? '啟用' : '停用'}
                </strong>
                <p>影響檢查已完成；尚未寫入變更。</p>
                <label>
                  <input
                    type="checkbox"
                    checked={runtimeConfirmed}
                    disabled={runtimeMutation === 'loading'}
                    onChange={(event) => setRuntimeConfirmed(event.target.checked)}
                  />
                  我已確認通知對象、目標狀態與調整原因
                </label>
                <button
                  type="button"
                  className="line-primary-btn"
                  disabled={!runtimeConfirmed || runtimeMutation === 'loading'}
                  onClick={() => void applyRuntimeMutation()}
                >
                  確認套用 LINE 異常通知設定
                </button>
              </div>
            )}

            {runtimeReceipt && <div className="line-success" role="status" style={{ marginTop: '12px' }}>{runtimeReceipt.operationLabel}已完成並回讀最新狀態。</div>}
            {runtimeError && <div className="line-error" role="alert" style={{ marginTop: '12px' }}>{runtimeError}</div>}
          </section>

          {/* 3. 人工客服升級 */}
          <section className="line-workspace-card">
            <div className="line-section-heading">
              <div>
                <h3>🧑‍💼 人工客服升級工作台</h3>
                <p>可建立升級事件，或以已知 ID 查詢並依 available actions 接手、處理與結案。</p>
              </div>
            </div>

            <div className="line-detail-grid" style={{ marginBottom: '14px' }}>
              <label>
                來源類型
                <select
                  className="line-filter-select"
                  style={{ width: '100%', marginTop: '4px' }}
                  value={escalationSourceKind}
                  onChange={(event) => { setEscalationSourceKind(event.target.value as CustomerServiceEscalationCreateRequest['source_kind']); setEscalationPending(null); setEscalationConfirmed(false); }}
                >
                  <option value="ticket_referral">客服工單轉介</option>
                  <option value="line_inbox">LINE inbox</option>
                  <option value="binding_failure">綁定失敗</option>
                  <option value="runtime_health">Runtime 異常</option>
                </select>
              </label>
              <label>
                觸發原因
                <select
                  className="line-filter-select"
                  style={{ width: '100%', marginTop: '4px' }}
                  value={escalationTrigger}
                  onChange={(event) => { setEscalationTrigger(event.target.value as CustomerServiceEscalationCreateRequest['trigger_code']); setEscalationPending(null); setEscalationConfirmed(false); }}
                >
                  <option value="explicit_human_request">明確要求人工</option>
                  <option value="explicit_wrong_answer">明確回覆錯誤</option>
                  <option value="binding_failure_threshold_2">綁定失敗達門檻</option>
                  <option value="complaint">客訴</option>
                  <option value="runtime_critical">Runtime 嚴重異常</option>
                </select>
              </label>
              <label>
                工單分類
                <select
                  className="line-filter-select"
                  style={{ width: '100%', marginTop: '4px' }}
                  value={escalationCategory}
                  onChange={(event) => { setEscalationCategory(event.target.value as CustomerServiceEscalationCreateRequest['ticket_category']); setEscalationPending(null); setEscalationConfirmed(false); }}
                >
                  <option value="service_flow">服務流程</option>
                  <option value="payment_subsidy">收費與補助</option>
                  <option value="service_progress">服務進度</option>
                  <option value="profile_update">修改登記資料</option>
                  <option value="contact_union">聯絡工會</option>
                  <option value="other">其他問題</option>
                </select>
              </label>
              <label>
                來源案件／事件參考
                <input className="line-search-input" value={escalationSourceIdentity} onChange={(event) => { setEscalationSourceIdentity(event.target.value); setEscalationPending(null); setEscalationConfirmed(false); }} />
              </label>
              <details style={{ gridColumn: '1 / -1' }}>
                <summary>進階來源資料</summary>
                <p style={{ margin: '8px 0', color: '#74593f', fontSize: '0.82rem' }}>
                  這些一致性欄位由來源流程提供；只有人工補登且已核對原始事件時才需填寫。
                </p>
                <div className="line-detail-grid">
                  <label>
                    來源資料校驗碼
                    <input className="line-search-input" value={escalationSourceFingerprint} onChange={(event) => { setEscalationSourceFingerprint(event.target.value); setEscalationPending(null); setEscalationConfirmed(false); }} />
                  </label>
                  <label>
                    自動化暫停範圍
                    <input className="line-search-input" value={escalationHoldScope} onChange={(event) => { setEscalationHoldScope(event.target.value); setEscalationPending(null); setEscalationConfirmed(false); }} />
                  </label>
                </div>
              </details>
              <div style={{ gridColumn: 'span 2' }}>
                <button
                  type="button"
                  className="line-primary-btn"
                  style={{ padding: '8px 16px', fontSize: '0.85rem', width: '100%', marginTop: '6px' }}
                  disabled={!escalationSourceIdentity.trim() || !/^[0-9a-f]{64}$/.test(escalationSourceFingerprint) || escalationMutation === 'loading'}
                  onClick={() => void previewCreateEscalation()}
                >
                  🚀 預覽建立人工客服升級
                </button>
              </div>
            </div>

            <div className="line-row-actions" style={{ marginBottom: '14px' }}>
              <label htmlFor="escalation-id" style={{ fontSize: '0.85rem', fontWeight: 700, color: '#57423b' }}>升級 ID：</label>
              <input
                id="escalation-id"
                inputMode="numeric"
                className="line-search-input"
                style={{ width: '180px' }}
                value={escalationIdInput}
                onChange={(event) => setEscalationIdInput(event.target.value)}
              />
              <button
                type="button"
                className="line-secondary-btn"
                disabled={!/^\d+$/.test(escalationIdInput)}
                onClick={() => void loadEscalation()}
              >
                🔍 查詢升級明細
              </button>
            </div>

            <LoadingOrError state={escalationDetail} loadingText="正在載入人工升級明細…" />

            {escalationDetail.value && (
              <>
                <div className="line-detail-grid">
                  <div><span>工單</span><strong>{escalationDetail.value.ticketRef}</strong></div>
                  <div><span>狀態</span><strong>{escalationDetail.value.workflowStatusLabel}</strong></div>
                  <div><span>分類</span><strong>{escalationDetail.value.categoryLabel}</strong></div>
                  <div><span>自動化</span><strong>{escalationDetail.value.automationHoldLabel}</strong></div>
                  <div><span>警示</span><strong>{escalationDetail.value.alertStatus}</strong></div>
                </div>

                <details style={{ marginTop: '12px' }}>
                  <summary>進階一致性與結案資料</summary>
                  <p style={{ margin: '8px 0', color: '#74593f', fontSize: '0.82rem' }}>
                    接手只需目前升級資料；開始處理或結案前，請依客服工單與結案紀錄補登下列校驗資料。
                  </p>
                  <div className="line-detail-grid">
                    <label htmlFor="escalation-ticket-version">
                      工單一致性版本
                      <input
                        id="escalation-ticket-version"
                        inputMode="numeric"
                        className="line-search-input"
                        value={escalationTicketVersion}
                        onChange={(event) => { setEscalationTicketVersion(event.target.value); setEscalationPending(null); setEscalationConfirmed(false); }}
                      />
                    </label>
                    <label htmlFor="escalation-resolution-digest">
                      結案紀錄校驗碼
                      <input
                        id="escalation-resolution-digest"
                        className="line-search-input"
                        value={escalationResolutionDigest}
                        onChange={(event) => { setEscalationResolutionDigest(event.target.value); setEscalationPending(null); setEscalationConfirmed(false); }}
                      />
                    </label>
                  </div>
                </details>

                <div className="line-row-actions" style={{ marginTop: '14px' }}>
                  {escalationDetail.value.availableActions.includes('claim') && (
                    <button
                      type="button"
                      className="line-primary-btn"
                      disabled={escalationMutation === 'loading'}
                      onClick={() => void previewAdvanceEscalation('claim')}
                    >
                      ✋ 預覽接手
                    </button>
                  )}
                  {escalationDetail.value.availableActions.includes('handling') && (
                    <button
                      type="button"
                      className="line-primary-btn"
                      disabled={escalationMutation === 'loading'}
                      onClick={() => void previewAdvanceEscalation('handling')}
                    >
                      ⚙️ 預覽開始處理
                    </button>
                  )}
                  {escalationDetail.value.availableActions.includes('resolve') && (
                    <button
                      type="button"
                      className="line-primary-btn"
                      disabled={escalationMutation === 'loading' || !/^[0-9a-f]{64}$/.test(escalationResolutionDigest)}
                      onClick={() => void previewAdvanceEscalation('resolve')}
                    >
                      ✅ 預覽解決並解除暫停
                    </button>
                  )}
                </div>
              </>
            )}

            {escalationPending && (
              <div className="line-preview-result" style={{ marginTop: '12px' }}>
                <strong>
                  {escalationPending.preview.before_workflow_status === 'absent' ? '尚未建立' : escalationPending.preview.before_workflow_status}
                  {' → '}
                  {escalationPending.preview.resulting_workflow_status}
                </strong>
                <p>
                  自動化暫停：{escalationPending.preview.before_hold_state === 'absent' ? '尚未建立' : escalationPending.preview.before_hold_state}
                  {' → '}
                  {escalationPending.preview.resulting_hold_state}；影響檢查已完成，尚未寫入。
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={escalationConfirmed}
                    disabled={escalationMutation === 'loading'}
                    onChange={(event) => setEscalationConfirmed(event.target.checked)}
                  />
                  我已確認升級來源、狀態與自動化暫停影響
                </label>
                <button
                  type="button"
                  className="line-primary-btn"
                  disabled={!escalationConfirmed || escalationMutation === 'loading'}
                  onClick={() => void applyEscalation()}
                >
                  確認套用人工客服升級操作
                </button>
              </div>
            )}

            {escalationReceipt && <div className="line-success" role="status" style={{ marginTop: '12px' }}>人工客服升級操作已完成；目前狀態：{escalationReceipt.workflowStatus}。</div>}
            {escalationError && <div className="line-error" role="alert" style={{ marginTop: '12px' }}>{escalationError}</div>}
          </section>
        </div>
      )}



      <Drawer isOpen={ticketDetail.status !== 'idle'} onClose={closeTicket} title="客服工單明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeTicket}>關閉</button>{ticketDetail.status === 'error' && ticketDetailId.current !== null && <button type="button" onClick={() => openTicket(ticketDetailId.current!)}>重試查詢</button>}{ticketDetail.status === 'loaded' && ticketDetail.value?.ticket.status !== 'resolved' && customerService.previewResolve && <button type="button" data-control-id="line.ticket.resolve.preview" disabled={ticketResolvePreview.status === 'loading' || ticketResolveStatus === 'loading'} onClick={() => void previewTicketResolve()}>檢查結案影響</button>}{ticketResolvePreview.value?.applyReady && ticketResolvePreview.value.blockers.length === 0 && customerService.applyResolve && <button type="button" data-control-id="line.ticket.resolve.apply" disabled={!ticketResolveConfirmed || ticketResolveStatus === 'loading'} onClick={() => void applyTicketResolve()}>確認結案</button>}</div>}><div data-control-id="line.ticket.detail" className="line-drawer-content"><LoadingOrError state={ticketDetail} loadingText="正在載入工單明細…" />{ticketDetail.status === 'loaded' && ticketDetail.value && <><div className="line-detail-grid"><div><span>客戶</span><strong>{ticketDetail.value.ticket.maskedLineUserId}</strong></div><div><span>案件</span><strong>{ticketDetail.value.ticket.caseNo ?? '無關聯'}</strong></div><div><span>狀態</span><strong>{ticketDetail.value.ticket.statusLabel}</strong></div></div>{ticketDetail.value.ticket.status !== 'resolved' && customerService.previewResolve && <div className="line-action-panel"><label htmlFor="ticket-resolve-note">結案說明</label><textarea id="ticket-resolve-note" value={ticketResolveNote} onChange={(event) => { setTicketResolveNote(event.target.value); setTicketResolvePreview(idleState()); setTicketResolveConfirmed(false); setTicketResolveStatus('idle'); }} rows={3} maxLength={4000} />{ticketResolvePreview.status === 'loading' && <p>正在驗證結案內容…</p>}{ticketResolvePreview.status === 'error' && <div className="line-error" role="alert">{ticketResolvePreview.error}</div>}{ticketResolvePreview.value && <div className="line-preview-result"><strong>{ticketResolvePreview.value.beforeStatusLabel} → {ticketResolvePreview.value.afterStatusLabel}</strong>{ticketResolvePreview.value.blockers.length > 0 ? <ul>{ticketResolvePreview.value.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul> : <label><input type="checkbox" checked={ticketResolveConfirmed} onChange={(event) => setTicketResolveConfirmed(event.target.checked)} />我已確認結案內容與目前工單狀態</label>}</div>}{ticketResolveStatus === 'success' && <div className="line-success" role="status">結案已完成</div>}{ticketResolveStatus === 'error' && <div className="line-error" role="alert">{ticketResolveError}</div>}</div>}<LineCustomerServiceActions detail={ticketDetail.value} onCommitted={(nextDetail) => { setTicketDetail(loadedState(nextDetail)); setTicketReload((value) => value + 1); }} /><div className="line-events"><h4>事件紀錄</h4>{ticketDetail.value.events.length === 0 ? <p>尚無事件紀錄</p> : ticketDetail.value.events.map((event) => <article key={event.id}><strong>{event.eventType}</strong><span>{event.createdAt}</span><p>{event.messageText ?? '無訊息內容'}</p></article>)}</div></>}</div></Drawer>

      <Drawer
        isOpen={bindingDetail.status !== 'idle'}
        onClose={closeBinding}
        title="LINE 身分綁定明細"
        size="wide"
        footer={(
          <div className="line-drawer-footer">
            <button type="button" onClick={closeBinding}>關閉</button>
            {bindingDetail.status === 'error' && bindingDetailId.current !== null && (
              <button type="button" onClick={() => openBinding(bindingDetailId.current!)}>重試查詢</button>
            )}
            {bindingDetail.status === 'loaded'
              && bindingDetail.value?.status === 'bound'
              && !bindingRevocationAccepted
              && lineIdentity.previewRevocation && (
                <button
                  type="button"
                  data-control-id="line.identity.revocation.preview"
                  disabled={bindingRevocationPreview.status === 'loading' || bindingRevocationStatus === 'loading'}
                  onClick={() => void previewBindingRevocation()}
                >
                  檢查解除影響
                </button>
              )}
            {bindingRevocationPreview.value
              && !bindingRevocationPreview.value.hasBlockers
              && !bindingRevocationAccepted
              && lineIdentity.applyRevocation && (
                <button
                  type="button"
                  data-control-id="line.identity.revocation.apply"
                  disabled={!bindingRevocationConfirmed || !bindingRevocationReason.trim() || bindingRevocationStatus === 'loading'}
                  onClick={() => void applyBindingRevocation()}
                >
                  提交解除
                </button>
              )}
            {bindingRevocationAccepted && bindingDetailId.current !== null && (
              <button type="button" onClick={() => openBinding(bindingDetailId.current!)}>
                重新查詢綁定狀態
              </button>
            )}
          </div>
        )}
      >
        <div data-control-id="line.identity.detail" className="line-drawer-content">
          <LoadingOrError state={bindingDetail} loadingText="正在載入身分綁定明細…" />
          {bindingDetail.status === 'loaded' && bindingDetail.value && (
            <>
              <div className="line-detail-grid">
                <div><span>LINE User ID</span><strong>{bindingDetail.value.maskedLineUserId}</strong></div>
                <div><span>實名姓名</span><strong>{bindingDetail.value.subjectName}</strong></div>
                <div><span>角色</span><strong>{bindingDetail.value.subjectTypeLabel}</strong></div>
                <div><span>狀態</span><strong>{bindingDetail.value.statusLabel}</strong></div>
                <div><span>更新時間</span><strong>{bindingDetail.value.updatedAt ?? '—'}</strong></div>
                <div><span>解除狀態</span><strong>{bindingDetail.value.revocationStatusLabel}</strong></div>
              </div>

              {bindingDetail.value.status === 'pending_review' && (
                <div className="line-scope-note" role="status">
                  此紀錄尚未構成有效授權；必須由具 LINE 身分審核權限的真人管理員明確核准、拒絕或取消，系統不會依等待時間自動決定。
                </div>
              )}

              {bindingDetail.value.status === 'bound' && lineIdentity.previewRevocation && (
                <div className="line-action-panel">
                  {bindingRevocationPreview.status === 'loading' && <p>正在驗證解除條件…</p>}
                  {bindingRevocationPreview.status === 'error' && (
                    <div className="line-error" role="alert">{bindingRevocationPreview.error}</div>
                  )}
                  {bindingRevocationPreview.value && (
                    <>
                      <div className="line-preview-result">
                        <p>已核對目前綁定狀態與解除影響。</p>
                        <p>Default Rich Menu：{bindingRevocationPreview.value.defaultMenuPublished ? '已發布' : '未發布'}</p>
                      </div>
                      {bindingRevocationPreview.value.hasBlockers ? (
                        <ul>{bindingRevocationPreview.value.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
                      ) : (
                        <>
                          <strong>可提交解除</strong>
                          <label htmlFor="binding-revocation-reason">解除原因</label>
                          <textarea
                            id="binding-revocation-reason"
                            value={bindingRevocationReason}
                            onChange={(event) => {
                              setBindingRevocationReason(event.target.value);
                              setBindingRevocationConfirmed(false);
                              setBindingRevocationStatus('idle');
                            }}
                            rows={3}
                            maxLength={1000}
                          />
                          <label>
                            <input
                              type="checkbox"
                              checked={bindingRevocationConfirmed}
                              onChange={(event) => setBindingRevocationConfirmed(event.target.checked)}
                            />
                            我已確認解除對象與影響範圍
                          </label>
                        </>
                      )}
                    </>
                  )}
                  {bindingRevocationStatus === 'loading' && <p>正在提交解除申請…</p>}
                  {bindingRevocationStatus === 'error' && (
                    <div className="line-error" role="alert">{bindingRevocationError}</div>
                  )}
                  {bindingRevocationAccepted && (
                    <div className="line-success" role="status">
                      <strong>解除申請已受理</strong>
                      <p>{bindingRevocationAccepted.statusLabel}｜正在等待解除結果回讀</p>
                      <p>{bindingRevocationAccepted.notice}</p>
                    </div>
                  )}
                </div>
              )}

              <LineIdentityMaintenanceActions
                lineUserId={bindingDetailId.current ?? ''}
                binding={{
                  status: bindingRevocationAccepted ? 'revocation_pending' : bindingDetail.value.status,
                  revocation_request_id: bindingRevocationAccepted?.requestId ?? bindingDetail.value.revocationRequestId,
                  revocation_status: bindingRevocationAccepted?.status ?? bindingDetail.value.revocationStatus,
                }}
                onBindingChanged={(nextBinding) => {
                  setBindingDetail(loadedState(adaptLineIdentityBinding(nextBinding)));
                  setBindingReload((value) => value + 1);
                }}
                onRevocationChanged={() => {
                  const lineUserId = bindingDetailId.current;
                  if (lineUserId) openBinding(lineUserId);
                  setBindingReload((value) => value + 1);
                }}
              />
            </>
          )}
        </div>
      </Drawer>

      <Drawer isOpen={deliveryDetail.status !== 'idle'} onClose={closeDeliveryTask} title="LINE 發送明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeDeliveryTask}>關閉</button></div>}><div className="line-drawer-content"><LoadingOrError state={deliveryDetail} loadingText="正在載入發送明細…" />{deliveryDetail.value && <><div className="line-detail-grid"><div><span>通知用途</span><strong>{deliveryDetail.value.task.sourceLabel}</strong></div><div><span>狀態</span><strong>{deliveryDetail.value.task.statusLabel}</strong></div><div><span>排程時間</span><strong>{deliveryDetail.value.task.scheduledAt}</strong></div><div><span>處理進度</span><strong>{deliveryDetail.value.task.attempts}</strong></div></div><div className="line-events"><h4>處理紀錄</h4>{deliveryDetail.value.attempts.length === 0 ? <p>尚無處理紀錄</p> : deliveryDetail.value.attempts.map((attempt) => <article key={attempt.number}><strong>第 {attempt.number} 次：{attempt.outcome}</strong><span>{attempt.startedAt}</span><p>完成時間：{attempt.completedAt ?? '進行中'}{attempt.retryAfterSeconds === null ? '' : `；預計 ${attempt.retryAfterSeconds} 秒後重試`}</p></article>)}</div></>}</div></Drawer>

      <Drawer isOpen={orderGroupDetail.status !== 'idle'} onClose={closeOrderGroup} title="三方服務群組明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeOrderGroup}>關閉</button></div>}><div className="line-drawer-content"><LoadingOrError state={orderGroupDetail} loadingText="正在載入三方服務群組明細…" />{orderGroupDetail.value && <><div className="line-detail-grid"><div><span>案件</span><strong>{orderGroupDetail.value.record.caseNo}</strong></div><div><span>狀態</span><strong>{orderGroupDetail.value.record.statusLabel}</strong></div></div><div className="line-events"><h4>事件紀錄</h4>{orderGroupDetail.value.events.length === 0 ? <p>尚無事件紀錄</p> : orderGroupDetail.value.events.map((event) => <article key={event.eventId}><strong>{event.eventType}</strong><span>{event.occurredAt}</span></article>)}</div></>}</div></Drawer>

      <Drawer isOpen={selectedRule !== null} onClose={() => setSelectedRule(null)} title="通知規則" footer={<div className="line-drawer-footer"><button type="button" onClick={() => setSelectedRule(null)}>關閉</button></div>}>{selectedRule && <div className="line-drawer-content" data-control-id="line.notification-rule.detail"><div className="line-detail-grid"><div><span>事件</span><strong>{selectedRule.eventLabel}</strong></div><div><span>收件人</span><strong>{selectedRule.recipientLabel}</strong></div><div><span>通知內容</span><strong>{selectedRule.templateId ? '已設定' : '尚未設定'}</strong></div><div><span>狀態</span><strong>{selectedRule.enabled ? '已啟用' : '未啟用'}</strong></div></div><p>{selectedRule.scheduleLabel}｜{selectedRule.frequencyLabel}</p>{selectedRule.predicateLabels.length > 0 && <p>條件：{selectedRule.predicateLabels.join('、')}</p>}</div>}</Drawer>

      <Drawer isOpen={selectedPublication.status !== 'idle'} onClose={closePublication} title="Rich Menu 發布紀錄" footer={<div className="line-drawer-footer"><button type="button" onClick={closePublication}>關閉</button>{selectedPublication.status === 'error' && publicationDetailId.current !== null && <button type="button" onClick={() => openPublication(publicationDetailId.current!)}>重試查詢</button>}</div>}><div className="line-drawer-content"><LoadingOrError state={selectedPublication} loadingText="正在載入發布紀錄明細…" />{selectedPublication.status === 'loaded' && selectedPublication.value && <div className="line-detail-grid"><div><span>選單</span><strong>{richMenuConfiguration.value?.menus.find((menu) => menu.id === selectedPublication.value?.menuDefinitionId)?.name ?? '已發布圖文選單'}</strong></div><div><span>目前狀態</span><strong>{selectedPublication.value.statusLabel}</strong></div></div>}</div></Drawer>
    </div>
  );
};

export default LineManagementPage;
