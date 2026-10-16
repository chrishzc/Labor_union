/** Verify the single button-name owner and typed action fields in a shared draft. */
import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { RichMenuDraft } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';
import { LineRichMenuDraftActionEditor } from '../components/LineRichMenuDraftActionEditor';
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


function Harness({ initial = DRAFT }: { initial?: RichMenuDraft }) {
  const [definition, setDefinition] = useState(initial.definition);
  return <LineRichMenuDraftActionEditor draft={initial} menuId={definition.menus[0]?.id ?? null} definition={definition} onDefinitionChange={setDefinition} />;
}
describe('LineRichMenuDraftActionEditor', () => {
  it('editing the button name does not change the actual message, and switching action kind clears incompatible fields', () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText('按鈕顯示名稱'), { target: { value: '專人諮詢' } });
    expect(screen.getByLabelText('送出訊息')).toHaveValue('我要聯絡客服');
    fireEvent.change(screen.getByLabelText('點擊後的動作'), { target: { value: 'postback' } });
    fireEvent.change(screen.getByLabelText('系統動作資料'), { target: { value: 'case_status' } });
    fireEvent.change(screen.getByLabelText('點擊後的動作'), { target: { value: 'message' } });
    expect(screen.getByLabelText('送出訊息')).toHaveValue('');
    expect(screen.queryByLabelText('系統動作資料')).not.toBeInTheDocument();
    expect(screen.getByLabelText('按鈕顯示名稱')).toHaveValue('專人諮詢');
  });
  it('offers supported canonical LIFF choices and no switch or retired anomaly entry', () => {
    render(<Harness />); fireEvent.change(screen.getByLabelText('點擊後的動作'), { target: { value: 'uri' } });
    expect(screen.queryByRole('option', { name: /切換 Rich Menu/ })).not.toBeInTheDocument();
    for (const name of ['狀態追蹤', '月嫂身分綁定', '修改訂單資訊']) expect(screen.getByRole('option', { name })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /anomalies_center|異常中心/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('LIFF target／網址'), { target: { value: '?target=profile_update' } });
    expect(screen.getByLabelText('LIFF target／網址')).toHaveValue('?target=profile_update');
  });
  it('processing versions expose the business reason without editable controls', () => {
    const initial = structuredClone(DRAFT); initial.publication_locks[0] = { ...initial.publication_locks[0], state: 'processing', readonly_reason: '此版本正在發布處理中' };
    render(<Harness initial={initial} />);
    expect(screen.getByText('此版本正在發布處理中')).toBeInTheDocument(); expect(screen.queryByLabelText('按鈕顯示名稱')).not.toBeInTheDocument();
  });
  it('published union staff content can be edited into the shared next draft', () => {
    const initial = structuredClone(DRAFT); initial.definition.menus[0].id = 'union_staff_menu'; initial.definition.menus[0].audience_role = 'union_staff';
    initial.publication_locks[0] = { menu_definition_id: 'union_staff_menu', configuration_revision: 3, state: 'published', readonly_reason: '已發布' };
    render(<Harness initial={initial} />); fireEvent.change(screen.getByLabelText('送出訊息'), { target: { value: '開啟工會客服' } });
    expect(screen.getByLabelText('送出訊息')).toHaveValue('開啟工會客服'); expect(screen.getByLabelText('按鈕顯示名稱')).toHaveValue('聯絡客服');
  });
  it('unlisted current LIFF values remain selected and are never silently replaced', () => {
    const initial = structuredClone(DRAFT); initial.definition.menus[0].buttons[0].action = { type: 'uri', uri: '?target=custom_preview_flow', uri_source: 'liff' };
    render(<Harness initial={initial} />); expect(screen.getByLabelText('LIFF target／網址')).toHaveValue('?target=custom_preview_flow');
    expect(screen.getByRole('option', { name: '?target=custom_preview_flow（自訂／未收錄入口）' })).toBeInTheDocument();
  });
  it('an unknown publication lock fails closed', () => {
    const initial = structuredClone(DRAFT); initial.publication_locks = [];
    render(<LineRichMenuDraftActionEditor draft={initial} menuId="customer_menu" definition={initial.definition} onDefinitionChange={vi.fn()} />);
    expect(screen.getByText(/無法確認這個選單版本是否可編輯/)).toBeInTheDocument(); expect(screen.queryByLabelText('按鈕顯示名稱')).not.toBeInTheDocument();
  });
});
