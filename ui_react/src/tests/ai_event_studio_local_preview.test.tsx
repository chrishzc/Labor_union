/**
 * File: ai_event_studio_local_preview.test.tsx
 * Description: 驗證 AI 事件工作室只以瀏覽器記憶體預覽草稿，並從正式 API 讀取 feedback aggregate；未取得 LINE token 不可寫入。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AiEventStudio } from '../pages/line_management/AiEventStudio';

describe('AI 事件工作室本機預覽', () => {
  const mockAggregateReadback = () => vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input).endsWith('/catalog')) {
      return new Response(JSON.stringify({ data: {
        revision: 1,
        entries: [
          {
            alias: '綁定訂單',
            route_key: 'customer_binding',
            tier: 'identity',
            source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1',
            revision: 1,
          },
        ],
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({ data: {
      catalog_revision: 1,
      window_start: '2026-09-01T00:00:00Z',
      window_end: '2026-09-01T01:00:00Z',
      resolved_count: 2,
      unresolved_count: 1,
      total_count: 3,
      resolved_rate: 2 / 3,
    } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('以目前瀏覽器草稿決定回覆，且整段操作不送出任何 request', async () => {
    const fetchSpy = mockAggregateReadback();
    render(React.createElement(AiEventStudio));

    fireEvent.change(screen.getByDisplayValue(/親愛的家長您好！新竹市到宅月子補助標準/), {
      target: { value: '這是尚未發布的本機草稿回覆。' },
    });

    const input = screen.getByPlaceholderText(/輸入民眾的測試問法/);
    fireEvent.change(input, { target: { value: '補助怎麼算' } });
    fireEvent.click(screen.getByRole('button', { name: /預覽本機規則比對/ }));

    expect(screen.getAllByText('這是尚未發布的本機草稿回覆。')).toHaveLength(2);
    expect(screen.getByText(/正式儲存與發布尚未接通/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/正式 navigation catalog：revision 1/)).toBeInTheDocument();
      expect(screen.getByText(/受保護別名：綁定訂單/)).toBeInTheDocument();
    });
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/line/ai-events/feedback/aggregate');
  });

  it('保留 nullable 指標槽位與滿意度操作，但不增加統計或假造工單', () => {
    const fetchSpy = mockAggregateReadback();
    render(React.createElement(AiEventStudio));

    expect(screen.getAllByText('回饋統計尚未接通')).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: '👍 有幫助' }));
    expect(screen.getByText(/未取得 token，未寫入/)).toBeInTheDocument();
    expect(screen.getAllByText('回饋統計尚未接通')).toHaveLength(4);

    fireEvent.click(screen.getByRole('button', { name: '👎 未解決' }));
    expect(screen.getByText(/未取得 token，未寫入/)).toBeInTheDocument();
    expect(screen.queryByText(/工單編號|已建立客服工單|已成功送出/)).not.toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/line/ai-events/feedback/aggregate');
  });

  it('未命中、人工需求與暫停自動回覆都固定進入人工 fallback', () => {
    const fetchSpy = mockAggregateReadback();
    render(React.createElement(AiEventStudio));

    const input = screen.getByPlaceholderText(/輸入民眾的測試問法/);
    const preview = screen.getByRole('button', { name: /預覽本機規則比對/ });

    fireEvent.change(input, { target: { value: '這句不會命中任何草稿' } });
    fireEvent.click(preview);
    expect(screen.getByText(/沒有符合的回覆規則；正式流程應轉入人工客服待辦/)).toBeInTheDocument();

    fireEvent.change(input, { target: { value: '我要找真人客服' } });
    fireEvent.click(preview);
    expect(screen.getByText(/正式流程必須優先轉人工，不會套用自動規則/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: '模擬自動回覆暫停' }));
    fireEvent.change(input, { target: { value: '補助怎麼算' } });
    fireEvent.click(preview);
    expect(screen.getByText(/目前模擬為自動回覆暫停/)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/line/ai-events/feedback/aggregate');
  });

  it('直接讀取 server-owned router，並以同一 source identity 建立 fallback 工單', async () => {
    const routerRequests: Array<Record<string, unknown>> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith('/catalog')) {
        return new Response(JSON.stringify({ data: { revision: 1, entries: [] } }), { status: 200 });
      }
      if (path.endsWith('/feedback/aggregate')) {
        return new Response(JSON.stringify({ data: {
          catalog_revision: 1,
          window_start: '2026-09-01T00:00:00Z',
          window_end: '2026-09-01T01:00:00Z',
          resolved_count: 0,
          unresolved_count: 0,
          total_count: 0,
          resolved_rate: null,
        } }), { status: 200 });
      }
      if (path.includes('/router/preview')) {
        const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
        routerRequests.push(body);
        const applying = body.apply_manual_fallback === true;
        return new Response(JSON.stringify({ data: {
          kind: 'unavailable',
          source_event_id: body.source_event_id,
          source_identity: 'LU96-M2-ROUTER-REPLY-SOURCE-V1',
          source_revision: 1,
          semantic_bucket: 'manual_fallback',
          confidence: 90,
          score_band: 'gte_80',
          reason_code: 'deterministic_answer_unavailable',
          route_key: null,
          options: [],
          answer_text: '請轉交客服人員確認。',
          ticket_id: applying ? 321 : null,
          apply_ready: true,
        } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response('{}', { status: 403 });
    });

    render(React.createElement(AiEventStudio));
    fireEvent.click(screen.getByRole('button', { name: '讀取 server router preview' }));
    await waitFor(() => expect(screen.getByText(/semantic bucket：manual_fallback/)).toBeInTheDocument());
    expect(screen.getByText(/confidence：90/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '建立 typed 客服 fallback 工單' }));
    await waitFor(() => expect(screen.getByText('ticket readback：321')).toBeInTheDocument());

    expect(routerRequests).toHaveLength(2);
    expect(routerRequests[0].source_event_id).toBe(routerRequests[1].source_event_id);
    expect(routerRequests[0].apply_manual_fallback).toBe(false);
    expect(routerRequests[1].apply_manual_fallback).toBe(true);
  });
});
