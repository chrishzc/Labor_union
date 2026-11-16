/**
 * File: LineNotificationWorkbench.tsx
 * Description: 統一 LINE 通知與卡片內容維護，提供即時預覽及版本化儲存。
 */
import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import { useRef as useValidationRef } from 'react';
import { useSaveValidation } from './useSaveValidation';
import { useEffect, useId, useRef, useState, type FC } from 'react';
import { ChevronDown, LayoutPanelTop, MessageSquare, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { FLOW_MANAGED_NOTIFICATION_EVENTS as FLOW_MANAGED_EVENTS, FLOW_PREVIEW_ONLY_IDS, LINE_MESSAGE_FLOWS, messageStageOrder, type FlowJourneyId } from '../adapters/line_configuration/line_message_flow_adapter';
import { LineMessagePreviewWorkspace } from './LineMessagePreviewWorkspace';
import { LineCardCopyEditor, cardCopyFieldId, type CardCopyField } from './LineCardCopyEditor';
import { lineMessagePreviewClient, type LineMessagePreviewClient, type PreviewDescriptor } from '../api/line_notification_rules/line_message_preview_client';
import {
  adaptLineNotificationRulesCatalog,
  ruleName,
  type LineNotificationRuleModel,
} from '../adapters/line_configuration/line_configuration_query_adapter';
import { lineConfigurationQueryClient, type LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import {
  lineNotificationTemplateClient,
  type LineNotificationTemplateClient,
} from '../api/line_notification_rules/line_notification_template_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import './LineNotificationWorkbench.css';

interface NotificationContent {
  content: string;
  revision: number;
  variables: string[];
  fields?: CardCopyField[];
}

const PAYMENT_REMINDER_MESSAGE_IDS = new Set([
  'deposit-reminder', 'payment-first-reminder', 'payment-first-greeting', 'payment-second-reminder',
  'payment-overdue-deposit', 'payment-overdue-first', 'payment-overdue-second',
  'cancellation-notice-settlement', 'cancellation-notice-refund', 'cancellation-notice-collection',
]);
const CANCELLATION_NOTICE_MESSAGE_IDS = new Set([
  'cancellation-notice-settlement', 'cancellation-notice-refund', 'cancellation-notice-collection',
]);
const RETIRED_MESSAGE_IDS = new Set(['deposit-settled', 'payment-first-settled']);
const RETIRED_TEMPLATE_IDS = new Set([
  'customer_onboarding_welcome', 'new_user_d1', 'new_user_d2', 'new_user_d3',
  'LU96-M4-SAFE-ALERT-CARD-V1', 'LU96-M4-COMPLAINT-HIGH-CARD-V1',
  'LINE-SECOND-PAYMENT-DUE-TEXT-V1', 'LINE-SECOND-PAYMENT-SETTLED-TEXT-V1',
  'LINE-SERVICE-COMPLETION-TEXT-V1', 'LINE-ORDER-SERVICE-START-DAY-CARD-V1',
]);

type SidebarGroup = FlowJourneyId | 'accounting' | 'other';
type SidebarJourney = { id: SidebarGroup; label: string; stages: { label: string; entries: NotificationEntry[] }[] };

const BUILTIN_RECIPIENTS: Record<string, string> = {
  'payment-overdue-deposit': '客戶私人聊天室', 'deposit-reminder': '客戶私人聊天室',
  'payment-overdue-first': '客戶私人聊天室', 'payment-overdue-second': '客戶私人聊天室',
  'payment-first-reminder': '案件服務群組', 'payment-first-greeting': '案件服務群組',
  'cancellation-notice-settlement': '客戶私人聊天室', 'cancellation-notice-refund': '客戶私人聊天室',
  'cancellation-notice-collection': '客戶私人聊天室', 'payment-second-reminder': '客戶私人聊天室',
  'helper-confirm-start-completed': '案件服務群組', 'helper-schedule-unconfirmed': '案件服務群組',
  'helper-postponement-completed': '案件服務群組', 'helper-staff-assistance-ack': '案件服務群組',
  'helper-staff-assistance-closed': '案件服務群組', 'helper-faq-ingredients': '案件服務群組',
  'helper-faq-hours': '案件服務群組', 'helper-faq-subsidy': '案件服務群組', 'helper-satisfaction-survey': '案件服務群組',
  'identity-bound-customer': '客戶私人聊天室', 'identity-bound-staff': '月嫂私人聊天室',
  'identity-bound-admin': '工會人員私人聊天室',
  'card-customer-confirmation': '客戶私人聊天室', 'card-customer-profiles': '客戶私人聊天室',
  'card-candidate-information-package': '候選月嫂私人聊天室',
  'card-candidate-information-1': '候選月嫂私人聊天室', 'card-candidate-information-2': '候選月嫂私人聊天室',
  'card-candidate-information-3': '候選月嫂私人聊天室', 'card-caregiver-information': '正式媒合月嫂私人聊天室',
  'card-caregiver-information-2': '正式媒合月嫂私人聊天室',
  'group-invitation-customer': '客戶私人聊天室', 'group-invitation-staff': '月嫂私人聊天室',
  'helper-menu-card': '案件服務群組', 'helper-menu-completed': '案件服務群組', 'helper-confirm-start-card': '案件服務群組',
  'helper-postponement-card': '案件服務群組', 'helper-guidelines-card': '案件服務群組',
};

interface NotificationEntry {
  id: string;
  name: string;
  recipient: string;
  kind: 'rule' | 'card';
  rule?: LineNotificationRuleModel;
  data: NotificationContent | null;
  error: string | null;
  textEditingUnsupported?: boolean;
}

interface LineNotificationWorkbenchProps {
  configuration?: LineConfigurationQueryClient;
  templates?: LineNotificationTemplateClient;
  previews?: LineMessagePreviewClient;
  search: string;
  onSearchChange(value: string): void;
  selectedEntryId?: string | null;
  onSelectedEntryChange?(id: string | null): void;
  initialCategory?: 'all' | 'accounting';
}

function contentError(error: unknown, saving = false): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '登入已失效，請重新登入後再試。';
    if (error.status === 403) return '目前帳號沒有維護通知內容的權限。';
    if (error.status === 404) return '找不到此通知使用的訊息內容。';
    if (error.status === 409) return '通知內容已變更或目前無法編輯，請重新整理後再試。';
    if (error.status === 422) return '內容不完整，請確認文字與必要變數後再試。';
  }
  return saving ? '通知內容儲存失敗，已保留你的修改，請稍後再試。' : '通知內容讀取失敗，請重新整理後再試。';
}

