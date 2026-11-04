"""MySQL read adapter for performance; roots and pricing remain with their owners."""
from datetime import date
from decimal import Decimal

from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
from subsystems.client_finance.pricing_configuration import case_total_amount
from subsystems.reporting.staff_performance_query import PerformanceServiceDay, PerformanceStaff
from subsystems.reporting.staff_performance_query import PerformanceCaseOpening
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
                + " AND o.actual_start_date IS NOT NULL ORDER BY service_year DESC")
            return tuple(int(row["service_year"]) for row in cursor.fetchall())

    def list_case_openings(self, start: date, end: date, service_cases: tuple[str, ...]):
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

    def case_amounts(self, case_nos: tuple[str, ...]):
        repository = MySqlPricingConfigurationRepository(self._connection)
        result = {}
        for case_no in case_nos:
            try:
                result[case_no] = case_total_amount(repository.case(case_no))
            except ValueError as exc:
                if str(exc) not in {"case_pricing_service_facts_required", "case_pricing_payroll_snapshot_required", "case_pricing_identity_not_confirmed"}:
                    raise
                result[case_no] = None
        return result
