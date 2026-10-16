/** Verify the approved identity workspace against real typed query/command boundaries. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LineIdentityWorkbench } from '../../../../../../components/LineIdentityWorkbench';
import { LineIdentityClientError } from '../../../../../../api/line_identity/line_identity_errors';
import { BOUND_IDENTITY_FIXTURE as binding, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE } from '../../../../../fixtures/line_identity/line_identity_contract_fixtures';
import type { LineIdentityBindingView } from '../../../../../../api/line_identity/line_identity_schemas';
import { lineIdentityClient } from '../../../../../../api/line_identity/line_identity_client';
import { sessionClient } from '../../../../../../api/auth/session_client';
import { transport } from '../../../../../../api/shared/transport';

const summary = { pending_total: 3, staff_pending: 0, rebind_pending: 2, processed_today: 1, stale_pending: 0, stale_hours: 24 };
const review = { request_id: 71, review_type: 'client_rebind' as const, status: 'pending' as const, version: 3, subject_type: 'customer' as const, subject_reference: '7', assigned_admin_id: null, due_at: null, line_user_id: 'U-request-private-new', current_line_user_id: 'U-request-private-old', display_name: '審核對象甲', subject_display_reference: 'ORD-071', decision_reason: null, reviewed_by_actor_id: null, reviewed_at: null, created_at: '2026-10-15T02:00:00Z' };
const staff: LineIdentityBindingView = { ...binding, subject_type: 'staff', subject_reference: '8', subject_name: '同帳號月嫂' };
const candidate = { subject_type: 'customer' as const, subject_reference: '9', subject_name: '更正客戶乙', subject_display_reference: 'ORD-009', current_line_user_id: null };
const paired = { orders: [{ case_no: 'ORD-086', client_id: 86, client_name: '邱珮瑜', client_phone: '0912345382', start_date: null, status: '待派案' }], provisional_registrations: [{ registration_id: 81, name: '邱佩瑜', phone: '0912345382', line_user_id: 'U-pair-private', client_id: null, submitted_at: '2026-10-15T02:00:00Z' }] };
function client(items = [binding]) {
  return {
    listBindings: vi.fn().mockResolvedValue({ items, total: items.length, page: 1, page_size: 25 }),
    getBinding: vi.fn().mockResolvedValue(binding), getReviewSummary: vi.fn().mockResolvedValue(summary),
    listReplacementCandidates: vi.fn().mockResolvedValue({ items: [candidate], total: 1, page: 1, page_size: 25 }),
    previewReplacement: vi.fn().mockResolvedValue({ binding, target_subject_reference: '9', target_subject_name: candidate.subject_name, blockers: [] }),
    applyReplacement: vi.fn().mockResolvedValue({ ...binding, subject_reference: '9', subject_name: candidate.subject_name, version: 8 }),
    previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE), applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE), retryRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
    listReviews: vi.fn().mockResolvedValue({ items: [review], page: 1, page_size: 25, total: 1 }), getReview: vi.fn().mockResolvedValue(review),
    previewReviewDecision: vi.fn().mockResolvedValue({ request_id: 71, decision: 'approve', before_status: 'pending', after_status: 'approved', expected_version: 3, resulting_version: 4, subject_type: 'customer', subject_reference: '7', line_user_id: review.line_user_id, preview_fingerprint: 'private-preview-fingerprint' }),
    applyReviewDecision: vi.fn().mockResolvedValue({ ...review, status: 'approved', version: 4, outcome: 'created', receipt_identity: 'private-receipt' }),
    listUnboundCandidates: vi.fn().mockResolvedValue(paired), pairProvisionalRegistration: vi.fn().mockResolvedValue({ case_no: 'ORD-086', client_id: 86, client_name: '邱珮瑜', line_user_id: 'U-pair-private', status: 'bound' }),
  };
}
async function openBinding(name = binding.subject_name, role = '客戶') { fireEvent.click(await screen.findByRole('button', { name: `查看${name}的${role}身分` })); return screen.findByRole('dialog'); }
async function confirmReason(label: string, reason: string) { fireEvent.change(screen.getByRole('textbox', { name: label }), { target: { value: reason } }); fireEvent.click(screen.getByRole('button', { name: '下一步：確認' })); await screen.findByRole('checkbox'); }
afterEach(() => { vi.restoreAllMocks(); window.history.replaceState(null, '', '/'); });

describe('身分與授權精簡工作區', () => {
  it('三分頁只掛載目前任務，主清單不顯示原始 LINE ID、KPI 或操作表單', async () => {
    const api = client(); render(<LineIdentityWorkbench client={api} />); await screen.findByText(binding.subject_name);
    expect(screen.getAllByRole('tab')).toHaveLength(3); expect(screen.getAllByRole('columnheader')).toHaveLength(5);
    expect(document.querySelector('.line-kpi-grid')).toBeNull(); expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(binding.line_user_id); expect(api.listReviews).not.toHaveBeenCalled(); expect(api.listUnboundCandidates).not.toHaveBeenCalled(); expect(api.previewRevocation).not.toHaveBeenCalled();
  });
  it('搜尋及分頁交給 server，回傳資料不再以遮罩 ID 二次過濾', async () => {
    const api = client(); api.listBindings.mockImplementation(async query => ({ items: [binding], total: 26, page: query.page, page_size: 25 }));
    render(<LineIdentityWorkbench client={api} />); await screen.findByText(binding.subject_name);
    fireEvent.click(screen.getByRole('button', { name: '下一頁' })); await screen.findByText('第 2／2 頁，共 26 筆');
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'ORD-071' } });
    await waitFor(() => expect(api.listBindings).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'ORD-071', page: 1 }), expect.any(Object)));
    await screen.findByText(binding.subject_name);
  });
  it('同一 LINE 的月嫂列明確傳送 staff 角色，不以目前選定角色開啟客戶資料', async () => {
    const api = client([binding, staff]); api.getBinding.mockResolvedValue(staff);
    render(<LineIdentityWorkbench client={api} />); const dialog = await openBinding(staff.subject_name, '月嫂');
    await waitFor(() => expect(api.getBinding).toHaveBeenCalledWith(binding.line_user_id, expect.objectContaining({ subjectType: 'staff' })));
    expect(within(dialog).getByText(staff.subject_name)).toBeInTheDocument(); expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(binding.line_user_id);
  });
  it('拒絕錯角色的 detail，不讓錯誤資料進入操作表單', async () => {
    const api = client([staff]); render(<LineIdentityWorkbench client={api} />); await openBinding(staff.subject_name, '月嫂');
    await screen.findByRole('alert'); expect(screen.queryByRole('button', { name: '解除此身分' })).not.toBeInTheDocument(); expect(api.applyRevocation).not.toHaveBeenCalled();
  });
  it('更正對象來自唯讀候選查詢，須 Preview、原因、確認且 Apply 帶角色與版本', async () => {
    const api = client(); api.getBinding.mockResolvedValueOnce(binding).mockResolvedValue({ ...binding, subject_reference: '9', subject_name: candidate.subject_name, version: 8 });
    render(<LineIdentityWorkbench client={api} />); await openBinding(); fireEvent.click(await screen.findByRole('button', { name: '更正綁定對象' }));
    const select = await screen.findByRole('combobox', { name: '新的綁定對象' }); await within(select).findByText(/更正客戶乙/);
    fireEvent.change(select, { target: { value: '9' } }); await confirmReason('更正原因', '已核對正確對象');
    expect(screen.getByRole('button', { name: '確認更正' })).toBeDisabled(); fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: '確認更正' }));
    await waitFor(() => expect(api.applyReplacement).toHaveBeenCalledTimes(1));
    expect(api.previewReplacement).toHaveBeenCalledWith(binding.line_user_id, '9', expect.objectContaining({ subjectType: 'customer' }));
    expect(api.applyReplacement).toHaveBeenCalledWith(binding.line_user_id, expect.objectContaining({ expected_version: 7, target_subject_reference: '9', reason: '已核對正確對象' }), expect.objectContaining({ subjectType: 'customer' }));
    await waitFor(() => expect(api.getBinding).toHaveBeenCalledTimes(2));
  });
  it('拒絕與所選對象不一致的 Preview，不提交不同對象', async () => {
    const api = client(); api.previewReplacement.mockResolvedValue({ binding, target_subject_reference: 'wrong', target_subject_name: '錯誤對象', blockers: [] });
    render(<LineIdentityWorkbench client={api} />); await openBinding(); fireEvent.click(await screen.findByRole('button', { name: '更正綁定對象' }));
    const select = await screen.findByRole('combobox', { name: '新的綁定對象' }); await within(select).findByText(/更正客戶乙/); fireEvent.change(select, { target: { value: '9' } }); fireEvent.change(screen.getByRole('textbox', { name: '更正原因' }), { target: { value: '已核對' } }); fireEvent.click(screen.getByRole('button', { name: '下一步：確認' }));
    await screen.findByRole('alert'); expect(screen.queryByRole('button', { name: '確認更正' })).not.toBeInTheDocument(); expect(api.applyReplacement).not.toHaveBeenCalled();
  });
  it('解除只操作選定角色；收到申請後重新查詢，不宣稱選單已回復', async () => {
    const api = client(); api.getBinding.mockResolvedValueOnce(binding).mockResolvedValue({ ...binding, status: 'revocation_pending', version: 8, revocation_status: 'pending_menu_reset', revocation_request_id: 901 });
    render(<LineIdentityWorkbench client={api} />); await openBinding(); fireEvent.click(await screen.findByRole('button', { name: '解除此身分' }));
    await confirmReason('解除原因', '客戶要求解除'); expect(screen.getByRole('button', { name: '確認解除此身分' })).toBeDisabled(); fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: '確認解除此身分' }));
    await waitFor(() => expect(api.applyRevocation).toHaveBeenCalledWith(binding.line_user_id, expect.objectContaining({ expected_version: 7, reason: '客戶要求解除' }), expect.objectContaining({ subjectType: 'customer' })));
    await within(screen.getByRole('dialog')).findByText('身分已停用'); expect(screen.queryByRole('button', { name: /人工完成/ })).not.toBeInTheDocument();
  });
  it('結果不明時禁止重複提交，提供讀取最新狀態', async () => {
    const api = client(); api.applyRevocation.mockRejectedValue(new LineIdentityClientError('TIMEOUT', 'private provider error', { outcomeUnknown: true }));
    render(<LineIdentityWorkbench client={api} />); await openBinding(); fireEvent.click(await screen.findByRole('button', { name: '解除此身分' })); await confirmReason('解除原因', '確認解除'); fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: '確認解除此身分' }));
    await screen.findByRole('alert'); expect(screen.queryByRole('button', { name: '確認解除此身分' })).not.toBeInTheDocument(); expect(screen.getByRole('button', { name: '重新查詢綁定狀態' })).toBeEnabled(); expect(document.body.textContent).not.toContain('private provider error');
  });
  it('待審核不預選核准，通過正式 Preview／Apply 後自動查回審核結果', async () => {
    const api = client(); api.getReview.mockResolvedValueOnce(review).mockResolvedValue({ ...review, status: 'approved', version: 4 });
    render(<LineIdentityWorkbench client={api} />); fireEvent.click(screen.getByRole('tab', { name: /待審核/ })); fireEvent.click(await screen.findByRole('button', { name: '審核審核對象甲的綁定申請' }));
    await screen.findByRole('radio', { name: '核准' }); expect(screen.getByRole('radio', { name: '核准' })).not.toBeChecked(); expect(screen.getByRole('button', { name: '下一步：確認' })).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: '核准' })); await confirmReason('審核原因', '已核對原帳號與新申請'); fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: '確認核准' }));
    await screen.findByText('已核准'); expect(api.getReview).toHaveBeenCalledTimes(2); expect(api.applyReviewDecision).toHaveBeenCalledWith(71, 'approve', expect.objectContaining({ expected_version: 3, preview_fingerprint: 'private-preview-fingerprint' }), expect.any(Object));
    expect(document.body.textContent).not.toContain('private-preview-fingerprint'); expect(document.body.textContent).not.toContain(review.line_user_id);
  });
  it('先選登記再選訂單，核對差異、原因與確認後才呼叫原配對 writer', async () => {
    const api = client(); api.listUnboundCandidates.mockResolvedValueOnce(paired).mockResolvedValue({ ...paired, provisional_registrations: [] });
    render(<LineIdentityWorkbench client={api} />); fireEvent.click(screen.getByRole('tab', { name: '待配對' })); fireEvent.click(await screen.findByRole('button', { name: '為邱佩瑜尋找對應訂單' }));
    fireEvent.click(await screen.findByRole('button', { name: '選擇邱珮瑜的訂單' })); expect(screen.getByText(/兩側姓名有差異/)).toBeInTheDocument(); expect(screen.getByRole('button', { name: '確認配對並綁定' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '配對原因' }), { target: { value: '已核對姓名用字差異' } }); fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: '確認配對並綁定' }));
    await screen.findByText('目前沒有待配對登記'); expect(api.pairProvisionalRegistration).toHaveBeenCalledWith(expect.objectContaining({ provisional_registration_id: 81, target_case_no: 'ORD-086', reason: '已核對姓名用字差異' }), expect.any(Object)); expect(document.body.textContent).not.toContain('0912345382');
  });
  it('loading 或錯誤不偽裝成零筆；合法空清單有明確狀態', async () => {
    const api = client(); api.listBindings.mockRejectedValueOnce(new Error('private SQL')).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    render(<LineIdentityWorkbench client={api} />); expect(screen.getByRole('status')).toHaveTextContent('正在載入'); await screen.findByRole('alert'); expect(screen.queryByText('目前沒有身分綁定紀錄')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新整理' })); await screen.findByText('目前沒有身分綁定紀錄'); expect(document.body.textContent).not.toContain('private SQL');
  });
  it('鍵盤可切換工作分頁', async () => {
    render(<LineIdentityWorkbench client={client()} />); const tab = screen.getByRole('tab', { name: '身分綁定' }); tab.focus(); fireEvent.keyDown(tab, { key: 'ArrowRight' }); expect(screen.getByRole('tab', { name: /待審核/ })).toHaveFocus(); expect(screen.getByRole('tab', { name: /待審核/ })).toHaveAttribute('aria-selected', 'true'); await screen.findByText(review.display_name);
  });
});

it('typed client 將角色參數送到實際明細與 mutation 路徑，候選查詢維持 GET', async () => {
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-session');
  const envelope = (data: unknown) => ({ success: true, message: 'ok', data, error: null });
  const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(binding));
  await lineIdentityClient.getBinding(binding.line_user_id, { subjectType: 'customer' }); expect(get).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ params: { subject_type: 'customer' } }));
  const post = vi.spyOn(transport, 'post').mockResolvedValue(envelope(REVOCATION_PREVIEW_FIXTURE)); await lineIdentityClient.previewRevocation(binding.line_user_id, { subjectType: 'customer' }); expect(post).toHaveBeenLastCalledWith(expect.any(String), undefined, expect.objectContaining({ params: { subject_type: 'customer' } }));
  post.mockResolvedValue(envelope(REVOCATION_REQUEST_FIXTURE)); await lineIdentityClient.applyRevocation(binding.line_user_id, { expected_version: 7, reason: '確認解除', idempotency_key: 'test-key', correlation_id: 'test-correlation' }, { subjectType: 'customer' }); expect(post).toHaveBeenLastCalledWith(expect.stringContaining('/revocation/apply'), expect.objectContaining({ expected_version: 7 }), expect.objectContaining({ params: { subject_type: 'customer' } }));
  get.mockResolvedValue(envelope({ items: [candidate], total: 1, page: 1, page_size: 25 })); await lineIdentityClient.listReplacementCandidates!({ subject_type: 'customer', search: '客戶' }); expect(get).toHaveBeenLastCalledWith('/api/v1/line/identity-bindings/replacement-candidates', expect.objectContaining({ params: { subject_type: 'customer', search: '客戶' } }));
});
