"""Read-only availability follows target, Admin and canonical LINE facts together."""
from contextlib import contextmanager
import sqlite3
from types import SimpleNamespace
import pytest
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from subsystems.line.runtime_alert_target_application import RuntimeAlertTargetApplication

class Cursor:
    def __init__(self, connection): self.cursor=connection.cursor()
    def __enter__(self): return self
    def __exit__(self,*args): self.cursor.close()
    def execute(self,sql,params=()):
        assert sql.lstrip().upper().startswith('SELECT')
        self.cursor.execute(sql.replace('%s','?').replace(' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci',' AS TEXT)'),params)
    def fetchone(self): return self.cursor.fetchone()

@pytest.mark.parametrize('target,admin,owner,binding_status,binding_line,role,available',[
    (1,1,'U-test','bound','U-test','admin',True),
    (0,1,'U-test','bound','U-test','admin',False),
    (1,0,'U-test','bound','U-test','admin',False),
    (1,1,None,'bound','U-test','admin',False),
    (1,1,'U-test','revoked','U-test','admin',False),
    (1,1,'U-test','pending_review','U-test','admin',False),
    (1,1,'U-other','bound','U-test','admin',False),
    (1,1,'U-test','bound','U-test','customer',False),
])
def test_available_target_needs_all_current_facts(target,admin,owner,binding_status,binding_line,role,available):
    c=sqlite3.connect(':memory:')
    c.executescript('''CREATE TABLE line_alert_notification_targets(id INTEGER,target_type TEXT,admin_user_id INTEGER,enabled INTEGER);
      CREATE TABLE admin_users(id INTEGER,enabled INTEGER,linked_line_user_id TEXT);
      CREATE TABLE line_identity_role_bindings(subject_type TEXT,subject_reference TEXT,binding_status TEXT,line_user_id TEXT);''')
    c.execute("INSERT INTO line_alert_notification_targets VALUES(1,'admin_user',1,?)",(target,))
    c.execute('INSERT INTO admin_users VALUES(1,?,?)',(admin,owner))
    c.execute('INSERT INTO line_identity_role_bindings VALUES(?,?,?,?)',(role,'1',binding_status,binding_line))
    repository=MySqlRuntimeMonitorRepository(SimpleNamespace(cursor=lambda:Cursor(c)))
    @contextmanager
    def uow(): yield SimpleNamespace(runtime_monitor=repository)
    before=c.total_changes
    assert RuntimeAlertTargetApplication(uow,lambda:None).has_available_admin_target() is available
    assert c.total_changes==before
    c.close()
