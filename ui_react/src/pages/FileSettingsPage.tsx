import { useUnsavedDraft } from '../components/UnsavedChanges';
import { useEffect, useRef, useState } from 'react';
import { Folder, Upload } from 'lucide-react';
import { fileSettingsClient, type FileSettings, type FileSettingsInput } from '../api/system/file_settings_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import './FileSettingsPage.css';

type Draft = { photo: string; resume: string; timeout: string; noTimeout: boolean };
const draftOf = (value: FileSettings): Draft => ({
  photo: String(value.photo_max_bytes / 1048576), resume: String(value.resume_max_bytes / 1048576),
  timeout: String(value.timeout_seconds || 60), noTimeout: value.timeout_seconds === 0 });
const timeLabel = (seconds: number) => seconds === 0 ? '不設定這一層的等待上限' : `${seconds} 秒`;
const sizeLabel = (bytes: number) => `${Number((bytes / 1048576).toFixed(4))} MiB`;

function errorText(error: unknown, saving = false): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '登入已失效，請重新登入後操作。';
    if (error.status === 403) return '僅 root 管理員可調整檔案設定。';
    if (error.status === 409) return '設定已變更或正在儲存，請重新讀取後再確認。';
    if (error.status === 422) return error.message;
  }
  return saving ? '儲存結果尚未確認，請重新讀取設定；不要直接認定儲存失敗。' : '目前無法讀取檔案設定，請稍後重試。';
}

