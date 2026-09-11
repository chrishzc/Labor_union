/**
 * File: weekly_operations_report_adapter.ts
 * Description: 將營運週報 strict view 映射為三分頁顯示資料，保留 null 與 typed 資料品質狀態。
 */
import type { WeeklyOperationsReport } from '../../api/reports/weekly_operations_report_schemas';
import { adaptSubsidyRow } from './subsidy_report_query_adapter';

const REVIEW_LABELS: Record<WeeklyOperationsReport['case_rows'][number]['review_result'], string> = {
  general_eligible: '一般符合',
  subsidized_eligible: '補助符合',
  rejected_unpartitioned: '不符合（待分流）',
  pending: '審核中',
};

export function displayWeeklyMetric(value: number | null): string {
  return value === null ? '未登錄／待補正' : value.toLocaleString();
}

export function displayWeeklyValue(value: string | number | null): string {
  return value === null || value === '' ? '未登錄／待補正' : String(value);
}

export function adaptWeeklyOperationsReport(source: WeeklyOperationsReport) {
  const subsidyTotalRows = source.subsidy_partitions.reduce((sum, partition) => sum + partition.row_count, 0);
  const subsidyTotalAmount = source.subsidy_partitions.reduce((sum, partition) => sum + partition.total_amount_ntd, 0);
  const subsidyPartitions = source.subsidy_partitions.map((partition) => ({
    kind: partition.citizen_kind,
    rowCount: partition.row_count,
    totalAmount: `NT$ ${partition.total_amount_ntd.toLocaleString()}`,
    rows: partition.rows.map((row) => ({
      ...adaptSubsidyRow(row),
      annualIdentity: `(${row.application_roc_year ?? '—'})${partition.citizen_kind === 'general' ? '一般市民' : '社福補助'}`,
      annualEntry: row.serial_number,
      notes: row.notes,
      reconciliationStatus: row.reconciliation_status || '結案',
      claimPeriodLabel: row.claim_period_label,
    })),
  }));
  return {
    period: source.period,
    generatedAt: source.generated_at,
    revision: source.source_revision,
    summary: source.summary,
    caseRows: source.case_rows.map((row) => ({
      ...row,
      reviewLabel: REVIEW_LABELS[row.review_result],
    })),
    subsidy: {
      totalRows: subsidyTotalRows,
      totalAmount: `NT$ ${subsidyTotalAmount.toLocaleString()}`,
      partitions: subsidyPartitions,
    },
    serviceRows: source.service_rows,
    weeklyMetrics: source.weekly_metrics,
    dataQualityIssues: source.data_quality_issues,
  };
}
