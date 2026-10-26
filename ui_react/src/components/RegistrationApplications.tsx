import { useEffect, useState } from 'react';
import { registrationApplicationsClient as client, type RegistrationApplication } from '../api/registration_applications/client';
import type { RegistryEditState } from './ClientRegistryDetailEditor';

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
      setMessage('需求申請已核准，正式客戶資料已建立。');
      await onCommitted?.();
    });
  };
  return <section aria-label="待核准需求申請">
    <h2>待核准需求</h2><p>需求表單先保存為申請。查看內容並核准後，才建立正式客戶資料及完成對應綁定。</p>
    <button type="button" disabled={busy} onClick={() => void refresh()}>重新查詢</button>
    <ul>{items.map(item => <li key={item.registration_id}>
      <button type="button" disabled={busy} onClick={() => void run(async () => setSelected(await client.detail(item.registration_id)))}>
        申請 {item.registration_id}：{item.name}／{item.phone}
      </button>
    </li>)}</ul>
    {!busy && !items.length && <p>目前沒有待核准的需求申請。</p>}
    {hasMore && <button type="button" disabled={busy} onClick={() => void run(async () => {
      const next = await client.pending(items.at(-1)?.registration_id ?? 0);
      setItems(previous => [...previous, ...next]); setHasMore(next.length === 50);
    })}>載入更多</button>}
    {selected && <section aria-label={`需求申請 ${selected.registration_id}`}>
      <h3>申請 {selected.registration_id}：{selected.name}</h3>
      <dl>{selected.fields.map((field, index) => <div key={`${field.label}-${index}`}><dt>{field.label}</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{field.value}</dd></div>)}</dl>
      {selected.approved ? <p>此申請已核准。</p> : <button type="button" disabled={busy} onClick={approve}>核准並建立客戶</button>}
    </section>}
    {message && <p role={error ? 'alert' : 'status'}>{message}</p>}
  </section>;
}
