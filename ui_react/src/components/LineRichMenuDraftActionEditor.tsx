/**
 * File: LineRichMenuDraftActionEditor.tsx
 * Description: 編輯 Rich Menu closed typed action，並執行草稿 Preview、確認、Apply 與 readback。
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { RichMenuAction } from '../api/line_configuration/line_configuration_query_schemas';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type {
  RichMenuDraft,
  RichMenuDraftDefinition,
  RichMenuDraftPreview,
} from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';

interface Props {
  draft: RichMenuDraft;
  menuId: string | null;
  client: LineRichMenuDraftClient;
  onApplied: (draft: RichMenuDraft) => void;
  onLocalDefinitionChange?: (definition: RichMenuDraftDefinition | null) => void;
  previewDefinition?: RichMenuDraftDefinition;
}

type Status = 'idle' | 'previewing' | 'previewed' | 'applying' | 'applied' | 'error';

function copyDefinition(value: RichMenuDraftDefinition): RichMenuDraftDefinition {
  return structuredClone(value);
}

function initialAction(kind: RichMenuAction['type']): RichMenuAction {
  switch (kind) {
    case 'message': return { type: 'message', text: '' };
    case 'uri': return { type: 'uri', uri: '?entry=registration', uri_source: 'liff' };
    case 'postback': return { type: 'postback', data: '' };
    case 'richmenuswitch': return { type: 'richmenuswitch', data: '', rich_menu_alias_id: '' };
  }
}

const CANONICAL_LIFF_TARGETS = [
  { value: '?entry=gateway', label: '?entry=gateway（服務確認與身分導流 Gateway）' },
  { value: '?entry=registration', label: '?entry=registration（服務登記／身分導流）' },
  { value: '?target=gateway', label: '?target=gateway（服務確認與身分導流 Gateway）' },
  { value: '?target=profile_update', label: '?target=profile_update（修改登記資料）' },
  { value: '?target=staff_order_search', label: '?target=staff_order_search（月嫂案件查詢）' },
  { value: '?target=staff_schedule', label: '?target=staff_schedule（月嫂服務行程）' },
  { value: '?target=staff_leave_apply', label: '?target=staff_leave_apply（月嫂請假登記）' },
  { value: '?target=customer_service', label: '?target=customer_service（客服管理）' },
  { value: '?target=scheduling_review', label: '?target=scheduling_review（排班審核）' },
  { value: '?target=staff_review', label: '?target=staff_review（月嫂審核）' },
  { value: '?target=staff_payout', label: '?target=staff_payout（薪資請款）' },
  { value: '?target=anomalies_center', label: '?target=anomalies_center（重大異常通報）' },
  { value: '?target=dashboard', label: '?target=dashboard（儀表板）' },
];

export const LineRichMenuDraftActionEditor: React.FC<Props> = ({
  draft,
  menuId,
  client,
  onApplied,
  onLocalDefinitionChange,
  previewDefinition,
}) => {
  const [definition, setDefinition] = useState(() => copyDefinition(draft.definition));
  const [buttonId, setButtonId] = useState<string | null>(null);
  const [preview, setPreview] = useState<RichMenuDraftPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState('工會人員調整 Rich Menu 按鈕動作');
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const appliedRevision = useRef<number | null>(null);

  useEffect(() => {
    const preserveApplyReadback = appliedRevision.current === draft.revision;
    setDefinition(copyDefinition(draft.definition));
    setButtonId(null);
    setPreview(null);
    setConfirmed(false);
    if (!preserveApplyReadback) {
      setStatus('idle');
      setMessage(null);
    }
    appliedRevision.current = null;
  }, [draft]);

  const menu = 'menus' in definition
    ? definition.menus.find((item) => item.id === menuId) ?? definition.menus[0]
    : undefined;
  const button = useMemo(
    () => menu?.buttons.find((item) => item.id === buttonId) ?? menu?.buttons[0],
    [buttonId, menu],
  );

  const updateAction = (action: RichMenuAction) => {
    if (!menu || !button) return;
    if (!('menus' in definition)) return;
    const nextDefinition: RichMenuDraftDefinition = {
      ...definition,
      menus: definition.menus.map((item) => item.id !== menu.id ? item : {
        ...item,
        buttons: item.buttons.map((candidate) => candidate.id === button.id
          ? { ...candidate, action }
          : candidate),
      }),
    };
    setDefinition(nextDefinition);
    onLocalDefinitionChange?.(copyDefinition(nextDefinition));
    setPreview(null);
    setConfirmed(false);
    setStatus('idle');
    setMessage(null);
  };

  const requestPreview = async () => {
    setStatus('previewing');
    setMessage(null);
    setConfirmed(false);
    try {
      const result = await client.preview({
        expected_revision: draft.revision,
        definition: previewDefinition ?? definition,
      });
      setPreview(result);
      setStatus('previewed');
    } catch (error) {
      setStatus('error');
      setMessage(error instanceof Error ? error.message : 'Rich Menu 草稿預覽失敗');
    }
  };

  const apply = async () => {
    if (!preview || !confirmed) return;
    setStatus('applying');
    setMessage(null);
    try {
      const identity = crypto.randomUUID();
      const result = await client.apply({
        expected_revision: draft.revision,
        definition: preview.normalized_definition,
        preview_fingerprint: preview.preview_fingerprint,
        reason,
        idempotency_key: `rich-menu-draft-${identity}`,
        correlation_id: `rich-menu-draft-${identity}`,
      });
      setStatus('applied');
      setMessage('草稿已保存並完成回讀；尚未發布至 LINE。');
      appliedRevision.current = result.readback.revision;
      onLocalDefinitionChange?.(null);
      onApplied(result.readback);
    } catch (error) {
      setStatus('error');
      setMessage(error instanceof Error ? error.message : 'Rich Menu 草稿套用失敗');
    }
  };

  if (!menu || !button) {
    return <div className="line-scope-note">目前沒有可編輯的 Rich Menu 草稿按鈕。</div>;
  }

  const publicationLock = draft.publication_locks.find(
    (item) => item.menu_definition_id === menu.id
      && item.configuration_revision === draft.revision,
  );
  const readonlyReason = publicationLock?.state === 'editable'
    ? null
    : publicationLock?.readonly_reason
      ?? '目前無法確認這個選單版本是否可編輯，已安全切換為唯讀。';
  if (readonlyReason) {
    return (
      <section className="richmenu-card" data-control-id="line.richmenu.draft.action-editor">
        <div className="richmenu-card-header">
          <div>
            <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
              ⚡ 修改按鈕動作
            </h4>
            <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
              此版本保留原始發布內容，目前不提供修改。
            </p>
          </div>
          <span className="line-category-badge category-service_flow">唯讀</span>
        </div>
        <div className="line-scope-note" role="status">{readonlyReason}</div>
      </section>
    );
  }

  const action = button.action;
  return (
    <section className="richmenu-card" data-control-id="line.richmenu.draft.action-editor">
      <div className="richmenu-card-header">
        <div>
          <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
            ⚡ 修改按鈕動作
          </h4>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
            只修改草稿版本；本機模擬不發送 LINE，可直接一鍵套用。
          </p>
        </div>
        <span className="line-category-badge category-navigation">編輯草稿</span>
      </div>

      <div className="richmenu-form-grid">
        <label className="richmenu-form-field">
          <span>按鈕</span>
          <select
            className="richmenu-form-select"
            value={button.id}
            onChange={(event) => {
              setButtonId(event.target.value);
              setPreview(null);
              setConfirmed(false);
              setStatus('idle');
              setMessage(null);
            }}
          >
            {menu.buttons.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.label}
              </option>
            ))}
          </select>
        </label>
        <label className="richmenu-form-field">
          <span>動作類型</span>
          <select
            className="richmenu-form-select"
            value={action.type}
            onChange={(event) => updateAction(initialAction(event.target.value as RichMenuAction['type']))}
          >
            <option value="message">發送訊息</option>
            <option value="uri">開啟 LIFF／網址</option>
            <option value="postback">Postback 資料</option>
            <option value="richmenuswitch">切換 Rich Menu</option>
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
              {action.uri_source === 'liff' ? (
                <select
                  className="richmenu-form-select"
                  aria-label="LIFF target／網址"
                  value={action.uri ?? '?entry=gateway'}
                  onChange={(event) => updateAction({ ...action, uri: event.target.value })}
                >
                  {CANONICAL_LIFF_TARGETS.map((target) => (
                    <option key={target.value} value={target.value}>
                      {target.label}
                    </option>
                  ))}
                </select>
              ) : (
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
            <span>Postback data</span>
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

        {action.type === 'richmenuswitch' && (
          <>
            <label className="richmenu-form-field">
              <span>切換資料</span>
              <input
                className="richmenu-form-input"
                maxLength={300}
                placeholder="例如：switch=staff"
                value={action.data ?? ''}
                onChange={(event) => updateAction({ ...action, data: event.target.value })}
              />
            </label>
            <label className="richmenu-form-field">
              <span>Rich Menu alias</span>
              <input
                className="richmenu-form-input"
                maxLength={32}
                placeholder="例如：staff-menu"
                value={action.rich_menu_alias_id ?? ''}
                onChange={(event) => updateAction({ ...action, rich_menu_alias_id: event.target.value })}
              />
            </label>
          </>
        )}

        <label className="richmenu-form-field richmenu-form-field-full">
          <span>變更原因</span>
          <input
            className="richmenu-form-input"
            value={reason}
            placeholder="例如：工會人員調整 Rich Menu 按鈕動作"
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
      </div>

      <div className="richmenu-editor-actions" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '16px' }}>
        <button
          type="button"
          className="richmenu-btn-primary"
          style={{ background: '#059669', color: '#fff', fontWeight: 700, padding: '10px 22px', borderRadius: '8px', border: 0, cursor: 'pointer' }}
          onClick={() => void saveDirectly()}
          disabled={status === 'previewing' || status === 'applying'}
        >
          {status === 'applying' ? '正在套用…' : '💾 儲存並套用變更'}
        </button>
        <button
          type="button"
          className="richmenu-btn-secondary"
          onClick={() => void requestPreview()}
          disabled={status === 'previewing' || status === 'applying'}
        >
          預覽草稿變更
        </button>
        <button
          type="button"
          className="richmenu-btn-secondary"
          onClick={() => {
            setDefinition(copyDefinition(draft.definition));
            setPreview(null);
            setConfirmed(false);
            setStatus('idle');
            setMessage('已取消本機修改。');
            onLocalDefinitionChange?.(null);
          }}
        >
          取消修改
        </button>
      </div>

      {preview && (
        <div className="richmenu-preview-callout">
          <p style={{ margin: 0, fontSize: '0.86rem', fontWeight: 600, color: '#166534' }}>
            預覽完成：已核對目前內容與保存後結果。
          </p>
          <label className="richmenu-confirm-checkbox-label">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            我確認保存此草稿；這不會發布或發送 LINE。
          </label>
          <div>
            <button
              type="button"
              className="richmenu-btn-apply"
              onClick={() => void apply()}
              disabled={!confirmed || status === 'applying'}
            >
              套用並回讀
            </button>
          </div>
        </div>
      )}
      {message && (
        <div
          className={status === 'error' ? 'line-error' : 'line-scope-note'}
          role={status === 'error' ? 'alert' : 'status'}
          style={{ marginTop: '12px' }}
        >
          {message}
        </div>
      )}
    </section>
  );
};
