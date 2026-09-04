/**
 * File: ai_event_studio_local_preview.test.tsx
 * Description: 驗證 AI 事件工作室只顯示 server-owned catalog，不再載入 4 筆舊 INITIAL_RULES。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AiEventStudio } from '../pages/line_management/AiEventStudio';

describe('AI 事件工作室正式規則 readback', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockReadback = () => vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input);
    if (path.endsWith('/catalog')) {
      return new Response(JSON.stringify({ data: {
        revision: 3,
        entries: [
          {
            alias: '修改登記資料',
            route_key: 'profile_update',
            tier: 'service',
            source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1',
            revision: 3,
          },
          {
            alias: '我要改資料',
            route_key: 'profile_update',
            tier: 'service',
            source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1',
            revision: 3,
          },
        ],
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (path.endsWith('/feedback/aggregate')) {
      return new Response(JSON.stringify({ data: {
        resolved_count: 2,
        unresolved_count: 1,
        total_count: 3,
        resolved_rate: 2 / 3,
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
        route_key: 'profile_update',
        options: [],
        answer_text: null,
        ticket_id: null,
        apply_ready: false,
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response('{}', { status: 404 });
  });

  it('不再顯示四筆舊 INITIAL_RULES，只顯示 server-owned catalog', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));

    expect(screen.queryByText(/新竹市月子補助計算與收費說明/)).not.toBeInTheDocument();
    expect(screen.queryByText(/客戶資料與服務異動申請/)).not.toBeInTheDocument();
    expect(screen.queryByText(/服務態度與爭議客訴/)).not.toBeInTheDocument();
    expect(screen.queryByText(/月嫂調休與順延機制說明/)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/舊版 4 筆 INITIAL_RULES 本機示範資料已移除/)).toBeInTheDocument();
      expect(screen.getByText('profile_update')).toBeInTheDocument();
      expect(screen.getByText('修改登記資料')).toBeInTheDocument();
      expect(screen.getByText('我要改資料')).toBeInTheDocument();
      expect(screen.getByText(/正式 catalog revision 3/)).toBeInTheDocument();
    });
  });

  it('server router preview 不再依賴本機規則', async () => {
    const fetchSpy = mockReadback();
    render(React.createElement(AiEventStudio));

    fireEvent.change(screen.getByLabelText('Server router 測試文字'), {
      target: { value: '我要修改登記資料' },
    });
    fireEvent.click(screen.getByRole('button', { name: '讀取 server router preview' }));

    await waitFor(() => {
      expect(screen.getByText(/semantic bucket：route/)).toBeInTheDocument();
      expect(screen.getByText(/route：profile_update/)).toBeInTheDocument();
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/line/ai-events/router/preview',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('點擊別名標籤能直接觸發 router 模擬與選中規則控制中心', async () => {
    mockReadback();
    render(React.createElement(AiEventStudio));

    await waitFor(() => {
      expect(screen.getByText('問法：修改登記資料')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('問法：修改登記資料'));

    await waitFor(() => {
      expect(screen.getByText(/🎯 成功命中事件規則【profile_update】/)).toBeInTheDocument();
      expect(screen.getByText('✨ 命中')).toBeInTheDocument();
    });
  });
});
