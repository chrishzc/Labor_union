/**
 * File: LineManagementPage.tsx
 * Description: 整合 LINE typed Query／Preview／Apply 工作區，所有外送副作用仍由後端 durable task 執行。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  Baby,
  Bot,
  CalendarDays,
  ClipboardCheck,
  Eraser,
  FilePenLine,
  FileText,
  GitCompareArrows,
  Headphones,
  Info,
  MapPin,
  Menu,
  PackageSearch,
  RefreshCw,
  Settings,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Star,
  TriangleAlert,
  Users,
  WalletCards,
} from 'lucide-react';

import {
  adaptLineRichMenuPublication,
  adaptLineRichMenuPublicationPage,
  type LineRichMenuConfigurationModel,
  type LineRichMenuPublicationModel,
  type LineRichMenuPublicationPageModel,
  type RichMenuButtonModel,
} from '../adapters/line_configuration/line_configuration_query_adapter';
import {
  customerServiceClient,
  type CustomerServiceClient,
  type CustomerServiceReminderClient,
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
import { adaptLineRichMenuDraft } from '../adapters/line_rich_menu_draft/line_rich_menu_draft_adapter';
import {
  lineRichMenuDraftClient,
  type LineRichMenuDraftClient,
} from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import { LineDeliveryQueryError } from '../api/line_delivery/line_delivery_query_errors';
import { LineOrderGroupWorkbench } from '../components/LineOrderGroupWorkbench';
import type { LineOrderGroupStatus } from '../api/line_order_groups/line_order_group_query_schemas';
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
import { LineCustomerServiceReminderWorkbench } from '../components/LineCustomerServiceReminderWorkbench';
import { LineIdentityWorkbench } from '../components/LineIdentityWorkbench';
import { LineNotificationWorkbench } from '../components/LineNotificationWorkbench';
import type { LineNotificationTemplateClient } from '../api/line_notification_rules/line_notification_template_client';
import type { LineOnboardingClient } from '../api/line_onboarding/line_onboarding_client';
import { LineRichMenuPublicationActions } from '../components/LineRichMenuPublicationActions';
import {
  lineRichMenuPublicationClient,
  type LineRichMenuPublicationClient,
} from '../api/line_rich_menu_publication/line_rich_menu_publication_client';
import { LineRichMenuDraftActionEditor } from '../components/LineRichMenuDraftActionEditor';
import { LineRichMenuDraftAppearanceEditor } from '../components/LineRichMenuDraftAppearanceEditor';
import { SafeReviewLinkWorkbench } from '../components/SafeReviewLinkWorkbench';
import { safeReviewLinkClient, type SafeReviewLinkClient } from '../api/line_safe_review_link/line_safe_review_link_client';
import type {
  RichMenuDraft,
  RichMenuDraftDefinition,
} from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';
import './LineManagementPage.css';

type LineTab = 'tickets' | 'richmenu' | 'binding' | 'push_queue' | 'order_groups' | 'runtime';
type RichMenuWorkspaceTab = 'overview' | 'appearance' | 'actions' | 'publish' | 'history';

function currentHashParams(): URLSearchParams {
  return new URLSearchParams(window.location.hash.split('?', 2)[1] ?? '');
}

function hashChoice<T extends string>(params: URLSearchParams, key: string, allowed: readonly T[], fallback: T): T {
  const value = params.get(key) as T | null;
  return value !== null && allowed.includes(value) ? value : fallback;
}

function hashPage(params: URLSearchParams, key: string): number {
  const value = Number.parseInt(params.get(key) ?? '', 10);
  return Number.isSafeInteger(value) && value > 0 ? value : 1;
}

type CustomerServicePageClient = Partial<CustomerServiceClient & CustomerServiceReminderClient>;
type LineIdentityPageClient = Partial<LineIdentityClient>;

interface LineManagementPageProps {
  customerService?: CustomerServicePageClient;
  lineIdentity?: LineIdentityPageClient;
  lineConfiguration?: LineConfigurationQueryClient;
  richMenuDraft?: LineRichMenuDraftClient;
  richMenuPublication?: LineRichMenuPublicationClient;
  richMenuPublicationPollIntervalMs?: number;
  runtimeTarget?: typeof lineRuntimeTargetClient;
  escalation?: typeof customerServiceEscalationClient;
  delivery?: typeof lineDeliveryQueryClient;
  safeReviewLink?: SafeReviewLinkClient;
  onboardingClient?: LineOnboardingClient;
  notificationTemplateClient?: LineNotificationTemplateClient;
  /** Render only the safety and human-escalation workspace inside the canonical Group & Security page. */
  runtimeOnly?: boolean;
}

type QueryStatus = 'idle' | 'loading' | 'loaded' | 'error';
type MutationStatus = 'idle' | 'loading' | 'success' | 'error';
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
  if (error instanceof LineSafeConfigError) return `${error.code}：${error.message}`;
  if (error instanceof LineRuntimeTargetError) return `${error.code}：${error.message}`;
  if (error instanceof CustomerServiceEscalationError) {
    if (error.code.includes('NOT_FOUND')) return '找不到可升級的正式來源事件；請先由客服工單、LINE inbox、綁定失敗或 runtime 異常建立來源。';
    return `${error.code}：${error.message}`;
  }
  return fallback;
}

const TABS: ReadonlyArray<readonly [LineTab, string, string]> = [
  ['tickets', '客服案件', 'line.tab.tickets'],
  ['richmenu', '圖文選單', 'line.tab.richmenu'],
  ['binding', '身分與授權', 'line.tab.binding'],
  ['push_queue', '通知與發送', 'line.tab.push-queue'],
  ['order_groups', '三方服務群組', 'line.tab.order-groups'],
];

const SAFE_CONFIGURATION_KINDS: readonly LineSafeConfigKind[] = [
  'message_templates', 'message_schedules', 'rich_menus', 'liff',
  'customer_service', 'notification_rules',
];

function LineErrorMessage({ error }: { error?: string | null }) {
  const errorText = error ?? '資料讀取失敗，請重新整理後再試。';
  const technicalMatch = errorText.match(/^([a-z][a-z0-9_]+)\s*[:：]\s*(.+)$/i);
  return (
    <div className="line-error" role="alert">
      <span>{technicalMatch?.[2] ?? errorText}</span>
      {technicalMatch && (
        <details className="line-error-technical">
          <summary>技術資訊</summary>
          <code>{technicalMatch[1]}</code>
        </details>
      )}
    </div>
  );
}

function LoadingOrError({ state, loadingText }: { state: QueryState<unknown>; loadingText: string }) {
  if (state.status === 'loading') return <div className="line-loading">{loadingText}</div>;
  if (state.status === 'error') return <LineErrorMessage error={state.error} />;
  return null;
}


