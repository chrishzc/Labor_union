/**
 * File: LineNotificationWorkbench.tsx
 * Description: 統一歡迎訊息與通知內容維護，沿用版本化儲存及既有規則影響確認。
 */
import { useCallback, useEffect, useRef, useState, type FC } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { Drawer } from './Drawer';
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

interface NotificationContent {
  content: string;
  revision: number;
  variables: string[];
}

interface NotificationEntry {
  id: string;
  name: string;
  recipient: string;
  kind: 'welcome' | 'rule';
  rule?: LineNotificationRuleModel;
  data: NotificationContent | null;
  error: string | null;
}

interface LineNotificationWorkbenchProps {
  configuration?: LineConfigurationQueryClient;
  onboarding?: LineOnboardingClient;
  templates?: LineNotificationTemplateClient;
  search: string;
  enabled: 'all' | 'enabled' | 'disabled';
  onSearchChange(value: string): void;
  onEnabledChange(value: 'all' | 'enabled' | 'disabled'): void;
}

const FLOW_MANAGED_EVENTS = new Set([
  'scheduling.leave.extension_requested',
  'matching.zero_pool.preview_applied',
  'runtime.alert.review_required',
  'complaint.ingress.hold_high_ticket',
]);

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

function previewText(content: string, variables: string[]): string {
  return variables.reduce((text, variable) => text.replaceAll(`{${variable}}`, variable === 'url' ? '［專屬安全登記連結］' : `〔${variable}〕`), content);
}

