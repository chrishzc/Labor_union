import { useEffect, useRef, useState } from 'react';
import { notificationTasksClient, type NotificationPage } from '../api/line_notifications/notification_tasks_client';
import {
  staffWebError, staffWebProfileClient, webProfileCategoryLabels,
  type WebProfileTemplate, type WebProfileTemplateInput,
} from '../api/staff/staff_web_profile_client';
import { LineNotificationTemplateEditor } from './LineNotificationTemplateEditor';
import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import './StaffWebProfile.css';

const tabs = [
  { id: 'templates', label: '網頁模板' },
  { id: 'review', label: '照片審核' },
  { id: 'reminders', label: '到期提醒' },
] satisfies { id: string; label: string }[];

const newTemplate: WebProfileTemplateInput = {
  name: '', category: 'photo', display_order: 0, version: 0,
  reminder_enabled: false, reminder_months: 1, reminder_days: 0,
};

function templateInput(item: WebProfileTemplate): WebProfileTemplateInput {
  return {
    name: item.name, category: item.category, display_order: item.display_order, version: item.version,
    reminder_enabled: item.reminder_enabled,
    reminder_months: item.reminder_lead.months, reminder_days: item.reminder_lead.days,
  };
}

function TemplateEditor({ item, reminderOnly, saved, close }: {
  item: WebProfileTemplate | null;
  reminderOnly: boolean;
  saved: (result: WebProfileTemplate) => void;
  close: () => void;
}) {
  const baseline = item ? templateInput(item) : newTemplate;
  const [draft, setDraft] = useState(baseline);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reloadRequired, setReloadRequired] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const { requestLeave } = useUnsavedNavigation();
  const change = (fields: Partial<WebProfileTemplateInput>) => {
    setDraft(current => ({ ...current, ...fields }));
    if (!reloadRequired) setError('');
  };
  async function save() {
    if (busy || reloadRequired) return false;
    if (!formRef.current?.reportValidity() || !draft.name.trim()) {
      setError('請輸入項目名稱。');
      return false;
    }
    setBusy(true);
    setError('');
    try {
      saved(await staffWebProfileClient.saveTemplate(item?.item_id ?? null, { ...draft, name: draft.name.trim() }));
      return true;
    } catch (caught) {
      setError(staffWebError(caught, '無法確認模板是否已儲存，請重新讀取。'));
      setReloadRequired(true);
      return false;
    } finally {
      setBusy(false);
    }
  }
  const draftRef = useUnsavedDraft('月嫂網頁模板', {
    '名稱': draft.name, '類別': draft.category, '順序': draft.display_order,
    '提醒': String(draft.reminder_enabled), '提前月數': draft.reminder_months, '提前天數': draft.reminder_days,
  }, {
    baseline: {
      '名稱': baseline.name, '類別': baseline.category, '順序': baseline.display_order,
      '提醒': String(baseline.reminder_enabled), '提前月數': baseline.reminder_months, '提前天數': baseline.reminder_days,
    },
    busy,
    save: async () => { if (!await save()) throw new Error('template_save_unconfirmed'); },
    discard: () => setDraft(baseline),
  });

  return <section ref={draftRef} className="staff-holiday-op-card" aria-label={item ? `編輯${item.name}` : '新增模板項目'}>
    <form ref={formRef} onSubmit={event => { event.preventDefault(); void save(); }}>
      <fieldset className="staff-web-fields" disabled={busy}>
        <legend>{item ? `編輯「${item.name}」` : '新增模板項目'}</legend>
        {!reminderOnly && <>
          <label className="staff-op-field">項目名稱<input required maxLength={100} value={draft.name} onChange={event => change({ name: event.target.value })} /></label>
          <label className="staff-op-field">類別<select value={draft.category} onChange={event => {
            const next = event.target.value;
            if (next === 'other') change({ category: next });
            else if (next === 'photo' || next === 'certificate') {
              change({ category: next, reminder_enabled: false, reminder_months: 1, reminder_days: 0 });
            }
          }}>
            <option value="photo">照片</option><option value="certificate">證照</option><option value="other">其他</option>
          </select></label>
          <label className="staff-op-field">顯示順序<input type="number" required min={0} max={2147483647} value={draft.display_order} onChange={event => change({ display_order: Number(event.target.value) })} /></label>
        </>}
        <p className="staff-op-hint">{draft.category === 'other' ? '照片須填寫到期日。' : '照片無須填寫到期日。'}</p>
        {draft.category === 'other' && <>
          <label className="staff-web-checkbox"><input type="checkbox" checked={draft.reminder_enabled} onChange={event => change({ reminder_enabled: event.target.checked })} />啟用到期提醒</label>
          {draft.reminder_enabled && <>
            <label className="staff-op-field">提前月數<input type="number" required min={0} max={120} value={draft.reminder_months} onChange={event => change({ reminder_months: Number(event.target.value) })} /></label>
            <label className="staff-op-field">另提前天數<input type="number" required min={0} max={3650} value={draft.reminder_days} onChange={event => change({ reminder_days: Number(event.target.value) })} /></label>
          </>}
        </>}
      </fieldset>
      <div className="staff-op-actions">
        <button type="submit" className="staff-primary-btn" disabled={busy || reloadRequired}>{busy ? '儲存中…' : '儲存項目'}</button>
        <button type="button" className="staff-secondary-btn" disabled={busy} onClick={() => requestLeave(close)}>取消</button>
      </div>
      {error && <p role="alert">{error}</p>}
    </form>
  </section>;
}

