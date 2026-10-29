/** Contract Signing template management; all validation and persistence belong to its API. */
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { ArrowLeft, ArrowRight, Check, ChevronDown, Download, FileSpreadsheet, Link2, List, MousePointer2, Save, Search, ShieldCheck, Trash2, Upload, X, ZoomIn, ZoomOut } from 'lucide-react';
import { contractTemplatesClient as client, type TemplateCatalog, type TemplateCell, type TemplateKey, type TemplateMutation, type TemplatePreview, type TemplateSave, type TemplateSource } from '../api/contract_templates/contract_templates_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedDraft, useUnsavedNavigation } from '../components/UnsavedChanges';
import './ContractTemplatesPage.css';

const COMMAND_STORAGE = 'contract-template-pending-command';
type Pending = { key: TemplateKey; id: string; action: 'save' | 'activate'; versionId?: string; expectedVersion: number; save?: TemplateSave; requiresFile?: boolean; fileName?: string; fileDigest?: string; restored?: boolean };
const templateName = (key: TemplateKey) => key === 'contract_client_copy' ? '客戶服務契約' : '服務人員委任契約';
const label = (text: string) => text.replace(/（[^）]*）|\([^)]*\)/g, '').trim();
const actorLabel = (value: string) => value === 'system' ? '系統隨附' : value === 'system:local_bypass' ? '本機管理員' : value.replace(/^admin:/, '管理員 ');
function column(n: number): string { let name = ''; for (; n > 0; n = Math.floor((n - 1) / 26)) name = String.fromCharCode(65 + (n - 1) % 26) + name; return name; }
function errorText(error: unknown): string { return error instanceof Error ? error.message : '目前無法完成操作，請保留內容後重試。'; }
function initialPending(): Pending | null { try { const raw = sessionStorage.getItem(COMMAND_STORAGE); if (!raw) return null; const value: unknown = JSON.parse(raw); if (typeof value !== 'object' || value === null) return null; const row = value as Record<string, unknown>; return (row.key === 'contract_client_copy' || row.key === 'contract_staff_service') && typeof row.id === 'string' && (row.action === 'save' || row.action === 'activate') && typeof row.expectedVersion === 'number' ? { ...row, restored: true } as unknown as Pending : null; } catch { return null; } }
function persistPending(value: Pending | null) { try { if (value) sessionStorage.setItem(COMMAND_STORAGE, JSON.stringify({ ...value, restored: undefined, save: value.save ? { ...value.save, file: null } : undefined })); else sessionStorage.removeItem(COMMAND_STORAGE); } catch { /* In-page command identity remains available even when session storage is denied. */ } }
async function fileDigest(file: File) { return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer())), byte => byte.toString(16).padStart(2, '0')).join(''); }
function cellStyle(cell: TemplateCell): CSSProperties {
  const s = cell.style;
  return { fontFamily: s.font, fontSize: `${s.size}pt`, fontWeight: s.bold ? 700 : 400, fontStyle: s.italic ? 'italic' : 'normal', color: s.color || undefined, backgroundColor: s.fill || undefined,
    textAlign: ['left', 'right', 'center', 'justify'].includes(s.align) ? s.align as CSSProperties['textAlign'] : 'left', verticalAlign: s.vertical === 'center' ? 'middle' : s.vertical,
    whiteSpace: s.wrap ? 'pre-wrap' : 'pre', borderTop: s.borders.top, borderRight: s.borders.right, borderBottom: s.borders.bottom, borderLeft: s.borders.left };
}

