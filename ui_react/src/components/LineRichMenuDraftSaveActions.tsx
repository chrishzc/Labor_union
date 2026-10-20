import { useUnsavedDraft } from './UnsavedChanges';
/**
 * File: LineRichMenuDraftSaveActions.tsx
 * Description: 以同一共用草稿執行零寫入檢查、明確確認、保存與重新查詢，不建立發布工作。
 */
import React, { useEffect, useRef, useState } from 'react';
import { Check, CircleCheck, RotateCcw, Save, X } from 'lucide-react';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type { RichMenuDraft, RichMenuDraftDefinition, RichMenuDraftPreview } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';

interface Props {
  draft: RichMenuDraft;
  definition: RichMenuDraftDefinition;
  client: LineRichMenuDraftClient;
  onApplied: (draft: RichMenuDraft) => void;
  onCancel: () => void;
  onBusyChange: (busy: boolean) => void;
  onReloadRequired: () => void;
  publicationAction: React.ReactNode;
}

function changedFields(before: RichMenuDraftDefinition, after: RichMenuDraftDefinition): string[] {
  return after.menus.flatMap((menu) => {
    const previous = before.menus.find((item) => item.id === menu.id);
    if (!previous) return [`${menu.name}：新增選單`];
    const result: string[] = [];
    if (previous.name !== menu.name) result.push(`${previous.name}：名稱改為「${menu.name}」`);
    if (previous.chat_bar_text !== menu.chat_bar_text) result.push(`${menu.name}：選單列改為「${menu.chat_bar_text}」`);
    if (previous.appearance?.background_color !== menu.appearance?.background_color) {
      result.push(`${menu.name}：底色 ${previous.appearance?.background_color ?? '預設'} → ${menu.appearance?.background_color ?? '預設'}`);
    }
    if (previous.appearance?.image_mode !== menu.appearance?.image_mode
      || previous.appearance?.image_asset_id !== menu.appearance?.image_asset_id) result.push(`${menu.name}：背景來源已變更`);
    for (const button of menu.buttons) {
      const old = previous.buttons.find((item) => item.id === button.id);
      if (old?.label !== button.label) result.push(`${menu.name}：按鈕「${old?.label ?? '未命名'}」改為「${button.label}」`);
      if (JSON.stringify(old?.action) !== JSON.stringify(button.action)) result.push(`${menu.name}：「${button.label}」點擊動作已變更`);
    }
    return result;
  });
}