export function FileSettingsPage() {
  const [current, setCurrent] = useState<FileSettings | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [preview, setPreview] = useState<FileSettingsInput | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saveUnknown, setSaveUnknown] = useState(false);
  const fields = useRef<Record<string, HTMLInputElement | null>>({});
  const active = useRef(true);

  const load = async () => {
    setLoading(true); setError(null); setMessage(null); setPreview(null);
    try {
      const value = await fileSettingsClient.read();
      if (!active.current) return;
      setCurrent(value); setDraft(draftOf(value)); setSaveUnknown(false); setFieldErrors({});
    } catch (caught) { if (active.current) setError(errorText(caught)); }
    finally { if (active.current) setLoading(false); }
  };
  useEffect(() => { active.current = true; void load(); return () => { active.current = false; }; }, []);

  const edit = (changes: Partial<Draft>) => {
    setDraft(value => value ? { ...value, ...changes } : value); setPreview(null); setFieldErrors({}); setError(null); setMessage(null);
  };
  const createPreview = (): FileSettingsInput | null => {
    if (!draft || !current || saving || saveUnknown) return null;
    const problems: Record<string, string> = {};
    const photo = Math.round(Number(draft.photo) * 1048576);
    const resume = Math.round(Number(draft.resume) * 1048576);
    const timeout = draft.noTimeout ? 0 : Number(draft.timeout);
    if (!Number.isSafeInteger(photo) || photo <= 0) problems.photo = '請輸入大於 0 的照片容量。';
    if (!Number.isSafeInteger(resume) || resume <= 0) problems.resume = '請輸入大於 0 的履歷容量。';
    if (!Number.isSafeInteger(timeout) || timeout < 0 || timeout > 2147483 || (!draft.noTimeout && timeout === 0)) problems.timeout = '請填有效的整數秒數，或勾選不設定等待上限。';
    setFieldErrors(problems); setError(null); setMessage(null);
    if (Object.keys(problems).length) { setPreview(null); fields.current[Object.keys(problems)[0]]?.focus(); return null; }
    const value = { photo_max_bytes: photo, resume_max_bytes: resume, timeout_seconds: timeout };
    setPreview(value);
    return value;
  };
  const save = async (input: FileSettingsInput | null = preview) => {
    if (!input || !current || saving || saveUnknown) return;
    setSaving(true); setError(null); setMessage(null);
    try {
      const value = await fileSettingsClient.save(input, current.version);
      if (!active.current) return;
      setCurrent(value); setDraft(draftOf(value)); setPreview(null);
      setMessage('檔案設定已儲存，容量與等待時間已生效。');
    } catch (caught) {
      if (!active.current) return;
      const knownRejection = caught instanceof ApiHttpError && [401, 403, 409, 422].includes(caught.status);
      setSaveUnknown(!knownRejection); setPreview(null); setError(errorText(caught, true));
    } finally { if (active.current) setSaving(false); }
  };
  const unsavedRef = useUnsavedDraft('檔案設定', draft ? { '照片單檔上限（MiB）': draft.photo, '履歷 PDF 上限（MiB）': draft.resume, '等待時間（秒）': draft.noTimeout ? '不設上限' : draft.timeout } : {}, { enabled: !!draft && !!current, busy: saving || saveUnknown, save: () => save(preview ?? createPreview()), baseline: current ? { '照片單檔上限（MiB）': draftOf(current).photo, '履歷 PDF 上限（MiB）': draftOf(current).resume, '等待時間（秒）': current.timeout_seconds === 0 ? '不設上限' : draftOf(current).timeout } : null });
  const disabled = loading || saving || saveUnknown;
  const ref = (name: string) => (node: HTMLInputElement | null) => { fields.current[name] = node; };
  const fieldError = (name: string) => fieldErrors[name] && <p className="file-settings-error" id={`file-${name}-error`} role="alert">{fieldErrors[name]}</p>;
  return <main ref={unsavedRef} className="file-settings-page" aria-labelledby="file-settings-title">
    <header className="file-settings-heading"><div><p className="file-settings-eyebrow">稽核與系統 ／ 檔案設定</p><h1 id="file-settings-title">NAS 檔案與上傳設定</h1><p>查看目前儲存位置，調整照片、履歷的檔案大小與等待時間。</p></div><button type="button" className="file-settings-button" disabled={saving || loading} onClick={() => void load()}>重新讀取設定</button></header>
    {loading && <p role="status">正在讀取檔案設定…</p>}
    {error && <p className="file-settings-error file-settings-feedback" role="alert">{error}</p>}
    {message && <p className="file-settings-success file-settings-feedback" role="status">{message}</p>}
    {draft && current && <>
      <div className="file-settings-layout"><div className="file-settings-stack">
        <section className="file-settings-card" aria-labelledby="file-location-title"><div className="file-settings-section-title"><Folder size={20} aria-hidden="true"/><h2 id="file-location-title">儲存位置</h2></div>
          <dl className="file-settings-mapping"><div><dt>程式使用的位置（容器內）</dt><dd><code>{current.container_root ?? '尚未設定儲存位置'}</code></dd></div></dl>
          <p className="file-settings-hint">此處唯讀，依目前執行設定顯示。對應的 NAS 資料夾由 Compose 掛載決定；容器無法直接得知 NAS 上的實體路徑。</p>
        </section>
        <section className="file-settings-card" aria-labelledby="file-transfer-title"><div className="file-settings-section-title"><Upload size={20} aria-hidden="true"/><h2 id="file-transfer-title">檔案大小與等待時間</h2></div><p className="file-settings-hint">超過上限時明確提示，不自動壓縮，也不覆蓋已存檔案。</p>
          <div className="file-settings-grid"><div><label htmlFor="file-photo-limit">照片單檔上限（MiB）</label><input ref={ref('photo')} id="file-photo-limit" type="number" step="any" value={draft.photo} disabled={disabled} aria-invalid={Boolean(fieldErrors.photo)} aria-describedby="file-photo-error" onChange={event => edit({ photo: event.target.value })}/>{fieldError('photo')}</div><div><label htmlFor="file-resume-limit">履歷 PDF 單檔上限（MiB）</label><input ref={ref('resume')} id="file-resume-limit" type="number" step="any" value={draft.resume} disabled={disabled} aria-invalid={Boolean(fieldErrors.resume)} aria-describedby="file-resume-error" onChange={event => edit({ resume: event.target.value })}/>{fieldError('resume')}</div></div>
          <label htmlFor="file-timeout">檔案操作等待時間（秒）</label><input className="file-settings-timeout" ref={ref('timeout')} id="file-timeout" type="number" step="1" value={draft.timeout} disabled={disabled || draft.noTimeout} aria-invalid={Boolean(fieldErrors.timeout)} aria-describedby="file-wait-help file-timeout-error" onChange={event => edit({ timeout: event.target.value })}/>
          <p className="file-settings-hint" id="file-wait-help">預設 60 秒（1 分鐘）；網路較慢時可延長等待。其他一般 API 不受影響。</p>{fieldError('timeout')}
          <label className="file-settings-check"><input type="checkbox" checked={draft.noTimeout} disabled={disabled} onChange={event => edit({ noTimeout: event.target.checked })}/>不設定這一層的等待上限</label>
          {draft.noTimeout && <p className="file-settings-hint">瀏覽器或網路入口仍可能中斷連線。</p>}
        </section>
      </div><aside className="file-settings-card file-settings-current" aria-label="目前儲存的設定"><h2>目前儲存的設定</h2><dl><div><dt>照片單檔</dt><dd>{sizeLabel(current.photo_max_bytes)}</dd></div><div><dt>履歷單檔</dt><dd>{sizeLabel(current.resume_max_bytes)}</dd></div><div><dt>等待時間</dt><dd>{timeLabel(current.timeout_seconds)}</dd></div></dl></aside></div>
      <div className="file-settings-actions"><button type="button" className="file-settings-button" disabled={disabled} onClick={() => { setDraft(draftOf(current)); setPreview(null); setError(null); setFieldErrors({}); setMessage(null); }}>取消變更</button><button type="button" className="file-settings-button primary" disabled={disabled} onClick={createPreview}>預覽變更</button></div>
      {preview && <section className="file-settings-card file-settings-preview" aria-labelledby="file-change-title"><h2 id="file-change-title">變更內容預覽</h2><p className="file-settings-hint">核對後按「儲存設定」，容量與等待時間即時生效。</p><div className="file-settings-table-wrap"><table><thead><tr><th scope="col">項目</th><th scope="col">目前設定</th><th scope="col">調整為</th></tr></thead><tbody>{[
        ['照片單檔上限', sizeLabel(current.photo_max_bytes), sizeLabel(preview.photo_max_bytes)],
        ['履歷單檔上限', sizeLabel(current.resume_max_bytes), sizeLabel(preview.resume_max_bytes)],
        ['等待時間', timeLabel(current.timeout_seconds), timeLabel(preview.timeout_seconds)],
      ].map(row => <tr key={row[0]}>{row.map((cell, index) => <td key={index}>{cell}</td>)}</tr>)}</tbody></table></div><div className="file-settings-actions"><button type="button" className="file-settings-button primary" disabled={saving} onClick={() => void save()}>{saving ? '正在儲存…' : '儲存設定'}</button></div></section>}
    </>}
  </main>;
}
