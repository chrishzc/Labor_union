/**
 * File: ai_event_studio_local_preview.test.tsx
 * Description: 驗證 AI 事件工作室只以瀏覽器記憶體預覽規則、回饋與人工 fallback，不建立外部副作用。
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AiEventStudio } from '../pages/line_management/AiEventStudio';

describe('AI 事件工作室本機預覽', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('以目前瀏覽器草稿決定回覆，且整段操作不送出任何 request', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render(React.createElement(AiEventStudio));

    fireEvent.change(screen.getByDisplayValue(/親愛的家長您好！新竹市到宅月子補助標準/), {
      target: { value: '這是尚未發布的本機草稿回覆。' },
    });

    const input = screen.getByPlaceholderText(/輸入民眾的測試問法/);
    fireEvent.change(input, { target: { value: '補助怎麼算' } });
    fireEvent.click(screen.getByRole('button', { name: /預覽本機規則比對/ }));

    expect(screen.getAllByText('這是尚未發布的本機草稿回覆。')).toHaveLength(2);
    expect(screen.getByText(/正式儲存與發布尚未接通/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('保留 nullable 指標槽位與滿意度操作，但不增加統計或假造工單', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render(React.createElement(AiEventStudio));

    expect(screen.getAllByText('回饋統計尚未接通')).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: '👍 有幫助' }));
    expect(screen.getByText(/不會寫入數據/)).toBeInTheDocument();
    expect(screen.getAllByText('回饋統計尚未接通')).toHaveLength(4);

    fireEvent.click(screen.getByRole('button', { name: '👎 未解決' }));
    expect(screen.getByText(/正式流程應轉人工處理/)).toBeInTheDocument();
    expect(screen.getByText(/不會假造工單/)).toBeInTheDocument();
    expect(screen.queryByText(/工單編號|已建立客服工單|已成功送出/)).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('未命中、人工需求與暫停自動回覆都固定進入人工 fallback', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
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
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