function readableRuleName(rule: LineNotificationRuleModel): string {
  const name = ruleName(rule.id);
  return name !== rule.id ? name.replace(/^M\d+：/, '') : rule.eventLabel !== rule.eventCode ? rule.eventLabel : '通知內容';
}

export const LineNotificationWorkbench: FC<LineNotificationWorkbenchProps> = ({
  configuration = lineConfigurationQueryClient,
  templates = lineNotificationTemplateClient,
  previews = lineMessagePreviewClient,
  search,
  onSearchChange,
  selectedEntryId,
  onSelectedEntryChange,
  initialCategory = 'all',
}) => {
  const [entries, setEntries] = useState<NotificationEntry[]>([]);
  const sidebarId = useId();
  const [builtinContents, setBuiltinContents] = useState<Record<string, { data: NotificationContent | null; error: string | null }>>({});
  const [descriptors, setDescriptors] = useState<PreviewDescriptor[]>([]);
  const [previewCatalogError, setPreviewCatalogError] = useState(false);
  const [previewCatalogLoading, setPreviewCatalogLoading] = useState(true);
  const [targetUnavailable, setTargetUnavailable] = useState(false);
  const [expandedGroup, setExpandedGroup] = useState<SidebarGroup | null>(initialCategory === 'accounting' ? 'accounting' : 'matching');
  const [expandedStage, setExpandedStage] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<NotificationEntry | null>(null);
  const [content, setContent] = useState('');
  const saveValidation = useSaveValidation();
  const saveFieldRef = useValidationRef<HTMLTextAreaElement>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const generation = useRef(0);
  const saveController = useRef<AbortController | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const sidebarHeading = useRef<HTMLHeadingElement | null>(null);
  const editorHeading = useRef<HTMLHeadingElement | null>(null);
  const focusAfterReload = useRef<string | null>(null);
  const contentDirty = selected?.data !== null && selected !== null && content !== selected.data.content;
  useUnsavedDraft(selected?.name ?? '通知內容', { '通知內容': content }, { baseline: { '通知內容': selected?.data?.content ?? '' }, enabled: !!selected && !!selected.data, busy: saving, save: contentDirty ? () => save() : undefined });

  useEffect(() => {
    const controller = new AbortController();
    setDescriptors([]); setPreviewCatalogError(false); setPreviewCatalogLoading(true);
    void previews.catalog({ signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) {
        const scoped = value.filter(item =>
          !RETIRED_MESSAGE_IDS.has(item.id)
          && !(item.template_id && RETIRED_TEMPLATE_IDS.has(item.template_id)),
        );
        setDescriptors(scoped); setPreviewCatalogLoading(false);
      }
    }).catch(() => { if (!controller.signal.aborted) { setPreviewCatalogError(true); setPreviewCatalogLoading(false); } });
    return () => controller.abort();
  }, [previews, reload]);

  useEffect(() => {
    const controller = new AbortController();
    const request = ++generation.current;
    setLoading(true);
    setCatalogError(null);
    setEntries([]);
    void configuration.getNotificationRules({ signal: controller.signal }).then(async (snapshot) => {
      if (controller.signal.aborted || generation.current !== request) return;
      const rules = adaptLineNotificationRulesCatalog(snapshot).rules.filter(rule =>
        rule.eventCode !== 'order.service_completed' && !RETIRED_TEMPLATE_IDS.has(rule.templateId),
      );
      const contents = await Promise.allSettled(rules.map(rule => templates.get(rule.id, { signal: controller.signal })));
      if (controller.signal.aborted || generation.current !== request) return;
      setEntries(rules.map((rule, index): NotificationEntry => {
        const result = contents[index];
        return {
          id: rule.id,
          name: result.status === 'fulfilled' && result.value.name && !/^Task96\b/.test(result.value.name) ? result.value.name : readableRuleName(rule),
          recipient: rule.recipientLabel,
          kind: 'rule', rule,
          data: result.status === 'fulfilled' ? result.value : null,
          error: result.status === 'rejected' ? contentError(result.reason) : null,
          // This GET returns 409 when a structured template has no text editor.
          textEditingUnsupported: result.status === 'rejected' && result.reason instanceof ApiHttpError && result.reason.status === 409,
        };
      }));
      setLoading(false);
    }).catch(() => {
      if (controller.signal.aborted || generation.current !== request) return;
      setCatalogError('通知清單讀取失敗，請重新整理。');
      setEntries([]);
      setLoading(false);
    });
    return () => controller.abort();
  }, [configuration, templates, reload]);

  useEffect(() => () => { saveController.current?.abort(); }, []);

  useEffect(() => { setBuiltinContents({}); }, [reload]);

  useEffect(() => {
    if (!selected || selected.kind !== 'card' || selected.id === 'card-candidate-information-3'
      || FLOW_PREVIEW_ONLY_IDS.has(selected.id) || builtinContents[selected.id]) return;
    const controller = new AbortController();
    const id = selected.id;
    void templates.get(id, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setBuiltinContents(current => ({ ...current, [id]: { data, error: null } }));
    }).catch(error => {
      if (!controller.signal.aborted) setBuiltinContents(current => ({ ...current, [id]: { data: null, error: contentError(error) } }));
    });
    return () => controller.abort();
  }, [selected?.id, templates, reload, builtinContents]);

  useEffect(() => {
    if (!selected || selected.kind !== 'card' || !builtinContents[selected.id]) return;
    const loaded = builtinContents[selected.id];
    if (selected.data === loaded.data && selected.error === loaded.error) return;
    setSelected({ ...selected, ...loaded });
    if (loaded.data) setContent(loaded.data.content);
  }, [builtinContents, selected?.id]);

  useEffect(() => {
    if (loading || focusAfterReload.current === null) return;
    const id = focusAfterReload.current;
    focusAfterReload.current = null;
    Array.from(document.querySelectorAll<HTMLButtonElement>(`[data-notification-id="${CSS.escape(id)}"]`))
      .find(button => !button.closest('[hidden]'))?.focus();
  }, [entries, loading]);

  useEffect(() => {
    if (!contentDirty) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [contentDirty]);

  const { requestLeave } = useUnsavedNavigation();
  const clearEditor = () => {
    setSelected(null);
    onSelectedEntryChange?.(null);
    setSaveError(null);
    setTargetUnavailable(false);
  };
  const close = () => {
    if (saving) return;
    requestLeave(() => {
      clearEditor();
      window.requestAnimationFrame(() => {
        const previous = opener.current;
        if (previous?.isConnected && !previous.closest('[hidden]')) previous.focus();
        else sidebarHeading.current?.focus();
      });
    });
  };
  const refresh = () => requestLeave(() => {
    clearEditor();
    setNotice(null);
    setReload(value => value + 1);
  });

  const open = (entry: NotificationEntry, button: HTMLButtonElement) => {
    if (saving || entry.id === selected?.id) return;
    requestLeave(() => {
      opener.current = button;
      setSelected(entry);
      onSelectedEntryChange?.(entry.id);
      setTargetUnavailable(false);
      setContent(entry.data?.content ?? '');
      setSaveError(null);
      setNotice(null);
      window.requestAnimationFrame(() => editorHeading.current?.focus());
    });
  };

  const save = async () => {
    if (!selected?.data || !contentDirty || saving) return;
    if (!saveValidation.validate([{ value: content, label: '通知內容', ref: saveFieldRef }])) return;
    if (selected.data.fields?.length) {
      const values = JSON.parse(content) as Record<string, string>;
      const invalid = selected.data.fields.find(field => (!field.optional && !values[field.id]?.trim()) || (values[field.id]?.length ?? 0) > field.max_length);
      if (invalid) {
        window.requestAnimationFrame(() => {
          const element = document.getElementById(cardCopyFieldId(invalid.id));
          const details = element?.closest('details');
          if (details) details.open = true;
          element?.focus();
        });
        setSaveError('請填寫完整文案，並確認各欄位的字數限制。');
        return;
      }
    }
    const target = selected;
    const controller = new AbortController();
    saveController.current = controller;
    setSaving(true);
    setSaveError(null);
    try {
      const payload = { content, expected_revision: target.data!.revision };
      await templates.update(target.id, payload, { signal: controller.signal });
      if (controller.signal.aborted) return;
      // MESSAGE_TEMPLATES revision is shared. Invalidate it by reading all entries again.
      setSelected(null);
      onSelectedEntryChange?.(null);
      focusAfterReload.current = target.id;
      setReload(value => value + 1);
      setNotice('通知內容已儲存。');
    } catch (error) {
      if (!controller.signal.aborted) setSaveError(contentError(error, true));
    } finally {
      if (!controller.signal.aborted) setSaving(false);
    }
  };

  const allEntries: NotificationEntry[] = [...entries, ...descriptors.filter(item => item.builtin).map(item => ({
    id: item.id, name: item.name, recipient: BUILTIN_RECIPIENTS[item.id] ?? '依正式流程對象', kind: 'card' as const, data: builtinContents[item.id]?.data ?? null, error: builtinContents[item.id]?.error ?? null,
  }))];
  // Parent navigation has already passed the shared unsaved-draft guard.
  // Wait for both queries: a builtin target may arrive after the rules list.
  useEffect(() => {
    if (!selectedEntryId || loading || previewCatalogLoading) return;
    const resolvedId = ({ 'template-bind_success_new_order': 'identity-bound-customer', 'template-staff_switch_success': 'identity-bound-staff',
      'service-other': 'service-menu',
      'card-caregiver-information': 'card-customer-confirmation', 'card-caregiver-information-2': 'card-customer-confirmation', 'card-customer-profiles': 'card-customer-confirmation',
    } as Record<string, string>)[selectedEntryId] ?? selectedEntryId;
    const entry = allEntries.find(item => item.id === resolvedId);
    setTargetUnavailable(!entry);
    if (!entry) { setSelected(null); return; }
    if (resolvedId !== selectedEntryId) onSelectedEntryChange?.(resolvedId);
    if (selected?.id === entry.id && selected.data === entry.data) return;
    setSelected(entry);
    setContent(entry.data?.content ?? '');
    setSaveError(null);
    onSearchChange('');
  }, [selectedEntryId, entries, descriptors, builtinContents, loading, previewCatalogLoading]);

  const query = search.trim().toLowerCase();
  const formatOf = (entry: NotificationEntry) => descriptors.find(item => item.id === entry.id)?.format ?? 'text';
  const identities = allEntries.map(entry => ({ entry, id: entry.id,
    template_id: descriptors.find(item => item.id === entry.id)?.template_id ?? entry.rule?.templateId ?? null }));
  const assignedIds = new Set<string>();
  const sidebar: SidebarJourney[] = LINE_MESSAGE_FLOWS.map(flow => ({ id: flow.id, label: flow.name,
    stages: flow.stages.map(stage => ({ label: stage.title, entries: identities
      .map(identity => ({ entry: identity.entry, order: messageStageOrder(stage, identity) }))
      .filter(item => item.order >= 0)
      .sort((left, right) => left.order - right.order)
      .map(({ entry }) => { assignedIds.add(entry.id); return entry; }),
    })),
  }));
  const otherEntries = allEntries.filter(entry => !assignedIds.has(entry.id));
  if (otherEntries.length) sidebar.push({ id: 'other', label: '其他通知', stages: [{ label: '未歸入流程', entries: otherEntries }] });
  if (initialCategory === 'accounting') sidebar.push({ id: 'accounting', label: '帳務', stages: [{ label: '帳務範本', entries: allEntries.filter(entry => PAYMENT_REMINDER_MESSAGE_IDS.has(entry.id)) }] });

  const selectedJourney = selected && sidebar.find(group => group.stages.some(stage => stage.entries.some(entry => entry.id === selected.id)));
  const selectedGroup = selectedJourney ? selectedJourney.id : null;
  const selectedStage = selectedJourney && selected ? selectedJourney.stages.findIndex(stage => stage.entries.some(entry => entry.id === selected.id)) : null;
  useEffect(() => {
    if (selectedGroup === null) return;
    setExpandedGroup(selectedGroup);
    setExpandedStage(selectedStage);
  }, [selected?.id, selectedGroup, selectedStage]);
  const matchesSearch = (entry: NotificationEntry) => !query || `${entry.name} ${entry.data?.content ?? ''}`.toLowerCase().includes(query);
  const sidebarLoading = loading || (previewCatalogLoading && entries.length === 0);
  const fields = selected?.data?.fields ?? [];
  const managed = selected?.rule ? FLOW_MANAGED_EVENTS.has(selected.rule.eventCode) : false;
  const descriptor = descriptors.find(item => item.id === selected?.id);
  const automaticImage = selected?.id === 'card-candidate-information-3';
  const previewOnly = selected ? FLOW_PREVIEW_ONLY_IDS.has(selected.id) : false;
  const helperMenuAlternative = selected?.id === 'helper-menu-card' ? allEntries.find(entry => entry.id === 'helper-menu-completed') :
    selected?.id === 'helper-menu-completed' ? allEntries.find(entry => entry.id === 'helper-menu-card') : undefined;
  const contentLoading = selected?.kind === 'card' && !automaticImage && !previewOnly && !builtinContents[selected.id];
  const confirmationFlows = ['card-customer-confirmation', 'card-candidate-information-package', 'card-candidate-information-1', 'card-candidate-information-2'].includes(selected?.id ?? '') ? [
    { id: 'card-customer-confirmation', label: '正式媒合 · 客戶確認' },
    { id: selected?.id === 'card-candidate-information-1' || selected?.id === 'card-candidate-information-2' ? selected.id : 'card-candidate-information-package', label: '初步候選 · 月嫂承接' },
  ] : [];
  return (
    <section className="notification-workspace" aria-label="通知內容設定">
      <div className="notification-page-heading">
        <div><h2>通知與發送</h2><p>依流程選擇訊息，編輯內容並即時預覽。</p></div>
        <div className="notification-heading-actions"><span className="notification-safe-badge"><ShieldCheck />預覽不會實際發送</span><button type="button" className="notification-button" disabled={loading || saving} onClick={refresh}><RefreshCw aria-hidden="true" />重新整理</button></div>
      </div>
      {notice && <p className="notification-feedback" role="status">{notice}</p>}
      {catalogError && <p className="notification-feedback error" role="alert">{catalogError}</p>}
      {previewCatalogError && <p className="notification-feedback error" role="alert">訊息卡片與預覽來源讀取失敗，請重新整理；既有通知內容仍可維護。</p>}
      {targetUnavailable && <p className="notification-feedback error" role="alert">找不到指定訊息，請重新整理或從左側流程圖選擇。</p>}
      <div className="notification-unified-layout">
        <section className="notification-message-library" aria-label="LINE 流程圖">
          <h3 ref={sidebarHeading} tabIndex={-1} className="notification-sidebar-heading">LINE 流程圖</h3>
          <label className="notification-search"><span className="sr-only">搜尋通知名稱或內容</span><Search aria-hidden="true" /><input type="search" value={search} maxLength={100} placeholder="搜尋訊息名稱或內容" onChange={event => onSearchChange(event.target.value)} /></label>
          {sidebarLoading ? <p className="notification-feedback" role="status">正在載入通知內容…</p>
            : query && !allEntries.some(matchesSearch) ? <p className="notification-help" role="status">沒有符合條件的通知</p>
            : <div className="notification-sidebar-journeys">{sidebar.map(group => {
              if (query && !group.stages.some(stage => stage.entries.some(matchesSearch))) return null;
              const groupOpen = Boolean(query) || expandedGroup === group.id;
              const groupId = `${sidebarId}-${group.id}`;
              return <div key={group.id} className="notification-sidebar-journey">
                <button type="button" className="notification-sidebar-group" aria-current={selectedGroup === group.id ? 'true' : undefined} aria-expanded={groupOpen} aria-controls={groupId} disabled={Boolean(query)} onClick={() => {
                  setExpandedGroup(groupOpen ? null : group.id);
                  setExpandedStage(group.id === selectedGroup ? selectedStage : null);
                }}>{group.label}<ChevronDown size={16} aria-hidden="true" /></button>
                <ol id={groupId} hidden={!groupOpen} className="notification-sidebar-steps">{group.stages.map((stage, index) => {
                  const stageEntries = stage.entries.filter(matchesSearch);
                  if (query && !stageEntries.length) return null;
                  const stageOpen = Boolean(query) || (groupOpen && expandedStage === index);
                  const stageId = `${groupId}-${index}`;
                  return <li key={stage.label} className="notification-sidebar-step">
                    <button type="button" className="notification-sidebar-stage" aria-current={selectedGroup === group.id && selectedStage === index ? 'step' : undefined} aria-expanded={stageOpen} aria-controls={stageId} disabled={Boolean(query)} onClick={() => setExpandedStage(stageOpen ? null : index)}>
                      <span className="notification-sidebar-step-number" aria-hidden="true">{index + 1}</span><span>{stage.label}</span><ChevronDown size={13} aria-hidden="true" />
                    </button>
                    <div id={stageId} hidden={!stageOpen} className="notification-sidebar-messages">
                      {!stageEntries.length && <p className="notification-help">此步驟目前無訊息範本</p>}
                      {stageEntries.map(entry => <button type="button" key={entry.id} className="notification-message-item" aria-pressed={selected?.id === entry.id} data-notification-id={entry.id} aria-label={`${entry.data ? '編輯' : '查看'}${entry.name}內容`} disabled={saving} onClick={event => open(entry, event.currentTarget)}>
                        <span className="notification-message-icon" aria-hidden="true">{formatOf(entry) === 'flex' ? <LayoutPanelTop /> : <MessageSquare />}</span>
                        <span><strong>{entry.name}</strong>{(CANCELLATION_NOTICE_MESSAGE_IDS.has(entry.id) || (entry.rule?.enabled === false && !FLOW_MANAGED_EVENTS.has(entry.rule.eventCode))) && <small>{CANCELLATION_NOTICE_MESSAGE_IDS.has(entry.id) ? '人工發送' : '已停用'}</small>}</span>
                      </button>)}
                    </div>
                  </li>;
                })}</ol>
              </div>;
            })}</div>}
        </section>
        {selected ? <LineMessagePreviewWorkspace key={selected.id} descriptor={descriptor} entryId={selected.id} content={selected.data ? content : undefined} client={previews}
          editor={<>
            <div className="notification-inline-title"><span>{formatOf(selected) === 'flex' ? '互動卡片' : '純文字'}</span><h3 ref={editorHeading} tabIndex={-1}>{selected.name}</h3><p>{selected.recipient}</p></div>
            {helperMenuAlternative && <button type="button" className="notification-text-button" disabled={saving} onClick={event => open(helperMenuAlternative, event.currentTarget)}>{previewOnly ? '返回小幫手選單文案' : '查看完工後選單公版'}</button>}
            {selected.error && !(selected.textEditingUnsupported && formatOf(selected) === 'flex') && <p className="notification-feedback error" role="alert">{selected.error}</p>}
            {selected.textEditingUnsupported && formatOf(selected) === 'flex' && <p className="notification-help">此卡片使用結構化內容，請查看手機預覽。</p>}
            {selected.id === 'card-candidate-information-package' && <p className="notification-help">表格圖片由系統資料自動產生。這裡可編輯最後一張卡片的文案。</p>}
            {['card-customer-confirmation', 'card-candidate-information-1', 'card-candidate-information-2'].includes(selected.id) && <p className="notification-help">表格圖片由系統資料自動產生。這裡可編輯最後一張卡片的文案與按鈕名稱。</p>}
            {automaticImage && <p className="notification-help">每週服務安排圖片由系統資料自動產生，無需編輯文案。</p>}
            {['helper-menu-card', 'helper-staff-assistance-closed'].includes(selected.id) && (
              <div className="notification-help" role="note">
                {selected.id === 'helper-menu-card'
                  ? '若要調整在群組輸入哪些關鍵字喚醒此選單（預設「小幫手」、「工會」），'
                  : '若要調整專員結案時可使用的觸發指令（預設「已處理結案」），'}
                請前往{' '}
                <a href="#line-interface?tab=guidance">
                  LINE 介面設定 → 引導動作
                </a>
                {' '}維護觸發指令。
              </div>
            )}
            {confirmationFlows.length > 0 && <nav className="notification-card-flow-tabs" aria-label="確認卡流程">{confirmationFlows.map(flow => {
              const entry = allEntries.find(item => item.id === flow.id);
              return entry && <button key={flow.id} type="button" aria-pressed={selected.id === flow.id} disabled={saving} onClick={event => open(entry, event.currentTarget)}>{flow.label}</button>;
            })}<span>不同流程的文案各自儲存</span></nav>}
            {contentLoading && <p className="notification-feedback" role="status">正在載入訊息內容…</p>}{selected.data && !contentLoading ? <>{fields.length > 0 ? <LineCardCopyEditor fields={fields} content={content} variables={selected.data.variables} disabled={saving} bodyRef={saveFieldRef} onChange={value => { setContent(value); setSaveError(null); }} /> : <label className="notification-content-field" htmlFor="notification-message-content">{managed ? '通知說明文字' : '通知內容'}<textarea ref={saveFieldRef} aria-required="true" id="notification-message-content" rows={16} value={content} maxLength={5000} disabled={saving} onChange={event => { setContent(event.target.value); setSaveError(null); }} /></label>}{saveValidation.feedback}
              {managed && <p className="notification-help">說明文字會用於新建立的通知。系統會自動帶入案件資料與互動按鈕。</p>}
              {fields.length === 0 && selected.data.variables.length > 0 && <p className="notification-help">系統會帶入這些變數的值 {selected.data.variables.map(variable => <code key={variable}>{`{${variable}}`}</code>)}</p>}
              {CANCELLATION_NOTICE_MESSAGE_IDS.has(selected.id) && <p className="notification-help">取消結算相關通知由工會人員於案件取消時在帳務頁手動預覽發送，系統於帳務結算時不會自動推播。</p>}
            </> : selected.kind === 'card' && !contentLoading && !selected.error && <p className="notification-help">這則訊息僅供預覽。</p>}
            {saveError && <p className="notification-feedback error" role="alert">{saveError}</p>}
          </>}
          footer={<><button type="button" className="notification-button" disabled={saving} onClick={close}>取消</button>{selected.data && <><button type="button" className="notification-text-button" disabled={saving || !contentDirty} onClick={() => { setContent(selected.data!.content); setSaveError(null); }}>還原內容</button><button type="button" className="notification-button primary" disabled={saving || !contentDirty} onClick={() => void save()}>{saving ? '儲存中…' : '儲存內容'}</button></>}</>}
        /> : <div className="notification-editor-placeholder"><MessageSquare /><h3>從左側選擇訊息</h3></div>}
      </div>
    </section>
  );
};