function TemplateItems({ reminderOnly }: { reminderOnly: boolean }) {
  const [templates, setTemplates] = useState<WebProfileTemplate[] | null>(null);
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const { requestLeave } = useUnsavedNavigation();

  useEffect(() => {
    const controller = new AbortController();
    staffWebProfileClient.templates(controller.signal).then(items => {
      if (!controller.signal.aborted) setTemplates(items);
    }).catch(caught => {
      if (!controller.signal.aborted) setError(staffWebError(caught, '無法讀取模板。'));
    });
    return () => controller.abort();
  }, [reload]);

  const items = templates?.filter(item => !reminderOnly || item.category === 'other');
  const selected = templates?.find(item => item.item_id === editing);
  function edit(id: number | 'new') {
    if (id === editing) return;
    requestLeave(() => { setEditing(id); setNotice(''); });
  }
  function save(item: WebProfileTemplate) {
    setTemplates(current => [...(current ?? []).filter(row => row.item_id !== item.item_id), item]);
    setEditing(null);
    setNotice(`已儲存「${item.name}」。`);
  }

  return <section aria-label={reminderOnly ? '各項目的提醒時間' : '模板項目'}>
    {!reminderOnly && <button type="button" className="staff-primary-btn" onClick={() => edit('new')} disabled={!templates}>新增項目</button>}
    {selected || editing === 'new' ? <>
      <TemplateEditor key={editing} item={selected ?? null} reminderOnly={reminderOnly} saved={save} close={() => setEditing(null)} />
      <button type="button" className="staff-secondary-btn" onClick={() => requestLeave(() => {
        setEditing(null);
        setTemplates(null);
        setError('');
        setReload(value => value + 1);
      })}>重新讀取項目</button>
    </> : null}
    {notice && <p role="status">{notice}</p>}
    {error && <div role="alert"><p>{error}</p><button type="button" className="staff-secondary-btn" onClick={() => {
      setError('');
      setReload(value => value + 1);
    }}>重新讀取項目</button></div>}
    {!items && !error && <p role="status">正在讀取模板項目…</p>}
    {items?.length === 0 && <p>{reminderOnly ? '目前沒有可設定提醒的其他類別項目。' : '目前沒有模板項目。'}</p>}
    {!!items?.length && <div className="staff-web-table-wrap"><table className="staff-web-table">
      <thead><tr><th scope="col">名稱</th><th scope="col">類別</th><th scope="col">顯示順序</th><th scope="col">到期提醒</th><th scope="col">操作</th></tr></thead>
      <tbody>{[...items].sort((a, b) => a.display_order - b.display_order || a.item_id - b.item_id).map(item => <tr key={item.item_id}>
        <th scope="row">{item.name}</th>
        <td>{webProfileCategoryLabels[item.category]}</td>
        <td>{item.display_order}</td>
        <td>{item.category !== 'other' ? '不適用' : item.reminder_enabled
          ? `提前 ${item.reminder_lead.months} 個月 ${item.reminder_lead.days} 天` : '關閉'}</td>
        <td><button type="button" className="staff-secondary-btn" aria-label={`編輯${item.name}`} onClick={() => edit(item.item_id)}>編輯</button></td>
      </tr>)}</tbody>
    </table></div>}
  </section>;
}

