/** Verify canonical lifecycle filtering, tab isolation and post-save roster membership. */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffPage } from '../../../../../../../pages/StaffPage';
import { staffDirectoryClient, loadAllStaffDirectoryPages } from '../../../../../../../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { staffQualificationMasterClient } from '../../../../../../../api/staff/qualification_master_client';
import { STAFF_PAGE_ONE } from '../../../../../../fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW, STAFF_LIFECYCLE_PREVIEW, STAFF_LIFECYCLE_RECEIPT } from '../../../../../../fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from '../../../../../../fixtures/staff/staff_qualification_contract_fixtures';

const activePage = { items: [STAFF_PAGE_ONE.items[0]], next_cursor: null };
const retiredPage = { items: [{ ...STAFF_PAGE_ONE.items[0], id: 13, name: '去敏退役人員' }], next_cursor: null };

describe('Staff roster lifecycle tabs', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockImplementation(async (params) => (
      params?.lifecycleState === 'retired' ? retiredPage : activePage
    ));
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
  });
  afterEach(() => vi.restoreAllMocks());

  it('defaults to active staff and keeps searches within the selected retired tab', async () => {
    render(<StaffPage />);
    expect(await screen.findByText('去敏人員甲')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '現役月嫂' })).toHaveAttribute('aria-selected', 'true');
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledWith(
      expect.objectContaining({ includeProfile: true, lifecycleState: 'active' }), expect.anything(),
    );
    fireEvent.click(screen.getByRole('tab', { name: '已退役月嫂' }));
    expect(await screen.findByText('去敏退役人員')).toBeInTheDocument();
    expect(screen.queryByText('去敏人員甲')).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: '即時搜尋月嫂' }), { target: { value: '退役' } });
    await waitFor(() => expect(screen.getByRole('status', { name: '' })).toHaveTextContent('搜尋結果 1 位服務人員'));
    expect(vi.mocked(staffDirectoryClient.queryPage).mock.calls.at(-1)?.[0]?.lifecycleState).toBe('retired');
    const selected = screen.getByRole('tab', { name: '已退役月嫂' });
    fireEvent.keyDown(selected, { key: 'Home' });
    await waitFor(() => expect(screen.getByRole('tab', { name: '現役月嫂' })).toHaveAttribute('aria-selected', 'true'));
    expect(screen.queryByText('去敏退役人員')).not.toBeInTheDocument();
  });

  it('ignores a previous tab response arriving after the retired tab loaded', async () => {
    let resolveActive!: (value: typeof activePage) => void;
    vi.mocked(staffDirectoryClient.queryPage).mockImplementation((params) => params?.lifecycleState === 'active'
      ? new Promise((resolve) => { resolveActive = resolve; })
      : Promise.resolve(retiredPage));
    render(<StaffPage />);
    fireEvent.click(screen.getByRole('tab', { name: '已退役月嫂' }));
    expect(await screen.findByText('去敏退役人員')).toBeInTheDocument();
    await act(async () => resolveActive(activePage));
    expect(screen.queryByText('去敏人員甲')).not.toBeInTheDocument();
    expect(screen.getByText('去敏退役人員')).toBeInTheDocument();
  });

  it('preserves the lifecycle filter on every bounded cursor page', async () => {
    const query = vi.fn().mockResolvedValueOnce({ ...activePage, next_cursor: 11 }).mockResolvedValueOnce(retiredPage);
    await loadAllStaffDirectoryPages(query, { includeProfile: true, lifecycleState: 'retired' });
    expect(query.mock.calls[0][0]).toMatchObject({ lifecycleState: 'retired' });
    expect(query.mock.calls[1][0]).toMatchObject({ lifecycleState: 'retired', afterId: 11 });
  });

  it.each(['retirement', 'reactivation'] as const)('%s removes staff from the old tab only after authoritative readback', async (action) => {
    const before = action === 'retirement' ? 'active' : 'retired';
    const after = action === 'retirement' ? 'retired' : 'active';
    vi.mocked(staffDirectoryClient.queryPage).mockResolvedValue(activePage);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue({ ...STAFF_LIFECYCLE_VIEW, state: after, version: 3 })
      .mockResolvedValueOnce({ ...STAFF_LIFECYCLE_VIEW, state: before })
      .mockResolvedValueOnce({ ...STAFF_LIFECYCLE_VIEW, state: after, version: 3 });
    vi.spyOn(staffLifecycleClient, 'preview').mockResolvedValue({ ...STAFF_LIFECYCLE_PREVIEW, state: before, after_state: after });
    vi.spyOn(staffLifecycleClient, 'apply').mockResolvedValue({ ...STAFF_LIFECYCLE_RECEIPT, state: after });
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
    render(<StaffPage />);
    if (before === 'retired') fireEvent.click(screen.getByRole('tab', { name: '已退役月嫂' }));
    const row = await screen.findByText('去敏人員甲');
    fireEvent.click(row);
    fireEvent.click(await screen.findByRole('button', { name: /辦理(退役|復職)登記/ }));
    fireEvent.change(screen.getByLabelText('生效日期'), { target: { value: '2026-08-15' } });
    fireEvent.click(screen.getByRole('button', { name: action === 'retirement' ? /^辦理退役$/ : /^辦理復職$/ }));
    expect(await screen.findByText('已確認最新任職狀態')).toBeInTheDocument();
    expect(within(screen.getByRole('tabpanel')).queryByText('去敏人員甲')).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: before === 'active' ? '現役月嫂' : '已退役月嫂' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    fireEvent.click(screen.getByRole('tab', { name: after === 'active' ? '現役月嫂' : '已退役月嫂' }));
    fireEvent.click(await screen.findByText('去敏人員甲'));
    fireEvent.click(await screen.findByRole('button', { name: /辦理(退役|復職)登記/ }));
    expect(screen.getByRole('button', { name: after === 'active' ? /^辦理退役$/ : /^辦理復職$/ })).toBeVisible();
  });
});
