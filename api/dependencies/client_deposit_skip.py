from dataclasses import dataclass
from infrastructure.mysql.client_deposit_skip_repository import MySqlClientDepositSkipRepository,UnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.deposit_skip_workflow import DepositSkipWorkflow
from subsystems.orders.client_finance_outbox_consumer import consume_client_finance_orders_case_override
@dataclass(slots=True)
class Application:
    workflow:DepositSkipWorkflow
    connection:object
    def preview(self,s):return self.workflow.preview(s)
    def apply(self,r):
        receipt=self.workflow.apply(r)
        consume_client_finance_orders_case_override(self.connection,r.selection.case_no)
        return receipt
def get_client_deposit_skip_application():
    c=get_connection(); repo=MySqlClientDepositSkipRepository(c)
    try:yield Application(DepositSkipWorkflow(repo,lambda:UnitOfWork(c)),c)
    finally:c.close()
