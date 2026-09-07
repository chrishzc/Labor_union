"""
File: seed_line_test_fixtures.py
Description: 依照「LINE 四大模組詳細測試手冊與前置條件」自動建立與復原測試資料與架構。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

import pymysql
from infrastructure.mysql.mysql_adapter import get_connection
from api.dependencies.case_architecture_bootstrap import (
    get_case_architecture_bootstrap_status_service,
    get_case_architecture_bootstrap_workflow,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.bootstrap.case_architecture_workflow import (
    EnsureCaseArchitectureBootstrap,
)


def seed_fixtures(verbose: bool = True) -> dict[str, object]:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env in {"prod", "production"}:
        raise RuntimeError("此腳本禁止在 production 正式環境執行！")

    conn = get_connection()
    cursor = None

    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 1. 客戶資料 (Clients)
        # Client 1: 陳雅婷
        cursor.execute("SELECT id FROM clients WHERE name = '陳雅婷' AND phone = '0912345678'")
        existing_c1 = cursor.fetchone()
        if existing_c1:
            c1_id = existing_c1['id']
            cursor.execute(
                "UPDATE clients SET case_no='CASE-2026-M301', city='新竹市', address='東區光復路二段101號', "
                "identity_status='一般市民', service_days=30, due_month='2026-10', service_start_date='2026-10-05', "
                "created_at=NOW(), line_user_id=NULL WHERE id = %s", (c1_id,)
            )
        else:
            cursor.execute(
                "INSERT INTO clients (name, gender, phone, city, address, identity_status, "
                "service_time, due_month, service_start_date, notes, service_days, residence_type, "
                "delivery_type, service_type, baby_info, case_no, line_user_id, admin_notes, created_at) "
                "VALUES ('陳雅婷', 'female', '0912345678', '新竹市', '東區光復路二段101號', '一般市民', "
                "'9小時日間', '2026-10', '2026-10-05', 'LINE E2E 測試客戶 - 需烹煮坐月子餐', 30, '公寓', "
                "'自然產', '到宅坐月子', '單胞胎男寶寶', 'CASE-2026-M301', NULL, 'PRECONDITION_FIXTURE', NOW())",
            )
            c1_id = cursor.lastrowid

        # Client 2: 林怡君
        cursor.execute("SELECT id FROM clients WHERE name = '林怡君' AND phone = '0922333444'")
        existing_c2 = cursor.fetchone()
        if existing_c2:
            c2_id = existing_c2['id']
            cursor.execute(
                "UPDATE clients SET case_no='CASE-2026-M302', city='新竹市', address='北區中正路200號', "
                "identity_status='一般市民', service_days=20, due_month='2026-11', service_start_date='2026-11-01', "
                "created_at=NOW(), line_user_id=NULL WHERE id = %s", (c2_id,)
            )
        else:
            cursor.execute(
                "INSERT INTO clients (name, gender, phone, city, address, identity_status, "
                "service_time, due_month, service_start_date, notes, service_days, residence_type, "
                "delivery_type, service_type, baby_info, case_no, line_user_id, admin_notes, created_at) "
                "VALUES ('林怡君', 'female', '0922333444', '新竹市', '北區中正路200號', '一般市民', "
                "'9小時日間', '2026-11', '2026-11-01', 'LINE E2E 測試客戶 2', 20, '大樓', "
                "'剖腹產', '到宅坐月子', '單胞胎女寶寶', 'CASE-2026-M302', NULL, 'PRECONDITION_FIXTURE', NOW())",
            )
            c2_id = cursor.lastrowid

        # Client 3: 李詩涵 (【狀態 B：有案號但缺問卷】專用測試資料)
        cursor.execute("SELECT id FROM clients WHERE name = '李詩涵' AND phone = '0933111222'")
        existing_c3 = cursor.fetchone()
        if existing_c3:
            c3_id = existing_c3['id']
            cursor.execute(
                "UPDATE clients SET case_no='CASE-2026-STATE-B', city='新竹市', address='東區科學園路1號', "
                "identity_status='一般市民', service_days=NULL, due_month='2026-12', service_start_date=NULL, "
                "notes=NULL, baby_info=NULL, residence_type=NULL, delivery_type=NULL, service_type=NULL, "
                "admin_notes='STATE_B_UNFILLED_SURVEY', created_at=NOW(), line_user_id=NULL WHERE id = %s", (c3_id,)
            )
        else:
            cursor.execute(
                "INSERT INTO clients (name, gender, phone, city, address, identity_status, "
                "service_time, due_month, service_start_date, notes, service_days, residence_type, "
                "delivery_type, service_type, baby_info, case_no, line_user_id, admin_notes, created_at) "
                "VALUES ('李詩涵', 'female', '0933111222', '新竹市', '東區科學園路1號', '一般市民', "
                "NULL, '2026-12', NULL, NULL, NULL, NULL, "
                "NULL, NULL, NULL, 'CASE-2026-STATE-B', NULL, 'STATE_B_UNFILLED_SURVEY', NOW())",
            )
            c3_id = cursor.lastrowid

        # 2. 月嫂資料 (Staff)
        # Staff 1: 王美華
        cursor.execute("SELECT id FROM staff WHERE name = '王美華' AND identity_card = 'A234567890'")
        existing_s1 = cursor.fetchone()
        if existing_s1:
            s1_id = existing_s1['id']
            cursor.execute(
                "UPDATE staff SET phone='0923456789', birthday='1980-05-15', city='新竹市', "
                "address='東區建中一路50號', status='active', has_massage_cert=1, "
                "weekly_rest_days=%s, care_babies=1, service_regions=%s, special_skills=%s, "
                "registered_at=NOW(), line_user_id=NULL WHERE id = %s",
                (json.dumps(["週日"]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["產婦催乳按摩", "月子膳食調理"]), s1_id)
            )
        else:
            cursor.execute(
                "INSERT INTO staff (name, identity_card, phone, birthday, city, address, "
                "has_massage_cert, status, weekly_rest_days, care_babies, service_regions, "
                "special_skills, registered_at, line_user_id) "
                "VALUES ('王美華', 'A234567890', '0923456789', '1980-05-15', '新竹市', '東區建中一路50號', "
                "1, 'active', %s, 1, %s, %s, NOW(), NULL)",
                (json.dumps(["週日"]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["產婦催乳按摩", "月子膳食調理"]))
            )
            s1_id = cursor.lastrowid

        # Staff 2: 張淑芬
        cursor.execute("SELECT id FROM staff WHERE name = '張淑芬' AND identity_card = 'B234567891'")
        existing_s2 = cursor.fetchone()
        if existing_s2:
            s2_id = existing_s2['id']
            cursor.execute(
                "UPDATE staff SET phone='0934567890', birthday='1982-08-20', city='新竹市', "
                "address='北區北大路88號', status='active', has_massage_cert=1, "
                "weekly_rest_days=%s, care_babies=1, service_regions=%s, special_skills=%s, "
                "registered_at=NOW(), line_user_id=NULL WHERE id = %s",
                (json.dumps(["週六", "週日"]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["新生兒照護", "嬰幼兒按摩"]), s2_id)
            )
        else:
            cursor.execute(
                "INSERT INTO staff (name, identity_card, phone, birthday, city, address, "
                "has_massage_cert, status, weekly_rest_days, care_babies, service_regions, "
                "special_skills, registered_at, line_user_id) "
                "VALUES ('張淑芬', 'B234567891', '0934567890', '1982-08-20', '新竹市', '北區北大路88號', "
                "1, 'active', %s, 1, %s, %s, NOW(), NULL)",
                (json.dumps(["週六", "週日"]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["新生兒照護", "嬰幼兒按摩"]))
            )
            s2_id = cursor.lastrowid

        # 3. 訂單案件 (Orders - Precondition Fixture)
        # Order 1: CASE-2026-M301
        cursor.execute("SELECT case_no FROM orders WHERE case_no = 'CASE-2026-M301'")
        if cursor.fetchone():
            cursor.execute(
                "UPDATE orders SET client_id=%s, staff_id=NULL, status='洽談中', "
                "service_days=30, service_hours_per_day=9, service_start_time='09:00:00', service_end_time='18:00:00', "
                "service_end_day_offset=0, start_date='2026-10-05', end_date='2026-11-03', "
                "requires_cooking=1, lifecycle_version=1 WHERE case_no = 'CASE-2026-M301'",
                (c1_id,)
            )
        else:
            cursor.execute(
                "INSERT INTO orders (case_no, client_id, staff_id, status, lifecycle_version, "
                "service_days, service_hours_per_day, service_start_time, service_end_time, "
                "service_end_day_offset, start_date, end_date, requires_cooking) "
                "VALUES ('CASE-2026-M301', %s, NULL, '洽談中', 1, 30, 9, '09:00:00', '18:00:00', 0, '2026-10-05', '2026-11-03', 1)",
                (c1_id,)
            )

        # Order 2: CASE-2026-M302
        cursor.execute("SELECT case_no FROM orders WHERE case_no = 'CASE-2026-M302'")
        if cursor.fetchone():
            cursor.execute(
                "UPDATE orders SET client_id=%s, staff_id=NULL, status='洽談中', "
                "service_days=20, service_hours_per_day=9, service_start_time='09:00:00', service_end_time='18:00:00', "
                "service_end_day_offset=0, start_date='2026-11-01', end_date='2026-11-20', "
                "requires_cooking=1, lifecycle_version=1 WHERE case_no = 'CASE-2026-M302'",
                (c2_id,)
            )
        else:
            cursor.execute(
                "INSERT INTO orders (case_no, client_id, staff_id, status, lifecycle_version, "
                "service_days, service_hours_per_day, service_start_time, service_end_time, "
                "service_end_day_offset, start_date, end_date, requires_cooking) "
                "VALUES ('CASE-2026-M302', %s, NULL, '洽談中', 1, 20, 9, '09:00:00', '18:00:00', 0, '2026-11-01', '2026-11-20', 1)",
                (c2_id,)
            )

        # 4. 清除可能殘留的測試用 LINE 綁定與解除申請 (保留乾淨狀態，遵循 FK 關聯順序)
        cursor.execute("DELETE FROM line_identity_revocation_requests")
        cursor.execute("DELETE FROM line_identity_role_binding_events")
        cursor.execute("DELETE FROM line_identity_role_bindings")
        cursor.execute("DELETE FROM line_identity_bindings")

        # 4.1 確保已發布的 LINE Rich Menu 任務存在 (供解除綁定 M1-06 回復 fallback menu 使用)
        rich_menu_fixtures = [
            ("default_menu", "richmenu-afe3c90c191abd8613ca7f9a06049a7b", "一般用戶選單", "seed-default-menu-publication", "seed-corr-default-menu"),
            ("staff_menu", "richmenu-b1c86786d69f902c79690842dd133afb", "月嫂專屬選單", "seed-staff-menu-publication", "seed-corr-staff-menu"),
            ("union_staff_menu", "richmenu-e5f8b155c10220e5d3296d50c0a8e027", "工會人員專屬選單", "seed-union-staff-menu-publication", "seed-corr-union-staff-menu"),
        ]
        for m_def_id, p_menu_id, m_name, idem_key, corr_id in rich_menu_fixtures:
            cursor.execute(
                "INSERT INTO line_rich_menu_publication_tasks ("
                "  menu_definition_id, configuration_revision, operation, publication_status,"
                "  definition_snapshot, provider_menu_id, idempotency_key, correlation_id, requested_by_actor_id"
                ") VALUES (%s, 1, 'publish', 'published', %s, %s, %s, %s, 'system:seed') "
                "ON DUPLICATE KEY UPDATE publication_status='published', provider_menu_id=%s",
                (m_def_id, json.dumps({"id": m_def_id, "name": m_name}), p_menu_id, idem_key, corr_id, p_menu_id),
            )
            task_id = cursor.lastrowid
            if not task_id:
                cursor.execute("SELECT id FROM line_rich_menu_publication_tasks WHERE idempotency_key=%s", (idem_key,))
                task_id = cursor.fetchone()["id"]
            cursor.execute(
                "INSERT IGNORE INTO line_rich_menu_publication_step_acknowledgements ("
                "  publication_id, step_name, request_fingerprint, idempotency_key, provider_menu_id, acknowledged_at_utc"
                ") VALUES (%s, 'cleanup', '0000000000000000000000000000000000000000000000000000000000000000', %s, %s, UTC_TIMESTAMP(6))",
                (task_id, f"seed-cleanup-ack-{task_id}", p_menu_id),
            )

        # 清理測試中可能產生的重複客戶資料
        cursor.execute(
            "SELECT id FROM clients WHERE id NOT IN (%s, %s, %s) AND (phone IN ('0912345678', '0922333444', '0933111222') OR name IN ('陳雅婷', '林怡君', '李詩涵'))",
            (c1_id, c2_id, c3_id)
        )
        fetchall = getattr(cursor, "fetchall", None)
        extra_clients = fetchall() if callable(fetchall) else []
        extra_client_ids = [
            r["id"] for r in extra_clients
            if isinstance(r, dict) and "id" in r
        ]
        if extra_client_ids:
            format_strings = ','.join(['%s'] * len(extra_client_ids))
            cursor.execute(f"DELETE FROM provisional_client_registrations WHERE client_id IN ({format_strings})", tuple(extra_client_ids))
            cursor.execute(f"DELETE FROM client_profile_change_requests WHERE client_id IN ({format_strings})", tuple(extra_client_ids))
            cursor.execute(f"DELETE FROM clients WHERE id IN ({format_strings})", tuple(extra_client_ids))

        cursor.execute("UPDATE clients SET line_user_id=NULL")
        cursor.execute("UPDATE staff SET line_user_id=NULL")
        cursor.execute("UPDATE provisional_client_registrations SET active_line_user_id=NULL")

        conn.commit()
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()

    # 5. 跨領域架構初始化 (Case Architecture Bootstrap)
    s_gen = get_case_architecture_bootstrap_status_service()
    w_gen = None
    try:
        status_service = next(s_gen)
        w_gen = get_case_architecture_bootstrap_workflow()
        workflow = next(w_gen)

        cases_bootstrapped = []
        for case_no in ["CASE-2026-M301", "CASE-2026-M302"]:
            status = status_service.query(case_no)
            if not status.ready and status.recommendation:
                correlation_id = CorrelationId(f"line-seed-prev-{case_no.lower()}")
                preview = workflow.preview(status.recommendation, correlation_id)
                cmd = EnsureCaseArchitectureBootstrap(
                    intent=status.recommendation,
                    expected_order_version=ExpectedVersion(1),
                    preview_fingerprint=preview.fingerprint,
                    idempotency_key=IdempotencyKey(f"line-seed-idem-{case_no.lower()}"),
                    actor=ActorContext(actor_id="admin", permission_scope=("admin", "system_admin")),
                    reason="LINE 模組測試前置架構初始化",
                    correlation_id=CorrelationId(f"line-seed-corr-{case_no.lower()}"),
                )
                workflow.ensure(cmd)
                cases_bootstrapped.append(case_no)
    finally:
        try:
            if w_gen is not None:
                w_gen.close()
        finally:
            s_gen.close()

    result = {
        "status": "ready",
        "client_1": {"id": c1_id, "name": "陳雅婷", "phone": "0912345678", "case_no": "CASE-2026-M301"},
        "client_2": {"id": c2_id, "name": "林怡君", "phone": "0922333444", "case_no": "CASE-2026-M302"},
        "client_3": {"id": c3_id, "name": "李詩涵", "phone": "0933111222", "case_no": "CASE-2026-STATE-B"},
        "staff_1": {"id": s1_id, "name": "王美華", "identity_card": "A234567890", "birthday": "1980-05-15", "phone": "0923456789"},
        "staff_2": {"id": s2_id, "name": "張淑芬", "identity_card": "B234567891", "birthday": "1982-08-20", "phone": "0934567890"},
        "bootstrapped_cases": cases_bootstrapped,
    }

    if verbose:
        print("================================================================================")
        print("✅ LINE 四大模組測試前置資料復原完成！")
        print("================================================================================")
        print("📱 測試客戶 1 (【狀態 A：舊客完全命中】/ M3 主測)：")
        print("   - 姓名：陳雅婷")
        print("   - 手機：0912345678")
        print("   - 案件：CASE-2026-M301 (服務期間 2026-10-05 ~ 2026-11-03)")
        print("   - 預期效果：bind.html 輸入後自動完成綁定，顯示 CASE-2026-M301，無需重填問卷！")
        print("--------------------------------------------------------------------------------")
        print("📱 測試客戶 3 (【狀態 B：有案號但缺問卷】專用測試)：")
        print("   - 姓名：李詩涵")
        print("   - 手機：0933111222")
        print("   - 案件：CASE-2026-STATE-B")
        print("   - 預期效果：bind.html 輸入後提示找到案號，自動預填 姓名+電話+案號 跳轉問卷！")
        print("--------------------------------------------------------------------------------")
        print("📱 測試月嫂 1 (M1-04 / M3 主測)：")
        print("   - 姓名：王美華")
        print("   - 身分證字號：A234567890")
        print("   - 出生年月日：1980-05-15")
        print("   - 手機：0923456789")
        print("--------------------------------------------------------------------------------")
        print("📱 測試月嫂 2 (M3 第二候選月嫂)：")
        print("   - 姓名：張淑芬")
        print("   - 身分證字號：B234567891")
        print("   - 出生年月日：1982-08-20")
        print("================================================================================")

    return result


if __name__ == "__main__":
    seed_fixtures()
