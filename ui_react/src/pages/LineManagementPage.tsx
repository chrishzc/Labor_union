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
import {
  adaptCustomerServiceEscalation,
  adaptCustomerServiceEscalationReceipt,
  type CustomerServiceEscalationModel,
  type CustomerServiceEscalationReceiptModel,
} from '../adapters/customer_service_escalations/customer_service_escalation_adapter';
import { customerServiceEscalationClient } from '../api/customer_service_escalations/customer_service_escalation_client';
import { CustomerServiceEscalationError } from '../api/customer_service_escalations/customer_service_escalation_errors';
import type { CustomerServiceEscalationCreateRequest } from '../api/customer_service_escalations/customer_service_escalation_schemas';
import { Drawer } from '../components/Drawer';
import './LineManagementPage.css';

type LineTab = 'tickets' | 'richmenu' | 'binding' | 'push_queue' | 'order_groups' | 'runtime';

type CustomerServicePageClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'> &
  Partial<Pick<CustomerServiceClient, 'previewResolve' | 'applyResolve'>>;
type LineIdentityPageClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'> &
  Partial<Pick<LineIdentityClient, 'previewRevocation' | 'applyRevocation'>>;

interface LineManagementPageProps {
  customerService?: CustomerServicePageClient;
  lineIdentity?: LineIdentityPageClient;
  lineConfiguration?: LineConfigurationQueryClient;
}

