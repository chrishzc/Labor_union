from scripts.reconcile_fixture_order_dates_v2 import reconcile
def test_current_database_dates_are_aligned():
    r=reconcile(False)
    assert r["scanned"]==50 and r["unchanged"]==50 and r["would_update"]==0
