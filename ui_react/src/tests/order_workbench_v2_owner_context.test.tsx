import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrdersCardProjection, OrdersCardProjectionField } from '../api/orders/order_card_projection_schemas';
import type { FormManagementContext } from '../api/orders/order_query_schemas';
import { OrderWorkbenchV2OwnerContext } from '../components/OrderWorkbenchV2OwnerContext';

const mocks = vi.hoisted(() => ({
  card: vi.fn(),
  form: vi.fn(),
  notifications: vi.fn(),
}));

vi.mock('../api/orders/order_card_projection_client', () => ({
  orderCardProjectionClient: { getCardProjection: mocks.card },
}));
vi.mock('../api/orders/order_query_client', () => ({
  ordersQueryClient: { getFormManagementContext: mocks.form },
}));
vi.mock('../api/line/notification_timeline_client', () => ({
  lineNotificationTimelineClient: { query: mocks.notifications },
}));

function field<T>(value: T | null, owner = 'Orders'): OrdersCardProjectionField<T> {
  return {
    value,
    owner,
    source_identity: `${owner}:fixture`,
    source_version: '1',
    availability: value === null ? 'unavailable' : 'available',
    availability_reason: value === null ? 'not_recorded' : null,
  };
}

function projection(caseNo = 'CASE-A', phone = '0200000000'): OrdersCardProjection {
  return {
    case_no: caseNo,
    contact_phone: field(phone, 'Clients'),
    contact_address: field('測試地址 101 號（非真實個資）', 'Clients'),
    requires_cooking: field(false),
    floor_fee_ntd: field(250),
    deposit_amount_ntd: field(12000, 'Client Finance'),
    deposit_settlement_state: field('unsettled' as const, 'Client Finance'),
    deposit_settled_on: field<string>(null, 'Client Finance'),
    actual_start_date: field<string>(null),
    actual_end_date: field<string>(null),
    assignment_segments: field([]),
  };
}

function form(caseNo = 'CASE-A'): FormManagementContext {
  return {
    case_no: caseNo,
    service_time: '09:00–17:00',
    service_type: '測試服務類型',
    delivery_type: '測試生產方式',
    residence_type: '測試住宅類型',
    city: '測試縣市',
    identity_status: '測試身分類別',
  };
}

function openContext() {
  fireEvent.click(screen.getByRole('button', { name: '讀取案件聯絡、服務資料與 LINE 歷程' }));
}

