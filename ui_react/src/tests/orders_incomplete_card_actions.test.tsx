import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrdersPage } from '../pages/OrdersPage';

const mocks = vi.hoisted(() => ({
  loadSummaries: vi.fn(),
  loadStages: vi.fn(),
  getCardProjection: vi.fn(),
  getOrderTerms: vi.fn(),
  getContractCompletion: vi.fn(),
  getOrderDetail: vi.fn(),
  contractQuery: vi.fn(),
}));

vi.mock('../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: mocks.loadSummaries,
  ordersQueryClient: {
    getOrderSummaries: vi.fn(),
    getOrderTerms: mocks.getOrderTerms,
    getContractCompletion: mocks.getContractCompletion,
    getOrderDetail: mocks.getOrderDetail,
  },
}));

vi.mock('../api/orders/order_stage_projection_client', () => ({
  loadAllOrderOperationalTimelines: mocks.loadStages,
  orderStageProjectionClient: {
    getOperationalTimelines: vi.fn(),
  },
}));

vi.mock('../api/orders/order_card_projection_client', () => ({
  orderCardProjectionClient: {
    getCardProjection: mocks.getCardProjection,
  },
}));

vi.mock('../api/orders/contract_signing_client', () => ({
  contractSigningClient: {
    query: mocks.contractQuery,
  },
}));

vi.mock('../adapters/orders/order_summary_adapter', () => ({
  ORDER_FILTER_OPTIONS: [{ stage: '全部', label: '全部' }],
  ORDERS_TYPED_PROJECTION_UNAVAILABLE: '訂單投影不可用',
  adaptOrderSummaryPage: () => ({
    items: [{
      id: 'CASE-INCOMPLETE',
      clientName: '待補姓名',
      identityStatus: '待補正',
      orderStatus: '待補件',
      status: '待補件',
      serviceRange: '待補服務日期',
      serviceDays: null,
      serviceDaysLabel: '待補天數',
      actualStartDate: null,
      contractAmount: null,
      contractAmountFormatted: '待補金額',
      assignedDoulaName: null,
      assignedDoulaDisplay: null,
    }],
    loadedCount: 1,
    nextCursor: null,
  }),
}));

describe('OrdersPage incomplete intake card actions', () => {
  beforeEach(() => {
    mocks.loadSummaries.mockReset();
    mocks.loadStages.mockReset();
    mocks.getCardProjection.mockReset();
    mocks.getOrderTerms.mockReset();
    mocks.getContractCompletion.mockReset();
    mocks.getOrderDetail.mockReset();
    mocks.contractQuery.mockReset();

    mocks.loadSummaries.mockResolvedValue({ items: [] });
    mocks.loadStages.mockRejectedValue(new Error('stage projection not needed for this focused test'));
    mocks.getCardProjection.mockRejectedValue(new Error('card projection not needed for this focused test'));
    mocks.getOrderTerms.mockRejectedValue(new Error('contract query not needed for drawer reachability'));
    mocks.getContractCompletion.mockRejectedValue(new Error('contract query not needed for drawer reachability'));
    mocks.getOrderDetail.mockRejectedValue(new Error('contract query not needed for drawer reachability'));
    mocks.contractQuery.mockRejectedValue(new Error('contract query not needed for drawer reachability'));
  });

  it('keeps the incomplete hint while leaving existing workbench actions reachable', async () => {
    render(<OrdersPage />);

    await waitFor(() => expect(screen.getByText('CASE-INCOMPLETE')).toBeInTheDocument());

    expect(screen.getByText(/案件仍待補齊姓名、服務日期等進件資料/)).toBeInTheDocument();
    const contractButton = screen.getByRole('button', { name: '📑 條款與契約' });
    expect(contractButton).toBeEnabled();
    expect(screen.getByRole('button', { name: '👩‍🍼 媒合與正式排班' })).toBeEnabled();

    fireEvent.click(contractButton);

    await waitFor(() => expect(screen.getByText(/訂單條款、服務日曆與契約簽署工作台 — CASE-INCOMPLETE/)).toBeInTheDocument());
  });
});