type QueryStatus = 'idle' | 'loading' | 'loaded' | 'error';
type MutationStatus = 'idle' | 'loading' | 'success' | 'error';
type LineDeliverySummaryView = ReturnType<typeof adaptLineDeliverySummary>;
type LineDeliveryItemView = ReturnType<typeof adaptLineDeliveryItem>;
type LineDeliveryDetailView = ReturnType<typeof adaptLineDeliveryDetail>;

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
  const [rulesReload, setRulesReload] = useState(0);
  const [selectedRule, setSelectedRule] = useState<LineNotificationRuleModel | null>(null);
  const [deliverySummary, setDeliverySummary] = useState<QueryState<LineDeliverySummaryView>>(idleState);
  const [deliveryItems, setDeliveryItems] = useState<QueryState<LineDeliveryItemView[]>>(idleState);
  const [deliveryDetail, setDeliveryDetail] = useState<QueryState<LineDeliveryDetailView>>(idleState);
  const deliveryDetailController = useRef<AbortController | null>(null);

  const [orderGroups, setOrderGroups] = useState<QueryState<LineOrderGroupRecordView[]>>(idleState);
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
  const [runtimeMutation, setRuntimeMutation] = useState<MutationStatus>('idle');
  const [runtimeError, setRuntimeError] = useState<string | null>(null);

  const [escalationIdInput, setEscalationIdInput] = useState('');
  const [escalationTicketVersion, setEscalationTicketVersion] = useState('0');
  const [escalationDetail, setEscalationDetail] = useState<QueryState<CustomerServiceEscalationModel>>(idleState);
  const [escalationReceipt, setEscalationReceipt] = useState<CustomerServiceEscalationReceiptModel | null>(null);
  const [escalationMutation, setEscalationMutation] = useState<MutationStatus>('idle');
  const [escalationError, setEscalationError] = useState<string | null>(null);
  const [escalationResolutionDigest, setEscalationResolutionDigest] = useState('');
  const [escalationSourceIdentity, setEscalationSourceIdentity] = useState('');
  const [escalationSourceFingerprint, setEscalationSourceFingerprint] = useState('');
  const [escalationHoldScope, setEscalationHoldScope] = useState('customer_service_automation');
  const [escalationSourceKind, setEscalationSourceKind] = useState<CustomerServiceEscalationCreateRequest['source_kind']>('ticket_referral');
  const [escalationTrigger, setEscalationTrigger] = useState<CustomerServiceEscalationCreateRequest['trigger_code']>('explicit_human_request');
  const [escalationCategory, setEscalationCategory] = useState<CustomerServiceEscalationCreateRequest['ticket_category']>('contact_union');

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
    setDeliverySummary(loadingState());
    setDeliveryItems(loadingState());
    const timer = window.setTimeout(() => {
      void Promise.allSettled([
        lineConfiguration.getNotificationRules({ signal: controller.signal }),
        lineDeliveryQueryClient.summary({ signal: controller.signal }),
        lineDeliveryQueryClient.list({ page: 1, pageSize: 100 }, { signal: controller.signal }),
      ]).then(([rulesResult, summaryResult, tasksResult]) => {
        if (cancelled) return;
        if (rulesResult.status === 'fulfilled') setRules(loadedState(adaptLineNotificationRulesCatalog(rulesResult.value)));
        else setRules(errorState(displayQueryError(rulesResult.reason, '通知規則目錄載入失敗')));
        if (summaryResult.status === 'fulfilled') setDeliverySummary(loadedState(adaptLineDeliverySummary(summaryResult.value)));
        else setDeliverySummary(errorState(displayQueryError(summaryResult.reason, '發送任務摘要載入失敗')));
        if (tasksResult.status === 'fulfilled') setDeliveryItems(loadedState(tasksResult.value.items.map(adaptLineDeliveryItem)));
        else setDeliveryItems(errorState(displayQueryError(tasksResult.reason, '發送任務清單載入失敗')));
      });
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
    if (activeTab !== 'order_groups') return;
    const controller = new AbortController();
    let cancelled = false;
    setOrderGroups(loadingState());
    const timer = window.setTimeout(() => {
      void lineOrderGroupQueryClient.list({ limit: 200 }, { signal: controller.signal })
        .then((page) => {
          if (!cancelled) setOrderGroups(loadedState(page.items.map(adaptLineOrderGroupRecord)));
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
        lineRuntimeTargetClient.listTargets({ correlationId, signal: controller.signal }),
        lineRuntimeTargetClient.listAdminCandidates({ correlationId, signal: controller.signal }),
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
  }, [activeTab, runtimeReload]);

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
  }, [activeTab]);

  useEffect(() => () => {
    ticketDetailController.current?.abort();
    ticketResolveController.current?.abort();
    bindingDetailController.current?.abort();
    bindingRevocationController.current?.abort();
    publicationController.current?.abort();
    deliveryDetailController.current?.abort();
    orderGroupDetailController.current?.abort();
    ticketDetailGeneration.current += 1;
    bindingDetailGeneration.current += 1;
    publicationGeneration.current += 1;
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

  const runRuntimeMutation = async (operation: 'add' | 'reset' | 'toggle', target?: LineRuntimeTargetModel) => {
    if (!runtimeReason.trim()) return;
    const correlationId = operationIdentity(`line-runtime-${operation}`);
    const idempotencyKey = operationIdentity(`line-runtime-${operation}-apply`);
    setRuntimeMutation('loading');
    setRuntimeError(null);
    setRuntimeReceipt(null);
    try {
      let receipt;
      if (operation === 'add') {
        if (selectedRuntimeCandidate === null) return;
        receipt = await lineRuntimeTargetClient.addAdminTarget({ admin_user_id: selectedRuntimeCandidate, minimum_status: 'warning', reason: runtimeReason.trim(), correlation_id: correlationId, idempotency_key: idempotencyKey });
      } else if (operation === 'reset') {
        if (!target) return;
        receipt = await lineRuntimeTargetClient.resetGroup({ expected_version: target.currentVersion, reason: runtimeReason.trim(), correlation_id: correlationId, idempotency_key: idempotencyKey });
      } else {
        if (!target) return;
        receipt = await lineRuntimeTargetClient.setEnabled(target.targetId, { expected_version: target.currentVersion, enabled: target.state !== 'active', reason: runtimeReason.trim(), correlation_id: correlationId, idempotency_key: idempotencyKey });
      }
      setRuntimeReceipt(adaptLineRuntimeTargetReceipt(receipt));
      setRuntimeMutation('success');
      refreshRuntime();
    } catch (error: unknown) {
      setRuntimeMutation('error');
      setRuntimeError(displayQueryError(error, '異常通知對象更新失敗'));
    }
  };

  const loadEscalation = async (escalationId = Number(escalationIdInput)) => {
    if (!Number.isInteger(escalationId) || escalationId < 1) return;
    setEscalationDetail(loadingState());
    setEscalationError(null);
    try {
      const detail = await customerServiceEscalationClient.getDetail(escalationId, { correlationId: operationIdentity('line-escalation-detail') });
      setEscalationDetail(loadedState(adaptCustomerServiceEscalation(detail)));
      setEscalationIdInput(String(escalationId));
    } catch (error: unknown) {
      setEscalationDetail(errorState(displayQueryError(error, '人工升級明細載入失敗')));
    }
  };

  const createEscalation = async () => {
    if (!escalationSourceIdentity.trim() || !/^[0-9a-f]{64}$/.test(escalationSourceFingerprint) || !escalationHoldScope.trim()) return;
    const correlationId = operationIdentity('line-escalation-create');
    setEscalationMutation('loading');
    setEscalationError(null);
    try {
      const receipt = await customerServiceEscalationClient.create({
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
      });
      const model = adaptCustomerServiceEscalationReceipt(receipt);
      setEscalationReceipt(model);
      setEscalationMutation('success');
      await loadEscalation(model.escalationId);
    } catch (error: unknown) {
      setEscalationMutation('error');
      setEscalationError(displayQueryError(error, '人工升級建立失敗'));
    }
  };

  const advanceEscalation = async (operation: 'claim' | 'handling' | 'resolve') => {
    const detail = escalationDetail.value;
    const ticketVersion = Number(escalationTicketVersion);
    if (!detail || !Number.isInteger(ticketVersion) || ticketVersion < 0) return;
    const correlationId = operationIdentity(`line-escalation-${operation}`);
    const identity = { correlation_id: correlationId, idempotency_key: operationIdentity(`line-escalation-${operation}-apply`) };
    setEscalationMutation('loading');
    setEscalationError(null);
    try {
      let receipt;
      if (operation === 'claim') receipt = await customerServiceEscalationClient.claim(detail.escalationId, { expected_escalation_version: detail.workflowVersion, ...identity });
      else if (operation === 'handling') receipt = await customerServiceEscalationClient.startHandling(detail.escalationId, { expected_escalation_version: detail.workflowVersion, expected_ticket_version: ticketVersion, ...identity });
      else {
        if (!/^[0-9a-f]{64}$/.test(escalationResolutionDigest)) return;
        receipt = await customerServiceEscalationClient.resolve(detail.escalationId, { expected_escalation_version: detail.workflowVersion, expected_ticket_version: ticketVersion, resolution_code: 'handled_by_union_staff', resolution_evidence_digest: escalationResolutionDigest, ...identity });
      }
      setEscalationReceipt(adaptCustomerServiceEscalationReceipt(receipt));
      setEscalationMutation('success');
      await loadEscalation(detail.escalationId);
    } catch (error: unknown) {
      setEscalationMutation('error');
      setEscalationError(displayQueryError(error, '人工升級狀態更新失敗'));
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

      {activeTab === 'tickets' && <section className="line-table-container"><div className="line-section-heading"><div><h3>📋 客服工單與案件關聯追蹤清單</h3><p>清單提供狀態與案件關聯；訊息內容由明細與事件紀錄呈現。</p></div><button type="button" className="line-secondary-btn" onClick={() => setTicketReload((value) => value + 1)}>重新整理</button></div><div className="line-kpi-grid"><div data-control-id="line.ticket.summary.waiting"><span>待處理</span><strong>{ticketSummary.value?.waiting ?? '—'}</strong></div><div data-control-id="line.ticket.summary.handling"><span>處理中</span><strong>{ticketSummary.value?.handling ?? '—'}</strong></div><div data-control-id="line.ticket.summary.resolved_today"><span>今日結案</span><strong>{ticketSummary.value?.resolvedToday ?? '—'}</strong></div></div>{ticketSummary.status === 'loading' && <div className="line-loading">正在載入客服摘要…</div>}{ticketSummary.status === 'error' && <div className="line-error" role="alert">{ticketSummary.error}</div>}{ticketPage.status === 'loading' && <div className="line-loading">正在載入客服工單…</div>}{ticketPage.status === 'error' && <div className="line-error" role="alert">{ticketPage.error}</div>}{ticketPage.status === 'loaded' && ticketPage.value && (ticketPage.value.items.length === 0 ? <div className="line-empty-state"><div>📋</div><h4>目前沒有客服工單</h4><p>可由 LINE 客服入口或人工升級流程建立新工單。</p></div> : <><div className="line-scope-note">第 {ticketPage.value.page} 頁，共載入 {ticketPage.value.items.length} 筆；總數 {ticketPage.value.total}。</div><div className="line-table-scroll"><table className="line-data-table" data-control-id="line.ticket.table"><thead><tr><th>工單編號</th><th>提問對象</th><th>關聯案件</th><th>分類</th><th>問題摘要</th><th>時間</th><th>狀態</th><th>操作</th></tr></thead><tbody>{ticketPage.value.items.map((ticket) => <tr key={ticket.ticketId}><td><strong>#{ticket.ticketIdText}</strong></td><td>👤 {ticket.maskedLineUserId}</td><td>{ticket.caseNo ?? '無關聯'}</td><td>{ticket.categoryLabel}</td><td>{ticket.issueSummary ?? CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE}</td><td>{ticket.createdAt ?? '—'}</td><td><span className={`line-status line-status-${ticket.status}`}>{ticket.statusLabel}</span></td><td><button type="button" data-control-id="line.ticket.detail" onClick={() => openTicket(ticket.ticketId)}>查看明細</button></td></tr>)}</tbody></table></div></>)}</section>}

      {activeTab === 'richmenu' && <section className="line-workspace-card" data-control-id="line.richmenu.configuration"><div className="line-section-heading"><div><h3>📱 多角色 Rich Menu 圖文選單</h3><p>檢查目前角色選單設定與後端發布紀錄；外送由 durable task 負責。</p></div><button type="button" className="line-secondary-btn" data-control-id="line.richmenu.refresh" onClick={() => setRichMenuReload((value) => value + 1)}>重新整理</button></div><LoadingOrError state={richMenuConfiguration} loadingText="正在載入 Rich Menu 設定…" />{richMenuConfiguration.status === 'loaded' && richMenuConfiguration.value?.isEmpty && <div className="line-empty-state"><div>📱</div><h4>目前尚未設定 Rich Menu</h4><p>設定完成後會在這裡顯示各角色選單。</p></div>}{richMenuConfiguration.status === 'loaded' && richMenuConfiguration.value && !richMenuConfiguration.value.isEmpty && <><div className="line-role-switcher">{richMenuConfiguration.value.menus.map((menu) => <button key={menu.id} type="button" className={selectedMenu?.id === menu.id ? 'active' : ''} onClick={() => setSelectedMenuId(menu.id)}>{menu.audienceRoleLabel}｜{menu.name}</button>)}</div>{selectedMenu && <div className="line-phone-preview"><div className="line-phone-header">{selectedMenu.name}</div><div className="line-phone-message">{selectedMenu.chatBarText}</div><div className="line-menu-grid">{selectedMenu.buttons.map((button) => <div key={button.id}>{button.label}</div>)}</div></div>}</>}{richMenuPublications.status === 'loading' && <div className="line-loading">正在載入 Rich Menu 發布紀錄…</div>}{richMenuPublications.status === 'error' && <div className="line-error" role="alert">{richMenuPublications.error}</div>}{richMenuPublications.status === 'loaded' && richMenuPublications.value && <div className="line-publication-history" data-control-id="line.richmenu.publications"><h4>發布紀錄</h4><p>目前載入最多 100 筆。</p>{richMenuPublications.value.items.length ? <div className="line-table-scroll"><table className="line-data-table"><thead><tr><th>ID</th><th>選單</th><th>設定版本</th><th>狀態</th><th>操作</th></tr></thead><tbody>{richMenuPublications.value.items.map((publication) => <tr key={publication.id}><td>{publication.id}</td><td>{publication.menuDefinitionId}</td><td>{publication.configurationRevision}</td><td>{publication.statusLabel}</td><td><button type="button" data-control-id="line.richmenu.publication-detail" onClick={() => openPublication(publication.id)}>查看</button></td></tr>)}</tbody></table></div> : <div className="line-empty-state"><h4>目前沒有發布紀錄</h4></div>}</div>}</section>}

      {activeTab === 'binding' && <section className="line-workspace-card"><div className="line-section-heading"><div><h3>🔑 LINE 身分綁定與解除</h3><p>查詢遮罩身分、綁定狀態與版本，並由明細執行解除 Preview／Apply。</p></div><button type="button" className="line-secondary-btn" onClick={() => setBindingReload((value) => value + 1)}>重新整理</button></div><LoadingOrError state={bindingPage} loadingText="正在載入身分綁定…" />{bindingPage.status === 'loaded' && bindingPage.value && (bindingPage.value.items.length === 0 ? <div className="line-empty-state"><div>🔑</div><h4>目前沒有身分綁定</h4><p>完成 LINE 身分綁定後會顯示在這裡。</p></div> : <><div className="line-scope-note">第 {bindingPage.value.page} 頁，共載入 {bindingPage.value.items.length} 筆；總數 {bindingPage.value.total}。</div><div className="line-table-scroll"><table className="line-data-table" data-control-id="line.identity.table"><thead><tr><th>LINE User ID</th><th>實名姓名</th><th>角色</th><th>更新時間</th><th>狀態</th><th>解除狀態</th><th>操作</th></tr></thead><tbody>{bindingPage.value.items.map((record, index) => <tr key={`${record.maskedLineUserId}-${record.version}-${index}`}><td><code>{record.maskedLineUserId}</code></td><td>👤 {record.subjectName}</td><td>{record.subjectTypeLabel}</td><td>{record.updatedAt ?? '—'}</td><td>{record.statusLabel}</td><td>{record.revocationStatusLabel}</td><td><button type="button" data-control-id="line.identity.detail" onClick={() => openBinding(bindingSources[index] ?? '')}>查看明細</button></td></tr>)}</tbody></table></div></>)}</section>}

      {activeTab === 'push_queue' && <section className="line-workspace-card"><div className="line-section-heading"><div><h3>🔔 通知規則與發送任務</h3><p>查詢目前規則版本、發送佇列狀態與每次嘗試結果。</p></div><button type="button" className="line-secondary-btn" data-control-id="line.notification-rules.refresh" onClick={() => setRulesReload((value) => value + 1)}>重新整理</button></div><LoadingOrError state={rules} loadingText="正在載入通知規則目錄…" />{rules.status === 'loaded' && rules.value?.isEmpty && <div className="line-empty-state" data-control-id="line.notification-rules.empty"><div>🔔</div><h4>目前尚未設定通知規則</h4><p>Current revision：{rules.value.revision}。</p></div>}{rules.status === 'loaded' && rules.value && !rules.value.isEmpty && <div className="line-rule-list" data-control-id="line.notification-rules.list">{rules.value.rules.map((rule) => <button key={rule.id} type="button" className="line-rule-card" onClick={() => setSelectedRule(rule)}><span>{rule.eventLabel}｜{rule.recipientLabel}</span><strong>{rule.id}</strong><small>{rule.scheduleLabel}｜{rule.frequencyLabel}｜{rule.enabled ? '已啟用' : '未啟用'}</small></button>)}</div>}<LoadingOrError state={deliverySummary} loadingText="正在載入發送任務摘要…" />{deliverySummary.value && <div className="line-kpi-grid"><div><span>全部任務</span><strong>{deliverySummary.value.total}</strong></div><div><span>待執行</span><strong>{deliverySummary.value.pending}</strong></div><div><span>處理中</span><strong>{deliverySummary.value.processing}</strong></div><div><span>已送達</span><strong>{deliverySummary.value.sent}</strong></div><div><span>失敗／待重試</span><strong>{deliverySummary.value.failed + deliverySummary.value.retryable_failed}</strong></div><div><span>Worker</span><strong>{deliverySummary.value.workerLabel}</strong></div></div>}<LoadingOrError state={deliveryItems} loadingText="正在載入發送任務…" />{deliveryItems.status === 'loaded' && deliveryItems.value && (deliveryItems.value.length === 0 ? <div className="line-empty-state"><h4>目前沒有發送任務</h4></div> : <div className="line-table-scroll"><table className="line-data-table" data-control-id="line.delivery.table"><thead><tr><th>ID</th><th>來源</th><th>任務類型</th><th>狀態</th><th>排程時間</th><th>嘗試</th><th>操作</th></tr></thead><tbody>{deliveryItems.value.map((task) => <tr key={task.taskId}><td>{task.taskId}</td><td>{task.sourceType}</td><td>{task.taskType}</td><td>{task.statusLabel}</td><td>{task.scheduledAt}</td><td>{task.attempts}</td><td><button type="button" onClick={() => openDeliveryTask(task.taskId)}>查看明細</button></td></tr>)}</tbody></table></div>)}</section>}

      {activeTab === 'order_groups' && <section className="line-table-container"><div className="line-section-heading"><div><h3>👥 三方服務群組</h3><p>依案件查詢群組綁定狀態、版本與事件紀錄。</p></div><button type="button" className="line-secondary-btn" onClick={() => setOrderGroupReload((value) => value + 1)}>重新整理</button></div><LoadingOrError state={orderGroups} loadingText="正在載入三方服務群組…" />{orderGroups.status === 'loaded' && orderGroups.value && (orderGroups.value.length === 0 ? <div className="line-empty-state"><h4>目前沒有三方服務群組</h4><p>訂單建立群組後會顯示在這裡。</p></div> : <div className="line-table-scroll"><table className="line-data-table" data-control-id="line.order-groups.table"><thead><tr><th>案件</th><th>群組識別</th><th>狀態</th><th>版本</th><th>操作</th></tr></thead><tbody>{orderGroups.value.map((record) => <tr key={record.caseNo}><td>{record.caseNo}</td><td>{record.groupIdentity}</td><td>{record.statusLabel}</td><td>{record.version}</td><td><button type="button" onClick={() => openOrderGroup(record.caseNo)}>查看明細</button></td></tr>)}</tbody></table></div>)}</section>}

      {activeTab === 'runtime' && <div className="line-runtime-workspace"><section className="line-workspace-card"><div className="line-section-heading"><div><h3>🛡️ LINE 去敏設定狀態</h3><p>只顯示六種設定的版本與是否已設定，不傳送 definition 或 provider secret。</p></div><button type="button" className="line-secondary-btn" onClick={refreshRuntime}>重新整理</button></div><LoadingOrError state={safeConfigurations} loadingText="正在載入 LINE 設定狀態…" />{safeConfigurations.value && <div className="line-kpi-grid">{safeConfigurations.value.map((config) => <div key={config.kind}><span>{config.kindLabel}</span><strong>{config.stateLabel}</strong><small>revision {config.revision}</small></div>)}</div>}</section><section className="line-workspace-card"><div className="line-section-heading"><div><h3>🚨 異常通知對象</h3><p>查詢並調整群組或管理員通知對象；每次更新均帶版本、correlation 與 idempotency。</p></div></div><label htmlFor="runtime-reason">調整原因</label><input id="runtime-reason" value={runtimeReason} onChange={(event) => setRuntimeReason(event.target.value)} maxLength={500} /><LoadingOrError state={runtimeTargets} loadingText="正在載入異常通知對象…" />{runtimeTargets.value && (runtimeTargets.value.length === 0 ? <div className="line-empty-state"><h4>目前沒有異常通知對象</h4></div> : <div className="line-table-scroll"><table className="line-data-table"><thead><tr><th>類型</th><th>顯示名稱</th><th>狀態</th><th>門檻</th><th>操作</th></tr></thead><tbody>{runtimeTargets.value.map((target) => <tr key={target.targetId}><td>{target.targetKindLabel}</td><td>{target.displayLabel}</td><td>{target.stateLabel}</td><td>{target.minimumStatusLabel}</td><td><div className="line-row-actions"><button type="button" disabled={runtimeMutation === 'loading' || !runtimeReason.trim()} onClick={() => void runRuntimeMutation('toggle', target)}>{target.state === 'active' ? '停用' : '啟用'}</button>{target.targetKind === 'group' && <button type="button" disabled={runtimeMutation === 'loading' || !runtimeReason.trim()} onClick={() => void runRuntimeMutation('reset', target)}>重設群組</button>}</div></td></tr>)}</tbody></table></div>)}<LoadingOrError state={runtimeCandidates} loadingText="正在載入管理員候選…" />{runtimeCandidates.value && <div className="line-row-actions"><label htmlFor="runtime-candidate">新增管理員對象</label><select id="runtime-candidate" value={selectedRuntimeCandidate ?? ''} onChange={(event) => setSelectedRuntimeCandidate(event.target.value ? Number(event.target.value) : null)}><option value="">請選擇已連結 LINE 的管理員</option>{runtimeCandidates.value.filter((candidate) => candidate.lineLinked).map((candidate) => <option key={candidate.candidateId} value={candidate.candidateId}>{candidate.displayLabel}</option>)}</select><button type="button" disabled={selectedRuntimeCandidate === null || !runtimeReason.trim() || runtimeMutation === 'loading'} onClick={() => void runRuntimeMutation('add')}>新增通知對象</button></div>}{runtimeReceipt && <div className="line-success" role="status">{runtimeReceipt.operationLabel}已完成；版本 {runtimeReceipt.currentVersion}</div>}{runtimeError && <div className="line-error" role="alert">{runtimeError}</div>}</section><section className="line-workspace-card"><div className="line-section-heading"><div><h3>🧑‍💼 人工客服升級</h3><p>可建立升級事件，或以已知 ID 查詢並依 available actions 接手、處理與結案。</p></div></div><div className="line-detail-grid"><label>來源事件識別<input value={escalationSourceIdentity} onChange={(event) => setEscalationSourceIdentity(event.target.value)} /></label><label>來源指紋（SHA-256）<input value={escalationSourceFingerprint} onChange={(event) => setEscalationSourceFingerprint(event.target.value)} /></label><label>暫停範圍<input value={escalationHoldScope} onChange={(event) => setEscalationHoldScope(event.target.value)} /></label><div><span>建立流程</span><button type="button" disabled={!escalationSourceIdentity.trim() || !/^[0-9a-f]{64}$/.test(escalationSourceFingerprint) || escalationMutation === 'loading'} onClick={() => void createEscalation()}>建立人工升級</button></div></div><div className="line-row-actions"><label htmlFor="escalation-id">升級 ID</label><input id="escalation-id" inputMode="numeric" value={escalationIdInput} onChange={(event) => setEscalationIdInput(event.target.value)} /><button type="button" disabled={!/^\d+$/.test(escalationIdInput)} onClick={() => void loadEscalation()}>查詢升級明細</button></div><LoadingOrError state={escalationDetail} loadingText="正在載入人工升級明細…" />{escalationDetail.value && <><div className="line-detail-grid"><div><span>工單</span><strong>{escalationDetail.value.ticketRef}</strong></div><div><span>狀態</span><strong>{escalationDetail.value.workflowStatusLabel}</strong></div><div><span>分類</span><strong>{escalationDetail.value.categoryLabel}</strong></div><div><span>自動化</span><strong>{escalationDetail.value.automationHoldLabel}</strong></div><div><span>警示</span><strong>{escalationDetail.value.alertStatus}</strong></div><div><span>版本</span><strong>{escalationDetail.value.workflowVersion}</strong></div></div><label htmlFor="escalation-ticket-version">目前工單版本</label><input id="escalation-ticket-version" inputMode="numeric" value={escalationTicketVersion} onChange={(event) => setEscalationTicketVersion(event.target.value)} /><label htmlFor="escalation-resolution-digest">結案證據摘要（SHA-256）</label><input id="escalation-resolution-digest" value={escalationResolutionDigest} onChange={(event) => setEscalationResolutionDigest(event.target.value)} /><div className="line-row-actions">{escalationDetail.value.availableActions.includes('claim') && <button type="button" disabled={escalationMutation === 'loading'} onClick={() => void advanceEscalation('claim')}>接手</button>}{escalationDetail.value.availableActions.includes('handling') && <button type="button" disabled={escalationMutation === 'loading'} onClick={() => void advanceEscalation('handling')}>開始處理</button>}{escalationDetail.value.availableActions.includes('resolve') && <button type="button" disabled={escalationMutation === 'loading' || !/^[0-9a-f]{64}$/.test(escalationResolutionDigest)} onClick={() => void advanceEscalation('resolve')}>解決並解除暫停</button>}</div></>}{escalationReceipt && <div className="line-success" role="status">操作已提交：{escalationReceipt.operation}，狀態 {escalationReceipt.workflowStatus}</div>}{escalationError && <div className="line-error" role="alert">{escalationError}</div>}</section></div>}
      {activeTab === 'runtime' && <section className="line-workspace-card"><h3>人工升級來源分類</h3><div className="line-detail-grid"><label htmlFor="escalation-source-kind">來源類型<select id="escalation-source-kind" value={escalationSourceKind} onChange={(event) => setEscalationSourceKind(event.target.value as CustomerServiceEscalationCreateRequest['source_kind'])}><option value="ticket_referral">客服工單轉介</option><option value="line_inbox">LINE inbox</option><option value="binding_failure">綁定失敗</option><option value="runtime_health">Runtime 異常</option></select></label><label htmlFor="escalation-trigger">觸發原因<select id="escalation-trigger" value={escalationTrigger} onChange={(event) => setEscalationTrigger(event.target.value as CustomerServiceEscalationCreateRequest['trigger_code'])}><option value="explicit_human_request">明確要求人工</option><option value="explicit_wrong_answer">明確回覆錯誤</option><option value="binding_failure_threshold_2">綁定失敗達門檻</option><option value="complaint">客訴</option><option value="runtime_critical">Runtime 嚴重異常</option></select></label><label htmlFor="escalation-category">工單分類<select id="escalation-category" value={escalationCategory} onChange={(event) => setEscalationCategory(event.target.value as CustomerServiceEscalationCreateRequest['ticket_category'])}><option value="service_flow">服務流程</option><option value="payment_subsidy">收費與補助</option><option value="service_progress">服務進度</option><option value="profile_update">修改登記資料</option><option value="contact_union">聯絡工會</option><option value="other">其他問題</option></select></label><div><span>使用上述來源分類</span><button type="button" disabled={!escalationSourceIdentity.trim() || !/^[0-9a-f]{64}$/.test(escalationSourceFingerprint) || escalationMutation === 'loading'} onClick={() => void createEscalation()}>以所選來源建立人工升級</button></div></div></section>}

      <Drawer isOpen={ticketDetail.status !== 'idle'} onClose={closeTicket} title="客服工單明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeTicket}>關閉</button>{ticketDetail.status === 'error' && ticketDetailId.current !== null && <button type="button" onClick={() => openTicket(ticketDetailId.current!)}>重試查詢</button>}{ticketDetail.status === 'loaded' && ticketDetail.value?.ticket.status !== 'resolved' && customerService.previewResolve && <button type="button" data-control-id="line.ticket.resolve.preview" disabled={ticketResolvePreview.status === 'loading' || ticketResolveStatus === 'loading'} onClick={() => void previewTicketResolve()}>預覽結案</button>}{ticketResolvePreview.value?.applyReady && ticketResolvePreview.value.blockers.length === 0 && customerService.applyResolve && <button type="button" data-control-id="line.ticket.resolve.apply" disabled={!ticketResolveConfirmed || ticketResolveStatus === 'loading'} onClick={() => void applyTicketResolve()}>確認結案</button>}</div>}><div data-control-id="line.ticket.detail" className="line-drawer-content"><LoadingOrError state={ticketDetail} loadingText="正在載入工單明細…" />{ticketDetail.status === 'loaded' && ticketDetail.value && <><div className="line-detail-grid"><div><span>客戶</span><strong>{ticketDetail.value.ticket.maskedLineUserId}</strong></div><div><span>案件</span><strong>{ticketDetail.value.ticket.caseNo ?? '無關聯'}</strong></div><div><span>狀態</span><strong>{ticketDetail.value.ticket.statusLabel}</strong></div><div><span>版本</span><strong>{ticketDetail.value.ticket.version}</strong></div></div>{ticketDetail.value.ticket.status !== 'resolved' && customerService.previewResolve && <div className="line-action-panel"><label htmlFor="ticket-resolve-note">結案說明</label><textarea id="ticket-resolve-note" value={ticketResolveNote} onChange={(event) => { setTicketResolveNote(event.target.value); setTicketResolvePreview(idleState()); setTicketResolveConfirmed(false); setTicketResolveStatus('idle'); }} rows={3} maxLength={4000} />{ticketResolvePreview.status === 'loading' && <p>正在驗證結案內容…</p>}{ticketResolvePreview.status === 'error' && <div className="line-error" role="alert">{ticketResolvePreview.error}</div>}{ticketResolvePreview.value && <div className="line-preview-result"><strong>{ticketResolvePreview.value.beforeStatusLabel} → {ticketResolvePreview.value.afterStatusLabel}</strong>{ticketResolvePreview.value.blockers.length > 0 ? <ul>{ticketResolvePreview.value.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul> : <label><input type="checkbox" checked={ticketResolveConfirmed} onChange={(event) => setTicketResolveConfirmed(event.target.checked)} />我已確認結案內容與目前版本</label>}</div>}{ticketResolveStatus === 'success' && <div className="line-success" role="status">結案已完成</div>}{ticketResolveStatus === 'error' && <div className="line-error" role="alert">{ticketResolveError}</div>}</div>}<div className="line-events"><h4>事件紀錄</h4>{ticketDetail.value.events.length === 0 ? <p>尚無事件紀錄</p> : ticketDetail.value.events.map((event) => <article key={event.id}><strong>{event.eventType}</strong><span>{event.createdAt}</span><p>{event.messageText ?? '無訊息內容'}</p></article>)}</div></>}</div></Drawer>

      <Drawer isOpen={bindingDetail.status !== 'idle'} onClose={closeBinding} title="LINE 身分綁定明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeBinding}>關閉</button>{bindingDetail.status === 'error' && bindingDetailId.current !== null && <button type="button" onClick={() => openBinding(bindingDetailId.current!)}>重試查詢</button>}{bindingDetail.status === 'loaded' && bindingDetail.value?.status === 'bound' && lineIdentity.previewRevocation && <button type="button" data-control-id="line.identity.revocation.preview" disabled={bindingRevocationPreview.status === 'loading' || bindingRevocationStatus === 'loading'} onClick={() => void previewBindingRevocation()}>預覽解除</button>}{bindingRevocationPreview.value && !bindingRevocationPreview.value.hasBlockers && lineIdentity.applyRevocation && <button type="button" data-control-id="line.identity.revocation.apply" disabled={!bindingRevocationConfirmed || !bindingRevocationReason.trim() || bindingRevocationStatus === 'loading'} onClick={() => void applyBindingRevocation()}>提交解除</button>}</div>}><div data-control-id="line.identity.detail" className="line-drawer-content"><LoadingOrError state={bindingDetail} loadingText="正在載入身分綁定明細…" />{bindingDetail.status === 'loaded' && bindingDetail.value && <><div className="line-detail-grid"><div><span>LINE User ID</span><strong>{bindingDetail.value.maskedLineUserId}</strong></div><div><span>實名姓名</span><strong>{bindingDetail.value.subjectName}</strong></div><div><span>角色</span><strong>{bindingDetail.value.subjectTypeLabel}</strong></div><div><span>狀態／版本</span><strong>{bindingDetail.value.statusLabel}／{bindingDetail.value.version}</strong></div><div><span>更新時間</span><strong>{bindingDetail.value.updatedAt ?? '—'}</strong></div><div><span>解除狀態</span><strong>{bindingDetail.value.revocationStatusLabel}</strong></div></div>{bindingDetail.value.status === 'bound' && lineIdentity.previewRevocation && <div className="line-action-panel">{bindingRevocationPreview.status === 'loading' && <p>正在驗證解除條件…</p>}{bindingRevocationPreview.status === 'error' && <div className="line-error" role="alert">{bindingRevocationPreview.error}</div>}{bindingRevocationPreview.value && <>{bindingRevocationPreview.value.hasBlockers ? <ul>{bindingRevocationPreview.value.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul> : <><strong>可提交解除</strong><label htmlFor="binding-revocation-reason">解除原因</label><textarea id="binding-revocation-reason" value={bindingRevocationReason} onChange={(event) => { setBindingRevocationReason(event.target.value); setBindingRevocationConfirmed(false); setBindingRevocationStatus('idle'); }} rows={3} maxLength={1000} /><label><input type="checkbox" checked={bindingRevocationConfirmed} onChange={(event) => setBindingRevocationConfirmed(event.target.checked)} />我已確認解除對象與目前版本</label></>}</>}{bindingRevocationStatus === 'loading' && <p>正在提交解除申請…</p>}{bindingRevocationStatus === 'error' && <div className="line-error" role="alert">{bindingRevocationError}</div>}{bindingRevocationAccepted && <div className="line-success" role="status"><strong>解除申請已受理</strong><p>{bindingRevocationAccepted.notice}</p></div>}</div>}</>}</div></Drawer>

      <Drawer isOpen={deliveryDetail.status !== 'idle'} onClose={closeDeliveryTask} title="LINE 發送任務明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeDeliveryTask}>關閉</button></div>}><div className="line-drawer-content"><LoadingOrError state={deliveryDetail} loadingText="正在載入發送任務明細…" />{deliveryDetail.value && <><div className="line-detail-grid"><div><span>任務 ID</span><strong>{deliveryDetail.value.task.taskId}</strong></div><div><span>狀態</span><strong>{deliveryDetail.value.task.statusLabel}</strong></div><div><span>來源</span><strong>{deliveryDetail.value.task.sourceType}</strong></div><div><span>任務類型</span><strong>{deliveryDetail.value.task.taskType}</strong></div><div><span>排程時間</span><strong>{deliveryDetail.value.task.scheduledAt}</strong></div><div><span>嘗試次數</span><strong>{deliveryDetail.value.task.attempts}</strong></div></div><div className="line-events"><h4>嘗試紀錄</h4>{deliveryDetail.value.attempts.length === 0 ? <p>尚無嘗試紀錄</p> : deliveryDetail.value.attempts.map((attempt) => <article key={attempt.number}><strong>第 {attempt.number} 次：{attempt.outcome}</strong><span>{attempt.startedAt}</span><p>完成：{attempt.completedAt ?? '進行中'}；重試等待：{attempt.retryAfterSeconds ?? '—'} 秒</p></article>)}</div></>}</div></Drawer>

      <Drawer isOpen={orderGroupDetail.status !== 'idle'} onClose={closeOrderGroup} title="三方服務群組明細" size="wide" footer={<div className="line-drawer-footer"><button type="button" onClick={closeOrderGroup}>關閉</button></div>}><div className="line-drawer-content"><LoadingOrError state={orderGroupDetail} loadingText="正在載入三方服務群組明細…" />{orderGroupDetail.value && <><div className="line-detail-grid"><div><span>案件</span><strong>{orderGroupDetail.value.record.caseNo}</strong></div><div><span>群組識別</span><strong>{orderGroupDetail.value.record.groupIdentity}</strong></div><div><span>狀態</span><strong>{orderGroupDetail.value.record.statusLabel}</strong></div><div><span>版本</span><strong>{orderGroupDetail.value.record.version}</strong></div></div><div className="line-events"><h4>事件紀錄</h4>{orderGroupDetail.value.events.length === 0 ? <p>尚無事件紀錄</p> : orderGroupDetail.value.events.map((event) => <article key={event.eventId}><strong>{event.eventType}</strong><span>{event.occurredAt}</span><p>操作者：{event.actorIdentity}；邀請指紋：{event.invitationFingerprint}</p></article>)}</div></>}</div></Drawer>

      <Drawer isOpen={selectedRule !== null} onClose={() => setSelectedRule(null)} title={`通知規則${selectedRule ? `－${selectedRule.id}` : ''}`} footer={<div className="line-drawer-footer"><button type="button" onClick={() => setSelectedRule(null)}>關閉</button></div>}>{selectedRule && <div className="line-drawer-content" data-control-id="line.notification-rule.detail"><div className="line-detail-grid"><div><span>事件</span><strong>{selectedRule.eventLabel}</strong></div><div><span>收件人</span><strong>{selectedRule.recipientLabel}</strong></div><div><span>模板</span><strong>{selectedRule.templateId}</strong></div><div><span>狀態</span><strong>{selectedRule.enabled ? '已啟用' : '未啟用'}</strong></div></div><p>{selectedRule.scheduleLabel}｜{selectedRule.frequencyLabel}</p>{selectedRule.predicateLabels.length > 0 && <p>條件：{selectedRule.predicateLabels.join('、')}</p>}</div>}</Drawer>

      <Drawer isOpen={selectedPublication.status !== 'idle'} onClose={closePublication} title="Rich Menu 發布紀錄" footer={<div className="line-drawer-footer"><button type="button" onClick={closePublication}>關閉</button>{selectedPublication.status === 'error' && publicationDetailId.current !== null && <button type="button" onClick={() => openPublication(publicationDetailId.current!)}>重試查詢</button>}</div>}><div className="line-drawer-content"><LoadingOrError state={selectedPublication} loadingText="正在載入發布紀錄明細…" />{selectedPublication.status === 'loaded' && selectedPublication.value && <div className="line-detail-grid"><div><span>選單定義</span><strong>{selectedPublication.value.menuDefinitionId}</strong></div><div><span>設定版本</span><strong>{selectedPublication.value.configurationRevision}</strong></div><div><span>伺服器狀態</span><strong>{selectedPublication.value.statusLabel}</strong></div><div><span>紀錄 ID</span><strong>{selectedPublication.value.id}</strong></div></div>}</div></Drawer>
    </div>
  );
};

export default LineManagementPage;
