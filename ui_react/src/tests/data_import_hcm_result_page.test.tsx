/** HCM import keeps this receipt's review rows in the import card without querying the anomaly page. */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
import { hcmResubmissionClient } from '../api/case_import/hcm_resubmission_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { HcmControlledCorrectionWorkbench } from '../components/HcmControlledCorrectionWorkbench';
import { HcmWorkbookSnapshot } from '../api/case_import/hcm_workbook_client';
import { DataImportPage } from '../pages/DataImportPage';
import { HCM_WORKBOOK_PREVIEW_FIXTURE } from './fixtures/hcm_workbook_contract_fixtures';

function workbook(): File {
  return new File(['hcm-review'], 'hcm-current.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

describe('DataImport HCM receipt review', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hcmResubmissionClient, 'query').mockResolvedValue({ review_identity: 'review-2', case_no: '115000002', source_field: '行動電話', review_version: 0, resolved: false });
    vi.spyOn(hcmResubmissionClient, 'current').mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(hcmWorkbookPreviewClient, 'preview').mockResolvedValue(HCM_WORKBOOK_PREVIEW_FIXTURE);
    vi.spyOn(hcmWorkbookPreviewClient, 'apply').mockResolvedValue({
      source_content_digest: HCM_WORKBOOK_PREVIEW_FIXTURE.source_content_digest,
      source_row_count: 4,
      inserted_count: 0,
      inserted_with_warning_count: 2,
      exact_replay_count: 0,
      review_required_count: 2,
      failed_count: 0,
      skipped_existing_count: 0,
      replayed_workbook: false,
      row_outcomes_available: true,
      legacy_summary_only: false,
      row_outcomes: [{
        source_row: 2,
        case_no: '115000002',
        outcome: 'inserted_with_warning',
        problem_identity: 'review-2',
        problem_fields: ['行動電話'],
        issue_codes: ['hcm_field_invalid:行動電話'],
        referral_occurrence_identities: [],
      }, {
        source_row: 3,
        case_no: '115000003',
        outcome: 'inserted_with_warning',
        problem_identity: 'review-3',
        problem_fields: ['hcm_identity'],
        issue_codes: ['hcm_identity:hcm_identity_ambiguous'],
        referral_occurrence_identities: [],
      }, {
        source_row: 4,
        case_no: '115000004',
        outcome: 'review_required',
        problem_identity: 'review-4',
        problem_fields: ['case_import'],
        issue_codes: ['hcm_case_import:case_import_bootstrap_blocked'],
        reason_codes: ['hcm_bootstrap_deposit_due_after_service_start'],
        referral_occurrence_identities: [],
      }, {
        source_row: 5,
        case_no: '115000005',
        outcome: 'review_required',
        problem_identity: 'review-5',
        problem_fields: ['case_import'],
        issue_codes: ['hcm_case_import:case_import_bootstrap_blocked'],
        referral_occurrence_identities: [],
      }],
    });
  });

  it('removes the persistent lower HCM section and shows this run inside the HCM card', async () => {
    render(<DataImportPage />);
    expect(screen.queryByText('HCM 目前待處理異常')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新整理結果' })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('選擇 HCM Current Workbook'), { target: { files: [workbook()] } });
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]') as HTMLButtonElement);
    await screen.findByText('預覽結果');
    fireEvent.click(screen.getByLabelText('我已核對檔案名稱與預覽筆數'));
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.apply"]') as HTMLButtonElement);

    expect(await screen.findByText('案件 115000002')).toBeInTheDocument();
    expect(screen.getByText('需修改欄位：行動電話（格式或內容不符合規則）。')).toBeInTheDocument();
    expect(screen.getByText('案件已依查詢序號(案件編號)匯入；姓名或 IP 位址與既有資料相同，不會合併或阻擋新案件。')).toBeInTheDocument();
    expect(screen.getByText('這可能是同一人再次申請或不同人共用網路；請由承辦人員視需要複核。')).toBeInTheDocument();
    expect(screen.getByText('這是舊版付款規則留下的結果；目前急件會把訂金期限提前到預計服務日期，不再阻擋建案。')).toBeInTheDocument();
    expect(screen.getByText(/常見原因是薪資費率未生效或既有初始化資料不一致/)).toBeInTheDocument();
    expect(screen.queryByText(/case_import|hcm_identity/)).not.toBeInTheDocument();
    expect(screen.getByText(/既有案件跳過 0 筆（不覆寫既有案件與訂單資料）/)).toBeInTheDocument();
    expect(screen.queryByText(/前往異常審核/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /在本頁提交修正/ }));
    await waitFor(() => expect(screen.getByText('修正案件 115000002')).toBeInTheDocument());
  });

  it('cancels the selected HCM workbook and clears preview confirmation without Apply', async () => {
    render(<DataImportPage />);
    const input = screen.getByLabelText('選擇 HCM Current Workbook');
    fireEvent.change(input, { target: { files: [workbook()] } });
    fireEvent.click(screen.getByRole('button', { name: '預覽檔案' }));
    await screen.findByText('預覽結果');
    fireEvent.click(screen.getByLabelText('我已核對檔案名稱與預覽筆數'));

    fireEvent.click(screen.getByRole('button', { name: '取消選取檔案' }));

    expect(screen.getByText('未選擇任何檔案')).toBeInTheDocument();
    expect(screen.queryByText('預覽結果')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('我已核對檔案名稱與預覽筆數')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽檔案' })).toBeDisabled();
    expect(hcmWorkbookPreviewClient.apply).not.toHaveBeenCalled();
  });
});


