/**
 * File: line_rich_menu_draft_appearance_editor.test.tsx
 * Description: 驗證 Rich Menu 外觀草稿只改顯示欄位，並經 Preview、確認、Apply 完成回讀。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LineRichMenuMediaClient } from '../api/line_rich_menu_media/line_rich_menu_media_client';
import type { RichMenuMediaAsset } from '../api/line_rich_menu_media/line_rich_menu_media_schemas';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type { RichMenuDraft } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';
import { LineRichMenuDraftAppearanceEditor } from '../components/LineRichMenuDraftAppearanceEditor';

const FINGERPRINT = 'b'.repeat(64);
const ASSET: RichMenuMediaAsset = {
  asset_id: 41,
  menu_definition_id: 'customer_menu',
  original_filename: 'customer-menu.png',
  mime_type: 'image/png',
  file_size: 1024,
  sha256: 'a'.repeat(64),
  width: 2500,
  height: 843,
  created_at: '2026-08-26T00:00:00Z',
  deleted_at: null,
  selectable: true,
  business_reason: null,
  asset_version: 'c'.repeat(64),
};
const DRAFT: RichMenuDraft = {
  kind: 'rich_menus', revision: 8,
  publication_locks: [{
    menu_definition_id: 'customer_menu', configuration_revision: 8,
    state: 'editable', readonly_reason: null,
  }],
  definition: { version: 4, menus: [{
    id: 'customer_menu', name: '客戶服務選單', audience_role: 'customer', enabled: true,
    selected: true, set_as_default: true, chat_bar_text: '服務選單',
    appearance: {
      background_color: '#F5C842', image_mode: 'uploaded', image_asset_id: 41,
      image_asset_sha256: 'a'.repeat(64), image_asset_version: 'c'.repeat(64),
    },
    buttons: [{
      id: 'contact', label: '聯絡客服', bounds: { x: 0, y: 0, width: 1250, height: 843 },
      action: { type: 'message', text: '我要聯絡客服' },
    }],
  }] },
};

function client(): LineRichMenuDraftClient {
  return {
    query: vi.fn(),
    preview: vi.fn(async (request) => ({
      before_revision: 8, resulting_revision: 9,
      normalized_definition: request.definition, preview_fingerprint: FINGERPRINT,
    })),
    apply: vi.fn(async (request) => ({
      receipt: { outcome: 'created' as const, committed_revision: 9, receipt_reference: 'rich-menu-appearance-9' },
      readback: {
        kind: 'rich_menus' as const, revision: 9, definition: request.definition,
        publication_locks: [{
          menu_definition_id: 'customer_menu', configuration_revision: 9,
          state: 'editable' as const, readonly_reason: null,
        }],
      },
    })),
  };
}

function media(items: RichMenuMediaAsset[] = [ASSET]): LineRichMenuMediaClient {
  return {
    list: vi.fn(async () => ({ items, page: 1, page_size: 100, total: items.length, total_pages: 1 })),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('LineRichMenuDraftAppearanceEditor', () => {
  it('本機編輯與取消皆零寫入，且不顯示 fingerprint 或 provider 欄位', async () => {
    const draftClient = client();
    const onLocalDefinitionChange = vi.fn();
    render(<LineRichMenuDraftAppearanceEditor draft={DRAFT} menuId="customer_menu" client={draftClient} mediaClient={media()} onApplied={vi.fn()} onLocalDefinitionChange={onLocalDefinitionChange} />);
    expect(await screen.findByText(/customer-menu\.png/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('選單名稱'), { target: { value: '新的客戶選單' } });
    fireEvent.change(screen.getByLabelText('按鈕 1 名稱'), { target: { value: '真人客服' } });
    expect(onLocalDefinitionChange).toHaveBeenLastCalledWith(expect.objectContaining({
      menus: [expect.objectContaining({
        name: '新的客戶選單',
        buttons: [expect.objectContaining({ label: '真人客服' })],
      })],
    }));
    expect(draftClient.query).not.toHaveBeenCalled();
    expect(draftClient.preview).not.toHaveBeenCalled();
    expect(draftClient.apply).not.toHaveBeenCalled();
    expect(screen.queryByText(FINGERPRINT)).not.toBeInTheDocument();
    expect(screen.queryByText(/provider/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '取消修改' }));
    expect(screen.getByLabelText('選單名稱')).toHaveValue('客戶服務選單');
    expect(screen.getByLabelText('按鈕 1 名稱')).toHaveValue('聯絡客服');
    expect(draftClient.preview).not.toHaveBeenCalled();
    expect(onLocalDefinitionChange).toHaveBeenLastCalledWith(null);
  });

  it('只從 owner-scoped 清單選擇 exact asset，已刪除圖片顯示原因且不可選', async () => {
    const deleted = {
      ...ASSET,
      asset_id: 42,
      original_filename: 'retired.png',
      deleted_at: '2026-08-27T00:00:00Z',
      selectable: false,
      business_reason: '此背景圖已刪除，只保留歷史查詢，不能再選用。',
      asset_version: 'd'.repeat(64),
    } satisfies RichMenuMediaAsset;
    const mediaClient = media([ASSET, deleted]);
    const onLocalDefinitionChange = vi.fn();
    render(<LineRichMenuDraftAppearanceEditor
      draft={{
        ...DRAFT,
        definition: {
          ...DRAFT.definition,
          menus: [{
            ...DRAFT.definition.menus[0],
            appearance: { background_color: '#F5C842', image_mode: 'generated' },
          }],
        },
      }}
      menuId="customer_menu"
      client={client()}
      mediaClient={mediaClient}
      onApplied={vi.fn()}
      onLocalDefinitionChange={onLocalDefinitionChange}
    />);

    expect(await screen.findByText(/customer-menu\.png/)).toBeInTheDocument();
    const deletedChoice = screen.getByRole('radio', { name: /retired\.png/ });
    expect(deletedChoice).toBeDisabled();
    expect(screen.getByText(/此背景圖已刪除/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: /customer-menu\.png/ }));
    expect(onLocalDefinitionChange).toHaveBeenLastCalledWith(expect.objectContaining({
      menus: [expect.objectContaining({
        appearance: {
          background_color: '#F5C842',
          image_mode: 'uploaded',
          image_asset_id: 41,
          image_asset_sha256: 'a'.repeat(64),
          image_asset_version: 'c'.repeat(64),
        },
      })],
    }));
    expect(screen.queryByText(/^[0-9a-f]{64}$/)).not.toBeInTheDocument();
  });

  it('Preview 保留 action 與影像 metadata，明確確認後才以 normalized definition Apply', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'appearance-editor-1' });
    const draftClient = client();
    const onApplied = vi.fn();
    render(<LineRichMenuDraftAppearanceEditor draft={DRAFT} menuId="customer_menu" client={draftClient} mediaClient={media()} onApplied={onApplied} />);
    fireEvent.change(screen.getByLabelText('選單名稱'), { target: { value: '照護服務' } });
    fireEvent.change(screen.getByLabelText('聊天室標題'), { target: { value: '照護選單' } });
    fireEvent.change(screen.getByLabelText('背景色彩'), { target: { value: '#123456' } });
    fireEvent.change(screen.getByLabelText('按鈕 1 名稱'), { target: { value: '聯絡工會' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽草稿變更' }));
    await waitFor(() => expect(draftClient.preview).toHaveBeenCalledTimes(1));
    const previewRequest = vi.mocked(draftClient.preview).mock.calls[0][0];
    const menu = previewRequest.definition.menus[0];
    expect(menu).toMatchObject({
      name: '照護服務', chat_bar_text: '照護選單',
      appearance: {
        background_color: '#123456', image_mode: 'uploaded', image_asset_id: 41,
        image_asset_sha256: 'a'.repeat(64), image_asset_version: 'c'.repeat(64),
      },
    });
    expect(menu.buttons[0]).toMatchObject({
      label: '聯絡工會', bounds: DRAFT.definition.menus[0].buttons[0].bounds,
      action: { type: 'message', text: '我要聯絡客服' },
    });
    expect(screen.queryByText(FINGERPRINT)).not.toBeInTheDocument();
    const applyButton = screen.getByRole('button', { name: '套用並回讀' });
    expect(applyButton).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /我確認保存此草稿/ }));
    fireEvent.click(applyButton);
    await waitFor(() => expect(draftClient.apply).toHaveBeenCalledTimes(1));
    expect(draftClient.apply).toHaveBeenCalledWith(expect.objectContaining({
      expected_revision: 8, definition: previewRequest.definition, preview_fingerprint: FINGERPRINT,
      idempotency_key: 'rich-menu-appearance-appearance-editor-1',
      correlation_id: 'rich-menu-appearance-appearance-editor-1',
    }));
    expect(onApplied).toHaveBeenCalledWith(expect.objectContaining({ revision: 9 }));
    expect(await screen.findByText(/草稿已保存並完成回讀/)).toBeInTheDocument();
    expect(draftClient.query).not.toHaveBeenCalled();
  });

  it('published 版本只顯示業務原因且不掛載外觀 mutation controls', () => {
    const draftClient = client();
    render(<LineRichMenuDraftAppearanceEditor
      draft={{
        ...DRAFT,
        publication_locks: [{
          menu_definition_id: 'customer_menu', configuration_revision: 8,
          state: 'published', readonly_reason: '此版本已正式發布，目前只能查看。',
        }],
      }}
      menuId="customer_menu"
      client={draftClient}
      mediaClient={media()}
      onApplied={vi.fn()}
    />);

    expect(screen.getByText('此版本已正式發布，目前只能查看。')).toBeInTheDocument();
    expect(screen.queryByLabelText('選單名稱')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽草稿變更' })).not.toBeInTheDocument();
    expect(draftClient.preview).not.toHaveBeenCalled();
    expect(draftClient.apply).not.toHaveBeenCalled();
  });
});