export const LineRichMenuDraftSaveActions: React.FC<Props> = ({ draft, definition, client, onApplied, onCancel, onBusyChange, onReloadRequired, publicationAction }) => {
  const [preview, setPreview] = useState<RichMenuDraftPreview | null>(null);
  const [discarding, setDiscarding] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef<AbortController | null>(null);
  const identity = useRef('');
  const dirty = JSON.stringify(definition) !== JSON.stringify(draft.definition);

  useEffect(() => {
    setPreview(null);
    setConfirmed(false);
    setDiscarding(false);
  }, [definition, draft.revision]);
  useEffect(() => {
    const element = dialog.current;
    if ((preview || discarding) && !element?.open) element?.showModal();
    if (!preview && !discarding) element?.close();
  }, [preview, discarding]);
  useEffect(() => () => request.current?.abort(), []);

  const start = () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    onBusyChange(true);
    setMessage(null);
    setFailed(false);
    return controller;
  };
  const finish = (controller: AbortController) => {
    if (!controller.signal.aborted) { setBusy(false); onBusyChange(false); }
  };
  const check = async () => {
    const controller = start();
    try {
      const result = await client.preview({ expected_revision: draft.revision, definition }, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (result.before_revision !== draft.revision) throw new Error('草稿版本已變更，請重新載入後再檢查。');
      identity.current = `rich-menu-draft-${crypto.randomUUID()}`;
      setPreview(result);
      setConfirmed(false);
      setReason('');
    } catch (error) {
      if (!controller.signal.aborted) { setFailed(true); setMessage(error instanceof Error ? error.message : '草稿檢查失敗，請重新載入後再試。'); }
    } finally { finish(controller); }
  };
  const apply = async () => {
    if (!preview || !confirmed || busy) return;
    const controller = start();
    onReloadRequired();
    try {
      const result = await client.apply({
        expected_revision: preview.before_revision,
        definition: preview.normalized_definition,
        preview_fingerprint: preview.preview_fingerprint,
        reason: reason.trim(), idempotency_key: identity.current, correlation_id: identity.current,
      }, { signal: controller.signal });
      const reloaded = await client.query({ signal: controller.signal });
      if (controller.signal.aborted) return;
      if (reloaded.revision !== result.receipt.committed_revision
        || JSON.stringify(reloaded.definition) !== JSON.stringify(preview.normalized_definition)) {
        throw new Error('草稿已儲存，但重新載入的內容與確認結果不同。請取消本機修改並重新整理，再確認目前版本；暫不發布。');
      }
      onApplied(reloaded);
      setPreview(null);
      setMessage('草稿已儲存並重新載入；尚未發布至 LINE。');
    } catch (error) {
      if (!controller.signal.aborted) { setFailed(true); setConfirmed(false); setMessage(error instanceof Error ? error.message : '草稿儲存或重新載入失敗，請確認目前版本後再試。'); }
    } finally { finish(controller); }
  };
  useUnsavedDraft('圖文選單草稿', { '變更內容': changedFields(draft.definition, definition), '原因': reason }, { baseline: { '變更內容': [], '原因': '' }, busy });


  return <>
    {message && <p className={failed ? 'line-error richmenu-save-message' : 'richmenu-save-message'} role={failed ? 'alert' : 'status'}>{message}</p>}
    <div className="richmenu-save-footer">
      <span className="richmenu-save-state" role="status"><Check aria-hidden="true" />{dirty ? '尚有未儲存的修改' : '草稿已載入'}</span>
      <div className="richmenu-save-buttons">
        <button type="button" className="line-secondary-btn" disabled={!dirty || busy} onClick={() => setDiscarding(true)}><RotateCcw aria-hidden="true" />取消修改</button>
        <button type="button" className="line-primary-btn" disabled={!dirty || busy} onClick={() => void check()}><CircleCheck aria-hidden="true" />{busy ? '處理中…' : '檢查並儲存草稿'}</button>
        {publicationAction}
      </div>
    </div>
    <dialog ref={dialog} className="richmenu-save-dialog" aria-labelledby="richmenu-save-title"
      onCancel={(event) => { if (busy) event.preventDefault(); else { setPreview(null); setDiscarding(false); } }}>
      <div className="richmenu-save-dialog-header"><h3 id="richmenu-save-title">{discarding ? '取消尚未儲存的修改' : '確認儲存草稿'}</h3>
        <button type="button" aria-label="關閉確認視窗" disabled={busy} onClick={() => { setPreview(null); setDiscarding(false); }}><X aria-hidden="true" /></button>
      </div>
      <div className="richmenu-save-dialog-body">
        {discarding ? <p>將還原所有角色尚未儲存的修改，已儲存的草稿仍會保留。</p> : <>
          <p>已完成草稿檢查，請核對以下變更。儲存不會發布至 LINE。</p>
          <ul className="richmenu-save-changes">{preview && changedFields(draft.definition, preview.normalized_definition).map((text, index) => <li key={index}>{text}</li>)}</ul>
          <><label className="richmenu-form-field"><span>備註（選填）</span><input  className="richmenu-form-input" maxLength={500} value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} placeholder="有需要補充的內容再填寫" /></label></>
          <label className="richmenu-confirm-checkbox-label"><input type="checkbox" checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} />我確認儲存此草稿；這不會發布或發送 LINE。</label>
          {failed && message && <p className="line-error" role="alert">{message}</p>}
        </>}
      </div>
      <div className="richmenu-save-dialog-footer"><button type="button" className="line-secondary-btn" disabled={busy} onClick={() => { setPreview(null); setDiscarding(false); }}>繼續編輯</button>
        {discarding ? <button type="button" className="line-primary-btn" onClick={() => { onCancel(); setMessage(null); setDiscarding(false); }}>確認取消修改</button>
          : <button type="button" className="line-primary-btn" disabled={!confirmed || busy} onClick={() => void apply()}><Save aria-hidden="true" />{busy ? '儲存並重新載入中…' : '確認儲存草稿'}</button>}
      </div>
    </dialog>
  </>;
};
