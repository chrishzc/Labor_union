/**
 * File: anomaly_query_adapter.test.ts
 * Description: 驗證 Anomalies DTO 的安全頁面映射。
 */

import { describe, it, expect } from 'vitest';
import {
  mapDomainToCategory,
  mapImportWarningLaneLabel,
  mapImportWarningStatusLabel,
  adaptAnomalySummary,
  adaptImportWarningTask,
  adaptAnomalyDetail,
  adaptImportWarningReferral,
  calculateAnomalyKPIs,
  filterAnomalies,
  CATEGORY_TAB_KEYS,
  type AnomalySummaryViewModel,
} from '../adapters/anomalies/anomaly_query_adapter';
import {
  VALID_ANOMALY_SUMMARY_1,
  VALID_ANOMALY_SUMMARY_2,
  VALID_ANOMALY_SUMMARY_3,
  VALID_IMPORT_WARNING_TASK_HCM,
  VALID_IMPORT_WARNING_TASK_BECLASS_CLI,
  VALID_IMPORT_WARNING_TASK_HISTORICAL,
  VALID_IMPORT_WARNING_TASK_BECLASS_STF,
  VALID_IMPORT_WARNING_TASK_FINANCE,
  VALID_IMPORT_WARNING_TASK_AUTO_RESOLVED,
  VALID_ANOMALY_DETAIL_VIEW,
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';
import type {
  AnomalySummaryView,
  ImportWarningTaskView,
} from '../api/anomalies/anomaly_query_schemas';

describe('Anomaly Query Adapter Suite', () => {
  it('maps typed detail timeline without exposing actor, reason, or raw action bindings', () => {
    const view = adaptAnomalyDetail(VALID_ANOMALY_DETAIL_VIEW);
    expect(view.summary.code).toBe('LINE-006');
    expect(view.timeline).toEqual([
      {
        action: 'reopen',
        expectedWorkflowVersion: 1,
        resultingWorkflowVersion: 2,
        createdAt: '2026-08-17T09:00:00+08:00',
      },
    ]);
    expect(view.actionsAvailable).toBe(false);
  });

  it('maps warning referral as neutral typed navigation only', () => {
    const view = adaptImportWarningReferral(VALID_IMPORT_WARNING_REFERRAL_VIEW);
    expect(view.owningLane).toBe('hcm');
    expect(view.targetCommand).toBe('preview_hcm_resubmission');
  });
  describe('Constants and Category Tabs', () => {
    it('defines expected CATEGORY_TAB_KEYS in canonical order', () => {
      expect(CATEGORY_TAB_KEYS).toEqual([
        '全部',
        '匯入資料',
        '媒合推播',
        '排班調度',
        '客戶帳務',
        '月嫂薪資',
        '政府補助',
        '其他',
      ]);
    });
  });

  describe('mapDomainToCategory', () => {
    it('maps all approved canonical source domains correctly', () => {
      expect(mapDomainToCategory('case_import')).toBe('匯入資料');
      expect(mapDomainToCategory('finance_import')).toBe('匯入資料');
      expect(mapDomainToCategory('CASE_IMPORT')).toBe('匯入資料');

      expect(mapDomainToCategory('line')).toBe('媒合推播');
      expect(mapDomainToCategory('line_integration')).toBe('媒合推播');
      expect(mapDomainToCategory('matching')).toBe('媒合推播');

      expect(mapDomainToCategory('scheduling')).toBe('排班調度');
      expect(mapDomainToCategory('assignments')).toBe('排班調度');

      expect(mapDomainToCategory('client_finance')).toBe('客戶帳務');
      expect(mapDomainToCategory('client_receivable')).toBe('客戶帳務');
      expect(mapDomainToCategory('client_payable')).toBe('客戶帳務');
      expect(mapDomainToCategory('client_subsidy_return')).toBe('客戶帳務');

      expect(mapDomainToCategory('staff_payables')).toBe('月嫂薪資');
      expect(mapDomainToCategory('payroll')).toBe('月嫂薪資');

      expect(mapDomainToCategory('government_subsidy')).toBe('政府補助');
    });

    it('maps unknown, empty, or nullable domains to "其他"', () => {
      expect(mapDomainToCategory('unknown_custom_domain')).toBe('其他');
      expect(mapDomainToCategory('')).toBe('其他');
      expect(mapDomainToCategory('   ')).toBe('其他');
      expect(mapDomainToCategory(null)).toBe('其他');
      expect(mapDomainToCategory(undefined)).toBe('其他');
    });
  });

  describe('mapImportWarningLaneLabel', () => {
    it('maps canonical import lanes to Chinese labels', () => {
      expect(mapImportWarningLaneLabel('hcm')).toBe('HCM 匯入');
      expect(mapImportWarningLaneLabel('beclass')).toBe('BeClass 匯入');
      expect(mapImportWarningLaneLabel('client_beclass')).toBe('BeClass 匯入');
      expect(mapImportWarningLaneLabel('staff_beclass')).toBe('BeClass 匯入');
      expect(mapImportWarningLaneLabel('historical_orders')).toBe('歷史訂單匯入');
      expect(mapImportWarningLaneLabel('historical_order')).toBe('歷史訂單匯入');
      expect(mapImportWarningLaneLabel('historical')).toBe('歷史訂單匯入');
      expect(mapImportWarningLaneLabel('finance')).toBe('財務匯入');
      expect(mapImportWarningLaneLabel('finance_import')).toBe('財務匯入');
    });

    it('fails closed for custom lanes and handles empty/null', () => {
      expect(mapImportWarningLaneLabel('custom_lane')).toBe('其他匯入');
      expect(mapImportWarningLaneLabel('')).toBe('其他匯入');
      expect(mapImportWarningLaneLabel(null)).toBe('其他匯入');
      expect(mapImportWarningLaneLabel(undefined)).toBe('其他匯入');
    });
  });

  describe('mapImportWarningStatusLabel', () => {
    it('maps all tracking statuses to Chinese labels', () => {
      expect(mapImportWarningStatusLabel('open')).toBe('待處理');
      expect(mapImportWarningStatusLabel('awaiting_external_confirmation')).toBe('等待外部確認');
      expect(mapImportWarningStatusLabel('response_recorded')).toBe('已記錄回應');
      expect(mapImportWarningStatusLabel('reimport_requested')).toBe('要求重新匯入');
      expect(mapImportWarningStatusLabel('closed')).toBe('已結案');
      expect(mapImportWarningStatusLabel('auto_resolved')).toBe('自動排除');
      expect(mapImportWarningStatusLabel('other_status')).toBe('狀態待確認');
    });
  });

  describe('adaptAnomalySummary', () => {
    it('transforms blocking open anomaly with staff calendar navigation correctly', () => {
      const dto: AnomalySummaryView = VALID_ANOMALY_SUMMARY_1;
      const adapted = adaptAnomalySummary(dto);

      expect(adapted.id).toBe(dto.fingerprint);
      expect(adapted.fingerprint).toBe(dto.fingerprint);
      expect(adapted.code).toBe('LINE-006');
      expect(adapted.severity).toBe('🔴 嚴重阻擋');
      expect(adapted.severityClass).toBe('critical');
      expect(adapted.status).toBe('🟡 待處理');
      expect(adapted.rawSeverity).toBe('blocking');
      expect(adapted.rawWorkflowStatus).toBe('open');
      expect(adapted.rawDomain).toBe('line_integration');
      expect(adapted.category).toBe('媒合推播');

      expect(adapted.title).toBe('LINE 通知發送待確認');
      expect(adapted.description).toBe('請核對案件 CASE-102的目前資料與可採取的處理方式。');
      expect(adapted.relatedEntity).toBe('案件 CASE-102');
      expect(adapted.suggestedAction).toBe('開啟詳情查看可執行的處置。');
      expect(adapted.rootEvidence).toBe('影響對象：案件 CASE-102');

      // Navigation & Metadata
      expect(adapted.staffCalendarNavigation).toEqual({
        staff_id: 14,
        target_date: '2026-08-20',
      });
      expect(adapted.metadata).toEqual({
        sourceDomain: 'line_integration',
        sourceVersion: 2,
        workflowVersion: 0,
        predicateActive: true,
      });
    });

    it('transforms warning claimed anomaly without navigation correctly', () => {
      const dto: AnomalySummaryView = VALID_ANOMALY_SUMMARY_2;
      const adapted = adaptAnomalySummary(dto);

      expect(adapted.id).toBe(dto.fingerprint);
      expect(adapted.code).toBe('LINE-006');
      expect(adapted.severity).toBe('🟡 警示待補');
      expect(adapted.severityClass).toBe('warning');
      expect(adapted.status).toBe('🔵 已認領');
      expect(adapted.rawSeverity).toBe('warning');
      expect(adapted.rawWorkflowStatus).toBe('claimed');
      expect(adapted.category).toBe('媒合推播');
      expect(adapted.staffCalendarNavigation).toBeNull();
      expect(adapted.metadata.predicateActive).toBe(true);
    });

    it('transforms resolved anomaly correctly', () => {
      const dto: AnomalySummaryView = VALID_ANOMALY_SUMMARY_3;
      const adapted = adaptAnomalySummary(dto);

      expect(adapted.code).toBe('LINE-006');
      expect(adapted.severity).toBe('🟡 警示待補');
      expect(adapted.severityClass).toBe('warning');
      expect(adapted.status).toBe('✅ 已排除');
      expect(adapted.rawSeverity).toBe('warning');
      expect(adapted.rawWorkflowStatus).toBe('resolved');
      expect(adapted.category).toBe('媒合推播');
      expect(adapted.metadata.predicateActive).toBe(false);
    });
  });

  describe('adaptImportWarningTask', () => {
    it('transforms HCM open task fixture correctly', () => {
      const dto: ImportWarningTaskView = VALID_IMPORT_WARNING_TASK_HCM;
      const adapted = adaptImportWarningTask(dto);

      expect(adapted.occurrenceIdentity).toBe('import-warning:3a7e4f9b8c0d1e2f3a4b5c6d7e8f9012');
      expect(adapted.owningLane).toBe('hcm');
      expect(adapted.laneLabel).toBe('HCM 匯入');
      expect(adapted.logicalCode).toBe('HCM-FIELD-001');
      expect(adapted.fieldPath).toBe('身分證字號');
      expect(adapted.subject).toBe('A12****789');
      expect(adapted.issueCodes).toEqual(['hcm_field_missing:身分證字號']);
      expect(adapted.status).toBe('open');
      expect(adapted.statusLabel).toBe('待處理');
      expect(adapted.version).toBe(1);
      expect(adapted.evidenceReference).toBe('batch-20260816-01');
      expect(adapted.displayMessage).toBe('缺少身分證字號');
      expect(adapted.navigationAction).toBe('hcm_import_center');
    });

    it('transforms BeClass, Historical, and Finance tasks with proper lane and status labels', () => {
      const adaptedCli = adaptImportWarningTask(VALID_IMPORT_WARNING_TASK_BECLASS_CLI);
      expect(adaptedCli.laneLabel).toBe('BeClass 匯入');
      expect(adaptedCli.statusLabel).toBe('等待外部確認');
      expect(adaptedCli.evidenceReference).toBeNull();

      const adaptedHist = adaptImportWarningTask(VALID_IMPORT_WARNING_TASK_HISTORICAL);
      expect(adaptedHist.laneLabel).toBe('歷史訂單匯入');
      expect(adaptedHist.statusLabel).toBe('已記錄回應');

      const adaptedStf = adaptImportWarningTask(VALID_IMPORT_WARNING_TASK_BECLASS_STF);
      expect(adaptedStf.laneLabel).toBe('BeClass 匯入');
      expect(adaptedStf.statusLabel).toBe('要求重新匯入');

      const adaptedFin = adaptImportWarningTask(VALID_IMPORT_WARNING_TASK_FINANCE);
      expect(adaptedFin.laneLabel).toBe('財務匯入');
      expect(adaptedFin.statusLabel).toBe('已結案');

      const adaptedAuto = adaptImportWarningTask(VALID_IMPORT_WARNING_TASK_AUTO_RESOLVED);
      expect(adaptedAuto.statusLabel).toBe('自動排除');
      expect(adaptedAuto.navigationAction).toBeNull();
    });
  });

  describe('calculateAnomalyKPIs', () => {
    it('computes zero counts for empty array', () => {
      const kpis = calculateAnomalyKPIs([]);
      expect(kpis).toEqual({
        criticalCount: 0,
        warningCount: 0,
        openCount: 0,
        claimedCount: 0,
      });
    });

    it('accurately counts critical/warning active items and open/claimed statuses', () => {
      const anomalies = [
        adaptAnomalySummary(VALID_ANOMALY_SUMMARY_1), // blocking, open
        adaptAnomalySummary(VALID_ANOMALY_SUMMARY_2), // warning, claimed
        adaptAnomalySummary(VALID_ANOMALY_SUMMARY_3), // warning, resolved
      ];

      const kpis = calculateAnomalyKPIs(anomalies);

      // VALID_ANOMALY_SUMMARY_1: blocking & open -> criticalCount=1, openCount=1
      // VALID_ANOMALY_SUMMARY_2: warning & claimed -> warningCount=1, claimedCount=1
      // VALID_ANOMALY_SUMMARY_3: warning & resolved -> not counted in warningCount (resolved), not open, not claimed
      expect(kpis.criticalCount).toBe(1);
      expect(kpis.warningCount).toBe(1);
      expect(kpis.openCount).toBe(1);
      expect(kpis.claimedCount).toBe(1);
    });

    it('does not include resolved blocking items in criticalCount', () => {
      const resolvedBlocking: AnomalySummaryViewModel = {
        ...adaptAnomalySummary(VALID_ANOMALY_SUMMARY_1),
        rawWorkflowStatus: 'resolved',
        status: '✅ 已排除',
      };

      const kpis = calculateAnomalyKPIs([resolvedBlocking]);
      expect(kpis.criticalCount).toBe(0);
      expect(kpis.openCount).toBe(0);
    });
  });

  describe('filterAnomalies', () => {
    const list = [
      adaptAnomalySummary(VALID_ANOMALY_SUMMARY_1), // category: '排班調度', status: 'open'
      adaptAnomalySummary(VALID_ANOMALY_SUMMARY_2), // category: '客戶帳務', status: 'claimed'
      adaptAnomalySummary(VALID_ANOMALY_SUMMARY_3), // category: '匯入資料', status: 'resolved'
    ];

    it('returns all items when category is "全部" and statusFilter is "all"', () => {
      const result = filterAnomalies(list, '全部', 'all');
      expect(result.length).toBe(3);
    });

    it('filters strictly by category', () => {
      const lineOnly = filterAnomalies(list, '媒合推播', 'all');
      expect(lineOnly.length).toBe(3);
      expect(lineOnly.every((item) => item.code === 'LINE-006')).toBe(true);

      const financeOnly = filterAnomalies(list, '客戶帳務', 'all');
      expect(financeOnly.length).toBe(0);

      const nonExistent = filterAnomalies(list, '政府補助', 'all');
      expect(nonExistent.length).toBe(0);
    });

    it('filters strictly by workflow status', () => {
      const openOnly = filterAnomalies(list, '全部', 'open');
      expect(openOnly.length).toBe(1);
      expect(openOnly[0].rawWorkflowStatus).toBe('open');

      const claimedOnly = filterAnomalies(list, '全部', 'claimed');
      expect(claimedOnly.length).toBe(1);
      expect(claimedOnly[0].rawWorkflowStatus).toBe('claimed');

      const resolvedOnly = filterAnomalies(list, '全部', 'resolved');
      expect(resolvedOnly.length).toBe(1);
      expect(resolvedOnly[0].rawWorkflowStatus).toBe('resolved');
    });

    it('filters by both category and workflow status simultaneously', () => {
      const matched = filterAnomalies(list, '媒合推播', 'open');
      expect(matched.length).toBe(1);
      expect(matched[0].code).toBe('LINE-006');

      const mismatched = filterAnomalies(list, '客戶帳務', 'claimed');
      expect(mismatched.length).toBe(0);
    });

    it('handles empty input array safely', () => {
      const result = filterAnomalies([], '全部', 'all');
      expect(result).toEqual([]);
    });
  });
});
