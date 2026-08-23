/**
 * File: qualification_master_adapter.ts
 * Description: 將 Staff qualification 六區段映射為固定可見且不洩漏內部原因碼的 UI view。
 */
import type {
  StaffQualificationAvailability,
  StaffQualificationFact,
  StaffQualificationMaster,
  StaffQualificationSection,
} from '../../api/staff/qualification_master_schemas';

export interface StaffQualificationFactViewModel extends StaffQualificationFact {
  displayValue: string;
}

export interface StaffQualificationSectionViewModel extends Omit<StaffQualificationSection, 'items'> {
  items: StaffQualificationFactViewModel[];
  availabilityLabel: string;
  dataNote: string | null;
}

export interface StaffQualificationMasterViewModel extends Omit<StaffQualificationMaster, 'sections'> {
  sections: StaffQualificationSectionViewModel[];
  overallAvailabilityLabel: string;
  officialDataNote: string | null;
}

const AVAILABILITY_LABELS: Record<StaffQualificationAvailability, string> = {
  available: '已登錄',
  unavailable: '尚無登錄資料',
  unknown: '資料狀態待確認',
  partial: '部分登錄',
};

function displayValue(value: string | boolean | null): string {
  if (value === null) return '尚無登錄值';
  if (typeof value === 'boolean') return value ? '是' : '否';
  return value;
}

function hasWp85Identity(value: string | null | undefined): boolean {
  return typeof value === 'string' && /wp85/i.test(value);
}

function sectionNote(section: StaffQualificationSection): string | null {
  if (hasWp85Identity(section.source_identity) || section.items.some((item) => hasWp85Identity(item.source_identity))) {
    return '測試資料污染：含 wp85 identity，未視為正式資格。';
  }
  if (section.kind === 'medical' || section.kind === 'validity') {
    if (section.availability !== 'available') return '正式資料尚無登錄，未推定通過或有效。';
  }
  if (section.availability !== 'available') return '此區段目前沒有完整的已登錄資料。';
  return null;
}

export function adaptStaffQualificationMaster(master: StaffQualificationMaster): StaffQualificationMasterViewModel {
  const sections = master.sections.map((section) => ({
    ...section,
    items: section.items.map((item) => ({ ...item, displayValue: displayValue(item.value) })),
    availabilityLabel: AVAILABILITY_LABELS[section.availability],
    dataNote: sectionNote(section),
  }));
  const official = sections.find((section) => section.kind === 'medical' || section.kind === 'validity');
  const contaminated = sections.some((section) => section.dataNote?.includes('wp85')) || hasWp85Identity(master.staff_name);
  return {
    ...master,
    sections,
    overallAvailabilityLabel: AVAILABILITY_LABELS[master.overall_availability],
    officialDataNote: contaminated
      ? '測試資料污染：qualification master 含 wp85 測試 identity，未推定正式資格。'
      : official?.dataNote ?? null,
  };
}

export function findStaffQualificationSection(
  master: StaffQualificationMasterViewModel,
  kind: StaffQualificationSection['kind']
): StaffQualificationSectionViewModel {
  const section = master.sections.find((item) => item.kind === kind);
  if (!section) throw new Error(`缺少 qualification section：${kind}`);
  return section;
}