export function ContractTemplatesPage() {
  const [key, setKey] = useState<TemplateKey>(() => initialPending()?.key ?? 'contract_client_copy');
  const [catalog, setCatalog] = useState<TemplateCatalog | null>(null), [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [sourceVersionId, setSourceVersionId] = useState<string | null>(null), [file, setFile] = useState<File | null>(null);
  const [assignments, setAssignments] = useState<Record<string, string>>({}), [baseline, setBaseline] = useState<Record<string, unknown>>({});
  const [inheritMappings, setInheritMappings] = useState(true);
  const [selected, setSelected] = useState('B8'), [fieldKey, setFieldKey] = useState('');
  const [mode, setMode] = useState<'original' | 'mapping' | 'sample'>('mapping'), [tab, setTab] = useState<'settings' | 'list'>('settings');
  const [search, setSearch] = useState(''), [zoom, setZoom] = useState(1), [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const [pending, setPending] = useState<Pending | null>(initialPending), [showVersions, setShowVersions] = useState(false), [activateConfirmation, setActivateConfirmation] = useState(false);
  const input = useRef<HTMLInputElement>(null), recoveryInput = useRef<HTMLInputElement>(null), versionsDialog = useRef<HTMLDialogElement>(null), activationDialog = useRef<HTMLDialogElement>(null), viewport = useRef<HTMLDivElement>(null);
  const { requestLeave } = useUnsavedNavigation();
  const fields = useMemo(() => new Map(catalog?.fields.map(field => [field.key, field]) ?? []), [catalog]);
  const field = fields.get(fieldKey);
  const source: TemplateSource = { file, sourceVersionId, worksheetName: preview?.worksheet_name ?? null, assignments };
  const draft = { 'Excel 模板': file?.name ?? preview?.filename ?? '', '工作表': preview?.worksheet_name ?? '', '欄位映射': assignments };
  const dirty = !!preview && JSON.stringify(draft) !== JSON.stringify(baseline);
  const locked = busy || !!pending;
  const unsaved = useUnsavedDraft('契約模板與欄位映射', draft, { baseline, enabled: !!preview, busy: locked });
  const missing = catalog?.fields.filter(field => field.requiredness === 'required' && !Object.values(assignments).includes(field.key)) ?? [];
  const currentVersion = catalog?.versions.find(version => version.version_id === sourceVersionId);
  const activeVersion = catalog?.versions.find(version => version.version_id === catalog.active_version_id);

  function acceptPreview(value: TemplatePreview, versionId: string | null, uploaded: File | null) {
    setPreview(value); setSourceVersionId(versionId); setFile(uploaded); setAssignments(value.assignments); setSelected(uploaded ? 'A1' : value.assignments.B8 ? 'B8' : Object.keys(value.assignments)[0] ?? 'A1');
    setFieldKey(''); setMode('mapping'); setError(''); setZoom(1);
    if (!uploaded) setBaseline({ 'Excel 模板': value.filename, '工作表': value.worksheet_name, '欄位映射': value.assignments });
    viewport.current?.scrollTo(0, 0);
  }
  useEffect(() => {
    const controller = new AbortController(); let live = true;
    setBusy(true); setError(''); setCatalog(null); setPreview(null);
    void (async () => { const value = await client.query(key, controller.signal); const content = await client.read(key, value.active_version_id, controller.signal); if (live) { setCatalog(value); acceptPreview(content, value.active_version_id, null); } })()
      .catch(reason => { if (live) setError(errorText(reason)); }).finally(() => { if (live) setBusy(false); });
    return () => { live = false; controller.abort(); };
  }, [key]);
  useEffect(() => { setFieldKey(assignments[selected] ?? ''); }, [selected, assignments]);
  useEffect(() => { if (showVersions) versionsDialog.current?.showModal(); else versionsDialog.current?.close(); }, [showVersions]);
  useEffect(() => { if (activateConfirmation) activationDialog.current?.showModal(); else activationDialog.current?.close(); }, [activateConfirmation]);

  async function openVersion(id: string) {
    setBusy(true); setError(''); setShowVersions(false);
    try { const value = await client.read(key, id); acceptPreview(value, id, null); }
    catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }
  async function upload(next: File) {
    if (!next.name.toLowerCase().endsWith('.xlsx')) { setError('請選擇 .xlsx 格式的 Excel 模板。'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const inherited = inheritMappings ? { ...assignments } : {};
      const value = await client.inspect(key, { file: next, sourceVersionId: null, worksheetName: null, assignments: {} });
      acceptPreview({ ...value, assignments: inherited }, null, next);
      setMessage(inheritMappings ? `已載入新模板，沿用目前 ${Object.keys(inherited).length} 個映射位置；請檢查套值並調整有變動的位置。原有模板尚未變更。` : '已載入新模板，請重新指定映射位置；原有模板尚未變更。');
    }
    catch (reason) { setError(errorText(reason)); } finally { setBusy(false); if (input.current) input.current.value = ''; }
  }
  async function changeWorksheet(name: string) {
    setBusy(true); setError('');
    try { const value = await client.inspect(key, { ...source, worksheetName: name, assignments: {} }); setPreview(value); setAssignments({}); setSelected('A1'); setMode('mapping'); }
    catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }
  function updateMapping() {
    if (!field || locked) return;
    setAssignments(previous => ({ ...previous, [selected]: field.key })); setMode('mapping'); setMessage(`${selected} 已對應「${label(field.label)}」，請保存新版本。`);
  }
  function relocateMapping(from: string) {
    if (locked || !selectedCell || layout.covered.has(selected) || assignments[selected]) return;
    setAssignments(previous => { const next = { ...previous, [selected]: previous[from]! }; delete next[from]; return next; });
    setMode('mapping'); setError(''); setMessage(`${from} 的映射已移至 ${selected}，請檢查套值後保存新版本。`);
  }
  async function sample() {
    if (unavailableMappings.length || locked) return;
    setBusy(true); setError('');
    try { const value = await client.inspect(key, source, true); setPreview(value); setMode('sample'); setMessage('目前套入的是虛構資料，請確認資料位置；真實契約仍由案件資料產生。'); }
    catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }
  async function acknowledge(result: TemplateMutation, operation: Pending) {
    persistPending(null); setPending(null); setCatalog(result.catalog);
    if (operation.action === 'save') {
      if (operation.save && preview && !operation.restored) { setSourceVersionId(result.version_id); setFile(null); setBaseline({ 'Excel 模板': preview.filename, '工作表': preview.worksheet_name, '欄位映射': operation.save.assignments }); }
      else acceptPreview(await client.read(key, result.version_id), result.version_id, null);
      setMessage('模板版本已保存，尚未啟用；既有契約不受影響。');
    } else setMessage(result.catalog.active_version_id === result.version_id ? '指定模板已啟用，後續產製使用此版本；既有契約保留原版本。' : '原啟用操作已完成；目前啟用版本已再變更，請查看版本清單。');
  }
  async function runMutation(operation: Pending) {
    persistPending(operation); setPending(operation); setBusy(true); setError(''); setActivateConfirmation(false);
    try {
      const result = operation.action === 'save' && operation.save ? await client.save(operation.key, operation.save)
        : await client.activate(operation.key, operation.versionId!, operation.expectedVersion, operation.id);
      await acknowledge(result, operation);
    } catch (reason) {
      if (reason instanceof ApiHttpError && reason.code !== 'contract_template_idempotency_mismatch' && [400, 401, 403, 404, 409, 422].includes(reason.status)) { persistPending(null); setPending(null); }
      setError(errorText(reason));
    } finally { setBusy(false); }
  }
  async function save() {
    if (!catalog || !preview || locked || unavailableMappings.length) return;
    const id = crypto.randomUUID();
    const saved: TemplateSave = { ...source, assignments: { ...assignments }, expectedVersion: catalog.catalog_version, commandId: id };
    setBusy(true);
    try { const digest = file ? await fileDigest(file) : undefined; await runMutation({ key, id, action: 'save', expectedVersion: catalog.catalog_version, save: saved, requiresFile: !!file, fileName: file?.name, fileDigest: digest }); }
    catch (reason) { setError(errorText(reason)); setBusy(false); }
  }
  async function reattachOriginalFile(next: File) {
    if (!pending?.save) return;
    setBusy(true); setError('');
    try { if (next.name !== pending.fileName || await fileDigest(next) !== pending.fileDigest) throw new Error('這不是原操作使用的 Excel，請選擇相同檔名及內容的原檔。'); setPending({ ...pending, save: { ...pending.save, file: next } }); setMessage('原檔已核對，可使用相同操作識別重送原操作。'); }
    catch (reason) { setError(errorText(reason)); } finally { setBusy(false); if (recoveryInput.current) recoveryInput.current.value = ''; }
  }
  async function recover() {
    if (!pending) return;
    setBusy(true); setError('');
    try { const result = await client.receipt(pending.key, pending.id); if (result) await acknowledge(result, pending); else setError('尚未查到原操作的完成紀錄。請保留此頁，可重送同一筆原操作，不要另建新操作。'); }
    catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }
  async function refreshCatalog() { setBusy(true); try { setCatalog(await client.query(key)); setMessage('版本清單已更新，你的 Excel 與未保存映射仍保留。'); } catch (reason) { setError(errorText(reason)); } finally { setBusy(false); } }
  async function download() {
    if (!sourceVersionId || !preview) return;
    try { const blob = await client.download(key, sourceVersionId); const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = preview.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
    catch (reason) { setError(errorText(reason)); }
  }

  const layout = useMemo(() => {
    const sheet = preview?.sheet, cells = new Map(sheet?.cells.map(cell => [cell.ref, cell]) ?? []), merges = new Map<string, { rowSpan: number; colSpan: number }>(), covered = new Map<string, string>();
    for (const merge of sheet?.merges ?? []) { const anchor = column(merge.start_col) + merge.start_row; merges.set(anchor, { rowSpan: merge.end_row - merge.start_row + 1, colSpan: merge.end_col - merge.start_col + 1 }); for (let r = merge.start_row; r <= merge.end_row; r++) for (let c = merge.start_col; c <= merge.end_col; c++) { const ref = column(c) + r; if (ref !== anchor) covered.set(ref, anchor); } }
    return { cells, merges, covered };
  }, [preview]);
  const selectedCell = layout.cells.get(selected), merged = layout.merges.get(selected);
  const unavailableMappings = Object.entries(assignments).filter(([ref]) => !layout.cells.has(ref) || layout.covered.has(ref));
  function selectCell(ref: string, scroll = false) { const anchor = layout.covered.get(ref) ?? ref; if (!layout.cells.has(anchor)) { setError('這個儲存格不在目前工作表範圍內。'); return; } setSelected(anchor); setTab('settings'); if (scroll) requestAnimationFrame(() => viewport.current?.querySelector(`[data-cell="${anchor}"]`)?.scrollIntoView({ block: 'center', inline: 'nearest' })); }
  const rows = preview ? Array.from({ length: preview.sheet.rows }, (_, i) => i + 1) : [];
  const columns = preview ? Array.from({ length: preview.sheet.columns }, (_, i) => i + 1) : [];
  const mappedEntries = Object.entries(assignments).filter(([ref, value]) => `${ref} ${fields.get(value)?.label ?? value}`.toLowerCase().includes(search.toLowerCase()));
  return <section className="ctm-page" ref={unsaved}>
    <div className="ctm-heading"><div><small>稽核與系統 ／ 契約模板</small><h1>契約模板與欄位映射 <span>{dirty ? '未保存修改' : '版本管理'}</span></h1><p>上傳你編好的 Excel，保留原有內容與版型，再指定資料要填在哪裡。</p></div><label>模板類型<select value={key} disabled={locked} onChange={event => { const next = event.target.value as TemplateKey; requestLeave(() => setKey(next)); }}><option value="contract_client_copy">客戶服務契約</option><option value="contract_staff_service">服務人員委任契約</option></select></label></div>
    <div className="ctm-steps"><span><Check />上傳 Excel 模板</span><i /><strong><b>2</b>調整映射欄位</strong><i /><button disabled={locked || !preview || unavailableMappings.length > 0} onClick={() => void sample()}><b>3</b>檢查套值結果</button></div>
    <div className="ctm-upload" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); const next = event.dataTransfer.files[0]; if (next && !locked) requestLeave(() => void upload(next)); }}>
      <div className="ctm-file"><FileSpreadsheet /><div><strong>{preview?.filename ?? '請先讀取或上傳 Excel 模板'}</strong><span>{file ? '新上傳，尚未保存' : currentVersion ? `${currentVersion.number === 0 ? '內建模板' : `保存版本 ${currentVersion.number}`} · ${preview?.sheet.rows ?? 0} 列 · ${preview?.sheet.merges.length ?? 0} 組合併格` : '讀取中'}</span></div></div>
      <div className="ctm-upload-actions"><label className="ctm-inherit"><input type="checkbox" aria-label="沿用目前版本映射" checked={inheritMappings} disabled={locked || !preview} onChange={event => setInheritMappings(event.target.checked)} />沿用目前版本映射<small>套用於下一次上傳</small></label>{sourceVersionId && <button className="ctm-btn" disabled={locked} onClick={() => void download()}><Download />下載此版 Excel</button>}<button className="ctm-btn" disabled={locked || !preview} onClick={() => input.current?.click()}><Upload />上傳新模板</button><input type="file" accept=".xlsx" ref={input} hidden aria-label="上傳 Excel 模板" onChange={event => { const next = event.target.files?.[0]; if (next) requestLeave(() => void upload(next)); }} /></div>
    </div>
    {error && <div className="ctm-error" role="alert">{error}<button onClick={() => void refreshCatalog()} disabled={busy}>重新讀取版本清單</button></div>}
    {pending && <div className="ctm-recovery" role="status"><strong>正在核對原操作結果，其他編輯暫停。</strong><button className="ctm-btn" disabled={busy} onClick={() => void recover()}>核對原操作結果</button>{((pending.save && (!pending.requiresFile || pending.save.file)) || pending.action === 'activate') && <button className="ctm-btn" disabled={busy} onClick={() => void runMutation(pending)}>重送同一筆原操作</button>}{pending.requiresFile && !pending.save?.file && <><button className="ctm-btn" disabled={busy} onClick={() => recoveryInput.current?.click()}>重新選取原 Excel 以核對</button><input ref={recoveryInput} type="file" accept=".xlsx" hidden aria-label="核對原 Excel" onChange={event => { const next = event.target.files?.[0]; if (next) void reattachOriginalFile(next); }} /></>}</div>}
    {message && <p className="ctm-message" role="status">{message}</p>}
    <div className="ctm-instruction"><MousePointer2 /><span><strong>點選契約中的儲存格，再從右側選擇要自動帶入的資料。</strong> 上傳時可沿用畫面目前的映射；欄位位置有變動時請調整，並檢查示範套值。系統不會自動判斷新條文與欄位是否相符。</span></div>
    {unavailableMappings.length > 0 && <div className="ctm-mapping-review" role="alert"><strong>有 {unavailableMappings.length} 個原映射位置需要調整</strong><p>設定仍保留。請先在契約中選取新的空閒位置，再移動映射；全部處理後才能套值與保存。</p><ul>{unavailableMappings.map(([ref, field]) => <li key={ref}><span><b>{ref}</b> · {label(fields.get(field)?.label ?? field)} · {layout.covered.has(ref) ? '已變成合併格內部' : '不在新工作表範圍內'}</span><button className="ctm-btn" disabled={locked || !selectedCell || !!assignments[selected] || layout.covered.has(selected)} onClick={() => relocateMapping(ref)}>將 {ref} 移至 {selected}</button><button className="ctm-btn" disabled={locked} onClick={() => setAssignments(previous => { const next = { ...previous }; delete next[ref]; return next; })}>不沿用 {ref}</button></li>)}</ul></div>}
    {!preview && <div className="ctm-empty">{busy ? '正在讀取模板與版本…' : '目前無法載入模板，請重新讀取。'}</div>}
    {preview && <div className="ctm-workspace"><section className="ctm-preview-section"><div className="ctm-sheet"><div className="ctm-sheet-toolbar"><strong><FileSpreadsheet />Excel 模板預覽</strong><div className="ctm-modes" role="group" aria-label="契約預覽模式"><button className={mode === 'original' ? 'active' : ''} aria-pressed={mode === 'original'} disabled={locked} onClick={() => setMode('original')}>原始模板</button><button className={mode === 'mapping' ? 'active' : ''} aria-pressed={mode === 'mapping'} disabled={locked} onClick={() => setMode('mapping')}>映射位置</button><button className={mode === 'sample' ? 'active' : ''} aria-pressed={mode === 'sample'} disabled={locked || unavailableMappings.length > 0} onClick={() => void sample()}>示範套值</button></div></div>
      <div className="ctm-formula"><form onSubmit={event => { event.preventDefault(); const ref = new FormData(event.currentTarget).get('address'); if (typeof ref === 'string' && /^[A-Z]{1,3}[1-9][0-9]*$/.test(ref.toUpperCase())) selectCell(ref.toUpperCase(), true); }}><input name="address" key={selected} defaultValue={selected} disabled={locked} aria-label="儲存格位置" /><button disabled={locked} aria-label="前往儲存格"><ChevronDown /></button></form><i>fx</i><span>{fields.get(assignments[selected] ?? '') ? label(fields.get(assignments[selected]!)!.label) : selectedCell?.value || '空白儲存格'}</span></div>
      <div className="ctm-sheet-viewport" ref={viewport}><table className="ctm-grid" style={{ width: 32 + columns.reduce((sum, col) => sum + (preview.sheet.column_widths[col] ?? 8.43) * 7, 0), zoom }} aria-label={`${preview.worksheet_name} 契約儲存格`}><colgroup><col style={{ width: 32 }} />{columns.map(col => <col key={col} style={{ width: (preview.sheet.column_widths[col] ?? 8.43) * 7 }} />)}</colgroup><thead><tr><th className="ctm-corner" />{columns.map(col => <th key={col} scope="col">{column(col)}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row} style={{ height: (preview.sheet.row_heights[row] ?? 15) * 4 / 3 }}><th scope="row" className="ctm-row-head">{row}</th>{columns.map(col => { const ref = column(col) + row; if (layout.covered.has(ref)) return null; const cell = layout.cells.get(ref); if (!cell) return null; const merge = layout.merges.get(ref), assigned = assignments[ref], mapped = assigned && fields.get(assigned), images = preview.sheet.images.filter(image => image.row === row && image.col === col); return <td key={ref} data-cell={ref} rowSpan={merge?.rowSpan} colSpan={merge?.colSpan} className={`${ref === selected ? 'selected' : ''} ${mapped && mode !== 'original' ? 'mapped' : ''}`} style={cellStyle(cell)} tabIndex={ref === selected ? 0 : -1} aria-label={`${ref} ${mapped ? label(mapped.label) : cell.value || '空白'}`} aria-selected={ref === selected} onClick={() => { if (!locked) selectCell(ref); }} onKeyDown={event => { if (locked) return; if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectCell(ref); document.getElementById('ctm-field')?.focus(); } }}><div className="ctm-cell-content">{mapped && mode === 'mapping' ? <span className="ctm-cell-token"><Link2 />{label(mapped.label)}</span> : mapped && mode === 'sample' ? preview.sample_values[ref] ?? '尚未預覽' : cell.value}</div>{images.map((image, index) => <img key={index} src={image.data_url} alt="Excel 內嵌圖片" style={{ position: 'absolute', left: image.left, top: image.top, width: image.width, height: image.height, maxWidth: 'none', pointerEvents: 'none' }} />)}</td>; })}</tr>)}</tbody></table></div>
      <div className="ctm-sheet-bottom"><label><FileSpreadsheet /><select aria-label="工作表" value={preview.worksheet_name} disabled={locked} onChange={event => { const name = event.target.value; requestLeave(() => void changeWorksheet(name)); }}>{preview.worksheet_names.map(name => <option key={name}>{name}</option>)}</select></label><div>{preview.sheet.rows} 列 × {preview.sheet.columns} 欄<button aria-label="縮小預覽" onClick={() => setZoom(value => Math.max(.6, Math.round((value - .1) * 10) / 10))}><ZoomOut /></button>{Math.round(zoom * 100)}%<button aria-label="放大預覽" onClick={() => setZoom(value => Math.min(1.3, Math.round((value + .1) * 10) / 10))}><ZoomIn /></button></div></div></div><p className="ctm-caption">藍框：已映射　橘框：目前選取。示範套值使用虛構資料；正式 PDF 請由案件流程核對。</p></section>
      <aside className="ctm-sidebar"><div className="ctm-settings"><div className="ctm-tabs" role="tablist" aria-label="映射檢視"><button role="tab" aria-selected={tab === 'settings'} className={tab === 'settings' ? 'active' : ''} onClick={() => setTab('settings')}>欄位設定</button><button role="tab" aria-selected={tab === 'list'} className={tab === 'list' ? 'active' : ''} onClick={() => setTab('list')}>映射清單 <span>{Object.keys(assignments).length}</span></button></div>
        {tab === 'settings' ? <div className="ctm-settings-body"><div className="ctm-selection"><small><MousePointer2 />目前選取的儲存格</small><strong>{selected}</strong><p>{merged ? `合併儲存格（${merged.rowSpan} 列 × ${merged.colSpan} 欄）` : '單一儲存格'} · 原始內容：{selectedCell?.value || '空白'}</p></div><label htmlFor="ctm-field">要帶入什麼資料？</label><select id="ctm-field" value={fieldKey} disabled={locked} onChange={event => setFieldKey(event.target.value)}><option value="">請選擇系統欄位</option>{catalog?.fields.map(field => <option key={field.key} value={field.key}>{label(field.label)}</option>)}</select><p className="ctm-help">資料仍由原功能提供，不在模板中重新計算。</p>{field && <dl className="ctm-field-info"><div><dt>欄位規則</dt><dd>{{ required: '必填', conditional: '依案件條件帶入', optional: '可留白' }[field.requiredness]}</dd></div><div><dt>示範內容</dt><dd>{field.example}</dd></div></dl>}{field && selectedCell?.value && <p className="ctm-warning">這格有原始文字，套值時會以系統資料取代。</p>}<div className="ctm-mapping-actions"><button className="ctm-btn primary" disabled={locked || !field} onClick={updateMapping}><Link2 />{assignments[selected] ? '更新映射' : '套用映射'}</button><button className="ctm-btn" disabled={locked || !assignments[selected]} aria-label="移除此格映射" onClick={() => { setAssignments(previous => { const next = { ...previous }; delete next[selected]; return next; }); setMode('mapping'); }}><Trash2 /></button></div><p className="ctm-help">合併儲存格只會寫入左上角位置。</p></div> : <div className="ctm-settings-body"><label className="ctm-search"><Search /><input placeholder="搜尋欄位或儲存格" aria-label="搜尋映射" value={search} onChange={event => setSearch(event.target.value)} /></label><div className="ctm-mapping-list">{mappedEntries.map(([ref, field]) => <button key={ref} disabled={locked} onClick={() => selectCell(ref, true)}><span>{ref}</span><strong>{label(fields.get(field)?.label ?? field)}</strong><ArrowRight /></button>)}{!mappedEntries.length && <p className="ctm-help">尚無符合的映射，請在左側選取儲存格設定。</p>}</div></div>}
        <div className="ctm-settings-footer"><FileSpreadsheet />條文、欄寬與合併格由 Excel 決定；此處設定資料位置。</div></div>
        <div className="ctm-summary"><h3><ShieldCheck />映射設定進度</h3><p><span>已設定映射</span><strong>{Object.keys(assignments).length} 個位置</strong></p><p><span>必要資料待設定</span><strong className={missing.length ? 'pending' : ''}>{missing.length} 項</strong></p>{missing.length > 0 && <details><summary>查看尚未設定的必要資料</summary><ul>{missing.map(field => <li key={field.key}>{label(field.label)}</li>)}</ul></details>}{preview.sheet.formula_cells.length > 0 && <p className="ctm-warning">公式不執行；保存前須將公式格設為映射，或在 Excel 轉為固定內容。</p>}</div>
      </aside></div>}
    <div className="ctm-bottom"><div><ShieldCheck /><span>目前啟用：{activeVersion ? activeVersion.number === 0 ? '內建模板' : `版本 ${activeVersion.number}` : '讀取中'}<small>新模板另存版本，既有契約保持原版本。</small></span></div><div className="ctm-bottom-actions"><button className="ctm-btn" disabled={locked || !catalog} onClick={() => setShowVersions(true)}><List />版本清單</button><button className="ctm-btn" disabled={locked || !dirty || !preview || missing.length > 0 || unavailableMappings.length > 0} onClick={save}><Save />保存版本</button><button className="ctm-btn primary" disabled={locked || dirty || !sourceVersionId || sourceVersionId === catalog?.active_version_id} onClick={() => setActivateConfirmation(true)}>啟用此版本<ArrowRight /></button></div></div>
    <dialog ref={versionsDialog} aria-labelledby="ctm-versions-title" className="ctm-dialog" onCancel={() => setShowVersions(false)}><div className="ctm-dialog-head"><h2 id="ctm-versions-title">模板版本清單</h2><button aria-label="關閉版本清單" onClick={() => setShowVersions(false)}><X /></button></div><p className="ctm-dialog-note">{templateName(key)} · 保存不會自動啟用，歷史版本持續保留。</p>{catalog?.versions.slice().reverse().map(version => <div className="ctm-version-row" key={version.version_id}><div><strong>{version.number === 0 ? '內建模板' : `版本 ${version.number}`} {version.version_id === catalog.active_version_id && <span>使用中</span>}</strong><p>{version.filename}</p><small>{version.created_at ? new Date(version.created_at).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' }) : '系統隨附'} · {actorLabel(version.created_by)}</small></div><button className="ctm-btn" onClick={() => { setShowVersions(false); requestLeave(() => void openVersion(version.version_id)); }}>查看</button></div>)}</dialog>
    <dialog ref={activationDialog} aria-labelledby="ctm-activate-title" className="ctm-dialog" onCancel={() => setActivateConfirmation(false)}><div className="ctm-dialog-head"><h2 id="ctm-activate-title">啟用此模板版本？</h2><button aria-label="關閉啟用確認" onClick={() => setActivateConfirmation(false)}><X /></button></div><p className="ctm-dialog-note">{currentVersion?.filename} · 版本 {currentVersion?.number ?? ''}</p><p className="ctm-dialog-copy">啟用後，後續明確產製的新契約來源會使用此模板與映射。已保存的契約、PDF 及簽回文件保留原版本。</p><div className="ctm-dialog-actions"><button className="ctm-btn" onClick={() => setActivateConfirmation(false)}><ArrowLeft />繼續檢查</button><button className="ctm-btn primary" onClick={() => { if (catalog && sourceVersionId) void runMutation({ key, id: crypto.randomUUID(), action: 'activate', versionId: sourceVersionId, expectedVersion: catalog.catalog_version }); }}>確認啟用</button></div></dialog>
  </section>;
}
