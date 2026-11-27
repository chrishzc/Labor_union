"""CI-only synthetic MySQL comparison; never connect to an application database.

Run from a checkout of Labor_union with PyMySQL installed. This is an adapter
microbenchmark, not a browser/API end-to-end acceptance test.
"""
from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

import pymysql
from pymysql.cursors import DictCursor


BASE = "e6bc4adc1919127884b7672c62adaff650188ec3"
REPOSITORY = "infrastructure/mysql/monthly_accounting_repository.py"
QUERY = "subsystems/finance_import/query.py"
SCHEMA = "db/fresh_schema/labor_union_fresh_current.sql"
TABLES = (
    "finance_import_rows", "client_ledger_entries", "staff_payout_events",
    "staff_payout_obligation_links", "staff_obligations",
    "government_subsidy_transactions", "government_subsidy_allocations",
    "subsidy_claim_batch_items", "government_subsidy_period_entries",
    "government_subsidy_period_members", "staff_overpayment_recovery_events",
    "staff_overpayment_recoveries",
)
PREDECLARED = {
    "situation": "MySQL 8, real baseline case_bank_facts; 16/160 target cases, 3000 unrelated cases, all five proof sources",
    "task": "Compare existing outer case predicate against experimental per-UNION-branch predicate without changing facts",
    "action": "Same connection/data/indexes; warm both; A/B/A/B, three measured samples per side; fetch and compare every result; EXPLAIN ANALYZE separately",
    "result": "Exact facts for every target, shared-bank complete case membership, government reversal, excluded unsuccessful transaction, fresh update visible, incomplete source raises existing error",
    "decision": "Consider SQL change only if output checks pass, median saves >=10%, absolute saving >=5ms, and median gap exceeds both sides' full run-to-run range; otherwise inconclusive/no measurable improvement",
    "noise_floor": "max(5ms, 10% baseline median, baseline max-min, experiment max-min)",
    "timed_work": "Actual repository method plus execute/fetchall/fact grouping per case, all returned facts consumed; excludes setup, counters, output checks and EXPLAIN",
    "limits": "Synthetic adapter microbenchmark with canonical table columns/indexes, no foreign keys/checks; production tuning/data/concurrency and user-wait share remain unverified",
}


def git_text(path: str) -> str:
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], text=True)


def proof_sql() -> str:
    for node in ast.parse(git_text(QUERY)).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "BANK_CASE_PROOFS_SQL" for t in node.targets):
            value = ast.literal_eval(node.value)
            if not isinstance(value, str):
                raise TypeError("BANK_CASE_PROOFS_SQL must be a literal string")
            return value
    raise RuntimeError("Baseline proof SQL not found")


