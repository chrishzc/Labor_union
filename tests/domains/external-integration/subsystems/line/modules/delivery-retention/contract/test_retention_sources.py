"""Expired original/replay source lineage cannot recreate cleared notifications."""
import sqlite3
from types import SimpleNamespace
import pytest
from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository, LineNotificationManualReplayValidationError

class Cursor:
    def __init__(self,connection):self.c=connection.cursor()
    def __enter__(self):return self
    def __exit__(self,*args):self.c.close()
    def execute(self,sql,params=()):return self.c.execute(sql.replace('%s','?'),params)
    def fetchone(self):return self.c.fetchone()

@pytest.mark.parametrize('identity,domain', [('original','orders'),('manual-replay:11:synthetic','manual_replay')])
def test_original_and_exact_replay_history_is_blocked_but_other_source_is_not(identity,domain):
    db=sqlite3.connect(':memory:')
    db.create_function('JSON_UNQUOTE',1,lambda value: 'true' if value==1 else 'false' if value==0 else value)
    try:
        db.executescript("CREATE TABLE line_notification_source_events(id INTEGER,source_domain TEXT,source_event_identity TEXT);CREATE TABLE line_notification_decisions(id INTEGER,source_event_id INTEGER);CREATE TABLE line_notification_intents(decision_id INTEGER,delivery_task_id INTEGER);CREATE TABLE line_delivery_tasks(id INTEGER,payload_snapshot TEXT);")
        source_id=11 if domain=='orders' else 12
        db.execute('INSERT INTO line_notification_source_events VALUES(?,?,?)',(source_id,domain,identity))
        db.execute('INSERT INTO line_notification_decisions VALUES(1,?)',(source_id,))
        db.execute('INSERT INTO line_notification_intents VALUES(1,5)')
        db.execute('INSERT INTO line_delivery_tasks VALUES(5,?)',('{"_retention_expired":true}',))
        repo=MySqlLineNotificationRepository(SimpleNamespace(cursor=lambda:Cursor(db)))
        assert repo._source_history_expired(11) is True
        assert repo._source_history_expired(1) is False
        assert repo._source_history_expired(110) is False
        repo._source_closed=lambda _:False
        with pytest.raises(LineNotificationManualReplayValidationError,match='notification_source_history_expired'):
            repo._validate_manual_replay(11,object(),None)
        db.execute("UPDATE line_delivery_tasks SET payload_snapshot='{}'")
        assert repo._source_history_expired(11) is False
    finally:db.close()
