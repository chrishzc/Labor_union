/**
 * File: staff_directory_adapter.ts
 * Description: 將 Staff 摘要三欄轉成名冊卡片 view model，缺少的主檔欄位一律標示 unavailable。
 */
import type {
  StaffDirectoryPage,
  StaffDirectorySummary,
} from '../../api/staff_directory/staff_directory_schemas';

export const STAFF_DIRECTORY_UNAVAILABLE = '後端尚未提供 typed contract';

export interface StaffDirectoryCardViewModel {
  id: number;
  name: string | null;
  phone: string | null;
  displayName: string;
  displayPhone: string;
}

export interface StaffDirectoryPageViewModel {
  items: StaffDirectoryCardViewModel[];
  nextCursor: number | null;
}

export function adaptStaffDirectorySummary(summary: StaffDirectorySummary): StaffDirectoryCardViewModel {
  return {
    id: summary.id,
    name: summary.name,
    phone: summary.phone,
    displayName: summary.name ?? `服務人員摘要 #${summary.id}`,
    displayPhone: summary.phone ?? '後端未提供',
  };
}

export function adaptStaffDirectoryPage(page: StaffDirectoryPage): StaffDirectoryPageViewModel {
  return {
    items: page.items.map(adaptStaffDirectorySummary),
    nextCursor: page.next_cursor,
  };
}

