import type { HolidayCaseRepricing } from '../api/scheduling/holiday_schemas';
import './HolidayRepricingResults.css';

const outcomeLabels: Record<HolidayCaseRepricing['outcome'], string> = {
  repriced: '已重算',
  repriced_funding_pending: '已重算，差額待人工對帳',
  preserved_cash_history: '已有正式收付，保留原帳',
  historical_excluded: '歷史來源，不適用雙倍',
  funding_decision_pending: '尚未重算，資金條件待確認',
  unchanged: '不需更動',
  blocked: '未重算',
  failed: '重算失敗',
};

const reasonLabels: Readonly<Partial<Record<string, string>>> = {
  formal_cash_history_exists: '已有正式收付，保留兩邊原帳',
  historical_source_excluded: '歷史來源不適用雙倍計價',
  holiday_service_attribution_ambiguous: '實際服務時數無法唯一對應原財務歸屬',
  pricing_amounts_unchanged: '核對後金額沒有變更',
  holiday_funding_assignment_pending: '服務費已重算，新增差額尚未指定負擔方',
  service_facts_unavailable: '缺少可計價的正式服務資料',
  holiday_recalculation_failed: '帳務重算未完成，請核對處理原因',
};

const mappingLabels: Readonly<Partial<Record<string, string>>> = {
  per_financial_source_to_target_hour_mapping: '每筆原財務來源到調整後服務日期的時數對應',
};

function amount(value: number | null | undefined): string {
  return value == null ? '待確認' : `NT$ ${value.toLocaleString()}`;
}

export function HolidayRepricingResults({ results }: { results: readonly HolidayCaseRepricing[] }) {
  return <details className="holiday-accounting-results">
    <summary>帳務處理結果{results.some(item => item.outcome === 'failed' || item.outcome === 'blocked')
      ? '，有案件未重算' : ''}</summary>
    {results.length === 0 ? <p>此回執尚無逐案處理紀錄。</p> : <ul className="holiday-accounting-results-list">{results.map(item => <li
      className={`holiday-accounting-result${item.outcome === 'failed' || item.outcome === 'blocked' ? ' is-failed' : ''}`}
      key={item.case_no}>
      <div className="holiday-accounting-result-heading">
        <strong>{item.case_no}</strong>
        <span className="holiday-accounting-result-status">{outcomeLabels[item.outcome]}</span>
      </div>
      {item.reason_code && <p>原因：{reasonLabels[item.reason_code] ?? item.reason_code}
        {reasonLabels[item.reason_code] && <> <code>{item.reason_code}</code></>}
      </p>}
      {(item.case_total_amount != null || item.staff_payable_amount != null) && <p>
        重算案件總額 {amount(item.case_total_amount)}；月嫂應付 {amount(item.staff_payable_amount)}；
        客戶應收 {amount(item.client_receivable_amount)}；補助 {amount(item.subsidy_amount)}
      </p>}
      {item.missing_mapping && item.missing_mapping.length > 0 && <p>缺少歸屬資料：{item.missing_mapping.map((mapping, index) => <span key={mapping}>
        {index > 0 && '；'}{mappingLabels[mapping] ?? mapping}
        {mappingLabels[mapping] && <> <code>{mapping}</code></>}
      </span>)}</p>}
      {item.unallocated_amount != null && <p>待人工對帳差額 {amount(item.unallocated_amount)}{item.unallocated_amount > 0 ? "，負擔歸屬待確認。" : "。"}</p>}
    </li>)}</ul>}
  </details>;
}
