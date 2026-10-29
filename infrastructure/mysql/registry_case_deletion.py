"""Fixed case-owned deletion SQL compiled from the canonical fresh schema.

Only inbound ownership paths are followed. Staff, shared clients, source import
batches and bank statements are never reached by following an outgoing FK.
There is no request-provided table, column, predicate or SQL.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

CASE_CYCLE_LINKS = {
    "orders": "pricing_override_event_id",
    "client_obligation_events": "source_obligation_identity",
    "client_obligations": "source_obligation_identity",
    "staff_obligation_events": "source_obligation_identity",
    "staff_obligations": "source_obligation_identity",
}

# Delivery sources use document/session identities rather than a bare case key.
# Capture their IDs while the case-owned documents/events still exist.
CASE_TASK_SCOPE = """EXISTS(
    SELECT 1 FROM contract_signing_events e
    WHERE e.case_no=(p_case COLLATE utf8mb4_unicode_ci) AND e.line_delivery_task_id=t.id
  ) OR EXISTS(
    SELECT 1 FROM contract_document_versions d
    WHERE d.case_no=(p_case COLLATE utf8mb4_unicode_ci)
      AND t.source_aggregate_type='contract_document_version'
      AND t.source_aggregate_identity=CONCAT(d.case_no,':',d.id)
  ) OR EXISTS(
    SELECT 1 FROM contract_external_signing_sessions s
    WHERE s.case_no=(p_case COLLATE utf8mb4_unicode_ci)
      AND (s.client_reminder_task_id=t.id OR
        (t.source_aggregate_type='contract_external_signing_session'
         AND SUBSTRING_INDEX(t.source_aggregate_identity,':',1)=s.id))
  )"""

def identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


@lru_cache(maxsize=1)
def case_deletion_statements() -> tuple[tuple[str, str], ...]:
    schema = Path(__file__).resolve().parents[2] / "db/fresh_schema/labor_union_fresh_current.sql"
    definitions = dict(re.findall(r"CREATE TABLE `([^`]+)` \((.*?)\) ENGINE=.*?;", schema.read_text(encoding="utf-8"), re.S))
    columns = {name: set(re.findall(r"^\s*`([^`]+)`", ddl, re.M)) for name, ddl in definitions.items()}
    relations = {
        name: [(re.findall(r"`([^`]+)`", child), parent, re.findall(r"`([^`]+)`", referenced))
               for child, parent, referenced in re.findall(r"FOREIGN KEY \((.*?)\) REFERENCES `([^`]+)` \((.*?)\)", ddl)]
        for name, ddl in definitions.items()
    }
    predicates = {"orders": "t.`case_no`=p_case", "clients": "p_delete_client AND t.`id`=p_client"}
    for name, fields in columns.items():
        if name in predicates:
            continue
        terms = [f"t.{identifier(column)}=p_case" for column in ("case_no", "bound_case_no") if column in fields]
        if "client_id" in fields:
            terms.append("(p_delete_client AND t.`client_id`=p_client)")
        if {"subject_reference", "owner_type"} <= fields:
            terms.append("(t.`subject_reference`=p_case AND t.`owner_type` IN ('orders','scheduling','contract_signing'))")
        if {"subject_reference", "subject_type"} <= fields:
            terms.append("(p_delete_client AND t.`subject_reference`=CAST(p_client AS CHAR) AND t.`subject_type`='customer')")
        for kind, identity in (("source_aggregate_type", "source_aggregate_identity"), ("aggregate_type", "aggregate_identity")):
            if {kind, identity} <= fields:
                terms.append(f"(t.{identifier(identity)}=p_case AND t.{identifier(kind)} IN ('orders','scheduling','contract_signing','client_finance','payroll'))")
        if name == "line_delivery_tasks":
            terms.append("JSON_CONTAINS(p_task_ids,CAST(t.id AS JSON))")
        if terms:
            predicates[name] = "(" + " OR ".join(terms) + ")"
    # Descendants without their own case identity inherit their parent's scope.
    # A row with an explicit case identity never inherits some other case's scope.
    reachable = set(predicates)
    while True:
        additions = {name for name, references in relations.items() if any(parent in reachable for _, parent, _ in references)}
        if additions <= reachable:
            break
        reachable.update(additions)
    aliases = {table: "r" + str(index) for index, table in enumerate(definitions)}
    def inherited_scope(name: str) -> str:
        if name in predicates:
            return predicates[name]
        terms = []
        for child, parent, referenced in relations[name]:
            if parent not in reachable or parent == name:
                continue
            parent_alias = aliases[parent]
            parent_scope = inherited_scope(parent).replace("t.", parent_alias + ".")
            joins = " AND ".join(f"t.{identifier(c)}={parent_alias}.{identifier(p)}" for c, p in zip(child, referenced, strict=True))
            terms.append(f"EXISTS(SELECT 1 FROM {identifier(parent)} {parent_alias} WHERE ({parent_scope}) AND {joins})")
        predicates[name] = "(" + " OR ".join(terms) + ")"
        return predicates[name]
    for name in sorted(reachable):
        inherited_scope(name)
    # Break only known nullable links within the rows being removed. Every
    # remaining FK is enforced throughout the outer transaction.
    remaining = set(predicates)
    ordered = []
    while remaining:
        leaves = sorted(parent for parent in remaining if not any(
            owner != parent and any(target == parent and CASE_CYCLE_LINKS.get(owner) not in child
                                    for child, target, _ in relations[owner])
            for owner in remaining
        ))
        if not leaves:
            raise ValueError("unresolved canonical case deletion dependency")
        ordered.extend(leaves)
        remaining.difference_update(leaves)
    statements = [(table, f"UPDATE {identifier(table)} SET {identifier(column)}=NULL WHERE case_no=p_case")
                  for table, column in CASE_CYCLE_LINKS.items()]
    for table in ordered:
        scope = predicates[table]
        # MySQL evaluates self-referencing RESTRICT row by row. Canonical event
        # references point to earlier immutable IDs; remove the newest first.
        self_reference = any(parent == table for _, parent, _ in relations[table])
        order = " ORDER BY t.`id` DESC" if self_reference and "id" in columns[table] else ""
        statements.append((table, f"DELETE FROM {identifier(table)} AS t WHERE {scope}{order}"))
    return tuple((table, re.sub(r"\bp_case\b", "(p_case COLLATE utf8mb4_unicode_ci)", sql).replace("CAST(p_client AS CHAR)", "(CAST(p_client AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci)")) for table, sql in statements)


def bind_case_statement(sql: str, case_no: str, client_id: int, delete_client: bool, task_ids: str = "[]") -> tuple[str, tuple]:
    values = {"p_case": case_no, "p_client": client_id, "p_delete_client": delete_client, "p_task_ids": task_ids}
    parameters = []
    def bind(match):
        parameters.append(values[match[0]])
        return "%s"
    return re.sub(r"\bp_(?:case|client|delete_client|task_ids)\b", bind, sql), tuple(parameters)


def nas_case_deletion_body() -> str:
    return """
      DECLARE p_delete_client BOOLEAN;
      DECLARE p_task_ids JSON;
      DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN
        SET @registry_delete_key=NULL,@registry_delete_case=NULL,@registry_delete_client=NULL,@registry_delete_client_owned=NULL,@registry_delete_tasks=NULL;
        RESIGNAL;
      END;
      IF NOT EXISTS(SELECT 1 FROM orders WHERE case_no=p_case AND lifecycle_version=p_version
                    AND client_id=p_client FOR UPDATE) OR
         NOT EXISTS(SELECT 1 FROM clients WHERE id=p_client AND client_profile_version=p_client_version FOR UPDATE) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='registry_deletion_stale_version'; END IF;
      IF EXISTS(SELECT 1 FROM contract_signing_events WHERE case_no=p_case AND event_type='signed_received' FOR UPDATE)
         OR EXISTS(SELECT 1 FROM order_contract_flow_events WHERE case_no=p_case AND event_type='contract_completed' FOR UPDATE) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='registry_deletion_signed'; END IF;
      IF NOT EXISTS(SELECT 1 FROM application_command_claims WHERE idempotency_key=p_command_key
        AND command_family='registry_delete/v1' AND aggregate_identity=CONCAT('case:',p_case)) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='registry_deletion_context_required'; END IF;
      SET p_delete_client=NOT EXISTS(SELECT 1 FROM orders WHERE client_id=p_client AND case_no<>p_case FOR UPDATE);
    """ + "SELECT COALESCE(JSON_ARRAYAGG(t.id),JSON_ARRAY()) INTO p_task_ids FROM line_delivery_tasks t WHERE " + CASE_TASK_SCOPE + ";\nSET @registry_delete_key=p_command_key,@registry_delete_case=p_case,@registry_delete_client=p_client,@registry_delete_client_owned=p_delete_client,@registry_delete_tasks=p_task_ids;\n" + ";\n".join(sql for _, sql in case_deletion_statements()) + ";\nSET @registry_delete_key=NULL,@registry_delete_case=NULL,@registry_delete_client=NULL,@registry_delete_client_owned=NULL,@registry_delete_tasks=NULL;"