describe('Beta reuses legacy canonical owner readbacks', () => {
  beforeEach(() => {
    mocks.card.mockReset().mockResolvedValue(projection());
    mocks.form.mockReset().mockResolvedValue(form());
    mocks.notifications.mockReset().mockResolvedValue({ case_no: 'CASE-A', records: [] });
  });

  it('queries the same three owner clients on demand and displays full canonical business values', async () => {
    render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" />);
    expect(mocks.card).not.toHaveBeenCalled();
    expect(mocks.form).not.toHaveBeenCalled();
    expect(mocks.notifications).not.toHaveBeenCalled();

    openContext();

    expect(await screen.findByText('0200000000')).toBeInTheDocument();
    expect(screen.getByText('測試地址 101 號（非真實個資）')).toBeInTheDocument();
    expect(screen.getByText('NT$ 12,000')).toBeInTheDocument();
    expect(screen.getByText('unsettled')).toBeInTheDocument();
    expect(screen.getByText('09:00–17:00')).toBeInTheDocument();
    expect(screen.getByText('測試服務類型')).toBeInTheDocument();
    expect(screen.getByText('測試生產方式')).toBeInTheDocument();
    expect(screen.getByText('測試住宅類型')).toBeInTheDocument();
    expect(screen.getByText('測試縣市')).toBeInTheDocument();
    expect(screen.getByText('尚無 LINE 通知事件。')).toBeInTheDocument();
    for (const query of [mocks.card, mocks.form, mocks.notifications]) {
      expect(query).toHaveBeenCalledWith('CASE-A', { signal: expect.any(AbortSignal) });
    }
  });

  it('keeps a LINE permission failure local instead of hiding contact or service owner facts', async () => {
    mocks.notifications.mockRejectedValue(new Error('403 權限不足（測試）'));
    render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" />);
    openContext();

    expect(await screen.findByText(/LINE 通知歷程不可用：403/)).toBeInTheDocument();
    expect(screen.getByText('0200000000')).toBeInTheDocument();
    expect(screen.getByText('測試服務類型')).toBeInTheDocument();
  });

  it('preserves owner field availability and does not infer a settlement or actual service date', async () => {
    const data = projection();
    data.deposit_amount_ntd = { ...field<number>(null, 'Client Finance'), availability: 'blocked', availability_reason: 'owner_unavailable' };
    mocks.card.mockResolvedValue(data);
    render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" />);
    openContext();

    expect(await screen.findByText('資料受阻（定金金額）')).toBeInTheDocument();
    expect(screen.getByText('資料待補正（已發生實際開始日）')).toBeInTheDocument();
    expect(screen.getByText('unsettled')).toBeInTheDocument();
    expect(screen.queryByText('NT$ 12,000')).not.toBeInTheDocument();
  });

  it('shows notification scheduling, delivery and historical silence as distinct owner facts', async () => {
    mocks.notifications.mockResolvedValue({
      case_no: 'CASE-A',
      records: [{
        source_event_id: 1,
        event_code: 'fixture.created',
        historical_silent: true,
        decision_status: 'suppressed',
        reason_code: 'historical_silent',
        intent_status: 'scheduled',
        delivery_status: null,
      }],
    });
    render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" />);
    openContext();

    expect(await screen.findByText('fixture.created')).toBeInTheDocument();
    expect(screen.getByText('scheduled')).toBeInTheDocument();
    expect(screen.getByText('尚無投遞紀錄')).toBeInTheDocument();
    expect(screen.getByText('歷史靜默事件；不補發通知。')).toBeInTheDocument();
  });

  it('re-queries all expanded owner readbacks after a drawer revision changes', async () => {
    const view = render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" revision={0} />);
    openContext();
    await screen.findByText('0200000000');
    const firstSignal = mocks.card.mock.calls[0]![1].signal as AbortSignal;
    mocks.card.mockResolvedValue(projection('CASE-A', '0200000001'));

    view.rerender(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" revision={1} />);

    expect(await screen.findByText('0200000001')).toBeInTheDocument();
    expect(screen.queryByText('0200000000')).not.toBeInTheDocument();
    expect(firstSignal.aborted).toBe(true);
    for (const query of [mocks.card, mocks.form, mocks.notifications]) expect(query).toHaveBeenCalledTimes(2);
  });

  it('does not replace the current case with a late response from the previous case', async () => {
    let resolveFirst!: (value: OrdersCardProjection) => void;
    mocks.card.mockImplementationOnce(() => new Promise<OrdersCardProjection>((resolve) => { resolveFirst = resolve; }));
    const view = render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" />);
    openContext();
    await waitFor(() => expect(mocks.card).toHaveBeenCalledTimes(1));
    const firstSignal = mocks.card.mock.calls[0]![1].signal as AbortSignal;
    mocks.card.mockResolvedValue(projection('CASE-B', '0200000001'));
    mocks.form.mockResolvedValue(form('CASE-B'));
    mocks.notifications.mockResolvedValue({ case_no: 'CASE-B', records: [] });

    view.rerender(<OrderWorkbenchV2OwnerContext caseNo="CASE-B" />);
    await screen.findByText('0200000001');
    await act(async () => { resolveFirst(projection()); });

    expect(firstSignal.aborted).toBe(true);
    expect(screen.getByText('0200000001')).toBeInTheDocument();
    expect(screen.queryByText('0200000000')).not.toBeInTheDocument();
  });

  it('rejects a mismatched form context without suppressing the other readbacks', async () => {
    mocks.form.mockResolvedValue(form('OTHER-CASE'));
    render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" />);
    openContext();

    expect(await screen.findByText(/客戶服務資料案件識別不一致/)).toBeInTheDocument();
    expect(screen.getByText('0200000000')).toBeInTheDocument();
    expect(screen.queryByText('測試服務類型')).not.toBeInTheDocument();
    expect(screen.getByText('尚無 LINE 通知事件。')).toBeInTheDocument();
  });
});
