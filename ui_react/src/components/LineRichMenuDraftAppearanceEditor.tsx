/**
 * File: LineRichMenuDraftAppearanceEditor.tsx
 * Description: 編輯共用草稿的選單名稱、底色與受控背景圖；儲存由工作區統一處理。
 */
import React, { useEffect, useState } from 'react';
import { Palette } from 'lucide-react';
import {
  lineRichMenuMediaClient,
  type LineRichMenuMediaClient,
} from '../api/line_rich_menu_media/line_rich_menu_media_client';
import type { RichMenuMediaAsset } from '../api/line_rich_menu_media/line_rich_menu_media_schemas';
import type {
  RichMenuDraft,
  RichMenuDraftDefinition,
} from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';

interface Props {
  draft: RichMenuDraft;
  menuId: string | null;
  definition: RichMenuDraftDefinition;
  onDefinitionChange: (definition: RichMenuDraftDefinition) => void;
  mediaClient?: LineRichMenuMediaClient;
}

export const LineRichMenuDraftAppearanceEditor: React.FC<Props> = ({
  draft,
  menuId,
  definition,
  onDefinitionChange,
  mediaClient = lineRichMenuMediaClient,
}) => {
  const [mediaAssets, setMediaAssets] = useState<RichMenuMediaAsset[]>([]);
  const [mediaState, setMediaState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');
  const [mediaMessage, setMediaMessage] = useState<string | null>(null);

  const menu = definition.menus.find((item) => item.id === menuId) ?? definition.menus[0];
  const publicationLock = draft.publication_locks.find(
    (item) => item.menu_definition_id === menu?.id
      && item.configuration_revision === draft.revision,
  );
  const mediaMenuId = menu?.id;
  const publicationState = publicationLock?.state;
  const canCreateNextDraft = publicationState === 'editable' || publicationState === 'published';

  useEffect(() => {
    if (!mediaMenuId || !canCreateNextDraft) {
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
  }, [canCreateNextDraft, draft.revision, mediaClient, mediaMenuId]);

  const updateMenu = (change: (current: NonNullable<typeof menu>) => NonNullable<typeof menu>) => {
    if (!menu) return;
    const nextDefinition: RichMenuDraftDefinition = {
      ...definition,
      menus: definition.menus.map((item) => item.id === menu.id ? change(item) : item),
    };
    onDefinitionChange(nextDefinition);
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

  if (!menu) {
    return <div className="line-scope-note">目前沒有可編輯的 Rich Menu 草稿。</div>;
  }

  const readonlyReason = canCreateNextDraft
    ? null
    : publicationLock?.readonly_reason
      ?? '目前無法確認這個選單版本是否可編輯，已安全切換為唯讀。';
  if (readonlyReason) {
    return (
      <section className="richmenu-card" data-control-id="line.richmenu.draft.appearance-editor">
        <div className="richmenu-card-header">
          <div>
            <h4 className="richmenu-editor-title">
              <Palette aria-hidden="true" />修改選單外觀與名稱
            </h4>
            <p className="richmenu-editor-description">
              此版本保留原始發布內容，目前不提供修改。
            </p>
          </div>
          <span className="line-category-badge category-service_flow">唯讀</span>
        </div>
        <div className="line-scope-note" role="status">{readonlyReason}</div>
      </section>
    );
  }

  return (
    <section className="richmenu-card" data-control-id="line.richmenu.draft.appearance-editor">
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
          <span>聊天室選單列文字</span>
          <input
            className="richmenu-form-input"
            maxLength={14}
            required
            value={menu.chat_bar_text}
            onChange={(event) => updateMenu((current) => ({ ...current, chat_bar_text: event.target.value }))}
          />
        </label>
        <div className="richmenu-form-field richmenu-form-field-full">
          <span>選單底色</span>
          <div className="richmenu-color-options" role="group" aria-label="選單底色">
            {['#FFF1DF', '#FFF0EC', '#EAF2ED', '#EAF0F8', '#F2EDF6', '#FFFFFF'].map((color) => (
              <button key={color} type="button" className="richmenu-color-swatch"
                style={{ backgroundColor: color }} aria-label={`底色 ${color}`}
                aria-pressed={menu.appearance?.background_color?.toUpperCase() === color}
                disabled={menu.appearance?.image_mode === 'uploaded'}
                onClick={() => updateBackground(color)} />
            ))}
            <label className="richmenu-custom-color">自訂
              <input type="color" aria-label="自訂選單底色" value={/^#[0-9a-f]{6}$/i.test(menu.appearance?.background_color ?? '') ? menu.appearance!.background_color : '#FFFFFF'}
                disabled={menu.appearance?.image_mode === 'uploaded'} onChange={(event) => updateBackground(event.target.value)} />
            </label>
          </div>
          <small>調整卡片之間的底色，卡片本身維持白色。使用背景圖片時不會替圖片換色。</small>
        </div>
      </div>

      <details className="richmenu-advanced-details richmenu-background-details">
        <summary>背景圖片</summary>
        <fieldset className="richmenu-form-field richmenu-form-field-full richmenu-form-section-spacing">
        <legend className="sr-only">選擇背景來源</legend>
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
      </details>

    </section>
  );
};
