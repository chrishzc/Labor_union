"""MySQL read adapter for performance; roots and pricing remain with their owners."""
from datetime import date
from decimal import Decimal

from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
from subsystems.client_finance.pricing_configuration import case_total_amount
from subsystems.reporting.staff_performance_query import (
    PerformanceCaseOpening, PerformanceHistoricalAssignment, PerformanceServiceDay, PerformanceStaff,
)
from domains.scheduling.assignment_plan import (
    OpeningAssignmentIdentity, OpeningAssignmentLineage,
    OpeningSubstitutionIdentity, resolve_opening_primary_staff,
)


_SERVICE_FROM = """
FROM case_staff_assignments a
JOIN scheduling_generations g ON g.id=a.generation_id AND g.effective_marker=1
JOIN staff_schedule ss ON ss.assignment_id=a.id AND ss.generation_id=a.generation_id
    AND ss.effective_marker=1 AND ss.is_work_day=1
JOIN orders o ON o.case_no=a.case_no
WHERE a.status NOT IN ('cancelled','replaced')
"""

_HISTORICAL_OPENING_FROM = """
FROM orders h
JOIN historical_order_adoption_receipts r ON r.id=(
    SELECT MAX(receipt.id) FROM historical_order_adoption_receipts receipt
    WHERE receipt.case_no=h.case_no AND receipt.outcome='adopted')
JOIN historical_order_pairing_evidence p ON p.receipt_id=r.id
    AND h.actual_start_date BETWEEN p.source_start_date AND p.source_end_date
LEFT JOIN case_staff_assignments historical_assignment
    ON historical_assignment.id=p.assignment_id AND historical_assignment.case_no=h.case_no
    AND historical_assignment.staff_id=p.staff_id
    AND historical_assignment.status NOT IN ('cancelled','replaced')
WHERE h.status IN ('歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成')
AND NOT EXISTS (SELECT 1 """ + _SERVICE_FROM + """ AND o.case_no=h.case_no)
"""

_HISTORICAL_OPENING_GROUP = """
GROUP BY h.case_no,h.actual_start_date
HAVING COUNT(DISTINCT p.staff_id)=1 AND COUNT(p.staff_id)=COUNT(*)
    AND COUNT(historical_assignment.id)>0
"""

_HISTORICAL_OPENING_SELECT = """
SELECT h.case_no,h.actual_start_date,MIN(p.staff_id) AS primary_staff_id,MAX(r.id) AS receipt_id
"""

_HISTORICAL_ASSIGNMENTS_FROM = """
FROM (""" + _HISTORICAL_OPENING_SELECT + _HISTORICAL_OPENING_FROM + _HISTORICAL_OPENING_GROUP + """) opening
JOIN orders h ON h.case_no=opening.case_no
JOIN clients c ON c.id=h.client_id
JOIN case_staff_assignments a ON a.case_no=h.case_no AND a.generation_id IS NULL
    AND a.status IN ('planned','active','completed')
LEFT JOIN historical_service_day_projections d ON d.case_no=h.case_no
LEFT JOIN historical_service_day_items i ON i.event_id=d.current_event_id
    AND i.assignment_id=a.id AND i.staff_id=a.staff_id
WHERE h.service_hours_per_day>0 AND a.assigned_end_date>=a.assigned_start_date
AND (i.actual_service_days>0 OR (d.current_event_id IS NULL AND EXISTS (
    SELECT 1 FROM historical_order_pairing_evidence p
    WHERE p.receipt_id=opening.receipt_id AND p.assignment_id=a.id AND p.staff_id=a.staff_id
)))
"""


