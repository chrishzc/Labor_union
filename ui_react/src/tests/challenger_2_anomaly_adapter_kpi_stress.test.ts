/**
 * File: challenger_2_anomaly_adapter_kpi_stress.test.ts
 * Description: 驗證 Anomalies 適配器、KPI 與匯入警示隔離。
 */

import { describe, it, expect } from 'vitest';
import {
  mapDomainToCategory,
  mapImportWarningStatusLabel,
  adaptAnomalySummary,
  adaptImportWarningTask,
  calculateAnomalyKPIs,
  filterAnomalies,
  type AnomalySummaryViewModel,
  type AnomalyDomainCategory,
} from '../adapters/anomalies/anomaly_query_adapter';
import type {
  AnomalySummaryView,
  AnomalySeverity,
  AnomalyWorkflowStatus,
  ImportWarningTaskView,
  ImportWarningTrackingStatus,
  ImportWarningNavigationAction,
} from '../api/anomalies/anomaly_query_schemas';

describe('Challenger 2 — Phase 2D Adapter & KPI Stress-Testing Suite', () => {
  // ==========================================================================
  // Section 1: calculateAnomalyKPIs Stress & Invariant Tests
  // ==========================================================================
  describe('calculateAnomalyKPIs Extreme & Stress Tests', () => {
    it('[KPI-1] Empty list returns zero for all 4 metrics', () => {
      const kpis = calculateAnomalyKPIs([]);
      expect(kpis).toEqual({
        criticalCount: 0,
        warningCount: 0,
        openCount: 0,
        claimedCount: 0,
      });
    });

    it('[KPI-2] Isolated Resolved Blocking items do NOT pollute criticalCount or open/claimed', () => {
      const resolvedBlocking: AnomalySummaryViewModel = {
        id: 'mock-1',
        fingerprint: 'a'.repeat(64),
        code: 'TEST-001',
        title: '目前 typed view 未納入摘要欄位',
        severity: '🔴 嚴重阻擋',
        severityClass: 'critical',
        status: '✅ 已排除',
        rawSeverity: 'blocking',
        rawWorkflowStatus: 'resolved',
        rawDomain: 'scheduling',
        category: '排班調度',
        relatedEntity: '目前 typed view 未納入關聯實體欄位',
        description: '目前 typed view 未納入描述欄位',
        suggestedAction: '目前 typed view 未納入建議處理欄位',
        rootEvidence: '目前 typed view 未納入根事實明細欄位',
        staffCalendarNavigation: null,
        metadata: {
          sourceDomain: 'scheduling',
          sourceVersion: 1,
          workflowVersion: 1,
          predicateActive: false,
        },
      };

      const kpis = calculateAnomalyKPIs([resolvedBlocking]);
      expect(kpis.criticalCount).toBe(0);
      expect(kpis.warningCount).toBe(0);
      expect(kpis.openCount).toBe(0);
      expect(kpis.claimedCount).toBe(0);
    });

    it('[KPI-3] Isolated Resolved Warning items do NOT pollute warningCount or open/claimed', () => {
      const resolvedWarning: AnomalySummaryViewModel = {
        id: 'mock-2',
        fingerprint: 'b'.repeat(64),
        code: 'TEST-002',
        title: '目前 typed view 未納入摘要欄位',
        severity: '🟡 警示待補',
        severityClass: 'warning',
        status: '✅ 已排除',
        rawSeverity: 'warning',
        rawWorkflowStatus: 'resolved',
        rawDomain: 'case_import',
        category: '匯入資料',
        relatedEntity: '目前 typed view 未納入關聯實體欄位',
        description: '目前 typed view 未納入描述欄位',
        suggestedAction: '目前 typed view 未納入建議處理欄位',
        rootEvidence: '目前 typed view 未納入根事實明細欄位',
        staffCalendarNavigation: null,
        metadata: {
          sourceDomain: 'case_import',
          sourceVersion: 1,
          workflowVersion: 1,
          predicateActive: false,
        },
      };

      const kpis = calculateAnomalyKPIs([resolvedWarning]);
      expect(kpis.criticalCount).toBe(0);
      expect(kpis.warningCount).toBe(0);
      expect(kpis.openCount).toBe(0);
      expect(kpis.claimedCount).toBe(0);
    });

    it('[KPI-4] 1000 items dataset with exact distribution computes exact deterministic counts', () => {
      const anomalies: AnomalySummaryViewModel[] = [];

      // Distribution plan for 1000 items:
      // 1. blocking + open: 300 items -> criticalCount +300, openCount +300
      // 2. blocking + claimed: 200 items -> criticalCount +200, claimedCount +200
      // 3. blocking + resolved: 150 items -> criticalCount +0, openCount +0, claimedCount +0
      // 4. warning + open: 150 items -> warningCount +150, openCount +150
      // 5. warning + claimed: 100 items -> warningCount +100, claimedCount +100
      // 6. warning + resolved: 100 items -> warningCount +0, openCount +0, claimedCount +0
      // Total items = 300 + 200 + 150 + 150 + 100 + 100 = 1000 items

      const createItem = (
        index: number,
        severity: AnomalySeverity,
        status: AnomalyWorkflowStatus,
        domain: string
      ): AnomalySummaryViewModel => {
        const hex = index.toString(16).padStart(64, '0');
        const isBlocking = severity === 'blocking';
        return {
          id: `item-${index}`,
          fingerprint: hex,
          code: `CODE-${index}`,
          title: '目前 typed view 未納入摘要欄位',
          severity: isBlocking ? '🔴 嚴重阻擋' : '🟡 警示待補',
          severityClass: isBlocking ? 'critical' : 'warning',
          status: status === 'open' ? '🟡 待處理' : status === 'claimed' ? '🔵 已認領' : '✅ 已排除',
          rawSeverity: severity,
          rawWorkflowStatus: status,
          rawDomain: domain,
          category: mapDomainToCategory(domain),
          relatedEntity: '目前 typed view 未納入關聯實體欄位',
          description: '目前 typed view 未納入描述欄位',
          suggestedAction: '目前 typed view 未納入建議處理欄位',
          rootEvidence: '目前 typed view 未納入根事實明細欄位',
          staffCalendarNavigation: null,
          metadata: {
            sourceDomain: domain,
            sourceVersion: 1,
            workflowVersion: 1,
            predicateActive: status !== 'resolved',
          },
        };
      };

      let idx = 0;
      // 1. 300 blocking open
      for (let i = 0; i < 300; i++) anomalies.push(createItem(idx++, 'blocking', 'open', 'scheduling'));
      // 2. 200 blocking claimed
      for (let i = 0; i < 200; i++) anomalies.push(createItem(idx++, 'blocking', 'claimed', 'line'));
      // 3. 150 blocking resolved
      for (let i = 0; i < 150; i++) anomalies.push(createItem(idx++, 'blocking', 'resolved', 'payroll'));
      // 4. 150 warning open
      for (let i = 0; i < 150; i++) anomalies.push(createItem(idx++, 'warning', 'open', 'case_import'));
      // 5. 100 warning claimed
      for (let i = 0; i < 100; i++) anomalies.push(createItem(idx++, 'warning', 'claimed', 'client_finance'));
      // 6. 100 warning resolved
      for (let i = 0; i < 100; i++) anomalies.push(createItem(idx++, 'warning', 'resolved', 'government_subsidy'));

      expect(anomalies.length).toBe(1000);

      const kpis = calculateAnomalyKPIs(anomalies);

      // Expected:
      // criticalCount = 300 + 200 = 500
      // warningCount = 150 + 100 = 250
      // openCount = 300 + 150 = 450
      // claimedCount = 200 + 100 = 300
      expect(kpis.criticalCount).toBe(500);
      expect(kpis.warningCount).toBe(250);
      expect(kpis.openCount).toBe(450);
      expect(kpis.claimedCount).toBe(300);

      // Conservation Invariant: Active Severity Total === Active Workflow Status Total
      expect(kpis.criticalCount + kpis.warningCount).toBe(kpis.openCount + kpis.claimedCount);
      expect(kpis.criticalCount + kpis.warningCount).toBe(750);
    });

    it('[KPI-5] Mathematical Invariant holds under 10,000 pseudo-random permutations', () => {
      const severities: AnomalySeverity[] = ['blocking', 'warning'];
      const statuses: AnomalyWorkflowStatus[] = ['open', 'claimed', 'resolved'];
      const domains = ['case_import', 'line', 'scheduling', 'client_finance', 'payroll', 'government_subsidy', 'other'];

      const randomItems: AnomalySummaryViewModel[] = [];
      for (let i = 0; i < 10000; i++) {
        const severity = severities[i % severities.length];
        const status = statuses[(i * 7) % statuses.length];
        const domain = domains[(i * 13) % domains.length];
        const hex = i.toString(16).padStart(64, '0');

        randomItems.push({
          id: `rand-${i}`,
          fingerprint: hex,
          code: `RAND-${i}`,
          title: '目前 typed view 未納入摘要欄位',
          severity: severity === 'blocking' ? '🔴 嚴重阻擋' : '🟡 警示待補',
          severityClass: severity === 'blocking' ? 'critical' : 'warning',
          status: status === 'open' ? '🟡 待處理' : status === 'claimed' ? '🔵 已認領' : '✅ 已排除',
          rawSeverity: severity,
          rawWorkflowStatus: status,
          rawDomain: domain,
          category: mapDomainToCategory(domain),
          relatedEntity: '目前 typed view 未納入關聯實體欄位',
          description: '目前 typed view 未納入描述欄位',
          suggestedAction: '目前 typed view 未納入建議處理欄位',
          rootEvidence: '目前 typed view 未納入根事實明細欄位',
          staffCalendarNavigation: null,
          metadata: {
            sourceDomain: domain,
            sourceVersion: 1,
            workflowVersion: 1,
            predicateActive: status !== 'resolved',
          },
        });
      }

      const kpis = calculateAnomalyKPIs(randomItems);

      // Unresolved items invariant check
      expect(kpis.criticalCount + kpis.warningCount).toBe(kpis.openCount + kpis.claimedCount);
      expect(Number.isInteger(kpis.criticalCount)).toBe(true);
      expect(Number.isInteger(kpis.warningCount)).toBe(true);
      expect(Number.isInteger(kpis.openCount)).toBe(true);
      expect(Number.isInteger(kpis.claimedCount)).toBe(true);
      expect(kpis.criticalCount).toBeGreaterThanOrEqual(0);
      expect(kpis.warningCount).toBeGreaterThanOrEqual(0);
      expect(kpis.openCount).toBeGreaterThanOrEqual(0);
      expect(kpis.claimedCount).toBeGreaterThanOrEqual(0);
    });
  });

  // ==========================================================================
  // Section 2: filterAnomalies Combinatorial Stress Tests (32 Permutations)
  // ==========================================================================
  describe('filterAnomalies 32-State Combinatorial Tests', () => {
    const categories: AnomalyDomainCategory[] = [
      '全部',
      '匯入資料',
      '媒合推播',
      '排班調度',
      '客戶帳務',
      '月嫂薪資',
      '政府補助',
      '其他',
    ];

    const statusFilters: string[] = ['all', 'open', 'claimed', 'resolved'];

    const domainList = [
      'case_import',
      'finance_import',
      'line',
      'line_integration',
      'matching',
      'scheduling',
      'assignments',
      'client_finance',
      'staff_payables',
      'payroll',
      'government_subsidy',
      'unknown_custom_source',
    ];

    // Build comprehensive test dataset covering all 12 domains x 2 severities x 3 statuses = 72 permutations
    const fullDataset: AnomalySummaryViewModel[] = [];
    let counter = 0;

    for (const domain of domainList) {
      for (const sev of ['blocking', 'warning'] as AnomalySeverity[]) {
        for (const st of ['open', 'claimed', 'resolved'] as AnomalyWorkflowStatus[]) {
          const hex = (counter++).toString(16).padStart(64, '0');
          fullDataset.push({
            id: `item-${hex.slice(-4)}`,
            fingerprint: hex,
            code: `ANOM-${domain}-${sev}-${st}`,
            title: '目前 typed view 未納入摘要欄位',
            severity: sev === 'blocking' ? '🔴 嚴重阻擋' : '🟡 警示待補',
            severityClass: sev === 'blocking' ? 'critical' : 'warning',
            status: st === 'open' ? '🟡 待處理' : st === 'claimed' ? '🔵 已認領' : '✅ 已排除',
            rawSeverity: sev,
            rawWorkflowStatus: st,
            rawDomain: domain,
            category: mapDomainToCategory(domain),
            relatedEntity: '目前 typed view 未納入關聯實體欄位',
            description: '目前 typed view 未納入描述欄位',
            suggestedAction: '目前 typed view 未納入建議處理欄位',
            rootEvidence: '目前 typed view 未納入根事實明細欄位',
            staffCalendarNavigation: null,
            metadata: {
              sourceDomain: domain,
              sourceVersion: 1,
              workflowVersion: 1,
              predicateActive: st !== 'resolved',
            },
          });
        }
      }
    }

    it('[Filter-1] All 32 filter combinations return exact deterministic filtered results', () => {
      expect(fullDataset.length).toBe(72);

      for (const cat of categories) {
        for (const stFilter of statusFilters) {
          const filtered = filterAnomalies(fullDataset, cat, stFilter);

          // Manually compute expected items
          const expected = fullDataset.filter((item) => {
            const matchesCat = cat === '全部' || item.category === cat;
            const matchesSt = stFilter === 'all' || item.rawWorkflowStatus === stFilter;
            return matchesCat && matchesSt;
          });

          expect(filtered.length).toBe(expected.length);
          for (let i = 0; i < filtered.length; i++) {
            expect(filtered[i].id).toBe(expected[i].id);
            expect(filtered[i].rawWorkflowStatus).toBe(expected[i].rawWorkflowStatus);
            expect(filtered[i].category).toBe(expected[i].category);
          }
        }
      }
    });

    it('[Filter-2] Case-insensitive alias "all" and "全部" behave identically', () => {
      const res1 = filterAnomalies(fullDataset, '全部', 'all');
      const res2 = filterAnomalies(fullDataset, 'all', 'all');
      const res3 = filterAnomalies(fullDataset, 'ALL', 'all');
      const res4 = filterAnomalies(fullDataset, '', 'all');

      expect(res1.length).toBe(fullDataset.length);
      expect(res2.length).toBe(fullDataset.length);
      expect(res3.length).toBe(fullDataset.length);
      expect(res4.length).toBe(fullDataset.length);
    });

    it('[Filter-3] Status filter alias "全部" and "all" behave identically', () => {
      const res1 = filterAnomalies(fullDataset, '排班調度', 'all');
      const res2 = filterAnomalies(fullDataset, '排班調度', '全部');
      const res3 = filterAnomalies(fullDataset, '排班調度', '');

      expect(res1.length).toBe(res2.length);
      expect(res2.length).toBe(res3.length);
    });

    it('[Filter-4] 1000 items filtered under extreme load produces correct subset without mutation', () => {
      // Create 1000 items replicated from fullDataset
      const largeList: AnomalySummaryViewModel[] = [];
      for (let i = 0; i < 1000; i++) {
        largeList.push({
          ...fullDataset[i % fullDataset.length],
          id: `large-item-${i}`,
        });
      }

      const originalFirstItem = { ...largeList[0] };
      const filtered = filterAnomalies(largeList, '客戶帳務', 'open');

      // Verify no mutation of input array
      expect(largeList.length).toBe(1000);
      expect(largeList[0].id).toBe(originalFirstItem.id);

      // Verify all filtered items strictly match criteria
      for (const item of filtered) {
        expect(item.category).toBe('客戶帳務');
        expect(item.rawWorkflowStatus).toBe('open');
      }
    });
  });

  // ==========================================================================
  // Section 3: Domain Category Mapping Exhaustive & Edge-Case Tests
  // ==========================================================================
  describe('mapDomainToCategory Exhaustive Tests', () => {
    it('[Category-1] Maps all canonical domains with various casings and whitespaces', () => {
      // 匯入資料
      expect(mapDomainToCategory('case_import')).toBe('匯入資料');
      expect(mapDomainToCategory('CASE_IMPORT')).toBe('匯入資料');
      expect(mapDomainToCategory('  case_import  ')).toBe('匯入資料');
      expect(mapDomainToCategory('finance_import')).toBe('匯入資料');
      expect(mapDomainToCategory('FINANCE_IMPORT')).toBe('匯入資料');

      // 媒合推播
      expect(mapDomainToCategory('line')).toBe('媒合推播');
      expect(mapDomainToCategory('LINE')).toBe('媒合推播');
      expect(mapDomainToCategory('line_integration')).toBe('媒合推播');
      expect(mapDomainToCategory('LINE_INTEGRATION')).toBe('媒合推播');
      expect(mapDomainToCategory('matching')).toBe('媒合推播');
      expect(mapDomainToCategory('MATCHING')).toBe('媒合推播');

      // 排班調度
      expect(mapDomainToCategory('scheduling')).toBe('排班調度');
      expect(mapDomainToCategory('SCHEDULING')).toBe('排班調度');
      expect(mapDomainToCategory('assignments')).toBe('排班調度');
      expect(mapDomainToCategory('ASSIGNMENTS')).toBe('排班調度');

      // 客戶帳務
      expect(mapDomainToCategory('client_finance')).toBe('客戶帳務');
      expect(mapDomainToCategory('CLIENT_FINANCE')).toBe('客戶帳務');

      // 月嫂薪資
      expect(mapDomainToCategory('staff_payables')).toBe('月嫂薪資');
      expect(mapDomainToCategory('STAFF_PAYABLES')).toBe('月嫂薪資');
      expect(mapDomainToCategory('payroll')).toBe('月嫂薪資');
      expect(mapDomainToCategory('PAYROLL')).toBe('月嫂薪資');

      // 政府補助
      expect(mapDomainToCategory('government_subsidy')).toBe('政府補助');
      expect(mapDomainToCategory('GOVERNMENT_SUBSIDY')).toBe('政府補助');
    });

    it('[Category-2] Falls back gracefully to "其他" for empty, null, undefined or unknown domains', () => {
      expect(mapDomainToCategory('')).toBe('其他');
      expect(mapDomainToCategory('   ')).toBe('其他');
      expect(mapDomainToCategory(null)).toBe('其他');
      expect(mapDomainToCategory(undefined)).toBe('其他');
      expect(mapDomainToCategory('unknown_domain')).toBe('其他');
      expect(mapDomainToCategory('audit_log')).toBe('其他');
      expect(mapDomainToCategory('security_event')).toBe('其他');
    });
  });

  // ==========================================================================
  // Section 4: Import Warning Isolation Challenge (6 Distinct Statuses)
  // ==========================================================================
  describe('Import Warning Status & Contract Isolation Challenge', () => {
    const importWarningStatuses: ImportWarningTrackingStatus[] = [
      'open',
      'awaiting_external_confirmation',
      'response_recorded',
      'reimport_requested',
      'closed',
      'auto_resolved',
    ];


    it('[Isolation-1] Import Warning defines exactly 6 distinct tracking statuses', () => {
      expect(importWarningStatuses.length).toBe(6);
      const uniqueStatuses = new Set(importWarningStatuses);
      expect(uniqueStatuses.size).toBe(6);
    });

    it('[Isolation-2] Status labels for Import Warning are distinct and mapped without conflation', () => {
      const labels = importWarningStatuses.map((st) => mapImportWarningStatusLabel(st));

      expect(labels).toEqual([
        '待處理',
        '等待外部確認',
        '已記錄回應',
        '要求重新匯入',
        '已結案',
        '自動排除',
      ]);

      // Ensure no undefined or fallback strings in canonical list
      for (const label of labels) {
        expect(label).toBeTruthy();
        expect(typeof label).toBe('string');
      }

      // Check contrast with Anomaly labels:
      // Anomaly uses "✅ 已排除" for resolved, whereas Import Warning uses "已結案" (closed) and "自動排除" (auto_resolved)
      expect(mapImportWarningStatusLabel('closed')).toBe('已結案');
      expect(mapImportWarningStatusLabel('auto_resolved')).toBe('自動排除');
      expect(mapImportWarningStatusLabel('closed')).not.toBe('✅ 已排除');
      expect(mapImportWarningStatusLabel('auto_resolved')).not.toBe('✅ 已排除');
    });

    it('[Isolation-3] adaptImportWarningTask accurately preserves and isolates all 6 statuses', () => {
      for (const status of importWarningStatuses) {
        const dto: ImportWarningTaskView = {
          occurrence_identity: `import-warning:test-${status}`,
          owning_lane: 'hcm',
          logical_code: 'TEST-CODE',
          field_path: '身分證字號',
          masked_subject: 'A12****789',
          issue_codes: ['code_1'],
          tracking_status: status,
          tracking_version: 1,
          evidence_reference: 'ref-123',
          display_message: `測試訊息 - ${status}`,
          navigation_action: 'hcm_import_center',
        };

        const adapted = adaptImportWarningTask(dto);

        // Verification of status isolation
        expect(adapted.status).toBe(status);
        expect(adapted.statusLabel).toBe(mapImportWarningStatusLabel(status));
        expect(adapted.occurrenceIdentity).toBe(`import-warning:test-${status}`);
        expect(adapted.navigationAction).toBe('hcm_import_center');
      }
    });

    it('[Isolation-4] Import Warning Navigation Actions (5 targets) are isolated from Anomaly Navigation', () => {
      const navigationActions: ImportWarningNavigationAction[] = [
        'hcm_import_center',
        'historical_order_import_center',
        'client_beclass_import_center',
        'staff_beclass_import_center',
        'finance_import_recovery_center',
      ];

      for (const nav of navigationActions) {
        const dto: ImportWarningTaskView = {
          occurrence_identity: `import-warning:nav-${nav}`,
          owning_lane: 'beclass',
          logical_code: 'NAV-TEST',
          field_path: '欄位',
          masked_subject: 'SUBJ',
          issue_codes: ['code_nav'],
          tracking_status: 'open',
          tracking_version: 1,
          evidence_reference: null,
          display_message: '導航測試',
          navigation_action: nav,
        };

        const adapted = adaptImportWarningTask(dto);
        expect(adapted.navigationAction).toBe(nav);
        // Ensure no staff_calendar_navigation contamination
        expect((adapted as any).staffCalendarNavigation).toBeUndefined();
      }
    });

    it('[Isolation-5] Anomaly Summary ViewModel does NOT contain Import Warning properties', () => {
      const anomalyDto: AnomalySummaryView = {
        fingerprint: '1'.repeat(64),
        definition_code: 'ANOM-ISO',
        source_domain: 'scheduling',
        source_identity: 'identity-1',
        source_version: 1,
        severity: 'blocking',
        predicate_active: true,
        workflow_status: 'open',
        workflow_version: 1,
        display_snapshot: null,
        staff_calendar_navigation: {
          staff_id: 99,
          target_date: '2026-08-20',
        },
      };

      const adaptedAnomaly = adaptAnomalySummary(anomalyDto);

      // Verify absence of Import Warning properties
      expect((adaptedAnomaly as any).occurrenceIdentity).toBeUndefined();
      expect((adaptedAnomaly as any).owningLane).toBeUndefined();
      expect((adaptedAnomaly as any).laneLabel).toBeUndefined();
      expect((adaptedAnomaly as any).logicalCode).toBeUndefined();
      expect((adaptedAnomaly as any).fieldPath).toBeUndefined();
      expect((adaptedAnomaly as any).maskedSubject).toBeUndefined();
      expect((adaptedAnomaly as any).issueCodes).toBeUndefined();
      expect((adaptedAnomaly as any).navigationAction).toBeUndefined();
    });
  });

  // ==========================================================================
  // Section 5: Adapt Anomaly Summary Integrity & Typed Source Projection Tests
  // ==========================================================================
  describe('adaptAnomalySummary Robustness & Typed Source Projection', () => {
    it('[Adapter-1] projects only typed source facts when display snapshot is absent', () => {
      const dto: AnomalySummaryView = {
        fingerprint: 'e'.repeat(64),
        definition_code: 'GAP-TEST-001',
        source_domain: 'unknown_source',
        source_identity: 'src:42',
        source_version: 5,
        severity: 'warning',
        predicate_active: false,
        workflow_status: 'resolved',
        workflow_version: 3,
        display_snapshot: null,
        staff_calendar_navigation: null,
      };

      const adapted = adaptAnomalySummary(dto);

      expect(adapted.title).toBe('其他待處理事項');
      expect(adapted.description).toBe('請核對其他相關資料的目前資料與可採取的處理方式。');
      expect(adapted.relatedEntity).toBe('其他相關資料');
      expect(adapted.suggestedAction).toBe('開啟詳情查看可執行的處置。');
      expect(adapted.rootEvidence).toBe('影響對象：其他相關資料');
      expect(adapted.category).toBe('其他');
      expect(adapted.status).toBe('✅ 已排除');
      expect(adapted.severity).toBe('🟡 警示待補');
      expect(adapted.staffCalendarNavigation).toBeNull();
    });

    it('[Adapter-2] Formats blocking & claimed correctly', () => {
      const dto: AnomalySummaryView = {
        fingerprint: 'f'.repeat(64),
        definition_code: 'CLAIMED-BLOCKING',
        source_domain: 'payroll',
        source_identity: 'payroll:123',
        source_version: 1,
        severity: 'blocking',
        predicate_active: true,
        workflow_status: 'claimed',
        workflow_version: 2,
        display_snapshot: null,
        staff_calendar_navigation: null,
      };

      const adapted = adaptAnomalySummary(dto);

      expect(adapted.severity).toBe('🔴 嚴重阻擋');
      expect(adapted.severityClass).toBe('critical');
      expect(adapted.status).toBe('🔵 已認領');
      expect(adapted.category).toBe('月嫂薪資');
      expect(adapted.rawSeverity).toBe('blocking');
      expect(adapted.rawWorkflowStatus).toBe('claimed');
    });
  });
});
