import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import {
  staffWebFileError, staffWebProfileClient, webProfileCategoryLabels,
  type WebProfileCategory, type WebProfileFolder, type WebProfileFolderFile, type WebProfilePublicationInput,
} from '../api/staff/staff_web_profile_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import './StaffWebFileManagement.css';

const categories: WebProfileCategory[] = ['photo', 'certificate', 'other'];
const supportedPhotos = 'image/jpeg,image/png,image/webp';
type DraftPhoto = { file: File; uploadId: string };
type UploadDraft = {
  category: WebProfileCategory;
  folder: WebProfileFolder | undefined;
  photos: DraftPhoto[];
  expiry: string;
};
type Message = { text: string; error?: boolean };

function FileDialog({ children, title, owner, busy, onClose }: {
  children: ReactNode; title: string; owner: string; busy: boolean; onClose: () => void;
}) {
  const heading = useId();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const modal = ref.current;
    modal?.showModal();
    return () => modal?.close();
  }, []);

  return createPortal(<dialog
    ref={ref}
    className="staff-web-files-dialog"
    aria-labelledby={heading}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}
  >
    <header>
      <div><p>{owner}</p><h3 id={heading}>{title}</h3></div>
      <button type="button" className="staff-secondary-btn" aria-label={`關閉${title}`} disabled={busy} onClick={onClose}>關閉</button>
    </header>
    {children}
  </dialog>, document.body);
}

