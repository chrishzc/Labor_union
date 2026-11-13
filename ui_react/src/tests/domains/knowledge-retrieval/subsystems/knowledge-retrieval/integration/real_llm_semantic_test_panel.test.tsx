import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as llmClient from '../../../../../../api/system/llm_configuration_client';
import { RealLlmSemanticTestPanel } from '../../../../../../pages/line_management/RealLlmSemanticTestPanel';


describe('真實 M2 測試題來源', () => {
  afterEach(() => vi.restoreAllMocks());

  it('只將正式 API 回傳的已發布 Knowledge QA 顯示為快捷題', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([
      { content: JSON.stringify({ schema: 'line.common_qa.v1', question: '市府到府月子服務補助多少小時？', answer: '市府補助 40 小時。' }) },
    ]), { status: 200 }));

    render(<RealLlmSemanticTestPanel />);

    expect(await screen.findByRole('button', { name: '市府到府月子服務補助多少小時？' })).toBeInTheDocument();
    expect(screen.getByLabelText('測試問題')).toHaveValue('市府到府月子服務補助多少小時？');
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
    expect(screen.getByRole('button', { name: '測試回答' })).toBeDisabled();
  });
  it('快捷題限制三題，其餘保留選題，並使用真實測試 client 與回饋 endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => new Response(JSON.stringify(
      String(url).endsWith('/router/preview') ? { data: { kind: 'menu_fallback', route_key: null } } :
      Array.from({ length: 5 }, (_, i) => ({ content: JSON.stringify({ schema: 'line.common_qa.v1', question: `正式問題 ${i + 1}`, answer: `核准答案 ${i + 1}` }) })),
    ), { status: 200 }));
    const testSpy = vi.spyOn(llmClient, 'testLlmSemantics').mockResolvedValue({ outcome: 'answered', provider: 'google', model: 'configured-model', index_version: 3, qa_id: 'QA-005', source_identity: 'line-common-qa:QA-005', answer_text: '核准答案 5', code: null });
    const openQa = vi.fn();
    render(<RealLlmSemanticTestPanel onOpenQa={openQa} />);
    expect(await screen.findByRole('button', { name: '正式問題 1' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '正式問題 4' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('選擇其他已發布題目（5 題）'));
    fireEvent.change(screen.getByLabelText('選擇已發布題目'), { target: { value: '正式問題 5' } });
    fireEvent.click(screen.getByRole('button', { name: '測試回答' }));
    await waitFor(() => expect(testSpy).toHaveBeenCalledWith('正式問題 5'));
    expect(await screen.findByText('核准答案 5')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '前往引導動作設定' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '編輯命中問答' }));
    expect(openQa).toHaveBeenCalledWith('QA-005');
    expect(fetchSpy.mock.calls.some(([url]) => String(url) === '/api/v1/line/feedback')).toBe(false);
    fireEvent.click(screen.getByText('回饋操作（會正式送出）'));
    fireEvent.click(screen.getByRole('button', { name: '有幫助' }));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith('/api/v1/line/feedback', expect.objectContaining({ method: 'POST' })));
  });

  it('命中引導動作時顯示服務入口與設定連結，並略過模型測試', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      const path = String(url);
      if (path.endsWith('/router/preview')) {
        expect(JSON.parse(String(init?.body))).toMatchObject({ text: '綁定訂單', apply_manual_fallback: false });
        return new Response(JSON.stringify({ data: { kind: 'deterministic_route', route_key: 'customer_binding' } }));
      }
      if (path.endsWith('/ai-events/catalog')) {
        return new Response(JSON.stringify({ data: { entries: [
          { route_key: 'customer_binding', alias: '綁定訂單', public_route: '/line-identity' },
        ] } }));
      }
      return new Response('[]');
    });
    const testSpy = vi.spyOn(llmClient, 'testLlmSemantics');
    render(<RealLlmSemanticTestPanel />);
    fireEvent.change(screen.getByLabelText('測試問題'), { target: { value: '綁定訂單' } });
    fireEvent.click(screen.getByRole('button', { name: '測試回答' }));

    const destination = await screen.findByRole('region', { name: '導向結果' });
    expect(destination).toHaveTextContent('綁定訂單');
    expect(destination).toHaveTextContent('/line-identity');
    expect(screen.getByRole('link', { name: '前往引導動作設定' })).toHaveAttribute('href', '#line-interface?tab=guidance');
    expect(testSpy).not.toHaveBeenCalled();
  });
});
