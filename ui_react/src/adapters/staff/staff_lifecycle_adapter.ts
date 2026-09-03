/**
 * File: staff_lifecycle_adapter.ts
 * Description: 映射 Staff lifecycle server view，依 state 呈現狀態且不恢復舊事實。
 */
import type {
  StaffLifecycleAction,
  StaffLifecycleApplyReceipt,
  StaffLifecyclePreview,
  StaffLifecycleState,
  StaffLifecycleView,
} from '../../api/staff_lifecycle/staff_lifecycle_schemas';

export interface StaffLifecycleViewModel {
  staffId: number;
  state: StaffLifecycleState;
  stateLabel: string;
  version: number;
  effectiveAt: string | null;
  displayEffectiveAt: string;
  reasonCode: string | null;
  canRetire: boolean;
  canReactivate: boolean;
}

export interface StaffLifecyclePreviewViewModel extends StaffLifecycleViewModel {
  action: StaffLifecycleAction;
  afterState: StaffLifecycleState;
  afterStateLabel: string;
  previewFingerprint: string;
}

export interface StaffLifecycleReceiptViewModel {
  staffId: number;
  state: StaffLifecycleState;
  stateLabel: string;
  resultingVersion: number;
  previewFingerprint: string;
  idempotencyKey: string;
}

function stateLabel(state: StaffLifecycleState): string {
  switch (state) {
    case 'active':
      return '在職';
    case 'retired':
      return '已退役';
  }
}

function viewModel(view: StaffLifecycleView): StaffLifecycleViewModel {
  return {
    staffId: view.staff_id,
    state: view.state,
    stateLabel: stateLabel(view.state),
    version: view.version,
    effectiveAt: view.effective_at ?? null,
    displayEffectiveAt: view.effective_at ?? '—',
    reasonCode: view.reason_code ?? null,
    canRetire: view.state === 'active',
    canReactivate: view.state === 'retired',
  };
}

export function adaptStaffLifecycleView(view: StaffLifecycleView): StaffLifecycleViewModel {
  return viewModel(view);
}

export function adaptStaffLifecyclePreview(
  preview: StaffLifecyclePreview,
  action: StaffLifecycleAction
): StaffLifecyclePreviewViewModel {
  return {
    ...viewModel(preview),
    action,
    afterState: preview.after_state,
    afterStateLabel: stateLabel(preview.after_state),
    previewFingerprint: preview.preview_fingerprint,
  };
}

export function adaptStaffLifecycleReceipt(
  receipt: StaffLifecycleApplyReceipt
): StaffLifecycleReceiptViewModel {
  return {
    staffId: receipt.staff_id,
    state: receipt.state,
    stateLabel: stateLabel(receipt.state),
    resultingVersion: receipt.resulting_version,
    previewFingerprint: receipt.preview_fingerprint,
    idempotencyKey: receipt.idempotency_key,
  };
}

export const adaptLifecycleView = adaptStaffLifecycleView;
export const adaptLifecyclePreview = adaptStaffLifecyclePreview;
export const adaptLifecycleReceipt = adaptStaffLifecycleReceipt;
