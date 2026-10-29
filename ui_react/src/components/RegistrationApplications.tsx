import { useEffect, useState } from 'react';
import { registrationApplicationsClient as client, type RegistrationApplication } from '../api/registration_applications/client';
import type { RegistryEditState } from './ClientRegistryDetailEditor';
import './RegistrationApplications.css';

const fieldLabels: Record<string, string> = {
  notes: '備註', line_id: 'LINE ID', baby_info: '寶寶資訊', service_time: '服務時段',
  service_type: '服務方式', delivery_type: '生產方式', residence_type: '居住型態',
  identity_status: '身分類別', service_start_date: '預計服務開始日',
};

export function RegistrationApplications({ onEditStateChange, initialId, onCommitted }: { onEditStateChange: (state: RegistryEditState) => void; initialId?: number; onCommitted?: () => Promise<void> }) {
  const [items, setItems] = useState<RegistrationApplication[]>([]);
  const [selected, setSelected] = useState<RegistrationApplication | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  useEffect(() => { onEditStateChange({ dirty: false, busy }); }, [busy, onEditStateChange]);
  const run = async (operation: () => Promise<void>) => {
    setBusy(true); setError(false); setMessage('');
    try { await operation(); } catch (failure) {
      setError(true); setMessage(failure instanceof Error ? failure.message : '處理結果未確認，請重新查詢同一筆申請。');
    } finally { setBusy(false); }
  };
  const refresh = () => run(async () => { const next = await client.pending(); setItems(next); setHasMore(next.length === 50); });
  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (initialId && Number.isSafeInteger(initialId) && initialId > 0) void run(async () => setSelected(await client.detail(initialId)));
  }, [initialId]);
  const approve = () => {
    if (!selected || busy || selected.approved) return;
    const submitted = selected;
    void run(async () => {
      const result = await client.approve(submitted); setSelected(result);
      setItems(previous => previous.filter(item => item.registration_id !== result.registration_id));
      setMessage(result.registration_kind === 'non_citizen' ? `非市民需求已核准，案件 ${result.case_no} 已建立。` : '需求申請已核准，正式客戶資料已建立。');
      await onCommitted?.();
    });
  };
  return <section className="registration-applications" aria-label="待核准需求申請" aria-busy={busy}>
    <header className="registration-applications__header">
      <div><h2>待核准需求</h2><p>需求表單先保存為申請。查看內容並核准後，才建立正式客戶資料及完成對應綁定。</p></div>
      <button type="button" disabled={busy} onClick={() => void refresh()}>重新查詢</button>
    </header>
    {message && <p className="registration-applications__message" role={error ? 'alert' : 'status'}>{message}</p>}
    {busy && <p className="registration-applications__loading" role="status">正在處理需求申請…</p>}
    <div className="registration-applications__layout">
    <div className="registration-applications__queue">
      <ul className="registration-applications__list">{items.map(item => <li key={item.registration_id}>
        <button type="button" className="registration-applications__item" aria-pressed={selected?.registration_id === item.registration_id} disabled={busy} onClick={() => void run(async () => setSelected(await client.detail(item.registration_id)))}>
          <span>申請 {item.registration_id}：{item.name}／{item.phone}{item.registration_kind === 'non_citizen' && '（非市民）'}</span>
          <small>查看申請 <span aria-hidden="true">→</span></small>
        </button>
      </li>)}</ul>
    {!busy && !items.length && <p className="registration-applications__empty">目前沒有待核准的需求申請。</p>}
    {hasMore && <button type="button" disabled={busy} onClick={() => void run(async () => {
      const next = await client.pending(items.at(-1)?.registration_id ?? 0);
      setItems(previous => [...previous, ...next]); setHasMore(next.length === 50);
    })}>載入更多</button>}
    </div>
    {selected ? <section className="registration-applications__detail" aria-label={`需求申請 ${selected.registration_id}`}>
      <header className="registration-applications__detail-header"><h3>申請 {selected.registration_id}：{selected.name}</h3><span className="registration-applications__badge">{selected.approved ? '已核准' : '待核准'}</span></header>
      {selected.registration_kind === 'non_citizen' && <p className="registration-applications__kind">非市民服務申請{selected.case_no && ` · 案件編號：${selected.case_no}`}</p>}
      <dl className="registration-applications__fields">{selected.fields.map((field, index) => <div key={`${field.label}-${index}`}><dt>{fieldLabels[field.label] ?? field.label}</dt><dd>{field.value}</dd></div>)}</dl>
      <footer className="registration-applications__actions">{selected.approved ? <p>此申請已核准。</p> : <button type="button" className="registration-applications__approve" disabled={busy} onClick={approve}>{selected.registration_kind === 'non_citizen' ? '核准並建立案件' : '核准並建立客戶'}</button>}</footer>
    </section> : <div className="registration-applications__placeholder"><h3>查看申請內容</h3><p>選擇一筆需求申請，確認填寫內容後再核准。</p></div>}
    </div>
  </section>;
}
