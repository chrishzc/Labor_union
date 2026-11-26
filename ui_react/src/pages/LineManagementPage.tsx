/**
 * File: LineManagementPage.tsx
 * Description: 整合 LINE typed Query／Preview／Apply 工作區，所有外送副作用仍由後端 durable task 執行。
 */
import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { useUnsavedNavigation } from '../components/UnsavedChanges';
import React, { Suspense, lazy, useEffect, useRef, useState } from 'react';
import {
  Baby,
  Bot,
  CalendarDays,
  ClipboardCheck,
  Eraser,
  FileBarChart,
  FilePenLine,
  FileText,
  Headphones,
  Info,
  MapPin,
  Menu,
  PackageSearch,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Star,
  TriangleAlert,
  Users,
  WalletCards,
} from 'lucide-react';

import {
  adaptLineRichMenuPublication,
  type LineRichMenuConfigurationModel,
  type LineRichMenuPublicationModel,
  type RichMenuButtonModel,
} from '../adapters/line_configuration/line_configuration_query_adapter';
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
  LineRuntimeTargetEnabledRequest,
  LineRuntimeTargetPreview,
} from '../api/line_runtime_targets/line_runtime_target_schemas';
import { LineIdentityWorkbench } from '../components/LineIdentityWorkbench';
import { LineDeliveryOperationsWorkbench } from '../components/LineDeliveryOperationsWorkbench';
import { LineNotificationWorkbench } from '../components/LineNotificationWorkbench';
import type { LineNotificationTemplateClient } from '../api/line_notification_rules/line_notification_template_client';
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
import { LineRichMenuDraftSaveActions } from '../components/LineRichMenuDraftSaveActions';
import { AiEventStudio } from './line_management/AiEventStudio';
import './LineManagementPage.css';
import './line_management/LineRichMenuWorkspace.css';

type LineTab = 'richmenu' | 'liff' | 'binding' | 'push_queue' | 'delivery' | 'guidance' | 'order_groups' | 'payment_overdue' | 'runtime';
/** 依責任邊界切分的頁面範圍：客服受理、通知寄送、LINE 介面設定。 */
export type LineScope = 'service' | 'notifications' | 'interface';
const LiffCardStudio = lazy(() => import('./line_management/LiffCardStudio').then((m) => ({ default: m.LiffCardStudio })));

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

type LineIdentityPageClient = Partial<LineIdentityClient>;

interface LineManagementPageProps {
  lineIdentity?: LineIdentityPageClient;
  lineConfiguration?: LineConfigurationQueryClient;
  richMenuDraft?: LineRichMenuDraftClient;
  richMenuPublication?: LineRichMenuPublicationClient;
  richMenuPublicationPollIntervalMs?: number;
  runtimeTarget?: typeof lineRuntimeTargetClient;
  delivery?: typeof lineDeliveryQueryClient;
  safeReviewLink?: SafeReviewLinkClient;
  notificationTemplateClient?: LineNotificationTemplateClient;
  /** Render only the safety workspace inside the canonical Group & Security page. */
  runtimeOnly?: boolean;
  /** 此頁面承載的責任範圍；預設為客服受理。 */
  scope?: LineScope;
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
  | { kind: 'toggle'; targetId: number; request: LineRuntimeTargetEnabledRequest; preview: LineRuntimeTargetPreview };

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
  if (error instanceof LineIdentityClientError) return `${error.code}：${error.message}`;
  if (error instanceof LineConfigurationQueryError) return `${error.code}：${error.message}`;
  if (error instanceof LineDeliveryQueryError) return `${error.code}：${error.message}`;
  if (error instanceof LineSafeConfigError) return `${error.code}：${error.message}`;
  if (error instanceof LineRuntimeTargetError) return `${error.code}：${error.message}`;
  return fallback;
}

const TABS: ReadonlyArray<readonly [LineTab, string, string]> = [
  ['binding', '身分與授權', 'line.tab.binding'],
  ['order_groups', '案件群組', 'line.tab.order-groups'],
  ['push_queue', '通知與發送', 'line.tab.push-queue'],
  ['delivery', '寄送與異常', 'line.tab.delivery'],
  ['richmenu', '圖文選單', 'line.tab.richmenu'],
  ['liff', '表單', 'line.tab.liff'],
  ['guidance', '引導動作', 'line.tab.guidance'],
];

