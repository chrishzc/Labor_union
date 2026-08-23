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
  eligible: '資格符合（server）',
  ineligible: '資格不符合（server）',
  partial: '資格資料不完整',
  unavailable: '資格不可用',
};

const AVAILABILITY_LABELS: Record<SchedulingStaffEligibilityCollision['availability'], string> = {
  available: '檔期可用（server）',
  blocked: '檔期衝突阻擋（server）',
  requires_review: '檔期需人工確認',
  unknown: '檔期無法判定',
};

function hasWp85Identity(value: string | null | undefined): boolean {
  return typeof value === 'string' && /wp85/i.test(value);
}

function dataNote(
  projection: SchedulingEligibilityCollisionProjection,
  staff: SchedulingStaffEligibilityCollision
): string | null {
  const values = [projection.case_no, ...staff.collisions.flatMap((item) => [item.case_no, item.source_identity])];
  if (values.some(hasWp85Identity)) return '測試資料污染：此 projection 含 wp85 測試 identity，未將其推定為正式資格。';
  const partial = [...projection.partial_data, ...staff.partial_data];
  if (partial.length > 0) return `需補正資料：${[...new Set(partial)].join('、')}；補齊後再查詢。`;
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
