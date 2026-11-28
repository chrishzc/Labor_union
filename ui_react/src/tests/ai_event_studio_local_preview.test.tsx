/**
 * File: ai_event_studio_local_preview.test.tsx
 * Description: 驗證引導動作頁的聊天室指令編輯與唯讀路由預覽。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AiEventStudio } from '../pages/line_management/AiEventStudio';

const RETIRED_TEXT_COMMANDS = {
  我是月嫂: 'staff_binding',
  我要綁定月嫂: 'staff_binding',
  服務登記: 'registration',
  案件資訊: 'customer_case_information',
  服務條件與費用: 'customer_case_information',
};

const ALTERNATE_ENTRY_COMMANDS = [
  ['service_help_menu', '常見問題', '服務說明'],
  ['service_progress', '查詢服務進度', '目前狀態'],
  ['group_postponement', '雙方合意延期', '改補班日'],
  ['group_payment_ack', '已經匯款', '匯款完成'],
] as const;

describe('AI 事件工作室正式規則 readback', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockReadback = (bindingOrderRoute = 'order_group_bind') => vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
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
          ...ALTERNATE_ENTRY_COMMANDS.map(([routeKey, , staleAlias]) => [staleAlias, routeKey, 'navigation']),
          ['工會選單', 'union_menu', 'admin'],
          ['開啟異常中心', 'union_menu', 'admin'],
          ['恢復自動回答', 'resume_ai_assistant', 'navigation'],
          ['通報客服', 'feedback_unresolved', 'navigation'],
          ['綁定訂單', 'customer_binding', 'identity'],
          ['查詢訂單', 'customer_binding', 'identity'],
          ['訂單查詢', 'customer_binding', 'identity'],
          ['綁定', 'customer_binding', 'identity'],
          ...Object.entries(RETIRED_TEXT_COMMANDS).map(([alias, routeKey]) => [alias, routeKey, 'navigation']),
          ['查詢服務進度', 'service_progress', 'navigation'],
          ['綁定後台帳號', 'admin_binding', 'identity'],
          ['綁定工會帳號', 'admin_binding', 'identity'],
          ['小幫手', 'group_helper_menu', 'navigation'],
          ['發送邀請', 'order_group_invite', 'admin'],
          ['綁定群組', 'order_group_bind', 'admin'],
          ['綁定訂單', 'order_group_bind', 'admin'],
          ['切換選單', 'menu_switch_help', 'admin'],
          ['客戶選單', 'menu_switch_customer', 'navigation'],
          ['回主選單', 'menu_switch_visitor', 'navigation'],
          ['月嫂專區', 'menu_switch_staff', 'navigation'],
        ].map(([alias, route_key, tier]) => ({
          alias, route_key, tier, source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1', revision: 3,
        })),
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (path.includes('/router/preview')) {
      const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
      const routes: Record<string, string> = {
        ...RETIRED_TEXT_COMMANDS,
        綁定後台帳號: 'admin_binding',
        綁定訂單: bindingOrderRoute,
        常見問題: 'service_help_menu',
        服務說明: 'service_help_menu',
        目前狀態: 'service_progress',
        修改登記資料: 'profile_update',
        發送邀請: 'order_group_invite',
      };
      return new Response(JSON.stringify({ data: {
        kind: 'protected_route',
        source_event_id: body.source_event_id,
        source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1',
        source_revision: 3,
        semantic_bucket: 'route',
        confidence: 90,
        score_band: 'gte_80',
        reason_code: 'protected_route',
        route_key: routes[String(body.text)] ?? null,
        options: [],
        answer_text: null,
        ticket_id: null,
        apply_ready: false,
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response('{}', { status: 404 });
  });

  it('列出有效的聊天室指令並排除退役或無效指令', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));

    expect(screen.getByText('輸入要測試的文字，即可預覽會觸發的引導動作。')).toBeInTheDocument();
    expect(screen.queryByText(/新竹市月子補助計算與收費說明/)).not.toBeInTheDocument();
    expect(screen.queryByText(/客戶資料與服務異動申請/)).not.toBeInTheDocument();
    expect(screen.queryByText(/服務態度與爭議客訴/)).not.toBeInTheDocument();
    expect(screen.queryByText(/月嫂調休與順延機制說明/)).not.toBeInTheDocument();

    const list = within(screen.getByRole('complementary'));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '綁定後台帳號' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '綁定工會帳號' })).toBeInTheDocument();
      for (const command of ['常見問題', '查詢服務進度', '發送邀請', '雙方合意延期', '已經匯款', '有疑問需要解決']) {
        expect(list.getByRole('button', { name: new RegExp(command) })).toBeInTheDocument();
      }
      expect(list.queryByRole('button', { name: /修改登記資料|恢復自動回答|通報客服|開啟異常中心/ })).not.toBeInTheDocument();
      expect(screen.getByText(/圖文選單.*預約與登記.*客戶綁定.*月嫂認證/)).toBeInTheDocument();
      expect(screen.getByText(/圖文選單.*案件資訊.*服務條件與費用/)).toBeInTheDocument();
      expect(screen.getByText(/修改個人資料或訂單內容.*留言/)).toBeInTheDocument();
      expect(screen.getByText(/小幫手選單.*雙方合意延期/)).toBeInTheDocument();
      expect(screen.queryByText('連結與技術資訊')).not.toBeInTheDocument();
    });
    const search = screen.getByRole('searchbox', { name: '搜尋引導動作' });
    for (const command of ['恢復自動回答', '開啟異常中心', '查詢訂單', '訂單查詢', ...Object.keys(RETIRED_TEXT_COMMANDS)]) {
      fireEvent.change(search, { target: { value: command } });
      expect(screen.getByText('沒有符合條件的引導動作。請調整搜尋或篩選條件。')).toBeInTheDocument();
    }
    fireEvent.change(search, { target: { value: '綁定訂單' } });
    expect(list.queryByRole('button', { name: /綁定訂單.*一對一聊天室/ })).not.toBeInTheDocument();
    expect(list.getByRole('button', { name: /綁定群組.*案件群組/ })).toBeInTheDocument();

    fireEvent.change(search, { target: { value: '查詢服務進度' } });
    fireEvent.click(list.getByRole('button', { name: /查詢服務進度/ }));
    expect(screen.getByText(/尚未綁定的客戶.*圖文選單.*預約與登記/)).toBeInTheDocument();
  });

  it('引導動作排除已退役的圖文選單切換指令和舊別名', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));

    const list = within(screen.getByRole('complementary'));
    expect(await list.findByRole('button', { name: /綁定後台帳號/ })).toBeInTheDocument();
    expect(list.queryByRole('button', {
      name: /切換選單|客戶選單|訪客選單|回主選單|服務選單|月嫂專區|月嫂選單|工會選單/,
    })).not.toBeInTheDocument();
  });

  it.each(['customer_binding', 'order_group_bind'])('一對一預覽排除綁定訂單的 %s 回傳', async (route) => {
    const fetchSpy = mockReadback(route);
    render(React.createElement(AiEventStudio));
    await screen.findByRole('button', { name: '綁定後台帳號' });

    fireEvent.change(screen.getByLabelText('客服測試問句'), {
      target: { value: '綁定訂單' },
    });
    fireEvent.click(screen.getByRole('button', { name: '預覽引導動作' }));

    await waitFor(() => {
      expect(screen.getByText(/沒有可在此確認的引導動作/)).toBeInTheDocument();
      expect(screen.queryByLabelText('問句處理預覽結果')).not.toBeInTheDocument();
      expect(screen.queryByText('命中')).not.toBeInTheDocument();
      expect(screen.queryByRole('link', { name: '客戶身分綁定連結' })).not.toBeInTheDocument();
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/line/ai-events/router/preview',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('群組日期指令顯示完整用法及正確的 Reply 公版', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));
    const list = within(screen.getByRole('complementary'));
    fireEvent.click(await list.findByRole('button', { name: /雙方合意延期/ }));
    expect(screen.getByText(/雙方合意延期：2026-12-01 順延至 2026-12-10/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '延期確認卡' })).toHaveAttribute(
      'href', '#line-notifications?tab=push_queue&message=helper-postponement-card',
    );
    fireEvent.click(list.getByRole('button', { name: /已經匯款/ }));
    expect(screen.getByRole('link', { name: '已匯款受理回覆' })).toHaveAttribute(
      'href', '#line-notifications?tab=push_queue&message=payment-reminder-ack',
    );
  });

  it('群組綁定和邀請分別連到成功與格式錯誤的 Reply 編輯器', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));
    const list = within(screen.getByRole('complementary'));
    fireEvent.click(await list.findByRole('button', { name: /綁定群組.*案件群組/ }));

    const bindReplies = within(screen.getByRole('region', { name: '編輯 Reply 文案' }));
    for (const [label, id] of [
      ['單行綁定成功', 'group-bound'],
      ['三步綁定成功', 'group-guided-bound'],
      ['案件編號與網址之間缺少空白', 'group-format-case-url-spacing'],
      ['邀請網址格式錯誤', 'group-format-invalid-url'],
      ['三步綁定的邀請網址格式錯誤', 'group-format-guided-url'],
    ]) {
      expect(bindReplies.getByRole('link', { name: label })).toHaveAttribute(
        'href', `#line-notifications?tab=push_queue&message=${id}`,
      );
    }

    fireEvent.click(list.getByRole('button', { name: /發送邀請/ }));
    const inviteReplies = within(screen.getByRole('region', { name: '編輯 Reply 文案' }));
    expect(inviteReplies.getAllByRole('link')).toHaveLength(2);
    expect(inviteReplies.getByRole('link', { name: '邀請已排入發送' })).toHaveAttribute(
      'href', '#line-notifications?tab=push_queue&message=group-invitations-queued',
    );
    expect(inviteReplies.getByRole('link', { name: '發送邀請指令格式錯誤' })).toHaveAttribute(
      'href', '#line-notifications?tab=push_queue&message=group-format-invite',
    );
  });

  it('文字預覽不把退役路由或群組指令視為一對一有效指令', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));
    await screen.findByRole('heading', { name: '綁定後台帳號' });

    for (const command of ['修改登記資料', '發送邀請', '服務說明', '目前狀態', ...Object.keys(RETIRED_TEXT_COMMANDS)]) {
      fireEvent.change(screen.getByLabelText('客服測試問句'), { target: { value: command } });
      fireEvent.click(screen.getByRole('button', { name: '預覽引導動作' }));
      expect(await screen.findByText(/沒有可在此確認的引導動作/)).toBeInTheDocument();
      expect(screen.queryByLabelText('問句處理預覽結果')).not.toBeInTheDocument();
      expect(screen.queryByText('命中')).not.toBeInTheDocument();
    }
  });

  it('有其他入口的動作只列出唯一保留的指令', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));
    const list = within(screen.getByRole('complementary'));
    const search = list.getByRole('searchbox', { name: '搜尋引導動作' });
    await list.findByRole('tab', { name: '全部 (9)' });

    for (const [, command, staleAlias] of ALTERNATE_ENTRY_COMMANDS) {
      const card = list.getByRole('button', { name: new RegExp(`^${command}.*1 個指令.*有其他入口`) });
      fireEvent.click(card);
      expect(screen.getByRole('heading', { name: command, level: 2 })).toBeInTheDocument();
      expect(screen.queryByText(staleAlias)).not.toBeInTheDocument();
      fireEvent.change(search, { target: { value: staleAlias } });
      expect(list.getByText('目前顯示 0 / 共 9 組引導動作')).toBeInTheDocument();
      fireEvent.change(search, { target: { value: '' } });
    }
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
      expect(screen.getByRole('tab', { name: '全部 (9)' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: '服務導覽 (6)' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: '身分綁定 (1)' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: '工會管理 (2)' })).toBeInTheDocument();
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
    expect(screen.getByText('綁定訂單', { exact: true })).toBeInTheDocument();

    // Back to all
    fireEvent.click(screen.getByRole('tab', { name: /全部/ }));
    expect(list.getByText('綁定後台帳號')).toBeInTheDocument();
    expect(list.getByText('綁定群組')).toBeInTheDocument();
  });

  it('標示其他入口，並只篩出需手動輸入的引導動作', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));
    const list = within(screen.getByRole('complementary'));
    const faqAction = await list.findByRole('button', { name: /常見問題.*有其他入口/ });
    fireEvent.click(faqAction);
    expect(screen.getByText('訪客與客戶的圖文選單「常見問題」會代送指令。')).toBeInTheDocument();

    const manualFilter = list.getByRole('checkbox', { name: '僅手動輸入' });
    expect(manualFilter).not.toBeChecked();
    fireEvent.click(manualFilter);
    expect(manualFilter).toBeChecked();
    expect(list.getByText('目前顯示 5 / 共 9 組引導動作')).toBeInTheDocument();
    expect(list.getByRole('button', { name: /綁定後台帳號.*僅手動輸入/ })).toBeInTheDocument();
    expect(list.getByRole('button', { name: /有疑問需要解決.*僅手動輸入/ })).toBeInTheDocument();
    expect(list.queryByRole('button', { name: /常見問題|查詢服務進度|雙方合意延期|已經匯款/ })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '綁定後台帳號' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '常見問題' })).not.toBeInTheDocument();

    fireEvent.click(list.getByRole('tab', { name: /服務導覽/ }));
    const search = list.getByRole('searchbox', { name: '搜尋引導動作' });
    fireEvent.change(search, { target: { value: '已經匯款' } });
    expect(list.getByText('目前顯示 0 / 共 9 組引導動作')).toBeInTheDocument();
    expect(screen.getByText('目前沒有可查看的引導動作。')).toBeInTheDocument();
    fireEvent.change(search, { target: { value: '有疑問需要解決' } });
    expect(list.getByText('目前顯示 1 / 共 9 組引導動作')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '有疑問需要解決' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '編輯指令' })).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: '已經匯款' } });
    fireEvent.click(manualFilter);
    const paymentAction = list.getByRole('button', { name: /已經匯款.*有其他入口/ });
    fireEvent.click(paymentAction);
    expect(screen.getByText('客戶私聊的首期款逾期提醒卡有「已經匯款」按鈕。')).toBeInTheDocument();
  });

  it('預覽有其他入口的動作時保留手動指令篩選', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));
    const list = within(screen.getByRole('complementary'));
    await list.findByRole('button', { name: /綁定後台帳號.*僅手動輸入/ });
    const manualFilter = list.getByRole('checkbox', { name: '僅手動輸入' });
    fireEvent.click(manualFilter);
    const input = screen.getByLabelText('客服測試問句');
    fireEvent.change(input, { target: { value: '常見問題' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽引導動作' }));

    const result = await screen.findByLabelText('問句處理預覽結果');
    expect(result).toHaveTextContent('這個動作另有入口，未列在目前的手動指令清單。');
    expect(manualFilter).toBeChecked();
    expect(screen.getByRole('heading', { name: '綁定後台帳號' })).toBeInTheDocument();
    expect(list.queryByRole('button', { name: /常見問題/ })).not.toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('checkbox', { name: '僅手動輸入' }));
    fireEvent.click(screen.getByRole('tab', { name: /工會管理/ }));
    expect(screen.getByRole('heading', { name: '綁定後台帳號' })).toBeInTheDocument();
    expect(screen.getByText('我是工會人員')).toBeInTheDocument();

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
