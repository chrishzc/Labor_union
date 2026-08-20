/**
 * File: staff_directory_no_fake_mutation.test.tsx
 * Description: 驗證 Staff query slice 的未核准控制皆 native disabled，且不觸發假變更或網路。
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

  it('keeps every visible mutation control natively disabled', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    for (const id of ['staff.master.create', 'staff.lifecycle.retirement.apply']) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeDisabled();
    }

    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    for (const id of [
      'staff.preferences.preview',
      'staff.preferences.apply',
      'staff.preferences.cooking-skills',
      'staff.preferences.special-notes',
    ]) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeDisabled();
    }

    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    for (const id of [
      'staff.availability.create.preview',
      'staff.availability.create.apply',
      'staff.availability.cancel.preview',
      'staff.availability.cancel.apply',
      'staff.availability.end-pause',
    ]) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeDisabled();
    }

    fireEvent.click(screen.getByRole('button', { name: /服務月嫂名冊/ }));
    fireEvent.click(screen.getAllByRole('button', { name: /檢視摘要/ })[0]);

    const mutationIds = [
      'staff.master.save',
      'staff.master.edit',
      'staff.master.attachment-upload',
      'staff.master.bank-edit',
      'staff.master.certificate-approve',
      'staff.lifecycle.retirement.preview',
      'staff.lifecycle.reactivation.preview',
      'staff.lifecycle.reactivation.apply',
    ];
    for (const id of mutationIds) {
      const control = document.querySelector(`[data-control-id="${id}"]`);
      expect(control).toBeTruthy();
      expect(control).toBeDisabled();
    }
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
  });
});