def load_baseline(directory: Path) -> Any:
    path = directory / "baseline_monthly_accounting.py"
    path.write_text(git_text(REPOSITORY), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("baseline_monthly_accounting", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load immutable baseline repository")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BANK_CASE_PROOFS_SQL = proof_sql()
    return module


def scoped_proofs(proofs: str) -> str:
    branches = proofs.strip().split("\nUNION\n")
    if len(branches) != 5:
        raise AssertionError("Expected exactly the baseline's five UNION branches")
    columns = ("case_no", "o.case_no", "i.case_no", "member.case_no", "o.case_no")
    return "\nUNION\n".join(
        branch + (" AND " if "WHERE " in branch else " WHERE ") + column + "=%s"
        for branch, column in zip(branches, columns, strict=True)
    )


@dataclass(frozen=True)
class Sample:
    side: str
    milliseconds: float
    facts_consumed: int
    case_memberships_consumed: int
    errors: int
    handler_reads: dict[str, int]


def canonical(facts: Sequence[Any]) -> list[dict[str, Any]]:
    if not all(is_dataclass(fact) for fact in facts):
        raise TypeError("Expected real AccountingBankFact dataclasses")
    return [asdict(fact) for fact in facts]


def create_schema(connection: Any) -> None:
    source = git_text(SCHEMA)
    with connection.cursor() as cursor:
        for table in TABLES:
            match = re.search(r"CREATE TABLE `" + table + r"` \((.*?)\) ENGINE=InnoDB[^;]*;", source, re.S)
            if match is None:
                raise RuntimeError(f"Missing canonical table {table}")
            lines = [line.rstrip(",") for line in match[1].splitlines() if line.strip() and not line.lstrip().startswith("CONSTRAINT ")]
            cursor.execute(f"CREATE TABLE `{table}` (" + ",\n".join(lines) + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")


def populate(connection: Any, unrelated: int) -> dict[str, list[dict[str, Any]]]:
    """Canonical columns/indexes; synthetic required values for unrelated fields."""
    rows: dict[str, list[dict[str, Any]]] = {table: [] for table in TABLES}
    expected: dict[str, list[dict[str, Any]]] = {}

    def add(table: str, **values: Any) -> int:
        identity = len(rows[table]) + 1
        row = {"id": identity, **values}
        rows[table].append(row)
        return identity

    def bank(case: str, source: int, direction: str, cases: tuple[str, ...]) -> int:
        identity = add("finance_import_rows", transaction_date="2026-01-15", direction=direction,
                       credit=1000 if direction == "incoming" else 0,
                       debit=1000 if direction == "outgoing" else 0,
                       format_id="taishin" if source in {2, 3} else "sinopac")
        flow = ("C", "PS", "G", "G", None)[source]
        expected.setdefault(case, []).append({"identity": f"bank:{identity}", "occurred_on": "2026-01-15",
            "direction": "in" if direction == "incoming" else "out", "amount_ntd": 1000,
            "cases": cases, "bank": "taishin" if source in {2, 3} else "sinopac", "cash_flow": flow})
        return identity

    for index in range(160 + unrelated):
        case = f"SYN{index:06d}"
        peer = f"PEER{index:06d}"
        receipt = bank(case, 0, "incoming", (case,))
        add("client_ledger_entries", case_no=case, finance_import_row_id=receipt, entry_type="receipt")
        payout = bank(case, 1, "outgoing", tuple(sorted((case, peer))))
        event = add("staff_payout_events", finance_import_row_id=payout)
        for member in (case, peer):
            obligation = f"obl-{member}"
            add("staff_obligations", case_no=member, obligation_identity=obligation)
            add("staff_payout_obligation_links", payout_event_id=event, obligation_identity=obligation,
                allocation_ordinal=1 if member == case else 2)
        subsidy = bank(case, 2, "incoming", (case,))
        transaction = add("government_subsidy_transactions", finance_import_row_id=subsidy, transaction_status="succeeded")
        item = add("subsidy_claim_batch_items", case_no=case)
        add("government_subsidy_allocations", transaction_id=transaction, claim_item_id=item)
        period = bank(case, 3, "incoming", (case,))
        root = add("government_subsidy_period_entries", finance_import_row_id=period, reversal_of_id=None)
        add("government_subsidy_period_members", receipt_id=root, case_no=case)
        reversal = bank(case, 3, "outgoing", (case,))
        expected[case][-1]["cash_flow"] = None
        add("government_subsidy_period_entries", finance_import_row_id=reversal, reversal_of_id=root)
        if index < 160 or index % 24 == 0:
            recovery_bank = bank(case, 4, "incoming", (case,))
            recovery = f"rec-{index}"
            add("staff_overpayment_recoveries", recovery_identity=recovery,
                source_obligation_identities=json.dumps([f"obl-{case}"]))
            add("staff_overpayment_recovery_events", recovery_identity=recovery,
                finance_import_row_id=recovery_bank, event_type="cash_recovered")
        failed_bank = add("finance_import_rows", transaction_date="2026-01-15", direction="incoming", credit=999, debit=0, format_id="taishin")
        failed = add("government_subsidy_transactions", finance_import_row_id=failed_bank, transaction_status="failed")
        add("government_subsidy_allocations", transaction_id=failed, claim_item_id=item)

    with connection.cursor() as cursor:
        for table, entries in rows.items():
            cursor.execute(f"SHOW COLUMNS FROM `{table}`")
            columns = cursor.fetchall()
            column_names = {str(column["Field"]) for column in columns}
            for identity, row in enumerate(entries, start=1):
                if "id" not in column_names:
                    del row["id"]
                for column in columns:
                    name, kind = str(column["Field"]), str(column["Type"])
                    if name in row or column["Null"] == "YES" or column["Default"] is not None or "auto_increment" in str(column["Extra"]):
                        continue
                    if kind == "json":
                        row[name] = "[]"
                    elif kind.startswith("enum("):
                        row[name] = re.findall(r"'([^']*)'", kind)[0]
                    elif "date" in kind or "time" in kind:
                        row[name] = "2026-01-15" if kind == "date" else "2026-01-15 00:00:00"
                    elif "char" in kind or "text" in kind:
                        size = re.search(r"\((\d+)\)", kind)
                        row[name] = sha256(f"{table}:{identity}:{name}".encode()).hexdigest()[:int(size[1]) if size else 64]
                    else:
                        row[name] = identity
            names = tuple(entries[0])
            if any(tuple(row) != names for row in entries):
                raise AssertionError(f"Inconsistent seed shape for {table}")
            sql = f"INSERT INTO `{table}` (" + ",".join(f"`{name}`" for name in names) + ") VALUES (" + ",".join("%s" for _ in names) + ")"
            cursor.executemany(sql, [tuple(row[name] for name in names) for row in entries])
            cursor.execute(f"ANALYZE TABLE `{table}`")
    return expected


def counters(connection: Any) -> dict[str, int]:
    with connection.cursor() as cursor:
        cursor.execute("SHOW SESSION STATUS LIKE 'Handler_read%'")
        return {str(row["Variable_name"]): int(row["Value"]) for row in cursor.fetchall()}


def main() -> None:
    print(json.dumps({"predeclared": PREDECLARED}, ensure_ascii=False), flush=True)
    if not os.environ.get("CI"):
        raise RuntimeError("CI-only: local execution is explicitly prohibited")
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "mysql"}:
        raise ValueError("Only the disposable CI MySQL service is allowed")
    unrelated = int(os.environ.get("SYNTHETIC_UNRELATED_CASES", "3000"))
    if not 1000 <= unrelated <= 10000:
        raise ValueError("Unrelated synthetic cases must be between 1000 and 10000")
    sys.path.insert(0, os.getcwd())
    with tempfile.TemporaryDirectory(prefix="lu-sql-synthetic-") as temporary:
        module = load_baseline(Path(temporary))
        original = module.MySqlMonthlyAccountingSource
        scoped = scoped_proofs(module.BANK_CASE_PROOFS_SQL)
        experimental_sql = "SELECT " + module._CASH_FACT_COLUMNS + " FROM finance_import_rows b JOIN (" + module.BANK_CASE_PROOFS_SQL + ") p ON p.row_id=b.id WHERE b.id IN (SELECT q.row_id FROM (" + scoped + ") q) ORDER BY b.id,p.case_no"

        class Experimental(original):
            def case_bank_facts(self, case_no: str) -> Any:
                with self.connection.cursor() as cursor:
                    cursor.execute(experimental_sql, (case_no,) * 5)
                    return self._facts(cursor.fetchall())

        connection = pymysql.connect(host=host, port=int(os.environ.get("MYSQL_PORT", "3306")), user="root",
            password=os.environ.get("MYSQL_ROOT_PASSWORD", "synthetic"), charset="utf8mb4", autocommit=True, cursorclass=DictCursor)
        database = "lu_synthetic_" + sha256(os.urandom(32)).hexdigest()[:12]
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                cursor.execute(f"USE `{database}`")
                cursor.execute("SELECT VERSION() version, @@optimizer_switch optimizer_switch, @@innodb_buffer_pool_size buffer_pool, @@transaction_isolation isolation")
                environment = cursor.fetchone()
            create_schema(connection)
            expected = populate(connection, unrelated)
            sources = {"A": original(connection), "B": Experimental(connection)}
            validation_errors = 0
            for side, source in sources.items():
                for case in (f"SYN{i:06d}" for i in range(16)):
                    if canonical(source.case_bank_facts(case)) != expected[case]:
                        validation_errors += 1
                        raise AssertionError(f"{side}: fact mismatch for {case}")
                if source.case_bank_facts("SYN-NOT-PRESENT"):
                    raise AssertionError("Unknown case must return no facts")
            samples: dict[str, list[dict[str, Any]]] = {}
            for count in (16, 160):
                cases = tuple(f"SYN{i:06d}" for i in range(count))
                measured: list[Sample] = []
                for side in ("A", "B"):
                    sources[side].case_bank_facts(cases[0])
                for side in ("A", "B", "A", "B", "A", "B"):
                    before = counters(connection)
                    consumed, memberships, errors = 0, 0, 0
                    outputs: dict[str, Sequence[Any]] = {}
                    started = time.perf_counter()
                    for case in cases:
                        try:
                            facts = sources[side].case_bank_facts(case)
                        except Exception:
                            errors += 1
                            raise
                        consumed += len(facts)
                        memberships += sum(len(fact.cases) for fact in facts)
                        outputs[case] = facts
                    elapsed = (time.perf_counter() - started) * 1000
                    after = counters(connection)
                    for case, facts in outputs.items():
                        if canonical(facts) != expected[case]:
                            raise AssertionError(f"Timed {side}: fact mismatch for {case}")
                    measured.append(Sample(side, elapsed, consumed, memberships, errors,
                        {key: after[key] - before[key] for key in before}))
                samples[str(count)] = [asdict(sample) for sample in measured]
            plans: dict[str, list[dict[str, Any]]] = {}
            baseline_sql = "SELECT " + module._CASH_FACT_COLUMNS + " FROM finance_import_rows b JOIN (" + module.BANK_CASE_PROOFS_SQL + ") p ON p.row_id=b.id WHERE b.id IN (SELECT q.row_id FROM (" + module.BANK_CASE_PROOFS_SQL + ") q WHERE q.case_no=%s) ORDER BY b.id,p.case_no"
            with connection.cursor() as cursor:
                for side, sql, params in (("A", baseline_sql, ("SYN000000",)), ("B", experimental_sql, ("SYN000000",) * 5)):
                    cursor.execute("EXPLAIN ANALYZE " + sql, params)
                    plans[side] = cursor.fetchall()
                cursor.execute("UPDATE finance_import_rows SET credit=1234 WHERE id=1")
            for source in sources.values():
                if source.case_bank_facts("SYN000000")[0].amount_ntd != 1234:
                    raise AssertionError("Fresh committed update was not visible")
            with connection.cursor() as cursor:
                cursor.execute("UPDATE finance_import_rows SET direction='unknown' WHERE id=1")
            failure_checks = 0
            for source in sources.values():
                try:
                    source.case_bank_facts("SYN000000")
                except module.MonthlyAccountingUnavailable as error:
                    if str(error) != "accounting_bank_source_incomplete":
                        raise
                    failure_checks += 1
                else:
                    raise AssertionError("Incomplete bank source must raise")
            summaries: dict[str, dict[str, Any]] = {}
            for size, data in samples.items():
                timings = {side: [sample["milliseconds"] for sample in data if sample["side"] == side] for side in ("A", "B")}
                medians = {side: statistics.median(values) for side, values in timings.items()}
                noise = max(5.0, medians["A"] * 0.1, *(max(values) - min(values) for values in timings.values()))
                delta = medians["A"] - medians["B"]
                summaries[size] = {"median_ms": medians, "range_ms": {side: [min(values), max(values)] for side, values in timings.items()},
                    "noise_floor_ms": noise, "delta_ms": delta,
                    "verdict": "candidate SQL micro-improvement; end-to-end impact unverified" if delta > noise else "no measurable improvement/inconclusive"}
            report = {"baseline": BASE, "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "environment": environment, "cpu_count": os.cpu_count(), "load_average": os.getloadavg(),
                "synthetic_unrelated_cases": unrelated, "predeclared": PREDECLARED, "samples": samples,
                "summary": summaries, "plans": plans, "validation_errors": validation_errors,
                "fresh_update_checks": 2, "expected_failure_checks": failure_checks,
                "e2e": "NOT_RUN; adapter-only disposable synthetic MySQL measurement",
                "schema": "canonical columns/indexes; constraints omitted solely for synthetic setup; no production data or credentials"}
            Path(os.environ.get("SQL_BENCHMARK_OUTPUT", "sql-benchmark.json")).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            print(json.dumps({"summary": summaries, "validation_errors": validation_errors, "expected_failure_checks": failure_checks}), flush=True)
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            connection.close()


if __name__ == "__main__":
    main()
