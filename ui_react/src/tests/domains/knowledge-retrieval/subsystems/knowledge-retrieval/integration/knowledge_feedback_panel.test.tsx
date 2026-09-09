import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { KnowledgeFeedbackPanel } from '../../../../../../pages/line_management/KnowledgeFeedbackPanel';


describe('AI 客服回饋與知識補強', () => {
  afterEach(() => vi.restoreAllMocks());

  it('獨立顯示實際問題，並只把 unsupported 標為知識缺口', async () => {
    const questions = [
      {
        id: 2, question: '民眾問了題庫沒有的問題', request_status: 'unsupported',
        created_at_utc: '2026-09-09T05:00:00Z', completed_at_utc: '2026-09-09T05:00:02Z',
        answer_text: null, index_version: 2, source_identity: null, source_version: null, failure_code: null,
      },
      {
        id: 1, question: '市府補助多少小時？', request_status: 'answered',
        created_at_utc: '2026-09-09T04:00:00Z', completed_at_utc: '2026-09-09T04:00:02Z',
        answer_text: '市府補助 40 小時。', index_version: 2,
        source_identity: 'line-common-qa:QA-025', source_version: 3, failure_code: null,
      },
    ];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).includes('/knowledge/questions')) return new Response(JSON.stringify(questions), { status: 200 });
      return new Response(JSON.stringify({ data: { total_count: 3, resolved_count: 2, unresolved_count: 1, resolved_rate: 2 / 3 } }), { status: 200 });
    });

    render(<KnowledgeFeedbackPanel />);

    expect(await screen.findByText('民眾問了題庫沒有的問題')).toBeInTheDocument();
    expect(screen.getByText('市府補助多少小時？')).toBeInTheDocument();
    expect(screen.getByText('命中題目：QA-025 v3')).toBeInTheDocument();
    expect(screen.getByText('市府補助 40 小時。')).toBeInTheDocument();
    expect(screen.getByText('67%')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('篩選結果'), { target: { value: 'gap' } });
    await waitFor(() => expect(screen.queryByText('市府補助多少小時？')).not.toBeInTheDocument());
    expect(screen.getByText('民眾問了題庫沒有的問題')).toBeInTheDocument();
  });
});