class MySqlStaffPerformanceQueryRepository:
    def __init__(self, connection):
        self._connection = connection

    def list_staff(self):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id,union_no,name FROM staff ORDER BY id")
            return tuple(PerformanceStaff(int(row["id"]), row["union_no"], str(row["name"] or "未命名月嫂")) for row in cursor.fetchall())

    def list_years(self):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT YEAR(ss.work_date) AS service_year " + _SERVICE_FROM
                + " UNION SELECT YEAR(o.actual_start_date) AS service_year " + _SERVICE_FROM
                + " AND o.actual_start_date IS NOT NULL"
                + " UNION SELECT YEAR(h.actual_start_date) AS service_year "
                + _HISTORICAL_OPENING_FROM + _HISTORICAL_OPENING_GROUP + " ORDER BY service_year DESC")
            years = {int(row["service_year"]) for row in cursor.fetchall()}
            cursor.execute("SELECT DISTINCT YEAR(a.assigned_start_date) AS first_year,"
                           "YEAR(a.assigned_end_date) AS last_year " + _HISTORICAL_ASSIGNMENTS_FROM)
            for row in cursor.fetchall():
                years.update(range(int(row["first_year"]), int(row["last_year"]) + 1))
            return tuple(sorted(years, reverse=True))

    def list_case_openings(self, start: date, end: date, service_cases: tuple[str, ...]):
        scheduled = self._list_scheduled_openings(start, end, service_cases)
        service_filter = " OR h.case_no IN (" + ",".join("%s" for _ in service_cases) + ")" if service_cases else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _HISTORICAL_OPENING_SELECT + _HISTORICAL_OPENING_FROM
                + " AND (h.actual_start_date BETWEEN %s AND %s" + service_filter + ") " + _HISTORICAL_OPENING_GROUP,
                (start, end, *service_cases),
            )
            historical = tuple(
                PerformanceCaseOpening(str(row["case_no"]), row["actual_start_date"], int(row["primary_staff_id"]))
                for row in cursor.fetchall()
            )
        return scheduled + historical

    def _list_scheduled_openings(self, start: date, end: date, service_cases: tuple[str, ...]):
        """Read exact opening principal from formal order/assignment lineage.

        The first current segment survives handover of the remaining service.
        Daily substitution and same-person rebuild history recover its principal
        even if the first service date itself was covered by a substitute.
        """
        service_filter = " OR o.case_no IN (" + ",".join("%s" for _ in service_cases) + ")" if service_cases else ""
        with self._connection.cursor() as cursor:
            cursor.execute("""SELECT o.case_no,o.actual_start_date,a.id AS first_assignment_id
                FROM orders o
                JOIN scheduling_generations g ON g.case_no=o.case_no AND g.effective_marker=1
                JOIN case_staff_assignments a ON a.generation_id=g.id AND a.case_no=o.case_no
                WHERE a.status NOT IN ('cancelled','replaced')
                AND a.assignment_sequence=(SELECT MIN(first.assignment_sequence)
                    FROM case_staff_assignments first WHERE first.generation_id=g.id
                    AND first.status NOT IN ('cancelled','replaced'))
                AND ((o.actual_start_date BETWEEN %s AND %s)""" + service_filter + """ )
                AND EXISTS (SELECT 1 FROM staff_schedule d WHERE d.generation_id=g.id
                    AND d.effective_marker=1 AND d.is_work_day=1 AND d.work_date<=%s)
                ORDER BY o.case_no""", (start, end, *service_cases, end))
            cases = tuple(cursor.fetchall())
            if not cases:
                return ()
            case_nos = tuple(str(row["case_no"]) for row in cases)
            placeholders = ",".join("%s" for _ in case_nos)
            cursor.execute("""SELECT a.case_no,a.id,a.staff_id,a.assignment_sequence,
                MIN(d.work_date) AS first_service_date FROM case_staff_assignments a
                LEFT JOIN staff_schedule d ON d.assignment_id=a.id AND d.generation_id=a.generation_id AND d.is_work_day=1
                WHERE a.case_no IN (""" + placeholders + """ )
                GROUP BY a.case_no,a.id,a.staff_id,a.assignment_sequence""", case_nos)
            assignment_rows = tuple(cursor.fetchall())
            cursor.execute("""SELECT a.case_no,l.old_assignment_identity,l.new_assignment_id
                FROM scheduling_rebuild_lineage l JOIN case_staff_assignments a ON a.id=l.new_assignment_id
                WHERE a.case_no IN (""" + placeholders + ")", case_nos)
            lineage_rows = tuple(cursor.fetchall())
            cursor.execute("""SELECT r.case_no,o.original_assignment_id,o.original_work_date,
                o.resulting_assignment_id,o.resulting_service_date
                FROM scheduling_leave_substitution_receipts r
                JOIN scheduling_leave_substitution_outcomes o ON o.batch_key=r.batch_key
                WHERE r.case_no IN (""" + placeholders + """ )
                AND o.resulting_assignment_id IS NOT NULL AND o.resulting_service_date IS NOT NULL""", case_nos)
            outcome_rows = tuple(cursor.fetchall())
        result = []
        for case in cases:
            case_no = str(case["case_no"])
            assignments = tuple(OpeningAssignmentIdentity(int(row["id"]), int(row["staff_id"]), int(row["assignment_sequence"]), row["first_service_date"])
                                for row in assignment_rows if row["case_no"] == case_no)
            lineage = []
            for row in lineage_rows:
                if row["case_no"] != case_no:
                    continue
                prefix, separator, identity = str(row["old_assignment_identity"]).partition(":")
                if prefix != "assignment" or not separator or not identity.isdecimal():
                    raise ValueError("opening_assignment_lineage_invalid")
                lineage.append(OpeningAssignmentLineage(int(identity), int(row["new_assignment_id"])))
            substitutions = tuple(OpeningSubstitutionIdentity(int(row["original_assignment_id"]), row["original_work_date"],
                int(row["resulting_assignment_id"]), row["resulting_service_date"]) for row in outcome_rows if row["case_no"] == case_no)
            primary_staff_id = resolve_opening_primary_staff(int(case["first_assignment_id"]), assignments, tuple(lineage), substitutions)
            result.append(PerformanceCaseOpening(case_no, case["actual_start_date"], primary_staff_id))
        return tuple(result)

    def list_service_days(self, start: date, end: date):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT a.staff_id,a.case_no,ss.work_date,o.service_hours_per_day " + _SERVICE_FROM
                + " AND ss.work_date BETWEEN %s AND %s ORDER BY ss.work_date,a.staff_id,a.case_no", (start, end))
            result = []
            for row in cursor.fetchall():
                value = row["service_hours_per_day"]
                hours = None if value is None else Decimal(str(value))
                if hours is not None and (not hours.is_finite() or hours <= 0 or hours * 2 != (hours * 2).to_integral_value()):
                    raise ValueError("staff_performance_hours_invalid")
                result.append(PerformanceServiceDay(int(row["staff_id"]), str(row["case_no"]), row["work_date"], None if hours is None else float(hours)))
            return tuple(result)

    def list_historical_assignments(self, start: date, end: date):
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT h.case_no,h.actual_start_date,h.service_days,h.service_hours_per_day,
                c.service_type,a.staff_id,a.assigned_start_date,a.assigned_end_date,i.actual_service_days """
                + _HISTORICAL_ASSIGNMENTS_FROM + """
                AND opening.actual_start_date<=%s AND EXISTS (
                    SELECT 1 FROM case_staff_assignments span WHERE span.case_no=h.case_no
                    AND span.assigned_start_date<=%s AND span.assigned_end_date>=%s
                )
                """,
                (end, end, start),
            )
            return tuple(
                PerformanceHistoricalAssignment(
                    int(row["staff_id"]), str(row["case_no"]),
                    max(row["assigned_start_date"], row["actual_start_date"]), row["assigned_end_date"],
                    row["service_type"], float(row["service_hours_per_day"]), int(row["service_days"] or 0),
                    None if row["actual_service_days"] is None else int(row["actual_service_days"]),
                )
                for row in cursor.fetchall() if row["assigned_end_date"] >= row["actual_start_date"]
            )

    def case_amounts(self, case_nos: tuple[str, ...]):
        repository = MySqlPricingConfigurationRepository(self._connection)
        result = {}
        for case_no in case_nos:
            try:
                result[case_no] = case_total_amount(repository.case(case_no))
            except ValueError as exc:
                if str(exc) not in {
                    "case_pricing_service_facts_required",
                    "case_pricing_payroll_snapshot_required",
                    "case_pricing_identity_not_confirmed",
                    "client_finance_bootstrap_required",
                    "historical_pricing_unique_assignment_required",
                    "historical_client_payment_terms_missing",
                    "historical_payroll_rate_policy_missing",
                    "historical_order_completion_date_missing",
                }:
                    raise
                result[case_no] = None
        return result
