import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CommonQaCatalogPanel } from '../pages/line_management/CommonQaCatalogPanel';


describe('常見 QA 題庫 panel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('從 server QA catalog 顯示題目、啟用狀態與固定答案', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      data: {
        source_identity: 'document/line/AI客服QA題庫.jsonl',
        total_count: 29,
        enabled_count: 17,
        items: [
          {
            id: 'QA-001',
            category: '月嫂媒合',
            tag: '更換月嫂',
            question: '如果和月嫂合作不適合，可以更換月嫂嗎？',
            aliases: ['可以換月嫂嗎？'],
            answer: '固定答案',
            enabled: true,
            source_ref: 'document/line/QA問答集.xlsx',
            notes: null,
          },
          {
            id: 'QA-003',
            category: '合約',
            tag: '試用期',
            question: '月嫂服務是否有試用期？',
            aliases: ['有試用期嗎？'],
            answer: '',
            enabled: false,
            source_ref: 'document/line/QA問答集.xlsx',
            notes: '尚無直接回答',
          },
        ],
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    render(React.createElement(CommonQaCatalogPanel));

    await waitFor(() => expect(screen.getByText(/共 29 筆 · 17 筆已啟用/)).toBeInTheDocument());
    expect(screen.getByText(/QA-001 · 如果和月嫂合作不適合/)).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/line/ai-events/qa-catalog');

    fireEvent.change(screen.getByLabelText('啟用狀態'), { target: { value: 'DISABLED' } });
    expect(screen.getByText(/QA-003 · 月嫂服務是否有試用期/)).toBeInTheDocument();
    expect(screen.queryByText(/QA-001 · 如果和月嫂合作不適合/)).not.toBeInTheDocument();
  });
});
