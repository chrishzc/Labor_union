/**
 * File: ai_event_studio_local_preview.test.tsx
 * Description: 驗證引導動作頁的聊天室指令編輯與唯讀路由預覽。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AiEventStudio } from '../pages/line_management/AiEventStudio';

describe('AI 事件工作室正式規則 readback', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockReadback = () => vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input);
    if (path.includes('/catalog/admin_binding/aliases') && init?.method === 'PUT') {
      const body = JSON.parse(String(init?.body ?? '{}')) as { aliases: string[] };
      return new Response(JSON.stringify({
        data: {
          revision: 4,
          entries: body.aliases.map((a: string) => ({
            alias: a,
            route_key: 'admin_binding',
            tier: 'identity',
            source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1',
            revision: 4,
          })),
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (path.endsWith('/catalog')) {
      return new Response(JSON.stringify({ data: {
        revision: 3,
        entries: [
          ['修改登記資料', 'profile_update', 'navigation'],
          ['延期一次', 'group_postponement', 'navigation'],
          ['工會選單', 'union_menu', 'admin'],
          ['恢復自動回答', 'resume_ai_assistant', 'navigation'],
          ['通報客服', 'feedback_unresolved', 'navigation'],
          ['綁定訂單', 'customer_binding', 'identity'],
          ['我是月嫂', 'staff_binding', 'identity'],
          ['查詢服務進度', 'service_progress', 'navigation'],
          ['綁定後台帳號', 'admin_binding', 'identity'],
          ['綁定工會帳號', 'admin_binding', 'identity'],
          ['小幫手', 'group_helper_menu', 'navigation'],
          ['發送邀請', 'order_group_invite', 'admin'],
          ['綁定群組', 'order_group_bind', 'admin'],
          ['綁定訂單', 'order_group_bind', 'admin'],
          ['切換選單', 'menu_switch_help', 'admin'],
          ['客戶選單', 'menu_switch_customer', 'navigation'],
          ['訪客選單', 'menu_switch_visitor', 'navigation'],
          ['月嫂專區', 'menu_switch_staff', 'navigation'],
        ].map(([alias, route_key, tier]) => ({
          alias, route_key, tier, source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1', revision: 3,
        })),
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (path.includes('/router/preview')) {
      const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
      return new Response(JSON.stringify({ data: {
        kind: 'protected_route',
        source_event_id: body.source_event_id,
        source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1',
        source_revision: 3,
        semantic_bucket: 'route',
        confidence: 90,
        score_band: 'gte_80',
        reason_code: 'protected_route',
        route_key: body.text === '綁定後台帳號' ? 'admin_binding' : 'customer_binding',
        options: [],
        answer_text: null,
        ticket_id: null,
        apply_ready: false,
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response('{}', { status: 404 });
  });

  it('只列可維護的聊天室指令，並指出選單入口', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));

    expect(screen.getByText('尚未預覽引導動作。')).toBeInTheDocument();
    expect(screen.queryByText(/新竹市月子補助計算與收費說明/)).not.toBeInTheDocument();
    expect(screen.queryByText(/客戶資料與服務異動申請/)).not.toBeInTheDocument();
    expect(screen.queryByText(/服務態度與爭議客訴/)).not.toBeInTheDocument();
    expect(screen.queryByText(/月嫂調休與順延機制說明/)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '綁定後台帳號' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '綁定工會帳號' })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /綁定訂單|我是月嫂|查詢服務進度|發送邀請|修改登記資料|工會選單|延期一次|恢復自動回答|通報客服/ })).not.toBeInTheDocument();
      expect(screen.getByText(/月嫂認證.*預約與登記/)).toBeInTheDocument();
      expect(screen.getByText(/修改個人資料或訂單內容.*留言/)).toBeInTheDocument();
      expect(screen.getByText(/小幫手選單.*雙方合意延期/)).toBeInTheDocument();
      expect(screen.getByText(/規則版本 3/)).toBeInTheDocument();
    });
    fireEvent.change(screen.getByRole('searchbox', { name: '搜尋引導動作' }), {
      target: { value: '恢復自動回答' },
    });
    expect(screen.getByText('沒有符合條件的引導動作。')).toBeInTheDocument();
  });

  it('把四個切換動作移出編輯清單，顯示唯讀標準指令', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));
    await screen.findByRole('tab', { name: '全部 (3)' });

    const list = within(screen.getByRole('complementary'));
    expect(list.queryByRole('button', { name: /切換選單|客戶選單|訪客選單|月嫂專區/ })).not.toBeInTheDocument();

    const instructions = screen.getByRole('region', { name: '圖文選單切換指令' });
    for (const command of ['切換選單', '切換客戶', '切換月嫂', '切換訪客', '切換工會']) {
      expect(instructions).toHaveTextContent(`「${command}」`);
    }
    expect(within(instructions).queryByRole('button')).not.toBeInTheDocument();
  });

  it('一對一綁定訂單仍可唯讀預覽，並保留原指令編輯項目', async () => {
    const fetchSpy = mockReadback();
    render(React.createElement(AiEventStudio));
    await screen.findByRole('button', { name: '綁定後台帳號' });

    fireEvent.change(screen.getByLabelText('客服測試問句'), {
      target: { value: '綁定訂單' },
    });
    fireEvent.click(screen.getByRole('button', { name: '預覽引導動作' }));

    await waitFor(() => {
      expect(screen.getByLabelText('問句處理預覽結果')).toHaveTextContent('問句分類route');
      expect(screen.getByLabelText('問句處理預覽結果')).toHaveTextContent('引導動作代碼customer_binding');
      expect(screen.getByText(/此動作沒有可在這裡維護的指令/)).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: '綁定後台帳號' })).toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: '綁定訂單' })).not.toBeInTheDocument();
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/line/ai-events/router/preview',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('常見問法只帶入輸入框，明確預覽後才呼叫正式 router', async () => {
    const fetchSpy = mockReadback();
    render(React.createElement(AiEventStudio));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '綁定後台帳號' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: '綁定後台帳號' }));

    expect(screen.getByLabelText('客服測試問句')).toHaveValue('綁定後台帳號');
    expect(fetchSpy.mock.calls.some(([url]) => String(url).includes('/router/preview'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '預覽引導動作' }));
    await waitFor(() => {
      expect(screen.getByText('已找到符合的引導動作。')).toBeInTheDocument();
      expect(screen.getByText('命中')).toBeInTheDocument();
    });
  });

  it('支援分類標籤篩選引導動作', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));
    const list = within(screen.getByRole('complementary'));

    await waitFor(() => {
      expect(screen.getByText('全部 (3)')).toBeInTheDocument();
      expect(screen.getByText('服務導覽 (1)')).toBeInTheDocument();
      expect(screen.getByText('身分綁定 (1)')).toBeInTheDocument();
      expect(screen.getByText('工會管理 (1)')).toBeInTheDocument();
    });

    // Filter by identity
    fireEvent.click(screen.getByRole('tab', { name: /身分綁定/ }));
    expect(list.getByText('綁定後台帳號')).toBeInTheDocument();
    expect(list.queryByText('綁定群組')).not.toBeInTheDocument();

    // Filter by admin
    fireEvent.click(screen.getByRole('tab', { name: /工會管理/ }));
    expect(list.getByText('綁定群組')).toBeInTheDocument();
    expect(list.queryByText('綁定後台帳號')).not.toBeInTheDocument();
    fireEvent.click(list.getByRole('button', { name: /綁定群組/ }));
    expect(screen.getByRole('heading', { name: '綁定群組' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '綁定訂單' })).toBeInTheDocument();

    // Back to all
    fireEvent.click(screen.getByRole('tab', { name: /全部/ }));
    expect(list.getByText('綁定後台帳號')).toBeInTheDocument();
    expect(list.getByText('綁定群組')).toBeInTheDocument();
  });

  it('支援編輯與儲存指令，篩選清單時保留正在編輯的動作', async () => {
    const fetchSpy = mockReadback();
    render(React.createElement(AiEventStudio));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /編輯指令/ })).toBeInTheDocument();
    });

    // Enter edit mode
    fireEvent.click(screen.getByRole('button', { name: /編輯指令/ }));
    expect(screen.getByPlaceholderText(/輸入新觸發指令/)).toBeInTheDocument();

    // Add a new alias
    fireEvent.change(screen.getByPlaceholderText(/輸入新觸發指令/), {
      target: { value: '我是工會人員' },
    });
    fireEvent.click(screen.getByRole('button', { name: /新增指令/ }));
    expect(screen.getByText('我是工會人員')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /工會管理/ }));
    expect(screen.getByRole('heading', { name: '綁定後台帳號' })).toBeInTheDocument();

    // Save changes
    fireEvent.click(screen.getByRole('button', { name: /儲存變更/ }));
    await waitFor(() => {
      expect(screen.getByText(/已成功更新/)).toBeInTheDocument();
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/line/ai-events/catalog/admin_binding/aliases',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ aliases: ['綁定後台帳號', '綁定工會帳號', '我是工會人員'] }),
      }),
    );
  });
});