export function StaffWebFileManagement({ staffId, staffName, canWrite }: {
  staffId: number; staffName: string; canWrite: boolean;
}) {
  const [folders, setFolders] = useState<WebProfileFolder[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<Message | null>(null);
  const [dialogMessage, setDialogMessage] = useState<Message | null>(null);
  const [folderId, setFolderId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<WebProfileFolderFile | null>(null);
  const [upload, setUpload] = useState<UploadDraft | null>(null);
  const [confirmed, setConfirmed] = useState<WebProfilePublicationInput | null>(null);
  const [busy, setBusy] = useState(false);
  const lifecycle = useRef<AbortController | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const { requestLeave } = useUnsavedNavigation();
  const sectionTitle = useId();

  useEffect(() => {
    const controller = new AbortController();
    lifecycle.current = controller;
    void staffWebProfileClient.folders(staffId, controller.signal).then(
      items => { if (!controller.signal.aborted) setFolders(items); },
      error => {
        if (!controller.signal.aborted) {
          setMessage({ text: staffWebFileError(error, '無法讀取照片資料夾。'), error: true });
        }
      },
    ).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [staffId]);

  const closeDialog = () => {
    setUpload(null);
    setConfirmed(null);
    setFolderId(null);
    setDeleting(null);
    setDialogMessage(null);
    requestAnimationFrame(() => opener.current?.focus());
  };
  const draftRef = useUnsavedDraft('代傳照片', { '已選檔案張數': upload?.photos.length ?? 0 }, {
    baseline: { '已選檔案張數': 0 },
    enabled: upload !== null,
    busy,
    discard: closeDialog,
  });

  const refreshFolders = async (signal: AbortSignal) => {
    const refreshed = await staffWebProfileClient.folders(staffId, signal);
    if (!signal.aborted) setFolders(refreshed);
    return refreshed;
  };
  const reload = async () => {
    const signal = lifecycle.current?.signal;
    if (!signal) return;
    setLoading(true);
    setMessage(null);
    try {
      await refreshFolders(signal);
    } catch (error) {
      if (!signal.aborted) setMessage({ text: staffWebFileError(error, '無法讀取照片資料夾。'), error: true });
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  };

  const openUpload = (button: HTMLButtonElement) => {
    const folder = folders?.[0];
    if (!folder) return;
    opener.current = button;
    setMessage(null);
    setUpload({ category: folder.category, folder, photos: [], expiry: '' });
  };
  const uploadFolder = upload?.folder;
  const editedFolder = folders?.find(folder => folder.template_item_id === folderId);

  const publish = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const signal = lifecycle.current?.signal;
    if (!signal || !upload || !uploadFolder || !upload.photos.length || !canWrite || busy) return;
    setBusy(true);
    setDialogMessage(null);
    try {
      let command = confirmed;
      if (!command) {
        const files = [];
        for (const draft of upload.photos) {
          const uploaded = await staffWebProfileClient.uploadForStaff(staffId, draft.file, draft.uploadId, signal);
          files.push({ file_id: uploaded.file_id, expiry_date: upload.category === 'other' ? upload.expiry : null });
        }
        const current = upload.category === 'other' ? uploadFolder.files[0] : undefined;
        command = {
          operation_id: crypto.randomUUID(),
          template_item_id: uploadFolder.template_item_id,
          template_version: uploadFolder.template_version,
          files,
          expected_current: current ? { entry_id: current.entry_id, entry_version: current.entry_version } : null,
        };
        setConfirmed(command);
      }
      const receipt = await staffWebProfileClient.publishForStaff(staffId, command, signal);
      try {
        const refreshed = await refreshFolders(signal);
        if (signal.aborted) return;
        const current = refreshed.find(folder => folder.template_item_id === command.template_item_id);
        const visible = receipt.files.every(file => current?.files.some(row =>
          row.entry_id === file.entry_id && row.entry_version === file.entry_version));
        closeDialog();
        setMessage(visible ? { text: '照片已發布。' } : { text: '已收到發布回條，目前清單已有其他變更。' });
      } catch {
        if (signal.aborted) return;
        closeDialog();
        setMessage({ text: '已收到發布回條，請重試讀取以確認目前清單。', error: true });
      }
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof ApiHttpError && error.status >= 400 && error.status < 500) {
        setConfirmed(null);
      }
      if (error instanceof ApiHttpError && error.status === 409) {
        setDialogMessage({ text: '發布未完成。請關閉代傳視窗並重試讀取清單，再核對最新資料。', error: true });
        setMessage({ text: '資料已更新，請重試讀取清單。', error: true });
      } else {
        setDialogMessage({ text: staffWebFileError(error, '發布結果未確認，請用原操作重試。'), error: true });
      }
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  };

  const remove = async () => {
    const signal = lifecycle.current?.signal;
    if (!signal || !editedFolder || !deleting || !canWrite || busy) return;
    setBusy(true);
    setDialogMessage(null);
    try {
      const receipt = await staffWebProfileClient.removeForStaff(staffId, editedFolder, deleting, signal);
      if (receipt.entry_id !== deleting.entry_id) throw new Error('staff_web_removal_receipt_mismatch');
      const refreshed = await refreshFolders(signal);
      if (signal.aborted) return;
      setDeleting(null);
      const removed = !refreshed.find(folder => folder.template_item_id === folderId)?.files
        .some(file => file.entry_id === receipt.entry_id);
      setDialogMessage(removed ? { text: '照片已刪除。' } : { text: '已收到刪除回條，請核對目前清單。' });
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof ApiHttpError && error.status === 409) {
        setDeleting(null);
        setMessage({ text: '資料已更新，請重試讀取清單。', error: true });
      }
      setDialogMessage({ text: staffWebFileError(error, '刪除結果未確認，請用原操作重試。'), error: true });
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  };

  return <section className="staff-web-files" aria-labelledby={sectionTitle}>
    <div className="staff-web-files-heading">
      <h3 id={sectionTitle}>履歷網頁與照片</h3>
      <div>
        <button type="button" className="staff-secondary-btn" onClick={() => requestLeave(() => {
          window.location.assign(`/line-staff-web-profile?staff_id=${staffId}&mode=admin`);
        })}>查看履歷網頁</button>
        {canWrite && <button type="button" className="staff-primary-btn" disabled={!folders?.length || loading} onClick={event => openUpload(event.currentTarget)}>代傳照片</button>}
      </div>
    </div>
    {loading && <p role="status">正在讀取照片資料夾…</p>}
    {message && <p role={message.error ? 'alert' : 'status'}>{message.text}
      {message.error && <button type="button" className="staff-secondary-btn" disabled={loading} onClick={() => void reload()}>重試讀取清單</button>}
    </p>}
    {folders?.length === 0 && <p>目前沒有模板項目。</p>}
    {categories.map(category => {
      const items = folders?.filter(folder => folder.category === category);
      if (!items?.length) return null;
      return <section className="staff-web-files-group" key={category} aria-label={webProfileCategoryLabels[category]}>
        <h4>{webProfileCategoryLabels[category]}</h4>
        <ul>{items.map(folder => <li key={folder.template_item_id}>
          <span className="staff-web-files-name">{folder.name}</span>
          <span>{folder.count} 張</span>
          {category === 'other' && <span className="staff-web-files-date">{folder.files[0]?.expiry_date ?? '—'}</span>}
          <button type="button" className="staff-secondary-btn" aria-label={`開啟資料夾 ${folder.name}`} onClick={event => {
            opener.current = event.currentTarget;
            setFolderId(folder.template_item_id);
          }}>開啟資料夾</button>
        </li>)}</ul>
      </section>;
    })}
    {editedFolder && <FileDialog title={editedFolder.name} owner={staffName} busy={busy} onClose={closeDialog}>
      <div className="staff-web-files-dialog-body">
        {editedFolder.files.length === 0 && <p>資料夾內沒有已發布照片。</p>}
        <ul>{editedFolder.files.map(file => <li key={file.entry_id}>
          <span className="staff-web-files-name">{file.filename}</span>
          {editedFolder.category === 'other' && <span className="staff-web-files-date">{file.expiry_date ?? '—'}</span>}
          {canWrite && <button type="button" className="staff-secondary-btn" disabled={busy} aria-label={`刪除照片 ${file.filename}`} onClick={() => {
            setDeleting(file);
            setDialogMessage(null);
          }}>刪除照片</button>}
        </li>)}</ul>
        {deleting && <div className="staff-web-files-confirm">
          <p>確認刪除「{deleting.filename}」？刪除後，履歷網頁將移除這張照片。</p>
          <button type="button" className="staff-secondary-btn" disabled={busy} onClick={() => setDeleting(null)}>取消刪除</button>
          <button type="button" className="staff-primary-btn" disabled={busy} onClick={() => void remove()}>{busy ? '正在刪除…' : '確認刪除'}</button>
        </div>}
        {dialogMessage && <p role={dialogMessage.error ? 'alert' : 'status'}>{dialogMessage.text}</p>}
      </div>
    </FileDialog>}
    {upload && <FileDialog title="代傳照片" owner={staffName} busy={busy} onClose={closeDialog}>
      <form ref={draftRef} onSubmit={event => void publish(event)}>
        <div className="staff-web-files-dialog-body">
          <fieldset className="staff-web-files-fields" disabled={busy || confirmed !== null}>
            <div>
              <label>分類
                <select value={upload.category} onChange={event => {
                  const category = categories.find(value => value === event.target.value);
                  if (category) setUpload({ category, folder: folders?.find(folder => folder.category === category), photos: [], expiry: '' });
                }}>
                  {categories.map(category => <option key={category} value={category}>{webProfileCategoryLabels[category]}</option>)}
                </select>
              </label>
              <label>模板項目
                <select required value={uploadFolder?.template_item_id ?? ''} onChange={event => {
                  const folder = folders?.find(item => String(item.template_item_id) === event.target.value);
                  setUpload({ ...upload, folder, photos: [], expiry: '' });
                }}>
                  {!uploadFolder && <option value="">目前沒有項目</option>}
                  {folders?.filter(folder => folder.category === upload.category).map(folder => <option key={folder.template_item_id} value={folder.template_item_id}>{folder.name}</option>)}
                </select>
              </label>
            </div>
            {upload.category === 'other' && <label>到期日（必填）<input
              type="date" required min="1000-01-01" max="9999-12-31" value={upload.expiry}
              onChange={event => setUpload({ ...upload, expiry: event.target.value })}
            /></label>}
            <label>選擇照片<input
              key={uploadFolder?.template_item_id}
              type="file" accept={supportedPhotos} multiple={upload.category !== 'other'} disabled={!uploadFolder}
              onChange={event => {
                const files = Array.from(event.target.files ?? []);
                if (files.length > (upload.category === 'other' ? 1 : 50)) {
                  event.target.value = '';
                  setDialogMessage({ text: upload.category === 'other' ? '此項目限選一張照片。' : '每次最多發布 50 張照片。', error: true });
                  setUpload({ ...upload, photos: [] });
                  return;
                }
                setDialogMessage(null);
                setUpload({ ...upload, photos: files.map(file => ({ file, uploadId: crypto.randomUUID() })) });
              }}
            /></label>
          </fieldset>
          {upload.photos.length > 0 && <div className="staff-web-files-selection">
            <p>已選 {upload.photos.length} 張</p>
            <ul>{upload.photos.map(photo => <li key={photo.uploadId}>{photo.file.name}</li>)}</ul>
          </div>}
          {upload.category === 'other' && !!uploadFolder?.count && <p>確認發布後會替換目前照片。</p>}
          {dialogMessage && <p role={dialogMessage.error ? 'alert' : 'status'}>{dialogMessage.text}</p>}
        </div>
        <footer>
          <button type="button" className="staff-secondary-btn" disabled={busy} onClick={closeDialog}>取消</button>
          <button type="submit" className="staff-primary-btn" disabled={busy || !upload.photos.length || !uploadFolder}>
            {busy ? '正在發布…' : confirmed ? '重試原發布' : '確認發布'}
          </button>
        </footer>
      </form>
    </FileDialog>}
  </section>;
}