export const LineNotificationWorkbench: FC<LineNotificationWorkbenchProps> = ({
  configuration = lineConfigurationQueryClient,
  onboarding = lineOnboardingClient,
  templates = lineNotificationTemplateClient,
  search,
  enabled,
  onSearchChange,
  onEnabledChange,
}) => {
  const [entries, setEntries] = useState<NotificationEntry[]>([]);
  const [catalog, setCatalog] = useState<LineNotificationRulesCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<NotificationEntry | null>(null);
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [discardOpen, setDiscardOpen] = useState(false);
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
  const settingsState = useCallback((changed: boolean, busy: boolean) => { setSettingsDirty(changed); setSettingsBusy(busy); }, []);

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
      const rules = adaptLineNotificationRulesCatalog(snapshot).rules.filter(rule => rule.templateId !== 'customer_onboarding_welcome');
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

  const close = () => {
    if (updating) return;
    if (dirty) { setDiscardOpen(true); return; }
    setSelected(null);
    setEditingSettings(false);
    setSettingsDirty(false);
    setSaveError(null);
    window.requestAnimationFrame(() => opener.current?.focus());
  };

  const open = (entry: NotificationEntry, button: HTMLButtonElement) => {
    opener.current = button;
    setSelected(entry);
    setContent(entry.data?.content ?? '');
    setSaveError(null);
    setDiscardOpen(false);
    setEditingSettings(false);
    setSettingsDirty(false);
    setNotice(null);
  };

  const save = async () => {
    if (!selected?.data || !dirty || !content.trim() || saving) return;
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
      focusAfterReload.current = target.id;
      setReload(value => value + 1);
      setNotice('通知內容已儲存。');
    } catch (error) {
      if (!controller.signal.aborted) setSaveError(contentError(error, true));
    } finally {
      if (!controller.signal.aborted) setSaving(false);
    }
  };

  const query = search.trim().toLowerCase();
  const visible = entries.filter(entry => (!query || `${entry.name} ${entry.data?.content ?? ''}`.toLowerCase().includes(query))
    && (enabled === 'all' || (!entry.rule || !FLOW_MANAGED_EVENTS.has(entry.rule.eventCode)) && (entry.rule?.enabled ?? true) === (enabled === 'enabled')));
  const managed = selected?.rule ? FLOW_MANAGED_EVENTS.has(selected.rule.eventCode) : false;

  return (
    <section className="notification-workspace" aria-label="通知內容設定">
      <div className="notification-page-heading">
        <div><h2>通知設定</h2><p>統一編輯各則通知內容，包含新好友歡迎訊息。</p></div>
        <button type="button" className="notification-button" disabled={loading} onClick={() => { setNotice(null); setReload(value => value + 1); }}><RefreshCw aria-hidden="true" />重新整理</button>
      </div>
      <div className="notification-content-list">
        <div className="notification-filters">
          <label className="notification-search"><span className="sr-only">搜尋通知名稱或內容</span><Search aria-hidden="true" /><input type="search" value={search} maxLength={100} placeholder="搜尋通知名稱或內容" onChange={event => onSearchChange(event.target.value)} /></label>
          <select aria-label="啟用狀態" value={enabled} onChange={event => onEnabledChange(event.target.value as typeof enabled)}><option value="all">全部狀態</option><option value="enabled">已啟用</option><option value="disabled">已停用</option></select>
        </div>
        {notice && <p className="notification-feedback" role="status">{notice}</p>}
        {catalogError && <p className="notification-feedback error" role="alert">{catalogError}</p>}
        {loading ? <p className="notification-feedback" role="status">正在載入通知內容…</p> : visible.length === 0 ? (
          <div className="notification-empty"><h3>沒有符合條件的通知</h3><button type="button" className="notification-button" onClick={() => { onSearchChange(''); onEnabledChange('all'); }}>清除條件</button></div>
        ) : <table className="notification-content-table"><caption className="sr-only">通知內容設定清單</caption><thead><tr><th scope="col">通知名稱</th><th scope="col">通知對象</th><th scope="col">內容摘要</th><th scope="col">操作</th></tr></thead><tbody>{visible.map(entry => <tr key={entry.id}>
          <td data-label="通知名稱"><strong>{entry.name}</strong>{entry.rule?.enabled === false && !FLOW_MANAGED_EVENTS.has(entry.rule.eventCode) && <span className="notification-secondary">已停用</span>}</td>
          <td data-label="通知對象">{entry.recipient}</td>
          <td data-label="內容摘要"><span className={`notification-excerpt${entry.error ? ' error' : ''}`}>{entry.error ?? entry.data?.content}</span></td>
          <td data-label="操作"><button type="button" className="notification-text-button" data-notification-id={entry.id} aria-label={`${entry.data ? '編輯' : '查看'}${entry.name}內容`} onClick={event => open(entry, event.currentTarget)}>{entry.data ? '編輯內容' : '查看狀態'}</button></td>
        </tr>)}</tbody></table>}
      </div>
      <Drawer isOpen={selected !== null} title={discardOpen ? '放棄尚未儲存的修改？' : selected?.name ?? '通知內容'} className="notification-content-drawer" closeLabel="關閉通知內容" closeDisabled={updating} onClose={discardOpen ? () => setDiscardOpen(false) : close}
        footer={discardOpen ? <><button type="button" className="notification-button" onClick={() => setDiscardOpen(false)}>繼續編輯</button><button type="button" className="notification-button danger" onClick={() => { setDiscardOpen(false); setSettingsDirty(false); setSelected(null); }}>放棄修改</button></> : editingSettings ? <button type="button" className="notification-button" disabled={updating} onClick={() => { if (settingsDirty) setDiscardOpen(true); else setEditingSettings(false); }}>返回內容</button> : <><button type="button" className="notification-button" disabled={saving} onClick={close}>取消</button>{selected?.data && <button type="button" className="notification-button primary" disabled={saving || !contentDirty || !content.trim()} onClick={() => void save()}>{saving ? '儲存中…' : '儲存內容'}</button>}</>}>
        {discardOpen && <p>離開後，這則通知尚未儲存的修改會被捨棄。</p>}
        <fieldset className="notification-editor-scope" disabled={discardOpen} hidden={discardOpen}>
        {selected && editingSettings && catalog ? <LineNotificationRulesMutationPanel catalog={catalog} selectedRuleId={selected.id} settingsOnly onEditingStateChange={settingsState} onCommitted={() => { setSelected(null); setSettingsDirty(false); setReload(value => value + 1); }} /> : selected && <>
          {selected.error && <p className="notification-feedback error" role="alert">{selected.error}</p>}
          {selected.data && <>
            <label className="notification-content-field" htmlFor="notification-message-content">{managed ? '通知說明文字' : '通知內容'}<textarea id="notification-message-content" rows={selected.kind === 'welcome' ? 12 : 7} value={content} maxLength={5000} disabled={saving} onChange={event => { setContent(event.target.value); setSaveError(null); }} /></label>
            {managed && <p className="notification-help">說明文字會用於新建立的通知；案件資料、互動按鈕與發送流程由系統帶入。</p>}
            {selected.data.variables.length > 0 && <p className="notification-help">動態資料於發送時帶入：{selected.data.variables.map(variable => <code key={variable}>{`{${variable}}`}</code>)}</p>}
            <div className="notification-preview"><p>訊息預覽</p><div className="notification-bubble">{previewText(content, selected.data.variables) || '尚未輸入內容'}</div></div>
          </>}
          {saveError && <p className="notification-feedback error" role="alert">{saveError}</p>}
          <details className="notification-delivery-settings"><summary>發送設定</summary><dl><div><dt>通知對象</dt><dd>{selected.recipient}</dd></div><div><dt>發送時機</dt><dd>{selected.kind === 'welcome' ? '加入或重新加入好友時' : managed ? '由業務流程觸發' : selected.rule?.scheduleLabel}</dd></div>{selected.rule && !managed && <><div><dt>狀態</dt><dd>{selected.rule.enabled ? '已啟用' : '已停用'}</dd></div><div><dt>頻率</dt><dd>{selected.rule.frequencyLabel}</dd></div></>}</dl>{selected.rule && !managed && <button type="button" className="notification-text-button" disabled={dirty || saving} onClick={() => setEditingSettings(true)}>修改發送設定</button>}{contentDirty && selected.rule && !managed && <p className="notification-help">請先儲存或取消內容修改，再調整發送設定。</p>}</details>
        </>}
        </fieldset>
      </Drawer>
    </section>
  );
};
