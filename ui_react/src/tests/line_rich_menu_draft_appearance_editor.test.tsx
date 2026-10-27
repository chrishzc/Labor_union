/** Verify shared-draft appearance fields and confirmed save/readback without publication. */
import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LineRichMenuMediaClient } from '../api/line_rich_menu_media/line_rich_menu_media_client';
import type { RichMenuMediaAsset } from '../api/line_rich_menu_media/line_rich_menu_media_schemas';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type { RichMenuDraft } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';
import { LineRichMenuDraftAppearanceEditor } from '../components/LineRichMenuDraftAppearanceEditor';
import { LineRichMenuDraftSaveActions } from '../components/LineRichMenuDraftSaveActions';
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


function client(initial = DRAFT): LineRichMenuDraftClient {
  let stored = structuredClone(initial);
  return {
    query: vi.fn(async () => structuredClone(stored)),
    preview: vi.fn(async request => ({ before_revision: stored.revision, resulting_revision: stored.revision + 1, normalized_definition: request.definition, preview_fingerprint: FINGERPRINT })),
    apply: vi.fn(async request => {
      stored = { ...stored, revision: stored.revision + 1, definition: request.definition, publication_locks: stored.publication_locks.map(lock => ({ ...lock, configuration_revision: stored.revision + 1, state: 'editable' as const, readonly_reason: null })) };
      return { receipt: { outcome: 'created' as const, committed_revision: stored.revision, receipt_reference: 'rich-menu-save' }, readback: structuredClone(stored) };
    }),
  };
}
function media(items: RichMenuMediaAsset[] = [ASSET]): LineRichMenuMediaClient {
  return { list: vi.fn(async () => ({ items, page: 1, page_size: 100, total: items.length, total_pages: 1 })) };
}
function Harness({ initial = DRAFT, draftClient = client(initial), mediaClient = media() }: { initial?: RichMenuDraft; draftClient?: LineRichMenuDraftClient; mediaClient?: LineRichMenuMediaClient }) {
  const [draft, setDraft] = useState(initial);
  const [definition, setDefinition] = useState(initial.definition);
  return <><LineRichMenuDraftAppearanceEditor draft={draft} menuId={definition.menus[0]?.id ?? null} definition={definition} onDefinitionChange={setDefinition} mediaClient={mediaClient} />
    <LineRichMenuDraftSaveActions draft={draft} definition={definition} client={draftClient} onBusyChange={() => {}} onReloadRequired={() => {}} publicationAction={null} onCancel={() => setDefinition(draft.definition)} onApplied={next => { setDraft(next); setDefinition(next.definition); }} /></>;
}
const generated = (): RichMenuDraft => ({ ...structuredClone(DRAFT), definition: { ...DRAFT.definition, menus: [{ ...DRAFT.definition.menus[0], appearance: { background_color: '#F5C842', image_mode: 'generated' } }] } });
async function confirmSave() {
  fireEvent.change(screen.getByLabelText('備註（選填）'), { target: { value: '驗證共用草稿' } });
  fireEvent.click(screen.getByRole('button', { name: '儲存草稿' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByRole('checkbox', { name: /我確認儲存此草稿/ })).not.toBeInTheDocument();
}
describe('Rich Menu appearance and shared save', () => {
  it('local editing and confirmed discard never call mutation APIs, and button names have one owner', async () => {
    const draftClient = client(); render(<Harness draftClient={draftClient} />);
    expect(await screen.findByText(/customer-menu\.png/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/按鈕.*名稱/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('選單名稱'), { target: { value: '新的客戶選單' } });
    expect(draftClient.preview).not.toHaveBeenCalled(); expect(draftClient.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '取消修改' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByLabelText('選單名稱')).toHaveValue('客戶服務選單');
    expect(draftClient.apply).not.toHaveBeenCalled(); expect(screen.queryByText(FINGERPRINT)).not.toBeInTheDocument();
    await screen.findByText(/customer-menu\.png/);
  });
  it('controlled media metadata is preserved, unavailable assets disabled and uploaded images cannot be recolored', async () => {
    const deleted = { ...ASSET, asset_id: 42, original_filename: 'retired.png', selectable: false, business_reason: '此背景圖已刪除', deleted_at: '2026-08-27T00:00:00Z' };
    render(<Harness mediaClient={media([ASSET, deleted])} />);
    fireEvent.click(screen.getByText('背景圖片', { selector: 'summary' }));
    expect(await screen.findByRole('radio', { name: /retired\.png/ })).toBeDisabled();
    expect(screen.getByLabelText('自訂選單底色')).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: '使用系統色彩背景' }));
    expect(screen.getByLabelText('自訂選單底色')).toBeEnabled();
    fireEvent.click(screen.getByRole('radio', { name: /customer-menu\.png/ }));
    expect(screen.getByLabelText('自訂選單底色')).toBeDisabled();
    expect(screen.queryByText(/^[0-9a-f]{64}$/)).not.toBeInTheDocument();
  });
  it.each(['', '   ', '驗證背景色保存'])('saves only after preview and confirmation with optional note %j, preserving action and bounds', async (note) => {
    const initial = generated(), draftClient = client(initial); render(<Harness initial={initial} draftClient={draftClient} />);
    fireEvent.change(screen.getByLabelText('選單名稱'), { target: { value: '照護服務' } });
    fireEvent.change(screen.getByLabelText('聊天室選單列文字'), { target: { value: '照護選單' } });
    fireEvent.change(screen.getByLabelText('自訂選單底色'), { target: { value: '#123456' } });
    expect(screen.getByLabelText('備註（選填）')).not.toHaveAttribute('aria-required');
    fireEvent.change(screen.getByLabelText('備註（選填）'), { target: { value: note } });
    expect(screen.getByRole('button', { name: '儲存草稿' })).toBeEnabled();
    expect(draftClient.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '儲存草稿' }));
    expect(screen.queryByRole('button', { name: '確認儲存草稿' })).not.toBeInTheDocument();
    await waitFor(() => expect(draftClient.query).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('草稿已儲存並重新載入；尚未發布至 LINE。')).toBeInTheDocument();
    const saved = await draftClient.query();
    expect(saved.definition.menus[0]).toMatchObject({ name: '照護服務', chat_bar_text: '照護選單', appearance: { background_color: '#123456' }, buttons: [{ label: '聯絡客服', action: DRAFT.definition.menus[0].buttons[0].action, bounds: DRAFT.definition.menus[0].buttons[0].bounds }] });
    expect(screen.getByLabelText('自訂選單底色')).toHaveValue('#123456');
    expect(draftClient.apply).toHaveBeenCalledWith(expect.objectContaining({ expected_revision: 8, preview_fingerprint: FINGERPRINT, reason: note.trim() }), expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.getByRole('button', { name: '儲存草稿' })).toBeDisabled();
  });
  it('published snapshots can start a new draft and uploaded asset metadata survives the shared save', async () => {
    const initial = structuredClone(DRAFT); initial.publication_locks[0] = { ...initial.publication_locks[0], state: 'published', readonly_reason: '已發布，可建立新版' };
    const draftClient = client(initial); render(<Harness initial={initial} draftClient={draftClient} />);
    fireEvent.change(screen.getByLabelText('選單名稱'), { target: { value: '新版選單' } }); await confirmSave();
    await waitFor(() => expect(draftClient.query).toHaveBeenCalledTimes(1));
    const saved = await draftClient.query(); expect(saved.definition.menus[0].appearance).toEqual(DRAFT.definition.menus[0].appearance);
  });
  it('processing appearance is read-only', () => {
    const initial = structuredClone(DRAFT); initial.publication_locks[0] = { ...initial.publication_locks[0], state: 'processing', readonly_reason: '正在發布，暫時唯讀' };
    render(<LineRichMenuDraftAppearanceEditor draft={initial} definition={initial.definition} menuId="customer_menu" onDefinitionChange={vi.fn()} />);
    expect(screen.getByText('正在發布，暫時唯讀')).toBeInTheDocument(); expect(screen.queryByLabelText('選單名稱')).not.toBeInTheDocument();
  });
  it('mismatched fresh readback keeps edits and prevents a success claim', async () => {
    const initial = generated(), draftClient = client(initial); vi.mocked(draftClient.query).mockResolvedValue(initial);
    render(<Harness initial={initial} draftClient={draftClient} />);
    fireEvent.change(screen.getByLabelText('自訂選單底色'), { target: { value: '#123456' } }); await confirmSave();
    expect((await screen.findAllByRole('alert')).some(el => el.textContent?.includes('重新載入的內容不同'))).toBe(true);
    expect(screen.queryByText('草稿已儲存並重新載入；尚未發布至 LINE。')).not.toBeInTheDocument();
  });
});
