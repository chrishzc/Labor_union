import { useEffect, useState } from 'react';
import { useUnsavedChanges } from '../../components/UnsavedChanges';
import { nonCitizenLiffClient as client, type NonCitizenLiffPage, type NonCitizenLiffView } from '../../api/line_configuration/non_citizen_liff_client';

export function NonCitizenLiffSettingsPanel({ active }: { active: boolean }) {
  const [current, setCurrent] = useState<NonCitizenLiffView | null>(null);
  const [draft, setDraft] = useState<NonCitizenLiffPage | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const dirty = current?.page && JSON.stringify(current.page) !== JSON.stringify(draft);
  useEffect(() => {
    if (!dirty && !busy) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty, busy]);
  const apply = (value: NonCitizenLiffView) => { setCurrent(value); setDraft(value.page); setUncertain(false); };
  const query = async () => {
    if (dirty && !window.confirm('重新查詢將放棄尚未儲存的設定，是否繼續？')) return;
    setBusy(true); setMessage('');
    try { apply(await client.query()); }
    catch (error) { setMessage(error instanceof Error ? error.message : '讀取設定失敗，請重試。'); }
    finally { setBusy(false); }
  };
  useEffect(() => { if (active && !current && !busy) void query(); }, [active]);
  const save = async () => {
    if (!current || busy || uncertain) return;
    setBusy(true); setMessage('');
    try {
      apply(draft ? await client.save(current.revision, draft) : await client.initialize(current.revision));
      setMessage('非市民申請頁面設定已儲存。');
    } catch (error) {
      setUncertain(true);
      setMessage(`${error instanceof Error ? error.message : '儲存結果未確認。'} 請重新查詢確認結果。`);
    } finally { setBusy(false); }
  };
  const guardRef = useUnsavedChanges('非市民申請頁面設定', dirty ? [{label:'表單文字與填寫提示',before:'已儲存設定',after:'尚有未儲存修改'}] : [], {
    busy, discard: () => setDraft(current?.page ?? null), save: uncertain ? undefined : save,
  });
  return <section ref={guardRef} hidden={!active} aria-label="非市民申請頁面設定" className="line-notification-rule-editor non-citizen-liff-settings">
    <h3>非市民申請頁面設定</h3>
    <p>調整非市民表單的文字與填寫提示，儲存後套用。</p>
    <button type="button" disabled={busy} onClick={() => void query()}>重新查詢設定</button>
    {current && !draft && <button type="button" disabled={busy || uncertain} onClick={() => void save()}>建立非市民頁面及入口</button>}
    {draft && <fieldset disabled={busy || uncertain}>
      <label><input type="checkbox" checked={draft.enabled} onChange={event => setDraft({ ...draft, enabled: event.target.checked })} />啟用填寫頁面</label>
      <label>頁面標題<input value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
      <label>頁面說明<textarea value={draft.subtitle} onChange={event => setDraft({ ...draft, subtitle: event.target.value })} /></label>
      <label>送出按鈕文字<input value={draft.submit_button} onChange={event => setDraft({ ...draft, submit_button: event.target.value })} /></label>
      <label>送出後說明<textarea value={draft.success_description} onChange={event => setDraft({ ...draft, success_description: event.target.value })} /></label>
      <details><summary>欄位名稱與提示</summary>{draft.fields.map((field, index) => <div key={field.id}>
        <label>{field.label}{field.required ? '（必填）' : ''}<input aria-label={`${field.id}欄位名稱`} value={field.label} onChange={event => setDraft({ ...draft, fields: draft.fields.map((item, i) => i === index ? { ...item, label: event.target.value } : item) })} /></label>
        <label>填寫提示<input value={field.placeholder} onChange={event => setDraft({ ...draft, fields: draft.fields.map((item, i) => i === index ? { ...item, placeholder: event.target.value } : item) })} /></label>
      </div>)}</details>
      <button type="button" onClick={() => void save()}>儲存頁面設定</button>
    </fieldset>}
    {busy && <p role="status">處理中…</p>}
    {message && <p role={uncertain ? 'alert' : 'status'}>{message}</p>}
  </section>;
}
