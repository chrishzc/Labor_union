/**
 * File: historical_order_review_remediation.test.tsx
 * Description: 驗證歷史訂單 review 更正的 strict binding、Preview invalidation 與 Confirm／Apply 流程。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  HISTORICAL_REVIEW_REMEDIATION_QUERY_PATH,
  queryHistoricalReviewRemediation,
} from '../api/orders/historical_review_remediation/client';
import { HistoricalOrderReviewRemediationWorkbench } from '../components/HistoricalOrderReviewRemediationWorkbench';
import { sessionClient } from '../api/auth/session_client';
import type { HistoricalReviewRemediationClient } from '../api/orders/historical_review_remediation/client';
import type { HistoricalReviewContext, HistoricalReviewPreview } from '../api/orders/historical_review_remediation/schemas';

const issue = {
  issue_code: 'historical_status_invalid',
  field_path: 'status',
  field_label: '訂單狀態',
  masked_source_value: '9',
  masked_current_value: '1',
  rule: 'status must be one of 0, 1, or 2',
  allowed_values: ['0', '1', '2'],
  process_blocker: '不得進入後續訂單流程',
};

const context: HistoricalReviewContext = {
  review_identity: 'review:historical:1',
  masked_case_identity: 'CASE-***1',
  issues: [issue],
  review_version: 2,
  remediation_version: 0,
  workbook_contract: { contract_key: 'orders.historical-review-correction', contract_version: 1, required_columns: ['case_no', 'status'], single_row_only: true, file_extension: 'xlsx' },
  reason_required: true,
  evidence_required: true,
  completion_condition: 'prior review disposition recorded',
  prior_alert_active: true,
};

const preview: HistoricalReviewPreview = {
  prior_review_identity: context.review_identity,
  source_content_digest: 'a'.repeat(64),
  outcome: 'corrected_source_adopted',
  remaining_issues: [],
  preview_fingerprint: 'b'.repeat(64),
  review_version: context.review_version,
  remediation_version: context.remediation_version,
};

function fakeClient(overrides: Partial<HistoricalReviewRemediationClient> = {}): HistoricalReviewRemediationClient {
  return {
    query: vi.fn().mockResolvedValue(context),
    preview: vi.fn().mockResolvedValue(preview),
    apply: vi.fn().mockResolvedValue({
      prior_review_identity: context.review_identity,
      disposition: 'corrected_source_adopted',
      receipt: { remediation_receipt_identity: 'receipt:1', disposition: 'corrected_source_adopted', source_content_digest: preview.source_content_digest, preview_fingerprint: preview.preview_fingerprint, resulting_remediation_version: 1 },
      prior_alert_active: false,
      successor: null,
      replayed: false,
      readback: { prior_review_identity: context.review_identity, prior_alert_active: false, remaining_issues: [], review_version: 2, remediation_version: 1 },
    }),
    ...overrides,
  };
}

describe('HistoricalOrderReviewRemediationWorkbench', () => {
  beforeEach(() => {
    sessionClient.setSession('historical-review-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
  });
  afterEach(() => sessionClient.clearSession());

  it('queries by exact review identity and rejects a response for another identity', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data: { ...context, review_identity: 'review:other' }, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;
    await expect(queryHistoricalReviewRemediation(context.review_identity)).rejects.toMatchObject({ code: 'historical_review_identity_mismatch' });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(HISTORICAL_REVIEW_REMEDIATION_QUERY_PATH(context.review_identity));
  });

  it('requires file, reason, evidence, Preview and explicit Confirm before Apply', async () => {
    const owner = fakeClient();
    render(<HistoricalOrderReviewRemediationWorkbench reviewIdentity={context.review_identity} client={owner} />);
    await waitFor(() => expect(screen.getByText(/CASE-\*\*\*1/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Preview 更正結果' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/處理原因/), { target: { value: '電話確認資料後更正' } });
    fireEvent.change(screen.getByLabelText(/佐證/), { target: { value: 'phone-log:1' } });
    const file = new File(['xlsx'], 'correction.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    fireEvent.change(screen.getByLabelText(/單列更正/), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Preview 更正結果' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Preview 更正結果' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Preview 結果' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '確認套用更正' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('button', { name: '確認套用更正' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '確認套用更正' }));
    await waitFor(() => expect(screen.getByText('原警示已解除')).toBeInTheDocument());
    expect(owner.apply).toHaveBeenCalledOnce();
  });

  it('keeps technical identities and raw outcomes out of the default business layer', async () => {
    const owner = fakeClient();
    render(<HistoricalOrderReviewRemediationWorkbench reviewIdentity={context.review_identity} client={owner} />);
    await waitFor(() => expect(screen.getByText(/CASE-\*\*\*1/)).toBeInTheDocument());

    expect(screen.getByText('更正檔案要求')).toBeInTheDocument();
    expect(screen.getByText(/請上傳單列 \.xlsx/)).toBeInTheDocument();
    expect(screen.queryByText(/review 版本/)).not.toBeInTheDocument();
    expect(screen.getByText(/historical_status_invalid/)).not.toBeVisible();

    fireEvent.change(screen.getByLabelText(/處理原因/), { target: { value: '電話確認' } });
    fireEvent.change(screen.getByLabelText(/佐證/), { target: { value: 'record:visible-layer' } });
    fireEvent.change(screen.getByLabelText(/單列更正/), { target: { files: [new File(['xlsx'], 'correction.xlsx')] } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Preview 更正結果' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Preview 更正結果' }));

    await waitFor(() => expect(screen.getByText('預計處理：更正資料可採用')).toBeInTheDocument());
    expect(screen.getByText(new RegExp(preview.preview_fingerprint))).not.toBeVisible();
    expect(screen.queryByText('corrected_source_adopted')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用更正' }));
    await waitFor(() => expect(screen.getByText('處理結果：更正資料可採用')).toBeInTheDocument());
    expect(screen.getByText(/receipt:1/)).not.toBeVisible();
    expect(screen.queryByText('corrected_source_adopted')).not.toBeInTheDocument();
  });

  it('maps unexpected failures to a closed business error', async () => {
    const owner = fakeClient({ query: vi.fn().mockRejectedValue(new Error('raw database host detail')) });
    render(<HistoricalOrderReviewRemediationWorkbench reviewIdentity={context.review_identity} client={owner} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('歷史訂單欄位衝突目前無法完成，請稍後再試。');
    expect(screen.queryByText(/raw database host detail/)).not.toBeInTheDocument();
  });

  it('invalidates Preview when reason changes', async () => {
    const owner = fakeClient();
    render(<HistoricalOrderReviewRemediationWorkbench reviewIdentity={context.review_identity} client={owner} />);
    await waitFor(() => expect(screen.getByText(/CASE-\*\*\*1/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/處理原因/), { target: { value: '電話確認' } });
    fireEvent.change(screen.getByLabelText(/佐證/), { target: { value: 'record:1' } });
    fireEvent.change(screen.getByLabelText(/單列更正/), { target: { files: [new File(['xlsx'], 'correction.xlsx')] } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Preview 更正結果' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Preview 更正結果' }));
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/處理原因/), { target: { value: '另一筆電話確認' } });
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(owner.apply).not.toHaveBeenCalled();
  });

  it('keeps explicit remaining issues visible while owner alert is still active', async () => {
    const owner = fakeClient({
      apply: vi.fn().mockResolvedValue({
        prior_review_identity: context.review_identity,
        disposition: 'corrected_source_adopted',
        receipt: { remediation_receipt_identity: 'receipt:active', disposition: 'corrected_source_adopted', source_content_digest: preview.source_content_digest, preview_fingerprint: preview.preview_fingerprint, resulting_remediation_version: 1 },
        prior_alert_active: true,
        successor: null,
        replayed: false,
        readback: { prior_review_identity: context.review_identity, prior_alert_active: true, remaining_issues: [issue], review_version: 2, remediation_version: 1 },
      }),
      query: vi.fn()
        .mockResolvedValueOnce(context)
        .mockResolvedValue({ ...context, remediation_version: 1, prior_alert_active: true }),
    });
    render(<HistoricalOrderReviewRemediationWorkbench reviewIdentity={context.review_identity} client={owner} />);
    await waitFor(() => expect(screen.getByText(/CASE-\*\*\*1/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/處理原因/), { target: { value: '電話確認' } });
    fireEvent.change(screen.getByLabelText(/佐證/), { target: { value: 'record:active' } });
    fireEvent.change(screen.getByLabelText(/單列更正/), { target: { files: [new File(['xlsx'], 'correction.xlsx')] } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Preview 更正結果' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Preview 更正結果' }));
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用更正' }));

    expect(await screen.findByText('原 review 尚未解除的欄位衝突')).toBeInTheDocument();
    expect(screen.getByText('更正已提交，等待異常重新檢核')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新檢核異常狀態' })).toBeInTheDocument();
  });
});
