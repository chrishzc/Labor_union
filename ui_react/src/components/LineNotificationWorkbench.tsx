import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import { useRef as useValidationRef } from 'react';
import { useSaveValidation } from './useSaveValidation';
/**
 * File: LineNotificationWorkbench.tsx
 * Description: 統一歡迎訊息與通知內容維護，沿用版本化儲存及既有規則影響確認。
 */
import { useCallback, useEffect, useRef, useState, type FC } from 'react';
import { ArrowLeft, LayoutPanelTop, MessageSquare, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { FLOW_MANAGED_NOTIFICATION_EVENTS as FLOW_MANAGED_EVENTS } from '../adapters/line_configuration/line_message_flow_adapter';
import { LineMessagePreviewWorkspace } from './LineMessagePreviewWorkspace';
import { lineMessagePreviewClient, type LineMessagePreviewClient, type PreviewDescriptor } from '../api/line_notification_rules/line_message_preview_client';
import { LineNotificationRulesMutationPanel } from './LineNotificationRulesMutationPanel';
import {
  adaptLineNotificationRulesCatalog,
  ruleName,
  type LineNotificationRuleModel,
} from '../adapters/line_configuration/line_configuration_query_adapter';
import { lineConfigurationQueryClient, type LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import type { LineNotificationRulesCatalog } from '../api/line_configuration/line_configuration_query_schemas';
import { lineOnboardingClient, type LineOnboardingClient } from '../api/line_onboarding/line_onboarding_client';
import {
  lineNotificationTemplateClient,
  type LineNotificationTemplateClient,
} from '../api/line_notification_rules/line_notification_template_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import './LineNotificationWorkbench.css';

const MANUAL_FLOW_DETAILS: Record<string, { recipient: string; trigger: string }> = {
  'contract-signing-client': { recipient: '客戶私人聊天室', trigger: '人員點「發送簽署提醒」後建立工作，無再次確認視窗' },
  'contract-signing-staff': { recipient: '月嫂私人聊天室', trigger: '人員點「發送簽署提醒」後建立工作，無再次確認視窗' },
  'payment-overdue-deposit': { recipient: '客戶私人聊天室', trigger: '訂金逾期隔天列待辦，由工會點「發送提醒」才建立工作' },
  'payment-overdue-first': { recipient: '案件群組', trigger: '第一期款逾期隔天列待辦，由工會點「發送提醒」才建立工作' },
  'payment-overdue-second': { recipient: '案件群組', trigger: '有第二期款且逾期未清才列待辦，由工會點「發送提醒」才建立工作' },
  'service-day-log-reminder': { recipient: '案件群組', trigger: '由工會逐次決定，點「發送提醒」後建立寄送工作' },
};

interface NotificationContent {
  content: string;
  revision: number;
  variables: string[];
}

interface NotificationEntry {
  id: string;
  name: string;
  recipient: string;
  kind: 'welcome' | 'rule' | 'card';
  rule?: LineNotificationRuleModel;
  data: NotificationContent | null;
  error: string | null;
  textEditingUnsupported?: boolean;
}

interface LineNotificationWorkbenchProps {
  configuration?: LineConfigurationQueryClient;
  onboarding?: LineOnboardingClient;
  templates?: LineNotificationTemplateClient;
  previews?: LineMessagePreviewClient;
  search: string;
  enabled: 'all' | 'enabled' | 'disabled';
  onSearchChange(value: string): void;
  onEnabledChange(value: 'all' | 'enabled' | 'disabled'): void;
  selectedEntryId?: string | null;
  onSelectedEntryChange?(id: string | null): void;
  onReturnToFlow?(): void;
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
  onboarding = lineOnboardingClient,
  templates = lineNotificationTemplateClient,
  previews = lineMessagePreviewClient,
  search,
  enabled,
  onSearchChange,
  onEnabledChange,
  selectedEntryId,
  onSelectedEntryChange,
  onReturnToFlow,
}) => {
  const [entries, setEntries] = useState<NotificationEntry[]>([]);
  const [descriptors, setDescriptors] = useState<PreviewDescriptor[]>([]);
  const [previewCatalogError, setPreviewCatalogError] = useState(false);
  const [previewCatalogLoading, setPreviewCatalogLoading] = useState(true);
  const [targetUnavailable, setTargetUnavailable] = useState(false);
  const [formatFilter, setFormatFilter] = useState<'all' | 'text' | 'flex'>('all');
  const [deliveryTab, setDeliveryTab] = useState(false);
  const [catalog, setCatalog] = useState<LineNotificationRulesCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<NotificationEntry | null>(null);
  const [content, setContent] = useState('');
  const saveValidation = useSaveValidation();
  const saveFieldRef = useValidationRef<HTMLTextAreaElement>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [editingSettings, setEditingSettings] = useState(false);
  const [settingsDirty, setSettingsDirty] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const generation = useRef(0);
  const saveController = useRef<AbortController | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const focusAfterReload = useRef<string | null>(null);
  const contentDirty = selected?.data !== null && selected !== null && content !== selected.data.content;
  const dirty = contentDirty || settingsDirty;
  const updating = saving || settingsBusy;
  useUnsavedDraft(selected?.name ?? '通知內容', { '通知內容': content }, { baseline: { '通知內容': selected?.data?.content ?? '' }, enabled: !!selected && !!selected.data, busy: updating, save: contentDirty ? () => save() : undefined });
  const settingsState = useCallback((changed: boolean, busy: boolean) => { setSettingsDirty(changed); setSettingsBusy(busy); }, []);

  useEffect(() => {
    const controller = new AbortController();
    setDescriptors([]); setPreviewCatalogError(false); setPreviewCatalogLoading(true);
    void previews.catalog({ signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) { setDescriptors(value); setPreviewCatalogLoading(false); }
    }).catch(() => { if (!controller.signal.aborted) { setPreviewCatalogError(true); setPreviewCatalogLoading(false); } });
    return () => controller.abort();
  }, [previews, reload]);

  useEffect(() => {
    const controller = new AbortController();
    const request = ++generation.current;
    setLoading(true);
    setCatalogError(null);
    setEntries([]);
    setCatalog(null);
    void Promise.allSettled([
      configuration.getNotificationRules({ signal: controller.signal }),
      onboarding.get({ signal: controller.signal }),
    ]).then(async ([rulesResult, welcomeResult]) => {
      if (controller.signal.aborted || generation.current !== request) return;
      const welcome: NotificationEntry = {
        id: 'welcome', name: '新好友歡迎訊息', recipient: '新加入的好友', kind: 'welcome',
        data: welcomeResult.status === 'fulfilled' ? welcomeResult.value : null,
        error: welcomeResult.status === 'rejected' ? contentError(welcomeResult.reason) : null,
      };
      if (rulesResult.status === 'rejected') {
        setCatalogError('通知清單讀取失敗，請重新整理。');
        setEntries([welcome]);
        setLoading(false);
        return;
      }
      const snapshot = rulesResult.value;
      const rules = adaptLineNotificationRulesCatalog(snapshot).rules.filter(rule => !['customer_onboarding_welcome', 'new_user_d1', 'new_user_d2', 'new_user_d3'].includes(rule.templateId));
      const contents = await Promise.allSettled(rules.map(rule => templates.get(rule.id, { signal: controller.signal })));
      if (controller.signal.aborted || generation.current !== request) return;
      setCatalog(snapshot);
      setEntries([welcome, ...rules.map((rule, index): NotificationEntry => {
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
      })]);
      setLoading(false);
    });
    return () => controller.abort();
  }, [configuration, onboarding, templates, reload]);

  useEffect(() => () => { saveController.current?.abort(); }, []);

  useEffect(() => {
    if (loading || focusAfterReload.current === null) return;
    const id = focusAfterReload.current;
    focusAfterReload.current = null;
    document.querySelector<HTMLButtonElement>(`[data-notification-id="${CSS.escape(id)}"]`)?.focus();
  }, [entries, loading]);

  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty]);

  const { requestLeave } = useUnsavedNavigation();
  const close = () => {
    if (updating) return;
    requestLeave(() => {
    setSelected(null);
    onSelectedEntryChange?.(null);
    setEditingSettings(false);
    setSettingsDirty(false);
    setSaveError(null);
    window.requestAnimationFrame(() => opener.current?.focus());
    });
  };

  const open = (entry: NotificationEntry, button: HTMLButtonElement) => {
    if (updating) return;
    requestLeave(() => {
    opener.current = button;
    setSelected(entry);
    onSelectedEntryChange?.(entry.id);
    setTargetUnavailable(false);
    setContent(entry.data?.content ?? (descriptors.find(item => item.id === entry.id)?.allows_draft ? '請協助確認本次服務時段，謝謝。' : ''));
    setSaveError(null);
    setEditingSettings(false);
    setSettingsDirty(false);
    setNotice(null);
    setDeliveryTab(false);
    });
  };

  const save = async () => {
    if (!selected?.data || !dirty || saving) return;
    if (!saveValidation.validate([{ value: content, label: '通知內容', ref: saveFieldRef }])) return;
    const target = selected;
    const controller = new AbortController();
    saveController.current = controller;
    setSaving(true);
    setSaveError(null);
    try {
      const payload = { content, expected_revision: target.data!.revision };
      await (target.kind === 'welcome'
        ? onboarding.update(payload, { signal: controller.signal })
        : templates.update(target.id, payload, { signal: controller.signal }));
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
    id: item.id, name: item.name, recipient: MANUAL_FLOW_DETAILS[item.id]?.recipient ?? (item.requires_case || item.requires_staff ? '公版案件與月嫂範例' : '依正式流程對象'), kind: 'card' as const, data: null, error: null,
  }))];
  // Parent navigation has already passed the shared unsaved-draft guard.
  // Wait for both queries: a builtin target may arrive after the rules list.
  useEffect(() => {
    if (!selectedEntryId || loading || previewCatalogLoading) return;
    const entry = allEntries.find(item => item.id === selectedEntryId);
    setTargetUnavailable(!entry);
    if (!entry) { setSelected(null); return; }
    if (selected?.id === entry.id) return;
    setSelected(entry);
    setContent(entry.data?.content ?? (descriptors.find(item => item.id === entry.id)?.allows_draft ? '請協助確認本次服務時段，謝謝。' : ''));
    setDeliveryTab(false); setEditingSettings(false); setSettingsDirty(false); setSaveError(null);
    setFormatFilter('all'); onSearchChange(''); onEnabledChange('all');
  }, [selectedEntryId, entries, descriptors, loading, previewCatalogLoading]);

  useEffect(() => {
    if (!selected) return;
    document.querySelector<HTMLButtonElement>(`[data-notification-id="${CSS.escape(selected.id)}"]`)?.scrollIntoView?.({ block: 'nearest' });
  }, [selected?.id]);
  const query = search.trim().toLowerCase();
  const formatOf = (entry: NotificationEntry) => descriptors.find(item => item.id === entry.id)?.format ?? 'text';
  const visible = allEntries.filter(entry => (!query || `${entry.name} ${entry.data?.content ?? ''}`.toLowerCase().includes(query))
    && (formatFilter === 'all' || formatOf(entry) === formatFilter)
    && (enabled === 'all' || !MANUAL_FLOW_DETAILS[entry.id] && (!entry.rule || !FLOW_MANAGED_EVENTS.has(entry.rule.eventCode)) && (entry.rule?.enabled ?? true) === (enabled === 'enabled')));
  const managed = selected?.rule ? FLOW_MANAGED_EVENTS.has(selected.rule.eventCode) : false;
  const manualFlow = selected ? MANUAL_FLOW_DETAILS[selected.id] : undefined;
  const descriptor = descriptors.find(item => item.id === selected?.id);

  return (
    <section className="notification-workspace" aria-label="通知內容設定">
      {onReturnToFlow && selectedEntryId && <button type="button" className="notification-text-button" disabled={updating} onClick={() => requestLeave(onReturnToFlow)}><ArrowLeft aria-hidden="true" />返回 LINE 流程圖</button>}
      <div className="notification-page-heading">
        <div><h2>通知與發送</h2><p>從通知文案到互動卡片，使用公版範例預覽，清楚查看每個帶入欄位與值。</p></div>
        <div className="notification-heading-actions"><span className="notification-safe-badge"><ShieldCheck />預覽不會實際發送</span><button type="button" className="notification-button" disabled={loading || updating} onClick={() => requestLeave(() => { setSelected(null); setNotice(null); setReload(value => value + 1); })}><RefreshCw aria-hidden="true" />重新整理</button></div>
      </div>
      {notice && <p className="notification-feedback" role="status">{notice}</p>}
      {catalogError && <p className="notification-feedback error" role="alert">{catalogError}</p>}
      {previewCatalogError && <p className="notification-feedback error" role="alert">訊息卡片與預覽來源讀取失敗，請重新整理；既有通知內容仍可維護。</p>}
      {targetUnavailable && <p className="notification-feedback error" role="alert">找不到指定訊息，可能已停用該來源或不再提供，請重新整理或返回流程圖選擇。</p>}
      <div className="notification-unified-layout">
        <section className="notification-message-library" aria-label="訊息清單">
          <div className="notification-library-title"><h3>所有訊息</h3><span>{visible.length} 則</span></div>
          <label className="notification-search"><span className="sr-only">搜尋通知名稱或內容</span><Search aria-hidden="true" /><input type="search" value={search} maxLength={100} placeholder="搜尋訊息名稱或內容" onChange={event => onSearchChange(event.target.value)} /></label>
          <div className="notification-format-filter" aria-label="訊息格式篩選">{([['all', '全部'], ['text', '純文字'], ['flex', '訊息卡片']] as const).map(([key, label]) => <button key={key} type="button" aria-pressed={formatFilter === key} onClick={() => setFormatFilter(key)}>{label}</button>)}</div>
          <select aria-label="啟用狀態" value={enabled} onChange={event => onEnabledChange(event.target.value as typeof enabled)}><option value="all">全部狀態</option><option value="enabled">已啟用</option><option value="disabled">已停用</option></select>
          <div className="notification-message-items">
            {loading ? <p className="notification-feedback" role="status">正在載入通知內容…</p> : visible.length === 0 ? <div className="notification-empty"><h3>沒有符合條件的通知</h3><button type="button" className="notification-button" onClick={() => { onSearchChange(''); onEnabledChange('all'); setFormatFilter('all'); }}>清除條件</button></div> : visible.map(entry => <button type="button" key={entry.id} className="notification-message-item" aria-pressed={selected?.id === entry.id} data-notification-id={entry.id} aria-label={`${entry.data ? '編輯' : '查看'}${entry.name}內容`} disabled={updating} onClick={event => open(entry, event.currentTarget)}>
              <span className="notification-message-icon">{formatOf(entry) === 'flex' ? <LayoutPanelTop /> : <MessageSquare />}</span><span><strong>{entry.name}</strong><small>{entry.recipient}・{formatOf(entry) === 'flex' ? '訊息卡片' : '純文字'}{entry.rule?.enabled === false && !FLOW_MANAGED_EVENTS.has(entry.rule.eventCode) ? '・已停用' : ''}</small></span>
            </button>)}
          </div>
          <p className="notification-library-note">資料只用於查看訊息效果，不會建立投遞任務。</p>
        </section>
        {selected ? <LineMessagePreviewWorkspace key={selected.id} descriptor={descriptor} entryId={selected.id} content={selected.data || descriptor?.allows_draft ? content : undefined} client={previews} showSources={!editingSettings && !deliveryTab}
          editor={<>
            <div className="notification-inline-title"><span>{formatOf(selected) === 'flex' ? '互動卡片' : '純文字'}</span><h3>{selected.name}</h3><p>{selected.recipient}</p></div>
            <nav className="notification-editor-tabs" aria-label="訊息內容與發送設定"><button type="button" aria-pressed={!deliveryTab} disabled={updating} onClick={() => requestLeave(() => { setDeliveryTab(false); setEditingSettings(false); setSettingsDirty(false); })}>內容與測試</button><button type="button" aria-pressed={deliveryTab} disabled={updating} onClick={() => requestLeave(() => { setDeliveryTab(true); setEditingSettings(false); setSettingsDirty(false); })}>發送設定</button></nav>
            {editingSettings && catalog ? <LineNotificationRulesMutationPanel catalog={catalog} selectedRuleId={selected.id} settingsOnly onEditingStateChange={settingsState} onCommitted={() => { setSelected(null); onSelectedEntryChange?.(null); setSettingsDirty(false); setReload(value => value + 1); }} /> : deliveryTab ? <section className="notification-delivery-settings" aria-label="發送設定">
              <dl><div><dt>通知對象</dt><dd>{selected.recipient}</dd></div><div><dt>發送時機</dt><dd>{manualFlow ? manualFlow.trigger : selected.kind === 'welcome' ? '加入或重新加入好友時' : managed || selected.kind === 'card' ? '由正式業務流程觸發' : selected.rule?.scheduleLabel}</dd></div>{manualFlow && <div><dt>狀態</dt><dd>由流程控制</dd></div>}{selected.rule && !managed && <><div><dt>狀態</dt><dd>{selected.rule.enabled ? '已啟用' : '已停用'}</dd></div><div><dt>頻率</dt><dd>{selected.rule.frequencyLabel}</dd></div></>}</dl>
              {selected.rule && !managed && <button type="button" className="notification-text-button" disabled={dirty || saving} onClick={() => setEditingSettings(true)}>修改發送設定</button>}
              {(managed || !selected.rule) && <p className="notification-help">由業務流程控制，沒有獨立啟用開關。</p>}
              {contentDirty && <p className="notification-help">請先儲存或取消內容修改，再調整發送設定。</p>}
            </section> : <>
              {selected.error && !(selected.textEditingUnsupported && formatOf(selected) === 'flex') && <p className="notification-feedback error" role="alert">{selected.error}</p>}
              {selected.textEditingUnsupported && formatOf(selected) === 'flex' && <p className="notification-help">此卡片使用結構化內容，請查看右側預覽；可在「發送設定」調整啟用狀態。</p>}
              {selected.data ? <><label className="notification-content-field" htmlFor="notification-message-content">{managed ? '通知說明文字' : '通知內容'}<textarea ref={saveFieldRef} aria-required="true" id="notification-message-content" rows={16} value={content} maxLength={5000} disabled={saving} onChange={event => { setContent(event.target.value); setSaveError(null); }} /></label>{saveValidation.feedback}
                {managed && <p className="notification-help">說明文字用於新建立的通知；案件資料、互動按鈕與發送流程由系統帶入。</p>}
                {selected.data.variables.length > 0 ? <p className="notification-help">預覽變數使用下方公版範例值；實際發送由正式流程帶入：{selected.data.variables.map(variable => <code key={variable}>{`{${variable}}`}</code>)}</p> : <p className="notification-help">此段文案沒有需要手動填寫的變數。</p>}
              </> : descriptor?.allows_draft ? <><label className="notification-content-field" htmlFor="notification-message-content">預覽文案<textarea id="notification-message-content" rows={16} value={content} maxLength={5000} onChange={event => setContent(event.target.value)} /></label><p className="notification-help">只試看工會自行輸入的詢問或回覆，不會儲存、建立待辦或發送。</p></> : selected.kind === 'card' && <p className="notification-help">使用正式訊息與卡片組裝方式，以下方公版範例資料展示內容。</p>}
              {saveError && <p className="notification-feedback error" role="alert">{saveError}</p>}
            </>}
          </>}
          footer={editingSettings ? <button type="button" className="notification-button" disabled={updating} onClick={() => requestLeave(() => { setSettingsDirty(false); setEditingSettings(false); setDeliveryTab(false); })}>返回內容</button> : <><button type="button" className="notification-button" disabled={updating} onClick={close}>取消</button>{selected.data && <><button type="button" className="notification-text-button" disabled={updating || !contentDirty} onClick={() => { setContent(selected.data!.content); setSaveError(null); }}>還原內容</button><button type="button" className="notification-button primary" disabled={updating || !contentDirty} onClick={() => void save()}>{saving ? '儲存中…' : '儲存內容'}</button></>}</>}
        /> : <div className="notification-editor-placeholder"><MessageSquare /><h3>選擇訊息，查看用戶收到的樣子</h3><p>從左側選擇通知或卡片，立即查看公版預覽及帶入的欄位與值。</p></div>}
      </div>
    </section>
  );
};
