import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import './UnsavedChanges.css';

export type UnsavedChange = { label: string; before: string; after: string };
type Entry = { name: string; changes: UnsavedChange[]; busy: boolean; review: () => void; discard: () => void; save?: () => Promise<void> | void };
type Navigation = { proceed: () => void };
type Guard = { update: (id: string, entry: Entry | null) => void; request: (proceed: () => void) => void; pending: boolean };
const GuardContext = createContext<Guard | null>(null);

export function useUnsavedNavigation() {
  const guard = useContext(GuardContext);
  const request = guard?.request;
  const requestLeave = useCallback((proceed: () => void) => {
    if (request) request(proceed); else proceed();
  }, [request]);
  return { requestLeave, pending: guard?.pending ?? false };
}

export function useUnsavedChanges(name: string, changes: UnsavedChange[], options: { busy?: boolean; save?: Entry['save']; review?: () => void; discard?: () => void } = {}) {
  const update = useContext(GuardContext)?.update;
  const id = useId();
  const ref = useRef<HTMLElement | null>(null);
  const latest = useRef(options);
  latest.current = options;
  const signature = JSON.stringify(changes);
  const busy = options.busy ?? false;
  const canSave = Boolean(options.save);
  useLayoutEffect(() => {
    if (!update) return;
    const currentChanges = JSON.parse(signature) as UnsavedChange[];
    update(id, { name, changes: currentChanges, busy,
      review: () => {
        if (latest.current.review) { latest.current.review(); return; }
        const root = ref.current;
        if (!root) return;
        for (let parent: HTMLElement | null = root; parent; parent = parent.parentElement) {
          if (parent instanceof HTMLDetailsElement) parent.open = true;
        }
        root.scrollIntoView?.({ block: 'center' });
        root.querySelector<HTMLElement>('input:not(:disabled), textarea:not(:disabled), select:not(:disabled), button:not(:disabled)')?.focus();
      },
      discard: () => latest.current.discard?.(),
      ...(canSave ? { save: () => latest.current.save?.() } : {}),
    });
  }, [update, id, name, signature, busy, canSave]);
  useLayoutEffect(() => () => update?.(id, null), [update, id]);
  return useCallback((node: HTMLElement | null) => { ref.current = node; }, []);
}

type Draft = Record<string, unknown>;
const valueText = (value: unknown): string => value === null || value === undefined || value === '' ? '未填寫'
  : typeof value === 'boolean' ? value ? '是' : '否'
  : Array.isArray(value) ? value.map(valueText).join('、') || '無' : typeof value === 'object'
    ? Object.entries(value).map(([key, item]) => `${key}：${valueText(item)}`).join('；') : String(value);

/** Only pass presentation fields. Passwords, keys and bank data use a presence flag, never their values. */
export function useUnsavedDraft(name: string, draft: Draft, options: {
  baseline?: Draft | null; enabled?: boolean; resetKey?: unknown; busy?: boolean; save?: Entry['save']; review?: () => void; discard?: () => void;
} = {}) {
  const initial = useRef(draft);
  const [, recheck] = useState(0);
  const reset = useRef(options.resetKey);
  const wasEnabled = useRef(options.enabled !== false);
  // The owner changes resetKey only after an acknowledged save or explicit editor reset.
  if ((!Object.is(reset.current, options.resetKey) && options.resetKey !== null && options.resetKey !== undefined && options.resetKey !== false) || options.enabled === false || !wasEnabled.current) {
    initial.current = draft;
  }
  wasEnabled.current = options.enabled !== false;
  reset.current = options.resetKey;
  const baseline = options.baseline ?? initial.current;
  const changes = options.enabled === false ? [] : Object.keys(draft).filter(key => JSON.stringify(draft[key]) !== JSON.stringify(baseline[key]))
    .map(key => ({ label: key, before: valueText(baseline[key]), after: valueText(draft[key]) }));
  const ref = useUnsavedChanges(name, changes, options);
  return Object.assign(ref, { markSaved: () => { initial.current = draft; recheck(value => value + 1); } });
}

