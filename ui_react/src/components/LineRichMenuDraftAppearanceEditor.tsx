/**
 * File: LineRichMenuDraftAppearanceEditor.tsx
 * Description: 在瀏覽器記憶體編輯 Rich Menu 顯示欄位，並以專用草稿 Preview、確認、Apply 保存。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  lineRichMenuMediaClient,
  type LineRichMenuMediaClient,
} from '../api/line_rich_menu_media/line_rich_menu_media_client';
import type { RichMenuMediaAsset } from '../api/line_rich_menu_media/line_rich_menu_media_schemas';
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
  mediaClient?: LineRichMenuMediaClient;
  onApplied: (draft: RichMenuDraft) => void;
  onLocalDefinitionChange?: (definition: RichMenuDraftDefinition | null) => void;
  previewDefinition?: RichMenuDraftDefinition;
}

type Status = 'idle' | 'previewing' | 'previewed' | 'applying' | 'applied' | 'error';

function copyDefinition(value: RichMenuDraftDefinition): RichMenuDraftDefinition {
  return structuredClone(value);
}

export const LineRichMenuDraftAppearanceEditor: React.FC<Props> = ({
  draft,
  menuId,
  client,
  mediaClient = lineRichMenuMediaClient,
  onApplied,
  onLocalDefinitionChange,
  previewDefinition,
}) => {
  const [definition, setDefinition] = useState(() => copyDefinition(draft.definition));
  const [preview, setPreview] = useState<RichMenuDraftPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState('工會人員調整 Rich Menu 顯示內容');
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const [mediaAssets, setMediaAssets] = useState<RichMenuMediaAsset[]>([]);
  const [mediaState, setMediaState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');
  const [mediaMessage, setMediaMessage] = useState<string | null>(null);
  const appliedRevision = useRef<number | null>(null);

  useEffect(() => {
    const preserveApplyReadback = appliedRevision.current === draft.revision;
    setDefinition(copyDefinition(draft.definition));
    setPreview(null);
    setConfirmed(false);
    if (!preserveApplyReadback) {
      setStatus('idle');
      setMessage(null);
    }
    appliedRevision.current = null;
  }, [draft]);

  const menu = definition.menus.find((item) => item.id === menuId) ?? definition.menus[0];
  const publicationLock = draft.publication_locks.find(
    (item) => item.menu_definition_id === menu?.id
      && item.configuration_revision === draft.revision,
  );
  const mediaMenuId = menu?.id;
  const publicationState = publicationLock?.state;

  useEffect(() => {
    if (!mediaMenuId || publicationState !== 'editable') {
      setMediaAssets([]);
      setMediaState('idle');
      setMediaMessage(null);
      return;
    }
    const controller = new AbortController();
    let current = true;
    setMediaState('loading');
    setMediaMessage(null);
    void mediaClient.list(mediaMenuId, { signal: controller.signal }).then((page) => {
      if (!current) return;
      setMediaAssets(page.items);
      setMediaState('loaded');
    }).catch((error) => {
      if (!current) return;
      setMediaAssets([]);
      setMediaState('error');
      setMediaMessage(error instanceof Error ? error.message : '無法載入受控背景圖。');
    });
    return () => {
      current = false;
      controller.abort();
    };
  }, [draft.revision, mediaClient, mediaMenuId, publicationState]);

  const invalidatePreview = () => {
    setPreview(null);
    setConfirmed(false);
    setStatus('idle');
    setMessage(null);
  };

  const updateMenu = (change: (current: NonNullable<typeof menu>) => NonNullable<typeof menu>) => {
    if (!menu) return;
    const nextDefinition: RichMenuDraftDefinition = {
      ...definition,
      menus: definition.menus.map((item) => item.id === menu.id ? change(item) : item),
    };
    setDefinition(nextDefinition);
    onLocalDefinitionChange?.(copyDefinition(nextDefinition));
    invalidatePreview();
  };

  const updateBackground = (backgroundColor: string) => {
    updateMenu((current) => {
      const appearance = { ...current.appearance };
      if (backgroundColor.trim()) appearance.background_color = backgroundColor;
      else delete appearance.background_color;
      return { ...current, appearance: Object.keys(appearance).length > 0 ? appearance : undefined };
    });
  };

  const selectGeneratedBackground = () => {
    updateMenu((current) => ({
      ...current,
      appearance: {
        background_color: current.appearance?.background_color,
        image_mode: 'generated',
      },
    }));
  };

  const selectMediaAsset = (asset: RichMenuMediaAsset) => {
    if (!asset.selectable) return;
    updateMenu((current) => ({
      ...current,
      appearance: {
        background_color: current.appearance?.background_color,
        image_mode: 'uploaded',
        image_asset_id: asset.asset_id,
        image_asset_sha256: asset.sha256,
        image_asset_version: asset.asset_version,
      },
    }));
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
    if (!preview || !confirmed || !reason.trim()) return;
    setStatus('applying');
    setMessage(null);
    try {
      const identity = crypto.randomUUID();
      const result = await client.apply({
        expected_revision: draft.revision,
        definition: preview.normalized_definition,
        preview_fingerprint: preview.preview_fingerprint,
        reason: reason.trim(),
        idempotency_key: `rich-menu-appearance-${identity}`,
        correlation_id: `rich-menu-appearance-${identity}`,
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

  if (!menu) {
    return <div className="line-scope-note">目前沒有可編輯的 Rich Menu 草稿。</div>;
  }

  const readonlyReason = publicationLock?.state === 'editable'
    ? null
    : publicationLock?.readonly_reason
      ?? '目前無法確認這個選單版本是否可編輯，已安全切換為唯讀。';
  if (readonlyReason) {
    return (
      <section className="richmenu-card" data-control-id="line.richmenu.draft.appearance-editor">
        <div className="richmenu-card-header">
          <div>
            <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
              🎨 修改選單外觀與名稱
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

  const invalid = !menu.name.trim()
    || !menu.chat_bar_text.trim()
    || menu.buttons.some((button) => !button.label.trim());

  return (
    <section className="richmenu-card" data-control-id="line.richmenu.draft.appearance-editor">
      <div className="richmenu-card-header">
        <div>
          <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
            🎨 修改選單外觀與名稱
          </h4>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
            修改先保留在本機；保存草稿不會發布或發送 LINE。
          </p>
        </div>
        <span className="line-category-badge category-service_flow">編輯草稿</span>
      </div>

      <div className="richmenu-form-grid">
        <label className="richmenu-form-field">
          <span>選單名稱</span>
          <input
            className="richmenu-form-input"
            maxLength={300}
            required
            value={menu.name}
            onChange={(event) => updateMenu((current) => ({ ...current, name: event.target.value }))}
          />
        </label>
        <label className="richmenu-form-field">
          <span>聊天室標題</span>
          <input
            className="richmenu-form-input"
            maxLength={14}
            required
            value={menu.chat_bar_text}
            onChange={(event) => updateMenu((current) => ({ ...current, chat_bar_text: event.target.value }))}
          />
        </label>
        <label className="richmenu-form-field">
          <span>背景色彩</span>
          <input
            className="richmenu-form-input"
            placeholder="#F5C842"
            value={menu.appearance?.background_color ?? ''}
            onChange={(event) => updateBackground(event.target.value)}
          />
        </label>
      </div>

      <fieldset className="richmenu-form-field richmenu-form-field-full" style={{ marginBottom: '14px' }}>
        <legend>背景圖片</legend>
        <label className="richmenu-confirm-checkbox-label">
          <input
            type="radio"
            name={`rich-menu-background-${menu.id}`}
            checked={(menu.appearance?.image_mode ?? 'generated') === 'generated'}
            onChange={selectGeneratedBackground}
          />
          使用系統色彩背景
        </label>
        {mediaState === 'loading' && (
          <div className="line-scope-note" role="status">正在載入可用背景圖…</div>
        )}
        {mediaState === 'error' && (
          <div className="line-error" role="alert">{mediaMessage ?? '無法載入受控背景圖。'}</div>
        )}
        {mediaState === 'loaded' && mediaAssets.length === 0 && (
          <div className="line-scope-note" role="status">
            目前沒有這個選單可用的受控背景圖；仍可使用系統色彩背景。
          </div>
        )}
        {mediaState === 'loaded' && mediaAssets.map((asset) => (
          <label key={asset.asset_id} className="richmenu-confirm-checkbox-label">
            <input
              type="radio"
              name={`rich-menu-background-${menu.id}`}
              checked={menu.appearance?.image_mode === 'uploaded'
                && menu.appearance.image_asset_id === asset.asset_id
                && menu.appearance.image_asset_sha256 === asset.sha256
                && menu.appearance.image_asset_version === asset.asset_version}
              disabled={!asset.selectable}
              onChange={() => selectMediaAsset(asset)}
            />
            <span>
              {asset.original_filename ?? '受控背景圖'}（{asset.width} × {asset.height}）
              {!asset.selectable && ` — ${asset.business_reason ?? '此背景圖目前不可選用。'}`}
            </span>
          </label>
        ))}
      </fieldset>

      <div className="richmenu-buttons-grid-fields">
        <div className="richmenu-buttons-grid-fields-title">
          🔘 各按鈕顯示名稱配置 (共 {menu.buttons.length} 個熱區)
        </div>
        {menu.buttons.map((button, index) => (
          <label key={button.id} className="richmenu-form-field">
            <span>按鈕 {index + 1} 名稱</span>
            <input
              className="richmenu-form-input"
              maxLength={30}
              required
              value={button.label}
              onChange={(event) => updateMenu((current) => ({
                ...current,
                buttons: current.buttons.map((item) => item.id === button.id
                  ? { ...item, label: event.target.value }
                  : item),
              }))}
            />
          </label>
        ))}
      </div>

      <label className="richmenu-form-field richmenu-form-field-full" style={{ marginBottom: '14px' }}>
        <span>變更原因</span>
        <input
          className="richmenu-form-input"
          value={reason}
          placeholder="例如：工會人員調整 Rich Menu 顯示內容"
          onChange={(event) => setReason(event.target.value)}
        />
      </label>

      <div className="richmenu-editor-actions">
        <button
          type="button"
          className="richmenu-btn-primary"
          onClick={() => void requestPreview()}
          disabled={invalid || status === 'previewing' || status === 'applying'}
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
              disabled={!confirmed || !reason.trim() || status === 'applying'}
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
