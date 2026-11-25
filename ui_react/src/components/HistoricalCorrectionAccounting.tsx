import { historicalPendingLabel, type HistoricalRepricingPlan } from '../api/client_finance/accounting_pricing_client';

const amount = (value: number | null): string => value === null ? '待核對' : `NT$ ${value.toLocaleString('zh-TW')}`;

export function HistoricalAccountingPending({ pending }: { pending: readonly string[] }) {
  if (!pending.length) return null;
  return <div role="status"><strong>待核對帳務</strong><ul>{pending.map(code => (
    <li key={code}>{historicalPendingLabel(code)}</li>
  ))}</ul></div>;
}

export function HistoricalCorrectionAccounting({ impact }: { impact: HistoricalRepricingPlan }) {
  const confirmedUpdates = [...impact.client_updates, ...impact.staff_updates].filter(update => update.before_effective !== update.effective);
  return <section aria-label="帳務影響">
    <dl>
      <div><dt>客戶應收計算差額</dt><dd>{amount(impact.client_delta)}</dd></div>
      <div><dt>補助退還計算差額</dt><dd>{amount(impact.subsidy_delta)}</dd></div>
    </dl>
    {impact.client_exempt && <p>本案已確認免自備，無須新增客戶期款。</p>}
    {!!impact.persons.length && <table className="pricing-table">
      <thead><tr><th>月嫂</th><th>服務時數</th><th>更正前應付計算額</th><th>更正後應付計算額</th><th>差額</th></tr></thead>
      <tbody>{impact.persons.map(person => <tr key={person.assignment_identity}>
        <th scope="row">{person.staff_name}</th>
        <td>{person.hours ?? '待核對'}</td>
        <td>{amount(person.before_amount)}</td>
        <td>{amount(person.after_amount)}</td>
        <td>{amount(person.delta)}</td>
      </tr>)}</tbody>
    </table>}
    {!!confirmedUpdates.length && <table className="pricing-table">
      <caption>可套用至原款項的有效金額</caption>
      <thead><tr><th>原款項識別</th><th>更正前有效額</th><th>更正後有效額</th><th>差額</th></tr></thead>
      <tbody>{confirmedUpdates.map(update => <tr key={update.identity}>
        <th scope="row">{update.identity}</th>
        <td>{amount(update.before_effective)}</td>
        <td>{amount(update.effective)}</td>
        <td>{amount(update.effective - update.before_effective)}</td>
      </tr>)}</tbody>
    </table>}
    <HistoricalAccountingPending pending={impact.pending} />
  </section>;
}
