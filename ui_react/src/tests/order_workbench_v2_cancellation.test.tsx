import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderCancellationPanel } from '../components/OrderCancellationPanel';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { OrderCancellationQuery, OrderCancellationReceipt, ServiceDay } from '../api/orders/order_cancellation_client';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';

const mocks = vi.hoisted(() => ({ query: vi.fn(), preview: vi.fn(), apply: vi.fn(), receipt: vi.fn() }));
vi.mock('../api/orders/order_cancellation_client', () => ({ orderCancellationClient: mocks }));
const CASE = 'CASE-BETA-CANCEL';
const fingerprint = 'c'.repeat(64);
let facts: OrderCancellationQuery;
function query(caseNo = CASE): OrderCancellationQuery {
  return { case_no: caseNo, lifecycle_status: '訂單成立', actual_start_date: null, contracted_service_days: 20,
    service_hours_per_day: 8, service_started: false, historical_mid_service_confirmation_available: false,
    service_data_locked: false, order_version: 2, scheduling_version: 3, scheduling_generation: 1,
    client_finance_version: 4, payroll_version: 5, confirmed_service_days: [], caregiver_options: [{ staff_id: 8, display_name: '測試月嫂' }] };
}
// Component-boundary doubles expose the owner fields consumed by this panel;
// decoding remains covered by the existing cancellation client contract tests.
function preview(days: ServiceDay[] = [], caseNo = CASE) {
  return { cancellation_date: '2026-09-05', actual_start_date: facts.actual_start_date, actual_end_date: null,
    confirmed_service_days: days, official_service_day_count: days.length, official_service_hours: days.length * 8,
    order_version: 2, scheduling_version: 3, scheduling_generation: 1, client_finance_version: 4, payroll_version: 5,
    scheduling: { case_no: caseNo }, client_finance_impact: { case_no: caseNo, actions: [{ payment_stage: 'deposit', direction: 'refund_due', direction_amount_ntd: 1000 }], blockers: [] },
    payroll_impact: { case_no: caseNo, actions: [], blockers: [] },
    lifecycle_impact: { case_no: caseNo, before_status: facts.lifecycle_status, after_status: '訂單取消' }, preview_fingerprint: fingerprint };
}
function receipt(caseNo = CASE): OrderCancellationReceipt {
  return { case_no: caseNo, lifecycle_status: '訂單取消', order_version: 3, scheduling_version: 4, scheduling_generation: 2,
    client_finance_version: 5, payroll_version: 6, actual_end_date: null, official_service_day_count: 0,
    official_service_hours: 0, cancelled_assignment_ids: [], created_assignment_keys: [], preview_fingerprint: fingerprint };
}
function commitFacts() { facts = { ...facts, lifecycle_status: '訂單取消', order_version: 3, scheduling_version: 4, client_finance_version: 5 }; }
async function open() {
  await screen.findByText(`目前狀態：${facts.lifecycle_status}`);
}
async function confirmPreview() {
  fireEvent.change(screen.getByLabelText('取消原因'), { target: { value: '客戶電話確認取消。' } });
}
async function requestPreview() {
  const button = screen.getByRole('button', { name: '預覽取消帳務' });
  await waitFor(() => expect(button).toBeEnabled());
  await act(async () => { fireEvent.click(button); });
}
async function apply() {
  const historical = screen.queryByRole('button', { name: '儲存實際服務事實' });
  if (!historical) {
    await requestPreview();
    expect(mocks.apply).not.toHaveBeenCalled();
  }
  const button = historical ?? screen.getByRole('button', { name: '確認取消' });
  await waitFor(() => expect(button).toBeEnabled());
  await act(async () => { fireEvent.click(button); });
}

