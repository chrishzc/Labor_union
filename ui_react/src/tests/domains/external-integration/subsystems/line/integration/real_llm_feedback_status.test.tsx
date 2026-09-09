import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../../../../api/system/llm_configuration_client', () => ({
  testLlmSemantics: vi.fn(),
}));

import { testLlmSemantics } from '../../../../../../api/system/llm_configuration_client';
import { RealLlmSemanticTestPanel } from '../../../../../../pages/line_management/RealLlmSemanticTestPanel';

describe('真實 AI 測試回饋狀態', () => {
  it('後端未接受回饋時不顯示假成功，並提供可重試訊息', async () => {
    vi.mocked(testLlmSemantics).mockResolvedValue({
      outcome: 'answered',
      code: null,
      provider: 'gemini',
      model: 'gemini-test',
      index_version: 1,
      qa_id: 'QA-001',
      source_identity: 'knowledge/qa',
      answer_text: '核准答案',
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).includes('/knowledge/items?')) {
        return new Response(JSON.stringify([{
          content: JSON.stringify({ schema: 'line.common_qa.v1', question: '已發布問題', answer: '核准答案' }),
        }]), { status: 200 });
      }
      throw new Error('offline');
    });

    render(<RealLlmSemanticTestPanel />);
    await screen.findByDisplayValue('已發布問題');
    fireEvent.click(screen.getByRole('button', { name: '執行真實 AI 智能解答' }));
    await screen.findByText('核准答案');
    expect(screen.queryByText(/provider：|Knowledge index：|來源：/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '未解決（通報專人客服）' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('回饋尚未送出'));
    expect(screen.queryByText(/已記錄為未解決/)).not.toBeInTheDocument();
  });
});