const SCOPE_VIEWS: Record<LineScope, { title: string; subtitle: string; tabs: readonly LineTab[]; fallback: LineTab }> = {
  service: { title: 'LINE 營運', subtitle: '管理身分授權與案件群組。', tabs: ['binding', 'order_groups'], fallback: 'binding' },
  notifications: { title: '通知與寄送', subtitle: '維護通知文案，查看寄送進度與失敗紀錄。', tabs: ['push_queue', 'delivery'], fallback: 'push_queue' },
  interface: { title: 'LINE 介面設定', subtitle: '維護圖文選單、表單與引導動作。', tabs: ['richmenu', 'liff', 'guidance'], fallback: 'richmenu' },
};

const SAFE_CONFIGURATION_KINDS: readonly LineSafeConfigKind[] = [
  'message_templates', 'message_schedules', 'rich_menus', 'liff',
  'notification_rules',
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
  'target:staff_order_search': '/line-staff-orders',
  'target:staff_schedule': '/line-staff-schedule',
  'target:staff_verification': '/line-identity?target=staff_verification',
  'target:staff_payout': '/line-staff-payout',
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

export const LineManagementPage: React.FC<LineManagementPageProps> = ({
  lineIdentity = lineIdentityClient,
  lineConfiguration = lineConfigurationQueryClient,
  notificationTemplateClient,
  richMenuDraft = lineRichMenuDraftClient,
  richMenuPublication = lineRichMenuPublicationClient,
  richMenuPublicationPollIntervalMs = 1500,
  runtimeTarget = lineRuntimeTargetClient,
  safeReviewLink = safeReviewLinkClient,
  runtimeOnly = false,
  scope = 'service',
}) => {
  const view = SCOPE_VIEWS[scope];
  const initialHashParams = useRef(currentHashParams()).current;
  const [activeTab, setActiveTab] = useState<LineTab>(() => {
    if (runtimeOnly) return 'runtime';
    const initialRoute = window.location.hash.replace(/^#\/?/, '').split('?', 1)[0];
    if (scope === 'interface' && (initialRoute === 'line-liff-studio' || initialRoute === 'line-studio')) return 'liff';
    return hashChoice<LineTab>(initialHashParams, 'tab', [...view.tabs, 'payment_overdue'], view.fallback);
  });
  useEffect(() => { if (activeTab === 'payment_overdue') window.location.hash = '#finance?tab=receipts&view=overdue'; }, [activeTab]);
  const [notificationMessageId, setNotificationMessageId] = useState<string | null>(initialHashParams.get('message')?.slice(0, 191) || null);
  const [notificationRuleSearch, setNotificationRuleSearch] = useState(initialHashParams.get('rule_q') ?? '');

  const [orderGroupPageNumber, setOrderGroupPageNumber] = useState(hashPage(initialHashParams, 'group_page'));
  const [orderGroupSearch, setOrderGroupSearch] = useState((initialHashParams.get('group_q') ?? '').slice(0, 50));
  const [orderGroupStatus, setOrderGroupStatus] = useState<LineOrderGroupStatus | 'all'>(hashChoice<LineOrderGroupStatus | 'all'>(initialHashParams, 'group_state', ['all', 'unbound', 'bound', 'inviting', 'active', 'attention', 'replaced', 'released'], 'all'));

  const [safeConfigurations, setSafeConfigurations] = useState<QueryState<LineSafeConfigModel[]>>(idleState);
  const [runtimeTargets, setRuntimeTargets] = useState<QueryState<LineRuntimeTargetModel[]>>(idleState);
  const [runtimeCandidates, setRuntimeCandidates] = useState<QueryState<LineRuntimeAdminCandidateModel[]>>(idleState);
  const [runtimeReload, setRuntimeReload] = useState(0);
  const [runtimeReason, setRuntimeReason] = useState('');
  const [selectedRuntimeCandidate, setSelectedRuntimeCandidate] = useState<number | null>(null);
  const [runtimeReceipt, setRuntimeReceipt] = useState<LineRuntimeTargetReceiptModel | null>(null);
  const [runtimeMutation, setRuntimeMutation] = useState<MutationStatus>('idle');
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const runtimePreviewController = useRef<AbortController | null>(null);
  const runtimePreviewGeneration = useRef(0);
  const runtimeIdentity = useRef<{ signature: string; correlationId: string; idempotencyKey: string } | null>(null);


  const [richMenuConfiguration, setRichMenuConfiguration] = useState<QueryState<LineRichMenuConfigurationModel>>(idleState);
  const [richMenuDraftSnapshot, setRichMenuDraftSnapshot] = useState<RichMenuDraft | null>(null);
  const [richMenuLocalDefinition, setRichMenuLocalDefinition] = useState<RichMenuDraftDefinition | null>(null);
  const [richMenuReload, setRichMenuReload] = useState(0);
  const richMenuListGeneration = useRef(0);
  const [selectedMenuId, setSelectedMenuId] = useState<string | null>(null);
  const [trackedRichMenuPublication, setTrackedRichMenuPublication] = useState<{
    id: number;
    menuDefinitionId: string;
    configurationRevision: number;
    status: LineRichMenuPublicationModel['status'];
    attempts: number;
    timedOut: boolean;
    lastStep?: string;
  } | null>(null);

  const [publicationReadState, setPublicationReadState] = useState<'idle' | 'loading' | 'unknown'>('idle');

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
  const [richMenuEditorTab, setRichMenuEditorTab] = useState<'appearance' | 'actions'>('appearance');
  const [richMenuBusy, setRichMenuBusy] = useState(false);
  const [richMenuReloadRequired, setRichMenuReloadRequired] = useState(false);

  useEffect(() => {
    if (runtimeOnly) return;
    const route = window.location.hash.replace(/^#\/?/, '').split('?', 1)[0];
    const hubRoute = route === 'line-management' || route === 'line' || route === 'line-notifications' || route === 'line-interface';
    const legacyFormRoute = (route === 'line-liff-studio' || route === 'line-studio') && activeTab !== 'liff';
    if (!hubRoute && !legacyFormRoute) return;
    const canonicalRoute = scope === 'notifications' ? 'line-notifications' : (route === 'line-notifications' || route === 'line-interface')
      ? route
      : (route === 'line' ? 'line' : 'line-management');
    const params = currentHashParams();
    const setParam = (key: string, value: string | number, fallback: string | number) => {
      if (value === fallback || value === '') params.delete(key);
      else params.set(key, String(value));
    };
    setParam('tab', activeTab, scope === 'service' ? 'binding' : '');
    params.delete('rich');
    params.delete('rich_page');
    setParam('rule_q', notificationRuleSearch, '');
    setParam('message', notificationMessageId ?? '', '');
    if (activeTab === 'push_queue') {
      ['notice', 'rule_event', 'rule_recipient', 'rule_page', 'rule_state'].forEach(key => params.delete(key));
      if (params.get('view') === 'flow') params.delete('view');
    }
    setParam('group_page', orderGroupPageNumber, 1);
    setParam('group_q', orderGroupSearch, '');
    setParam('group_state', orderGroupStatus, 'all');
    const query = params.toString();
    const nextHash = `#${canonicalRoute}${query ? `?${query}` : ''}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}${nextHash}`);
    }
  }, [
    activeTab,
    scope,
    notificationRuleSearch,
    notificationMessageId,
    orderGroupPageNumber,
    orderGroupSearch,
    orderGroupStatus,
    runtimeOnly,
  ]);



  useEffect(() => {
    if (activeTab !== 'richmenu') return;
    const controller = new AbortController();
    const generation = ++richMenuListGeneration.current;
    setRichMenuLocalDefinition(null);
    setRichMenuDraftSnapshot(null);
    setRichMenuConfiguration(loadingState());
    void richMenuDraft.query({ signal: controller.signal }).then((draft) => {
      if (controller.signal.aborted || generation !== richMenuListGeneration.current) return;
      const configuration = adaptLineRichMenuDraft(draft);
      setRichMenuDraftSnapshot(draft);
      setRichMenuReloadRequired(false);
      setRichMenuConfiguration(loadedState(configuration));
      setSelectedMenuId((current) => current ?? configuration.menus[0]?.id ?? null);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setRichMenuConfiguration(errorState(displayQueryError(error, '圖文選單設定載入失敗')));
    });
    return () => controller.abort();
  }, [activeTab, richMenuDraft, richMenuReload]);

  useEffect(() => {
    const tracked = trackedRichMenuPublication;
    if (
      activeTab !== 'richmenu'
      || publicationReadState === 'loading'
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
                lastStep: publication.step_receipts?.at(-1)?.step,
                attempts: existing.attempts + 1,
              }
            : existing);
          if (!['queued', 'publishing'].includes(current.status)) {
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
    publicationReadState,
  ]);

  async function refreshRichMenuPublication(): Promise<void> {
    if (publicationReadState === 'loading') return;
    const revision = richMenuDraftSnapshot?.revision;
    const menuId = selectedMenuId;
    if (richMenuReloadRequired || revision === undefined || !menuId) {
      setRichMenuReload(value => value + 1);
      return;
    }
    setPublicationReadState('loading');
    try {
      const tracked = trackedRichMenuPublication;
      const id = tracked?.menuDefinitionId === menuId && tracked.configurationRevision === revision
        ? tracked.id
        : (await lineConfiguration.listRichMenuPublications({ menuId, page: 1, pageSize: 1 })).items
          .find(item => item.menu_definition_id === menuId && item.configuration_revision === revision)?.id;
      if (id !== undefined) {
        const publication = await lineConfiguration.getRichMenuPublication(id);
        const current = adaptLineRichMenuPublication(publication);
        if (current.id !== id || current.menuDefinitionId !== menuId || current.configurationRevision !== revision) {
          throw new Error('Rich Menu publication identity mismatch');
        }
        setTrackedRichMenuPublication({
          ...current, attempts: 0, timedOut: false,
          lastStep: publication.step_receipts?.at(-1)?.step,
        });
      }
      setPublicationReadState('idle');
      setRichMenuReload(value => value + 1);
    } catch {
      setPublicationReadState('unknown');
    }
  }



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
        if (targetResult.status === 'fulfilled') setRuntimeTargets(loadedState(targetResult.value.filter((target) => target.target_kind === 'admin_user').map(adaptLineRuntimeTarget)));
        else setRuntimeTargets(errorState(displayQueryError(targetResult.reason, '異常通知對象載入失敗')));
        if (candidateResult.status === 'fulfilled') setRuntimeCandidates(loadedState(candidateResult.value.map(adaptLineRuntimeAdminCandidate)));
        else setRuntimeCandidates(errorState(displayQueryError(candidateResult.reason, '管理員候選載入失敗')));
      });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); controller.abort(); };
  }, [activeTab, runtimeReload, runtimeTarget]);

  useEffect(() => {

    if (activeTab !== 'runtime') {
      runtimePreviewController.current?.abort();
      runtimePreviewController.current = null;
      runtimePreviewGeneration.current += 1;
      }
  }, [activeTab]);

  useEffect(() => () => {
    runtimePreviewController.current?.abort();
    runtimePreviewGeneration.current += 1;
  }, []);

  const refreshRuntime = () => setRuntimeReload((value) => value + 1);

  const previewRuntimeMutation = async (operation: 'add' | 'toggle', target?: LineRuntimeTargetModel) => {
    if (operation === 'add' && selectedRuntimeCandidate === null) return;
    if (operation !== 'add' && target?.targetKind !== 'admin_user') return;
    runtimePreviewController.current?.abort();
    const controller = new AbortController();
    runtimePreviewController.current = controller;
    const generation = runtimePreviewGeneration.current + 1;
    runtimePreviewGeneration.current = generation;
    const signature = JSON.stringify([operation, target?.targetId, target?.currentVersion, target?.state, selectedRuntimeCandidate, runtimeReason.trim()]);
    if (runtimeIdentity.current?.signature !== signature) runtimeIdentity.current = {
      signature, correlationId: operationIdentity(`line-runtime-${operation}`), idempotencyKey: operationIdentity(`line-runtime-${operation}-apply`),
    };
    const { correlationId, idempotencyKey } = runtimeIdentity.current;
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
      } else {
        if (!target) return;
        const request = { expected_version: target.currentVersion, enabled: target.state !== 'active', reason: runtimeReason.trim(), correlation_id: correlationId, idempotency_key: idempotencyKey };
        const preview = await runtimeTarget.previewSetEnabled(target.targetId, request, { signal: controller.signal });
        pending = { kind: 'toggle', targetId: target.targetId, request, preview };
      }
      if (controller.signal.aborted || generation !== runtimePreviewGeneration.current) return;
      await applyRuntimeMutation(pending);
    } catch (error: unknown) {
      if (controller.signal.aborted || generation !== runtimePreviewGeneration.current) return;
      setRuntimeMutation('error');
      setRuntimeError(displayQueryError(error, '異常通知對象 Preview 失敗'));
    }
  };

  const applyRuntimeMutation = async (runtimePending: RuntimePendingOperation) => {
    setRuntimeMutation('loading');
    setRuntimeError(null);
    try {
      let receipt;
      if (runtimePending.kind === 'add') {
        receipt = await runtimeTarget.addAdminTarget({
          ...runtimePending.request,
          preview_fingerprint: runtimePending.preview.preview_fingerprint,
        });
      } else {
        receipt = await runtimeTarget.setEnabled(runtimePending.targetId, {
          ...runtimePending.request,
          preview_fingerprint: runtimePending.preview.preview_fingerprint,
        });
      }
      runtimeIdentity.current = null;
      setRuntimeReceipt(adaptLineRuntimeTargetReceipt(receipt));
      setRuntimeMutation('success');
      refreshRuntime();
    } catch (error: unknown) {
      setRuntimeMutation('error');
      setRuntimeError(displayQueryError(error, '異常通知對象 Apply 失敗'));
    }
  };

  const { requestLeave } = useUnsavedNavigation();
  const localRichMenuConfiguration = richMenuDraftSnapshot && richMenuLocalDefinition
    ? adaptLineRichMenuDraft({ ...richMenuDraftSnapshot, definition: richMenuLocalDefinition })
    : richMenuConfiguration.value;
  const selectedMenu = localRichMenuConfiguration?.menus.find((menu) => menu.id === selectedMenuId) ?? null;
  const richMenuDirty = Boolean(richMenuDraftSnapshot && richMenuLocalDefinition
    && JSON.stringify(richMenuLocalDefinition) !== JSON.stringify(richMenuDraftSnapshot.definition));
  useEffect(() => {
    if (!richMenuDirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [richMenuDirty]);

  return (
    <div className={`line-page-wrapper${runtimeOnly ? ' line-runtime-embedded' : ''}${activeTab === 'richmenu' ? ' line-richmenu-active' : ''}`} data-control-id="line.page">
      {!runtimeOnly && <ManagementPageHeader className="line-page-header" title={view.title} description={view.subtitle}>
        <span className="line-hub-eyebrow">LINE 專區</span>
      </ManagementPageHeader>}
      {!runtimeOnly && <nav className="line-tab-bar" aria-label={view.title}>
        {[view.title].map((group) => <div key={group} className="line-nav-group" role="group" aria-label={group}>
          {TABS.filter(([tab]) => view.tabs.includes(tab)).map(([tab, label, id]) => <button key={tab} type="button" data-control-id={id} className={`line-tab-btn ${activeTab === tab ? 'active' : ''}`} disabled={richMenuBusy} aria-current={activeTab === tab ? 'page' : undefined} onClick={() => { if (activeTab !== tab) requestLeave(() => { if (activeTab === 'richmenu') setRichMenuLocalDefinition(null); setActiveTab(tab); }); }}>{label}</button>)}
        </div>)}
      </nav>}

      {activeTab === 'delivery' && <LineDeliveryOperationsWorkbench/>}
      {activeTab === 'payment_overdue' && <a href="#finance?tab=receipts&view=overdue">前往帳務作業的逾期提醒</a>}

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
          <section className="line-table-container richmenu-clean-workspace" data-control-id="line.richmenu.configuration">
            <div className="line-section-heading">
              <div>
                <h2>圖文選單</h2>
            <p>選擇角色，編輯選單，再確認發布。儲存草稿不會發布至 LINE。</p>
              </div>
              <button
                type="button"
                className="line-secondary-btn"
                data-control-id="line.richmenu.refresh"
                aria-label="重新整理"
                title={richMenuDirty ? '請先儲存或取消修改，再重新整理' : '重新整理草稿'}
                disabled={richMenuDirty || richMenuBusy || publicationReadState === 'loading'}
                onClick={() => void refreshRichMenuPublication()}
              >
                <RefreshCw aria-hidden="true" /><span className="richmenu-refresh-label">重新整理</span>
              </button>
            </div>

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
                    aria-pressed={activeMenu?.id === menu.id}
                    disabled={richMenuBusy}
                    onClick={() => {
                      setSelectedMenuId(menu.id);
                      setActiveSimLiff(null);
                      setSimChatMessages([]);
                    }}
                  >
                    {menu.audienceRoleLabel}
                  </button>
                ))}
              </div>

              {(simChatMessages.length > 0 || activeSimLiff) && <button type="button" className="line-secondary-btn" onClick={() => { setSimChatMessages([]); setActiveSimLiff(null); }}><Eraser aria-hidden="true" />清除預覽</button>}
            </div>


            {/* 左右分割工作台 */}
            {activeMenu && (
            <div className="richmenu-studio-grid richmenu-studio-grid-edit">
              {/* 左側：3D 手機即時模擬器 */}
              <div className="richmenu-phone-card">
                <div className="richmenu-phone-card-header">
                  <span className="richmenu-phone-heading">
                    手機預覽
                  </span>
                  {activeSimLiff && (
                    <span className="richmenu-preview-badge">
                      點擊動作預覽
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
                    style={{ backgroundColor: activeMenuDefinition?.appearance?.background_color, aspectRatio: `${activeMenu.width} / ${activeMenu.height}` }}
                  >
                    {activeMenu.buttons.map((btn) => {
                      const label = btn.label;
                      const act = getTypedButtonAction(btn);
                      const btnAccent = activeMenuDefinition?.buttons.find((item) => item.id === btn.id)?.background_color;
                      let Icon = MapPin;
                      if (label.includes('營運') || label.includes('摘要') || label.includes('報表')) Icon = FileBarChart;
                      else if (label.includes('客服') || label.includes('諮詢') || label.includes('聯絡') || label.includes('專人')) Icon = Headphones;
                      else if (label === '我的資料' || label.includes('改') || label.includes('修改') || label.includes('異動')) Icon = FilePenLine;
                      else if (label.includes('月嫂')) Icon = Baby;
                      else if (label.includes('預約') || label.includes('登記')) Icon = FileText;
                      else if (label.includes('說明') || label.includes('FAQ') || label.includes('常見問答') || label.includes('問答')) Icon = Info;
                      else if (label.includes('AI') || label.includes('智慧問答') || label.includes('助理')) Icon = Sparkles;
                      else if (label.includes('案件') || label.includes('訂單')) Icon = PackageSearch;
                      else if (label.includes('班表') || label.includes('排班') || label.includes('日曆') || label.includes('請假')) Icon = CalendarDays;
                      else if (label.includes('薪資') || label.includes('請款')) Icon = WalletCards;
                      else if (label.includes('契約') || label.includes('合約')) Icon = FileText;
                      else if (label.includes('評價') || label.includes('滿意度')) Icon = Star;
                      else if (label.includes('待辦') || label.includes('審核')) Icon = ClipboardCheck;
                      else if (label.includes('一般用戶')) Icon = Users;
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
                            ...(btnAccent ? { '--richmenu-btn-accent': btnAccent } as React.CSSProperties : {}),
                          }}
                          onClick={() => {
                            if (act.type === 'URI') {
                              const resolvedUri = resolveRichMenuUri(act.uri);
                              setSimChatMessages([]);
                              setActiveSimLiff({
                                title: '連結預覽',
                                subtitle: '僅顯示草稿中的目標；不開啟網址、不送出請求。',
                                badge: '零寫入預覽',
                                fields: [
                                  { label: '草稿參數', value: act.uri ?? '未設定' },
                                  { label: '開啟網址', value: resolvedUri ?? '未設定' },
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
              </div>

              {/* 右側：選單定義與發布面板 */}
              <div className="richmenu-inspector-column">
                {richMenuDraftSnapshot && localDefinition && <>
                  <div className="richmenu-editor-heading"><h3>選單設定</h3><span>{activeMenu.name}</span></div>
                  <fieldset className="richmenu-editor-fields" disabled={richMenuBusy}>
                    <legend className="sr-only">編輯選單設定</legend>
                    <div className="richmenu-editor-switch" role="group" aria-label="編輯項目">
                      <button type="button" className={richMenuEditorTab === 'appearance' ? 'active' : ''} aria-pressed={richMenuEditorTab === 'appearance'} onClick={() => setRichMenuEditorTab('appearance')}>外觀與名稱</button>
                      <button type="button" className={richMenuEditorTab === 'actions' ? 'active' : ''} aria-pressed={richMenuEditorTab === 'actions'} onClick={() => setRichMenuEditorTab('actions')}>按鈕設定</button>
                    </div>
                    {richMenuEditorTab === 'appearance' ? <LineRichMenuDraftAppearanceEditor draft={richMenuDraftSnapshot} menuId={activeMenu.id}
                      definition={localDefinition} onDefinitionChange={setRichMenuLocalDefinition} />
                      : <LineRichMenuDraftActionEditor draft={richMenuDraftSnapshot} menuId={activeMenu.id}
                        definition={localDefinition} onDefinitionChange={setRichMenuLocalDefinition} />}
                  </fieldset>
                  <p className="richmenu-edit-help">儲存後即可點選「發布至 LINE」。</p>
                </>}
              </div>
            </div>
            )}

            <div className="richmenu-publish-panel">
            {/* 本機幾何初檢；正式路由與發布資格只由 server Preview 裁決。 */}
            {activeMenu && (() => {
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
                      <strong>按鈕區域檢查：</strong>
                      <span className="richmenu-safety-description">
                        {localGeometryPassed
                          ? '範圍完整、無重疊。'
                          : `需修正：${geometryIssues.join('、')}。`}
                        {' '}正式路由與發布資格仍須由系統檢查。
                      </span>
                    </div>
                  </div>
                  <span className="richmenu-safety-status">
                    {localGeometryPassed ? '檢查正常' : '需修正範圍'}
                  </span>
                </div>
              );
            })()}

                {/* Card C: 發布操作 */}
                {!richMenuDirty && !richMenuReloadRequired
                  && !activePublicationTracking
                  && activePublicationLock?.state === 'editable' && (
                  <LineRichMenuPublicationActions
                    selectedMenu={activeMenu}
                    selectedPublication={null}
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
                      setRichMenuReload((value) => value + 1);
                    }}
                  />
                )}
                {publicationReadState === 'unknown' && <p role="status">目前無法查詢發布結果；未重新送出發布。</p>}
                {(activePublicationTracking || activePublicationLock?.state !== 'editable') && (
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
                        <p>發布編號：{activePublicationTracking.id}{activePublicationTracking.lastStep && ` · 最後已確認步驟：${activePublicationTracking.lastStep}`}</p>
                        {activePublicationTracking.status === 'published' ? (
                          <p>LINE 平台已完成發布。如需再次發布，請先儲存變更，建立下一版草稿。</p>
                        ) : ['queued', 'publishing'].includes(activePublicationTracking.status) ? (
                          <p role="status">
                            {activePublicationTracking.timedOut
                              ? '自動追蹤已停止；發布可能仍在背景處理，請按上方「重新整理」取得最新狀態。'
                              : '工作已排入，系統正在自動追蹤 LINE 發布結果。'}
                          </p>
                        ) : (
                          <>
                            <p>發布工作未成功完成。</p>
                            {activePublicationTracking.status === 'publish_retryable_failed' && <LineRichMenuPublicationActions
                              selectedMenu={null} selectedPublication={{ id: activePublicationTracking.id, menuDefinitionId: activePublicationTracking.menuDefinitionId, status: activePublicationTracking.status, statusLabel: '發布可重試失敗' }}
                              client={richMenuPublication} onQueued={(queued) => {
                                setTrackedRichMenuPublication({ id: queued.publicationId, menuDefinitionId: queued.menuDefinitionId, configurationRevision: queued.configurationRevision, status: queued.status, attempts: 0, timedOut: false });
                                setRichMenuReload((value) => value + 1);
                              }} />}
                          </>
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
                        <p>無法確認目前選單的發布狀態。請重新整理後再發布。</p>
                      </>
                    )}
                  </section>
                )}
            </div>

            {activeMenu && richMenuDraftSnapshot && localDefinition
              && (activePublicationLock?.state === 'editable' || activePublicationLock?.state === 'published') && <LineRichMenuDraftSaveActions
                publicationAction={null}
                draft={richMenuDraftSnapshot} definition={localDefinition} client={richMenuDraft} onBusyChange={setRichMenuBusy} onReloadRequired={() => setRichMenuReloadRequired(true)}
                onCancel={() => { setRichMenuLocalDefinition(null); setActiveSimLiff(null); setSimChatMessages([]); }} onApplied={(readback) => {
                  setRichMenuLocalDefinition(null); setRichMenuReloadRequired(false); setRichMenuDraftSnapshot(readback); setRichMenuConfiguration(loadedState(adaptLineRichMenuDraft(readback)));
                }} />}

            {activeMenu && activePublicationLock?.state === 'processing' && <div className="richmenu-save-footer">
              <span className="richmenu-save-state">發布處理中，選單暫時唯讀</span>
            </div>}

          </section>
        );
      })()}

      {activeTab === 'binding' && <LineIdentityWorkbench client={lineIdentity} />}

      {activeTab === 'liff' && <Suspense fallback={<p role="status">載入表單設計…</p>}><LiffCardStudio embedded /></Suspense>}

      {activeTab === 'guidance' && (
        <div className="line-guidance-panel">
          <AiEventStudio />
        </div>
      )}

      {activeTab === 'push_queue' && <LineNotificationWorkbench configuration={lineConfiguration} templates={notificationTemplateClient}
          search={notificationRuleSearch} onSearchChange={setNotificationRuleSearch}
          initialCategory={initialHashParams.get('category') === 'accounting' ? 'accounting' : 'all'}
          selectedEntryId={notificationMessageId} onSelectedEntryChange={setNotificationMessageId}
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
                <h3>管理員個人異常通知對象</h3>
                <p>查詢並調整管理員個人通知對象；儲存時會自動核對最新狀態並避免重複處理。</p>
              </div>
            </div>

            <div className="line-field-stack line-section-bottom">
              <label htmlFor="runtime-reason" className="line-field-label">
                調整原因說明（選填）
              </label>
              <input
                id="runtime-reason"
                className="line-search-input line-full-width"
                value={runtimeReason}
                onChange={(event) => {
                  setRuntimeReason(event.target.value);
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
                                disabled={runtimeMutation === 'loading'}
                                onClick={() => void previewRuntimeMutation('toggle', target)}
                              >
                                {target.state === 'active' ? '停用' : '啟用'}
                              </button>
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
                  disabled={selectedRuntimeCandidate === null || runtimeMutation === 'loading'}
                  onClick={() => void previewRuntimeMutation('add')}
                >
                  新增通知對象
                </button>
              </div>
              ) : (
                <div className="line-scope-note line-block-spacing" role="status">
                  目前沒有已連結 LINE 且可加入的管理員。
                </div>
              )
            )}

            {runtimeReceipt && <div className="line-success line-block-spacing-12" role="status">{runtimeReceipt.operationLabel}已完成並回讀最新狀態。</div>}
            {runtimeError && <div className="line-error line-block-spacing-12" role="alert">{runtimeError}</div>}
          </section>

          <SafeReviewLinkWorkbench client={safeReviewLink} />

        </div>
      )}






    </div>
  );
};

export default LineManagementPage;
