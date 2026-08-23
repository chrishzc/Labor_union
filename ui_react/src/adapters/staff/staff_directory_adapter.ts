/**
 * File: staff_directory_adapter.ts
 * Description: 將 Staff 摘要三欄轉成名冊卡片 view model，合法 null 採中性顯示。
 */
import type {
  StaffDirectoryPage,
  StaffDirectorySummary,
} from '../../api/staff_directory/staff_directory_schemas';

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
    displayPhone: summary.phone ?? '—',
  };
}

export function adaptStaffDirectoryPage(page: StaffDirectoryPage): StaffDirectoryPageViewModel {
  return {
    items: page.items.map(adaptStaffDirectorySummary),
    nextCursor: page.next_cursor,
  };
}
