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

const SECTION_AVAILABILITY_LABELS: Record<StaffQualificationAvailability, string> = {
  available: '已登錄',
  unavailable: '尚無登錄資料',
  unknown: '資料狀態待確認',
  partial: '部分登錄',
};

const OVERALL_AVAILABILITY_LABELS: Record<StaffQualificationAvailability, string> = {
  available: '目前無有效不可服務期間',
  unavailable: '目前不可服務',
  unknown: '可服務狀態待確認',
  partial: '部分資料待確認',
};

function sectionAvailabilityLabel(section: StaffQualificationSection): string {
  if (section.items.length === 0 && section.availability === 'available') {
    return section.kind === 'unavailability' ? '目前無不可服務期間' : '尚未登錄';
  }
  return SECTION_AVAILABILITY_LABELS[section.availability];
}

function displayValue(value: string | boolean | null): string {
  if (value === null) return '尚無登錄值';
  if (typeof value === 'boolean') return value ? '是' : '否';
  return value;
}

function sectionNote(section: StaffQualificationSection): string | null {
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
    availabilityLabel: sectionAvailabilityLabel(section),
    dataNote: sectionNote(section),
  }));
  const official = sections.find((section) => section.kind === 'medical' || section.kind === 'validity');
  return {
    ...master,
    sections,
    overallAvailabilityLabel: OVERALL_AVAILABILITY_LABELS[master.overall_availability],
    officialDataNote: official?.dataNote ?? null,
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
