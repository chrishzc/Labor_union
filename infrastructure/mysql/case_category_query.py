"""
File: case_category_query.py
Description: 依已綁定定價規則與身分分類別名提供唯讀案件類別 SQL 表達式。
"""

BOUND_POLICY_IDENTITY_SQL = """CASE
 WHEN JSON_SEARCH(p.policy_json,'one','一般市民',NULL,'$.identities[*].identity_name') IS NOT NULL
 THEN CASE c.identity_status WHEN '社福' THEN '補助市民' WHEN '低收入戶' THEN '補助市民'
      WHEN '中低收入戶' THEN '補助市民' WHEN '原民' THEN '原住民' WHEN '原住民市民' THEN '原住民'
      ELSE c.identity_status END
 ELSE CASE c.identity_status WHEN '一般市民' THEN '補助市民' WHEN '低收入戶' THEN '社福'
      WHEN '中低收入戶' THEN '社福' WHEN '原民' THEN '原住民' WHEN '原住民市民' THEN '原住民'
      ELSE c.identity_status END END"""

CASE_CATEGORY_SQL = f"""CASE WHEN COALESCE(
 (SELECT JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.rule'))
  FROM case_pricing_events e WHERE e.id=o.pricing_override_event_id AND e.case_no=o.case_no),
 (SELECT j.identity_rule FROM accounting_pricing_policies p
  JOIN JSON_TABLE(p.policy_json,'$.identities[*]' COLUMNS(
    identity_name VARCHAR(100) PATH '$.identity_name',
    identity_rule VARCHAR(32) PATH '$.rule')) j
  WHERE p.id=o.pricing_policy_id AND BINARY j.identity_name=BINARY {BOUND_POLICY_IDENTITY_SQL} LIMIT 1),
 CASE WHEN c.identity_status='非市民' THEN 'non_citizen' ELSE 'citizen' END
)='non_citizen' THEN 'non_citizen' ELSE 'subsidy' END"""
