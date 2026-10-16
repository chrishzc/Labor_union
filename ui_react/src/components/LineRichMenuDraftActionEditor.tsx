/**
 * File: LineRichMenuDraftActionEditor.tsx
 * Description: 統一編輯共用草稿的按鈕名稱與 typed action；不執行儲存或發布。
 */
import React, { useState } from 'react';
import { Zap } from 'lucide-react';
import type { RichMenuAction } from '../api/line_configuration/line_configuration_query_schemas';
import type {
  RichMenuDraft,
  RichMenuDraftDefinition,
} from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';

interface Props {
  draft: RichMenuDraft;
  menuId: string | null;
  definition: RichMenuDraftDefinition;
  onDefinitionChange: (definition: RichMenuDraftDefinition) => void;
}

type EditableActionType = 'message' | 'uri' | 'postback';

function initialAction(kind: EditableActionType): RichMenuAction {
  switch (kind) {
    case 'message': return { type: 'message', text: '' };
    case 'uri': return { type: 'uri', uri: '?entry=registration', uri_source: 'liff' };
    case 'postback': return { type: 'postback', data: '' };
  }
}

const CANONICAL_LIFF_TARGETS = [
  { value: '?entry=gateway', label: '?entry=gateway（服務確認與身分導流 Gateway）' },
  { value: '?entry=registration', label: '?entry=registration（服務登記／身分導流）' },
  { value: '?target=gateway', label: '?target=gateway（服務確認與身分導流 Gateway）' },
  { value: '?target=profile_update', label: '?target=profile_update（修改登記資料）' },
  { value: '?target=staff_order_search', label: '?target=staff_order_search（月嫂案件查詢）' },
  { value: '?target=staff_schedule', label: '?target=staff_schedule（月嫂服務行程）' },
  { value: '?target=staff_leave_apply', label: '?target=staff_leave_apply（月嫂請假登記，相容入口）' },
  { value: '?target=staff_baby_log', label: '?target=staff_baby_log（月嫂寶寶日誌）' },
  { value: '?target=staff_verification', label: '?target=staff_verification（月嫂身分綁定）' },
  { value: '?target=staff_payout', label: '?target=staff_payout（薪資請款）' },
  { value: '?target=order_update', label: '?target=order_update（修改訂單資訊）' },
  { value: '?target=order_tracking', label: '?target=order_tracking（狀態追蹤）' },
  { value: '?target=faq', label: '?target=faq（常見問答）' },
  { value: '?target=ai_assistant', label: '?target=ai_assistant（AI 智慧問答）' },
  { value: '?target=dashboard', label: '?target=dashboard（營運摘要）' },
  { value: '?target=customer_service', label: '?target=customer_service（客服管理）' },
  { value: '?target=scheduling_review', label: '?target=scheduling_review（排班審核）' },
  { value: '?target=staff_review', label: '?target=staff_review（待辦工作台）' },
];

