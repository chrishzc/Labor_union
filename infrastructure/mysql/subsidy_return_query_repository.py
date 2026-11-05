"""Read customer subsidy-return case facts in one bounded snapshot query."""

from decimal import Decimal
from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule
from infrastructure.mysql.pricing_configuration_repository import CASE_PRICING_FACTS_SQL

from subsystems.client_finance.subsidy_return_query import SubsidyReturnCaseFacts


class MySqlSubsidyReturnQueryRepository:
    def __init__(self, connection):
        self._connection = connection

    def query_facts(self, *, after_case_no, case_no, search, limit):
        conditions = ["(c.identity_status IN ('一般市民','補助市民','社福','低收入戶','中低收入戶') OR pricing.pricing_rule='citizen')"]
        values = []
        if after_case_no:
            conditions.append('o.case_no > %s')
            values.append(after_case_no)
        if case_no:
            conditions.append('o.case_no = %s')
            values.append(case_no)
        if search:
            conditions.append('(LOCATE(%s,o.case_no)>0 OR LOCATE(%s,c.name)>0)')
            values.extend((search, search))
        values.append(limit)
        sql = _SELECT + ' WHERE ' + ' AND '.join(conditions) + ' ORDER BY o.case_no LIMIT %s'
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(values))
            rows = cursor.fetchall()
        return tuple(_facts(row) for row in rows)


def _facts(row):
    hours = row['actual_service_hours']
    if hours is None and row['service_days'] is not None and row['service_hours_per_day'] is not None:
        hours = Decimal(str(row['service_days'])) * Decimal(str(row['service_hours_per_day']))
    return SubsidyReturnCaseFacts(
        row['case_no'], row['client_name'], row['order_status'], row['identity_status'],
        None if hours is None else Decimal(str(hours)),
        None if row['floor_fee'] is None else Decimal(str(row['floor_fee'])),
        row['client_hourly_rate_ntd'], row['actual_end_date'],
        bool(row['return_count']),
        None if not row['open_return_count'] else int(row['formal_amount_ntd']),
        row['formal_due_date'] if row['due_date_count'] == 1 and not row['missing_due_count'] else None,
        bool(row['return_count']) and row['settled_return_count'] == row['return_count'],
        _pricing(row),
    )


def _pricing(row):
    if not row.get('pricing_active'):
        return None
    return CasePricingTerms(row['identity_status'], IdentityRule(row['pricing_rule']),
        Decimal(str(row['pricing_subsidy_hours'])),
        HourlyRates(int(Decimal(str(row['pricing_client_covered']))), int(Decimal(str(row['pricing_client_excess'])))),
        HourlyRates(int(Decimal(str(row['pricing_payroll_covered']))), int(Decimal(str(row['pricing_payroll_excess'])))))


_SELECT = f"""
SELECT o.case_no,c.name AS client_name,o.status AS order_status,c.identity_status,
       pricing.pricing_active,pricing.pricing_rule,pricing.pricing_subsidy_hours,
       pricing.pricing_client_covered,pricing.pricing_client_excess,
       pricing.pricing_payroll_covered,pricing.pricing_payroll_excess,
       o.service_days,o.service_hours_per_day,
       COALESCE(day_event.historical_floor_fee_ntd,o.floor_fee) AS floor_fee,
       day_projection.total_actual_service_hours AS actual_service_hours,
       terms.client_hourly_rate_ntd,COALESCE(o.actual_end_date,o.end_date) AS actual_end_date,
       COALESCE(payable.return_count,0) AS return_count,
       COALESCE(payable.open_return_count,0) AS open_return_count,
       COALESCE(payable.settled_return_count,0) AS settled_return_count,
       payable.formal_amount_ntd,payable.formal_due_date,payable.due_date_count,payable.missing_due_count
FROM orders o JOIN clients c ON c.id=o.client_id
LEFT JOIN ({CASE_PRICING_FACTS_SQL}) pricing ON pricing.case_no=o.case_no
LEFT JOIN client_payment_terms terms ON terms.case_no=o.case_no
LEFT JOIN historical_service_day_projections day_projection ON day_projection.case_no=o.case_no
LEFT JOIN historical_service_day_events day_event ON day_event.id=day_projection.current_event_id
LEFT JOIN (
  SELECT case_no,COUNT(*) AS return_count,
         SUM(status='open') AS open_return_count,SUM(status='settled') AS settled_return_count,
         SUM(CASE WHEN status='open' THEN amount_due_ntd ELSE 0 END) AS formal_amount_ntd,
         MIN(CASE WHEN status='open' THEN due_date END) AS formal_due_date,
         COUNT(DISTINCT CASE WHEN status='open' THEN due_date END) AS due_date_count,
         SUM(status='open' AND due_date IS NULL) AS missing_due_count
  FROM client_obligations WHERE obligation_type='subsidy_return' AND direction='payable_to_client'
  GROUP BY case_no
) payable ON payable.case_no=o.case_no
"""
