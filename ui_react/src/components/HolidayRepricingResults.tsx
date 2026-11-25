import type { HolidayCaseRepricing } from '../api/scheduling/holiday_schemas';

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

function amount(value: number | null | undefined): string {
  return value == null ? '待確認' : `NT$ ${value.toLocaleString()}`;
}

export function HolidayRepricingResults({ results }: { results: readonly HolidayCaseRepricing[] }) {
  return <details className="holiday-accounting-results">
    <summary>帳務處理結果{results.some(item => item.outcome === 'failed' || item.outcome === 'blocked')
      ? '，有案件未重算' : ''}</summary>
    {results.length === 0 ? <p>此回執尚無逐案處理紀錄。</p> : <ul>{results.map(item => <li key={item.case_no}>
      <strong>{item.case_no}</strong>：{outcomeLabels[item.outcome]}
      {item.reason_code && <span>，原因：{item.reason_code}</span>}
      {(item.case_total_amount != null || item.staff_payable_amount != null) && <p>
        重算案件總額 {amount(item.case_total_amount)}；月嫂應付 {amount(item.staff_payable_amount)}；
        客戶應收 {amount(item.client_receivable_amount)}；補助 {amount(item.subsidy_amount)}
      </p>}
      {item.missing_mapping && item.missing_mapping.length > 0 && <p>缺少歸屬資料：{item.missing_mapping.join("；")}</p>}
      {item.unallocated_amount != null && <p>待人工對帳差額 {amount(item.unallocated_amount)}{item.unallocated_amount > 0 ? "，負擔歸屬待確認。" : "。"}</p>}
    </li>)}</ul>}
  </details>;
}
