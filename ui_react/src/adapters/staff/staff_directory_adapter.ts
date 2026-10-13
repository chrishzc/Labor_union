/**
 * File: staff_directory_adapter.ts
 * Description: 將 Staff bounded 摘要轉成名冊 view model，合法 null 採中性顯示。
 */
import type {
  StaffRosterServiceProfile,
  StaffDirectoryPage,
  StaffDirectorySummary,
} from '../../api/staff_directory/staff_directory_schemas';
import type { StaffProfile } from '../../api/staff_profile/staff_profile_schemas';

export interface StaffDirectoryCardViewModel {
  id: number;
  unionNo: string | null;
  profile?: StaffProfile;
  serviceProfile?: StaffRosterServiceProfile;
  name: string | null;
  phone: string | null;
  education: string | null;
  displayName: string;
  displayPhone: string;
  displayEducation: string;
}

export interface StaffDirectoryPageViewModel {
  items: StaffDirectoryCardViewModel[];
  nextCursor: number | null;
}

export function adaptStaffDirectorySummary(summary: StaffDirectorySummary): StaffDirectoryCardViewModel {
  const displayEducation = summary.education ?? '—';
  return {
    id: summary.id,
    unionNo: summary.union_no ?? null,
    ...(summary.profile ? { profile: summary.profile } : {}),
    ...(summary.service_profile ? { serviceProfile: summary.service_profile } : {}),
    name: summary.name,
    phone: summary.phone,
    education: summary.education,
    displayName: summary.name ?? `服務人員摘要 #${summary.id}`,
    displayPhone: `${summary.phone ?? '—'} ｜ 學歷：${displayEducation}`,
    displayEducation,
  };
}

export function adaptStaffDirectoryPage(page: StaffDirectoryPage): StaffDirectoryPageViewModel {
  return {
    items: page.items.map(adaptStaffDirectorySummary),
    nextCursor: page.next_cursor,
  };
}
