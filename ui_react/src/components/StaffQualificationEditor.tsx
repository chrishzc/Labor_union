import { useEffect, useRef, useState } from 'react';
import { staffQualificationEditingClient, type QualificationFacts, type QualificationSnapshot } from '../api/staff/qualification_editing_client';
import { useUnsavedDraft } from './UnsavedChanges';

const editorTitle = '交通與照顧人數';
const editableFields = ['transportation', 'care_babies'] as const;
type EditableField = typeof editableFields[number];
const labels: Record<EditableField, string> = {
  transportation: '交通方式',
  care_babies: '最多照顧寶寶數',
};

function display(value: QualificationFacts[EditableField]): string {
  return (Array.isArray(value) ? value.join('、') : value?.toString()) || '尚未登錄';
}

export function StaffQualificationEditor({ staffId, onUpdated }: { staffId: number; onUpdated: () => void | Promise<void> }) {
  const [messageError, setMessageError] = useState(false);
  const [snapshot, setSnapshot] = useState<QualificationSnapshot | null>(null);
  const [transportation, setTransportation] = useState('');
  const [careBabies, setCareBabies] = useState('');
  const [preview, setPreview] = useState<QualificationSnapshot | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [needsRequery, setNeedsRequery] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const epoch = useRef(0);

  const reset = (value: QualificationSnapshot) => {
    setTransportation(value.after.transportation.join('\n'));
    setCareBabies(value.after.care_babies?.toString() ?? '');
    setPreview(null);
    setKey(null);
  };

  const invalidate = () => {
    setMessageError(false);
    setPreview(null);
    setKey(null);
    setMessage('');
  };

  const load = async () => {
    const current = ++epoch.current;
    controller.current?.abort();
    controller.current = new AbortController();
    setBusy(true);
    setMessageError(false);
    setNeedsRequery(false);
    setSnapshot(null);
    setMessage('正在載入交通與照顧人數…');
    try {
      const value = await staffQualificationEditingClient.query(staffId, controller.current.signal);
      if (current !== epoch.current) return false;
      setSnapshot(value);
      reset(value);
      setMessage('');
      return true;
    } catch (error) {
      if (current === epoch.current) {
        setMessageError(true);
        setNeedsRequery(true);
        setMessage(error instanceof Error ? error.message : '交通與照顧人數載入失敗。');
      }
      return false;
    } finally {
      if (current === epoch.current) setBusy(false);
    }
  };

  useEffect(() => {
    void load();
    return () => {
      ++epoch.current;
      controller.current?.abort();
    };
  }, [staffId]);

  const unsavedRef = useUnsavedDraft(
    editorTitle,
    { [labels.transportation]: transportation, [labels.care_babies]: careBabies },
    {
      enabled: !!snapshot,
      busy: busy && (!!snapshot || !!preview),
      baseline: snapshot ? {
        [labels.transportation]: snapshot.after.transportation.join('\n'),
        [labels.care_babies]: snapshot.after.care_babies?.toString() ?? '',
      } : null,
    }
  );

  const doApply = async () => {
    if (busy || !snapshot) return;
    const current = epoch.current;
    setMessageError(false);
    setBusy(true);
    try {
      const submitted: QualificationFacts = {
        ...snapshot.after,
        transportation: transportation.split('\n').map(value => value.trim()).filter(Boolean),
        care_babies: careBabies === '' ? null : Number(careBabies),
      };
      const approved = preview ?? await staffQualificationEditingClient.preview(staffId, submitted, controller.current?.signal);
      if (current !== epoch.current) return;
      if (approved.snapshot_fingerprint !== snapshot.snapshot_fingerprint) {
        setMessageError(true);
        setNeedsRequery(true);
        setMessage('資料已有更新，請重新查詢後再儲存。');
        return;
      }
      const intent = key ?? `staff-qualification-${crypto.randomUUID()}`;
      setPreview(approved);
      setKey(intent);
      await staffQualificationEditingClient.apply(staffId, submitted, approved, '', intent, controller.current?.signal);
      if (current !== epoch.current) return;
      const refreshed = await load();
      if (current + 1 !== epoch.current) return;
      setMessage(refreshed ? '交通與照顧人數已儲存。' : '資料已儲存，但重新查詢失敗，請重試查詢。');
      await onUpdated();
    } catch (error) {
      if (current === epoch.current) {
        setMessageError(true);
        setNeedsRequery(true);
        setMessage(error instanceof Error ? error.message : '儲存結果未確認，請重試或重新查詢。');
      }
    } finally {
      if (current === epoch.current) setBusy(false);
    }
  };

  return (
    <section ref={unsavedRef} className="staff-qualification-editor" aria-label={editorTitle}>
      <h4 className="staff-op-title">{editorTitle}</h4>
      {snapshot && <>
        <p>交通方式每行填一項，刪除該行即可移除。</p>
        <div className="staff-op-grid staff-qualification-details-grid">
          <label className="staff-op-field">
            {labels.transportation}
            <textarea rows={3} disabled={busy} value={transportation} onChange={event => {
              setTransportation(event.target.value);
              invalidate();
            }} />
          </label>
          <label className="staff-op-field">
            {labels.care_babies}
            <input type="number" min={1} step={1} max={2147483647} disabled={busy} value={careBabies} onChange={event => {
              setCareBabies(event.target.value);
              invalidate();
            }} />
          </label>
        </div>
        {preview && (
          <div aria-label="交通與照顧人數變更預覽">
            {editableFields.filter(field => JSON.stringify(preview.before[field]) !== JSON.stringify(preview.after[field])).map(field => (
              <p key={field}><strong>{labels[field]}</strong>：{display(preview.before[field])} → {display(preview.after[field])}</p>
            ))}
          </div>
        )}
        {busy && <p role="status" className="staff-op-hint">正在處理，請稍候。</p>}
        <div className="staff-op-actions">
          <button type="button" className="staff-secondary-btn" disabled={busy} onClick={() => {
            reset(snapshot);
            setMessageError(false);
            setMessage('已取消變更。');
          }}>取消變更</button>
          <button type="button" className="staff-primary-btn" disabled={busy} onClick={() => void doApply()}>儲存</button>
        </div>
      </>}
      {needsRequery && <button type="button" className="staff-secondary-btn" disabled={busy} onClick={() => void load()}>重試讀取交通與照顧人數</button>}
      {message && <p role={messageError ? 'alert' : 'status'} className={messageError ? 'staff-op-error' : undefined}>{message}</p>}
    </section>
  );
}
