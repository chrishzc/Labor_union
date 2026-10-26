from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from api.dependencies import admin_auth
from api.dependencies.service_start import get_service_start_application
from api.routes import service_start,matching_schedule_confirmation
from subsystems.access.authentication_session import AdminPrincipal
from api.schemas.line_order_change import LineOrderChangePreviewRequest
from subsystems.line.message_preview_samples import current_message_sample

@pytest.mark.parametrize('role,status',[('line_manager',200),('staff',403),('line_viewer',200)])
def test_union_capability_allows_current_operations_and_rejects_other_audiences(role,status):
 app=FastAPI();app.include_router(service_start.router)
 app.dependency_overrides[admin_auth.require_admin]=lambda:AdminPrincipal(1,'synthetic','測試',role)
 app.dependency_overrides[get_service_start_application]=lambda:SimpleNamespace(todos=lambda *_:((),0))
 with TestClient(app) as http:assert http.get('/api/v1/scheduling/service-start/todos').status_code==status


def test_retired_confirmation_api_has_no_mutation():
 app=FastAPI();app.include_router(matching_schedule_confirmation.router)
 app.dependency_overrides[admin_auth.require_line_matching_override]=lambda:AdminPrincipal(1,'synthetic','測試','line_manager')
 from api.dependencies.matching_schedule_confirmation import get_matching_schedule_confirmation_workflow
 app.dependency_overrides[get_matching_schedule_confirmation_workflow]=lambda:object()
 with TestClient(app) as http:
  response=http.post('/api/v1/orders/CASE/matching-plans/1/schedule-confirmation/send',headers={'Idempotency-Key':'synthetic'})
  assert response.status_code==410


def test_customer_retired_date_kind_is_rejected_at_transport_before_any_command():
 with pytest.raises(ValidationError):
  LineOrderChangePreviewRequest(line_id_token='synthetic',case_no='CASE',expected_order_version=1,kind='service_days',requested={'start_date':'2027-01-05'})


def test_public_preview_uses_current_buttons_and_buttonless_result():
 inquiry,_=current_message_sample('service-start-inquiry');result,_=current_message_sample('service-start-result')
 assert [button['action']['label'] for button in inquiry['contents']['footer']['contents']]==['願意代班','無法代班']
 assert result['type']=='text' and '服務日期安排' in result['text']
 assert 'action' not in result and '確認' not in result['text']


@pytest.mark.parametrize('status,visible',[(s,s in ('洽談中','訂單成立','服務中')) for s in
 ('待補件','洽談中','訂單成立','服務中','訂單取消','訂單完成','歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成')])
def test_pending_service_todos_only_include_cases_the_apply_can_handle(status,visible):
 import sqlite3
 from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;c.create_function('JSON_UNQUOTE',1,lambda value:value)
 c.executescript('CREATE TABLE orders(case_no TEXT,status TEXT); CREATE TABLE scheduling_service_start_requests(id INTEGER,case_no TEXT,status TEXT,execution_dates TEXT,staff_id INTEGER,segment_id INTEGER,assignment_id INTEGER);')
 c.execute('INSERT INTO orders VALUES(?,?)',('CASE',status))
 c.execute('INSERT INTO scheduling_service_start_requests VALUES(1,?,?,?,?,NULL,NULL)',('CASE','substitute_required','{"kind":"leave-v1"}',1))
 class Cursor:
  def __enter__(self):self.cursor=c.cursor();return self
  def __exit__(self,*args):self.cursor.close()
  def execute(self,sql,params=()):
   assert sql.lstrip().upper().startswith('SELECT');self.cursor.execute(sql.replace('%s','?').replace('<=>',' IS '),params)
  def fetchone(self):return dict(self.cursor.fetchone())
  def fetchall(self):return [dict(r) for r in self.cursor.fetchall()]
 repo=MySqlServiceStartRepository(SimpleNamespace(cursor=Cursor));repo.view=lambda identity:identity
 items,total=repo.todos(1,25)
 assert bool(items) is visible and total==int(visible)
 c.close()