function getTypedButtonAction(btn: RichMenuButtonModel) {
  const action = btn.action;
  if (!action) return { type: 'UNAVAILABLE', uri: null, text: null, data: null, alias: null } as const;
  if (action.kind === 'uri') return { type: 'URI', uri: action.uri, text: null, data: null, alias: null } as const;
  if (action.kind === 'message') return { type: 'MESSAGE', uri: null, text: action.text, data: null, alias: null } as const;
  if (action.kind === 'postback') return { type: 'POSTBACK', uri: null, text: null, data: action.data, alias: null } as const;
  return { type: 'RICHMENU_SWITCH', uri: null, text: null, data: action.data, alias: action.richMenuAliasId } as const;
}

const CANONICAL_RICH_MENU_ROUTES: Readonly<Record<string, string>> = {
  'entry:gateway': '/line-gateway',
  'entry:registration': '/line-bind',
  'target:gateway': '/line-gateway',
  'target:profile_update': '/line-profile-guard',
  'target:staff_order_search': '/line-staff-orders',
  'target:staff_schedule': '/line-staff-schedule',
  'target:staff_leave_apply': '/line-staff-schedule',
  'target:staff_baby_log': '/line-staff-baby-log',
  'target:staff_verification': '/line-identity?target=staff_verification',
  'target:staff_payout': '/line-staff-payout',
  'target:order_update': '/line-order-update',
  'target:customer_service': '/line-mobile-admin?target=customer_service',
  'target:scheduling_review': '/line-mobile-admin?target=scheduling_review',
  'target:staff_review': '/line-mobile-admin?target=staff_review',
  'target:order_tracking': '/line-mobile-admin?target=order_tracking',
  'target:anomalies_center': '/line-mobile-admin?target=anomalies_center',
  'target:dashboard': '/line-mobile-admin?target=dashboard',
  'target:faq': '/line-service-help?tab=faq',
  'target:ai_assistant': '/line-service-help?tab=ai',
};

export function resolveRichMenuUri(uri: string | null): string | null {
  if (!uri) return null;
  try {
    const parsed = new URL(uri, 'https://line.invalid/line-identity');
    const entry = parsed.searchParams.get('entry');
    const target = parsed.searchParams.get('target');
    if (entry && CANONICAL_RICH_MENU_ROUTES[`entry:${entry}`]) return CANONICAL_RICH_MENU_ROUTES[`entry:${entry}`];
    if (target && CANONICAL_RICH_MENU_ROUTES[`target:${target}`]) return CANONICAL_RICH_MENU_ROUTES[`target:${target}`];
    return parsed.origin === 'https://line.invalid' ? `${parsed.pathname}${parsed.search}${parsed.hash}` : parsed.toString();
  } catch {
    return uri;
  }
}

function mergeRichMenuAppearance(
  base: RichMenuDraftDefinition,
  source: RichMenuDraftDefinition,
): RichMenuDraftDefinition {
  return {
    ...base,
    menus: base.menus.map((menu) => {
      const sourceMenu = source.menus.find((candidate) => candidate.id === menu.id);
      if (!sourceMenu) return menu;
      return {
        ...menu,
        name: sourceMenu.name,
        chat_bar_text: sourceMenu.chat_bar_text,
        appearance: sourceMenu.appearance,
        buttons: menu.buttons.map((button) => {
          const sourceButton = sourceMenu.buttons.find((candidate) => candidate.id === button.id);
          return sourceButton ? { ...button, label: sourceButton.label } : button;
        }),
      };
    }),
  };
}

function mergeRichMenuActions(
  base: RichMenuDraftDefinition,
  source: RichMenuDraftDefinition,
): RichMenuDraftDefinition {
  return {
    ...base,
    menus: base.menus.map((menu) => {
      const sourceMenu = source.menus.find((candidate) => candidate.id === menu.id);
      if (!sourceMenu) return menu;
      return {
        ...menu,
        buttons: menu.buttons.map((button) => {
          const sourceButton = sourceMenu.buttons.find((candidate) => candidate.id === button.id);
          return sourceButton ? { ...button, action: sourceButton.action } : button;
        }),
      };
    }),
  };
}

