/**
 * File: staff_directory_no_fake_mutation.test.tsx
 * Description: 驗證 Staff 不呈現無契約控制，合法動作保留輸入鎖且不觸發假變更。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { StaffPage } from '../pages/StaffPage';
import { STAFF_PAGE_ONE } from './fixtures/staff/staff_directory_contract_fixtures';

describe('StaffPage zero fake mutation', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
  });

  it('removes unsupported mutations while supported actions remain input-gated', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(document.querySelector('[data-control-id="staff.master.create"]')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '辦理退役／復職' })[0]).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    for (const id of [
      'staff.preferences.preview',
      'staff.preferences.apply',
    ]) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeDisabled();
    }
    expect(document.querySelector('[data-control-id="staff.preferences.cooking-skills"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="staff.preferences.special-notes"]')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    for (const id of [
      'staff.availability.create.preview',
      'staff.availability.create.apply',
      'staff.availability.cancel.apply',
      'staff.availability.end-pause',
      'staff.availability.end-pause.apply',
    ]) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeDisabled();
    }
    fireEvent.click(screen.getByRole('button', { name: /服務月嫂名冊/ }));
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);

    const unsupportedIds = [
      'staff.master.save',
      'staff.master.edit',
      'staff.master.attachment-upload',
      'staff.master.bank-edit',
      'staff.master.certificate-approve',
    ];
    for (const id of unsupportedIds) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).not.toBeInTheDocument();
    }
    for (const id of ['staff.lifecycle.retirement.preview', 'staff.lifecycle.reactivation.preview', 'staff.lifecycle.reactivation.apply']) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeDisabled();
    }
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
  });
});
