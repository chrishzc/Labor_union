import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderCaregiverContractPanel } from '../components/OrderCaregiverContractPanel';
import { OrderClientContractPanel } from '../components/OrderClientContractPanel';
import { OrderTermsMutationPanel } from '../components/OrderTermsMutationPanel';
import { OrderCandidateContactStatusPanel } from '../components/OrderCandidateContactStatusPanel';
import { OrderAssignmentPlanPanel } from '../components/OrderAssignmentPlanPanel';
import { OrderFormalRecommendationPanel } from '../components/OrderFormalRecommendationPanel';
import type { OrderTerms } from '../api/orders/order_query_schemas';

const mocks = vi.hoisted(() => ({ signing: vi.fn(), sendStaff: vi.fn(), sendClient: vi.fn(),
  termsQuery: vi.fn(), termsPreview: vi.fn(), termsApply: vi.fn(), pool: vi.fn(), willingness: vi.fn(),
  assignment: vi.fn(), active: vi.fn(), contact: vi.fn(), sendProfiles: vi.fn() }));
vi.mock('../api/orders/contract_signing_client', () => ({ contractSigningClient: { query: mocks.signing } }));
vi.mock('../api/orders/contract_signing_mutation_client', () => ({ contractSigningMutationClient: { sendStaff: mocks.sendStaff, sendClient: mocks.sendClient } }));
vi.mock('../api/orders/order_terms_mutation_client', () => ({ orderTermsMutationClient: { query: mocks.termsQuery, preview: mocks.termsPreview, apply: mocks.termsApply } }));
vi.mock('../api/scheduling/candidate_contact_pool_client', () => ({ candidateContactPoolClient: { query: mocks.pool, recordWillingness: mocks.willingness } }));
vi.mock('../api/orders/order_query_client', () => ({ ordersQueryClient: { getAssignmentPlan: mocks.assignment } }));
vi.mock('../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: { queryPlan: mocks.active } }));
vi.mock('../api/scheduling/matching_plan_communication_client', () => ({ matchingPlanCommunicationClient: { queryContactState: mocks.contact, sendCustomerProfiles: mocks.sendProfiles } }));
vi.mock('../components/ServiceBeforeReplacementActions', () => ({ ServiceBeforeReplacementActions: ({ onCommitted }: { onCommitted: () => Promise<void> }) => (
  <button type="button" onClick={() => void onCommitted()}>模擬正式更換完成</button>
) }));
const CASE = 'CASE-OWNER-CALLBACK';
function signing(sent: boolean) {
  return { case_no: CASE, staff_segments: [{ segment_id: 7, staff_id: 8, sent, signed_received: false }],
    commitment_id: 1, client_document_sent: sent, client_signed_received: false, contract_identity: null, documents: [] };
}
function terms(updated = false): OrderTerms {
  return { case_no: CASE, order_version: updated ? 3 : 2, scheduling_version: updated ? 4 : 3,
    scheduling_generation: updated ? 2 : 1, client_finance_version: updated ? 5 : 4, payroll_version: updated ? 6 : 5,
    service_data_locked: false, terms: { planned_start_date: '2026-09-01', service_days: updated ? 3 : 2,
      service_hours_per_day: 8, requires_cooking: false, floor_fee_ntd: 0,
      service_time: { start_time: '09:00:00', end_time: '17:00:00', end_day_offset: 0 } } };
}
function pool(willingness: 'pending' | 'willing') {
  return { case_no: CASE, pool_id: 9, candidates: [{ id: 17, staff_id: 8, staff_name: '測試月嫂', status: 'active',
    willingness, reason: null, information: { '1': null, '2': null } }] };
}
function TermsHarness({ onObserved }: { onObserved: () => void }) {
  const [query, setQuery] = useState(terms());
  return <OrderTermsMutationPanel caseNo={CASE} query={query} onObserved={() => { setQuery(terms(true)); onObserved(); }} />;
}
async function applyTerms() {
  fireEvent.change(screen.getByLabelText('Beta 服務天數'), { target: { value: '3' } });
  fireEvent.click(screen.getByRole('button', { name: '檢查訂單條款變更' }));
  const reason = await screen.findByLabelText('Beta 條款變更原因');
  fireEvent.change(reason, { target: { value: '客戶確認延長一天。' } });
  fireEvent.click(screen.getByRole('button', { name: '確認套用訂單條款' }));
}

describe('Beta 實際 owner 元件只在正式回讀成立後通知外層', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.sendStaff.mockResolvedValue({}); mocks.sendClient.mockResolvedValue({});
    mocks.termsPreview.mockResolvedValue({ before: terms().terms, after: terms(true).terms,
      order_version: 2, scheduling_version: 3, client_finance_version: 4, payroll_version: 5, preview_fingerprint: 'a'.repeat(64) });
    mocks.termsApply.mockResolvedValue({ case_no: CASE, order_version: 3, scheduling_version: 4,
      client_finance_version: 5, payroll_version: 6, official_service_day_count: 3 });
    mocks.termsQuery.mockResolvedValue(terms(true));
    mocks.willingness.mockResolvedValue({ status: 'willing', event_id: 18 });
    mocks.assignment.mockResolvedValue({ case_no: CASE, assignments: [], scheduling_version: 4,
      scheduling_generation: 2, contracted_service_days: 3, service_hours_per_day: 8 });
    mocks.active.mockResolvedValue({ planId: 51, status: 'proposed', activeLockId: null, communicationVersion: 4, segments: [] });
    mocks.contact.mockResolvedValue({ plan: { id: 51, case_no: CASE, communication_version: 4, status: 'proposed', is_active: 1 },
      segments: [], all_willing: true, customer_decision: 'pending', customer_profiles_status: null, customer_profiles_manual_confirmation: null });
  });

  it.each(['caregiver', 'client'] as const)('%s 契約寄送回讀 true 後才刷新外層', async (kind) => {
    mocks.signing.mockResolvedValueOnce(signing(false)).mockResolvedValue(signing(true));
    const onObserved = vi.fn();
    render(kind === 'caregiver' ? <OrderCaregiverContractPanel caseNo={CASE} onObserved={onObserved} /> : <OrderClientContractPanel caseNo={CASE} onObserved={onObserved} />);
    fireEvent.click(screen.getByRole('button', { name: kind === 'caregiver' ? '讀取月嫂契約狀態' : '讀取客戶契約狀態' }));
    fireEvent.change(await screen.findByLabelText(kind === 'caregiver' ? '受控 HTTPS 文件下載網址' : '客戶契約受控 HTTPS 文件下載網址'), { target: { value: 'https://example.test/controlled.pdf' } });
    expect(onObserved).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: kind === 'caregiver' ? '建立月嫂契約寄送工作' : '建立客戶契約寄送工作' }));
    await waitFor(() => expect(onObserved).toHaveBeenCalledTimes(1));
    expect(mocks.signing).toHaveBeenCalledTimes(2);
  });

  it.each(['caregiver', 'client'] as const)('%s 契約只有 receipt、owner 尚未確認時不回報完成', async (kind) => {
    mocks.signing.mockResolvedValue(signing(false));
    const onObserved = vi.fn();
    render(kind === 'caregiver' ? <OrderCaregiverContractPanel caseNo={CASE} onObserved={onObserved} /> : <OrderClientContractPanel caseNo={CASE} onObserved={onObserved} />);
    fireEvent.click(screen.getByRole('button', { name: kind === 'caregiver' ? '讀取月嫂契約狀態' : '讀取客戶契約狀態' }));
    fireEvent.change(await screen.findByLabelText(kind === 'caregiver' ? '受控 HTTPS 文件下載網址' : '客戶契約受控 HTTPS 文件下載網址'), { target: { value: 'https://example.test/controlled.pdf' } });
    fireEvent.click(screen.getByRole('button', { name: kind === 'caregiver' ? '建立月嫂契約寄送工作' : '建立客戶契約寄送工作' }));
    await screen.findByText(kind === 'caregiver' ? '月嫂契約回讀尚未觀察到本次操作結果。' : '客戶契約回讀尚未觀察到本次操作結果。');
    expect(onObserved).not.toHaveBeenCalled();
  });

  it('條款 callback 帶動父查詢更新至同一已觀察版本，不抹去完成證據', async () => {
    const onObserved = vi.fn(); render(<TermsHarness onObserved={onObserved} />);
    await applyTerms();
    await screen.findByText('條款已套用並完成正式回讀；Order version 3，合約服務 3 日。');
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Beta 服務天數')).toHaveValue(3);
  });

  it('條款回讀比 receipt 舊時不將舊版本當成完成', async () => {
    mocks.termsQuery.mockResolvedValue(terms());
    const onObserved = vi.fn(); render(<OrderTermsMutationPanel caseNo={CASE} query={terms()} onObserved={onObserved} />);
    await applyTerms(); await screen.findByText(/條款回讀案件識別或版本與收據不一致/);
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.queryByText(/條款已套用並完成正式回讀/)).not.toBeInTheDocument();
  });

  it('候選意願需同案件同 candidate 的實際 readback，才通知外層', async () => {
    mocks.pool.mockResolvedValueOnce(pool('pending')).mockResolvedValue(pool('willing'));
    const onObserved = vi.fn(); render(<OrderCandidateContactStatusPanel caseNo={CASE} onObserved={onObserved} />);
    fireEvent.click(screen.getByRole('button', { name: '讀取候選聯絡狀態' }));
    fireEvent.click(await screen.findByRole('button', { name: '記錄 測試月嫂 願意' }));
    await screen.findByText('意願已記錄並回讀：willing · event #18');
    expect(onObserved).toHaveBeenCalledTimes(1); expect(mocks.pool).toHaveBeenCalledTimes(2);
  });

  it('正式指派單純 GET 不刷新父頁形成迴圈，更換完成後的 GET 才通知', async () => {
    const onObserved = vi.fn(); render(<OrderAssignmentPlanPanel caseNo={CASE} onObserved={onObserved} />);
    fireEvent.click(screen.getByRole('button', { name: '讀取正式指派與排班' }));
    await screen.findByText('尚無正式指派'); expect(onObserved).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '服務前更換月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '模擬正式更換完成' }));
    await waitFor(() => expect(onObserved).toHaveBeenCalledTimes(1)); expect(mocks.assignment).toHaveBeenCalledTimes(2);
  });

  it('履歷命令已送出後卸載，晚回來的 receipt 不通知另一個畫面', async () => {
    let resolve!: (value: { intent_id: number; delivery_status: string }) => void;
    mocks.sendProfiles.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const onObserved = vi.fn(); const view = render(<OrderFormalRecommendationPanel caseNo={CASE} onObserved={onObserved} />);
    fireEvent.change(await screen.findByLabelText('方案 51 履歷傳送備註'), { target: { value: '人工核對履歷。' } });
    fireEvent.click(screen.getByRole('button', { name: '寄送月嫂履歷給客戶' }));
    await waitFor(() => expect(mocks.sendProfiles).toHaveBeenCalledTimes(1));
    view.unmount();
    await act(async () => { resolve({ intent_id: 81, delivery_status: 'pending' }); });
    expect(onObserved).not.toHaveBeenCalled(); expect(mocks.sendProfiles).toHaveBeenCalledTimes(1);
  });
});