describe('HCM correction cancel and official readback', () => {
  const selection = { caseNo: 'SYNTH-326', reviewIdentity: 'review-326', displayMessage: '縣市格式不符' };
  const preview = { review_identity: 'review-326', case_no: 'SYNTH-326', source_field: '縣市', target_fields: ['clients.city'], review_version: 0, root_fingerprint: 'a'.repeat(64), preview_fingerprint: 'b'.repeat(64) };
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hcmResubmissionClient, 'preview').mockResolvedValue(preview);
    vi.spyOn(hcmResubmissionClient, 'apply').mockResolvedValue({ event_identity: 'event-326', review_identity: 'review-326', case_no: 'SYNTH-326', target_fields: ['clients.city'], resulting_review_version: 1, replayed: false });
  });
  async function ready() {
    fireEvent.change(screen.getByLabelText('選擇 HCM 修正版'), { target: { files: [workbook()] } });
    await waitFor(() => expect(screen.getByRole('button', { name: '預覽修正' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '預覽修正' }));
    await screen.findByRole('button', { name: '確認套用修正' });
  }
  it('cancels a ready correction without Apply and reopening has no previous preview', async () => {
    const onCancel = vi.fn(); const onApplied = vi.fn();
    const view = render(<HcmControlledCorrectionWorkbench {...selection} onCancel={onCancel} onApplied={onApplied} />);
    await ready();
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(hcmResubmissionClient.apply).not.toHaveBeenCalled();
    view.unmount();
    render(<HcmControlledCorrectionWorkbench {...selection} onCancel={onCancel} onApplied={onApplied} />);
    expect(screen.queryByRole('button', { name: '確認套用修正' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽修正' })).toBeDisabled();
  });
  it('failed preview clears an old preview and can be cancelled without Apply', async () => {
    const onCancel = vi.fn();
    render(<HcmControlledCorrectionWorkbench {...selection} onCancel={onCancel} onApplied={vi.fn()} />);
    await ready();
    vi.mocked(hcmResubmissionClient.preview).mockRejectedValueOnce(new Error('invalid workbook'));
    fireEvent.click(screen.getByRole('button', { name: '預覽修正' }));
    await screen.findByRole('alert');
    expect(screen.queryByRole('button', { name: '確認套用修正' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(hcmResubmissionClient.apply).not.toHaveBeenCalled();
  });
  it('retains committed state after readback failure and retries only Query', async () => {
    const onApplied = vi.fn();
    vi.spyOn(hcmResubmissionClient, 'query').mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ ...selection, case_no: selection.caseNo, review_identity: selection.reviewIdentity, source_field: '縣市', review_version: 1, resolved: true });
    render(<HcmControlledCorrectionWorkbench {...selection} onCancel={vi.fn()} onApplied={onApplied} />);
    await ready();
    fireEvent.click(screen.getByRole('button', { name: '確認套用修正' }));
    await screen.findByText(/修正已提交，尚未確認問題解除/);
    expect(onApplied).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '重新讀取修正結果' }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledOnce());
    expect(hcmResubmissionClient.apply).toHaveBeenCalledOnce();
    expect(hcmResubmissionClient.query).toHaveBeenCalledTimes(2);
  });
  it('late file reads cannot enable submitting a superseded file', async () => {
    const old = await HcmWorkbookSnapshot.fromFile(workbook());
    let finish!: (value: HcmWorkbookSnapshot) => void;
    vi.spyOn(HcmWorkbookSnapshot, 'fromFile').mockReturnValueOnce(new Promise((resolve) => { finish = resolve; })).mockRejectedValueOnce(new Error('file failed'));
    render(<HcmControlledCorrectionWorkbench {...selection} onCancel={vi.fn()} onApplied={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('選擇 HCM 修正版'), { target: { files: [workbook()] } });
    fireEvent.change(screen.getByLabelText('選擇 HCM 修正版'), { target: { files: [workbook()] } });
    await screen.findByRole('alert');
    finish(old);
    await waitFor(() => expect(screen.getByRole('button', { name: '預覽修正' })).toBeDisabled());
  });
  it.each(['preview', 'apply'] as const)('does not claim cancellation during %s', async (phase) => {
    const onCancel = vi.fn();
    render(<HcmControlledCorrectionWorkbench {...selection} onCancel={onCancel} onApplied={vi.fn()} />);
    if (phase === 'preview') {
      vi.mocked(hcmResubmissionClient.preview).mockReturnValueOnce(new Promise(() => {}));
      fireEvent.change(screen.getByLabelText('選擇 HCM 修正版'), { target: { files: [workbook()] } });
      await waitFor(() => expect(screen.getByRole('button', { name: '預覽修正' })).toBeEnabled());
      fireEvent.click(screen.getByRole('button', { name: '預覽修正' }));
    } else {
      await ready();
      vi.mocked(hcmResubmissionClient.apply).mockReturnValueOnce(new Promise(() => {}));
      fireEvent.click(screen.getByRole('button', { name: '確認套用修正' }));
    }
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onCancel).not.toHaveBeenCalled();
  });
  it('returns to the current collection after same-case readback and preserves another issue', async () => {
    const item = { source_id: 2, review_identity: selection.reviewIdentity, case_no: selection.caseNo, fields: ['縣市'], can_correct: true };
    const other = { ...item, source_id: 1, review_identity: 'review-other', case_no: 'SYNTH-OTHER' };
    vi.spyOn(hcmResubmissionClient, 'current').mockResolvedValueOnce({ items: [item, other], next_cursor: null }).mockResolvedValue({ items: [other], next_cursor: null });
    vi.spyOn(hcmResubmissionClient, 'query').mockResolvedValue({ review_identity: selection.reviewIdentity, case_no: selection.caseNo, source_field: '縣市', review_version: 1, resolved: true });
    render(<DataImportPage />);
    fireEvent.click(screen.getByRole('button', { name: '讀取目前問題' }));
    await screen.findByText('案件 SYNTH-326');
    fireEvent.click(screen.getAllByRole('button', { name: '修正此案件' })[0]);
    await ready();
    expect(hcmResubmissionClient.preview).toHaveBeenCalledWith(expect.any(HcmWorkbookSnapshot), selection.reviewIdentity);
    fireEvent.click(screen.getByRole('button', { name: '確認套用修正' }));
    await waitFor(() => expect(screen.queryByText('案件 SYNTH-326')).not.toBeInTheDocument());
    expect(screen.getByText('案件 SYNTH-OTHER')).toBeInTheDocument();
    expect(hcmResubmissionClient.query).toHaveBeenCalledWith(selection.reviewIdentity);
    expect(hcmResubmissionClient.current).toHaveBeenCalledTimes(2);
  });

  it('a confirmed stale rejection permits a new preview instead of replaying forever', async () => {
    vi.mocked(hcmResubmissionClient.apply).mockRejectedValueOnce(new ApiHttpError(409, 'hcm_resubmission_stale_preview', 'stale'));
    render(<HcmControlledCorrectionWorkbench {...selection} onCancel={vi.fn()} onApplied={vi.fn()} />);
    await ready();
    fireEvent.click(screen.getByRole('button', { name: '確認套用修正' }));
    await screen.findByText(/正式資料或預覽版本已變更/);
    expect(screen.queryByRole('button', { name: '重播同一筆修正提交' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽修正' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '取消' })).toBeEnabled();
  });

});
