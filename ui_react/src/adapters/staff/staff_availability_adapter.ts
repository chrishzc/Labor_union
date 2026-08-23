/**
 * File: staff_availability_adapter.ts
 * Description: 映射 Availability server view，保留日期與 blocker 原值且不做業務推導。
 */
import type {
  StaffAvailabilityAction,
  StaffAvailabilityPreview,
  StaffAvailabilityReceipt,
  StaffUnavailabilityBlock,
} from '../../api/staff_availability/staff_availability_schemas';

export const STAFF_AVAILABILITY_UI_ACTIONS = [
  'create_long_leave',
  'create_pause',
  'end_pause',
  'cancel',
] as const;

export type StaffAvailabilityUiAction = (typeof STAFF_AVAILABILITY_UI_ACTIONS)[number];

export interface StaffAvailabilityBlockViewModel {
  blockId: number;
  staffId: number;
  kind: StaffUnavailabilityBlock['kind'];
  kindLabel: string;
  startDate: string;
  endDate: string | null;
  displayEndDate: string;
  status: StaffUnavailabilityBlock['status'];
  statusLabel: string;
  reason: string;
  durationDays: null;
  durationLabel: string;
}

export interface StaffAvailabilityPreviewViewModel {
  staffId: number;
  action: StaffAvailabilityAction;
  actionSupportedByUi: boolean;
  sourceVersion: number;
  targetBlock: StaffAvailabilityBlockViewModel | null;
  candidateKind: StaffAvailabilityPreview['candidate_kind'];
  candidateStartDate: StaffAvailabilityPreview['candidate_start_date'];
  candidateEndDate: StaffAvailabilityPreview['candidate_end_date'];
  blockers: readonly string[];
  canApply: boolean;
  previewFingerprint: string;
  durationDays: null;
  durationLabel: string;
}

export interface StaffAvailabilityReceiptViewModel {
  staffId: number;
  action: StaffAvailabilityAction;
  block: StaffAvailabilityBlockViewModel;
  aggregateVersion: number;
  previewFingerprint: string;
  idempotencyKey: string;
}

function kindLabel(kind: StaffUnavailabilityBlock['kind']): string {
  switch (kind) {
    case 'long_leave':
      return '長假';
    case 'paused_service':
      return '暫停接案';
  }
}

function statusLabel(status: StaffUnavailabilityBlock['status']): string {
  switch (status) {
    case 'effective':
      return '生效中';
    case 'cancelled':
      return '已取消';
  }
}

export function isStaffAvailabilityUiAction(
  action: StaffAvailabilityAction
): action is StaffAvailabilityUiAction {
  return STAFF_AVAILABILITY_UI_ACTIONS.some((candidate) => candidate === action);
}

export function adaptStaffAvailabilityBlock(
  block: StaffUnavailabilityBlock
): StaffAvailabilityBlockViewModel {
  return {
    blockId: block.block_id,
    staffId: block.staff_id,
    kind: block.kind,
    kindLabel: kindLabel(block.kind),
    startDate: block.start_date,
    endDate: block.end_date,
    displayEndDate: block.end_date ?? '—',
    status: block.status,
    statusLabel: statusLabel(block.status),
    reason: block.reason,
    durationDays: null,
    durationLabel: '—',
  };
}

export function adaptStaffAvailabilityBlocks(
  blocks: readonly StaffUnavailabilityBlock[]
): StaffAvailabilityBlockViewModel[] {
  return blocks.map(adaptStaffAvailabilityBlock);
}

export function adaptStaffAvailabilityPreview(
  preview: StaffAvailabilityPreview
): StaffAvailabilityPreviewViewModel {
  return {
    staffId: preview.staff_id,
    action: preview.action,
    actionSupportedByUi: isStaffAvailabilityUiAction(preview.action),
    sourceVersion: preview.source_version,
    targetBlock: preview.target_block ? adaptStaffAvailabilityBlock(preview.target_block) : null,
    candidateKind: preview.candidate_kind,
    candidateStartDate: preview.candidate_start_date,
    candidateEndDate: preview.candidate_end_date,
    blockers: preview.blockers,
    canApply: preview.can_apply,
    previewFingerprint: preview.preview_fingerprint,
    durationDays: null,
    durationLabel: '—',
  };
}

export function adaptStaffAvailabilityReceipt(
  receipt: StaffAvailabilityReceipt
): StaffAvailabilityReceiptViewModel {
  return {
    staffId: receipt.staff_id,
    action: receipt.action,
    block: adaptStaffAvailabilityBlock(receipt.block),
    aggregateVersion: receipt.aggregate_version,
    previewFingerprint: receipt.preview_fingerprint,
    idempotencyKey: receipt.idempotency_key,
  };
}

export const adaptAvailabilityBlock = adaptStaffAvailabilityBlock;
export const adaptAvailabilityBlocks = adaptStaffAvailabilityBlocks;
export const adaptAvailabilityPreview = adaptStaffAvailabilityPreview;
export const adaptAvailabilityReceipt = adaptStaffAvailabilityReceipt;
