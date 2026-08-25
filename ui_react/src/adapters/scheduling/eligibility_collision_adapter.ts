/**
 * File: eligibility_collision_adapter.ts
 * Description: 將 Scheduling 資格衝突 projection 映射為不推定的 UI view model。
 */
import type {
  SchedulingCollision,
  SchedulingEligibilityCollisionProjection,
  SchedulingQualificationCheck,
  SchedulingStaffEligibilityCollision,
} from '../../api/scheduling/eligibility_collision_schemas';

export interface SchedulingEligibilityCollisionViewModel {
  caseNo: string;
  caseStatus: string;
  asOf: string;
  evaluatedAt: string;
  schedulingVersion: number | null;
  staffId: number;
  eligibility: SchedulingStaffEligibilityCollision['eligibility'];
  availability: SchedulingStaffEligibilityCollision['availability'];
  eligibilityLabel: string;
  availabilityLabel: string;
  qualificationChecks: SchedulingQualificationCheck[];
  collisions: SchedulingCollision[];
  collisionCount: number;
  coverage: SchedulingStaffEligibilityCollision['coverage'];
  partialData: string[];
  dataNote: string | null;
}

const ELIGIBILITY_LABELS: Record<SchedulingStaffEligibilityCollision['eligibility'], string> = {
  eligible: '資格符合',
  ineligible: '資格不符合',
  partial: '資格資料不完整',
  unavailable: '資格不可用',
};

const AVAILABILITY_LABELS: Record<SchedulingStaffEligibilityCollision['availability'], string> = {
  available: '檔期可用',
  blocked: '檔期衝突阻擋',
  requires_review: '檔期需人工確認',
  unknown: '檔期無法判定',
};

const PARTIAL_DATA_LABELS: Record<string, string> = {
  assignment_interval_missing_or_invalid: '既有指派期間不完整',
  buffer_date_missing_or_invalid: '既有防撞期日期不完整',
  case_cooking_requirement_missing: '案件下廚需求尚未登錄',
  case_location_missing: '案件服務地點尚未登錄',
  schedule_date_missing_or_invalid: '正式服務日資料不完整',
  service_time_terms_incomplete: '每日服務時段尚未完整',
  staff_cooking_skills_missing: '月嫂料理能力尚未登錄',
  staff_regions_missing: '月嫂服務區域尚未登錄',
  staff_unavailability_interval_missing_or_invalid: '不可服務期間資料不完整',
  waiting_lock_date_missing_or_invalid: '待定金案件的服務日資料不完整',
};

function partialDataLabel(value: string): string {
  if (PARTIAL_DATA_LABELS[value]) return PARTIAL_DATA_LABELS[value];
  if (value.startsWith('case_preferred_service_days')) return '案件正式服務日尚未完整';
  if (value.startsWith('case_daily_service_hours')) return '案件每日工時尚未完整';
  if (value.startsWith('staff_preferred_service_days')) return '月嫂可接服務天數尚未登錄';
  if (value.startsWith('staff_daily_service_hours')) return '月嫂可接每日工時尚未登錄';
  return '媒合所需資料尚未完整';
}

function hasWp85Identity(value: string | null | undefined): boolean {
  return typeof value === 'string' && /wp85/i.test(value);
}

function dataNote(
  projection: SchedulingEligibilityCollisionProjection,
  staff: SchedulingStaffEligibilityCollision
): string | null {
  const values = [projection.case_no, ...staff.collisions.flatMap((item) => [item.case_no, item.source_identity])];
  if (values.some(hasWp85Identity)) return '此案含非正式驗證資料，系統未判定為可排班，請人工確認。';
  const partial = [...projection.partial_data, ...staff.partial_data];
  if (partial.length > 0) {
    const labels = [...new Set(partial.map(partialDataLabel))];
    return `需補齊：${labels.join('、')}；補齊後再查詢。`;
  }
  if (staff.coverage.status === 'unavailable') return '服務日期覆蓋尚待建立，未推定可用性。';
  return null;
}

export function adaptSchedulingEligibilityCollision(
  projection: SchedulingEligibilityCollisionProjection
): SchedulingEligibilityCollisionViewModel {
  const staff = projection.staff[0];
  if (!staff) throw new Error('資格衝突 projection 缺少選定 staff。');
  return {
    caseNo: projection.case_no,
    caseStatus: projection.case_status,
    asOf: projection.as_of,
    evaluatedAt: projection.evaluated_at,
    schedulingVersion: projection.scheduling_version,
    staffId: staff.staff_id,
    eligibility: staff.eligibility,
    availability: staff.availability,
    eligibilityLabel: ELIGIBILITY_LABELS[staff.eligibility],
    availabilityLabel: AVAILABILITY_LABELS[staff.availability],
    qualificationChecks: staff.qualification_checks,
    collisions: staff.collisions,
    collisionCount: staff.collisions.length,
    coverage: staff.coverage,
    partialData: [...new Set([...projection.partial_data, ...staff.partial_data])],
    dataNote: dataNote(projection, staff),
  };
}
