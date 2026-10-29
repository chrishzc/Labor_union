"""Read-only classification from the bound pricing rule, then legacy identity.

The aliases are fixed by the three consuming owner queries (orders o, clients c).
No classification depends on the spelling of a case number.
"""

CASE_CATEGORY_SQL = """CASE WHEN COALESCE(
 (SELECT JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.rule'))
  FROM case_pricing_events e WHERE e.id=o.pricing_override_event_id AND e.case_no=o.case_no),
 (SELECT j.identity_rule FROM accounting_pricing_policies p
  JOIN JSON_TABLE(p.policy_json,'$.identities[*]' COLUMNS(
    identity_name VARCHAR(100) PATH '$.identity_name',
    identity_rule VARCHAR(32) PATH '$.rule')) j
  WHERE p.id=o.pricing_policy_id AND BINARY j.identity_name=BINARY CASE c.identity_status
    WHEN '一般市民' THEN '補助市民' WHEN '低收入戶' THEN '社福'
    WHEN '中低收入戶' THEN '社福' ELSE c.identity_status END LIMIT 1),
 CASE WHEN c.identity_status='非市民' THEN 'non_citizen' ELSE 'citizen' END
)='non_citizen' THEN 'non_citizen' ELSE 'subsidy' END"""
