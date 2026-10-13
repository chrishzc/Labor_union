import { useEffect, useRef, useState } from 'react';
import { staffQualificationEditingClient, type QualificationFacts, type QualificationSnapshot } from '../api/staff/qualification_editing_client';

const labels: Record<keyof QualificationFacts, string> = { special_skills: '專業技能', has_massage_cert: '按摩證書', certifications: '一般證照', care_babies: '最多照顧寶寶數', transportation: '交通方式' };
const listKeys = ['special_skills', 'certifications', 'transportation'] as const;
const display = (value: QualificationFacts[keyof QualificationFacts]) => Array.isArray(value) ? value.join('、') || '尚未登錄' : value === null ? '尚未登錄' : typeof value === 'boolean' ? value ? '有' : '無' : String(value);

export function StaffQualificationEditor({ staffId, onUpdated }: { staffId: number; onUpdated: () => void | Promise<void> }) {
  const [snapshot, setSnapshot] = useState<QualificationSnapshot | null>(null);
  const [lists, setLists] = useState({ special_skills: '', certifications: '', transportation: '' });
  const [massage, setMassage] = useState('');
  const [care, setCare] = useState('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<QualificationSnapshot | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [needsRequery, setNeedsRequery] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const reset = (value: QualificationSnapshot) => { setLists({ special_skills: value.after.special_skills.join('\n'), certifications: value.after.certifications.join('\n'), transportation: value.after.transportation.join('\n') }); setMassage(value.after.has_massage_cert === null ? '' : String(value.after.has_massage_cert)); setCare(value.after.care_babies === null ? '' : String(value.after.care_babies)); setReason(''); setPreview(null); setKey(null); };
  const invalidate = () => { setPreview(null); setKey(null); setMessage(''); };
  const load = async () => {
    const current = ++epoch.current;
    controller.current?.abort(); controller.current = new AbortController();
    setBusy(true); setNeedsRequery(false); setSnapshot(null); setMessage('正在載入專業資格…');
    try { const value = await staffQualificationEditingClient.query(staffId, controller.current.signal); if (current !== epoch.current) return false; setSnapshot(value); reset(value); setMessage(''); return true; }
    catch (error) { if (current === epoch.current) { setNeedsRequery(true); setMessage(error instanceof Error ? error.message : '資格載入失敗。'); } return false; }
    finally { if (current === epoch.current) setBusy(false); }
  };
  useEffect(() => { void load(); return () => { ++epoch.current; controller.current?.abort(); }; }, [staffId]);
  const facts = (): QualificationFacts => ({ special_skills: lists.special_skills.split('\n').map(v => v.trim()).filter(Boolean), certifications: lists.certifications.split('\n').map(v => v.trim()).filter(Boolean), transportation: lists.transportation.split('\n').map(v => v.trim()).filter(Boolean), has_massage_cert: massage === '' ? null : massage === 'true', care_babies: care === '' ? null : Number(care) });
  const doPreview = async () => {
    const current = epoch.current; setBusy(true); invalidate();
    try { const value = await staffQualificationEditingClient.preview(staffId, facts(), controller.current?.signal); if (current !== epoch.current) return; setPreview(value); setKey(`staff-qualification-${crypto.randomUUID()}`); setMessage('預覽完成，請核對變更後確認儲存。'); }
    catch (error) { if (current === epoch.current) setMessage(error instanceof Error ? error.message : '預覽失敗。'); }
    finally { if (current === epoch.current) setBusy(false); }
  };
  const doApply = async () => {
    if (!preview || !key || !reason.trim()) return;
    const current = epoch.current; setBusy(true);
    try { await staffQualificationEditingClient.apply(staffId, facts(), preview, reason.trim(), key, controller.current?.signal); if (current !== epoch.current) return; const refreshed = await load(); if (current + 1 !== epoch.current) return; setMessage(refreshed ? '專業資格與服務資料已儲存並重新查詢。' : '資料已儲存，但重新查詢失敗，請重試查詢。'); await onUpdated(); }
    catch (error) { if (current === epoch.current) { setNeedsRequery(true); setMessage(error instanceof Error ? error.message : '儲存結果未確認，請重試或重新查詢。'); } }
    finally { if (current === epoch.current) setBusy(false); }
  };
  return <section className="staff-holiday-op-card" aria-label="專業資格與服務資料編輯">
    <h3 className="staff-op-title">✏️ 專業資格與服務資料</h3>
    <p>技能、一般證照及交通方式每行填一項；刪除該行即可移除。按摩證書獨立登錄，與一般證照分開保存。</p>
    {snapshot && <><div className="staff-op-grid">
      {listKeys.map(field => <label className="staff-op-field" key={field}>{labels[field]}<textarea rows={3} disabled={busy} value={lists[field]} onChange={event => { setLists(value => ({ ...value, [field]: event.target.value })); invalidate(); }} /></label>)}
      <label className="staff-op-field">按摩證書<select disabled={busy} value={massage} onChange={event => { setMassage(event.target.value); invalidate(); }}><option value="">尚未登錄</option><option value="true">有</option><option value="false">無</option></select></label>
      <label className="staff-op-field">最多照顧寶寶數<input type="number" min={1} step={1} max={2147483647} disabled={busy} value={care} onChange={event => { setCare(event.target.value); invalidate(); }} /></label>
    </div><label className="staff-op-field">專業資格異動原因<input maxLength={500} disabled={busy} value={reason} onChange={event => setReason(event.target.value)} /></label>
    {preview && <div aria-label="專業資格變更預覽">{(Object.keys(labels) as Array<keyof QualificationFacts>).filter(field => JSON.stringify(preview.before[field]) !== JSON.stringify(preview.after[field])).map(field => <p key={field}><strong>{labels[field]}</strong>：{display(preview.before[field])} → {display(preview.after[field])}</p>)}</div>}
    <div className="staff-op-actions"><button type="button" className="staff-secondary-btn" disabled={busy} onClick={() => { reset(snapshot); setMessage('已取消變更。'); }}>取消變更</button><button type="button" className="staff-primary-btn" disabled={busy} onClick={() => void doPreview()}>預覽變更</button><button type="button" className="staff-primary-btn" disabled={busy || !preview || !reason.trim()} onClick={() => void doApply()}>確認儲存</button></div></>}
    {needsRequery && <button type="button" className="staff-secondary-btn" disabled={busy} onClick={() => void load()}>重試讀取專業資格</button>}
    {message && <p role="status">{message}</p>}
  </section>;
}