export function UnsavedChangesProvider({ children }: { children: ReactNode }) {
  const entries = useRef(new Map<string, Entry>());
  const [revision, setRevision] = useState(0);
  const [navigation, setNavigation] = useState<Navigation | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveFinished, setSaveFinished] = useState(false);
  const [saveError, setSaveError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const leaving = useRef(false);
  const update = useCallback((id: string, entry: Entry | null) => {
    const previous = entries.current.get(id);
    if (entry) entries.current.set(id, entry); else entries.current.delete(id);
    if (JSON.stringify(previous && [previous.name, previous.changes, previous.busy, Boolean(previous.save)]) !== JSON.stringify(entry && [entry.name, entry.changes, entry.busy, Boolean(entry.save)])) setRevision(value => value + 1);
  }, []);
  const request = useCallback((proceed: () => void) => {
    if (leaving.current) { proceed(); return; }
    const active = [...entries.current.values()];
    if (!active.some(entry => entry.busy || entry.changes.length)) { proceed(); return; }
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSaveError(''); setNavigation(current => current ?? { proceed });
  }, []);
  const cancel = useCallback(() => { dialog.current?.close(); setNavigation(null); setSaveFinished(false); setSaveError(''); opener.current?.focus(); }, []);
  const active = useMemo(() => navigation ? [...entries.current.values()] : [], [navigation, revision]);
  const dirty = active.filter(entry => entry.changes.length);
  const busy = saving || active.some(entry => entry.busy);
  const canSave = dirty.length === 1 && Boolean(dirty[0].save);
  const hasPending = [...entries.current.values()].some(entry => entry.busy || entry.changes.length);
  useEffect(() => {
    if (!hasPending) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', unload);
    return () => window.removeEventListener('beforeunload', unload);
  }, [hasPending]);
  useEffect(() => {
    if (!navigation) return;
    const element = dialog.current;
    element?.showModal();
    element?.focus({ preventScroll: true });
    if (element) element.scrollTop = 0;
    return () => element?.close();
  }, [navigation]);
  useEffect(() => {
    if (saveFinished && navigation) {
      if (active.some(entry => entry.busy)) { if (saving) setSaving(false); return; }
      setSaveFinished(false); setSaving(false);
      if (!saveError && !dirty.length) {
        setNavigation(null); navigation.proceed();
      } else if (!saveError) {
        setSaveError('尚有變更未儲存，請確認原畫面的儲存結果。');
      }
    }
  }, [revision, saveFinished, saving, navigation, active, dirty.length, saveError]);
  const save = async () => {
    const entry = dirty[0];
    if (!entry?.save || !canSave || busy) return;
    setSaving(true); setSaveError('');
    try { await entry.save(); setSaveFinished(true); }
    catch { setSaving(false); setSaveError('尚未完成儲存，請返回原畫面確認錯誤與變更內容。'); }
  };
  const context = useMemo(() => ({ update, request, pending: navigation !== null }), [update, request, navigation]);
  return <GuardContext value={context}>{children}{navigation && createPortal(
    <dialog ref={dialog} className="unsaved-dialog" aria-labelledby="unsaved-title" onCancel={event => { event.preventDefault(); if (!busy) cancel(); }}>
      <h2 id="unsaved-title">尚有未儲存的變更</h2>
      <p>離開會捨棄以下內容。請先儲存，或確認捨棄後離開。</p>
      {dirty.map((entry, index) => <section key={index}><h3>{entry.name}</h3><div className="unsaved-table"><table><thead><tr><th>欄位</th><th>變更前</th><th>變更後</th></tr></thead><tbody>{entry.changes.map((change, i) => <tr key={i}><th scope="row">{change.label}</th><td>{change.before}</td><td>{change.after}</td></tr>)}</tbody></table></div></section>)}
      {busy && <p role="status">操作進行中或結果尚未確認，請留在原畫面完成確認。</p>}
      {dirty.length > 0 && !canSave && <p id="unsaved-save-guidance">此處無法一次儲存這些變更。請選擇「繼續編輯」，回原表單完成儲存。</p>}
      {saveError && <p role="alert">{saveError}</p>}
      <div className="unsaved-actions">
        <button type="button" disabled={saving} onClick={() => { cancel(); dirty[0]?.review(); }}>繼續編輯</button>
        <button type="button" disabled={busy} onClick={() => {
          leaving.current = true;
          try { dirty.forEach(entry => entry.discard()); dialog.current?.close(); setNavigation(null); navigation.proceed(); }
          finally { leaving.current = false; }
        }}>捨棄變更並離開</button>
        {dirty.length > 0 && <button type="button" className="unsaved-save" disabled={busy || !canSave} aria-describedby={!canSave ? 'unsaved-save-guidance' : undefined} onClick={() => void save()}>儲存變更並離開</button>}
      </div>
    </dialog>, document.body)}</GuardContext>;
}
