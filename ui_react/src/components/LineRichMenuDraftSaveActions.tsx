import { useUnsavedDraft } from './UnsavedChanges';
/**
 * File: LineRichMenuDraftSaveActions.tsx
 * Description: 以同一共用草稿執行零寫入檢查、一次點擊保存與重新查詢，不建立發布工作。
 */
import React, { useEffect, useRef, useState } from 'react';
import { Check, RotateCcw, Save } from 'lucide-react';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type { RichMenuDraft, RichMenuDraftDefinition, RichMenuDraftApplyRequest } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';

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
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const request = useRef<AbortController | null>(null);
  const intent = useRef<{ signature: string; command: RichMenuDraftApplyRequest } | null>(null);
  const dirty = JSON.stringify(definition) !== JSON.stringify(draft.definition);

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
  const apply = async () => {
    if (busy || !dirty) return;
    const controller = start();
    try {
      const signature = JSON.stringify([draft.revision, definition, reason.trim()]);
      if (intent.current?.signature !== signature) {
        const preview = await client.preview({ expected_revision: draft.revision, definition }, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (preview.before_revision !== draft.revision) throw new Error('草稿版本已變更，請重新載入後再儲存。');
        const key = `rich-menu-draft-${crypto.randomUUID()}`;
        intent.current = { signature, command: {
          expected_revision: preview.before_revision,
          definition: preview.normalized_definition,
          preview_fingerprint: preview.preview_fingerprint,
          reason: reason.trim(), idempotency_key: key, correlation_id: key,
        } };
      }
      const command = intent.current.command;
      onReloadRequired();
      const result = await client.apply(command, { signal: controller.signal });
      const reloaded = await client.query({ signal: controller.signal });
      if (controller.signal.aborted) return;
      if (reloaded.revision !== result.receipt.committed_revision
        || JSON.stringify(reloaded.definition) !== JSON.stringify(command.definition)) {
        throw new Error('草稿已儲存，但重新載入的內容不同。請重新整理並查詢目前版本；暫不發布。');
      }
      intent.current = null;
      onApplied(reloaded);
      setReason('');
      setMessage('草稿已儲存並重新載入；尚未發布至 LINE。');
    } catch (error) {
      if (!controller.signal.aborted) { setFailed(true); setMessage(error instanceof Error ? error.message : '草稿儲存或重新載入失敗，請查詢目前版本後再試。'); }
    } finally { finish(controller); }
  };
  useUnsavedDraft('圖文選單草稿', { '變更內容': changedFields(draft.definition, definition), '原因': reason }, { baseline: { '變更內容': [], '原因': '' }, busy });


  return <>
    {message && <p className={failed ? 'line-error richmenu-save-message' : 'richmenu-save-message'} role={failed ? 'alert' : 'status'}>{message}</p>}
    <label className="richmenu-form-field"><span>備註（選填）</span><input className="richmenu-form-input" maxLength={500} value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} /></label>
    <div className="richmenu-save-footer">
      <span className="richmenu-save-state" role="status"><Check aria-hidden="true" />{dirty ? '尚有未儲存的修改' : '草稿已載入'}</span>
      <div className="richmenu-save-buttons">
        <button type="button" className="line-secondary-btn" disabled={!dirty || busy} onClick={() => { onCancel(); setMessage(null); setReason(''); }}><RotateCcw aria-hidden="true" />取消修改</button>
        <button type="button" className="line-primary-btn" disabled={!dirty || busy} onClick={() => void apply()}><Save aria-hidden="true" />{busy ? '處理中…' : '儲存草稿'}</button>
        {publicationAction}
      </div>
    </div>

  </>;
};
