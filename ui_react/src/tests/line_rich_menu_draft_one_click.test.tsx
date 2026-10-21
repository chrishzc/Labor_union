import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LineRichMenuDraftSaveActions } from '../components/LineRichMenuDraftSaveActions';
import type { LineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type { RichMenuDraft } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';

const draft: RichMenuDraft = {
  kind: 'rich_menus', revision: 3,
  publication_locks: [{ menu_definition_id: 'customer_menu', configuration_revision: 3, state: 'editable', readonly_reason: null }],
  definition: { version: 1, menus: [{
    id: 'customer_menu', name: '客戶選單', audience_role: 'customer', enabled: true,
    selected: true, set_as_default: true, chat_bar_text: '服務選單',
    buttons: [{ id: 'contact', label: '聯絡客服', bounds: { x: 0, y: 0, width: 2500, height: 843 }, action: { type: 'message', text: '我要聯絡客服' } }],
  }] },
};

function setup() {
  const definition = structuredClone(draft.definition);
  definition.menus[0].chat_bar_text = '服務與協助';
  const client: LineRichMenuDraftClient = {
    preview: vi.fn().mockResolvedValue({ before_revision: 3, normalized_definition: definition, preview_fingerprint: 'a'.repeat(64) }),
    apply: vi.fn().mockResolvedValue({ receipt: { committed_revision: 4 } }),
    query: vi.fn().mockResolvedValue({ ...draft, revision: 4, definition }),
  };
  const applied = vi.fn();
  render(<LineRichMenuDraftSaveActions draft={draft} definition={definition} client={client} onApplied={applied} onCancel={vi.fn()} onBusyChange={vi.fn()} onReloadRequired={vi.fn()} publicationAction={null} />);
  return { client, definition, applied };
}

describe('Rich Menu one-click draft save', () => {
  it.each(['', '   ', '調整服務入口'])('saves once with optional note %j and verifies the actual readback', async note => {
    const { client, definition, applied } = setup();
    fireEvent.change(screen.getByLabelText('備註（選填）'), { target: { value: note } });
    expect(client.apply).not.toHaveBeenCalled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存草稿' }));
    await screen.findByText('草稿已儲存並重新載入；尚未發布至 LINE。');
    expect(client.preview).toHaveBeenCalledOnce();
    expect(client.apply).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
      expected_revision: 3, definition, preview_fingerprint: 'a'.repeat(64), reason: note.trim(),
      idempotency_key: expect.any(String), correlation_id: expect.any(String),
    }), expect.any(Object));
    expect(applied).toHaveBeenCalledWith(expect.objectContaining({ revision: 4, definition }));
  });

  it('does not apply an invalid backend candidate', async () => {
    const { client, applied } = setup();
    vi.mocked(client.preview).mockRejectedValue(new Error('草稿已被其他人更新'));
    fireEvent.click(screen.getByRole('button', { name: '儲存草稿' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('草稿已被其他人更新');
    expect(client.apply).not.toHaveBeenCalled();
    expect(applied).not.toHaveBeenCalled();
  });

  it('reuses the exact command after an uncertain save result', async () => {
    const { client } = setup();
    vi.mocked(client.apply).mockRejectedValueOnce(new Error('連線中斷，結果未知'));
    fireEvent.click(screen.getByRole('button', { name: '儲存草稿' }));
    await screen.findByText('連線中斷，結果未知');
    fireEvent.click(screen.getByRole('button', { name: '儲存草稿' }));
    await waitFor(() => expect(client.apply).toHaveBeenCalledTimes(2));
    expect(vi.mocked(client.apply).mock.calls[1][0]).toEqual(vi.mocked(client.apply).mock.calls[0][0]);
    expect(client.preview).toHaveBeenCalledOnce();
  });
});
