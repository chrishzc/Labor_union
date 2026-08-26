/**
 * File: line_rich_menu_draft_action_editor.test.tsx
 * Description: 驗證 Rich Menu typed action 編輯、kind 清理及 Preview、確認、Apply 流程。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type { RichMenuDraft } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';
import { LineRichMenuDraftActionEditor } from '../components/LineRichMenuDraftActionEditor';

const FINGERPRINT = 'c'.repeat(64);
const DRAFT: RichMenuDraft = {
  kind: 'rich_menus', revision: 3,
  publication_locks: [{
    menu_definition_id: 'customer_menu', configuration_revision: 3,
    state: 'editable', readonly_reason: null,
  }],
  definition: { version: 1, menus: [{
    id: 'customer_menu', name: '客戶選單', audience_role: 'customer', enabled: true,
    selected: true, set_as_default: true, chat_bar_text: '服務選單',
    buttons: [{
      id: 'contact', label: '聯絡客服', bounds: { x: 0, y: 0, width: 2500, height: 843 },
      action: { type: 'message', text: '我要聯絡客服' },
    }],
  }] },
};

function client(): LineRichMenuDraftClient {
  const query = vi.fn<LineRichMenuDraftClient['query']>();
  const preview: LineRichMenuDraftClient['preview'] = async (request) => ({
    before_revision: 3, resulting_revision: 4,
    normalized_definition: request.definition, preview_fingerprint: FINGERPRINT,
  });
  const apply: LineRichMenuDraftClient['apply'] = async (request) => ({
    receipt: { outcome: 'created', committed_revision: 4, receipt_reference: 'rich-menu-action-4' },
    readback: {
      kind: 'rich_menus', revision: 4, definition: request.definition,
      publication_locks: [{
        menu_definition_id: 'customer_menu', configuration_revision: 4,
        state: 'editable', readonly_reason: null,
      }],
    },
  });
  return {
    query,
    preview: vi.fn(preview),
    apply: vi.fn(apply),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('LineRichMenuDraftActionEditor', () => {
  it('kind 切換只保留新 kind 欄位，取消不寫入', () => {
    const draftClient = client();
    const onLocalDefinitionChange = vi.fn();
    render(<LineRichMenuDraftActionEditor draft={DRAFT} menuId="customer_menu" client={draftClient} onApplied={vi.fn()} onLocalDefinitionChange={onLocalDefinitionChange} />);
    fireEvent.change(screen.getByLabelText('動作類型'), { target: { value: 'postback' } });
    fireEvent.change(screen.getByLabelText('Postback data'), { target: { value: 'case_status' } });
    expect(onLocalDefinitionChange).toHaveBeenLastCalledWith(expect.objectContaining({
      menus: [expect.objectContaining({
        buttons: [expect.objectContaining({ action: { type: 'postback', data: 'case_status' } })],
      })],
    }));
    fireEvent.click(screen.getByRole('button', { name: '取消修改' }));
    expect(screen.getByLabelText('動作類型')).toHaveValue('message');
    expect(screen.getByLabelText('送出訊息')).toHaveValue('我要聯絡客服');
    expect(draftClient.preview).not.toHaveBeenCalled();
    expect(draftClient.apply).not.toHaveBeenCalled();
    expect(onLocalDefinitionChange).toHaveBeenLastCalledWith(null);
  });

  it('只有 Preview 與明確確認後才 Apply normalized typed action', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'action-editor-1' });
    const draftClient = client();
    const onApplied = vi.fn();
    render(<LineRichMenuDraftActionEditor draft={DRAFT} menuId="customer_menu" client={draftClient} onApplied={onApplied} />);
    fireEvent.change(screen.getByLabelText('動作類型'), { target: { value: 'richmenuswitch' } });
    fireEvent.change(screen.getByLabelText('切換資料'), { target: { value: 'switch=staff' } });
    fireEvent.change(screen.getByLabelText('Rich Menu alias'), { target: { value: 'staff-menu' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽草稿變更' }));
    await waitFor(() => expect(draftClient.preview).toHaveBeenCalledTimes(1));
    const request = vi.mocked(draftClient.preview).mock.calls[0][0];
    expect(request.definition.menus[0].buttons[0].action).toEqual({
      type: 'richmenuswitch', data: 'switch=staff', rich_menu_alias_id: 'staff-menu',
    });
    expect(screen.queryByText(FINGERPRINT)).not.toBeInTheDocument();
    const applyButton = screen.getByRole('button', { name: '套用並回讀' });
    expect(applyButton).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /我確認保存此草稿/ }));
    fireEvent.click(applyButton);
    await waitFor(() => expect(draftClient.apply).toHaveBeenCalledTimes(1));
    expect(draftClient.apply).toHaveBeenCalledWith(expect.objectContaining({
      expected_revision: 3, preview_fingerprint: FINGERPRINT,
      idempotency_key: 'rich-menu-draft-action-editor-1',
      correlation_id: 'rich-menu-draft-action-editor-1',
    }));
    expect(onApplied).toHaveBeenCalledWith(expect.objectContaining({ revision: 4 }));
  });

  it('processing 版本只顯示業務原因且不掛載 mutation controls', () => {
    const draftClient = client();
    render(<LineRichMenuDraftActionEditor
      draft={{
        ...DRAFT,
        publication_locks: [{
          menu_definition_id: 'customer_menu', configuration_revision: 3,
          state: 'processing', readonly_reason: '此版本正在發布處理中，目前只能查看。',
        }],
      }}
      menuId="customer_menu"
      client={draftClient}
      onApplied={vi.fn()}
    />);

    expect(screen.getByText('此版本正在發布處理中，目前只能查看。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽草稿變更' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('動作類型')).not.toBeInTheDocument();
    expect(draftClient.preview).not.toHaveBeenCalled();
    expect(draftClient.apply).not.toHaveBeenCalled();
  });
});
