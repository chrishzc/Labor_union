/**
 * File: orders_mutation_adapter.test.ts
 * Description: 驗證 Orders mutation Adapter 的 Apply 未明、receipt 後觀察恢復、stale 與指紋防護。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  resolveServiceDatesMachineState,
  resolveReopenMachineState,
  fetchServiceDatesQuery,
  selectServiceDates,
  previewServiceDatesFlow,
  applyServiceDatesFlow,
  retryServiceDatesApplyFlow,
  retryServiceDatesObservationFlow,
  previewReopenFlow,
  updateReopenReason,
  applyReopenFlow,
  retryReopenApplyFlow,
  retryReopenObservationFlow,
} from '../adapters/orders/order_mutation_adapter';
import {
  orderMutationFlowStore,
} from '../adapters/orders/order_mutation_flow_store';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import {
  realisticServiceDateQueryView,
  realisticServiceDatePreviewView,
  realisticServiceDateReceiptView,
  realisticOrderReopenPreviewView,
  realisticOrderReopenReceiptView,
} from './fixtures/orders/order_mutation_contract_fixtures';
import {
  OrderMutationConflictError,
  OrderMutationValidationError,
  OrderMutationUnavailableError,
  ApiTimeoutError,
  ApiNetworkError,
} from '../api/orders/order_mutation_errors';

describe('OrderMutationAdapter State Machine & Flow Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
  });

  // ==========================================================================
  // 1. Discriminated Union Resolver Tests
  // ==========================================================================
  describe('1. Discriminated Union Resolvers', () => {
    it('服務日期各階段 status 映射至型別完備的 ServiceDatesMachineState', () => {
      expect(resolveServiceDatesMachineState(undefined)).toEqual({ type: 'idle' });

      orderMutationFlowStore.setServiceDatesQueryLoading('CASE-1');
      expect(
        resolveServiceDatesMachineState(
          orderMutationFlowStore.getServiceDatesDraft('CASE-1')
        )
      ).toEqual({ type: 'query_loading', caseNo: 'CASE-1' });

      orderMutationFlowStore.setServiceDatesQueryReady(
        'CASE-1',
        realisticServiceDateQueryView
      );
      const queryReadyState = resolveServiceDatesMachineState(
        orderMutationFlowStore.getServiceDatesDraft('CASE-1')
      );
      expect(queryReadyState.type).toBe('query_ready');

      // 選擇不足天數 -> canPreview: false
      selectServiceDates('CASE-1', ['2026-09-01']);
      const draftChangedState1 = resolveServiceDatesMachineState(
        orderMutationFlowStore.getServiceDatesDraft('CASE-1')
      );
      expect(draftChangedState1.type).toBe('draft_changed');
      if (draftChangedState1.type === 'draft_changed') {
        expect(draftChangedState1.canPreview).toBe(false);
      }

      // 選滿 3 天 -> canPreview: true
      selectServiceDates('CASE-1', ['2026-09-01', '2026-09-02', '2026-09-03']);
      const draftChangedState2 = resolveServiceDatesMachineState(
        orderMutationFlowStore.getServiceDatesDraft('CASE-1')
      );
      if (draftChangedState2.type === 'draft_changed') {
        expect(draftChangedState2.canPreview).toBe(true);
      }

      orderMutationFlowStore.setServiceDatesPreviewReady(
        'CASE-1',
        realisticServiceDatePreviewView
      );
      expect(
        resolveServiceDatesMachineState(
          orderMutationFlowStore.getServiceDatesDraft('CASE-1')
        ).type
      ).toBe('preview_ready');

      orderMutationFlowStore.setServiceDatesApplyPending('CASE-1');
      expect(
        resolveServiceDatesMachineState(
          orderMutationFlowStore.getServiceDatesDraft('CASE-1')
        ).type
      ).toBe('apply_pending');

      orderMutationFlowStore.setServiceDatesReceiptReceived(
        'CASE-1',
        realisticServiceDateReceiptView
      );
      expect(
        resolveServiceDatesMachineState(
          orderMutationFlowStore.getServiceDatesDraft('CASE-1')
        ).type
      ).toBe('receipt_received');

      orderMutationFlowStore.setServiceDatesObserved(
        'CASE-1',
        realisticServiceDateQueryView
      );
      expect(
        resolveServiceDatesMachineState(
          orderMutationFlowStore.getServiceDatesDraft('CASE-1')
        ).type
      ).toBe('observed');
    });

    it('受控重開各階段 status 映射至型別完備的 ReopenMachineState', () => {
      expect(resolveReopenMachineState(undefined)).toEqual({ type: 'closed' });

      orderMutationFlowStore.setReopenPreviewLoading('CASE-2');
      expect(
        resolveReopenMachineState(orderMutationFlowStore.getReopenDraft('CASE-2'))
      ).toEqual({ type: 'preview_loading', caseNo: 'CASE-2' });

      orderMutationFlowStore.setReopenPreviewReady(
        'CASE-2',
        realisticOrderReopenPreviewView
      );
      expect(
        resolveReopenMachineState(orderMutationFlowStore.getReopenDraft('CASE-2'))
      ).toMatchObject({
        type: 'preview_ready',
        caseNo: 'CASE-2',
      });

      orderMutationFlowStore.setReopenApplyPending('CASE-2');
      expect(
        resolveReopenMachineState(orderMutationFlowStore.getReopenDraft('CASE-2'))
      ).toMatchObject({
        type: 'apply_pending',
      });

      orderMutationFlowStore.setReopenReceiptReceived('CASE-2', realisticOrderReopenReceiptView);
      expect(
        resolveReopenMachineState(orderMutationFlowStore.getReopenDraft('CASE-2'))
      ).toMatchObject({
        type: 'receipt_received',
      });

      orderMutationFlowStore.setReopenObserved('CASE-2');
      expect(
        resolveReopenMachineState(orderMutationFlowStore.getReopenDraft('CASE-2'))
      ).toMatchObject({
        type: 'observed',
      });
    });
  });

  // ==========================================================================
  // 2. Confirmed Service Dates Flow Operations
  // ==========================================================================
  describe('2. Confirmed Service Dates Operations', () => {
    it('fetchServiceDatesQuery: 成功取得資料後轉換為 query_ready', async () => {
      vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue(
        realisticServiceDateQueryView
      );

      const res = await fetchServiceDatesQuery('ORD-2026-0801');
      expect(res.case_no).toBe('ORD-2026-0801');

      const draft = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
      expect(draft?.status).toBe('query_ready');
      expect(draft?.queryView).toEqual(realisticServiceDateQueryView);
    });

    it('previewServiceDatesFlow: 產生預覽成功並轉為 preview_ready', async () => {
      orderMutationFlowStore.setServiceDatesQueryReady(
        'ORD-2026-0801',
        realisticServiceDateQueryView
      );
      selectServiceDates('ORD-2026-0801', ['2026-09-01', '2026-09-02', '2026-09-03']);

      vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue(
        realisticServiceDatePreviewView
      );

      const preview = await previewServiceDatesFlow('ORD-2026-0801');
      expect(preview.preview_fingerprint).toBe('a'.repeat(64));

      const draft = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
      expect(draft?.status).toBe('preview_ready');
      expect(draft?.previewView).toEqual(realisticServiceDatePreviewView);
    });

    it('previewServiceDatesFlow: 遇到 409 Conflict 時轉為 stale 且清空舊 Preview', async () => {
      orderMutationFlowStore.setServiceDatesQueryReady(
        'ORD-2026-0801',
        realisticServiceDateQueryView
      );
      selectServiceDates('ORD-2026-0801', ['2026-09-01', '2026-09-02', '2026-09-03']);

      const conflictErr = new OrderMutationConflictError({
        code: 'service_date_confirmation_preview_stale',
        message: '排程版本已過期',
        status: 409,
      });
      vi.spyOn(ordersMutationClient, 'previewServiceDates').mockRejectedValue(conflictErr);

      await expect(previewServiceDatesFlow('ORD-2026-0801')).rejects.toThrow(conflictErr);

      const draft = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
      expect(draft?.status).toBe('stale');
      expect(draft?.previewView).toBeNull();
    });

    it('applyServiceDatesFlow: Apply 成功後必須自動 Re-Query 進入 observed 狀態', async () => {
      orderMutationFlowStore.setServiceDatesQueryReady(
        'ORD-2026-0801',
        realisticServiceDateQueryView
      );
      selectServiceDates('ORD-2026-0801', ['2026-09-01', '2026-09-02', '2026-09-03']);
      orderMutationFlowStore.setServiceDatesPreviewReady(
        'ORD-2026-0801',
        realisticServiceDatePreviewView
      );
      orderMutationFlowStore.updateServiceDatesReason('ORD-2026-0801', '確認服務日期');

      vi.spyOn(ordersMutationClient, 'applyServiceDates').mockResolvedValue(
        realisticServiceDateReceiptView
      );
      vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
        ...realisticServiceDateQueryView,
        current_version: 1,
        current_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
      });

      const receipt = await applyServiceDatesFlow('ORD-2026-0801');
      expect(receipt.confirmed_version).toBe(1);

      const draft = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
      expect(draft?.status).toBe('observed');
      expect(draft?.queryView?.current_version).toBe(1);
    });

    it('applyServiceDatesFlow: Receipt 指紋與 Preview 不一致時必須 fail closed', async () => {
      orderMutationFlowStore.setServiceDatesPreviewReady(
        'ORD-2026-0801',
        realisticServiceDatePreviewView
      );
      orderMutationFlowStore.updateServiceDatesReason('ORD-2026-0801', '原因說明');

      const corruptedReceipt = {
        ...realisticServiceDateReceiptView,
        preview_fingerprint: 'f'.repeat(64), // 假指紋
      };
      vi.spyOn(ordersMutationClient, 'applyServiceDates').mockResolvedValue(corruptedReceipt);

      await expect(applyServiceDatesFlow('ORD-2026-0801')).rejects.toThrow(
        /receipt，但指紋與預覽不一致/
      );

      const draft = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
      expect(draft?.status).toBe('observation_failed');
      expect(draft?.receiptView?.preview_fingerprint).toBe('f'.repeat(64));
    });

    it('applyServiceDatesFlow: Apply 發生逾時或 503 時轉入 outcome_unknown 並允許同 Key 重試', async () => {
      orderMutationFlowStore.setServiceDatesPreviewReady(
        'ORD-2026-0801',
        realisticServiceDatePreviewView
      );
      orderMutationFlowStore.updateServiceDatesReason('ORD-2026-0801', '確認服務日期');
      const initialKey = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801')?.idempotencyKey;

      const timeoutErr = new ApiTimeoutError(5000);
      vi.spyOn(ordersMutationClient, 'applyServiceDates')
        .mockRejectedValueOnce(timeoutErr)
        .mockResolvedValueOnce(realisticServiceDateReceiptView);

      vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
        ...realisticServiceDateQueryView,
        current_version: 1,
      });

      await expect(applyServiceDatesFlow('ORD-2026-0801')).rejects.toThrow(timeoutErr);

      const unknownDraft = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
      expect(unknownDraft?.status).toBe('outcome_unknown');
      expect(unknownDraft?.idempotencyKey).toBe(initialKey);

      // 重試
      const retryReceipt = await retryServiceDatesApplyFlow('ORD-2026-0801');
      expect(retryReceipt.confirmed_version).toBe(1);

      const observedDraft = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
      expect(observedDraft?.status).toBe('observed');
    });

    it('Apply receipt 已收到後 Re-Query 失敗時保留 receipt，且只重試 Query', async () => {
      orderMutationFlowStore.setServiceDatesQueryReady(
        'ORD-2026-0801',
        realisticServiceDateQueryView
      );
      orderMutationFlowStore.setServiceDatesPreviewReady(
        'ORD-2026-0801',
        realisticServiceDatePreviewView
      );
      orderMutationFlowStore.updateServiceDatesReason('ORD-2026-0801', '確認服務日期');

      const applySpy = vi
        .spyOn(ordersMutationClient, 'applyServiceDates')
        .mockResolvedValue(realisticServiceDateReceiptView);
      const querySpy = vi
        .spyOn(ordersMutationClient, 'getServiceDates')
        .mockRejectedValueOnce(new ApiNetworkError('查詢失敗'))
        .mockResolvedValueOnce({
          ...realisticServiceDateQueryView,
          current_version: 1,
        });

      await expect(applyServiceDatesFlow('ORD-2026-0801')).rejects.toThrow('查詢失敗');
      const failedDraft = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
      expect(failedDraft?.status).toBe('observation_failed');
      expect(failedDraft?.receiptView).toEqual(realisticServiceDateReceiptView);
      expect(failedDraft?.outcomeUnknown).toBe(false);

      await retryServiceDatesObservationFlow('ORD-2026-0801');
      expect(applySpy).toHaveBeenCalledTimes(1);
      expect(querySpy).toHaveBeenCalledTimes(2);
      expect(orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801')?.status).toBe(
        'observed'
      );
    });
  });

  // ==========================================================================
  // 3. Controlled Order Reopen Flow Operations
  // ==========================================================================
  describe('3. Controlled Order Reopen Operations', () => {
    it('previewReopenFlow: 成功產生預覽並驗證 restored 列表為空', async () => {
      vi.spyOn(ordersMutationClient, 'previewReopen').mockResolvedValue(
        realisticOrderReopenPreviewView
      );

      const preview = await previewReopenFlow('ORD-2026-0801');
      expect(preview.requires_fresh_scheduling_preview).toBe(true);

      const draft = orderMutationFlowStore.getReopenDraft('ORD-2026-0801');
      expect(draft?.status).toBe('preview_ready');
    });

    it('previewReopenFlow: 若 restored 列表非空必須標記 contract drift 並 fail closed', async () => {
      const driftedPreview = {
        ...realisticOrderReopenPreviewView,
        restored_assignment_ids: [999],
      };
      vi.spyOn(ordersMutationClient, 'previewReopen').mockResolvedValue(driftedPreview);

      await expect(previewReopenFlow('ORD-2026-0801')).rejects.toThrow(/restored 列表/);

      const draft = orderMutationFlowStore.getReopenDraft('ORD-2026-0801');
      expect(draft?.status).toBe('typed_error');
    });

    it('applyReopenFlow: 成功套用並觸發外部 re-query 回調', async () => {
      orderMutationFlowStore.setReopenPreviewReady(
        'ORD-2026-0801',
        realisticOrderReopenPreviewView
      );
      updateReopenReason('ORD-2026-0801', '客戶恢復訂單需求');

      vi.spyOn(ordersMutationClient, 'applyReopen').mockResolvedValue(
        realisticOrderReopenReceiptView
      );

      let requeryCalled = false;
      const onRequery = async () => {
        requeryCalled = true;
      };

      const receipt = await applyReopenFlow('ORD-2026-0801', onRequery);
      expect(receipt.lifecycle_status).toBe('洽談中');
      expect(requeryCalled).toBe(true);

      const draft = orderMutationFlowStore.getReopenDraft('ORD-2026-0801');
      expect(draft?.status).toBe('observed');
    });

    it('applyReopenFlow: 原因為純空白時拒絕提交並拋出 OrderMutationValidationError', async () => {
      orderMutationFlowStore.setReopenPreviewReady(
        'ORD-2026-0801',
        realisticOrderReopenPreviewView
      );
      updateReopenReason('ORD-2026-0801', '   ');

      await expect(applyReopenFlow('ORD-2026-0801')).rejects.toThrow(
        OrderMutationValidationError
      );
    });

    it('applyReopenFlow: 503 錯誤時轉入 outcome_unknown 並可使用相同 Idempotency-Key 重試', async () => {
      orderMutationFlowStore.setReopenPreviewReady(
        'ORD-2026-0801',
        realisticOrderReopenPreviewView
      );
      updateReopenReason('ORD-2026-0801', '客戶恢復需求');
      const key = orderMutationFlowStore.getReopenDraft('ORD-2026-0801')?.idempotencyKey;

      const unavailErr = new OrderMutationUnavailableError({
        code: 'temporarily_unavailable',
        message: '可使用相同冪等鍵重試',
        status: 503,
      });

      vi.spyOn(ordersMutationClient, 'applyReopen')
        .mockRejectedValueOnce(unavailErr)
        .mockResolvedValueOnce(realisticOrderReopenReceiptView);

      await expect(applyReopenFlow('ORD-2026-0801')).rejects.toThrow(unavailErr);

      const draft = orderMutationFlowStore.getReopenDraft('ORD-2026-0801');
      expect(draft?.status).toBe('outcome_unknown');
      expect(draft?.idempotencyKey).toBe(key);

      const retryReceipt = await retryReopenApplyFlow('ORD-2026-0801');
      expect(retryReceipt.lifecycle_status).toBe('洽談中');

      const observedDraft = orderMutationFlowStore.getReopenDraft('ORD-2026-0801');
      expect(observedDraft?.status).toBe('observed');
    });

    it('Reopen receipt 已收到後列表 Re-Query 失敗時不得重送 Apply', async () => {
      orderMutationFlowStore.setReopenPreviewReady(
        'ORD-2026-0801',
        realisticOrderReopenPreviewView
      );
      updateReopenReason('ORD-2026-0801', '客戶恢復需求');

      const applySpy = vi
        .spyOn(ordersMutationClient, 'applyReopen')
        .mockResolvedValue(realisticOrderReopenReceiptView);
      const requery = vi.fn().mockRejectedValueOnce(new ApiNetworkError('列表查詢失敗'));

      await expect(applyReopenFlow('ORD-2026-0801', requery)).rejects.toThrow(
        '列表查詢失敗'
      );
      const failedDraft = orderMutationFlowStore.getReopenDraft('ORD-2026-0801');
      expect(failedDraft?.status).toBe('observation_failed');
      expect(failedDraft?.receiptView).toEqual(realisticOrderReopenReceiptView);

      requery.mockResolvedValueOnce(undefined);
      await retryReopenObservationFlow('ORD-2026-0801', requery);
      expect(applySpy).toHaveBeenCalledTimes(1);
      expect(requery).toHaveBeenCalledTimes(2);
      expect(orderMutationFlowStore.getReopenDraft('ORD-2026-0801')?.status).toBe(
        'observed'
      );
    });
  });
});
