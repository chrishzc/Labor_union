/**
 * File: orders_mutation_flow_store.test.ts
 * Description: 驗證 Orders mutation Store 的冪等鍵、未決 payload 鎖定、receipt 保留與案件隔離。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  orderMutationFlowStore,
  generateIdempotencyKey,
} from '../adapters/orders/order_mutation_flow_store';
import {
  realisticServiceDateQueryView,
  realisticServiceDatePreviewView,
  realisticOrderReopenPreviewView,
  realisticOrderReopenReceiptView,
} from './fixtures/orders/order_mutation_contract_fixtures';
import {
  OrderMutationUnavailableError,
  OrderMutationConflictError,
} from '../api/orders/order_mutation_errors';

describe('OrderMutationFlowStore Unit Test Suite', () => {
  beforeEach(() => {
    orderMutationFlowStore.clearAll();
  });

  it('1. 產生的 Idempotency Key 必須為符合 RFC 4122 之有效 UUID 字串', () => {
    const key1 = generateIdempotencyKey();
    const key2 = generateIdempotencyKey();
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

    expect(key1).toMatch(uuidRegex);
    expect(key2).toMatch(uuidRegex);
    expect(key1).not.toBe(key2);
  });

  it('2. 純記憶體儲存：操作不得讀取或寫入 localStorage / sessionStorage / document.cookie', () => {
    const localSpyGet = vi.spyOn(Storage.prototype, 'getItem');
    const localSpySet = vi.spyOn(Storage.prototype, 'setItem');

    const draft = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-TEST1');
    orderMutationFlowStore.updateServiceDatesSelection('ORD-2026-TEST1', ['2026-09-01']);
    orderMutationFlowStore.setServiceDatesPreviewReady(
      'ORD-2026-TEST1',
      realisticServiceDatePreviewView
    );

    expect(draft.caseNo).toBe('ORD-2026-TEST1');
    expect(localSpyGet).not.toHaveBeenCalled();
    expect(localSpySet).not.toHaveBeenCalled();
  });

  it('3. 相同日期草稿重試時沿用相同 Idempotency-Key，修改日期則重置 Preview 並產生新 Key', () => {
    orderMutationFlowStore.setServiceDatesQueryReady(
      'ORD-2026-0801',
      realisticServiceDateQueryView
    );
    const initialDraft = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801');
    const key1 = initialDraft.idempotencyKey;

    orderMutationFlowStore.updateServiceDatesSelection('ORD-2026-0801', [
      '2026-09-01',
      '2026-09-02',
    ]);
    const key2 = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801').idempotencyKey;
    expect(key2).not.toBe(key1);

    orderMutationFlowStore.setServiceDatesPreviewReady(
      'ORD-2026-0801',
      realisticServiceDatePreviewView
    );
    expect(
      orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801').previewView
    ).not.toBeNull();

    // 傳入相同順序/元素日期時，Key 與 Preview 應保留
    orderMutationFlowStore.updateServiceDatesSelection('ORD-2026-0801', [
      '2026-09-02',
      '2026-09-01',
    ]);
    const unchangedDraft = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801');
    expect(unchangedDraft.idempotencyKey).toBe(key2);
    expect(unchangedDraft.previewView).not.toBeNull();

    // 傳入相異日期時，Preview 應清空且 Key 應重新生成
    orderMutationFlowStore.updateServiceDatesSelection('ORD-2026-0801', [
      '2026-09-01',
      '2026-09-03',
    ]);
    const changedDraft = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801');
    expect(changedDraft.idempotencyKey).not.toBe(key2);
    expect(changedDraft.previewView).toBeNull();
    expect(changedDraft.status).toBe('draft_changed');
  });

  it('4. 服務日期進入 outcome_unknown 時，完整保留 Draft Payload、Preview 與 Idempotency-Key 以供重試', () => {
    orderMutationFlowStore.setServiceDatesQueryReady(
      'ORD-2026-0801',
      realisticServiceDateQueryView
    );
    orderMutationFlowStore.updateServiceDatesSelection('ORD-2026-0801', [
      '2026-09-01',
      '2026-09-02',
      '2026-09-03',
    ]);
    orderMutationFlowStore.setServiceDatesPreviewReady(
      'ORD-2026-0801',
      realisticServiceDatePreviewView
    );
    orderMutationFlowStore.updateServiceDatesReason('ORD-2026-0801', '客戶確認服務日期');

    const beforeKey = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801').idempotencyKey;
    const timeoutErr = new OrderMutationUnavailableError({
      code: 'timeout',
      message: '閘道逾時',
      status: 503,
    });

    orderMutationFlowStore.setServiceDatesOutcomeUnknown('ORD-2026-0801', timeoutErr);

    const draft = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801');
    expect(draft.status).toBe('outcome_unknown');
    expect(draft.outcomeUnknown).toBe(true);
    expect(draft.idempotencyKey).toBe(beforeKey);
    expect(draft.selectedDates).toEqual(['2026-09-01', '2026-09-02', '2026-09-03']);
    expect(draft.previewView).toEqual(realisticServiceDatePreviewView);
    expect(draft.reason).toBe('客戶確認服務日期');
    expect(draft.error).toBe(timeoutErr);

    orderMutationFlowStore.updateServiceDatesSelection('ORD-2026-0801', ['2026-09-04']);
    orderMutationFlowStore.updateServiceDatesReason('ORD-2026-0801', '不得覆寫');
    const frozenDraft = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801');
    expect(frozenDraft.selectedDates).toEqual(['2026-09-01', '2026-09-02', '2026-09-03']);
    expect(frozenDraft.reason).toBe('客戶確認服務日期');
    expect(frozenDraft.idempotencyKey).toBe(beforeKey);
  });

  it('5. 409 Stale 衝突時，清空 Preview 並重新生成 Idempotency-Key', () => {
    orderMutationFlowStore.setServiceDatesPreviewReady(
      'ORD-2026-0801',
      realisticServiceDatePreviewView
    );
    const keyBefore = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801').idempotencyKey;
    const conflictErr = new OrderMutationConflictError({
      code: 'stale_version',
      message: '版本衝突',
      status: 409,
    });

    orderMutationFlowStore.setServiceDatesStale('ORD-2026-0801', conflictErr);
    const draft = orderMutationFlowStore.getOrCreateServiceDatesDraft('ORD-2026-0801');

    expect(draft.status).toBe('stale');
    expect(draft.previewView).toBeNull();
    expect(draft.idempotencyKey).not.toBe(keyBefore);
    expect(draft.error).toBe(conflictErr);
  });

  it('6. 受控重開 (Controlled Reopen) 完整狀態流轉與 draft 保留測試', () => {
    const draft = orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN');
    expect(draft.status).toBe('closed');

    orderMutationFlowStore.setReopenPreviewLoading('ORD-2026-REOPEN');
    expect(orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN').status).toBe('preview_loading');

    orderMutationFlowStore.setReopenPreviewReady('ORD-2026-REOPEN', realisticOrderReopenPreviewView);
    const readyDraft = orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN');
    expect(readyDraft.status).toBe('preview_ready');
    expect(readyDraft.previewView?.case_no).toBe('ORD-2026-0801');

    orderMutationFlowStore.updateReopenReason('ORD-2026-REOPEN', '客戶恢復需求');
    expect(orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN').reason).toBe('客戶恢復需求');

    orderMutationFlowStore.setReopenApplyPending('ORD-2026-REOPEN');
    expect(orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN').status).toBe('apply_pending');

    orderMutationFlowStore.setReopenReceiptReceived('ORD-2026-REOPEN', realisticOrderReopenReceiptView);
    expect(orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN').status).toBe('receipt_received');

    orderMutationFlowStore.setReopenObserved('ORD-2026-REOPEN');
    expect(orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN').status).toBe('observed');
  });

  it('7. 受控重開 outcome_unknown 時保留 reason、previewView 與 idempotencyKey', () => {
    orderMutationFlowStore.setReopenPreviewReady('ORD-2026-REOPEN', realisticOrderReopenPreviewView);
    orderMutationFlowStore.updateReopenReason('ORD-2026-REOPEN', '重開專用原因說明');
    const key = orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN').idempotencyKey;

    const unavailErr = new OrderMutationUnavailableError({
      code: 'service_unavailable',
      message: '暫時不可用',
      status: 503,
    });
    orderMutationFlowStore.setReopenOutcomeUnknown('ORD-2026-REOPEN', unavailErr);

    const draft = orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN');
    expect(draft.status).toBe('outcome_unknown');
    expect(draft.outcomeUnknown).toBe(true);
    expect(draft.reason).toBe('重開專用原因說明');
    expect(draft.previewView).toEqual(realisticOrderReopenPreviewView);
    expect(draft.idempotencyKey).toBe(key);
    expect(draft.error).toBe(unavailErr);

    orderMutationFlowStore.updateReopenReason('ORD-2026-REOPEN', '不得覆寫');
    expect(
      orderMutationFlowStore.getOrCreateReopenDraft('ORD-2026-REOPEN').reason
    ).toBe('重開專用原因說明');
  });

  it('8. 多案件草稿互相獨立隔離', () => {
    orderMutationFlowStore.updateServiceDatesSelection('CASE-A', ['2026-09-01']);
    orderMutationFlowStore.updateServiceDatesSelection('CASE-B', ['2026-09-02', '2026-09-03']);

    const draftA = orderMutationFlowStore.getOrCreateServiceDatesDraft('CASE-A');
    const draftB = orderMutationFlowStore.getOrCreateServiceDatesDraft('CASE-B');

    expect(draftA.selectedDates).toEqual(['2026-09-01']);
    expect(draftB.selectedDates).toEqual(['2026-09-02', '2026-09-03']);
    expect(draftA.idempotencyKey).not.toBe(draftB.idempotencyKey);
  });

  it('9. 訂閱者監聽機制：狀態變更時觸發通知，取消訂閱後不再通知', () => {
    let callCount = 0;
    const unsubscribe = orderMutationFlowStore.subscribe(() => {
      callCount += 1;
    });

    orderMutationFlowStore.updateServiceDatesSelection('CASE-SUB', ['2026-09-01']);
    expect(callCount).toBe(1);

    orderMutationFlowStore.updateServiceDatesReason('CASE-SUB', 'Reason update');
    expect(callCount).toBe(2);

    unsubscribe();
    orderMutationFlowStore.updateServiceDatesReason('CASE-SUB', 'Another reason');
    expect(callCount).toBe(2);
  });
});