export const LineRichMenuDraftActionEditor: React.FC<Props> = ({
  draft,
  menuId,
  definition,
  onDefinitionChange,
}) => {
  const [buttonId, setButtonId] = useState<string | null>(null);
  const menu = definition.menus.find((item) => item.id === menuId) ?? definition.menus[0];
  const button = menu?.buttons.find((item) => item.id === buttonId) ?? menu?.buttons[0];
  const updateButton = (change: Partial<NonNullable<typeof button>>) => {
    if (!menu || !button) return;
    onDefinitionChange({ ...definition, menus: definition.menus.map((item) => item.id !== menu.id ? item : {
      ...item, buttons: item.buttons.map((candidate) => candidate.id === button.id ? { ...candidate, ...change } : candidate),
    }) });
  };
  const updateAction = (action: RichMenuAction) => updateButton({ action });

  if (!menu || !button) {
    return <div className="line-scope-note">目前沒有可編輯的 Rich Menu 草稿按鈕。</div>;
  }

  const publicationLock = draft.publication_locks.find(
    (item) => item.menu_definition_id === menu.id
      && item.configuration_revision === draft.revision,
  );
  const canCreateNextDraft = publicationLock?.state === 'editable'
    || publicationLock?.state === 'published';
  const readonlyReason = canCreateNextDraft
    ? null
    : publicationLock?.readonly_reason
      ?? '目前無法確認這個選單版本是否可編輯，已安全切換為唯讀。';
  if (readonlyReason) {
    return (
      <section className="richmenu-card" data-control-id="line.richmenu.draft.action-editor">
        <div className="richmenu-card-header">
          <div>
            <h4 className="richmenu-editor-title"><Zap aria-hidden="true" />修改按鈕動作</h4>
            <p className="richmenu-editor-description">此版本保留原始發布內容，目前不提供修改。</p>
          </div>
          <span className="line-category-badge category-service_flow">唯讀</span>
        </div>
        <div className="line-scope-note" role="status">{readonlyReason}</div>
      </section>
    );
  }

  const action = button.action;
  const legacySwitchBlocked = action.type === 'richmenuswitch';

  return (
    <section className="richmenu-card" data-control-id="line.richmenu.draft.action-editor">
      {legacySwitchBlocked && (
        <div className="line-warning" role="alert">
          此按鈕仍是舊版 Rich Menu switch 動作。使用者端選單切換已停用，請改成訊息、LIFF／網址或 Postback 後再保存。
        </div>
      )}

      <div className="richmenu-form-grid">
        <div className="richmenu-button-choices richmenu-form-field-full" role="group" aria-label="選擇編輯按鈕">
          {menu.buttons.map((candidate, index) => <button key={candidate.id} type="button"
            className={button.id === candidate.id ? 'active' : ''} aria-pressed={button.id === candidate.id}
            onClick={() => setButtonId(candidate.id)}><small>按鈕 {index + 1}</small>{candidate.label}</button>)}
        </div>
        <label className="richmenu-form-field richmenu-form-field-full">
          <span>按鈕顯示名稱</span>
          <input className="richmenu-form-input" maxLength={30} required value={button.label}
            onChange={(event) => updateButton({ label: event.target.value })} />
        </label>
        <label className="richmenu-form-field">
          <span>點擊後的動作</span>
          <select
            className="richmenu-form-select"
            value={legacySwitchBlocked ? '' : action.type}
            onChange={(event) => updateAction(initialAction(event.target.value as EditableActionType))}
          >
            {legacySwitchBlocked && <option value="">請改用支援的動作</option>}
            <option value="message">發送訊息</option>
            <option value="uri">開啟 LIFF／網址</option>
            <option value="postback">觸發系統操作（進階）</option>
          </select>
        </label>

        {action.type === 'message' && (
          <label className="richmenu-form-field richmenu-form-field-full">
            <span>送出訊息</span>
            <input
              className="richmenu-form-input"
              maxLength={300}
              placeholder="輸入點擊按鈕時，使用者將自動發送的訊息文字..."
              value={action.text ?? ''}
              onChange={(event) => updateAction({ type: 'message', text: event.target.value })}
            />
          </label>
        )}

        {action.type === 'uri' && (
          <>
            <label className="richmenu-form-field">
              <span>目標來源</span>
              <select
                className="richmenu-form-select"
                value={action.uri_source ?? 'literal'}
                onChange={(event) => updateAction({
                  type: 'uri',
                  uri_source: event.target.value as 'literal' | 'liff',
                  uri: event.target.value === 'liff' ? '?entry=gateway' : 'https://',
                })}
              >
                <option value="liff">系統 LIFF 入口</option>
                <option value="literal">HTTPS 網址</option>
              </select>
            </label>
            <label className="richmenu-form-field">
              <span>{action.uri_source === 'liff' ? 'LIFF 入口' : 'HTTPS 網址'}</span>
              {action.uri_source === 'liff' ? (() => {
                const currentUri = action.uri ?? '?entry=gateway';
                const isListed = CANONICAL_LIFF_TARGETS.some((target) => target.value === currentUri);
                return (
                  <select
                    className="richmenu-form-select"
                    aria-label="LIFF target／網址"
                    value={currentUri}
                    onChange={(event) => updateAction({ ...action, uri: event.target.value })}
                  >
                    {!isListed && (
                      <option key={currentUri} value={currentUri}>
                        {currentUri}（自訂／未收錄入口）
                      </option>
                    )}
                    {CANONICAL_LIFF_TARGETS.map((target) => (
                      <option key={target.value} value={target.value}>{target.label.replace(/^.*?（/, '').replace(/）$/, '')}</option>
                    ))}
                  </select>
                );
              })() : (
                <input
                  className="richmenu-form-input"
                  aria-label="LIFF target／網址"
                  maxLength={1000}
                  placeholder="https://..."
                  value={action.uri ?? ''}
                  onChange={(event) => updateAction({ ...action, uri: event.target.value })}
                />
              )}
            </label>
          </>
        )}

        {action.type === 'postback' && (
          <label className="richmenu-form-field richmenu-form-field-full">
            <span>系統動作資料</span>
            <textarea
              className="richmenu-form-textarea"
              maxLength={300}
              rows={2}
              placeholder="例如：action=inquiry_status&case_id=123"
              value={action.data ?? ''}
              onChange={(event) => updateAction({ type: 'postback', data: event.target.value })}
            />
          </label>
        )}

      </div>
    </section>
  );
};
