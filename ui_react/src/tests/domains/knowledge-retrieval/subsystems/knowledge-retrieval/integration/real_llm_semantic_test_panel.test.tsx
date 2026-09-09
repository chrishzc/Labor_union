import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RealLlmSemanticTestPanel } from '../../../../../../pages/line_management/RealLlmSemanticTestPanel';


describe('真實 M2 測試題來源', () => {
  afterEach(() => vi.restoreAllMocks());

  it('只將正式 API 回傳的已發布 Knowledge QA 顯示為快捷題', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([
      { content: JSON.stringify({ schema: 'line.common_qa.v1', question: '市府到府月子服務補助多少小時？', answer: '市府補助 40 小時。' }) },
    ]), { status: 200 }));

    render(<RealLlmSemanticTestPanel />);

    expect(await screen.findByRole('button', { name: '市府到府月子服務補助多少小時？' })).toBeInTheDocument();
    expect(screen.getByLabelText('Gemini 真實語意測試文字')).toHaveValue('市府到府月子服務補助多少小時？');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/knowledge/items?limit=100&lifecycle_status=published',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('題庫讀取失敗時不顯示硬編碼的未發布測試題', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'));

    render(<RealLlmSemanticTestPanel />);

    expect(await screen.findByText(/不提供可能失敗的快捷測試題/)).toBeInTheDocument();
    expect(screen.queryByText('月嫂服務是否有試用期？')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '執行真實 AI 智能解答' })).toBeDisabled();
  });
});
