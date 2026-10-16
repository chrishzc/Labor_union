/** Four import families show only conserved receipt counts and preserve safe confirmation/recovery. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clientBeClassWorkbookPreviewClient } from '../api/case_import/client_beclass_workbook/client';
import { ClientBeClassWorkbookApplyError } from '../api/case_import/client_beclass_workbook/errors';
import { staffHistoricalWorkbookPreviewClient } from '../api/case_import/staff_historical_workbook/client';
import { historicalOrderWorkbookPreviewClient } from '../api/orders/historical_order_workbook/client';
import { historicalReviewRemediationClient } from '../api/orders/historical_review_remediation/client';
import { DataImportPage } from '../pages/DataImportPage';
const digest = 'a'.repeat(64);
const identity = 'b'.repeat(64);
const fingerprint = 'c'.repeat(64);
const historicalResultCounts = { not_adopted: 1, matching_pending_deposit: 1, historical_unserved: 1, historical_in_service: 1, historical_service_completed: 0 };
function workbook(contents: string): File { return new File([contents], 'import.xlsx'); }
const cases = [
  ['客戶 BeClass', '選擇客戶 BeClass Workbook', 'client-beclass', [4, 1, 1, 2]],
  ['月嫂歷史資料', '選擇月嫂歷史 Workbook', 'staff-historical', [4, 2, 0, 2]],
  ['歷史訂單', '選擇歷史訂單 Workbook', 'historic-orders', [4, 2, 0, 2]],
] as const;
function metrics(card: HTMLElement): string[] { return Array.from(card.querySelectorAll('dd > span')).map(node => node.textContent ?? ''); }
async function preview(kind: string, label: string, id: string) {
  fireEvent.click(screen.getByRole('button', { name: kind }));
  fireEvent.change(screen.getByLabelText(label), { target: { files: [workbook(id)] } });
  fireEvent.click(document.querySelector(`[data-control-id="imports.${id}.preview"]`) as HTMLButtonElement);
  const card = document.querySelector(`[data-surface-id="imports.${id}.workbench"]`) as HTMLElement;
  await within(card).findByText('預覽結果');
  return card;
}
async function apply(card: HTMLElement) {
  fireEvent.click(within(card).getByLabelText('我已核對檔案名稱與預覽筆數'));
  fireEvent.click(within(card).getByRole('button', { name: '確認匯入' }));
  await within(card).findByText('匯入結果');
}
describe('Data Import simple result flows', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(clientBeClassWorkbookPreviewClient, 'preview').mockResolvedValue({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, create_count: 1, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, preview_fingerprint: fingerprint, row_issues: [{ source_row: 7, query_no: 'CLIENT-007', fields: ['行動電話'], issue_codes: ['client_field_invalid:行動電話'] }] });
    vi.spyOn(clientBeClassWorkbookPreviewClient, 'apply').mockResolvedValue({ source_content_digest: digest, source_row_count: 4, created_count: 1, exact_replay_count: 0, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, replayed_workbook: false });
    vi.spyOn(staffHistoricalWorkbookPreviewClient, 'preview').mockResolvedValue({ source_content_digest: digest, source_row_count: 4, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: fingerprint });
    vi.spyOn(staffHistoricalWorkbookPreviewClient, 'apply').mockResolvedValue({ source_content_digest: digest, source_row_count: 4, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: fingerprint, exact_replay_count: 0, replayed_workbook: false });
    vi.spyOn(historicalOrderWorkbookPreviewClient, 'preview').mockResolvedValue({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 1, assignment_candidate_count: 1, evidence_only_pairing_count: 1, absent_order_cancellation_count: 0, status_counts: { cancelled_0: 1, deposit_paid_1: 1, discussion_2: 1, invalid_or_blank: 1 }, result_counts: historicalResultCounts, preview_fingerprint: fingerprint, row_issues: [{ source_row: 12, case_no: 'CASE-012', fields: ['訂單狀態'], issue_codes: ['historical_status_invalid'] }] });
    vi.spyOn(historicalOrderWorkbookPreviewClient, 'apply').mockResolvedValue({ source_content_digest: digest, source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 0, assignments_created: 1, replayed_rows: 0, replayed_workbook: false, absent_order_cancellation_count: 0, status_counts: { cancelled_0: 1, deposit_paid_1: 1, discussion_2: 1, invalid_or_blank: 1 }, result_counts: historicalResultCounts, review_references: [] });
  });


  it.each(cases)('%s shows only four final counters and replaces the preview', async (kind, label, id, expected) => {
    render(<DataImportPage />);
    const card = await preview(kind, label, id);
    expect(metrics(card)).toEqual(['4', '—', '—', '—']);
    expect(within(card).getByRole('button', { name: '確認匯入' })).toBeDisabled();
    expect(Array.from(card.querySelectorAll('dt')).map(node => node.textContent)).toEqual(['來源筆數', '成功匯入', '重複略過', '未匯入']);
    expect(within(card).queryByText(/CLIENT-007|CASE-012|原始資料問題|需人工檢查|既有衝突|身分阻擋/)).not.toBeInTheDocument();
    await apply(card);
    expect(metrics(card)).toEqual(expected.map(String));
    expect(within(card).queryByText('預覽結果')).not.toBeInTheDocument();
    expect(card.querySelectorAll('dl')).toHaveLength(1);
    expect(within(card).getByRole('button', { name: '匯入下一份檔案' })).toBeEnabled();
    expect(within(card).queryByRole('button', { name: '確認匯入' })).not.toBeInTheDocument();
    expect(within(card).queryByText(/需檢查|問題列|第.*列/)).not.toBeInTheDocument();
  });

  it('keeps one operation identity and navigation lock while an Apply result is unknown', async () => {
    let rejectApply!: (reason: unknown) => void;
    vi.mocked(clientBeClassWorkbookPreviewClient.apply).mockReturnValueOnce(new Promise((_, reject) => { rejectApply = reject; }));
    render(<DataImportPage />);
    const card = await preview('客戶 BeClass', '選擇客戶 BeClass Workbook', 'client-beclass');
    fireEvent.click(within(card).getByLabelText('我已核對檔案名稱與預覽筆數'));
    fireEvent.click(within(card).getByRole('button', { name: '確認匯入' }));
    await waitFor(() => expect(clientBeClassWorkbookPreviewClient.apply).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('選擇客戶 BeClass Workbook')).toBeDisabled();
    expect(screen.getByRole('button', { name: '月嫂歷史資料' })).toBeDisabled();
    expect(within(card).queryByText('匯入結果')).not.toBeInTheDocument();
    const navigation = document.createElement('button');
    navigation.className = 'sidebar-nav-item';
    const navigate = vi.fn(); navigation.addEventListener('click', navigate); document.body.appendChild(navigation);
    fireEvent.click(navigation); expect(navigate).not.toHaveBeenCalled(); navigation.remove();
    const unload = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(unload); expect(unload.defaultPrevented).toBe(true);
    rejectApply(new ClientBeClassWorkbookApplyError('timeout', '等待回應逾時，結果尚未確認。', true));
    const query = await within(card).findByRole('button', { name: '查詢這次匯入結果' });
    expect(query).toBeEnabled();
    expect(screen.getByLabelText('選擇客戶 BeClass Workbook')).toBeDisabled();
    fireEvent.click(query);
    await within(card).findByText('匯入結果');
    const calls = vi.mocked(clientBeClassWorkbookPreviewClient.apply).mock.calls;
    expect(calls[0]?.[2].idempotencyKey).toBe(calls[1]?.[2].idempotencyKey);
    expect(calls[0]?.[2].signal).toBeUndefined();
  });

  it.each(cases)('%s result lookup labels original counts and does not double the totals', async (kind, label, id, expected) => {
    const client = id === 'client-beclass' ? clientBeClassWorkbookPreviewClient : id === 'staff-historical' ? staffHistoricalWorkbookPreviewClient : historicalOrderWorkbookPreviewClient;
    const receipt = await client.apply({} as never, fingerprint, { idempotencyKey: 'fixture', correlationId: 'fixture' });
    vi.spyOn(client, 'apply').mockResolvedValue({ ...receipt, replayed_workbook: true } as never);
    render(<DataImportPage />);
    const card = await preview(kind, label, id);
    await apply(card);
    expect(within(card).getByText('已處理過，以下為原處理結果')).toBeInTheDocument();
    expect(metrics(card)).toEqual(expected.map(String));
  });

  it('does not open or query historical review remediation from an import receipt', async () => {
    const query = vi.spyOn(historicalReviewRemediationClient, 'query');
    vi.mocked(historicalOrderWorkbookPreviewClient.apply).mockResolvedValueOnce({ source_content_digest: digest, source_row_count: 1, adopted_count: 1, unmatched_case_count: 0, review_required_count: 1, current_conflict_count: 0, assignments_created: 0, replayed_rows: 0, replayed_workbook: false, absent_order_cancellation_count: 0, status_counts: { cancelled_0: 0, deposit_paid_1: 1, discussion_2: 0, invalid_or_blank: 0 }, result_counts: { not_adopted: 0, matching_pending_deposit: 0, historical_unserved: 1, historical_in_service: 0, historical_service_completed: 0 }, review_references: ['historical-order-review:one'] });
    render(<DataImportPage />);
    const card = await preview('歷史訂單', '選擇歷史訂單 Workbook', 'historic-orders'); await apply(card);
    expect(metrics(card)).toEqual(['1', '1', '0', '0']);
    expect(query).not.toHaveBeenCalled();
    expect(screen.queryByText(/處理歷史訂單待確認|歷史訂單欄位衝突更正/)).not.toBeInTheDocument();
  });

  it('explains the first action for each import family', () => {
    render(<DataImportPage />);
    for (const name of ['HCM 案件', '客戶 BeClass', '月嫂歷史資料', '歷史訂單']) {
      fireEvent.click(screen.getByRole('button', { name }));
      expect(screen.getByRole('button', { name: '預覽檔案' })).toBeDisabled();
      expect(screen.getByText('請先選擇 .xlsx 工作簿。')).toBeInTheDocument();
      expect(screen.getByText('預覽成功後才能確認匯入。')).toBeInTheDocument();
    }
  });

  it('allows a fresh preview of the same file after a definite Apply conflict', async () => {
    vi.mocked(clientBeClassWorkbookPreviewClient.apply).mockRejectedValueOnce(new ClientBeClassWorkbookApplyError('stale', '請重新預覽。', false, 409));
    render(<DataImportPage />);
    const card = await preview('客戶 BeClass', '選擇客戶 BeClass Workbook', 'client-beclass');
    fireEvent.click(within(card).getByLabelText('我已核對檔案名稱與預覽筆數'));
    fireEvent.click(within(card).getByRole('button', { name: '確認匯入' }));
    const retry = await within(card).findByRole('button', { name: '重新預覽' });
    fireEvent.click(retry);
    await waitFor(() => expect(clientBeClassWorkbookPreviewClient.preview).toHaveBeenCalledTimes(2));
    expect(within(card).getByRole('button', { name: '確認匯入' })).toBeDisabled();
    expect(within(card).queryByRole('alert')).not.toBeInTheDocument();
  });

  it('selecting another file clears previous results and confirmation', async () => {
    render(<DataImportPage />);
    const card = await preview('客戶 BeClass', '選擇客戶 BeClass Workbook', 'client-beclass'); await apply(card);
    fireEvent.change(screen.getByLabelText('選擇客戶 BeClass Workbook'), { target: { files: [workbook('another')] } });
    expect(within(card).queryByText('匯入結果')).not.toBeInTheDocument();
    expect(within(card).queryByLabelText('我已核對檔案名稱與預覽筆數')).not.toBeInTheDocument();
    fireEvent.click(within(card).getByRole('button', { name: '預覽檔案' }));
    await within(card).findByText('預覽結果');
    expect(within(card).getByRole('button', { name: '確認匯入' })).toBeDisabled();
    const calls = vi.mocked(clientBeClassWorkbookPreviewClient.preview).mock.calls;
    expect(calls[0]?.[0].sha256).not.toBe(calls[1]?.[0].sha256);
  });
});
