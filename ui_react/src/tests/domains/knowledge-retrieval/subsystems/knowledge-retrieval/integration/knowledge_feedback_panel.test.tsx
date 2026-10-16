import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { KnowledgeFeedbackPanel } from '../../../../../../pages/line_management/KnowledgeFeedbackPanel';


describe('AI 客服回饋與知識補強', () => {
  afterEach(() => vi.restoreAllMocks());

  it('只依用戶回饋判定已回答或待補強，未回饋與無答案分開顯示', async () => {
    const questions = [
      {
        id: 4, question: '民眾問了題庫沒有的問題', request_status: 'unsupported',
        created_at_utc: '2026-09-09T05:00:00Z', completed_at_utc: '2026-09-09T05:00:02Z',
        answer_text: null, index_version: 2, source_identity: null, source_version: null,
        feedback_outcome: null, failure_code: null,
      },
      {
        id: 3, question: '回答已送出但尚未回饋', request_status: 'answered',
        created_at_utc: '2026-09-09T04:00:00Z', completed_at_utc: '2026-09-09T04:00:02Z',
        answer_text: '等待用戶決定是否有幫助。', index_version: 2,
        source_identity: 'line-common-qa:QA-030', source_version: 1,
        feedback_outcome: null, failure_code: null,
      },
      {
        id: 2, question: '用戶認為有幫助', request_status: 'answered',
        created_at_utc: '2026-09-09T03:00:00Z', completed_at_utc: '2026-09-09T03:00:02Z',
        answer_text: '已取得有幫助回饋。', index_version: 2,
        source_identity: 'line-common-qa:QA-031', source_version: 1,
        feedback_outcome: 'resolved', failure_code: null,
      },
      {
        id: 1, question: '用戶認為沒有解決', request_status: 'answered',
        created_at_utc: '2026-09-09T02:00:00Z', completed_at_utc: '2026-09-09T02:00:02Z',
        answer_text: '這次回答需要補強。', index_version: 2,
        source_identity: 'line-common-qa:QA-032', source_version: 1,
        feedback_outcome: 'unresolved', failure_code: null,
      },
    ];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).includes('/knowledge/questions')) return new Response(JSON.stringify(questions), { status: 200 });
      return new Response(JSON.stringify({ data: { total_count: 3, resolved_count: 2, unresolved_count: 1, resolved_rate: 2 / 3 } }), { status: 200 });
    });

    const createQa = vi.fn();
    const openQa = vi.fn();
    render(<KnowledgeFeedbackPanel onCreateQa={createQa} onOpenQa={openQa} />);

    expect(await screen.findByText('民眾問了題庫沒有的問題')).toBeInTheDocument();
    expect(screen.queryByText('回答已送出但尚未回饋')).not.toBeInTheDocument();
    expect(screen.queryByText('用戶認為有幫助')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('篩選結果'), { target: { value: 'all' } });
    expect(screen.getByText('回答已送出但尚未回饋')).toBeInTheDocument();
    expect(screen.getByText('用戶認為有幫助')).toBeInTheDocument();
    expect(screen.getByText('用戶認為沒有解決')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看提問：回答已送出但尚未回饋' }));
    expect(screen.getByText('命中題目：QA-030 v1')).toBeInTheDocument();
    expect(screen.getByText(/尚未收到用戶回饋，無法判定是否解決問題/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '關閉提問明細' }));
    expect(screen.getAllByText('等待用戶回饋').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('用戶確認有幫助').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('用戶回饋未解決').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('未找到答案').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('67%').length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText('篩選結果'), { target: { value: 'gap' } });
    await waitFor(() => expect(screen.queryByText('用戶認為有幫助')).not.toBeInTheDocument());
    expect(screen.getByText('用戶認為沒有解決')).toBeInTheDocument();
    expect(screen.queryByText('民眾問了題庫沒有的問題')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看提問：用戶認為沒有解決' }));
    fireEvent.click(screen.getByRole('button', { name: '檢查命中問答' }));
    expect(openQa).toHaveBeenCalledWith('QA-032');
    fireEvent.click(screen.getByRole('button', { name: '關閉提問明細' }));
    fireEvent.change(screen.getByLabelText('篩選結果'), { target: { value: 'unsupported' } });
    fireEvent.click(screen.getByRole('button', { name: '查看提問：民眾問了題庫沒有的問題' }));
    fireEvent.click(screen.getByRole('button', { name: '新增問答草稿' }));
    expect(createQa).toHaveBeenCalledWith('民眾問了題庫沒有的問題');
  });
});