describe('Beta 取消與歷史取消服務補登', () => {
  beforeEach(() => {
    orderMutationFlowStore.clearAll();
    Object.values(mocks).forEach((mock) => mock.mockReset());
    facts = query();
    mocks.query.mockImplementation(async () => structuredClone(facts));
    mocks.preview.mockImplementation(async (_case, days) => preview(days));
    mocks.apply.mockImplementation(async () => { commitFacts(); return receipt(); });
  });

  it('取消完成後直接提供帶入新非市民案入口，不自動建案', async () => {
    render(<OrderCancellationPanel caseNo={CASE} />);
    await open(); await apply();
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(screen.getByRole('link', { name: '以此案資料建立非市民新案' })).toHaveAttribute('href', `#clients?tab=applications&source_case=${encodeURIComponent(CASE)}`);
    expect(mocks.apply).toHaveBeenCalledTimes(1);
  });

  it('重新開啟已取消案件仍提供帶入入口，不要求再次取消', async () => {
    facts = { ...facts, lifecycle_status: '訂單取消' };
    render(<OrderCancellationPanel caseNo={CASE} />);
    await open();
    expect(screen.getByRole('link', { name: '以此案資料建立非市民新案' })).toHaveAttribute('href', `#clients?tab=applications&source_case=${encodeURIComponent(CASE)}`);
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('允許歷史取消服務補登時仍直接提供帶入入口', async () => {
    facts = { ...facts, lifecycle_status: '訂單取消', historical_mid_service_confirmation_available: true };
    render(<OrderCancellationPanel caseNo={CASE} />);
    await open();
    expect(screen.getByRole('link', { name: '以此案資料建立非市民新案' })).toHaveAttribute('href', `#clients?tab=applications&source_case=${encodeURIComponent(CASE)}`);
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('未服務案件以零日預覽，明確確認後才送出並回讀', async () => {
    const onObserved = vi.fn(); const onBusyChange = vi.fn();
    render(<OrderCancellationPanel caseNo={CASE} onObserved={onObserved} onBusyChange={onBusyChange} />);
    await open();
    expect(screen.queryByRole('button', { name: '新增實際服務日' })).not.toBeInTheDocument();
    await confirmPreview();
    expect(screen.getByRole('checkbox', { name: '收取違約金' })).not.toBeChecked();
    expect(screen.queryByRole('button', { name: '讀取取消狀態' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '檢查取消影響' })).not.toBeInTheDocument();
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(mocks.preview).not.toHaveBeenCalled();
    await apply();
    expect(mocks.preview).toHaveBeenCalledWith(CASE, [], expect.any(AbortSignal));
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.apply).toHaveBeenCalledWith(CASE, {
      confirmed_service_days: [], expected_order_version: 2, expected_scheduling_version: 3,
      expected_client_finance_version: 4, expected_payroll_version: 5, preview_fingerprint: fingerprint, reason: '客戶電話確認取消。',
    }, expect.objectContaining({ idempotencyKey: expect.any(String), actor: '' }));
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(onBusyChange).toHaveBeenCalledWith(true);
    expect(onBusyChange).toHaveBeenLastCalledWith(false);
  });

  it('未初始化案件以空版本一次取消並完成正式回讀', async () => {
    facts = { ...facts, actual_start_date: '2026-09-01', scheduling_version: null, scheduling_generation: null, client_finance_version: null, payroll_version: null };
    mocks.preview.mockImplementation(async () => ({ ...preview([]), scheduling_version: null, scheduling_generation: null, client_finance_version: null, payroll_version: null, scheduling: null, client_finance_impact: null, payroll_impact: null }));
    mocks.apply.mockImplementation(async () => {
      facts = { ...facts, lifecycle_status: '訂單取消', order_version: 3 };
      return { ...receipt(), scheduling_version: null, scheduling_generation: null, client_finance_version: null, payroll_version: null };
    });
    render(<OrderCancellationPanel caseNo={CASE} />);
    await open(); await confirmPreview();
    await apply();
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.apply).toHaveBeenCalledTimes(1);
    expect(mocks.apply).toHaveBeenCalledWith(CASE, expect.objectContaining({ expected_scheduling_version: null, expected_client_finance_version: null, expected_payroll_version: null }), expect.anything());
  });

  it('保留服務日及月嫂修正送交 owner 驗證', async () => {
    facts = { ...facts, service_started: true, actual_start_date: '2026-09-01',
      confirmed_service_days: [{ service_date: '2026-09-01', staff_id: 8, reason: null }] };
    render(<OrderCancellationPanel caseNo={CASE} />); await open();
    fireEvent.change(screen.getByLabelText('取消實際服務日 1'), { target: { value: '2026-09-02' } });
    expect(mocks.preview).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('取消實際服務日原因 1'), { target: { value: '核對實際出勤' } });
    await confirmPreview();
    await apply();
    expect(mocks.preview).toHaveBeenCalledWith(CASE, [{ service_date: '2026-09-02', staff_id: 8, reason: '核對實際出勤' }], expect.any(AbortSignal));
  });

  it('取消當日確認未服務可移除全部服務日並以零日取消', async () => {
    facts = { ...facts, service_started: true, actual_start_date: '2026-09-05',
      confirmed_service_days: [{ service_date: '2026-09-05', staff_id: 8, reason: null }] };
    render(<OrderCancellationPanel caseNo={CASE} />); await open();
    expect(screen.getByText(/已自動排除取消日之後的排班/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '移除取消實際服務日 1' }));
    await apply();
    expect(mocks.preview).toHaveBeenCalledWith(CASE, [], expect.any(AbortSignal));
    expect(mocks.apply).toHaveBeenCalledWith(CASE, expect.objectContaining({ confirmed_service_days: [], reason: '' }), expect.anything());
  });

  it('歷史取消明確 capability 允許實際日補登，但普通已取消案件不可再取消', async () => {
    facts = { ...facts, lifecycle_status: '訂單取消', historical_mid_service_confirmation_available: true,
      confirmed_service_days: [{ service_date: '2026-09-01', staff_id: 8, reason: '歷史出勤資料' }] };
    const view = render(<OrderCancellationPanel caseNo={CASE} />); await open();
    await screen.findByText('後端允許補登歷史取消的實際服務事實；不是重新取消或重開。');
    const confirmed = facts.confirmed_service_days;
    await apply(); expect(mocks.preview).toHaveBeenCalledWith(CASE, confirmed, expect.any(AbortSignal));
    view.unmount(); facts.historical_mid_service_confirmation_available = false;
    render(<OrderCancellationPanel caseNo={CASE} />); await open();
    expect(screen.queryByRole('button', { name: /確認取消訂單|確認補登/ })).not.toBeInTheDocument();
    expect(mocks.preview).toHaveBeenCalledTimes(1);
  });

  it('owner blocker 不能 Apply', async () => {
    mocks.preview.mockResolvedValue({ ...preview(), payroll_impact: { case_no: CASE, actions: [], blockers: ['payroll_frozen'] } });
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await requestPreview();
    expect(screen.getByText('payroll_frozen')).toBeInTheDocument();
    expect(screen.getByText('應退款 NT$ 1000')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認取消' })).toBeDisabled();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('有正式服務時開啟原服務條件入口，保留取消未執行', async () => {
    mocks.preview.mockRejectedValue(new ApiHttpError(409, 'order_cancellation_has_actual_service', '案件有實際服務'));
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await requestPreview();
    expect(await screen.findByRole('link', { name: '前往修改服務條件與完整班表' }))
      .toHaveAttribute('href', `#clients?case=${CASE}&from=workbench`);
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it.each([true, false, undefined])('歷史資料缺漏或待核對仍可由人員確認，預覽後套用並讀回成立後未服務（現金差額待核對標記 %s）', async (requiresReview) => {
    facts = { ...facts, lifecycle_status: '訂單取消', historical_unserved_correction: {
      blockers: [], review_codes: ['historical_unserved_not_historical', 'historical_unserved_establishment_evidence_missing',
        'historical_unserved_actual_service_evidence', 'historical_unserved_cash_evidence_requires_review'],
      establishment_lifecycle_event_ids: [], establishment_adoption_receipt_ids: [],
      establishment_owner_status: null, historical_adoption_receipt_ids: [], historical_absence_event_ids: [],
      actual_service_evidence: ['confirmed_service_days'], actual_start_date: null, actual_end_date: null, prior_fee_ntd: 1000,
      prior_fee_reason: '歷史費用', net_cash_received_ntd: null, prior_cancellation_event_id: 4,
      client_obligations: [], payroll_obligations: [],
    } };
    const calculated = preview();
    mocks.preview.mockResolvedValue({
      ...calculated,
      lifecycle_impact: { ...calculated.lifecycle_impact, after_status: '成立後未服務' },
      historical_unserved_correction: {
        classification_only: false, retired_adopted_assignment_ids: [], payroll_recoveries: [],
        ...(requiresReview === undefined ? {} : { client_cash_difference_requires_review: requiresReview }),
      },
    });
    mocks.apply.mockImplementation(async () => {
      facts = { ...facts, lifecycle_status: '成立後未服務', order_version: 3, scheduling_version: 4, client_finance_version: 5, payroll_version: 6, historical_unserved_correction: null };
      return { ...receipt(), lifecycle_status: '成立後未服務' };
    });
    const onObserved = vi.fn();
    render(<OrderCancellationPanel caseNo={CASE} historicalUnservedCorrection onObserved={onObserved} />);
    await screen.findByText('訂單取消', { selector: 'strong' });
    const check = screen.getByRole('button', { name: '預覽零服務更正' });
    expect(check).toBeDisabled();
    expect(screen.getByText('系統沒有正式成立紀錄。')).toBeVisible();
    expect(screen.getByText('服務證據：confirmed_service_days')).toBeVisible();
    expect(screen.getByText('收付款項待核對。更正後請確認對帳明細配對。')).toBeVisible();
    expect(screen.getByLabelText('更正原因（選填）')).toHaveValue('');
    expect(screen.getByLabelText('證據來源（選填）')).toHaveValue('');
    fireEvent.click(screen.getByRole('checkbox', { name: '我確認將本案更正為成立後未服務' }));
    expect(check).toBeEnabled();
    const correction = { reason: '', evidence_source: '', confirmed_actual_service_day_count: 0 };
    await act(async () => { fireEvent.click(check); });
    expect(mocks.preview).toHaveBeenCalledWith(CASE, [], expect.any(AbortSignal), { historical_unserved_correction: correction });
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(screen.getByText(/正式服務：0 日／0 小時/)).toBeVisible();
    expect(screen.getByText('應退款 NT$ 1000')).toBeVisible();
    const notice = screen.queryByText(/退款／補收金額為待核對目標/);
    if (requiresReview) {
      expect(notice).toBeVisible();
      expect(notice).toHaveTextContent('套用後會保留未能辨識的舊差額，暫緩新增退款以避免重複退款。請由對帳人員確認明細配對。');
    } else {
      expect(notice).not.toBeInTheDocument();
    }
    const confirm = screen.getByRole('button', { name: '確認更正為成立後未服務' });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await screen.findByText('本案已完成更正，無須再次操作。');
    expect(mocks.apply).toHaveBeenCalledWith(CASE, expect.objectContaining({ historical_unserved_correction: correction }), expect.anything());
    expect(onObserved).toHaveBeenCalledTimes(1);
  });

  it('歷史更正有技術阻擋時顯示原因且禁止預覽', async () => {
    facts = { ...facts, lifecycle_status: '訂單取消', historical_unserved_correction: {
      blockers: ['historical_unserved_status_ineligible'], review_codes: [],
      establishment_lifecycle_event_ids: [], establishment_adoption_receipt_ids: [],
      establishment_owner_status: null, historical_adoption_receipt_ids: [], historical_absence_event_ids: [],
      actual_service_evidence: [], actual_start_date: null, actual_end_date: null, prior_fee_ntd: 0,
      prior_fee_reason: '', net_cash_received_ntd: null, prior_cancellation_event_id: null,
      client_obligations: [], payroll_obligations: [],
    } };
    render(<OrderCancellationPanel caseNo={CASE} historicalUnservedCorrection />);
    await screen.findByText('訂單取消', { selector: 'strong' });
    expect(screen.getByRole('alert')).toHaveTextContent('案件目前的狀態無法執行這項更正。');
    expect(screen.queryByRole('button', { name: '預覽零服務更正' })).not.toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it.each([
    { name: '沒有更正明細', blockers: null },
    { name: '已有更正明細', blockers: ['historical_unserved_status_ineligible'] },
    { name: '另有帳務阻擋', blockers: ['historical_unserved_status_ineligible', 'historical_unserved_cash_ledger_invalid'] },
  ])('重新開啟已完成更正的案件時顯示唯讀結果（$name）', async ({ blockers }) => {
    facts = {
      ...facts,
      lifecycle_status: '成立後未服務',
      historical_unserved_correction: blockers === null ? null : {
        blockers,
        review_codes: ['historical_unserved_cash_evidence_requires_review'],
        establishment_lifecycle_event_ids: [12345], establishment_adoption_receipt_ids: [],
        establishment_owner_status: null, historical_adoption_receipt_ids: [], historical_absence_event_ids: [],
        actual_service_evidence: [], actual_start_date: null, actual_end_date: null, prior_fee_ntd: 0,
        prior_fee_reason: '', net_cash_received_ntd: 1000, prior_cancellation_event_id: null,
        client_obligations: [
          { obligation_identity: 'deposit-1', payment_stage: 'deposit', contracted_ntd: 1000, settled_ntd: 1000 },
          { obligation_identity: 'first-1', payment_stage: 'first', contracted_ntd: 8000, settled_ntd: 0 },
        ],
        payroll_obligations: [],
      },
    };
    const onObserved = vi.fn();
    render(<OrderCancellationPanel caseNo={CASE} historicalUnservedCorrection onObserved={onObserved} />);

    expect(await screen.findByText('本案已完成更正，無須再次操作。')).toHaveAttribute('role', 'status');
    expect(screen.getByText('成立後未服務', { selector: 'strong' })).toBeVisible();
    expect(screen.getByRole('link', { name: '查看本案帳務' })).toHaveAttribute('href', `#finance?tab=case-accounting&case_no=${CASE}&from=workbench`);
    expect(screen.getByRole('link', { name: '以此案資料建立非市民新案' })).toHaveAttribute('href', `#clients?tab=applications&source_case=${CASE}`);
    expect(screen.queryByText('案件目前的狀態無法執行這項更正。')).not.toBeInTheDocument();
    if (blockers?.includes('historical_unserved_cash_ledger_invalid')) {
      expect(screen.getByRole('alert')).toHaveTextContent('本案收付款紀錄有誤，請先核對帳務。');
    } else {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    }
    if (blockers !== null) {
      expect(screen.getByRole('heading', { name: '定金' })).toBeVisible();
      expect(screen.getByRole('heading', { name: '第一期款' })).toBeVisible();
      expect(screen.getByText('收付款項待核對。更正後請確認對帳明細配對。')).toBeVisible();
      const summary = screen.getByText('來源紀錄編號');
      expect(summary.closest('details')).not.toHaveAttribute('open');
      expect(screen.getByText('12345')).toBeInTheDocument();
    }
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽零服務更正' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認更正為成立後未服務' })).not.toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(onObserved).not.toHaveBeenCalled();
  });

  it('Apply 409 使預覽失效，不能用舊版本重送', async () => {
    mocks.apply.mockRejectedValue(new ApiHttpError(409, 'stale_preview', '版本已變更'));
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await confirmPreview(); await apply();
    await screen.findByText('取消未通過檢查，請重新讀取並預覽：版本已變更');
    expect(screen.queryByRole('button', { name: '確認取消' })).not.toBeInTheDocument();
    expect(mocks.apply).toHaveBeenCalledTimes(1);
  });

  it('未知結果先讀原收據，已取得時只回讀而不重送 Apply', async () => {
    mocks.apply.mockImplementation(async () => { commitFacts(); throw new Error('network outcome unknown'); });
    mocks.receipt.mockResolvedValue(receipt());
    const onObserved = vi.fn();
    render(<OrderCancellationPanel caseNo={CASE} onObserved={onObserved} />); await open(); await confirmPreview(); await apply();
    const retry = await screen.findByRole('button', { name: '查詢原取消收據並確認結果' });
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.getByLabelText('取消原因')).toBeDisabled();
    fireEvent.click(retry);
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.receipt).toHaveBeenCalledWith(CASE, mocks.apply.mock.calls[0]![2].idempotencyKey);
    expect(mocks.apply).toHaveBeenCalledTimes(1); expect(onObserved).toHaveBeenCalledTimes(1);
  });

  it('只有原收據 404 才能用同 payload／key 重試 Apply', async () => {
    mocks.apply.mockRejectedValueOnce(new Error('lost response'));
    mocks.receipt.mockRejectedValue(new ApiHttpError(404, 'receipt_not_found', 'no receipt'));
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await confirmPreview(); await apply();
    fireEvent.click(await screen.findByRole('button', { name: '查詢原取消收據並確認結果' }));
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.apply).toHaveBeenCalledTimes(2);
    expect(mocks.apply.mock.calls[1]).toEqual(mocks.apply.mock.calls[0]);
  });

  it('原收據 403 或暫時失敗不能當成404重送取消', async () => {
    mocks.apply.mockRejectedValue(new Error('lost response'));
    mocks.receipt.mockRejectedValue(new ApiHttpError(403, 'forbidden', 'no permission'));
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await confirmPreview(); await apply();
    fireEvent.click(await screen.findByRole('button', { name: '查詢原取消收據並確認結果' }));
    await waitFor(() => expect(mocks.receipt).toHaveBeenCalledTimes(1));
    expect(mocks.apply).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole('button', { name: '查詢原取消收據並確認結果' })).toBeInTheDocument();
  });

  it('receipt 後 Query 失敗只重試觀察，不再次寫入', async () => {
    mocks.query.mockResolvedValueOnce(query()).mockRejectedValueOnce(new Error('readback unavailable'))
      .mockImplementation(async () => structuredClone(facts));
    const onObserved = vi.fn(); render(<OrderCancellationPanel caseNo={CASE} onObserved={onObserved} />);
    await open(); await confirmPreview(); await apply();
    fireEvent.click(await screen.findByRole('button', { name: '只重新讀取取消結果' }));
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.apply).toHaveBeenCalledTimes(1); expect(mocks.receipt).not.toHaveBeenCalled();
    expect(onObserved).toHaveBeenCalledTimes(1);
  });

  it('重複點擊只能送出一次，卸載後晚回讀不通知其他案件', async () => {
    let finish!: (value: OrderCancellationReceipt) => void;
    mocks.apply.mockImplementation(() => new Promise<OrderCancellationReceipt>((resolve) => { finish = resolve; }));
    const onObserved = vi.fn(); const view = render(<OrderCancellationPanel caseNo={CASE} onObserved={onObserved} />);
    await open(); await confirmPreview();
    await requestPreview();
    const button = screen.getByRole('button', { name: '確認取消' });
    fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledTimes(1));
    view.unmount(); commitFacts();
    await act(async () => { finish(receipt()); });
    expect(onObserved).not.toHaveBeenCalled();
  });

  it('取消原因維持選填，空白也能在預覽後送出', async () => {
    render(<OrderCancellationPanel caseNo={CASE} />);
    await open();
    window.alert = vi.fn();
    await apply();
    expect(window.alert).not.toHaveBeenCalled();
    expect(mocks.preview).toHaveBeenCalledTimes(1);
    expect(mocks.apply).toHaveBeenCalledWith(CASE, expect.objectContaining({ reason: '' }), expect.anything());
  });

  it('切換案件後捨棄前一案件的晚到查詢', async () => {
    let finish!: (value: OrderCancellationQuery) => void;
    mocks.query.mockImplementationOnce(() => new Promise<OrderCancellationQuery>((resolve) => { finish = resolve; }))
      .mockResolvedValue(query('CASE-OTHER'));
    mocks.preview.mockImplementation(async (caseNo, days) => preview(days, caseNo));
    const view = render(<OrderCancellationPanel caseNo={CASE} />);
    view.rerender(<OrderCancellationPanel caseNo="CASE-OTHER" />);
    await screen.findByLabelText('案件 CASE-OTHER 訂單取消');
    await act(async () => { finish(query()); });
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();
  });
});
