/**
 * File: subsidy_report_query_adapter.ts
 * Description: 將季度、年度與週報共用的補助分區映射為唯讀 view，不重算公式或 aggregates。
 */
import type { SubsidyReportPartition, SubsidyReportPreview } from '../../api/reports/subsidy_report_query_schemas';

export function adaptSubsidyPartitions(partitions: readonly SubsidyReportPartition[]) {
  return partitions.map((partition) => ({
    kind: partition.citizen_kind,
    rowCount: partition.row_count,
    totalAmount: `NT$ ${partition.total_amount_ntd.toLocaleString()}`,
    rows: partition.rows.map((row) => ({
      serial: row.serial_number,
      caseNo: row.case_no,
      eligibility: row.eligibility,
      serviceRange: `${row.service_start} ~ ${row.service_end}`,
      subsidyHours: String(row.subsidy_hours),
      subsidyDays: String(row.subsidy_days),
      serviceDays: row.service_days,
      amount: `NT$ ${row.subsidy_amount_ntd.toLocaleString()}`,
      unitPrice: `NT$ ${row.unit_price_ntd.toLocaleString()}`,
      employer: row.employer_name,
      staff: row.staff_name,
      identity: row.identity_card,
      address: row.address,
    })),
  }));
}

export function adaptSubsidyReport(source: SubsidyReportPreview) {
  return {
    kind: source.period_kind,
    year: source.application_year,
    quarter: source.quarter,
    generatedAt: source.generated_at,
    revision: source.source_revision,
    totalRows: source.total_row_count,
    totalAmount: `NT$ ${source.total_amount_ntd.toLocaleString()}`,
    partitions: adaptSubsidyPartitions(source.partitions),
  };
}
