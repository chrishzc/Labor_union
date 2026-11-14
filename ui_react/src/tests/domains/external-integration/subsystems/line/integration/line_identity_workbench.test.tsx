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
async function openRevocation() {
  fireEvent.click(await screen.findByRole('button', { name: '解除綁定' }));
  return screen.findByRole('dialog', { name: '是否確認解除綁定？' });
}
async function confirmReason(label: string, reason: string) { fireEvent.change(screen.getByRole('textbox', { name: label }), { target: { value: reason } }); fireEvent.click(screen.getByRole('button', { name: '提交審核決定' })); expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); }
afterEach(() => { vi.restoreAllMocks(); window.history.replaceState(null, '', '/'); });

describe('身分與授權精簡工作區', () => {
  it('把同步操作放在狀態欄，解除中與已停用列都可永久刪除', async () => {
    const revoked = { ...staff, status: 'revoked' as const };
    const pending = { ...staff, line_user_id: 'U-pending', subject_name: '解除中月嫂', status: 'revocation_pending' as const };
    const api = {
      ...client([binding, revoked, pending]),
      resyncMenu: vi.fn(),
      deleteRevokedBinding: vi.fn().mockResolvedValue(undefined),
    };
    render(<LineIdentityWorkbench client={api} />);
    const sync = await screen.findByRole('button', { name: '重新同步選單' });
    expect(sync.closest('td')).toHaveAttribute('data-label', '狀態');
    expect(screen.getAllByRole('button', { name: '刪除停用資料' })).toHaveLength(2);
    const row = screen.getByRole('row', { name: /解除中月嫂/ });
    const button = within(row).getByRole('button', { name: '刪除停用資料' });
    fireEvent.click(button);
    const dialog = await screen.findByRole('dialog', { name: '永久刪除停用綁定資料？' });
    expect(api.deleteRevokedBinding).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: '永久刪除' }));
    await screen.findByText('已永久刪除停用綁定資料。');
    expect(api.deleteRevokedBinding).toHaveBeenCalledExactlyOnceWith(
      pending.line_user_id,
      { expected_version: pending.version, expected_updated_at: pending.updated_at, idempotency_key: expect.any(String) },
      expect.objectContaining({ subjectType: 'staff' }),
    );
  });

  it('對選單未切換的客戶排入單筆同步，並停用處理中的按鈕', async () => {
    const failed = { ...binding, rich_menu_sync_status: 'failed' as const };
    const pending = { ...binding, rich_menu_sync_status: 'pending' as const };
    const api = { ...client([failed]), resyncMenu: vi.fn().mockResolvedValue(pending) };
    api.listBindings.mockResolvedValueOnce({ items: [failed], total: 1, page: 1, page_size: 25 })
      .mockResolvedValue({ items: [pending], total: 1, page: 1, page_size: 25 });
    render(<LineIdentityWorkbench client={api} />);
    fireEvent.click(await screen.findByRole('button', { name: '重新同步選單' }));
    await screen.findByText('選單同步中');
    expect(api.resyncMenu).toHaveBeenCalledExactlyOnceWith(
      binding.line_user_id,
      { expected_version: binding.version, idempotency_key: expect.any(String) },
      expect.objectContaining({ subjectType: 'customer' }),
    );
    expect(await screen.findByRole('button', { name: '重新同步選單' })).toBeDisabled();
    expect(screen.queryByText('選單已同步')).toBeNull();
  });

  it('重新同步送到單筆角色限定的 API 並解碼受理狀態', async () => {
    const pending = { ...binding, rich_menu_sync_status: 'pending' as const };
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-session');
    const post = vi.spyOn(transport, 'post').mockResolvedValue({ success: true, data: pending, message: 'ok', error: null });
    const payload = { expected_version: binding.version, idempotency_key: 'test-resync' };
    await expect(lineIdentityClient.resyncMenu(binding.line_user_id, payload, { subjectType: 'customer' }))
      .resolves.toEqual(pending);
    expect(post).toHaveBeenCalledExactlyOnceWith(
      `/api/v1/line/identity-bindings/${binding.line_user_id}/menu/resync`,
      payload,
      expect.objectContaining({ params: { subject_type: 'customer' } }),
    );
  });

  it.each([
    ['pending', null, '選單同步中'],
    ['synced', null, '選單已同步'],
    ['failed', 'line_http_401', '選單同步失敗（LINE 憑證無效）'],
    ['unverified', null, '選單同步未確認'],
  ] as const)('分別顯示已綁定及選單 %s', async (status, errorCode, label) => {
    const api = client();
    api.listBindings.mockResolvedValue({
      items: [{ ...binding, rich_menu_sync_status: status, rich_menu_sync_error_code: errorCode }],
      total: 1, page: 1, page_size: 25,
    });
    render(<LineIdentityWorkbench client={api} />);
    const row = await screen.findByRole('row', { name: new RegExp(binding.subject_name) });
    expect(within(row).getByText('已綁定')).toBeInTheDocument();
    expect(within(row).getByText(label)).toBeInTheDocument();
    if (status !== 'synced') expect(within(row).queryByText('選單已同步')).toBeNull();
  });

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
  it('清單不提供更正或綁定明細抽屜', async () => {
    const api = client([binding, staff]);
    render(<LineIdentityWorkbench client={api} />);
    await screen.findByText(staff.subject_name, { exact: false });
    expect(screen.queryByRole('button', { name: '更正綁定對象' })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.getBinding).not.toHaveBeenCalled();
    expect(api.listReplacementCandidates).not.toHaveBeenCalled();
  });
  it('解除綁定在置中確認前零寫入，確認後只操作該身分且不需原因', async () => {
    const api = client();
    const pending: LineIdentityBindingView = { ...binding, status: 'revocation_pending', version: 8, revocation_status: 'pending_menu_reset', revocation_request_id: 901 };
    api.getBinding.mockResolvedValue(pending);
    api.listBindings.mockResolvedValueOnce({ items: [binding], total: 1, page: 1, page_size: 25 })
      .mockResolvedValue({ items: [pending], total: 1, page: 1, page_size: 25 });
    render(<LineIdentityWorkbench client={api} />);
    const dialog = await openRevocation();
    expect(within(dialog).getByText(binding.subject_name)).toBeInTheDocument();
    expect(within(dialog).getByText('客戶')).toBeInTheDocument();
    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument();
    expect(api.applyRevocation).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    expect(api.applyRevocation).not.toHaveBeenCalled();
    const reopened = await openRevocation();
    fireEvent.click(within(reopened).getByRole('button', { name: '確認解除綁定' }));
    await waitFor(() => expect(api.applyRevocation).toHaveBeenCalledWith(binding.line_user_id, expect.objectContaining({ expected_version: 7, reason: '' }), expect.objectContaining({ subjectType: 'customer' })));
    await waitFor(() => expect(screen.getByText('訪客選單回復中')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '修復訪客選單' })).not.toBeInTheDocument();
  });
  it('解除結果不明時先回讀，禁止重複提交', async () => {
    const api = client(); api.applyRevocation.mockRejectedValue(new LineIdentityClientError('TIMEOUT', 'private provider error', { outcomeUnknown: true }));
    render(<LineIdentityWorkbench client={api} />);
    fireEvent.click(within(await openRevocation()).getByRole('button', { name: '確認解除綁定' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: '解除綁定' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重新查詢綁定狀態' })).toBeEnabled();
    expect(document.body.textContent).not.toContain('private provider error');
  });
  it('失敗列直接修復訪客選單，不開啟抽屜或要求原因', async () => {
    const failed: LineIdentityBindingView = { ...binding, status: 'revocation_pending', version: 8, revocation_status: 'menu_reset_failed', revocation_request_id: 901 };
    const api = client([failed]); api.getBinding.mockResolvedValue(failed);
    render(<LineIdentityWorkbench client={api} />);
    fireEvent.click(await screen.findByRole('button', { name: '修復訪客選單' }));
    await waitFor(() => expect(api.retryRevocation).toHaveBeenCalledWith(901, { reason: '' }, expect.objectContaining({ subjectType: 'customer' })));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(api.applyRevocation).not.toHaveBeenCalled();
  });
  it('待審核不預選核准，通過正式 Preview／Apply 後自動查回審核結果', async () => {
    const api = client(); api.getReview.mockResolvedValueOnce(review).mockResolvedValue({ ...review, status: 'approved', version: 4 });
    render(<LineIdentityWorkbench client={api} />); fireEvent.click(screen.getByRole('tab', { name: /待審核/ })); fireEvent.click(await screen.findByRole('button', { name: '審核審核對象甲的綁定申請' }));
    await screen.findByRole('radio', { name: '核准' }); expect(screen.getByRole('radio', { name: '核准' })).not.toBeChecked(); expect(screen.getByRole('button', { name: '提交審核決定' })).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: '核准' })); await confirmReason('審核原因（選填）', '已核對原帳號與新申請'); expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: '確認核准' })).not.toBeInTheDocument();
    await screen.findByText('已核准'); expect(api.getReview).toHaveBeenCalledTimes(2); expect(api.applyReviewDecision).toHaveBeenCalledWith(71, 'approve', expect.objectContaining({ expected_version: 3, preview_fingerprint: 'private-preview-fingerprint' }), expect.any(Object));
    expect(document.body.textContent).not.toContain('private-preview-fingerprint'); expect(document.body.textContent).not.toContain(review.line_user_id);
  });
  it('先選登記再選訂單，一次提交配對並沿用原 writer 與差異資訊', async () => {
    const api = client(); api.listUnboundCandidates.mockResolvedValueOnce(paired).mockResolvedValue({ ...paired, provisional_registrations: [] });
    render(<LineIdentityWorkbench client={api} />); fireEvent.click(screen.getByRole('tab', { name: '待配對' })); fireEvent.click(await screen.findByRole('button', { name: '為邱佩瑜尋找對應訂單' }));
    fireEvent.click(await screen.findByRole('button', { name: '選擇邱珮瑜的訂單' })); expect(screen.getByText(/兩側姓名有差異/)).toBeInTheDocument(); expect(screen.getByRole('button', { name: '配對並綁定' })).toBeEnabled(); expect(api.pairProvisionalRegistration).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('textbox', { name: '配對原因（選填）' }), { target: { value: '已核對姓名用字差異' } }); expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); fireEvent.click(screen.getByRole('button', { name: '配對並綁定' }));
    await screen.findByText('目前沒有待配對登記'); expect(api.pairProvisionalRegistration).toHaveBeenCalledWith(expect.objectContaining({ provisional_registration_id: 81, target_case_no: 'ORD-086', reason: '已核對姓名用字差異' }), expect.any(Object)); expect(document.body.textContent).not.toContain('0912345382');
  });
  it('確認後刪除待審核申請，重新讀取清單', async () => {
    const api = { ...client(), deletePendingReview: vi.fn().mockResolvedValue(undefined) };
    render(<LineIdentityWorkbench client={api} />);
    fireEvent.click(screen.getByRole('tab', { name: /待審核/ }));
    fireEvent.click(await screen.findByRole('button', { name: '刪除審核對象甲的待審核申請' }));
    expect(api.deletePendingReview).not.toHaveBeenCalled();
    api.listReviews.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25, pending_total: 0 });
    fireEvent.click(screen.getByRole('button', { name: '永久刪除' }));
    await screen.findByText('目前沒有待審核申請');
    expect(api.deletePendingReview).toHaveBeenCalledWith(71, { expected_version: 3, idempotency_key: expect.any(String) });
    expect(api.applyReviewDecision).not.toHaveBeenCalled();
  });
  it('確認後刪除待配對登記，重新讀取清單', async () => {
    const api = { ...client(), deletePendingPairing: vi.fn().mockResolvedValue(undefined) };
    api.listUnboundCandidates
      .mockResolvedValueOnce({ ...paired, provisional_registrations: [{ ...paired.provisional_registrations[0], version: 2 }] })
      .mockResolvedValue({ ...paired, provisional_registrations: [] });
    render(<LineIdentityWorkbench client={api} />);
    fireEvent.click(screen.getByRole('tab', { name: '待配對' }));
    fireEvent.click(await screen.findByRole('button', { name: '刪除邱佩瑜的待配對登記' }));
    expect(api.deletePendingPairing).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '永久刪除' }));
    await screen.findByText('目前沒有待配對登記');
    expect(api.deletePendingPairing).toHaveBeenCalledWith(81, { expected_version: 2, idempotency_key: expect.any(String) });
    expect(api.pairProvisionalRegistration).not.toHaveBeenCalled();
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