function PendingApplications() {
  const [page, setPage] = useState<NotificationPage | null>(null);
  const [cursor, setCursor] = useState<number | string>(0);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    notificationTasksClient.list('staff_profile', cursor, controller.signal).then(result => {
      if (!controller.signal.aborted) setPage(result);
    }).catch(caught => {
      if (!controller.signal.aborted) setError(staffWebError(caught, '無法讀取待審申請。'));
    });
    return () => controller.abort();
  }, [cursor, reload]);

  function go(next: number | string) {
    setPage(null);
    setError('');
    if (next === cursor) setReload(value => value + 1);
    else setCursor(next);
  }

  return <section aria-label="待審申請">
    {!page && !error && <p role="status">正在讀取待審申請…</p>}
    {error && <div role="alert"><p>{error}</p><button type="button" className="staff-secondary-btn" onClick={() => go(cursor)}>重新讀取</button></div>}
    {page?.items.length === 0 && <p>目前沒有待審申請。</p>}
    {!!page?.items.length && <ul className="staff-web-review-list">{page.items.map(item => item.reference_id !== null && <li key={item.id}>
      <strong>{item.person}</strong><span>{item.title}</span>
      <a href={`#staff?profile_request=${item.reference_id}&return=web`}>審核申請 #{item.reference_id}</a>
    </li>)}</ul>}
    <div className="staff-op-actions">
      {cursor !== 0 && <button type="button" className="staff-secondary-btn" onClick={() => go(0)}>回第一頁</button>}
      {page?.next_cursor != null && <button type="button" className="staff-secondary-btn" onClick={() => go(page.next_cursor ?? 0)}>下一頁</button>}
    </div>
  </section>;
}

export function StaffWebProfileManagement({ initialTab = 'templates' }: { initialTab?: string }) {
  const [tab, setTab] = useState(initialTab);
  const { requestLeave } = useUnsavedNavigation();
  return <div className="staff-holiday-op-card staff-web-management">
    <div className="staff-filter-pills" role="tablist" aria-label="履歷網頁管理">
      {tabs.map(({ id, label }, index) => <button type="button" key={id} id={`staff-web-${id}`} role="tab"
        aria-selected={tab === id} aria-controls="staff-web-panel" tabIndex={tab === id ? 0 : -1}
        className={`staff-filter-pill ${tab === id ? 'active' : ''}`} onClick={() => { if (tab !== id) requestLeave(() => setTab(id)); }}
        onKeyDown={event => {
          const positions: Record<string, number> = { ArrowLeft: (index + 2) % 3, ArrowRight: (index + 1) % 3, Home: 0, End: 2 };
          const target = tabs[positions[event.key]];
          if (!target || target.id === id) return;
          event.preventDefault();
          requestLeave(() => { setTab(target.id); document.getElementById(`staff-web-${target.id}`)?.focus(); });
        }}>{label}</button>)}
    </div>
    <div id="staff-web-panel" className="staff-web-panel" role="tabpanel" aria-labelledby={`staff-web-${tab}`}>
      {tab === 'templates' && <TemplateItems reminderOnly={false} />}
      {tab === 'review' && <PendingApplications />}
      {tab === 'reminders' && <>
        <TemplateItems reminderOnly />
        <LineNotificationTemplateEditor ruleId="staff-web-expiry-reminder" />
      </>}
    </div>
  </div>;
}
