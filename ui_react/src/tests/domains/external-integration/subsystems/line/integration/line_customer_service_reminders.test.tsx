import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import { BINDING_PAGE_FIXTURE } from '../../../../../fixtures/line_identity/line_identity_contract_fixtures';

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, '', '/');
});

it('舊客服紀錄連結回到身分與授權，頁面無查閱入口也不查詢客服工單', async () => {
  window.history.replaceState(null, '', '#line-management?tab=tickets');
  const fetch = vi.spyOn(window, 'fetch').mockRejectedValue(new Error('unexpected network request'));
  const listBindings = vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE);

  render(<LineManagementPage lineIdentity={{ listBindings }} />);

  await screen.findByText('測試客戶甲');
  expect(screen.getByRole('button', { name: '身分與授權' })).toHaveAttribute('aria-current', 'page');
  expect(screen.queryByRole('button', { name: '查閱歷史客服紀錄' })).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '歷史客服紀錄' })).not.toBeInTheDocument();
  expect(fetch.mock.calls.map(([url]) => String(url))).not.toEqual(expect.arrayContaining([
    expect.stringContaining('/api/v1/customer-service/'),
  ]));
});
