"""Persistence for existing qualification columns/relations, without hidden commits."""
import json
from infrastructure.mysql.nas_mutations import call_mutation

from domains.staff.qualification_editing import QualificationEditingError, normalize_facts
from subsystems.staff.qualification_editing_workflow import COMMAND_FAMILY


class MySqlStaffQualificationEditingRepository:
    def __init__(self, connection):
        self.connection = connection

    def load(self, staff_id, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT special_skills,has_massage_cert,care_babies FROM staff WHERE id=%s" + suffix, (staff_id,))
            row = cursor.fetchone()
            if row is None:
                raise QualificationEditingError("staff_qualification_not_found")
            skills = row["special_skills"]
            skills = json.loads(skills) if isinstance(skills, str) else skills
            massage = row["has_massage_cert"]
            if massage not in (None, 0, 1):
                raise QualificationEditingError("staff_qualification_massage_invalid")
            values = {"special_skills": [] if skills is None else skills, "has_massage_cert": None if massage is None else bool(massage), "care_babies": row["care_babies"]}
            for key, table, column in (("certifications", "staff_certifications", "certification_type"), ("transportation", "staff_transportation", "vehicle_type")):
                cursor.execute(f"SELECT {column} FROM {table} WHERE staff_id=%s" + suffix, (staff_id,))
                values[key] = [item[column] for item in cursor.fetchall()]
        return normalize_facts(values)

    def persist(self, staff_id, before, after):
        with self.connection.cursor() as cursor:
            cursor.execute("UPDATE staff SET special_skills=%s,has_massage_cert=%s,care_babies=%s WHERE id=%s", (json.dumps(after.special_skills, ensure_ascii=False), after.has_massage_cert, after.care_babies, staff_id))
            # Retain unchanged certifications and their original registration timestamps.
            for key, table, column in (("certifications", "staff_certifications", "certification_type"), ("transportation", "staff_transportation", "vehicle_type")):
                old, new = set(getattr(before, key)), set(getattr(after, key))
                for value in sorted(old - new):
                    call_mutation(cursor, f"lu_nas_remove_{table}_v1", staff_id, value, None)
                for value in sorted(new - old):
                    cursor.execute(f"INSERT INTO {table} (staff_id,{column}) VALUES (%s,%s)", (staff_id, value))

    def find_receipt(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT request_fingerprint,result_snapshot FROM admin_command_receipts WHERE command_family=%s AND idempotency_key=%s FOR UPDATE", (COMMAND_FAMILY, key))
            row = cursor.fetchone()
        if row is None:
            return None
        result = row["result_snapshot"]
        return {"request_fingerprint": row["request_fingerprint"], "result": json.loads(result) if isinstance(result, str) else result}

    def save_receipt(self, key, request_fingerprint, preview, actor, reason, result):
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO admin_command_receipts (command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)", (COMMAND_FAMILY, key, request_fingerprint, preview, actor, reason, json.dumps(result, ensure_ascii=False, sort_keys=True)))
