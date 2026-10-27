/**
 * File: line_identity_review_workbench.test.tsx
 * Description: 驗證 LINE 身分人工審核一次提交時的 list／detail／內部 Preview／Apply／receipt／readback 流程。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  LineIdentityReviewWorkbench,
  type LineIdentityReviewClient,
} from '../components/LineIdentityReviewWorkbench';
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';

const PENDING_REVIEW = {
  request_id: 71,
  review_type: 'staff_verification' as const,
  status: 'pending' as const,
  version: 3,
  subject_type: 'staff' as const,
  subject_reference: 'STAFF-REVIEW-071',
  assigned_admin_id: null,
  due_at: null,
  line_user_id: 'Ureview-should-be-masked-7890',
  display_name: '待審月嫂甲',
  decision_reason: null,
  reviewed_by_actor_id: null,
  reviewed_at: null,
  created_at: '2026-08-24T10:00:00+08:00',
};

const APPROVED_REVIEW = {
  ...PENDING_REVIEW,
  status: 'approved' as const,
  version: 4,
  decision_reason: '管理員已人工核對資料',
  reviewed_by_actor_id: 'admin:1',
  reviewed_at: '2026-08-24T10:30:00+08:00',
  outcome: 'created' as const,
  receipt_identity: 'line-review:71:approved',
};

const REVIEW_PREVIEW = {
  request_id: 71,
  decision: 'approve' as const,
  before_status: 'pending' as const,
  after_status: 'approved' as const,
  expected_version: 3,
  resulting_version: 4,
  subject_type: 'staff' as const,
  subject_reference: 'STAFF-REVIEW-071',
  line_user_id: 'Ureview-should-be-masked-7890',
  preview_fingerprint: 'review-preview-fixture-071',
};

function reviewClient() {
  return {
    listReviews: vi.fn().mockResolvedValue({ items: [PENDING_REVIEW], page: 1, page_size: 25, total: 1 }),
    getReviewSummary: vi.fn().mockResolvedValue({
      pending_total: 4,
      staff_pending: 2,
      rebind_pending: 1,
      processed_today: 3,
      stale_pending: 1,
      stale_hours: 24,
    }),
    getReview: vi.fn()
      .mockResolvedValueOnce(PENDING_REVIEW)
      .mockResolvedValue(APPROVED_REVIEW),
    previewReviewDecision: vi.fn<LineIdentityReviewClient['previewReviewDecision']>().mockResolvedValue(REVIEW_PREVIEW),
    applyReviewDecision: vi.fn<LineIdentityReviewClient['applyReviewDecision']>().mockResolvedValue(APPROVED_REVIEW),
  } satisfies LineIdentityReviewClient;
}

describe('LINE 身分人工審核工作台', () => {
  it('一次提交依序完成內部 Preview、Apply、receipt 與 GET readback', async () => {
    const client = reviewClient();
    render(<LineIdentityReviewWorkbench client={client} />);

    await screen.findByText('未設定 待審月嫂甲');
    expect(screen.getByText('只有具審核權限的真人管理員可核准或拒絕；等待時間不會自動做出決定。')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(PENDING_REVIEW.line_user_id);
    fireEvent.click(screen.getByRole('button', { name: '查看審核 #71' }));
    await screen.findByRole('heading', { name: '審核 #71｜月嫂身分驗證' });

    fireEvent.change(screen.getByRole('textbox', { name: '審核原因（選填）' }), {
      target: { value: '管理員已人工核對資料' },
    });
    expect(client.applyReviewDecision).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '提交審核決定' }));
    await screen.findByText('審核決定已受理');
    expect(screen.getByRole('button', { name: '提交審核決定' })).toBeDisabled();
    expect(screen.queryByRole('checkbox', { name: '我已確認審核對象與決定' })).not.toBeInTheDocument();
    expect(client.previewReviewDecision).toHaveBeenCalledExactlyOnceWith(
      71, 'approve', { expected_version: 3, reason: '管理員已人工核對資料' }, expect.any(Object),
    );
    expect(client.previewReviewDecision.mock.invocationCallOrder[0]).toBeLessThan(client.applyReviewDecision.mock.invocationCallOrder[0]);
    expect(screen.getByText('已建立')).toBeInTheDocument();

    expect(client.applyReviewDecision).toHaveBeenCalledWith(
      71,
      'approve',
      expect.objectContaining({
        expected_version: 3,
        reason: '管理員已人工核對資料',
        preview_fingerprint: 'review-preview-fixture-071',
        idempotency_key: expect.stringMatching(/^line-review-decision-/),
      }),
      expect.any(Object)
    );
    expect(screen.getByText(/LINE provider 訊息已送達/)).toHaveTextContent('不代表');

    fireEvent.click(screen.getByRole('button', { name: '重新查詢審核結果' }));
    await waitFor(() => expect(client.getReview).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getAllByText('已核准').length).toBeGreaterThan(0));
    expect(screen.getByText('此審核已是 已核准，不可再提交決定；可保留明細作為最新審核結果。')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('readback');
  });

  it('修改 reason 後廢止既有 Preview，不可使用 stale fingerprint Apply', async () => {
    const client = reviewClient();
    const pending = (() => { let resolve!: (value: typeof REVIEW_PREVIEW) => void; const promise = new Promise<typeof REVIEW_PREVIEW>(done => { resolve = done; }); return { promise, resolve }; })();
    client.previewReviewDecision.mockReturnValueOnce(pending.promise);
    render(<LineIdentityReviewWorkbench client={client} />);
    await screen.findByText('未設定 待審月嫂甲');
    fireEvent.click(screen.getByRole('button', { name: '查看審核 #71' }));
    await screen.findByRole('heading', { name: /審核 #71/ });
    const reason = screen.getByRole('textbox', { name: '審核原因（選填）' });
    fireEvent.change(reason, { target: { value: '第一次人工確認' } });
    fireEvent.click(screen.getByRole('button', { name: '提交審核決定' }));
    await waitFor(() => expect(client.previewReviewDecision).toHaveBeenCalledOnce());
    const signal = client.previewReviewDecision.mock.calls[0][3]?.signal;

    fireEvent.change(reason, { target: { value: '第二次人工確認' } });
    expect(signal?.aborted).toBe(true);
    await act(async () => { pending.resolve(REVIEW_PREVIEW); });
    expect(screen.queryByRole('heading', { name: '預覽：核准' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '提交審核決定' })).toBeEnabled();
    expect(client.applyReviewDecision).not.toHaveBeenCalled();
  });

  it('使用 server numbered metadata 換頁，並在篩選變更時回到第一頁', async () => {
    const listReviews = vi.fn((query?: Parameters<LineIdentityReviewClient['listReviews']>[0]) => Promise.resolve({
      items: [PENDING_REVIEW],
      page: query?.page ?? 1,
      page_size: 25,
      total: 26,
    }));
    const client = { ...reviewClient(), listReviews };
    render(<LineIdentityReviewWorkbench client={client} />);

    await screen.findByText('顯示 1-25 / 26 件');
    expect(screen.getByRole('button', { name: '上一頁' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '下一頁' }));
    await waitFor(() => expect(listReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2, page_size: 25 }),
      expect.any(Object),
    ));
    await screen.findByText('顯示 26-26 / 26 件');
    expect(screen.getByRole('button', { name: '下一頁' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('審核類型'), {
      target: { value: 'staff_verification' },
    });
    await waitFor(() => expect(listReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, review_type: 'staff_verification' }),
      expect.any(Object),
    ));
    await screen.findByText('顯示 1-25 / 26 件');
  });

  it('不將 typed error code 或後端訊息穿透到一般審核畫面', async () => {
    const client = reviewClient();
    client.previewReviewDecision.mockRejectedValueOnce(new LineIdentityClientError(
      'BACKEND_REJECTED',
      'raw provider detail must stay closed',
    ));
    render(<LineIdentityReviewWorkbench client={client} />);

    await screen.findByText('未設定 待審月嫂甲');
    fireEvent.click(screen.getByRole('button', { name: '查看審核 #71' }));
    await screen.findByRole('heading', { name: /審核 #71/ });
    fireEvent.change(screen.getByRole('textbox', { name: '審核原因（選填）' }), {
      target: { value: '管理員已人工核對資料' },
    });
    fireEvent.click(screen.getByRole('button', { name: '提交審核決定' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('LINE 身分審核服務目前無法安全完成這項操作，請稍後再試。');
    expect(document.body.textContent).not.toContain('BACKEND_REJECTED');
    expect(document.body.textContent).not.toContain('raw provider detail');
  });
});