export const LineManagementPage: React.FC<LineManagementPageProps> = ({
  customerService = customerServiceClient,
  lineIdentity = lineIdentityClient,
  lineConfiguration = lineConfigurationQueryClient,
  richMenuDraft = lineRichMenuDraftClient,
  richMenuPublication = lineRichMenuPublicationClient,
  richMenuPublicationPollIntervalMs = 1500,
  runtimeTarget = lineRuntimeTargetClient,
  escalation = customerServiceEscalationClient,
  safeReviewLink = safeReviewLinkClient,
  onboardingClient,
  notificationTemplateClient,
  runtimeOnly = false,
}) => {
  const initialHashParams = useRef(currentHashParams()).current;
  const [activeTab, setActiveTab] = useState<LineTab>(runtimeOnly ? 'runtime' : hashChoice<LineTab>(initialHashParams, 'tab', ['tickets', 'richmenu', 'binding', 'push_queue', 'order_groups'], 'tickets'));
  const [richMenuWorkspaceTab, setRichMenuWorkspaceTab] = useState<RichMenuWorkspaceTab>(hashChoice<RichMenuWorkspaceTab>(initialHashParams, 'rich', ['overview', 'appearance', 'actions', 'publish', 'history'], 'overview'));
  const [notificationRuleSearch, setNotificationRuleSearch] = useState(initialHashParams.get('rule_q') ?? '');
  const [notificationRuleEnabled, setNotificationRuleEnabled] = useState<'all' | 'enabled' | 'disabled'>(hashChoice<'all' | 'enabled' | 'disabled'>(initialHashParams, 'rule_state', ['all', 'enabled', 'disabled'], 'all'));

  const [orderGroupPageNumber, setOrderGroupPageNumber] = useState(hashPage(initialHashParams, 'group_page'));
  const [orderGroupSearch, setOrderGroupSearch] = useState((initialHashParams.get('group_q') ?? '').slice(0, 50));
  const [orderGroupStatus, setOrderGroupStatus] = useState<LineOrderGroupStatus | 'all'>(hashChoice<LineOrderGroupStatus | 'all'>(initialHashParams, 'group_state', ['all', 'unbound', 'bound', 'inviting', 'active', 'attention', 'replaced', 'released'], 'all'));

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
  const [richMenuDraftSnapshot, setRichMenuDraftSnapshot] = useState<RichMenuDraft | null>(null);
  const [richMenuLocalDefinition, setRichMenuLocalDefinition] = useState<RichMenuDraftDefinition | null>(null);
  const [richMenuPublications, setRichMenuPublications] = useState<QueryState<LineRichMenuPublicationPageModel>>(idleState);
  const [richMenuPublicationPageNumber, setRichMenuPublicationPageNumber] = useState(hashPage(initialHashParams, 'rich_page'));
  const richMenuPublicationPageSize = 25;
  const [richMenuReload, setRichMenuReload] = useState(0);
  const richMenuListGeneration = useRef(0);
  const [selectedMenuId, setSelectedMenuId] = useState<string | null>(null);
  const [selectedPublication, setSelectedPublication] = useState<QueryState<LineRichMenuPublicationModel>>(idleState);
  const publicationController = useRef<AbortController | null>(null);
  const publicationGeneration = useRef(0);
  const publicationDetailId = useRef<number | null>(null);
  const [trackedRichMenuPublication, setTrackedRichMenuPublication] = useState<{
    id: number;
    menuDefinitionId: string;
    configurationRevision: number;
    status: LineRichMenuPublicationModel['status'];
    attempts: number;
    timedOut: boolean;
  } | null>(null);

  // 圖文選單 本機互動沙盒與比對狀態
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
    if (runtimeOnly) return;
    const route = window.location.hash.replace(/^#\/?/, '').split('?', 1)[0];
    if (route !== 'line-management' && route !== 'line') return;
    const params = currentHashParams();
    const setParam = (key: string, value: string | number, fallback: string | number) => {
      if (value === fallback || value === '') params.delete(key);
      else params.set(key, String(value));
    };
    setParam('tab', activeTab, 'tickets');
    setParam('rich', richMenuWorkspaceTab, 'overview');
    setParam('rule_q', notificationRuleSearch, '');
    setParam('rule_state', notificationRuleEnabled, 'all');
    if (activeTab === 'push_queue') ['notice', 'rule_event', 'rule_recipient', 'rule_page'].forEach(key => params.delete(key));
    setParam('rich_page', richMenuPublicationPageNumber, 1);
    setParam('group_page', orderGroupPageNumber, 1);
    setParam('group_q', orderGroupSearch, '');
    setParam('group_state', orderGroupStatus, 'all');
    const query = params.toString();
    const nextHash = `#${route}${query ? `?${query}` : ''}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}${nextHash}`);
    }
  }, [
    activeTab,
    notificationRuleEnabled,
    notificationRuleSearch,
    orderGroupPageNumber,
    orderGroupSearch,
    orderGroupStatus,
    richMenuPublicationPageNumber,
    richMenuWorkspaceTab,
    runtimeOnly,
  ]);



  useEffect(() => {
    if (activeTab !== 'richmenu') return;
    const controller = new AbortController();
    const generation = ++richMenuListGeneration.current;
    let cancelled = false;
    setRichMenuLocalDefinition(null);
    setRichMenuConfiguration(loadingState());
    setRichMenuPublications(loadingState());
    const timer = window.setTimeout(() => {
      void Promise.allSettled([
        richMenuDraft.query({ signal: controller.signal }),
        lineConfiguration.listRichMenuPublications({
          page: richMenuPublicationPageNumber,
          pageSize: richMenuPublicationPageSize,
          signal: controller.signal,
        }),
      ]).then(([configurationResult, publicationResult]) => {
        if (cancelled || generation !== richMenuListGeneration.current) return;
        if (configurationResult.status === 'fulfilled') {
          const nextConfiguration = adaptLineRichMenuDraft(configurationResult.value);
          setRichMenuDraftSnapshot(configurationResult.value);
          setRichMenuConfiguration(loadedState(nextConfiguration));
          setSelectedMenuId((current) => current ?? nextConfiguration.menus[0]?.id ?? null);
        } else setRichMenuConfiguration(errorState(displayQueryError(configurationResult.reason, '圖文選單 設定載入失敗')));
        if (publicationResult.status === 'fulfilled') setRichMenuPublications(loadedState(adaptLineRichMenuPublicationPage(publicationResult.value)));
        else setRichMenuPublications(errorState(displayQueryError(publicationResult.reason, '圖文選單 發布紀錄載入失敗')));
      });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, lineConfiguration, richMenuDraft, richMenuPublicationPageNumber, richMenuReload]);

  useEffect(() => {
    const tracked = trackedRichMenuPublication;
    if (
      activeTab !== 'richmenu'
      || !tracked
      || tracked.timedOut
      || !['queued', 'publishing'].includes(tracked.status)
    ) return;
    if (tracked.attempts >= 80) {
      setTrackedRichMenuPublication((current) => current?.id === tracked.id
        ? { ...current, timedOut: true }
        : current);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void lineConfiguration.getRichMenuPublication(tracked.id, { signal: controller.signal })
        .then((publication) => {
          if (controller.signal.aborted) return;
          const current = adaptLineRichMenuPublication(publication);
          setTrackedRichMenuPublication((existing) => existing?.id === tracked.id
            ? {
                ...existing,
                status: current.status,
                attempts: existing.attempts + 1,
              }
            : existing);
          if (!['queued', 'publishing'].includes(current.status)) {
            setRichMenuPublicationPageNumber(1);
            setRichMenuReload((value) => value + 1);
          }
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setTrackedRichMenuPublication((existing) => existing?.id === tracked.id
            ? { ...existing, attempts: existing.attempts + 1 }
            : existing);
        });
    }, richMenuPublicationPollIntervalMs);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [
    activeTab,
    lineConfiguration,
    richMenuPublicationPollIntervalMs,
    trackedRichMenuPublication,
  ]);



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

    if (activeTab !== 'richmenu') {
      publicationController.current?.abort();
      publicationController.current = null;
      publicationGeneration.current += 1;
      publicationDetailId.current = null;
      setSelectedPublication(idleState());
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
    publicationController.current?.abort();
    runtimePreviewController.current?.abort();
    escalationPreviewController.current?.abort();
    publicationGeneration.current += 1;
    runtimePreviewGeneration.current += 1;
    escalationPreviewGeneration.current += 1;
  }, []);

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
        context: { summary_code: escalationTrigger, policy_version: 'ui-react-v1', category: escalationCategory, redaction_version: 'v1' },
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
      .catch((error: unknown) => { if (!controller.signal.aborted && generation === publicationGeneration.current) setSelectedPublication(errorState(displayQueryError(error, '圖文選單 發布明細載入失敗'))); });
  };

  const closePublication = () => {
    publicationController.current?.abort();
    publicationController.current = null;
    publicationGeneration.current += 1;
    publicationDetailId.current = null;
    setSelectedPublication(idleState());
  };

  const localRichMenuConfiguration = richMenuDraftSnapshot && richMenuLocalDefinition
    ? adaptLineRichMenuDraft({ ...richMenuDraftSnapshot, definition: richMenuLocalDefinition })
    : richMenuConfiguration.value;
  const selectedMenu = localRichMenuConfiguration?.menus.find((menu) => menu.id === selectedMenuId) ?? null;
  const updateLocalRichMenuAppearance = (candidate: RichMenuDraftDefinition | null) => {
    if (!richMenuDraftSnapshot) return;
    setRichMenuLocalDefinition((current) => mergeRichMenuAppearance(
      current ?? richMenuDraftSnapshot.definition,
      candidate ?? richMenuDraftSnapshot.definition,
    ));
  };
  const updateLocalRichMenuActions = (candidate: RichMenuDraftDefinition | null) => {
    if (!richMenuDraftSnapshot) return;
    setRichMenuLocalDefinition((current) => mergeRichMenuActions(
      current ?? richMenuDraftSnapshot.definition,
      candidate ?? richMenuDraftSnapshot.definition,
    ));
  };

  return (
    <div className={`line-page-wrapper${runtimeOnly ? ' line-runtime-embedded' : ''}`} data-control-id="line.page">
      {!runtimeOnly && <header className="page-header-banner line-page-header">
        <div>
          <p className="line-hub-eyebrow">LINE 專區</p>
          <h1 className="page-title">客服與營運工作台</h1>
          <p className="page-subtitle">處理客服案件、圖文選單、身分、通知與服務群組。</p>
        </div>

      </header>}
      {!runtimeOnly && <nav className="line-tab-bar" aria-label="客服與營運功能">
        {(['日常作業', '選單設定'] as const).map((group) => <div key={group} className="line-nav-group" role="group" aria-label={group}>
          <span className="line-nav-group-label">{group}</span>
          {TABS.filter(([tab]) => group === '選單設定' ? tab === 'richmenu' : tab !== 'richmenu').map(([tab, label, id]) => <button key={tab} type="button" data-control-id={id} className={`line-tab-btn ${activeTab === tab ? 'active' : ''}`} aria-current={activeTab === tab ? 'page' : undefined} onClick={() => setActiveTab(tab)}>{label}</button>)}
        </div>)}
      </nav>}

      {activeTab === 'tickets' && <LineCustomerServiceReminderWorkbench client={customerService} />}

      {activeTab === 'richmenu' && (() => {
        const menus = localRichMenuConfiguration?.menus ?? [];
        const activeMenu = selectedMenu ?? menus[0] ?? null;
        const localDefinition = richMenuLocalDefinition ?? richMenuDraftSnapshot?.definition;
        const activeMenuDefinition = localDefinition?.menus.find((menu) => menu.id === activeMenu?.id);
        const activePublicationLock = activeMenu && richMenuDraftSnapshot
          ? richMenuDraftSnapshot.publication_locks.find(
            (lock) => lock.menu_definition_id === activeMenu.id
              && lock.configuration_revision === richMenuDraftSnapshot.revision,
          )
          : undefined;
        const activePublicationTracking = activeMenu && richMenuDraftSnapshot
          && trackedRichMenuPublication?.menuDefinitionId === activeMenu.id
          && trackedRichMenuPublication.configurationRevision === richMenuDraftSnapshot.revision
          ? trackedRichMenuPublication
          : null;

        return (
          <section className="line-table-container" data-control-id="line.richmenu.configuration">
            <div className="line-section-heading">
              <div>
                <h2>各角色的圖文選單</h2>
            <p>可編輯草稿的背景、名稱與按鈕動作；草稿保存不會發布，正式發布另須檢查影響並由人員確認。</p>
              </div>
              <button
                type="button"
                className="line-secondary-btn"
                data-control-id="line.richmenu.refresh"
                onClick={() => setRichMenuReload((value) => value + 1)}
              >
                <RefreshCw aria-hidden="true" />重新整理
              </button>
            </div>

            <nav className="line-hub-section-tabs richmenu-workspace-tabs" aria-label="圖文選單 工作區">
              {([
                ['overview', '選單概覽'],
                ['appearance', '外觀編輯'],
                ['actions', '按鈕動作'],
                ['publish', '發布'],
                ['history', '發布歷程'],
              ] as const).map(([tab, label]) => (
                <button
                  key={tab}
                  type="button"
                  className={richMenuWorkspaceTab === tab ? 'active' : ''}
                  aria-current={richMenuWorkspaceTab === tab ? 'page' : undefined}
                  onClick={() => setRichMenuWorkspaceTab(tab)}
                >
                  {label}
                </button>
              ))}
            </nav>

            <LoadingOrError state={richMenuConfiguration} loadingText="正在載入 圖文選單 設定…" />
            {richMenuConfiguration.status === 'loaded' && richMenuConfiguration.value?.isEmpty && (
              <div className="line-empty-state">
                <h4>目前沒有已核准的 圖文選單 設定</h4>
                <p>畫面不會以範例選單或未核准 LIFF 路由補齊。</p>
              </div>
            )}

            {/* 工具與模式切換列 */}
            <div className="richmenu-toolbar">
              {/* 角色選單切換列 */}
              <div className="richmenu-role-tabs richmenu-role-tabs-toolbar">
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
              <div className="richmenu-toolbar-actions">
                <button
                  type="button"
                  className={`line-secondary-btn richmenu-diff-toggle ${isDiffMode ? 'active' : ''}`}
                  onClick={() => setIsDiffMode(!isDiffMode)}
                >
                  <GitCompareArrows aria-hidden="true" />
                  {isDiffMode ? '關閉版本比對' : '開啟版本變更比對'}
                </button>
                {simChatMessages.length > 0 && (
                  <button
                    type="button"
                  className="line-secondary-btn richmenu-compact-action"
                    onClick={() => setSimChatMessages([])}
                  >
                    <Eraser aria-hidden="true" />
                    清除模擬對話
                  </button>
                )}
              </div>
            </div>

            {/* 本機幾何初檢；正式路由與發布資格只由 server Preview 裁決。 */}
            {activeMenu && (richMenuWorkspaceTab === 'overview' || richMenuWorkspaceTab === 'publish') && (() => {
              const targetW = activeMenu.width;
              const targetH = activeMenu.height;
              let totalArea = 0;
              let hasOverlap = false;
              let hasInvalidDimensions = false;
              let hasOutOfBounds = false;
              const buttons = activeMenu.buttons;

              for (let i = 0; i < buttons.length; i++) {
                const b1 = buttons[i].bounds;
                totalArea += b1.width * b1.height;
                hasInvalidDimensions ||= b1.width <= 0 || b1.height <= 0;
                hasOutOfBounds ||=
                  b1.x < 0 ||
                  b1.y < 0 ||
                  b1.x + b1.width > targetW ||
                  b1.y + b1.height > targetH;
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
              const localGeometryPassed =
                !hasInvalidDimensions && !hasOutOfBounds && isFullCoverage && !hasOverlap;
              const geometryIssues = [
                hasInvalidDimensions ? '熱區尺寸必須為正值' : null,
                hasOutOfBounds ? '熱區超出畫布範圍' : null,
                !isFullCoverage ? '熱區未完整覆蓋版面' : null,
                hasOverlap ? '熱區存在重疊' : null,
              ].filter((issue): issue is string => issue !== null);

              return (
                <div
                  className={`richmenu-safety-banner ${localGeometryPassed ? 'is-safe' : 'has-warning'}`}
                >
                  <div className="richmenu-safety-copy">
                    <span className="richmenu-safety-icon">{localGeometryPassed ? <ShieldCheck aria-hidden="true" /> : <TriangleAlert aria-hidden="true" />}</span>
                    <div>
                      <strong>本機幾何初檢：</strong>
                      <span className="richmenu-safety-description">
                        {localGeometryPassed
                          ? `熱區位於 ${targetW}×${targetH} 畫布內、無重疊並完整覆蓋。`
                          : `需修正：${geometryIssues.join('、')}。`}
                        {' '}正式路由與發布資格仍須由系統檢查。
                      </span>
                    </div>
                  </div>
                  <span className="richmenu-safety-status">
                    {localGeometryPassed ? '本機初檢通過' : '需修正幾何'}
                  </span>
                </div>
              );
            })()}

            {/* 左右分割工作台 */}
            {activeMenu && richMenuWorkspaceTab !== 'history' && (
            <div className={`richmenu-studio-grid richmenu-studio-grid-${richMenuWorkspaceTab}`}>
              {/* 左側：3D 手機即時模擬器 */}
              {richMenuWorkspaceTab !== 'publish' && <div className="richmenu-phone-card">
                <div className="richmenu-phone-card-header">
                  <span className="richmenu-phone-heading">
                    手機擬真互動沙盒（點擊下方按鈕測試）
                  </span>
                  {activeSimLiff && (
                    <span className="richmenu-preview-badge">
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
                    <span>5G · 100%</span>
                  </div>
                  {/* Header */}
                  <div className="richmenu-phone-topbar">
                    <span className="richmenu-phone-nav-label">‹ 聊天</span>
                    <strong className="richmenu-phone-brand">新竹市月子工會 (LINE)</strong>
                    <span className="richmenu-phone-menu-icon"><Menu aria-hidden="true" /></span>
                  </div>

                  {/* LIFF 彈窗預覽層 (In-situ LIFF Modal) */}
                  {activeSimLiff ? (
                    <div className="phone-liff-modal">
                      <div className="phone-liff-header">
                        <div>
                          <span className="phone-liff-badge">{activeSimLiff.badge}</span>
                          <h4 className="phone-liff-title">
                            {activeSimLiff.title}
                          </h4>
                          <small className="phone-liff-subtitle">{activeSimLiff.subtitle}</small>
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
                        <div className="richmenu-bot-avatar"><Bot aria-hidden="true" /></div>
                        <div className="richmenu-bubble-content">
                          <strong>工會小幫手</strong>
                          <p>您好！已載入「{activeMenu.audienceRoleLabel}」專屬選單。請點擊下方 {activeMenu.buttons.length} 個按鈕測試互動反應！</p>
                        </div>
                      </div>

                      {simChatMessages.map((msg) => (
                        <div
                          key={msg.id}
                          className={`richmenu-chat-bubble ${msg.sender === 'user' ? 'user-bubble' : ''}`}
                        >
                          {msg.sender === 'bot' && <div className="richmenu-bot-avatar"><Bot aria-hidden="true" /></div>}
                          <div className={`richmenu-bubble-content ${msg.sender === 'user' ? 'user-message' : 'bot-message'}`}>
                            {msg.sender === 'bot' && <strong>工會小幫手</strong>}
                            <p className="richmenu-message-text">{msg.text}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Chat Bar Text */}
                  <div className="richmenu-chat-bar-hint">
                    {activeMenu.chatBarText} ▾
                  </div>

                  {/* 圖文選單 Button Grid (可點擊互動) */}
                  <div
                    className="richmenu-buttons-grid"
                    data-control-id="line.richmenu.local-preview"
                    style={{ backgroundColor: activeMenuDefinition?.appearance?.background_color }}
                  >
                    {activeMenu.buttons.map((btn) => {
                      const label = btn.label;
                      const act = getTypedButtonAction(btn);
                      let Icon = MapPin;
                      if (label.includes('登記')) Icon = FileText;
                      else if (label.includes('修改') || label.includes('異動')) Icon = FilePenLine;
                      else if (label.includes('說明') || label.includes('FAQ') || label.includes('常見問答') || label.includes('問答')) Icon = Info;
                      else if (label.includes('AI') || label.includes('智慧問答') || label.includes('助理')) Icon = Sparkles;
                      else if (label.includes('客服') || label.includes('諮詢')) Icon = Headphones;
                      else if (label.includes('訂單')) Icon = PackageSearch;
                      else if (label.includes('排班') || label.includes('日曆') || label.includes('請假')) Icon = CalendarDays;
                      else if (label.includes('薪資') || label.includes('請款')) Icon = WalletCards;
                      else if (label.includes('契約') || label.includes('合約')) Icon = FileText;
                      else if (label.includes('評價') || label.includes('滿意度')) Icon = Star;
                      else if (label.includes('審核')) Icon = ClipboardCheck;
                      else if (label.includes('一般用戶')) Icon = Users;
                      else if (label.includes('月嫂專區')) Icon = Baby;
                      else if (label.includes('工會管理')) Icon = ShieldCheck;

                      return (
                        <button
                          key={btn.id}
                          type="button"
                          className="richmenu-grid-btn"
                          style={{
                            position: 'absolute',
                            left: `${activeMenu.width > 0 ? (btn.bounds.x / activeMenu.width) * 100 : 0}%`,
                            top: `${activeMenu.height > 0 ? (btn.bounds.y / activeMenu.height) * 100 : 0}%`,
                            width: `${activeMenu.width > 0 ? (btn.bounds.width / activeMenu.width) * 100 : 0}%`,
                            height: `${activeMenu.height > 0 ? (btn.bounds.height / activeMenu.height) * 100 : 0}%`,
                          }}
                          onClick={() => {
                            if (act.type === 'URI') {
                              const resolvedUri = resolveRichMenuUri(act.uri);
                              setSimChatMessages([]);
                              setActiveSimLiff({
                                title: 'LIFF／網址動作本機預覽',
                                subtitle: '僅顯示草稿中的目標；不開啟網址、不送出請求。',
                                badge: '零寫入預覽',
                                fields: [
                                  { label: '草稿參數', value: act.uri ?? '未設定' },
                                  { label: '實際開啟路由', value: resolvedUri ?? '未設定' },
                                ],
                                actionButtons: [],
                              });
                              return;
                            }
                            if (act.type === 'MESSAGE') {
                              setActiveSimLiff(null);
                              setSimChatMessages([{ id: `msg-${Date.now()}`, sender: 'user', text: act.text ?? '', time: '本機預覽' }]);
                              return;
                            }
                            if (act.type === 'POSTBACK' || act.type === 'RICHMENU_SWITCH') {
                              setSimChatMessages([]);
                              setActiveSimLiff({
                                title: act.type === 'POSTBACK' ? 'Postback 動作本機預覽' : '圖文選單 切換本機預覽',
                                subtitle: '僅顯示草稿中的按鈕動作；不會送出 LINE 訊息。',
                                badge: '零寫入預覽',
                                fields: [
                                  { label: 'data', value: act.data ?? '未設定' },
                                  ...(act.alias ? [{ label: '圖文選單 alias', value: act.alias }] : []),
                                ],
                                actionButtons: [],
                              });
                              return;
                            }
                            setSimChatMessages([]);
                            setActiveSimLiff({
                              title: '此按鈕尚未設定動作',
                              subtitle: '系統不會依按鈕名稱猜測 action。',
                              badge: '設定缺口',
                              fields: [],
                              actionButtons: [],
                            });
                            return;
                          }}
                        >
                          <span className="richmenu-btn-icon"><Icon aria-hidden="true" /></span>
                          <span className="richmenu-btn-text">{btn.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>}

              {/* 右側：選單定義與發布面板 */}
              <div className="richmenu-inspector-column">
                {/* Card A: 選單定義與動作熱區綁定 */}
                {(richMenuWorkspaceTab === 'overview' || richMenuWorkspaceTab === 'actions') && <div className="richmenu-card">
                  <div className="richmenu-card-header">
                    <div>
                      <h3 className="line-card-title richmenu-heading-with-icon">
                        <Settings aria-hidden="true" />選單內容與按鈕設定
                      </h3>
                      <p className="line-card-description">
                        {activeMenu.audienceRoleLabel}｜{activeMenu.name}
                      </p>
                    </div>
                    <span className="line-category-badge category-service_flow">
                      {activeMenu.buttons.length} 個按鈕
                    </span>
                  </div>

                  <div className="line-table-scroll richmenu-table-spacing">
                    <table className="line-data-table">
                      <caption className="sr-only">圖文選單 按鈕動作與熱區</caption>
                      <thead>
                        <tr>
                          <th scope="col">熱區</th>
                          <th scope="col">按鈕標題</th>
                          <th scope="col">動作與進階資訊</th>
                          <th scope="col" className="line-align-end">沙盒測試</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeMenu.buttons.map((btn, idx) => {
                          const act = getTypedButtonAction(btn);
                          const resolvedUri = act.type === 'URI' ? resolveRichMenuUri(act.uri) : null;
                          return (
                            <tr key={btn.id}>
                              <td>
                                <span className="richmenu-hotspot-index">
                                  {idx + 1}
                                </span>
                              </td>
                              <td><strong>{btn.label}</strong></td>
                              <td>
                                <span className={`richmenu-action-kind ${act.type === 'URI' ? 'is-uri' : 'is-local'}`}>
                                  {act.type}
                                </span>
                                <details className="richmenu-advanced-details">
                                  <summary>進階資訊</summary>
                                  <div>
                                    <strong>目標參數／路由</strong>
                                    <code>
                                      {act.type === 'URI'
                                        ? (act.uri || '未設定')
                                        : act.type === 'MESSAGE'
                                          ? (act.text || '未設定')
                                          : act.type === 'RICHMENU_SWITCH'
                                            ? `${act.alias || '未設定 alias'} / ${act.data || '未設定 data'}`
                                            : (act.data || '未設定')}
                                    </code>
                                    {act.type === 'URI' && resolvedUri && <small>實際開啟：{resolvedUri}</small>}
                                    <strong>熱區座標</strong>
                                    <code>x:{btn.bounds.x} y:{btn.bounds.y} w:{btn.bounds.width} h:{btn.bounds.height}</code>
                                  </div>
                                </details>
                              </td>
                              <td className="line-align-end">
                                <button
                                  type="button"
                                  className="line-action-link-btn"
                                  onClick={() => {
                                    const syntheticBtn = document.querySelectorAll('.richmenu-grid-btn')[idx] as HTMLButtonElement | undefined;
                                    if (syntheticBtn) syntheticBtn.click();
                                  }}
                                >
                                  <Smartphone aria-hidden="true" />模擬點擊
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="line-scope-note line-block-spacing">
                    <strong>本機操作預覽</strong>：只顯示草稿中的按鈕動作或實際訊息文字；不猜測動作、不開啟網址、不送出 LINE 訊息。
                  </div>
                </div>}

                {richMenuDraftSnapshot && richMenuWorkspaceTab === 'appearance' && (
                  <LineRichMenuDraftAppearanceEditor
                    draft={richMenuDraftSnapshot}
                    menuId={activeMenu.id}
                    client={richMenuDraft}
                    previewDefinition={localDefinition}
                    onApplied={(readback) => {
                      setRichMenuLocalDefinition(null);
                      setRichMenuDraftSnapshot(readback);
                      setRichMenuConfiguration(loadedState(adaptLineRichMenuDraft(readback)));
                    }}
                    onLocalDefinitionChange={updateLocalRichMenuAppearance}
                  />
                )}

                {richMenuDraftSnapshot && richMenuWorkspaceTab === 'actions' && (
                  <>
                    <LineRichMenuDraftActionEditor
                      draft={richMenuDraftSnapshot}
                      menuId={activeMenu.id}
                      client={richMenuDraft}
                      previewDefinition={localDefinition}
                      onApplied={(readback) => {
                        setRichMenuLocalDefinition(null);
                        setRichMenuDraftSnapshot(readback);
                        setRichMenuConfiguration(loadedState(adaptLineRichMenuDraft(readback)));
                      }}
                      onLocalDefinitionChange={updateLocalRichMenuActions}
                    />
                  </>
                )}

                {/* 缺少 active snapshot typed Query 時，Diff 必須 fail closed。 */}
                {richMenuWorkspaceTab === 'publish' && isDiffMode && (
                  <div className="richmenu-card richmenu-diff-card">
                    <div className="richmenu-card-header">
                      <div>
                        <h3 className="line-card-title richmenu-heading-with-icon richmenu-diff-title">
                          <Sparkles aria-hidden="true" />版本變更比對
                        </h3>
                        <p className="line-card-description compact">
                          線上生效版本與目前草稿配置
                        </p>
                      </div>
                      <span className="richmenu-diff-badge">
                        比對模式已開啟
                      </span>
                    </div>

                    <div className="line-scope-note line-block-spacing-compact" role="status">
                      尚缺線上生效版本資料，暫不能進行正式版本差異比對；系統不會以按鈕順序或固定文案猜測原本內容。
                    </div>
                  </div>
                )}

                {/* Card C: 發布操作 */}
                {richMenuWorkspaceTab === 'publish'
                  && !activePublicationTracking
                  && activePublicationLock?.state === 'editable' && (
                  <LineRichMenuPublicationActions
                    selectedMenu={activeMenu}
                    selectedPublication={selectedPublication.value}
                    client={richMenuPublication}
                    onQueued={(queued) => {
                      setTrackedRichMenuPublication({
                        id: queued.publicationId,
                        menuDefinitionId: queued.menuDefinitionId,
                        configurationRevision: queued.configurationRevision,
                        status: queued.status,
                        attempts: 0,
                        timedOut: false,
                      });
                      setRichMenuPublicationPageNumber(1);
                      setRichMenuReload((value) => value + 1);
                    }}
                  />
                )}
                {richMenuWorkspaceTab === 'publish'
                  && (activePublicationTracking || activePublicationLock?.state !== 'editable') && (
                  <section className="richmenu-publish-card" aria-label="圖文選單 發布狀態">
                    {activePublicationTracking ? (
                      <>
                        <h4 className="richmenu-editor-title">
                          {activePublicationTracking.status === 'published'
                            ? '此版本已發布'
                            : ['queued', 'publishing'].includes(activePublicationTracking.status)
                              ? '發布處理中'
                              : '發布未完成'}
                        </h4>
                        {activePublicationTracking.status === 'published' ? (
                          <p>LINE 平台已完成發布。如需再次發布，請先到「外觀編輯」或「按鈕動作」保存變更，建立下一版草稿。</p>
                        ) : ['queued', 'publishing'].includes(activePublicationTracking.status) ? (
                          <p role="status">
                            {activePublicationTracking.timedOut
                              ? '自動追蹤已停止；發布可能仍在背景處理，請按上方「重新整理」取得最新狀態。'
                              : '工作已排入，系統正在自動追蹤 LINE 發布結果。'}
                          </p>
                        ) : (
                          <p>發布工作未成功完成，請到「發布歷程」查看失敗狀態與可用的重試操作。</p>
                        )}
                      </>
                    ) : activePublicationLock ? (
                      <>
                        <h4 className="richmenu-editor-title">
                          {activePublicationLock.state === 'published' ? '此版本已發布' : '發布處理中'}
                        </h4>
                        <p>{activePublicationLock.readonly_reason}</p>
                        {activePublicationLock.state === 'published' && (
                          <p>這不是月嫂或工會人員的權限限制；若要再次發布，請先編輯並保存，建立下一版草稿。</p>
                        )}
                      </>
                    ) : (
                      <>
                        <h4 className="richmenu-editor-title">目前無法判定發布資格</h4>
                        <p>缺少此選單目前版本的發布狀態，系統已停止發布操作；請重新整理後再試。</p>
                      </>
                    )}
                  </section>
                )}
              </div>
            </div>
            )}

            {/* 發布紀錄歷程 */}
            {richMenuWorkspaceTab === 'history' && <div className="richmenu-history-section" data-control-id="line.richmenu.publications">
              <div className="line-section-heading richmenu-history-heading">
                <div>
                  <h3 className="line-card-title">圖文選單 發布歷程紀錄</h3>
                  <p className="line-card-description">
                    顯示每次發布的排程、處理狀態與結果，方便追蹤未完成或失敗項目。
                  </p>
                </div>
              </div>

              {richMenuPublications.status === 'loading' && <div className="line-loading">正在載入 圖文選單 發布紀錄…</div>}
              {richMenuPublications.status === 'error' && <LineErrorMessage error={richMenuPublications.error} />}
              {richMenuPublications.status === 'loaded' && richMenuPublications.value && (
                richMenuPublications.value.items.length === 0 ? (
                  <div className="line-empty-state">
                    <h4>目前尚無發布紀錄</h4>
                    <p>由上方發布面板建立預覽並確認排入後，將會在此顯示發布狀態與結果。</p>
                  </div>
                ) : (
                  <div>
                    <div className="line-pagination-summary">
                      第 {richMenuPublications.value.page}／{Math.max(1, richMenuPublications.value.totalPages)} 頁，
                      顯示第 {(richMenuPublications.value.page - 1) * richMenuPublications.value.pageSize + 1}–
                      {Math.min(richMenuPublications.value.page * richMenuPublications.value.pageSize, richMenuPublications.value.total)} 筆，
                      共 {richMenuPublications.value.total} 筆
                    </div>
                    <div className="line-table-scroll">
                    <table className="line-data-table">
                      <caption className="sr-only">圖文選單 發布歷程</caption>
                      <thead>
                        <tr>
                          <th scope="col">選單</th>
                          <th scope="col">狀態</th>
                          <th scope="col">操作</th>
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
                                查看紀錄
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    </div>
                    <div className="line-pagination-actions">
                      <button type="button" className="line-secondary-btn" disabled={richMenuPublications.value.page <= 1} onClick={() => setRichMenuPublicationPageNumber((value) => Math.max(1, value - 1))}>上一頁</button>
                      <button type="button" className="line-secondary-btn" disabled={richMenuPublications.value.page >= Math.max(1, richMenuPublications.value.totalPages)} onClick={() => setRichMenuPublicationPageNumber((value) => Math.min(Math.max(1, richMenuPublications.value!.totalPages), value + 1))}>下一頁</button>
                    </div>
                  </div>
                )
              )}
            </div>}
          </section>
        );
      })()}

      {activeTab === 'binding' && <LineIdentityWorkbench client={lineIdentity} />}

      {activeTab === 'push_queue' && <LineNotificationWorkbench
        configuration={lineConfiguration}
        onboarding={onboardingClient}
        templates={notificationTemplateClient}
        search={notificationRuleSearch}
        enabled={notificationRuleEnabled}
        onSearchChange={setNotificationRuleSearch}
        onEnabledChange={setNotificationRuleEnabled}
      />}

      {activeTab === 'order_groups' && <LineOrderGroupWorkbench
        page={orderGroupPageNumber}
        search={orderGroupSearch}
        status={orderGroupStatus}
        onPageChange={setOrderGroupPageNumber}
        onSearchChange={setOrderGroupSearch}
        onStatusChange={setOrderGroupStatus}
      />}

      {activeTab === 'runtime' && (
        <div className="line-runtime-workspace">
          {/* 1. 安全去敏設定 */}
          <section className="line-workspace-card">
            <div className="line-section-heading">
              <div>
                <h2>LINE 安全狀態</h2>
                <p>只顯示六種安全設定的使用狀態；敏感定義與 LINE 密鑰不傳送到前端。</p>
              </div>
              <button
                type="button"
                className="line-secondary-btn"
                onClick={refreshRuntime}
              >
                <RefreshCw aria-hidden="true" />重新整理
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
                <h3>異常通知對象與群組</h3>
                <p>查詢並調整群組或管理員通知對象；送出時會自動核對最新狀態並避免重複處理。</p>
              </div>
            </div>

            <div className="line-field-stack line-section-bottom">
              <label htmlFor="runtime-reason" className="line-field-label">
                調整原因說明
              </label>
              <input
                id="runtime-reason"
                className="line-search-input line-full-width"
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
                  <h4>目前沒有異常通知對象</h4>
                  <p>通知對象會由已完成 LINE 綁定的管理員，或正式群組登錄流程建立。</p>
                </div>
              ) : (
                <div className="line-table-scroll">
                  <table className="line-data-table">
                    <caption className="sr-only">LINE 安全設定狀態</caption>
                    <thead>
                      <tr>
                        <th scope="col">類型</th>
                        <th scope="col">顯示名稱</th>
                        <th scope="col">狀態</th>
                        <th scope="col">觸發門檻</th>
                        <th scope="col" className="line-align-end">操作</th>
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
                          <td className="line-align-end">
                            <div className="line-row-actions line-actions-end">
                              <button
                                type="button"
                                className="line-secondary-btn line-compact-button"
                                disabled={runtimeMutation === 'loading' || !runtimeReason.trim()}
                                onClick={() => void previewRuntimeMutation('toggle', target)}
                              >
                                預覽{target.state === 'active' ? '停用' : '啟用'}
                              </button>
                              {target.targetKind === 'group' && (
                                <button
                                  type="button"
                                  className="line-secondary-btn line-compact-button"
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
              runtimeCandidates.value.some((candidate) => candidate.lineLinked) ? (
              <div className="line-row-actions runtime-candidate-row">
                <label htmlFor="runtime-candidate" className="line-field-label">
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
                  className="line-primary-btn line-compact-button"
                  disabled={selectedRuntimeCandidate === null || !runtimeReason.trim() || runtimeMutation === 'loading'}
                  onClick={() => void previewRuntimeMutation('add')}
                >
                  預覽新增通知對象
                </button>
              </div>
              ) : (
                <div className="line-scope-note line-block-spacing" role="status">
                  目前沒有已連結 LINE 且可加入的管理員。
                </div>
              )
            )}

            {runtimePending && (
              <div className="line-preview-result line-block-spacing-12">
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

            {runtimeReceipt && <div className="line-success line-block-spacing-12" role="status">{runtimeReceipt.operationLabel}已完成並回讀最新狀態。</div>}
            {runtimeError && <div className="line-error line-block-spacing-12" role="alert">{runtimeError}</div>}
          </section>

          <SafeReviewLinkWorkbench client={safeReviewLink} />

          {/* 3. 人工客服升級 */}
          <section className="line-workspace-card">
            <div className="line-section-heading">
              <div>
                <h2>人工客服升級</h2>
                <p>可建立升級事件，或以已知 ID 查詢並依 available actions 接手、處理與結案。</p>
              </div>
            </div>

            <div className="line-detail-grid line-section-bottom">
              <label>
                來源類型
                <select
                  className="line-filter-select line-full-width line-field-top-spacing"
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
                  className="line-filter-select line-full-width line-field-top-spacing"
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
                  className="line-filter-select line-full-width line-field-top-spacing"
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
              <details className="line-details-full">
                <summary>進階來源資料</summary>
                <p className="line-advanced-help">
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
              <div className="line-grid-full">
                {escalationSourceIdentity.trim() && !/^[0-9a-f]{64}$/.test(escalationSourceFingerprint) && (
                  <div className="line-scope-note line-bottom-spacing" role="status">
                    需先完成來源事件核對並補齊進階來源資料，才能預覽建立。
                  </div>
                )}
                <button
                  type="button"
                  className="line-primary-btn line-full-action"
                  disabled={!escalationSourceIdentity.trim() || !/^[0-9a-f]{64}$/.test(escalationSourceFingerprint) || escalationMutation === 'loading'}
                  onClick={() => void previewCreateEscalation()}
                >
                  預覽建立人工客服升級
                </button>
              </div>
            </div>

            <div className="line-row-actions line-section-bottom">
              <label htmlFor="escalation-id" className="line-field-label">升級 ID：</label>
              <input
                id="escalation-id"
                inputMode="numeric"
                className="line-search-input escalation-id-input"
                value={escalationIdInput}
                onChange={(event) => setEscalationIdInput(event.target.value)}
              />
              <button
                type="button"
                className="line-secondary-btn"
                disabled={!/^\d+$/.test(escalationIdInput)}
                onClick={() => void loadEscalation()}
              >
                查詢升級明細
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
                  <div><span>告警投遞任務</span><strong>{escalationDetail.value.deliveryTaskRef ?? '尚未建立'}</strong></div>
                  <div><span>本機結果</span><strong>{escalationDetail.value.deliveryOutcomeRef ?? '尚未回讀'}</strong></div>
                  {escalationDetail.value.triggerIdentity && <div><span>觸發身分（遮罩）</span><strong>{escalationDetail.value.triggerIdentity}</strong></div>}
                  {escalationDetail.value.attemptWindow && <div><span>嘗試窗口</span><strong>{escalationDetail.value.attemptWindow.attemptCount} / {escalationDetail.value.attemptWindow.maximumAttempts}（第 {escalationDetail.value.attemptWindow.generation} 輪）</strong></div>}
                  {escalationDetail.value.ownerSelector && <div><span>負責人選擇器</span><strong>{escalationDetail.value.ownerSelector}</strong></div>}
                </div>

                <details className="line-advanced-section">
                  <summary>進階一致性與結案資料</summary>
                  <p className="line-advanced-help">
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

                <div className="line-row-actions line-block-spacing">
                  {escalationDetail.value.availableActions.includes('claim') && (
                    <button
                      type="button"
                      className="line-primary-btn"
                      disabled={escalationMutation === 'loading'}
                      onClick={() => void previewAdvanceEscalation('claim')}
                    >
                      預覽接手
                    </button>
                  )}
                  {escalationDetail.value.availableActions.includes('handling') && (
                    <button
                      type="button"
                      className="line-primary-btn"
                      disabled={escalationMutation === 'loading'}
                      onClick={() => void previewAdvanceEscalation('handling')}
                    >
                      預覽開始處理
                    </button>
                  )}
                  {escalationDetail.value.availableActions.includes('resolve') && (
                    <button
                      type="button"
                      className="line-primary-btn"
                      disabled={escalationMutation === 'loading' || !/^[0-9a-f]{64}$/.test(escalationResolutionDigest)}
                      onClick={() => void previewAdvanceEscalation('resolve')}
                    >
                      預覽解決並解除暫停
                    </button>
                  )}
                </div>
              </>
            )}

            {escalationPending && (
              <div className="line-preview-result line-block-spacing-12">
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

            {escalationReceipt && <div className="line-success line-block-spacing-12" role="status">人工客服升級操作已完成；目前狀態：{escalationReceipt.workflowStatus}。</div>}
            {escalationError && <div className="line-error line-block-spacing-12" role="alert">{escalationError}</div>}
          </section>
        </div>
      )}





      <Drawer isOpen={selectedPublication.status !== 'idle'} onClose={closePublication} title="圖文選單 發布紀錄" footer={<div className="line-drawer-footer"><button type="button" onClick={closePublication}>關閉</button>{selectedPublication.status === 'error' && publicationDetailId.current !== null && <button type="button" onClick={() => openPublication(publicationDetailId.current!)}>重試查詢</button>}</div>}><div className="line-drawer-content"><LoadingOrError state={selectedPublication} loadingText="正在載入發布紀錄明細…" />{selectedPublication.status === 'loaded' && selectedPublication.value && <div className="line-detail-grid"><div><span>選單</span><strong>{richMenuConfiguration.value?.menus.find((menu) => menu.id === selectedPublication.value?.menuDefinitionId)?.name ?? '已發布圖文選單'}</strong></div><div><span>目前狀態</span><strong>{selectedPublication.value.statusLabel}</strong></div></div>}</div></Drawer>
    </div>
  );
};

export default LineManagementPage;
